第023章：AST 与符号表
====================

核心知识点
----------

AST 表达结构化语法
   Parser 产生的结果会被整理成语句、表达式和名字节点。模块、函数、赋值、调用、条件、返回等源码结构在 AST 中都有明确节点和字段。

AST 保留编译信息并丢弃表层形式
   注释、空行、部分括号和缩进文本通常不再保留；语句层级、表达式嵌套、读写上下文和源码位置仍会进入后续编译阶段。

名字节点带有访问上下文
   ``Name`` 节点通过 ``Load``、``Store``、``Del`` 表示读取、绑定和删除位置。增强赋值虽然需要先读后写，目标节点仍处于写入上下文，编译器结合语句类型生成完整操作。

AST 尚未决定名字访问方式
   AST 只记录“此处使用了某个名字”。该名字最终是局部变量、全局变量、自由变量还是闭包 cell，需要 symbol table 在每个 block 中继续分析。

Symbol table 以 code block 为单位分类名字
   模块、函数、类、推导式以及部分新语法作用域会建立独立 block。每个 block 记录参数、赋值、导入、声明、引用和嵌套 block 关系。

绑定动作决定局部性
   函数中的参数、赋值目标、循环目标、异常目标、``with as`` 目标、导入和内部定义都会建立当前 block 的绑定。只要存在局部绑定，普通读取就按局部变量解释。

``global`` 与 ``nonlocal`` 改变归属
   ``global`` 把当前 block 中的访问指向模块 namespace；``nonlocal`` 要求最近的外层函数 block 已有绑定，并让当前 block 通过闭包访问该名字。

Free variable 与 cell variable 成对产生
   内层函数使用外层函数绑定时，该名字在内层是 free variable；外层对应 local 会升级为 cell variable，以便函数 frame 结束后仍由闭包持有。

符号分类决定 code object 元数据
   局部变量进入 fast locals 布局，自由变量与 cell 进入 ``co_freevars``、``co_cellvars``，全局名字进入 globals/builtins 查找路径。后续 codegen 据此选择不同访问指令。

AST 变换必须满足目标版本结构
   修改 AST 后要保证节点字段完整、``ctx`` 合法、源码位置信息可用，并通过编译器验证。AST schema 会随 Python 版本演进。

关键路径
--------

名字分类路径：

::

   Parser 产生结构结果
   → 构造 Module / stmt / expr 等 AST 节点
   → 为 Name 标记 Load / Store / Del
   → 按模块、函数、类等建立 symbol table block
   → 收集参数、赋值、引用、global 与 nonlocal
   → 先判定当前 block 的 local / explicit global
   → 向嵌套 block 传播 free variable 需求
   → 把被内层捕获的外层 local 升级为 cell
   → 生成局部变量、闭包变量和名字表元数据

闭包形成路径：

::

   内层函数读取或写入外层函数名字
   → 内层符号被标记为 free
   → 外层对应 local 被标记为 cell
   → code object 记录 co_freevars 与 co_cellvars
   → 执行外层函数时创建 cell
   → 创建内层 function object 时保存 closure cells
   → 外层 frame 结束后闭包仍可访问绑定

概念辨析
--------

* **AST 与源码文本**：AST 表达编译所需结构，不是源码的完整无损表示。
* **AST 名字节点与作用域分类**：前者记录名字及读写位置；后者决定运行时从哪里取得该名字。
* **Local 与 cell**：cell 仍是外层函数的局部绑定，只因被嵌套函数捕获而改用 cell 存储。
* **Free 与 global**：free 来自外层函数 block；global 交给模块 globals 和 builtins 查找。
* **``global`` 与 ``nonlocal``**：前者指向模块层；后者必须命中外层非全局函数绑定。
* **Class namespace 与 enclosing function scope**：类体会建立 namespace，但方法普通名字查找不会把类 namespace 当作函数闭包层。

本章结论
--------

阅读 Python 名字问题时，应先从 AST 确认绑定和读取位置，再按 block 建立符号表，最后判断 local、global、free 与 cell。闭包不是运行时临时猜测，而是编译期作用域分析、code object 元数据和运行时 cell 共同完成的固定布局。
