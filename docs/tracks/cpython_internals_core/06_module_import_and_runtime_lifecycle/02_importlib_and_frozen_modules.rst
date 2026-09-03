=============================================================================
导入子系统 Importlib、字节码冻结模块与 sys.modules 缓存表
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解构了 CPython 3.13+ 从操作系统入口 ``main()`` 到核心运行时就绪（``Py_InitializeFromConfig``）的完整生命周期图谱。在内核创世阶段（``pyinit_core``）与主运行时就绪阶段（``pyinit_main``）之间，存在一个极具哲学意味的技术交汇点——**解释器必须依靠 Python 编写的导入子系统（``importlib``）来加载 Python 模块，但要在虚拟机中执行 Python 编写的 ``importlib``，又必须先具备导入 Python 模块的能力**。
   
   这种“鸡生蛋还是蛋生鸡”的**自举悖论（Bootstrap Paradox）**是如何被 CPython 在 C 语言层完美化解的？本章将深入 CPython 核心源码文件 ``Python/import.c``、``Python/frozen.c``、``Include/internal/pycore_import.h`` 以及 ``Lib/importlib/_bootstrap.py``，全景式剖析字节码冻结（Frozen Modules）的二进制内存映射拓扑、``_imp`` 内核 C 模块与 ``importlib`` 的两阶段自举协议、PEP 451 引入的 ``ModuleSpec`` 规范与 Finder / Loader 双层架构、``sys.modules`` 字典缓存的原子发布与循环导入防死锁状态机，以及 Python 3.13+ 最新引入的延迟导入（Lazy Imports）物理机制。

-----------------------------------------------------------------------------
1. 导入自举悖论与字节码冻结机制（Frozen Modules）
-----------------------------------------------------------------------------

自举悖论与解决方案
~~~~~~~~~~~~~~~~~~

在早期的 Python（Python 2 及早期 Python 3）中，导入逻辑主要由庞大且难以维护的 C 语言函数（``import.c``）硬编码实现。从 Python 3.3（PEP 302 / PEP 451 演进）开始，CPython 将全部导入逻辑重构为基于标准协议的纯 Python 实现——即标准库中的 ``Lib/importlib/_bootstrap.py``（核心导入骨架）与 ``Lib/importlib/_bootstrap_external.py``（文件系统与外部加载器）。

这立刻引发了启动悖论：
- 虚拟机启动时，文件系统抽象、路径解析、异常类包装与代码读取均尚未就绪；
- 虚拟机如何加载最初的 ``_bootstrap.py``？

CPython 的破局方案是：**编译期静态字节码冻结（Frozen Bytecode Compilation）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     字节码冻结编译与自举加载流水线                      |
   +=========================================================================+
   | 【编译期 Build Time】                                                   |
   |   Lib/importlib/_bootstrap.py ──► freeze_modules.py 编译为字节码        |
   |                                ──► 序列化 (Marshal) 为十六进制 C 数组   |
   |                                ──► 生成 Python/frozen_modules/_bootstrap.h|
   +───────────────────────────────────┬─────────────────────────────────────+
                                       │ (编译链接至 Python 二进制 BSS/ROData)
                                       ▼
   +-------------------------------------------------------------------------+
   | 【运行时 Runtime (0 磁盘 I/O)】                                         |
   |   1. C 语言直接读取 _PyImport_FrozenBootstrap 内存指针                  |
   |   2. 调用 PyMarshal_ReadObjectFromString() 反序列化为 PyCodeObject      |
   |   3. 构造 module 字典并在当前栈帧执行字节码 ──► importlib 瞬时就绪!     |
   +-------------------------------------------------------------------------+

`struct _frozen` 物理内存拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``Include/internal/pycore_import.h`` 中，冻结模块在 C 语言结构体中定义为只读常量数组：

.. code-block:: c

   struct _frozen {
       const char *name;              /* 模块完全限定名, 如 "_frozen_importlib" */
       const unsigned char *code;     /* 预编译并序列化的 Marshal 字节码内存首地址 */
       int size;                      /* 字节码数组长度 (若为负数表示该模块为包 Package) */
       bool is_package;               /* 是否为包结构 */
   };

当 CPython 启动进入 ``init_importlib()`` 时，调用 ``_imp_find_frozen_impl()`` 与 ``unmarshal_frozen_code()``，直接从进程只读数据段（ROData）中以指针解引用方式加载代码对象，**全程产生 0 次操作系统 ``open()`` 或 ``read()`` 系统调用**，实现了微秒级的极致自举。

在 Python 3.11+ 及 3.13 中，该机制被进一步推广至标准库关键模块（如 ``os``、``stat``、``posixpath``、``genericpath``、``abc`` 等），使 Python 进程的冷启动（Cold Startup）速度提升了 15%~30%。

