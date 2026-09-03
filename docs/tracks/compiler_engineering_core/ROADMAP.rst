========================================================================
现代编译器架构设计与程序转换优化全景深度剖析：工程图谱
========================================================================

.. note:: 单一事实源说明
   本文件是《现代编译器架构设计与程序转换优化全景深度剖析》全书各章节编写状态与知识依赖的唯一权威图谱。所有自动化写作任务与调度器均以此文件的完成状态作为推进依据。

总体进度概览
============

- **总规划模块数**：9 个核心系统模块
- **总规划章节数**：45 节深度专著章节
- **已完成章节**：45 节（全书 9 个核心模块 45 节已全量完工结项！）
- **当前写作状态**：全书 45 节已全部完工落盘！达成端到端完整闭环。

.. contents::
   :local:
   :depth: 2

------------------------------------------------------------------------

模块详细进度与章节清单
======================

第 1 模块：编译器世界观与工程心智模型 (01_compiler_worldview_and_mental_model)
------------------------------------------------------------------------------

- [x] ``01_compiler_transformation_model.rst`` - 编译器转换模型：源码文本、程序语义、阶段边界与语义保持契约
- [x] ``02_source_code_as_a_structured_system.rst`` - 源码作为结构化系统：文本表面形式、注释与排版、未定义行为与语义间隙，以及优化代码偏离源码形态的物理本质
- [x] ``03_compilation_as_a_sequence_of_representations.rst`` - 编译作为表示流转序列：Token、AST、High-Level IR、Low-Level IR 到 Machine IR 的抽象降级与信息守恒
- [x] ``04_interpreter_compiler_transpiler_and_jit.rst`` - 执行范式全景：解释器、AOT 编译、Transpiler 与 JIT 动态反馈的成本支付阶段权衡
- [x] ``05_compiler_correctness_performance_and_developer_experience.rst`` - 编译器工程契约：语义保持正确性、编译耗时/产物性能取舍与诊断调试信息保留

第 2 模块：词法分词、语法分析与 AST 构建 (02_lexical_syntax_analysis_and_ast)
-------------------------------------------------------------------------------

- [x] ``01_source_stream_encoding_and_source_locations.rst`` - 源码字符流与物理编码：UTF-8 字节流、行/列/偏移量 SourceLocation 元数据与平台换行归一化
- [x] ``02_lexical_state_machine_tokens_and_trivia.rst`` - 词法状态机与 Token 流：Lexeme 词素、最长匹配原则、二义性裁决与 Whitespace/Comment 附着
- [x] ``03_grammars_and_recursive_descent_parsing.rst`` - 形式文法与递归下降解析：产生式规则、左递归消除、回溯抑制与上下文相关文法处理
- [x] ``04_pratt_parsing_and_operator_precedence.rst`` - 表达式优先级与 Pratt 算法：Binding Power 结合力、前缀/中缀/后缀统一解析与二义性消除
- [x] ``05_ast_topology_and_parser_error_recovery.rst`` - AST 节点拓扑与语法错误恢复：CST 向 AST 简化、Panic Mode 恐慌恢复与同步 Token 探测

第 3 模块：语义分析、作用域与类型系统 (03_semantic_analysis_and_type_systems)
-------------------------------------------------------------------------------

- [x] ``01_symbol_tables_and_nested_scope_chains.rst`` - 符号表物理拓扑与嵌套作用域链：声明/使用绑定、变量遮蔽 (Shadowing) 与自由变量/闭包捕获
- [x] ``02_declarations_name_resolution_and_modules.rst`` - 名字决议与模块依赖图：多遍扫描 (Multi-Pass) 查找、重载决议候选集与跨模块符号可见性
- [x] ``03_static_typing_and_structural_vs_nominal_equivalence.rst`` - 静态类型系统基石：名义类型 vs 结构类型等价性、子类型多态与类型规则健全性
- [x] ``04_type_checking_conversions_and_generics.rst`` - 表达式类型检查与泛型实例化：隐式转换截断、单态化 (Monomorphization) 与类型擦除
- [x] ``05_type_inference_and_unification_algorithms.rst`` - 局部与全局类型推导：类型变量、方程约束收集与 Hindley-Milner / Unification 合一求解算法

第 4 模块：中间表示 (IR)、控制流图 (CFG) 与 SSA 形式 (04_ir_cfg_and_ssa_construction)
---------------------------------------------------------------------------------------

- [x] ``01_ir_design_working_language_and_lowering.rst`` - 中间表示 (IR) 设计哲学：高层语言语义保留与机器无关性前端解耦、受控降级 (Lowering)
- [x] ``02_basic_blocks_terminators_and_cfg_topology.rst`` - 基本块与控制流图 (CFG)：单入口单出口区间、Terminator 终止指令与前驱后继边拓扑
- [x] ``03_dominance_frontiers_and_natural_loops.rst`` - 支配关系与自然循环识别：不可达块消除、支配树 (Dominator Tree) 构建与回边 (Backedge) 检测
- [x] ``04_ssa_form_value_identity_and_phi_nodes.rst`` - SSA 静态单赋值形式核心：变量槽位向唯一计算值映射、Phi 节点语义与 Mem2Reg 栈提升
- [x] ``05_ssa_destruction_and_phi_elimination.rst`` - SSA 销毁与 Phi 消除：并行拷贝冲突、关键边分割 (Critical Edge Splitting) 与寄存器降级

第 5 模块：数据流分析与中端优化 Pass 体系 (05_data_flow_analysis_and_optimizations)
------------------------------------------------------------------------------------

