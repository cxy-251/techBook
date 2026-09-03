========================================================================
现代C++对象模型与STL工程内核全景深度剖析：工程图谱
========================================================================

.. note:: 单一事实源说明
   本文件是《现代C++对象模型与STL工程内核全景深度剖析》全书各章节编写状态与知识依赖的唯一权威图谱。所有自动化写作任务与调度器均以此文件的完成状态作为推进依据。

总体进度概览
============

- **总规划模块数**：8 个核心系统模块
- **总规划章节数**：40 节深度专著章节
- **已完成章节**：40 节（第 1、2、3、4、5、6、7、8 模块全量完工，全书进度达 100% 结项）
- **当前写作状态**：全书 8 个核心系统模块、全部 40 节深度专著章节已全量落盘完工结项。

.. contents::
   :local:
   :depth: 2

------------------------------------------------------------------------

模块详细进度与章节清单
======================

第 1 模块：C++ 底层基石与对象模型 (01_cpp_low_level_foundations)
------------------------------------------------------------------

- [x] ``01_cpp_object_model.rst`` - C++ 底层对象模型与内存布局：身份、存储期、对齐与虚表拓扑
- [x] ``02_object_lifetime_and_construction_state_machine.rst`` - 对象生命周期状态机：存储分配、构造函数家族、赋值重载、临时对象生命周期延长与析构销毁顺序
- [x] ``03_move_semantics_and_value_categories.rst`` - 右值引用与移动语义深度解析：值类别 (lvalue/xvalue/prvalue)、std::move、完美转发折叠与 moved-from 状态
- [x] ``04_memory_management_primitives_and_raii.rst`` - 物理内存管理体系与 RAII 哲学：malloc/free 与 new/delete 表达式解构、placement new、未初始化内存与缓存局部性
- [x] ``05_template_instantiation_and_two_phase_lookup.rst`` - 泛型模板底层基石：实例化机制、参数推导、变长参数包展开、依赖类型 typename 与二阶段名字查找

第 2 模块：STL 核心机制与内存子系统 (02_stl_core_mechanisms_and_allocators)
----------------------------------------------------------------------------

- [x] ``01_iterator_taxonomy_and_traits_system.rst`` - 迭代器核心体系与能力分层：输入/输出/前向/双向/随机/连续迭代器拓扑、traits 萃取与适配器模型
- [x] ``02_allocator_concept_and_allocator_traits.rst`` - 内存分配器体系：allocator 接口契约、allocator_traits 统一抽象、未初始化内存批量构造算法
- [x] ``03_polymorphic_memory_resources_pmr.rst`` - std::pmr 多态内存资源：std::pmr::memory_resource、单调内存池 (monotonic_buffer_resource) 与无锁分配器
- [x] ``04_exception_safety_guarantees_and_rollbacks.rst`` - 异常安全保证与回滚机制：基本保证/强保证/不抛保证、noexcept 移动判定与 vector 扩容事务一致性
- [x] ``05_generic_algorithm_decoupling_philosophy.rst`` - 泛型算法解耦哲学：半开区间 [first, last) 几何契约、迭代器操作分发与可插入策略设计

第 3 模块：顺序容器物理拓扑与实现 (03_sequence_containers_internals)
----------------------------------------------------------------------

- [x] ``01_vector_three_pointer_model_and_growth.rst`` - std::vector 连续内存动态数组：三指针状态模型、几何级扩容迁移、异常安全强保证与 vector<bool> 特化边界
- [x] ``02_array_fixed_capacity_and_constexpr.rst`` - std::array 固定大小连续内存：聚合初始化、零运行时开销、constexpr 编译期支持与原生数组退化边界
- [x] ``03_deque_chunked_map_buffer_architecture.rst`` - std::deque 分段连续双端队列：中控 map 指针数组、固定块缓冲 (block)、复合迭代器寻址与两端常数扩容
- [x] ``04_list_and_forward_list_node_topologies.rst`` - 链表体系物理拓扑：std::list 环形双向带哨兵节点与 splice 零拷贝剪切、std::forward_list 极简单向链表
- [x] ``05_string_sso_and_memory_layouts.rst`` - std::basic_string 字符串体系：小字符串优化 (SSO) 内部联合体布局、动态扩容与 COW 历史包袱

第 4 模块：关联容器、红黑树与哈希表内核 (04_associative_and_hash_containers)
------------------------------------------------------------------------------

- [x] ``01_red_black_tree_invariants_and_balance_repair.rst`` - 红黑树底层平衡机制：五大不变量、黑高约束、左旋右旋拓扑变换与插入/删除重新着色平衡修复
- [x] ``02_map_and_set_ordered_associative_containers.rst`` - std::map 与 std::set 有序容器：严格弱序比较器契约、节点物理拓扑、lower_bound/upper_bound 对数搜索
- [x] ``03_multimap_and_multiset_equivalent_keys.rst`` - std::multimap 与 std::multiset 多重容器：等价键连续区间存储、equal_range 二分定位与插入策略
- [x] ``04_hash_table_chaining_and_rehash_dynamics.rst`` - 哈希表微架构与冲突处理：拉链法 (Chaining) 节点拓扑、负载因子 (Load Factor) 与二次幂/质数桶设计
- [x] ``05_unordered_containers_and_iterator_invalidation.rst`` - std::unordered_map 与 std::unordered_set：哈希函数、等价谓词、rehash 动态重构与迭代器局部失效

