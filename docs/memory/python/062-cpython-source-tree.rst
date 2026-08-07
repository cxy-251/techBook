第062章：CPython Source Tree
===========================

核心知识点
----------

* CPython 源码阅读先做“目录定位”，再追函数。一个 Python 现象通常先归入语法、编译、执行、对象、导入、C API、标准库或启动路径。
* ``Objects/`` 是对象行为层：``typeobject.c``、``dictobject.c``、``listobject.c``、``unicodeobject.c``、``funcobject.c``、``descrobject.c`` 等实现具体 Python 对象、slot、descriptor、引用管理和释放路径。
* ``Python/`` 是解释器控制层：编译、符号表、code object 生成、frame 执行、异常传播、runtime 初始化、import 底层支撑和解释器生命周期主要在这里组织。
* ``Parser/`` 负责源码文本进入语法结构的前半段：tokenizer、PEG parser、语法错误和 AST 构造入口。语法问题先在这里定位，名字作用域和 bytecode 选择属于后续编译阶段。
* ``Include/`` 是 C 声明边界。``Include/`` 偏公共 API，``Include/cpython/`` 暴露更多 CPython-specific 结构，``Include/internal/`` 服务解释器内部，常见 ``pycore_*`` 与 ``_Py*`` 符号都应视为版本绑定实现细节。
* ``Lib/`` 保存 Python 实现的标准库；``Modules/`` 保存 C 扩展、内建模块和部分平台接口。一个标准库模块可能同时有 ``Lib`` 高层逻辑和 ``Modules`` C accelerator。
* ``Programs/``、启动相关 ``Python/`` 文件和配置代码负责从进程入口进入 runtime。启动问题不能只看 ``ceval.c``，还要看配置、path initialization、main interpreter 创建与 ``__main__`` 执行。
* 同一个现象常跨目录。例如属性访问由执行器发起，在 ``typeobject.c`` 中完成查找，命中的 descriptor 可能由 ``descrobject.c`` 实现，相关结构声明又位于 ``Include/``。
* 源码文件名和内部函数会随版本拆分或移动。稳定结论应绑定“职责和对象关系”，具体符号必须以目标 CPython tag 为准。

关键路径
--------

典型脚本启动与执行路径：

::

    python app.py
        ↓
    进程入口 / PyConfig / runtime bootstrap
        ↓
    Parser/：tokenize + PEG parse
        ↓
    AST
        ↓
    Python/：symtable + code generation + assemble
        ↓
    PyCodeObject
        ↓
    frame / evaluation loop
        ↓
    opcode 触发对象协议
        ↓
    Objects/*object.c
        ↓
    返回值 / 异常 / 引用生命周期

根据问题选择首个源码入口：

::

    语法与解析       → Parser/
    名字与闭包       → Python/symtable.c
    编译与 bytecode  → Python/compile.c、codegen/CFG/assemble
    frame 与执行     → Python/ceval.c、bytecodes.c
    类型与属性       → Objects/typeobject.c
    dict             → Objects/dictobject.c
    list / str       → Objects/listobject.c / unicodeobject.c
    descriptor       → Objects/descrobject.c
    function         → Objects/funcobject.c
    generator/frame  → Objects/genobject.c / frameobject.c
    GC / allocator   → Python/gc.c（或对应版本）/ Objects/obmalloc.c
    import           → Lib/importlib/ + Python/import.c
    Python 标准库    → Lib/
    C 扩展/加速器    → Modules/
    C 结构与 API     → Include/

一次源码阅读应沿“现象 → 对象 → 协议 → 实现”推进，而不是从目录顶部顺序通读整个仓库。

概念辨析
--------

* ``Objects/`` 不等于“所有运行逻辑”。对象实现回答“这个对象怎样工作”，opcode 调度和 frame 推进仍属于解释器层。
* ``Python/`` 不等于“Python 语言源码”。它是 CPython C 实现中的解释器核心目录。
* ``Lib/`` 不等于 runtime 核心。大量标准库由 Python 实现，但底层仍依赖解释器对象、协议和系统调用。
* ``Modules/`` 不等于第三方扩展。它包含 CPython 自带的 C 模块、内建模块和 accelerator。
* ``Include/internal/`` 中能找到结构体，不代表第三方扩展可以依赖这些字段；可读性和 API 稳定性是两件事。
* AST 解决语法结构，symbol table 解决名字分类，compiler 生成 code object，``ceval`` 执行 code object；四层不能混为一个“解析过程”。
* CPython 源码结构是实现细节，Python 语言语义是更高层约束；其它实现可以保持同样语义而采用完全不同源码布局。

本章结论
--------

阅读 CPython 源码最重要的第一步不是记文件名，而是建立职责地图：``Parser`` 负责语法，``Python`` 负责编译与执行控制，``Objects`` 负责对象行为，``Include`` 定义 C 边界，``Lib`` 与 ``Modules`` 组织标准库实现。先把 Python 现象定位到正确层级，再沿 runtime 对象和协议向下追函数，源码树才会从“几十万行 C”变成可导航的执行模型。