- [x] ``01_data_flow_framework_lattices_and_fixed_points.rst`` - 数据流分析框架：传递函数 (Transfer Function)、格理论 (Lattice) 与不动点单调迭代收敛
- [x] ``02_reaching_definitions_liveness_and_use_def_chains.rst`` - 到达定值与活跃变量分析：Kill/Gen 集合构建、Def-Use / Use-Def 链与死代码消除 (DCE)
- [x] ``03_constant_propagation_gvn_and_cse.rst`` - 全局值编号 (GVN) 与公共子表达式消除：稀疏条件常量传播 (SCCP)、代数恒等式化简与支配树折叠
- [x] ``04_memory_alias_analysis_and_memory_ssa.rst`` - 内存别名分析 (Alias Analysis)：Must/May/No-Alias 判定、逃逸分析与 MemorySSA 建模
- [x] ``05_loop_optimizations_licm_unroll_and_vectorization.rst`` - 循环优化与自动向量化：循环不变量外提 (LICM)、循环展开/分块 (Tiling) 与 SIMD 代码生成

第 6 模块：后端基石、指令选择与指令调度 (06_backend_and_instruction_selection)
-------------------------------------------------------------------------------

- [x] ``01_target_machine_model_and_target_triples.rst`` - 目标机模型与硬件描述：TargetTriple、DataLayout 字节序/对齐、寻址模式与合法化 (Legalization)
- [x] ``02_instruction_selection_and_dag_pattern_matching.rst`` - 指令选择算法：树形覆盖匹配、SelectionDAG 图重写与 GlobalISel 现代后端管线
- [x] ``03_machine_ir_and_pseudo_instruction_expansion.rst`` - Machine IR 物理形态：无限虚拟寄存器、目标伪指令展开与流水线感知指令调度
- [x] ``04_instruction_scheduling_and_hazard_mitigation.rst`` - 指令调度与冒险规避：数据冒险 (RAW/WAR/WAW)、流水线延迟槽、列表调度 (List Scheduling)
- [x] ``05_backend_correctness_and_target_flags.rst`` - 后端正确性保证：ISA 标志位溢出语义、分支条件码折叠与机器码验证

第 7 模块：寄存器分配、栈帧布局与 ABI 规范 (07_register_allocation_stack_and_abi)
---------------------------------------------------------------------------------

- [x] ``01_liveness_intervals_and_interference_graphs.rst`` - 变量生命周期与冲突图：活跃区间 (Live Interval) 分析、冲突边建立与寄存器压力评估
- [x] ``02_graph_coloring_and_linear_scan_allocation.rst`` - 寄存器分配核心算法：Chaitin-Briggs 图着色 (Graph Coloring) 与 Poletto 线性扫描 (Linear Scan)
- [x] ``03_spill_code_generation_and_stack_slot_coloring.rst`` - 溢出代码生成与栈槽复用：溢出代价评估、栈槽生命周期重叠判定与微架构热路径保护
- [x] ``04_stack_frame_layout_prologue_and_epilogue.rst`` - 栈帧物理布局与函数序言/尾声：RBP/RSP 调整、Red Zone 保护区、动态全栈对齐与寄存器保护
- [x] ``05_calling_conventions_and_system_abi_contracts.rst`` - 调用约定与系统 ABI 契约：System V vs MSVC ABI 参数寄存器分发、结构体传参及跨语言调用

第 8 模块：目标文件、链接加载与运行时虚拟机 (08_linking_runtime_vms_and_jit)
-----------------------------------------------------------------------------

- [x] ``01_object_file_formats_elf_macho_and_pe.rst`` - 目标文件物理拓扑：段 (Sections) 与加载段 (Segments)、符号表、DWARF 调试行表 (.debug_line)
- [x] ``02_static_linking_relocations_and_symbol_resolution.rst`` - 静态链接与重定位：符号合并决议、重定位记录计算 (R_X86_64_PC32) 与 Weak 符号处理
- [x] ``03_dynamic_linking_pic_got_and_plt.rst`` - 动态链接与位置无关代码 (PIC)：Global Offset Table (GOT)、Procedure Linkage Table (PLT) 延迟绑定
- [x] ``04_bytecode_interpreters_and_evaluation_loops.rst`` - 字节码解释器与分发循环：栈式 vs 寄存器式 VM、Switch-Case 与 Direct Threaded Code 效率
- [x] ``05_jit_compilation_tiered_execution_and_deoptimization.rst`` - JIT 动态编译与分层执行：热点探测计数器、推测特化 (Speculative Inlining)、去优化 (Deopt) 与 OSR

第 9 模块：现代多层编译体系、MLIR 与微型编译器实战 (09_modern_mlir_and_mini_compiler)
---------------------------------------------------------------------------------------

- [x] ``01_llvm_pass_manager_and_infrastructure_engineering.rst`` - LLVM 基础设施与 PassManager：模块化管线、PreservedAnalyses 缓存与 opt/FileCheck 实战
- [x] ``02_mlir_dialects_and_progressive_lowering.rst`` - MLIR 多层中间表示：Dialect 扩展哲学、Operation/Region/Type 系统与渐进降级 (Progressive Lowering)
- [x] ``03_domain_specific_compilers_gpu_and_ai_graphs.rst`` - 领域特定编译器：SPIR-V 着色器编译、AI 计算图算子融合 (Operator Fusion) 与 Tensor IR
- [x] ``04_building_a_mini_compiler_frontend_and_ir.rst`` - 从零构建微型编译器（前端与 IR）：手写词法分析、递归下降 Parser、类型检查与三地址码 IR 生成
- [x] ``05_building_a_mini_compiler_backend_and_codegen.rst`` - 从零构建微型编译器（后端与机器码）：CFG 构建、简易寄存器分配、x86-64/ARM64 汇编生成与端到端运行验证
