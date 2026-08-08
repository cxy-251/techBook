第100章：Evaluation Loop and Runtime Objects
=============================================

核心知识点
----------

* CPython 的执行入口不是源码文本，而是 code object 中的 bytecode 和元数据。Compiler 先生成 code object，VM 再执行它。
* Code object 描述可复用的静态执行单元，包含 bytecode、constants、names、local-variable information、argument counts、stack requirements 和位置元数据。
* Frame 是一次 code object 调用的动态执行容器。相同 code object 可以被多次调用，每次调用拥有独立 frame。
* Frame 维护当前局部变量、value stack、instruction position、异常/返回状态以及与调用链相关的信息，把静态 code object 变成可推进的执行状态。
* Value stack 保存表达式和相邻 bytecode instructions 之间的临时 Python object references；它与函数调用 frame stack 是不同层次的栈。
* Evaluation loop 的稳定模型是 ``fetch/decode/dispatch/execute/update``：读取当前 instruction，进入对应 handler，修改 frame/object 状态，再选择下一执行位置。
* Opcode 的参数通常要结合 code object 表解释，例如 constant index、local slot、name entry 或 jump target；opcode 文本本身不是完整语义。
* ``LOAD``/``STORE`` 类指令主要在 frame 与 value stack 之间搬运对象引用；算术、调用、属性和迭代类指令会进一步进入 Python runtime object protocols。
* Python bytecode 中的 ``+`` 语义不是一条固定 CPU add。VM 知道这里要执行二元操作，真正是整数加法、字符串连接、用户定义特殊方法还是 TypeError，要等运行时对象类型决定。
* Python 的整数、字符串、函数、类、模块、列表、字典、迭代器和异常都以 runtime object 参与执行；bytecode 提供控制骨架，对象模型提供动态语义。
* 同一份 bytecode 在不同输入对象下可以走不同底层实现路径，因此“opcode 相同”不代表运行时成本或具体 helper 相同。
* Runtime type error 可以在语法、作用域和 bytecode 均合法后才发生。此时 traceback 提供源码位置，frame/local state 提供参与对象，``dis`` 提供触发动态操作的指令证据。
* Function call 会创建/切换 frame，被调用者返回后结果再进入调用者状态；递归则让同一 code object 同时对应多个不同 frame。
* CPython 的 specializing adaptive interpreter 可以根据运行时反馈优化部分通用指令的执行路径；specialization 改变性能实现，不改变 Python 对象语义合同。
* CPython bytecode 是实现细节，opcode 与 specialization 形式会随版本演进。长期稳定的理解对象应是 code object、frame、dispatch、stack effect 和 object protocol 之间的关系。

关键路径
--------

VM 执行：

::

   code object
   → create frame for this call
   → bind arguments / initialize locals
   → fetch current bytecode instruction
   → decode + dispatch
   → read/write value stack and locals
   → invoke runtime object protocol if needed
   → advance/jump/call/return/raise
   → repeat until frame exits

动态二元操作：

::

   load left object
   → load right object
   → binary-operation opcode
   → inspect/runtime-dispatch object types
   → execute built-in fast path or special method
   → produce result object or exception
   → store/use result

概念辨析
--------

* **Code object 与 frame**：code object 是可复用静态编译产物，frame 是某一次执行的动态状态实例。
* **Frame stack 与 value stack**：前者表达调用链，后者保存当前 frame 内表达式计算的临时对象引用。
* **Opcode semantics 与 object semantics**：opcode 指定操作类别，对象类型/协议决定该操作在当前值上的具体行为。
* **Bytecode 与 machine code**：bytecode 由 CPython VM 执行，不是直接绑定某个 CPU ISA 的原生机器指令。
* **Adaptive specialization 与 language semantics**：specialization 优化解释器内部路径，但必须保持用户可观察的 Python 行为一致。

本章结论
--------

CPython 的完整执行闭环可以压成 ``Source → Compiler → Code Object/Bytecode → Frame → Evaluation Loop → Runtime Objects``。理解 Python 运行时问题时，应先定位当前 code object 和 frame，再沿 opcode 的 stack effect 进入对象协议；CPython 本质上同时是一套编译器和一台面向 Python 对象模型的虚拟机。