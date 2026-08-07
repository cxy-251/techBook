Python 必背课本
===============

本目录与 AIBook 的 ``docs/Python`` 一一对应。AIBook 保留完整讲解、案例、源码和练习，这里只保留每章稳定、必须掌握、可以直接复习的知识模型。

Part 1：Python 语言语义
-----------------------

* `第001章：Python 执行模型 <001-python-execution-model.rst>`_；
* `第002章：名字绑定与作用域 <002-name-binding-and-scope.rst>`_；
* `第003章：对象引用语义 <003-object-reference-semantics.rst>`_；
* `第004章：表达式求值语义 <004-evaluation-semantics.rst>`_；
* `第005章：控制流语义 <005-control-flow-semantics.rst>`_；
* `第006章：异常语义 <006-exception-semantics.rst>`_；
* `第007章：上下文管理语义 <007-context-management-semantics.rst>`_。

Part 2：Python 对象系统
-----------------------

* `第008章：万物皆对象 <008-everything-is-object.rst>`_；
* `第009章：类型系统 <009-type-system.rst>`_；
* `第010章：属性查找系统 <010-attribute-lookup-system.rst>`_；
* `第011章：描述符协议 <011-descriptor-protocol.rst>`_；
* `第012章：函数对象内部结构 <012-function-object-internals.rst>`_；
* `第013章：类对象构造 <013-class-construction.rst>`_；
* `第014章：继承与 MRO <014-inheritance-and-mro.rst>`_；
* `第015章：元类系统 <015-metaclass-system.rst>`_。

Part 3：内置能力与核心协议
--------------------------

* `第016章：内置函数 <016-built-in-functions.rst>`_；
* `第017章：内置异常 <017-built-in-exceptions.rst>`_；
* `第018章：核心协议 <018-core-protocols.rst>`_；
* `第019章：迭代、序列与映射协议 <019-iteration-sequence-mapping-protocols.rst>`_；
* `第020章：数值、比较与哈希协议 <020-numeric-comparison-hashing-protocols.rst>`_；
* `第021章：调用、上下文、异步与缓冲区协议 <021-callable-context-async-buffer-protocols.rst>`_。

Part 4：编译流水线
-----------------

* `第022章：Tokenizer 与 PEG 解析器 <022-tokenizer-and-peg-parser.rst>`_；
* `第023章：AST 与符号表 <023-ast-and-symbol-table.rst>`_；
* `第024章：CFG 与字节码生成 <024-cfg-and-bytecode-generation.rst>`_；
* `第025章：字节码架构 <025-bytecode-architecture.rst>`_；
* `第026章：Adaptive Runtime（PEP 659） <026-adaptive-runtime-pep-659.rst>`_。

Part 5：求值运行时
-----------------

* `第027章：Execution Engine <027-execution-engine.rst>`_；
* `第028章：Execution State and Frame <028-execution-state-and-frame.rst>`_；
* `第029章：Callable Runtime <029-callable-runtime.rst>`_；
* `第030章：Suspended Execution Model <030-suspended-execution-model.rst>`_；
* `第031章：Async Runtime <031-async-runtime.rst>`_。

Part 6：内存系统
---------------

* `第032章：引用计数 <032-reference-counting.rst>`_；
* `第033章：垃圾回收 <033-garbage-collection.rst>`_；
* `第034章：Pymalloc 架构 <034-pymalloc-architecture.rst>`_；
* `第035章：Immortal Objects（PEP 683） <035-immortal-objects-pep-683.rst>`_。

Part 7：核心容器
---------------

* `第036章：Dict Architecture <036-dict-architecture.rst>`_；
* `第037章：List and Tuple Architecture <037-list-and-tuple-architecture.rst>`_；
* `第038章：Set Architecture <038-set-architecture.rst>`_；
* `第039章：Buffer and Binary Architecture <039-buffer-and-binary-architecture.rst>`_。

Part 8：导入系统
---------------

