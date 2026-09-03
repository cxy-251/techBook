====================================================================
现代C++对象模型与STL工程内核全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书 8 大核心系统模块体系目录:
   :numbered:

   ROADMAP
   01_cpp_low_level_foundations/index
   02_stl_core_mechanisms_and_allocators/index
   03_sequence_containers_internals/index
   04_associative_and_hash_containers/index
   05_generic_algorithms_and_performance/index
   06_callables_and_template_metaprogramming/index
   07_modern_stl_and_ranges_architecture/index
   08_mini_stl_and_performance_engineering/index

专著简介与架构全景
==================

本专著是一部立足于现代 C++ 对象模型、内存拓扑、模板元编程与工业级 STL 源码实现（libstdc++ / libc++ / MSVC STL）的全景深度技术著作。

全书坚持“微架构物理事实与源码真实实现优先”原则，从 CPU 寄存器、栈帧布局、缓存行局部性与堆内存分配出发，系统化解构从对象生命周期、移动语义、allocator 策略与迭代器抽象，到顺序/关联容器物理拓扑、泛型算法特化、Ranges 管线与工业级 Mini-STL 独立实现的全部底层机制。

核心知识模块拓扑
----------------

.. list-table:: C++ 对象模型与 STL 架构核心知识体系映射
   :widths: 10 25 35 30
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 微架构关键机制与核心路径
     - 解决的核心工程问题
   * - 01
     - C++ 底层基石与对象模型
     - 内存对齐、Padding、vptr 虚表拓扑、移动语义、RAII 与模板二阶段查找
     - 建立硬件级内存布局心智，消除未定义行为与隐式拷贝开销
   * - 02
     - STL 核心机制与内存子系统
     - 迭代器能力分层、allocator 接口契约、std::pmr 多态内存池与异常安全保证
     - 掌握 STL 核心解耦哲学，杜绝内存泄漏与异常状态污染
   * - 03
     - 顺序容器物理拓扑与实现
     - vector 连续内存三指针模型、deque 分段缓冲区与 map 控制表、list 双向链接与 SSO 优化
     - 消除迭代器失效陷阱，精准匹配访问模式与缓存局部性
   * - 04
     - 关联容器、红黑树与哈希表内核
     - 严格弱序比较契约、红黑树平衡修复、拉链法哈希桶数组与 rehash 动态迁移
     - 保证对数与常数时间确定性复杂度，防范哈希碰撞退化
   * - 05
     - 泛型算法、双指针与内省排序
     - 半开区间几何契约、双指针扫描、二分收敛、内省排序 (Introsort) 与 SIMD 并行归约
     - 避免重复造轮子，利用编译期 tag dispatch 自动走最优汇编路径
   * - 06
     - 可调用对象、类型擦除与模板元编程
     - Lambda 闭包内存布局、std::function 类型擦除、std::invoke、SFINAE 与 C++20 Concepts
     - 消除间接调用开销与悬垂引用，将运行时错误前移至编译期
   * - 07
     - 现代 STL 体系演进与 Ranges 管道
     - Ranges / Views 惰性计算管线、std::span 非拥有连续视图、constexpr STL 与协程生成器
     - 消除中间容器内存物化，实现极速零拷贝数据流处理
   * - 08
     - 工业级 Mini-STL 实战与性能工程
     - 手工实现 Allocator/Vector/Deque/RBTree/HashTable/Algorithms、Cache 局部性与源码阅读法
     - 建立严谨工业级性能决策框架，具备独立设计工业级基础库能力

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
