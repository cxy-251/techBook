=============================================================================
CPython 启动流程：从 main() 到 Py_InitializeEx 的运行时初始化图谱
=============================================================================

.. note:: 前置背景与上下文承接
   在前五个核心模块中，我们先后解构了 CPython 3.13+ 的底层对象模型与内存基石、PEG 前端编译与 AST 生成、虚拟机栈帧与 CEval 指令分发循环、核心内建数据结构（Compact Dict、FSR Unicode、List/Set），以及 PEP 703 自由线程（Free-Threading）并发内存安全性体系。此时，虚拟机内部的所有数据结构与并发原语已清晰呈现。
   
   然而，一个极其关键的宏观问题尚未解答：**当用户在操作系统终端敲下 ``python3 script.py`` 的那一瞬间，操作系统进程是如何一步步蜕变为一个功能完备、内置类型就绪、导入子系统激活、JIT 优化器启动的 Python 虚拟机的？**
   
   本章作为**第 6 模块【运行时生命周期与导入系统】的开篇之作**，将深入 CPython 核心源码文件 ``Programs/python.c``、``Modules/main.c``、``Python/pylifecycle.c``、``Python/initconfig.c`` 以及 ``Include/internal/pycore_runtime.h``，全景式解构 CPython 从 C 语言入口函数 ``main()`` 到核心运行时就绪（``Py_InitializeFromConfig`` / ``Py_InitializeEx``）的工业级初始化图谱。

-----------------------------------------------------------------------------
1. 启动全景流水线与 PEP 587 配置模型
-----------------------------------------------------------------------------

PEP 587 标准化配置体系
~~~~~~~~~~~~~~~~~~~~~~

在 Python 3.8 之前，CPython 的初始化依赖散落在各处的全局变量（如 ``Py_OptimizeFlag``、``Py_VerboseFlag``），极易引发 C 扩展嵌入时的状态污染与竞态。**PEP 587（Python Initialization Configuration）** 将初始化流程统一抽象为两级结构体：
1. **``PyPreConfig``（预初始化配置）**：负责在 Python 内存分配器就绪前，配置 C 运行库的 Locale（如 UTF-8 Mode 判定、``LC_CTYPE`` 强制转换）以及全局内存分配器类型（``MIMALLOC`` / ``PYMALLOC`` / ``MALLOC``）；
2. **``PyConfig``（核心运行时配置）**：以纯结构体形式封装所有启动参数（包括命令行参数 ``argv``、环境变量、模块搜索路径 ``sys.path``、JIT 标志、安全与审计钩子等）。

CPython 启动四阶段全景流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     CPython 3.13+ 启动全景四阶段流水线                  |
   +=========================================================================+
   | Stage 0: 进程入口与预初始化 (Pre-Initialization)                        |
   | └─ main() ──► Py_BytesMain() ──► Py_PreInitializeFromConfig()           |
   |    (解析 Locale、启用 UTF-8 模式、初始化底层全局 _PyRuntimeState)       |
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | Stage 1: 核心初始化 (Core Initialization - pyinit_core)                 |
   | ├── 创建主解释器状态 (PyInterpreterState) 与主线程状态 (PyThreadState)  |
   | ├── 初始化全局单例 (None, True, False, 空元组/空字符串) 与不可变不朽标记 |
   | ├── 初始化内置基础类型系统 (Type, Long, Unicode, Dict, Tuple, List, Set) |
   | ├── 创建 sys 模块与 builtins 模块, 注入通用常量池与 callable 缓存        |
   | └── 启动核心导入机制 (_PyImport_InitCore, 仅支持 builtin/frozen 模块)   |
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | Stage 2: 主运行时初始化 (Main Initialization - pyinit_main)             |
   | ├── 计算并装载模块搜索路径 (_PyPathConfig_UpdateGlobal -> sys.path)     |
   | ├── 引导外部导入系统 (_PyImport_InitExternal -> 激活 importlib.bootstrap)|
   | ├── 初始化标准 I/O 流 (sys.stdin, sys.stdout, sys.stderr) 与 TextIOWrap  |
   | ├── 注册操作系统中断信号处理器 (_PySignal_Init) 与 TraceMalloc/FaultHdl |
   | ├── 创建 __main__ 顶层执行模块, 导入 site.py (加载 site-packages)       |
   | └── 激活 Tier 2 优化器与 Copy-and-Patch JIT 编译器引擎 (interp->jit=true)|
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | Stage 3: 代码执行与终结清理 (Execution & Py_FinalizeEx)                 |
   | ├── 依据 CLI 参数分发执行: 交互式 REPL / 脚本文件 / 模块(-m) / 命令(-c) |
   | └── 退出时执行 Py_FinalizeEx(): 冲刷流、等待线程、执行 atexit、GC 回收  |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