* `第040章：Import Semantics <040-import-semantics.rst>`_；
* `第041章：Import Machinery <041-import-machinery.rst>`_；
* `第042章：Module Object、sys.modules 与 Import Cache <042-module-object-sys-modules-import-cache.rst>`_；
* `第043章：Packages、Namespace Packages 与 Resource Loading <043-packages-namespace-packages-resource-loading.rst>`_；
* `第044章：Import Failure、Finder/Loader Contracts 与 Diagnostics <044-import-failure-finder-loader-diagnostics.rst>`_。

Part 9：并发运行时
-----------------

* `第045章：GIL Internals <045-gil-internals.rst>`_；
* `第046章：Async Runtime Architecture <046-async-runtime-architecture.rst>`_；
* `第047章：Subinterpreters（PEP 684） <047-subinterpreters-pep-684.rst>`_；
* `第048章：Free-Threaded Python <048-free-threaded-python.rst>`_。

Part 10：标准库设计
------------------

* `第049章：Functional Abstraction <049-functional-abstraction.rst>`_；
* `第050章：Runtime Introspection <050-runtime-introspection.rst>`_；
* `第051章：Typing and Runtime Boundary <051-typing-runtime-boundary.rst>`_；
* `第052章：Context Managers and Resource Cleanup Architecture <052-context-managers-resource-cleanup-architecture.rst>`_；
* `第053章：Serialization Boundary <053-serialization-boundary.rst>`_；
* `第054章：Filesystem and OS Abstraction <054-filesystem-os-abstraction.rst>`_；
* `第055章：Concurrency Abstraction <055-concurrency-abstraction.rst>`_。

Part 11：Python C API
--------------------

* `第056章：Python C API Entry Points and Runtime Contract <056-python-c-api-entry-points-runtime-contract.rst>`_；
* `第057章：Extension Type System <057-extension-type-system.rst>`_；
* `第058章：Embedding and Interop <058-embedding-and-interop.rst>`_；
* `第059章：Reference Ownership and Error Path Discipline <059-reference-ownership-error-path-discipline.rst>`_；
* `第060章：Stable ABI, Limited API, and Extension Compatibility <060-stable-abi-limited-api-extension-compatibility.rst>`_；
* `第061章：Buffer Protocol, Capsules, and Native Boundary Design <061-buffer-protocol-capsules-native-boundary-design.rst>`_。

Part 12：CPython 源码阅读
------------------------

* `第062章：CPython Source Tree <062-cpython-source-tree.rst>`_；
* `第063章：typeobject.c <063-typeobject-c.rst>`_；
* `第064章：dictobject.c <064-dictobject-c.rst>`_；
* `第065章：listobject.c and unicodeobject.c <065-listobject-c-unicodeobject-c.rst>`_；
* `第066章：descrobject.c and funcobject.c <066-descrobject-c-funcobject-c.rst>`_；
* `第067章：genobject.c and frameobject.c <067-genobject-c-frameobject-c.rst>`_；
* `第068章：compile.c and symtable.c <068-compile-c-symtable-c.rst>`_；
* `第069章：ceval.c <069-ceval-c.rst>`_；
* `第070章：gcmodule.c and obmalloc.c <070-gcmodule-obmalloc.rst>`_；
* `第071章：importlib asyncio and contextlib <071-importlib-asyncio-contextlib.rst>`_。

Part 13：Runtime Evolution
-------------------------

* `第072章：Parser and Compiler Pipeline Evolution <072-parser-compiler-pipeline-evolution.rst>`_；
* `第073章：Adaptive Interpreter, Specialization, and JIT Direction <073-adaptive-interpreter-specialization-jit-direction.rst>`_；
* `第074章：Immortal Objects, Memory Model, and Free-Threaded Python <074-immortal-objects-memory-model-free-threaded-python.rst>`_；
* `第075章：Subinterpreters, Isolation, and Runtime Parallelism <075-subinterpreters-isolation-runtime-parallelism.rst>`_；
* `第076章：Reading Future CPython Changes with Stable Models <076-reading-future-cpython-changes-stable-models.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先建立对象与状态模型，再沿关键路径复盘执行顺序，最后用概念边界检查判断是否准确。