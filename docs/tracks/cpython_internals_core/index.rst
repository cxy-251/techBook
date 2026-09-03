======================================================
CPython 3.13+ 虚拟机与内核运行全景深度剖析
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书目录导航
   :numbered:

   ROADMAP
   01_object_model_and_memory/index
   02_parser_and_compilation/index
   03_frame_and_eval_loop/index
   04_builtins_and_data_structures/index
   05_concurrency_and_free_threading/index
   06_module_import_and_runtime_lifecycle/index
   07_jit_and_advanced_execution/index

专著简介与架构全景
==================

本书是一本以 CPython 3.13+ / 3.14 / 3.16 核心源码为基础，自底向上剖析 Python 语言运行时、虚拟机、对象内存模型、并发架构与 JIT 编译器的硬核技术专著。

全书坚持“物理内存与源码真实实现优先”原则，杜绝悬浮抽象概念，从 C 语言数据结构拓扑、底层系统调用、内存对齐与 CPU 指令流出发，完整拆解 Python 程序从源代码字符流到虚拟机执行、再到 JIT 本地机器码生成的全生命周期物理链路。

核心知识模块拓扑
----------------

1. **对象模型与内存基石 (01_object_model_and_memory)**
   - PyObject 基础结构、定长/变长对象头与引用计数机制
   - PyTypeObject 元类型、tp_* 槽位分发机制与 MRO 继承拓扑
   - 内存分配器架构：从 PyMem/PyObject 内存池到 Python 3.13+ 引入的 Mimalloc 深度剖析
   - 分代垃圾回收器、循环引用检测算法与 gc_generation 双向链表物理拓扑

2. **前端编译与 AST 生成 (02_parser_and_compilation)**
   - PEG 解析器架构、Grammar 规则与词法分析 Tokenizer 状态机
   - 具象语法树 CST 到抽象语法树 AST 的构建与符号表 Symbol Table 生成
   - 控制流图 CFG 构建、Basicblock 划分与字节码编译器 CodeGen 流程
   - 窥孔优化器 Peephole Optimizer、常量折叠与指令特化准备

3. **虚拟机栈帧与 CEval 解释器核心 (03_frame_and_eval_loop)**
   - _PyInterpreterFrame 物理栈帧结构、局部变量与值栈布局
   - _PyEval_EvalFrameDefault 执行状态机、Direct Threaded Code 与指令分发
   - PEP 659 自适应指令特化机制 Adaptive Bytecode 与 Quickening 状态转换
   - 零开销异常处理表 Exception Table 与栈回溯 Unwinding 物理机制

4. **核心内建数据结构实现 (04_builtins_and_data_structures)**
   - 字典紧凑哈希表 Compact Dict、DKIX 表与 Split Table 内存优化
   - Unicode 紧凑字符串表示 FSR：1-byte, 2-byte, 4-byte 字符紧凑编码
   - 元组不变性优化与列表过度分配 Over-allocation 扩容策略
   - 集合开放寻址法、扰动哈希探查冲突解决算法

5. **并发、GIL 与 3.13+ Free-Threading (05_concurrency_and_free_threading)**
   - 传统 GIL 全局解释器锁底层机制、竞争与切换时机
   - PEP 703 Free-Threading 架构全景：禁用 GIL 后的内存安全性模型
   - 偏向引用计数 Biased Reference Counting、线程私有 vs 共享计数器
   - Free-Threaded 模式下的 Stop-the-World 安全点停顿机制与 GC

6. **运行时生命周期与导入系统 (06_module_import_and_runtime_lifecycle)**
   - CPython 启动流程：从 main() 到 Py_InitializeEx 的运行时初始化图谱
   - 导入子系统 Importlib、字节码冻结模块与 sys.modules 缓存表
   - C 扩展模块加载、PyMethodDef 结构与 Stable ABI / Limited API 机制
   - PEP 684/PEP 554 多子解释器 Sub-interpreters 与独立 GIL 隔离

7. **Python 3.13+ Copy-and-Patch JIT 与未来展望 (07_jit_and_advanced_execution)**
   - Tier 2 优化器架构、微指令 uops 轨迹提取与 Trace 执行
   - Copy-and-Patch JIT 原理：Clang 模板编译与机器码拼接
   - JIT 守卫 Guard 指令、去优化 Deoptimization 与回退机制
