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

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先建立对象与状态模型，再沿关键路径复盘执行顺序，最后用概念边界检查判断是否准确。