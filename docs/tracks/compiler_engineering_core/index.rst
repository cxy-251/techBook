====================================================================
现代编译器架构设计与程序转换优化全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书 9 大核心系统模块体系目录:
   :numbered:

   ROADMAP
   01_compiler_worldview_and_mental_model/index
   02_lexical_syntax_analysis_and_ast/index
   03_semantic_analysis_and_type_systems/index
   04_ir_cfg_and_ssa_construction/index
   05_data_flow_analysis_and_optimizations/index
   06_backend_and_instruction_selection/index
   07_register_allocation_stack_and_abi/index
   08_linking_runtime_vms_and_jit/index
   09_modern_mlir_and_mini_compiler/index

专著简介与架构全景
==================

本专著是一部立足于工业级编译器全栈架构、程序表示流转、中间表示（IR）、静态单赋值（SSA）、全链路转换优化、后端指令选择与跨领域编译技术（LLVM / MLIR / CPython / WebAssembly / SPIR-V / AI 计算图 / 数据库优化器）的全景深度技术著作。

全书坚持“语义保持契约与机器物理约束优先”原则，自顶向下解构从源码字符流到 AST、从 AST 到 SSA IR、从中端分析优化 Pass 到后端机器指令与目标文件链接的完整生命周期，彻底拆解现代编译器将人类抽象意图压缩转化为硬件物理指令的工程机理。

核心知识模块拓扑
----------------

.. list-table:: 编译器工程架构核心知识体系映射
   :widths: 8 22 40 30
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 微架构关键机制与核心路径
     - 解决的核心工程问题
   * - 01
     - 编译器世界观与工程心智模型
     - 转换模型、源码物理系统、表示流转序列、执行范式全景与正确性工程契约
     - 建立严格基于语义保持与抽象降级的编译器工程心智
   * - 02
     - 词法分词、语法分析与 AST 构建
     - UTF-8 字符流、SourceLocation 追踪、词法状态机、Pratt 优先级解析与错误恢复
     - 保证代码解析鲁棒性，产出高保真 AST 与源码映射
   * - 03
     - 语义分析、作用域与类型系统
     - 作用域链拓扑、名字查找决议、类型规则系统、泛型单态化与合一推导算法
     - 消除歧义与非法语义，建立强类型程序事实
   * - 04
     - 中间表示 (IR)、CFG 与 SSA 形式
     - 多级 Lowering、基本块控制流图、支配树 Dominance、SSA 形式与 Mem2Reg 栈提升
     - 建立显式值流动与控制流拓扑，奠定优化基石
   * - 05
     - 数据流分析与中端优化 Pass 体系
     - 格不动点迭代、活跃变量/到达定值、GVN/SCCP、内存别名/MemorySSA 与循环向量化
     - 消除冗余计算与内存瓶颈，最大化算法执行效率
   * - 06
     - 后端基石、指令选择与指令调度
     - 目标机抽象 TargetTriple、DAG 指令选择、伪指令展开与流水线指令调度
     - 高效将中间表示映射至目标 ISA 硬件指令
   * - 07
     - 寄存器分配、栈帧布局与 ABI 规范
     - 活跃区间分析、图着色与线性扫描分配、栈槽着色、序言尾声与 System V ABI
     - 解决稀缺寄存器资源竞争，确立跨边界二进制调用契约
   * - 08
     - 目标文件、链接加载与运行时虚拟机
     - ELF/Mach-O 格式、重定位记录、PLT/GOT 动态链接、字节码 VM 与分层 JIT
     - 弥合静态代码与运行时执行边界，实现自适应动态特化
   * - 09
     - 现代多层编译体系、MLIR 与微型编译器实战
     - LLVM PassManager、MLIR Dialect 渐进降级、AI/GPU 领域编译与端到端小编译器实战
     - 复用现代编译基建，融会贯通编译器全栈实现能力

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
