======================================================
第 6 模块：运行时生命周期与导入系统
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_cpython_init_and_pymain
   02_importlib_and_frozen_modules
   03_c_extension_and_limited_api
   04_subinterpreters_and_per_interpreter_gil

模块概述
========

本模块完整追踪 CPython 解释器从进程启动到销毁的全生命周期。

从操作系统入口 `main()` 到 `Py_InitializeFromConfig` 的内核初始化图谱；剖析 `_PyRuntime` 全局状态、进程级锁、线程状态（`PyThreadState`）绑定；解构 Importlib 导入子系统、Finder 与 Loader 机制、字节码冻结（Frozen Modules）与 `sys.modules` 缓存；深入 C 扩展模块加载、`PyMethodDef` 与 Stable ABI / Limited API 机制；探讨 PEP 684/554 多子解释器（Sub-interpreters）与 Per-interpreter GIL 的隔离模型。
