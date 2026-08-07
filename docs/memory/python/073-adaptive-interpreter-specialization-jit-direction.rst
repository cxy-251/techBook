第073章：Adaptive Interpreter, Specialization, and JIT Direction
================================================================

核心知识点
----------

* Python 源码先编译成 bytecode，CPython 再在运行时根据真实对象形状反馈，对部分热点指令进行 specialization。
* PEP 659 的核心模型是：通用 opcode → adaptive/quickened 状态 → specialized opcode → guard 命中 fast path；guard 失败时回退并更新计数器。
* specialization 的对象不是整个函数，而通常是某个具体 instruction position。相同 opcode 出现在两个位置，可以因为运行时输入不同而拥有不同特化状态。
* inline cache 紧贴指令保存 fast path 所需事实，例如类型/字典版本、属性位置、调用形状、计数器等。cache 保存的是“当前快速假设”，不是 Python 语义本身。
* ``LOAD_ATTR``、``LOAD_GLOBAL``、``BINARY_OP``、调用相关 opcode 都可根据运行时稳定性走更窄路径；动态性增加时会发生 miss 或 deoptimization。
* deoptimization 边界很小：某条指令的 guard 失效，只需让这一次操作回到通用语义，并降低该位置的特化置信度，而不是撤销整个函数。
* 性能收益来自减少重复查找、协议分派、分支和临时对象路径；语义正确性来自 guard 失败后仍能回到完整 Python 语义。
* ``dis(..., adaptive=True, show_caches=True)`` 可用于观察当前解释器的特化结果，但输出高度版本敏感。
* Python 3.13 之后的实验性 JIT 方向建立在 specialization 之上：Tier 1 specialized bytecode → Tier 2 micro-op/IR trace → 优化 → 可选机器码。
* copy-and-patch JIT 使用预生成机器码模板，在运行时复制并补入常量、地址、缓存值和跳转目标，以降低运行时编译成本。
* JIT、Tier 2、specialized opcode 都属于 CPython 实现层；Python 语义、对象协议和异常结果必须保持一致。

关键路径
--------

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

热点代码继续进入未来优化层时，可概括为：

.. code-block:: text

   Tier 1 specialized bytecode
        ↓
   hot-path detection
        ↓
   Tier 2 micro-ops / IR
        ↓
   optimization passes
        ↓
   JIT enabled ?
      ├─ no  → Tier 2 interpreter
      └─ yes → copy-and-patch native trace

排查某段热点 Python 代码时，先找重复执行的动态操作，再看对象类型、属性布局、global namespace、call shape 是否稳定，最后才看当前版本具体 specialized opcode。

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

**Tier 2/JIT 与语言规范**
   JIT 改变执行器形态和性能成本，不应改变 attribute lookup、数值协议、异常传播等可见语义。

本章结论
--------

Adaptive interpreter 的稳定模型是“动态语义 + 局部运行时反馈”。热点指令先观察对象形状，再用 inline cache 和 guard 走专用 fast path；形状变化就回到通用路径。JIT 方向继续消费这层反馈，把稳定 trace 下沉到 micro-op 和机器码，但任何优化都必须以可回退、可验证的 Python 语义为边界。
