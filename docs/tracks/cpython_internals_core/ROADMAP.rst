==================================================
CPython 3.13+ 虚拟机与内核运行全景深度剖析：工程图谱
==================================================

.. note:: 单一事实源说明
   本文件是《CPython 3.13+ 虚拟机与内核运行全景深度剖析》全书各章节编写状态与知识依赖的唯一权威图谱。所有自动化写作任务与调度器均以此文件的完成状态作为推进依据。

总体进度概览
============

- **总规划模块数**：7 个核心模块
- **总规划章节数**：27 节深度专著章节
- **已完成章节**：27 节（完成度 100.0%）
- **当前写作状态**：【全书圆满竣工】全部 7 大模块、27 篇长篇深度专著章节均已全量落盘并挂载完成！

.. contents::
   :local:
   :depth: 2

--------------------------------------------------

模块详细进度与章节清单
======================

第 1 模块：对象模型与内存基石 (01_object_model_and_memory)
----------------------------------------------------------

- [x] ``01_pyobject_header_and_ob_refcnt.rst`` - PyObject 基础结构、定长/变长对象头与引用计数机制（含 Free-Threading 偏向计数与静态不朽对象）
- [x] ``02_type_object_and_slot_dispatch.rst`` - PyTypeObject 元类型、tp_* 槽位分发机制与 MRO 继承拓扑
- [x] ``03_pyarena_and_mimalloc_allocator.rst`` - 内存分配器架构：从 PyMem/PyObject 内存池到 Python 3.13+ 引入的 Mimalloc 深度剖析
- [x] ``04_gc_and_cyclic_references.rst`` - 分代垃圾回收器、循环引用检测算法与 gc_generation 双向链表物理拓扑

第 2 模块：前端编译与 AST 生成 (02_parser_and_compilation)
----------------------------------------------------------

- [x] ``01_peg_parser_and_grammar.rst`` - PEG 解析器架构、Grammar 规则与词法分析 Tokenizer 状态机
- [x] ``02_cst_to_ast_transformation.rst`` - 具象语法树 CST 到抽象语法树 AST 的构建与符号表 Symbol Table 生成
- [x] ``03_bytecode_generation_and_cfg.rst`` - 控制流图 CFG 构建、Basicblock 划分与字节码编译器 CodeGen 流程
- [x] ``04_peephole_and_bytecode_optimization.rst`` - 窥孔优化器 Peephole Optimizer、常量折叠与指令特化准备

第 3 模块：虚拟机栈帧与 CEval 解释器核心 (03_frame_and_eval_loop)
------------------------------------------------------------------

- [x] ``01_pyframeobject_and_stack_layout.rst`` - _PyInterpreterFrame 物理栈帧结构、局部变量与值栈布局
- [x] ``02_ceval_interpreter_loop.rst`` - _PyEval_EvalFrameDefault 执行状态机、Direct Threaded Code 与指令分发
- [x] ``03_specialized_adaptive_interpreter.rst`` - PEP 659 自适应指令特化机制 Adaptive Bytecode 与 Quickening 状态转换
- [x] ``04_exception_table_and_unwinding.rst`` - 零开销异常处理表 Exception Table 与栈回溯 Unwinding 物理机制

第 4 模块：核心内建数据结构实现 (04_builtins_and_data_structures)
------------------------------------------------------------------

- [x] ``01_compact_dict_and_split_table.rst`` - 字典紧凑哈希表 Compact Dict、DKIX 表与 Split Table 内存优化
- [x] ``02_unicode_flexible_representation.rst`` - Unicode 紧凑字符串表示 FSR：1-byte, 2-byte, 4-byte 字符紧凑编码
- [x] ``03_pytuple_and_pylist_resizing.rst`` - 元组不变性优化与列表过度分配 Over-allocation 扩容策略
- [x] ``04_set_and_frozenset_probing.rst`` - 集合开放寻址法、扰动哈希探查冲突解决算法

第 5 模块：并发、GIL 与 3.13+ Free-Threading (05_concurrency_and_free_threading)
---------------------------------------------------------------------------------

- [x] ``01_gil_internals_and_mutex_mechanisms.rst`` - 传统 GIL 全局解释器锁底层机制、竞争与切换时机
- [x] ``02_pep_703_free_threaded_cpython.rst`` - PEP 703 Free-Threading 架构全景：禁用 GIL 后的内存安全性模型
- [x] ``03_biased_reference_counting.rst`` - 偏向引用计数 Biased Reference Counting、线程私有 vs 共享计数器
- [x] ``04_thread_safe_stop_the_world_and_gc.rst`` - Free-Threaded 模式下的 Stop-the-World 安全点停顿机制与 GC

第 6 模块：运行时生命周期与导入系统 (06_module_import_and_runtime_lifecycle)
-----------------------------------------------------------------------------

- [x] ``01_cpython_init_and_pymain.rst`` - CPython 启动流程：从 main() 到 Py_InitializeEx 的运行时初始化图谱
- [x] ``02_importlib_and_frozen_modules.rst`` - 导入子系统 Importlib、字节码冻结模块与 sys.modules 缓存表
- [x] ``03_c_extension_and_limited_api.rst`` - 语法分析与 C 扩展模块加载、PyMethodDef 结构与 Stable ABI / Limited API 机制
- [x] ``04_subinterpreters_and_per_interpreter_gil.rst`` - PEP 684/PEP 554 多子解释器 Sub-interpreters 与独立 GIL 隔离

第 7 模块：Python 3.13+ Copy-and-Patch JIT 与未来展望 (07_jit_and_advanced_execution)
--------------------------------------------------------------------------------------

- [x] ``01_tier2_ir_and_micro_ops.rst`` - Tier 2 优化器架构、微指令 uops 轨迹提取与 Trace 执行
- [x] ``02_copy_and_patch_jit_compilation.rst`` - Copy-and-Patch JIT 原理：Clang 模板编译与机器码拼接
- [x] ``03_jit_guard_and_deoptimization.rst`` - JIT 守卫 Guard 指令、去优化 Deoptimization 与回退机制
