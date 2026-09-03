=============================================================================
_PyEval_EvalFrameDefault 执行状态机、Direct Threaded Code 与指令分发
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解构了 CPython 3.13+ 的物理栈帧结构 ``_PyInterpreterFrame``、线程私有数据栈（``_PyStackChunk``）上的 Bump Pointer 极速分配机制，以及局部变量与求值栈在 ``localsplus`` 中的单调排布。当函数的参数与栈帧初始化完毕后，虚拟机便进入了最核心的物理循环——**解释器执行状态机（CEval Loop）**。
   
   作为 Python 虚拟机的“心脏”，``Python/ceval.c`` 中的 ``_PyEval_EvalFrameDefault`` 函数负责以极速循环取指、解码并执行字节码序列。本章将深入 CPython 核心源码文件 ``Python/ceval.c``、``Python/ceval_macros.h``、``Include/internal/pycore_ceval.h`` 以及 ``Python/opcode_targets.h``，深度剖析解释器主循环的“寄存器化”上下文、从经典 Switch-Case 到 Direct Threaded Code（计算跳转）以及现代 Tail-Call Dispatch（尾调用分发）的分发机制革命、基于 64 位原子位图 ``eval_breaker`` 的全局异步中断/GIL/GC 调度状态机，以及 Tier 1 与 Tier 2 执行引擎之间的平滑切换接口。

-----------------------------------------------------------------------------
1. _PyEval_EvalFrameDefault 的微观物理状态机
-----------------------------------------------------------------------------

``_PyEval_EvalFrameDefault`` 是 CPython 默认的字节码求值引擎入口。为了榨干现代 CPU 架构的全部算力，该函数在进入主循环前，会将栈帧与解释器的核心指针“寄存器化（Register Allocation）”：

.. code-block:: c

   PyObject* _Py_HOT_FUNCTION
   _PyEval_EvalFrameDefault(PyThreadState *tstate, _PyInterpreterFrame *frame, int throwflag)
   {
       /* 1. 核心虚拟 CPU 寄存器 (由编译器直接分配至 CPU 物理通用寄存器) */
       _Py_CODEUNIT *next_instr;         /* 程序计数器 PC / 指令指针 IP */
       _PyStackRef  *stack_pointer;      /* 求值栈顶指针 SP (TOS) */
       uint8_t      opcode;              /* 当前 8 位操作码 */
       int          oparg;               /* 当前指令操作数 */

       /* 2. 构造解释器哨兵入口帧 (_PyEntryFrame) */
       _PyEntryFrame entry;
       entry.frame.owner = FRAME_OWNED_BY_INTERPRETER;
       entry.frame.instr_ptr = (_Py_CODEUNIT *)_Py_INTERPRETER_TRAMPOLINE_INSTRUCTIONS + 1;
       entry.frame.previous = tstate->current_frame;
       frame->previous = &entry.frame;
       tstate->current_frame = frame;

       /* 3. 初始加载栈帧寄存器 */
       next_instr = frame->instr_ptr;
       stack_pointer = _PyFrame_GetStackPointer(frame);

       /* 4. 跳转进入主分发状态机 */
       DISPATCH();
   }

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                虚拟 CPU 核心寄存器与物理硬件映射关系                    |
   +====================+==========================+=========================+
   | 虚拟机抽象概念     | CPython 局部变量         | 物理寄存器典型映射      |
   |                    |                          | (ARM64 / x86-64)        |
   +--------------------+--------------------------+-------------------------+
   | 程序计数器 (PC)    | next_instr               | x19 / %r12              |
   +--------------------+--------------------------+-------------------------+
   | 栈顶指针 (SP)      | stack_pointer            | x20 / %r13              |
   +--------------------+--------------------------+-------------------------+
   | 当前栈帧基址 (FP)  | frame                    | x21 / %r14              |
   +--------------------+--------------------------+-------------------------+
   | 线程上下文 (TLS)   | tstate                   | x22 / %r15              |
   +--------------------+--------------------------+-------------------------+

通过将这些最高频访问的指针固定在硬件寄存器中，解释器在执行绝大多数算术、入栈、出栈指令时，均无需访问 C 机器栈内存，使字节码指令的处理延迟降低至物理硬件极限。

-----------------------------------------------------------------------------
2. 指令分发机制的演进：Switch-Case $	o$ Computed Goto $	o$ Tail-Call
-----------------------------------------------------------------------------

解释器每执行完一条指令，必须决定“下一条指令跳转至何处”。分发机制的效率直接决定了 Python 的运行吞吐。

第一代：传统 Switch-Case 分发（Central Switch Dispatch）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   while (1) {
       opcode = next_instr->op.code;
       switch (opcode) {
           case LOAD_FAST:  ... break;
           case BINARY_OP:  ... break;
       }
   }

