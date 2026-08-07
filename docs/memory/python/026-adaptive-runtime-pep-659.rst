第026章：Adaptive Runtime（PEP 659）
====================================

核心知识点
----------

* CPython 3.11 起引入 specializing adaptive interpreter：同一条通用 bytecode 可以在运行期根据真实对象形态变成更窄的 specialized opcode。
* 这套机制优化的是“重复确认动态事实”的成本，例如对象类型、属性位置、全局名字所在命名空间、调用目标和数值操作数类型。
* 一条热指令通常经历：通用 opcode → quickened/adaptive 形态 → specialized opcode；当假设失效时再回退到 adaptive 或通用路径。
* specialization 的粒度是“具体 code object 中的具体指令位置”，不是整段源码，也不是整个函数。
* inline cache 与指令相邻，保存快路径所需的运行时证据，例如 type/version、namespace keys version、属性位置或调用形态。
* adaptive counter 决定何时尝试特殊化、何时降低对当前假设的信任；稳定输入让 specialization 保持，频繁失配会触发 de-optimization。
* ``LOAD_ATTR``、``LOAD_GLOBAL``、``CALL``、``BINARY_OP`` 等动态分发频繁的指令族最适合做专门化。
* specialization 只能改变执行成本，不能改变 Python 语义。descriptor、``__getattribute__``、异常、名字解析和调用协议仍必须保持完整行为。
* ``dis.dis(..., adaptive=True, show_caches=True)`` 可以观察当前 CPython 的专门化和 cache 状态；具体 opcode 名称与 cache 布局属于版本敏感实现细节。
* 类型稳定、命名空间稳定、调用形态稳定、循环足够热时收益明显；一次性代码、强多态代码、频繁修改 class/module namespace 的代码收益有限。

关键路径
--------

一条典型属性读取的运行期优化链：

::

   source: user.name
       ↓
   compiler emits generic LOAD_ATTR
       ↓
   code object repeated execution
       ↓
   adaptive counter reaches threshold
       ↓
   inspect runtime facts
       ↓
   install specialized LOAD_ATTR variant
       ↓
   validate inline-cache guards on each hit
       ↓
   guard success → fast path
       ↓
   guard failure → generic fallback / counter decay
       ↓
   repeated misses → de-specialize to adaptive form

阅读某个 specialized opcode 时按以下顺序：

#. 先确定它所属的通用 instruction family，例如 ``LOAD_ATTR`` 或 ``BINARY_OP``。
#. 再确认通用语义原本必须完成哪些动态检查。
#. 找 specialized 变体保存了哪些 cache 字段、使用了哪些 guard。
#. 判断快路径省略了通用路径中的哪几步。
#. 最后确认 guard 失败时怎样回到完整语义路径。

概念辨析
--------

* **adaptive opcode 与 specialized opcode**：adaptive 负责收集证据和决定是否特殊化；specialized 已经建立具体运行时假设并执行快路径。
* **inline cache 与普通结果缓存**：inline cache 保存的是分发结构和校验信息，不是简单记住上一次表达式结果。
* **specialization 与 JIT**：PEP 659 的核心是解释器内部指令级专门化，不要求把整个函数编译成本地机器码。
* **de-optimization 与执行失败**：回退只是说明当前运行时假设不再稳定；Python 操作本身仍可通过通用路径正常完成。
* **语义与性能**：``user.name`` 的属性语义来自对象模型；specialization 只是在 guard 成立时缩短实现路径。
* **热度与算法复杂度**：adaptive runtime 能减少解释器常数开销，不能把平方级算法变成线性算法，也不能消除 I/O、数据库、NumPy C 循环等外层成本。

本章结论
--------

PEP 659 的核心模型是“先执行通用语义，再让热指令根据稳定运行时事实变窄”。每个指令位置独立积累证据，通过 counter 和 inline cache 建立局部假设；假设成立时进入 specialized 快路径，假设失效时局部回退。理解 adaptive runtime 时，应始终从通用 opcode 的语义出发，再看 specialized family、guard、cache 和 de-optimization，而不是把专门化 opcode 当成新的 Python 语义。