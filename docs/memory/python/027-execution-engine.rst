第027章：Execution Engine
=========================

核心知识点
----------

* 编译器把源码变成 code object；真正让 code object 运行的是 CPython execution engine。
* 一次执行的主链是：code object → frame → evaluation loop → opcode dispatch → value stack / locals / runtime protocol → 下一条指令。
* 现代 CPython 的默认 frame evaluation 路径围绕 ``_PyEval_EvalFrame()`` 与 ``_PyEval_EvalFrameDefault()`` 展开；``ceval.c`` 是执行入口之一，opcode 定义与生成代码还分布在 ``bytecodes.c``、generated cases 等文件中。
* code object 保存静态执行计划；frame 保存某一次具体执行的动态状态，包括局部变量、globals、builtins、value stack、当前指令位置和异常相关状态。
* evaluation loop 不理解 Python 源码，只消费 bytecode instruction stream。
* opcode handler 的职责是从当前 frame 读取输入、修改 value stack 或局部状态、调用对象协议，并决定控制流怎样继续。
* CPython bytecode 是 stack-machine 指令流：加载类指令 push 对象，运算和调用类指令消费栈顶输入并 push 结果，store 类指令把结果写回变量或对象位置。
* instruction pointer 默认顺序推进；jump、``FOR_ITER``、return、exception、yield 等指令会改写正常推进路径。
* opcode dispatch 与对象协议 dispatch 是两层机制。``LOAD_ATTR`` 先进入属性读取 handler，handler 内部再进入 descriptor、type slot、inline cache 等对象运行时逻辑。
* eval breaker 让解释器在指令推进过程中处理需要跨指令响应的事件，例如 signal、pending call、线程切换或其它 runtime 检查。
* PEP 659 之后，evaluation loop 还会执行 adaptive / specialized opcode，因此当前 code object 的运行时执行形态可以和初始通用 bytecode 不完全相同。

关键路径
--------

普通 Python 函数的一次执行可以压缩为：

::

   function call
       ↓
   function.__code__
       ↓
   create / initialize frame
       ↓
   _PyEval_EvalFrame(...)
       ↓
   evaluation loop
       ↓
   fetch opcode + oparg
       ↓
   dispatch to opcode handler
       ↓
   read/write value stack, fast locals, globals
       ↓
   invoke object/runtime protocol when needed
       ↓
   advance or rewrite instruction pointer
       ↓
   return / raise / suspend

以 ``acc += item.value`` 为例：

#. ``LOAD_FAST`` 读取 ``acc`` 并压栈。
#. ``LOAD_FAST`` 读取 ``item`` 并压栈。
#. ``LOAD_ATTR`` 消费 ``item``，执行属性查找并压入 ``value``。
#. ``BINARY_OP`` 消费两个操作数，进入数值协议并压入结果。
#. ``STORE_FAST`` 弹出结果并写回 ``acc`` 的局部槽位。

概念辨析
--------

* **code object 与 frame**：code object 是静态模板；frame 是这份模板某一次运行的执行现场。
* **value stack 与 call stack**：value stack 位于单个 frame 内，保存表达式中间值；call stack 描述多个 frame 的嵌套调用关系。
* **opcode dispatch 与 runtime dispatch**：前者决定执行哪段解释器 handler；后者决定 Python 对象最终由哪个类型、slot、descriptor 或 callable 处理。
* **instruction pointer 与源码行号**：instruction pointer 指向 bytecode 位置；源码行号来自 code object 的位置元数据，二者不是同一个概念。
* **execution engine 与 compiler**：compiler 决定“应该执行哪些指令”；execution engine 决定“当前 frame 如何逐条执行这些指令”。
* **普通顺序执行与 eval breaker**：大部分指令按顺序推进；signal、线程和 pending runtime 事件需要在检查点介入执行循环。

本章结论
--------

CPython execution engine 的核心单位是 frame，而不是源码函数文本。Code object 提供指令与静态元数据，frame 保存具体调用的动态状态，evaluation loop 逐条取指并把 opcode 分派到 handler，handler 再通过 value stack、locals 和对象协议完成实际操作。理解执行行为时，应按“frame 当前状态 → 当前 opcode → handler 修改了什么 → instruction pointer 下一步去哪”这条路径追踪。