第025章：字节码架构
==================

核心知识点
----------

Bytecode 是 CPython 的执行表示
   源码经过 parser、AST、symbol table、CFG 和 assemble 后，成为 code object 中的指令流。解释器在 frame 中按 instruction pointer 逐条推进这些指令。

指令由 opcode 与 argument 构成
   Opcode 表示加载、存储、调用、运算、跳转或返回等动作；argument 通常指向常量表、名字表、局部槽位、比较类型或跳转目标。

Code object 把指令与静态元数据封装在一起
   ``co_consts`` 保存常量和嵌套 code object，``co_names`` 保存全局名和属性名，``co_varnames`` 保存局部变量布局，free/cell metadata 保存闭包位置。

CPython bytecode 使用 value stack
   加载指令把对象压栈，运算和调用指令消费若干栈顶对象并推入结果，存储指令取走结果并写入目标。阅读指令的核心是跟踪每条指令的 stack effect。

Frame 提供执行上下文
   当前 frame 连接 code object、locals、globals、builtins、closure cells、value stack 和 instruction pointer。Bytecode 只排列运行时动作，真正对象行为仍由类型协议和解释器分发完成。

``dis`` 是观察工具而非语言规范
   ``dis.dis``、``dis.get_instructions`` 和 ``dis.Bytecode`` 展示当前 CPython 版本的指令。Opcode 名称、偏移、调用形式和跳转表示会跨版本变化。

指令阅读应从源码现象回到栈变化
   一行函数调用通常拆成 callable 加载、参数加载、调用和返回值入栈；一次赋值通常拆成值计算和存储；循环拆成 iterator 获取、推进、跳转和退出。

Inline cache 保存局部运行时事实
   特定指令后可带缓存区域，记录全局名字、属性类型、调用形状或运算类型等可复用信息。缓存命中减少重复动态检查，失效时回到通用路径。

Adaptive specialization 改写执行形态
   Python 3.11+ 可根据实际运行数据把通用指令 specialized 为更具体的变体。原始 bytecode 表达通用执行计划，adaptive bytecode 表达当前运行历史形成的优化状态。

Specialized opcode 必须还原到 base family 阅读
   优化指令仍属于加载、属性访问、调用或二元运算等基础家族。假设失效时需要 de-opt 回通用指令，因此 specialization 不改变 Python 语义。

Bytecode 没有跨版本稳定 ABI
   它是 CPython 实现细节，缓存布局、opcode 编号、参数含义和 ``dis`` 输出都可能改变。持久化和工具分析必须绑定明确解释器版本。

关键路径
--------

Frame 执行路径：

::

   调用函数并创建或恢复 frame
   → 取得 code object 与 bytecode stream
   → instruction pointer 指向下一条指令
   → opcode 读取 argument 及对应元数据表
   → 从 locals / globals / builtins / closure 取得对象
   → 在 value stack 上加载、消费并产生结果
   → 顺序推进、跳转、调用或返回
   → 异常时查询 exception table 并转入 handler

Adaptive 优化路径：

::

   初始使用通用 bytecode
   → 指令重复执行并积累类型与版本信息
   → inline cache 记录局部假设
   → 满足条件后 specialized 为具体变体
   → 快速路径检查缓存和对象形状
   → 命中时直接执行优化操作
   → 假设失效时 de-opt 并回到通用路径

概念辨析
--------

* **语言语义与 bytecode**：语言参考规定可观察行为；bytecode 是 CPython 实现这些行为的内部形式。
* **Opcode 与协议实现**：opcode 选择运行时入口；类型 slot 和对象方法决定该入口的具体行为。
* **Argument 编号与真实对象**：指令中多为索引或编码参数；真实名字和常量保存在 code object 表中。
* **Value stack 与调用栈**：value stack 属于单个 frame 的表达式执行；调用栈由多个 frame 的调用关系组成。
* **原始 bytecode 与 adaptive bytecode**：前者由编译器产生；后者包含运行后形成的 specialization 状态。
* **Inline cache 与普通 Python 缓存**：inline cache 是解释器内部指令缓存，不是用户对象中的字典或应用级缓存。

本章结论
--------

阅读 CPython 字节码时，应固定跟踪“指令、参数、元数据表、value stack、控制流”五个对象，再把调用和运算还原到对象协议。``dis`` 能证明当前版本的执行形态，inline cache 与 specialization 解释性能变化，但都不改变语言层语义。