-----------------------------------------------------------------------------
2. `_imp` 核心 C 模块与 importlib 的两阶段自举
-----------------------------------------------------------------------------

既然 ``importlib`` 是纯 Python 代码，它在执行过程中仍然需要一些操作系统底层的绝对特权（如加锁、调用动态链接器 ``dlopen``、计算字节码 Hash 等）。这些能力由内置 C 模块 ``_imp``（``Python/import.c``）全权提供。

两阶段自举协议（Two-Phase Bootstrap）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CPython 按照精密的拓扑顺序完成自举：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Importlib 两阶段自举时序图                          |
   +=========================================================================+
   | Phase 1: 核心导入就绪 (_PyImport_InitCore)                              |
   | ├── 1.1 从冻结字节码加载并执行 _frozen_importlib                         |
   | ├── 1.2 C 语言直接创建内置 _imp 模块 (bootstrap_imp)                    |
   | └── 1.3 调用 _frozen_importlib._install(sys, _imp)                      |
   |     └─ 将 BuiltinImporter 与 FrozenImporter 注册至 sys.meta_path        |
   +───────────────────────────────────┬─────────────────────────────────────+
                                       │ (此时已具备加载内置 C 模块与冻结模块能力)
                                       ▼
   +-------------------------------------------------------------------------+
   | Phase 2: 外部导入就绪 (_PyImport_InitExternal)                          |
   | ├── 2.1 从冻结字节码加载 _frozen_importlib_external                      |
   | ├── 2.2 调用 _install_external_importers()                              |
   | │   └─ 将 PathFinder 与 FileLoader 挂载至 sys.meta_path                 |
   | └── 2.3 初始化 zipimport 并插入 sys.path_hooks                          |
   |     └─ 此时 CPython 具备了完整的文件系统 .py / .pyc 及 .so 动态库加载能力! |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
3. PEP 451 体系：ModuleSpec、Finder 与 Loader 运行时架构
-----------------------------------------------------------------------------

三位一体的导入抽象
~~~~~~~~~~~~~~~~~~

Python 的现代导入体系遵循 PEP 451 标准，由三大核心构件支撑：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                   PEP 451 导入子系统三层交互架构                        |
   +=========================================================================+
   | 1. 元路径查找器 (MetaPathFinder)                                        |
   | └─ 遍历 sys.meta_path, 调用 find_spec(fullname, path, target)           |
   |    根据模块名和搜索路径寻找物理载体, 匹配成功则构建并返回 ModuleSpec。   |
   +───────────────────────────────────┬─────────────────────────────────────+
                                       │ 返回 ModuleSpec 对象
                                       ▼
   +-------------------------------------------------------------------------+
   | 2. 模块规格说明书 (ModuleSpec)                                          |
   | ├── name: 模块全名 (如 "email.mime.text")                               |
   | ├── loader: 负责加载该模块的 Loader 实例                                |
   | ├── origin: 物理路径 (如 "/usr/lib/python3.13/email/mime/text.py")      |
   | ├── submodule_search_locations: 包专有的子模块搜索目录列表 (__path__)    |
   | └── _initializing: 并发加载状态布尔标记 (True / False)                  |
   +───────────────────────────────────┬─────────────────────────────────────+
                                       │ 传递给加载器执行
                                       ▼
   +-------------------------------------------------------------------------+
   | 3. 模块加载器 (Loader)                                                  |
   | ├── create_module(spec): 分配 PyModuleObject (若返回 None 则由系统分配)  |
   | └── exec_module(module): 将编译好的字节码注入模块命名空间并在栈帧中执行  |
   +-------------------------------------------------------------------------+

默认 `sys.meta_path` 优先级拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当执行 ``import foo`` 时，解释器按照固定优先级依次遍历查找器：
1. **``BuiltinImporter``**：检查模块名是否存在于 C 语言内置模块表（``_PyImport_Inittab``，如 ``sys``、``builtins``、``gc``、``time``）；
2. **``FrozenImporter``**：检查是否为预编译冻结模块（``_PyImport_FrozenBootstrap`` / ``_PyImport_FrozenStdlib``）；
3. **``PathFinder``**：遍历 ``sys.path``，利用 ``sys.path_hooks``（如 ``FileFinder``、``zipimporter``）在磁盘或归档文件中探查目标文件。

-----------------------------------------------------------------------------
4. `sys.modules` 缓存字典与循环导入防死锁模型
-----------------------------------------------------------------------------

提前写入（Early Insertion）与循环引用破解
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在大型 Python 工程中，循环导入（Circular Import / Mutual Dependency）极为常见（例如模块 A 导入模块 B，模块 B 在顶层又导入模块 A）。