第 5 模块：泛型算法、双指针与内省排序 (05_generic_algorithms_and_performance)
-------------------------------------------------------------------------------

- [x] ``01_half_open_range_contract_and_iterator_dispatch.rst`` - STL 算法设计准则：半开区间几何不变量、只读/变易分类与迭代器能力编译期 tag dispatch
- [x] ``02_linear_and_subsequence_search_algorithms.rst`` - 线性与子序列查找算法：find/find_if 短路、search KMP 思想与 mismatch 范围比对
- [x] ``03_modifying_reordering_and_partition_algorithms.rst`` - 变易与重排算法：copy 内存重叠安全性、remove-erase 惯用法与 rotate 循环位移
- [x] ``04_introsort_quicksort_heapsort_and_stablesort.rst`` - 排序算法全景：std::sort 内省排序 (Introsort)、快速排序/堆排序/插入排序三层降级与 stable_sort 归并
- [x] ``05_binary_search_heap_and_numeric_reductions.rst`` - 二分收敛、堆操作与数值算法：lower_bound/upper_bound 步进、make_heap 线性建堆与 std::accumulate/reduce 并行归约

第 6 模块：可调用对象、类型擦除与模板元编程 (06_callables_and_template_metaprogramming)
----------------------------------------------------------------------------------------

- [x] ``01_function_objects_and_lambda_closures.rst`` - 仿函数与 Lambda 闭包机制：operator() 重载、编译器生成闭包类、捕获列表内存布局与泛型 lambda
- [x] ``02_std_function_type_erasure_and_small_object_optimization.rst`` - std::function 类型擦除实现：虚表/函数指针双态分发、小对象优化 (SOO) 内存缓冲与间接调用开销
- [x] ``03_invoke_mem_fn_and_uniform_callable_model.rst`` - 统一调用模型：std::invoke 10 种调用分支规则、std::mem_fn 成员指针包装与 std::bind 占位符机制
- [x] ``04_type_traits_sfinae_and_compile_time_branching.rst`` - Traits 萃取与 SFINAE 机制：type_traits 编译期属性查询、enable_if_t 与 void_t 成员探测
- [x] ``05_cpp20_concepts_constraints_and_requires_clauses.rst`` - C++20 Concepts 概念约束：requires 子句与表达式、约束归一化、编译器可读诊断与重载决议

第 7 模块：现代 STL 体系演进与 Ranges 管道 (07_modern_stl_and_ranges_architecture)
------------------------------------------------------------------------------------

- [x] ``01_ranges_concepts_and_iterator_sentinel_split.rst`` - C++20 Ranges 体系：Range Concept、Iterator-Sentinel 分离拓扑与统一操作管道
- [x] ``02_views_lazy_evaluation_and_pipeline_composition.rst`` - std::views 惰性求值视图：filter/transform/take 组合管线、零拷贝变换与悬垂视图防范
- [x] ``03_span_and_string_view_non_owning_views.rst`` - 非拥有连续视图：std::span 静态/动态 extent、std::string_view 指针长度二元组与临时对象生命周期陷阱
- [x] ``04_constexpr_containers_and_compile_time_algorithms.rst`` - 编译期 STL 运行机制：constexpr 容器与算法、编译期内存分配与瞬态销毁规则
- [x] ``05_coroutine_generators_and_modern_concurrency_stl.rst`` - 现代并发与协程支持：std::generator 惰性流、std::jthread 自动加入、stop_token 协作取消与 std::atomic

第 8 模块：工业级 Mini-STL 实战与性能工程 (08_mini_stl_and_performance_engineering)
-------------------------------------------------------------------------------------

- [x] ``01_mini_allocator_and_uninitialized_memory.rst`` - 极简 Allocator 实战：allocate / deallocate 原始内存管理、construct / destroy 生命周期分离
- [x] ``02_mini_vector_and_mini_deque.rst`` - 工业级 Mini-Vector 与 Mini-Deque 实战：三指针模型、几何扩容、move_if_noexcept 迁移与中控 map 缓冲区
- [x] ``03_mini_red_black_tree_and_mini_hash_table.rst`` - 工业级 Mini-RBTree 与 Mini-HashTable 实战：旋转平衡修复、拉链法桶数组与动态 rehash 迁移
- [x] ``04_mini_algorithm_and_tag_dispatch.rst`` - 极简泛型算法实战：find / copy / lower_bound / introsort 与 tag dispatch 优化
- [x] ``05_stl_hardware_performance_model_and_source_reading.rst`` - STL 硬件级性能模型与源码读解法：Cache 局部性、分支预测、内存碎片、选型决策树与工业级源码分析方法论
