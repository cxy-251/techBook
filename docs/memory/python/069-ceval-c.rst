第069章：ceval.c
================

核心知识点
----------

* ``ceval.c`` 及其版本相关拆分文件是 CPython 执行器主线：它拿到当前 frame，读取 instruction，分派 opcode，维护 value stack/locals，并处理调用、返回、异常、暂停和 runtime 事件。
* evaluation loop 的输入是 frame，不是源码、AST 或 function object。function 调用先形成执行 frame，解释器再执行 frame 中的 code object。
* frame 的核心执行材料包括 code object、globals/builtins、locals/localsplus、value stack、instruction pointer 和异常相关状态。
* opcode 是局部状态变换。``LOAD_FAST`` 类指令从局部槽取对象，``STORE_FAST`` 写局部槽，binary operation 调用对象协议，``CALL`` 进入 callable dispatch，``RETURN_VALUE`` 结束当前 frame。
* value stack 保存表达式尚未消费的中间对象；fast locals 保存编译期已确定的局部绑定。二者用途不同。
* opcode dispatch 可以由 switch、computed goto 或生成代码实现；这属于 C 层分派优化，Python bytecode 语义不因此改变。
* 现代 CPython 会把 instruction 定义、生成 cases、metadata 和执行器拆分到多个文件。阅读目标应锁定 ``_PyEval_EvalFrameDefault`` 或目标版本等价入口，再追具体 instruction handler。
* PEP 659 specialization 让通用 opcode 在 hot/stable 输入上变成 specialized path。inline cache 保存类型、dict version、index、counter、call shape 等已验证运行时事实。
* specialized path 必须有 guard；guard 失败时必须回到通用语义或 deopt。specialization 改善常见路径成本，不改变 Python 语言结果。
* Python 3.11+ 的异常处理更依赖 exception table。正常路径不必为每个 ``try`` 维护传统 block stack；异常发生后解释器根据当前位置查找 handler，并恢复合适栈状态。
* eval breaker 是解释器处理线程切换请求、signals、pending calls、async exception、GC/运行时维护等慢路径的协调点。它不是“每条 opcode 都切线程”。
* generator/coroutine resume 仍进入 frame execution；区别是 frame 可以从 suspended state 恢复，并在 yield/await 时再次离开 evaluation loop。

关键路径
--------

函数执行：

::

    Python function call
        ↓
    argument binding + frame setup
        ↓
    interpreter frame
        ↓
    evaluation loop
        ↓
    fetch instruction
        ↓
    dispatch handler
        ↓
    update stack / locals / instruction pointer
        ↓
    next instruction

opcode handler 阅读顺序：

::

    opcode + operand
       ↓
    operand 从哪里取？
       ↓
    pop 几个 stack values？
       ↓
    调哪个 object protocol / helper？
       ↓
    push 几个结果？
       ↓
    是否修改 locals / jump / exception state？
       ↓
    下一 instruction

specialization：

::

    generic opcode
       ↓ execute repeatedly
    adaptive counter / feedback
       ↓
    specialization attempt
       ↓
    specialized opcode + inline cache
       ↓ each execution
    guard
      ├─ hit  → fast path
      └─ miss → generic/deopt path

异常：

::

    opcode/helper returns error
       ↓
    thread exception indicator set
       ↓
    current instruction offset
       ↓
    exception table lookup
       ↓
    restore stack / enter handler
       ├─ handled → continue evaluation
       └─ unhandled → unwind frame + traceback propagation

调用：

::

    CALL instruction
       ↓
    callable + args from stack
       ↓
    Python function fast path / vectorcall / tp_call
       ↓
    Python function → new/inlined interpreter frame
    C callable       → C API call path
       ↓
    result pushed to caller stack or error propagated

概念辨析
--------

* function object 是定义与调用材料，frame 是一次执行状态，evaluation loop 执行的是 frame。
* value stack 与 Python 调用栈不是一回事；前者是单个 frame 中的表达式操作数栈。
* opcode dispatch 与 object protocol 不同：dispatch 选择“执行哪条指令”，协议决定“当前对象怎样完成这项操作”。
* specialization 与 JIT 不是同一个概念；PEP 659 首先是解释器内 opcode specialization/inline cache。
* inline cache 命中不代表跳过语义检查，而是把重复动态查找压缩成少量 guards。
* eval breaker 是异步事件检查机制，不等于 OS scheduler 或业务锁。
* exception table 是编译产物，异常对象/indicator 是 runtime 状态；二者协作完成 handler 跳转。
* ``ceval.c`` 文件布局高度版本相关，稳定的是 frame → instruction → state transition 的模型。

本章结论
--------

CPython 执行器可以压缩成“frame 状态机 + opcode 局部变换”。每条 instruction 在 value stack、locals 和对象协议之间搬运状态；调用、返回、异常和暂停是离开当前直线路径的主要出口；specialization 用 guard 和 inline cache 缩短 hot path。读 ``ceval`` 时先锁定当前 frame，再逐条分析 stack effect 和协议调用，比追宏名或 goto 标签更可靠。