2. 进程引导与预初始化（Stage 0）
-----------------------------------------------------------------------------

C 语言入口与 `_PyRuntimeState` 实例化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当可执行文件启动时，首先进入 ``Programs/python.c`` 的 ``main()``：

.. code-block:: c

   int
   main(int argc, char **argv)
   {
       return Py_BytesMain(argc, argv);
   }

在 ``Modules/main.c`` 中，``Py_BytesMain`` 调用 ``pymain_main()``，首先触发 ``_PyRuntime_Initialize()``：
- 在进程的 BSS 段分配全局唯一的 ``_PyRuntimeState _PyRuntime`` 物理单例；
- 初始化全局原子锁、Parking-Lot 等待队列以及底层 C 线程局部存储（TLS）。

Locale 强制转换（Locale Coercion）与 UTF-8 模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 POSIX 系统中，若环境变量检测到传统的 ``LC_CTYPE=C``（默认 7 位 ASCII 编码），CPython 会在 ``_Py_CoerceLegacyLocale()`` 中自动将 Locale 强制升级为 ``C.UTF-8`` 或 ``UTF-8``。这一步必须在创建任何 Python 字符串对象之前完成，以确保后续宽字符（``wchar_t*``）与命令行参数能够无损转码。

-----------------------------------------------------------------------------
3. 核心初始化阶段（Stage 1: pyinit_core）
-----------------------------------------------------------------------------

主解释器与主线程状态就绪
~~~~~~~~~~~~~~~~~~~~~~~~

在 ``Python/pylifecycle.c`` 的 ``pycore_create_interpreter()`` 中：
1. **创建主解释器**：调用 ``_PyInterpreterState_New()`` 分配全局根解释器 ``interp``；
2. **初始化内存子系统**：调用 ``_PyMem_init_obmalloc(interp)`` 绑定全局内存池或 Mimalloc 线程局部堆；
3. **创建主线程**：调用 ``_PyThreadState_New()`` 创建进程主执行线程 ``tstate``，并将其绑定至运行时 ``runtime->main_tstate = tstate``；
4. **初始化锁机制**：在非自由线程构建中调用 ``_PyEval_InitGIL(tstate)`` 初始化全局 GIL 互斥量。

全局单例与内置类型就绪（`pycore_init_types`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

此时内存中尚未存在任何 Python 对象，解释器执行基础类型的自举（Bootstrap）：
1. **静态单例物理初始化**：创建不可变对象单例（``Py_None``、``Py_True``、``Py_False``、空字符串 ``""``、空元组 ``()``），并调用 ``_Py_SetImmortal()`` 将其引用计数标记为永不销毁；
2. **元类型与内建类型装配**：
   - 调用 ``_PyTypes_InitTypes(interp)`` 初始化 ``PyType_Type``（元类型 ``type``）与 ``PyBaseObject_Type``（基类 ``object``）；
   - 依次调用 ``_PyLong_InitTypes``、``_PyUnicode_InitTypes``、``_PyFloat_InitTypes``、``_PyExc_InitTypes`` 完成所有内置数据结构和异常层次结构的虚函数槽位（``tp_*``）填充与 MRO 继承拓扑构建。

`sys` 与 `builtins` 创世模块生成
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``pycore_init_builtins()`` 与 ``_PySys_Create()`` 中：
- 创建全局命名空间字典并挂载至 ``interp->builtins`` 与 ``interp->sysdict``；
- 将常用高频常量（如 ``AssertionError``, ``len``, ``isinstance``, ``list.append``）注入解释器的 ``callable_cache`` 高速查找缓存；
- 调用 ``_PyImport_InitCore()``，构建能够加载内置 C 模块与内置冻结字节码的极简核心导入表。

-----------------------------------------------------------------------------
4. 主运行时初始化阶段（Stage 2: pyinit_main）
-----------------------------------------------------------------------------

装载 `sys.path` 与引导 `importlib`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``init_interp_main()`` 中：
1. **路径计算**：``_PyPathConfig_UpdateGlobal()`` 结合可执行文件路径（``PYTHONHOME`` / 虚拟环境 ``pyvenv.cfg``），计算标准库路径前缀，注入 ``sys.path``；
2. **自举外部导入器**：调用 ``_PyImport_InitExternal()``，将预先编译在解释器内部的冻结字节码（``_frozen_importlib`` 与 ``_frozen_importlib_external``）反序列化为代码对象，构建完整的纯 Python 模块搜索体系（PathFinder / FileLoader）。

