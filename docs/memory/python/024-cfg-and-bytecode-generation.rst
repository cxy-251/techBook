第024章：CFG 与字节码生成
========================

核心知识点
----------

CFG 把语法树转换为执行图
   AST 擅长表达包含关系，CFG 用基本块和有向边表达实际控制流。条件、循环、短路逻辑、返回和异常都会改变块之间的连接方式。

基本块内部顺序执行
   进入一个 basic block 后，指令从头执行到块尾；块尾通过顺序落下、条件跳转、无条件跳转、返回或异常边进入后继块。

分支会分裂并重新汇合
   ``if`` 的判断块至少连接真、假两个后继，两个分支可以在后续 join block 汇合。循环还会产生回边，形成重复执行路径。

Codegen 同时依赖 AST 与符号表
   AST 决定需要生成什么操作，symbol table 决定名字属于 local、global、free 还是 cell。相同的名字节点可能因此生成不同的访问指令。

字节码面向栈机器
   表达式先把操作数压入 value stack，运算、比较和调用指令消费栈顶对象并推入结果，存储指令再把结果写入局部槽位、名字或属性位置。

Opcode 参数依赖 code object 表
   常量进入 ``co_consts``，全局名和属性名进入 ``co_names``，局部变量进入 ``co_varnames``，闭包信息进入 cell/free metadata。指令参数通常是这些表项或跳转目标的编号。

编译链路由多个 pass 构成
   AST 与符号表之后，codegen 先生成接近字节码的伪指令；CFG pass 建图和优化；assemble pass 解析标签、计算栈深、生成异常表和源码位置表，最终构造 code object。

优化必须保持可观察语义
   删除空块、整理跳转链或不可达代码时，执行结果、异常边界、栈效果、traceback、调试行号和 tracing 行为都必须保持正确。

Stacksize 是所有可达路径的最大栈深
   编译器沿 CFG 传播每条指令的 stack effect，检查汇合点的栈状态，并把最大值写入 code object，供 frame 分配 value stack 空间。

Exception table 独立描述异常控制流
   CPython 3.11+ 主要通过 code object 的 exception table 记录受保护指令范围、handler 目标和恢复栈状态。阅读 ``try`` 字节码不能只看普通指令流。

关键路径
--------

AST 到 code object：

::

   已完成作用域分析的 AST
   → 根据语句和表达式生成伪指令
   → 根据名字分类选择 local / global / deref 操作
   → 按分支点建立 basic blocks
   → 用条件边、回边、返回边和异常边连接 CFG
   → 执行 CFG 优化并整理跳转
   → 解析 logical labels 为实际跳转参数
   → 沿所有路径计算 stack effect 与最大栈深
   → 生成 constants、names、locals、位置表与 exception table
   → 构造 PyCodeObject

条件表达式路径：

::

   加载比较操作数
   → 执行比较并把结果留在栈顶
   → 条件跳转消费 truth value
   → 进入真分支或假分支 basic block
   → 各分支生成自己的指令序列
   → 汇合到共同后继块
   → 继续执行或返回

概念辨析
--------

* **AST 与 CFG**：AST 表达语法层级；CFG 表达执行位置和转移关系。
* **基本块与源码缩进块**：基本块由控制流边界划分，不必与源码缩进块一一对应。
* **伪指令与最终 bytecode**：伪指令可以保留标签和抽象操作；assemble 后才形成可执行指令序列。
* **Value stack 与局部变量槽位**：前者保存表达式中间值；后者保存当前 frame 的局部绑定。
* **Jump target 与源码行号**：跳转目标指向指令位置；源码位置表服务 traceback、debugger 和 tracing。
* **普通控制流与异常控制流**：普通边体现在跳转和顺序执行中；异常边主要由 exception table 补充。

本章结论
--------

分析 Python 编译后半段时，应把源码控制结构先还原为基本块和 CFG，再观察 codegen 如何按名字分类与栈机器规则发出指令。最终 code object 不只包含 bytecode，还包含常量、名字、局部布局、最大栈深、源码位置和异常处理信息。