- **硬件瓶颈**：C 编译器会将 ``switch`` 编译为单一的集中式间接跳转指令（``jmp *table[opcode]``）。
  在现代超标量 CPU 的**分支目标预测器（Branch Target Buffer, BTB）**看来，整个解释器中数以亿计的指令跳转全部挤在同一个物理跳转地址上，导致 BTB 频繁发生冲突失效率（Prediction Miss 率高达 80%~90%），每次预测失败都会导致 CPU 渲染管线彻底清空并产生 15~20 个周期的严重停顿！

第二代：Direct Threaded Code（基于计算跳转 Computed Goto）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了打破 BTB 冲突，CPython 引入了基于 GCC/Clang 扩展的 **Direct Threaded Code（标签即值）**：

.. code-block:: c

   /* static jump table: opcode_targets.h */
   static const void *opcode_targets_table[256] = {
       [LOAD_FAST] = &&TARGET_LOAD_FAST,
       [BINARY_OP] = &&TARGET_BINARY_OP,
       ...
   };

   #define DISPATCH() do {                                   \
       _Py_CODEUNIT word = *next_instr++;                    \
       opcode = word.op.code;                                \
       oparg = word.op.arg;                                  \
       goto *opcode_targets[opcode];                         \
   } while (0)

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Direct Threaded Code 物理分发拓扑                        |
   +=========================================================================+
   | TARGET_LOAD_FAST:                                                       |
   |   *stack_pointer++ = frame->localsplus[oparg];                          |
   |   DISPATCH(); ──► [间接跳转 A: 预测 LOAD_FAST 的下一条指令]             |
   +-------------------------------------------------------------------------+
   | TARGET_BINARY_OP:                                                       |
   |   ... 执行加法 ...                                                      |
   |   DISPATCH(); ──► [间接跳转 B: 预测 BINARY_OP 的下一条指令]             |
   +-------------------------------------------------------------------------+

- **硬件优势**：每条操作码的末尾都独立内联了一份跳转指令。由于跳转指令分散在不同的内存地址，CPU 的分支预测器能够分别记录每种指令之后最可能紧随的下一条操作码（例如预测 ``LOAD_FAST`` 后面通常紧随 ``BINARY_OP``），使 BTB 预测成功率大幅提升，直接带来 **15%~20% 的纯性能提升**！

第三代：Python 3.13+ Tail-Call Dispatch（尾调用分发架构）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Python 3.13 中，CPython 引入了实验性的 **尾调用解释器（``_Py_TAIL_CALL_INTERP``）**，结合 Clang/GCC 的 ``__attribute__((musttail))`` 与 ``__attribute__((preserve_none))`` 调用约定：

.. code-block:: c

   typedef PyObject *(Py_PRESERVE_NONE_CC *py_tail_call_funcptr)(
       _PyInterpreterFrame *frame, _PyStackRef *stack_pointer,
       PyThreadState *tstate, _Py_CODEUNIT *next_instr,
       const void *instruction_funcptr_table, int oparg);

   #define DISPATCH_GOTO()                                                   \
       do {                                                                  \
           Py_MUSTTAIL return (((py_tail_call_funcptr *)                     \
               instruction_funcptr_table)[opcode])(TAIL_CALL_ARGS);           \
       } while (0)

- **优势**：将庞大冗长（数千行）的单一 ``_PyEval_EvalFrameDefault`` 函数拆分为数百个独立的 C 函数。利用编译器极佳的寄存器着色算法，消除了单个巨型函数造成的寄存器溢出（Register Spilling）损耗。

-----------------------------------------------------------------------------
3. Eval Breaker 中断状态机与异步事件调度
-----------------------------------------------------------------------------

在解释器高速循环执行字节码时，虚拟机必须同时响应来自外界的多种异步事件：
1. **操作系统信号（Signals）**：如用户在终端按下 ``Ctrl+C`` 触发的 ``SIGINT``；
2. **全局解释器锁抢占（GIL Drop Request）**：其他线程请求释放 GIL；
3. **异步异常注入（Async Exceptions）**：如 ``ctypes.pythonapi.PyThreadState_SetAsyncExc``；
4. **分代垃圾回收触发（GC Scheduled）**；
5. **自由线程全局停顿（Stop-the-World）**：Free-Threading 下 GC 发起的挂起请求。

.. warning:: 为什么不能在每条指令执行时都进行系统调用或加锁轮询？
   系统调用与互斥锁检查会摧毁 CPU 流水线。CPython 采用 **64 位原子位图 ``eval_breaker`` 状态机**，将所有外部事件统一折叠为一个单周期的位掩码测试。