标准 I/O 流包装与 `__main__` 命名空间
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 调用 ``init_sys_streams()``：打开操作系统标准文件描述符（fd 0, 1, 2），使用 ``_io.TextIOWrapper`` 对二进制缓冲区进行字符编解码封装，注入 ``sys.stdin``、``sys.stdout``、``sys.stderr``；
- 调用 ``init_set_builtins_open()`` 将内建函数 ``open()`` 重定向至高性能底层 ``_io.open``；
- 调用 ``add_main_module()`` 创建顶级运行模块 ``__main__``，注入 ``__builtins__`` 引用与默认加载器。

加载 `site.py` 与 JIT 编译引擎激活
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **导入 site 模块**：调用 ``init_import_site()`` 执行标准库 ``site.py``，解析 ``.pth`` 路径文件并将第三方包路径（``site-packages``）推入 ``sys.path``；
2. **激活 JIT 与 Tier 2 优化器**：检测配置标志与环境变量 ``PYTHON_JIT``，若启用则置位 ``interp->jit = true``，初始化微指令（uops）执行器轨迹缓存池。

-----------------------------------------------------------------------------
5. 代码执行与优雅终结（Stage 3: Py_FinalizeEx）
-----------------------------------------------------------------------------

代码分发执行
~~~~~~~~~~~~

解释器就绪后，控制权交由 ``Modules/main.c`` 的 ``pymain_run_python()`` 进行分发：
- **`-c cmd`**：调用 ``PyRun_SimpleStringFlags()`` 编译并执行单行代码；
- **`-m module`**：调用 ``_PyRun_SimpleModule()`` 借助 ``runpy`` 模块加载并执行入口点；
- **`file.py`**：调用 ``_PyRun_SimpleFileObject()`` 读取源文件，经过词法解析、AST 生成、字节码编译后交由 CEval 循环执行；
- **交互式环境**：若无参数或带 ``-i``，调用 ``_PyRun_InteractiveLoopGeneric()`` 开启标准 REPL 循环。

优雅终结协议（`Py_FinalizeEx`）物理析构时序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

程序执行完毕后，必须调用 ``Py_FinalizeEx()`` 逆向拆卸虚拟机，防止数据丢失与资源泄露：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                    Py_FinalizeEx() 物理终结倒序时序                     |
   +=========================================================================+
   | 1. 等待线程收工: wait_for_thread_shutdown() 等待所有非守护线程退出      |
   | 2. 触发回调函数: 调用 atexit 注册的所有用户清理钩子                     |
   | 3. 清理子解释器: finalize_subinterpreters() 销毁所有并发子解释器        |
   | 4. 冲刷标准 I/O: flush_std_files() 强制同步 sys.stdout 与 sys.stderr    |
   | 5. 模块大拆卸: finalize_modules() 将 sys.modules 内所有模块键值置 None  |
   | 6. 终结垃圾回收: PyGC_Collect() 触发最后一次循环垃圾回收与析构器终结    |
   | 7. 销毁类型单例: finalize_interp_types() 释放 interned 字符串与基础类型 |
   | 8. 释放内存与运行时: _PyMem_FiniDelayed() 释放延迟堆, 销毁 _PyRuntime   |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 运行时的完整初始化图谱：
1. PEP 587 两级配置模型（``PyPreConfig`` 与 ``PyConfig``）与启动四阶段流水线；
2. 进程入口 ``main()`` 与全局单例 ``_PyRuntimeState`` 的内存分配与 Locale 强制转换；
3. ``pyinit_core`` 阶段主解释器、主线程、不可变单例、内置类型系统与核心模块的创世构建；
4. ``pyinit_main`` 阶段搜索路径计算、冻结 ``importlib`` 自举、标准 I/O 包装、``site.py`` 加载与 JIT 引擎就绪；
5. ``Py_FinalizeEx()`` 在进程退出时的八步严格逆向清理时序。

在虚拟机初始化完成后，Python 程序最核心的外部能力便是模块加载。下一章我们将对其中最精妙的自举子系统进行深度解构—— **06_module_import_and_runtime_lifecycle/02_importlib_and_frozen_modules.rst（导入子系统 Importlib、字节码冻结模块与 sys.modules 缓存表）**。
