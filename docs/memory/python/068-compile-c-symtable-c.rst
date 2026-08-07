第068章：compile.c and symtable.c
=================================

核心知识点
----------

* ``symtable.c`` 与 compiler 链连接 AST 和 code object：前者决定名字属于哪个作用域，后者依据这些分类生成指令、CFG、常量表、名字表、cell/free vars、位置信息和 exception table。
* 稳定编译链是 ``source → parser → AST → symbol table → code generation → CFG/optimization → assemble → PyCodeObject``。当前 CPython 版本可能把实现拆到 ``compile.c``、``codegen.c``、``flowgraph.c``、``assemble.c`` 等文件。
* symbol analysis 处理的是“名字关系”，不处理运行时值。它先划分 module/function/class/comprehension/generator 等 code block，再标记绑定、读取、参数、global、nonlocal 和嵌套捕获。
* local 是当前 block 自己绑定的名字；global 指向模块 namespace；free variable 是当前 block 从外层函数作用域读取的名字；cell variable 是当前 block 需要提供给内层 block 的绑定。
* free/cell 是同一条 closure 关系的两端：外层绑定被内层捕获时，外层 local 升级为 cell，内层把它视为 free variable。
* ``nonlocal x`` 要求外层非全局函数作用域存在绑定，并让当前 block 读写那个 cell；``global x`` 把当前 block 的读写指向 module global namespace。
* symbol table 的分类会影响 opcode/storage 选择：fast local、global/builtins、cell/free variable 使用不同访问路径。
* function definition 在编译结果中既包含“嵌套 code object 常量”，也包含外层运行时创建 function object 的指令。
* generator expression / comprehension 可能拥有独立 code object，也可能在新版本中部分内联；语言作用域语义与当前 CPython 的实现形态必须分开判断。
* bytecode generation 是栈式编译：表达式产生 stack effect，读取/写入名字根据 symbol classification 选择对应指令；jump 和 exception region 再被组织进 CFG/basic block。
* code object 是编译后的静态执行模板，保存 bytecode/instruction representation、consts、names、varnames、cellvars、freevars、flags、stacksize、line/position 和 exception metadata；它不保存某次函数调用的实际 locals。

关键路径
--------

完整编译主干：

::

    source text
       ↓
    tokenizer + PEG parser
       ↓
    AST
       ↓
    symtable.c
       ↓
    block / name classification
       ↓
    compiler unit / codegen
       ↓
    instruction sequence
       ↓
    basic blocks + CFG
       ↓
    optimization + stack-depth analysis
       ↓
    assembler
       ↓
    PyCodeObject

闭包分析：

::

    outer:
        total = ...       # bind
        inner:
            nonlocal total
            read/write total

    symbol analysis
        ↓
    outer.total = CELL
    inner.total = FREE
        ↓
    outer code creates cell
        ↓
    function creation captures cell
        ↓
    inner runtime uses closure access

名字访问选择：

::

    AST Name("x")
        ↓
    lookup symbol-table classification
        ├─ local    → fast-local path
        ├─ global   → globals/builtins path
        ├─ free     → closure/freevar path
        └─ cell     → cell storage path

嵌套函数：

::

    compile inner body
        ↓
    inner PyCodeObject stored in outer constants
        ↓ runtime outer executes
    load code + closure cells
        ↓
    create function object
        ↓
    bind function name in outer frame

概念辨析
--------

* parser 判断语法合法性与 AST 结构，symbol table 判断名字作用域；二者不是同一阶段。
* local/global/free/cell 是编译期名字分类，不是对象类型。
* cell object 保存可共享绑定，free variable 是内层 code 对该 cell 的访问关系；“闭包变量”不是简单复制外层值。
* code object 与 function object 不同：function 把 code 与 globals/defaults/closure 组合起来。
* code object 与 frame 不同：code 可被多次调用复用，frame 是一次具体执行状态。
* ``nonlocal`` 与 ``global`` 都改变名字分类，但目标 namespace 完全不同。
* comprehension 的“变量不泄漏”是语言语义；是否单独创建 frame/code object 属于版本相关实现。
* bytecode 名称会随版本变化，稳定阅读目标应是 stack effect、storage class 和控制流，而不是死记某一版 opcode。

本章结论
--------

``symtable.c`` 决定“一个名字运行时应去哪里找”，compiler 链决定“AST 怎样被编码成可执行 code object”。闭包、global、nonlocal、fast locals 和 opcode 选择都来自这两个阶段的衔接。阅读编译器时先做 block 与 symbol 分类，再看 codegen；直接从某个 opcode 倒推名字语义，很容易漏掉真正的前置决定。