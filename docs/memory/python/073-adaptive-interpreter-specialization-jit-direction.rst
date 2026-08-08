第073章：Adaptive Interpreter, Specialization, and JIT Direction
================================================================

核心知识点
----------

* Python 源码先编译成 bytecode，CPython 再在运行时根据真实对象形状反馈，对部分热点指令进行 specialization。
* PEP 659 的稳定模型是：通用 opcode → adaptive/quickened 状态 → specialized opcode → guard 命中 fast path；guard 失败时回退并更新计数器。
* specialization 的对象不是整个函数，而通常是某个具体 instruction position。相同 opcode 出现在两个位置，可以因为运行时输入不同而拥有不同特化状态。
* inline cache 紧贴指令保存 fast path 所需事实，例如类型/字典版本、属性位置、调用形状、计数器等。cache 保存的是“当前快速假设”，不是 Python 语义本身。
* ``LOAD_ATTR``、``LOAD_GLOBAL``、``BINARY_OP``、调用相关 opcode 都可根据运行时稳定性走更窄路径；动态性增加时会发生 miss 或 deoptimization。
* deoptimization 边界很小：某条指令的 guard 失效，只需让这一次操作回到通用语义，并降低该位置的特化置信度，而不是撤销整个函数。
* 性能收益来自减少重复查找、协议分派、分支和临时对象路径；语义正确性来自 guard 失败后仍能回到完整 Python 语义。
* ``dis(..., adaptive=True, show_caches=True)`` 可用于观察当前解释器的特化结果，但 opcode、cache layout 和输出都高度版本敏感。
* CPython 的实验性 JIT 建立在 specialization 与 Tier 2 micro-op/trace 基础之上：``Tier 1 specialized bytecode → Tier 2 representation → optimization → optional native code``。
* Python 3.14 的官方 macOS/Windows 二进制已经可以包含实验性 JIT，但它仍处于早期阶段、默认关闭，不建议作为生产性能前提；可通过 ``PYTHON_JIT`` 和 ``sys._jit`` 判断支持与启用状态。
* Python 3.14 当前的 free-threaded build 不支持 JIT compilation。free-threading 与 JIT 是两条独立演进路线，不能把二者合并成一个默认 runtime 层级。
* JIT 的实际性能不是单向提升；当前版本可能因 workload 不同出现回退或收益，因此基准必须记录 Python 版本、build 选项、JIT enabled 状态与 workload。
* 当前实验性 JIT 对原生 debugger/profiler 的 JIT frame unwind 仍有限制；解释器级工具与 native tooling 的可观测性边界不同。
* copy-and-patch 等机器码生成方式属于 CPython 当前实现方向，未来 JIT backend、IR、trace 组织和启用策略仍可能变化。
* JIT、Tier 2、specialized opcode 都属于 CPython 实现层；Python 语义、对象协议和异常结果必须保持一致。

关键路径
--------

Specialization：

.. code-block:: text

   generic bytecode
        ↓
   quickening / adaptive state
        ↓
   runtime observations
        ↓
   specialization attempt
        ↓
   specialized opcode + inline cache
        ↓
      guard
      ├─ hit  → fast path
      └─ miss → generic path / counter update
                     ↓
              possible deopt

Python 3.14 的执行层判断：

.. code-block:: text

   CPython build
      ↓
   specialization available
      ↓
   Tier 2 / experimental JIT support compiled in ?
      ├─ no  → interpreter path
      └─ yes → JIT enabled for this process ?
                  ├─ no  → interpreter / Tier 2 path
                  └─ yes → experimental native trace path

   free-threaded build ?
      └─ yes → current 3.14 JIT path unavailable

排查某段热点代码时，先确认 Python 版本、GIL/free-threaded build 和 JIT 状态，再看对象类型、属性布局、global namespace、call shape 是否稳定，最后才分析当前版本具体 opcode 或 trace。

概念辨析
--------

**specialization 与静态编译**
   specialization 依赖运行时真实输入，对已有 bytecode 的局部执行路径收窄；它没有把 Python 代码静态变成固定类型程序。

**inline cache 与普通业务缓存**
   inline cache 缓存解释器执行前提，例如类型或命名空间结构；它不缓存业务函数返回值。

**guard failure 与语义失败**
   guard failure 只表示优化假设不再成立，解释器应回到 generic operation；它不是 Python 程序异常。

**deoptimization 与异常处理**
   deoptimization 是优化层回退；异常是语言运行时控制流。二者可以在同一执行路径附近发生，但含义不同。

**JIT available 与 JIT enabled**
   当前 executable 包含 JIT 支持，不代表进程已经启用 JIT；必须分别判断构建能力和运行状态。

**JIT experimental 与 production contract**
   Python 3.14 提供可实际测试的官方 JIT binary，不代表它已经成为稳定、默认或推荐生产使用的执行层。

**free-threaded 与 JIT**
   free-threaded 解决同一解释器多线程并行，JIT 优化热点执行；Python 3.14 当前两者不能组合使用。

本章结论
--------

Adaptive interpreter 的稳定模型是“动态语义 + 局部运行时反馈”。Specialization 已是现代 CPython 的核心执行机制；Tier 2 与 JIT 继续消费这些反馈，但 Python 3.14 的 JIT 仍是默认关闭的实验能力，并且当前不支持 free-threaded build。性能判断必须先确认版本、build 和运行状态，再讨论 opcode、trace 或 native code。