eval_breaker 原子位图拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``Include/internal/pycore_ceval.h`` 中，定义了以下关键位域：

.. code-block:: c

   #define _PY_GIL_DROP_REQUEST_BIT          (1U << 0)  /* GIL 释放请求 */
   #define _PY_SIGNALS_PENDING_BIT           (1U << 1)  /* 挂起的操作系统信号 */
   #define _PY_CALLS_TO_DO_BIT               (1U << 2)  /* 待处理的异步 C 回调 */
   #define _PY_ASYNC_EXCEPTION_BIT           (1U << 3)  /* 异步异常注入 */
   #define _PY_GC_SCHEDULED_BIT              (1U << 4)  /* GC 回收触发 */
   #define _PY_EVAL_PLEASE_STOP_BIT          (1U << 5)  /* Free-Threading 全局停顿 */

.. code-block:: text

   [主解释器循环正常执行]
             │
             ├─► 执行无跳转指令: 完全不检查 eval_breaker (零开销!)
             │
             ▼
   [遇到循环回跳 / 函数调用边界 (CHECK_EVAL_BREAKER)]
             │
             ▼
   原子加载 _Py_atomic_load_uintptr_relaxed(&tstate->eval_breaker)
             │
             ├─► eval_breaker == 0: 毫无中断，继续全速直行！
             │
             └─► eval_breaker != 0: 触发中断！
                   │
                   ▼ (跳出快速循环，转入慢速服务子系统)
              _Py_HandlePending(tstate):
              ├── 若命中 SIGNALS_PENDING ──► 执行 Python 信号处理函数
              ├── 若命中 GIL_DROP_REQUEST ──► 释放当前 GIL，主动让渡 CPU
              └── 若命中 PLEASE_STOP     ──► 进入挂起睡眠，等待 GC 恢复

这种机制保证了在 99.999% 的指令执行过程中，解释器处于完全零额外开销的直行状态；仅在回跳指令与函数调用边界处，以 1 条 CPU 周期指令精准拦截所有异步事件。

-----------------------------------------------------------------------------
4. Tier 1 与 Tier 2 / JIT 之间的双向执行流切换
-----------------------------------------------------------------------------

在 Python 3.13+ 中，解释器形成了多层次执行架构：
- **Tier 1**：传统的字节码直译执行（带 PEP 659 自适应特化）；
- **Tier 2**：由微指令（uops）构成的 Trace 执行器（``_PyTier2Interpreter``）；
- **JIT**：直接由 Copy-and-Patch 生成的机器码执行。

在 ``ceval_macros.h`` 中，定义了跨层穿梭的高速宏：

.. code-block:: text

   [Tier 1 解释器循环]
            │
            ├─► 遇到热点循环跳转 (JUMP_BACKWARD)
            ├─► 命中已编译的 Tier 2 Executor / JIT Entry
            │
            ▼ TIER1_TO_TIER2(EXECUTOR)
   [切入 Tier 2 微指令解释器 / JIT 机器码高速执行]
            │
            ├─► 守卫断言成功 (Guard Hit): 继续在 JIT/Tier 2 中全速运行
            │
            └─► 守卫断言失败 (Guard Failure / Deopt):
                  │
                  ▼ GOTO_TIER_ONE(TARGET)
   [现场恢复 frame->instr_ptr 与 stackpointer，平滑回退至 Tier 1 字节码]

这种分层设计确保了无论是高度动态的偶发代码，还是规律运行的密集热点循环，都能在同一套栈帧结构上无缝切换执行引擎，实现吞吐量与动态性的完美平衡。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 主解释器循环的微观物理运行状态机：
1. ``_PyEval_EvalFrameDefault`` 的虚拟 CPU 核心寄存器与物理硬件寄存器绑定；
2. 指令分发机制从早期容易导致 BTB 冲突的 Switch-Case，进化到 Direct Threaded Code（Computed Goto），再到现代 Tail-Call Dispatch 的演进历程与分支预测优势；
3. 基于 64 位原子位图 ``eval_breaker`` 的中断状态机如何兼顾零开销直行与精准处理异步信号、GIL 释放、GC 调度与 Stop-the-World 全局停顿；
4. Tier 1 解释器与 Tier 2 / JIT 之间的执行流穿梭与去优化（Deopt）回退链路。

在纯解释执行之外，现代 CPython 的核心性能秘诀在于其能够根据运行时的数据流特征自我演化。在下一章中，我们将深入—— **03_frame_and_eval_loop/03_specialized_adaptive_interpreter.rst（PEP 659 自适应指令特化机制 Adaptive Bytecode 与 Quickening 状态转换）**。