CPython 在 ``importlib._bootstrap._load_unlocked()`` 中采用了精妙的**先占位后执行（Early Insertion）**机制：

.. code-block:: python

   # importlib/_bootstrap.py 核心加载逻辑简化伪代码
   def _load_unlocked(spec):
       # 1. 创建未初始化的空白模块对象 (或由 loader.create_module 创建)
       module = module_from_spec(spec)
       
       # 2. 标记模块处于初始化中
       spec._initializing = True
       
       # 3. 关键步: 在执行任何模块内部代码之前, 先将半成品模块注入 sys.modules!
       sys.modules[spec.name] = module
       
       try:
           # 4. 执行模块内部顶层字节码
           spec.loader.exec_module(module)
       except BaseException:
           # 5. 异常回滚: 若执行失败, 必须从 sys.modules 中彻底剔除
           sys.modules.pop(spec.name, None)
           raise
       finally:
           spec._initializing = False
           
       return module

- **循环依赖解题**：当 A 执行到 ``import B`` 时，A 已经作为空白对象存在于 ``sys.modules["A"]`` 中。B 在执行过程中遇到 ``import A``，直接在 ``sys.modules`` 中命中并获取 A 的引用，从而打断了无限递归死锁；
- **状态不一致性边界**：若 B 在模块顶层试图直接访问 A 尚未执行到的属性（如 ``A.some_var``），会抛出经典的 ``AttributeError: partially initialized module 'A' has no attribute 'some_var'``。

细粒度模块锁（`_lock_unlock_module`）与线程安全
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在多线程环境下，若线程 1 和 线程 2 同时触发 ``import foo``：
- CPython 不再使用全局粗粒度锁，而是使用针对每个模块独立分配的递归互斥锁（``_ModuleLock``）；
- 线程 1 获得 ``foo`` 的模块锁并开始执行 ``exec_module()``；
- 线程 2 发现 ``sys.modules["foo"]`` 存在但 ``spec._initializing == True``，调用 ``_lock_unlock_module("foo")`` 自动进入等待队列挂起；
- 线程 1 执行完毕将 ``_initializing`` 置为 False 并释放锁，线程 2 被唤醒后直接无感复用已初始化完成的模块单例。

-----------------------------------------------------------------------------
5. Python 3.13+ 延迟导入（Lazy Imports）物理机制
-----------------------------------------------------------------------------

传统 Python 项目的一大痛点是“导入即执行（Import-Time Overhead）”：为了使用某个包的单个工具函数，往往需要拉起几十个庞大的第三方依赖，导致命令行 CLI 工具启动延迟高达几百毫秒。

在 Python 3.13 中，底层深度集成了对**延迟导入（Lazy Imports，PEP 810/PEP 690 演进）**的高性能 C 级支撑：
1. **``PyLazyImportObject`` 虚拟占位对象**：
   当启用延迟导入模式时，``import foo`` 并不立即触发 Finder 与 Loader，而是在当前命名空间绑定一个轻量级的代理对象 ``_PyLazyImport_New()``；
2. **父子层级关系注册**：
   在 ``register_lazy_on_parent()`` 中，将模块层级拓扑记录在解释器内部的 ``LAZY_PENDING_SUBMODULES`` 字典表中；
3. **按需具象化（On-Demand Reification）**：
   当用户代码第一次尝试访问该对象的属性（触发 ``_Py_module_getattro_impl()``）或将其作为实参传递时，虚拟机底层调用 ``_PyImport_TryLoadLazySubmodule()`` 瞬时触发真实的模块加载与字节码执行，并将代理指针原地替换为真实模块单例！

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 导入子系统的底层物理拓扑与运行机制：
1. 字节码冻结（Frozen Modules）的编译期 Marshal 序列化与运行时 0 磁盘 I/O 自举；
2. ``_imp`` 内核 C 模块与 ``_frozen_importlib`` 的两阶段自举时序；
3. PEP 451 标准下 ``ModuleSpec`` 规格说明书、``MetaPathFinder`` 与 ``Loader`` 的三层架构；
4. ``sys.modules`` 提前占位写入（Early Insertion）机制破除循环导入死锁与细粒度模块锁并发模型；
5. Python 3.13+ 基于 ``PyLazyImportObject`` 与按需具象化的延迟导入物理实现。

在理解了纯 Python 与冻结模块的加载机制后，下一章我们将深入探讨 Python 与底层原生世界连接的最核心枢纽—— **06_module_import_and_runtime_lifecycle/03_c_extension_and_limited_api.rst（语法分析与 C 扩展模块加载、PyMethodDef 结构与 Stable ABI / Limited API 机制）**。
