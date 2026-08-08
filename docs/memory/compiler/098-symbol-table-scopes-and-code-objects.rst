第098章：Symbol Table, Scopes, and Code Objects
================================================

核心知识点
----------

* CPython 在 AST 之后、bytecode 之前构造 symbol table。它解决的不是“名字当前指向哪个对象”，而是“这个 identifier 在当前代码块应从哪里查找或写入”。
* Symbol table 会按 module、function、class 以及部分内部代码块组织名字事实，并扫描 AST 中的绑定、读取、删除、``global``、``nonlocal`` 等结构。
* 名字作用域分类在执行前已经完成。VM 执行某个名字访问时，不会重新扫描源码判断它是不是局部变量。
* Local 表示当前代码块绑定的名字；global 表示走模块命名空间并可能继续 builtins；nonlocal 表示显式引用最近外层函数绑定。
* Free variable 是当前函数使用、但绑定来自外层函数的名字；cell variable 是当前函数自己绑定、同时被内层函数捕获的名字。
* 闭包的关键是 cell/free 对。外层函数把需要被捕获的 local 提升为 cell，内层函数通过 free variable 访问同一个 cell。
* ``nonlocal`` 改变名字写入目标；目标必须存在于合适的外层函数作用域，否则可以在编译阶段直接报 SyntaxError。
* ``global`` 让当前函数中的对应名字绕过局部绑定路径，进入模块全局/builtins 查找规则。
* ``UnboundLocalError`` 的根源往往是编译期分类：只要函数块中存在对某名字的绑定，未声明 global/nonlocal 时该名字会被归为 local；运行到赋值前的读取才发现局部槽位尚未绑定。
* Class scope 与 function lexical scope 不等价。类体名字进入 class namespace，但方法体中的裸名不会自动把类属性当作外层 lexical variable。
* Comprehension、generator 等语法有自己的版本相关作用域实现，分析时应先确认它是否形成独立代码块/执行单元，再判断名字分类。
* Code object 是编译后的执行单元。它保存 bytecode、常量、名字表、局部变量表、free/cell variable 信息、参数数量、栈需求和位置元数据。
* ``co_varnames`` 反映局部槽位相关名字，``co_names`` 反映需要名字查找的符号，``co_freevars`` 与 ``co_cellvars`` 反映闭包关系；这些字段是作用域分类落入编译产物后的直接证据。
* Nested function、class body、comprehension 等通常会对应独立 code object，并作为常量或嵌套编译产物被外层 code object 引用。
* Python 是动态语言，不代表所有名字解析都推迟到运行时。对象类型与属性值高度动态，但 lexical scope classification 是明显的编译期工作。

关键路径
--------

名字分类：

::

   AST
   → scan code block bindings/references
   → apply global/nonlocal rules
   → classify local/global/free/cell
   → symbol table facts
   → bytecode/code-object generation

闭包：

::

   outer function binds name
   → inner function references it
   → outer local becomes cell variable
   → inner reference becomes free variable
   → function object captures cell
   → outer frame ends
   → inner function still accesses shared cell

编译产物：

::

   symbol table + AST
   → compile one code block
   → bytecode + constants + names
   → co_varnames / co_names
   → co_cellvars / co_freevars
   → code object

概念辨析
--------

* **Symbol table 与 runtime namespace**：symbol table 保存编译期名字分类，runtime namespace 保存实际对象绑定。
* **Local 与 cell**：cell 首先也是当前函数的绑定，只是因为被内层函数捕获而获得可跨 frame 生命周期的存储形式。
* **Free 与 global**：free 从外层函数 closure 获取，global 从模块/builtins 路径查找。
* **Class namespace 与 enclosing function scope**：类体产生类命名空间，方法体裸名不会把类属性自动当作 lexical free variable。
* **Code object 与 function object**：code object 保存可执行代码和静态元数据；function object 还绑定 globals、defaults、closure 等运行时环境。

本章结论
--------

CPython 的名字主线是 ``AST → Symbol Table → Scope Classification → Code Object → VM Access Strategy``。理解 Python 名字问题时，应先判断编译器把名字归为 local、global、free 还是 cell，再看 VM 到底访问局部槽位、模块字典还是 closure cell；动态语言并不等于动态作用域判定。