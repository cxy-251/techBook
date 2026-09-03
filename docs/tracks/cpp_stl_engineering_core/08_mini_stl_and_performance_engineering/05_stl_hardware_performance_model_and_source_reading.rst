========================================================================================================================
STL 硬件级性能模型与源码读解法：Cache 局部性、分支预测、内存碎片、选型决策树与工业级源码分析方法论
========================================================================================================================

.. note:: 前置背景与全书知识体系收束
   在上一节（``04_mini_algorithm_and_tag_dispatch.rst``）中，我们完成了泛型算法库的核心实现，系统推导了线性查找、内存加速拷贝、对数二分以及内省排序的运行机制。作为《现代C++对象模型与STL工程内核全景深度剖析》全书的收官篇章，本节将全书八个模块所沉淀的对象模型、移动语义、内存分配、容器物理拓扑以及泛型算法进行综合收束与工程升华。脱离现代计算机微架构谈论 STL 复杂度分析常常导致片面的工程判断；本节自底向上构建基于 CPU 缓存层级（Cache Hierarchy）、分支预测流水线、虚拟内存页与 TLB 命中率的硬件级性能模型，确立工业级容器正交选型决策树，并交付一套穿透模板噪声、精准逆向主流标准库（GCC libstdc++、LLVM libc++、MSVC STL）内核实现的高效源码分析方法论。

微架构物理模型：CPU 缓存拓扑与数据局部性
-----------------------------------------

传统算法复杂度理论（大 $\mathcal{O}$ 记号）基于抽象图灵机模型，假设计算机访问任意内存地址的时间均等且为常数。现代超标量微架构采用分层存储器结构（Registers $	o$ L1 Data Cache $	o$ L2 Cache $	o$ L3 Shared Cache $	o$ DRAM 主存）。物理内存访问延迟呈现出量级跳跃：

.. list-table:: 现代 x86-64 / ARM64 微架构存储层级访问延迟与容量基准
   :widths: 20 22 28 30
   :header-rows: 1
   :class: tight-table

   * - 存储层次
     - 典型物理容量
     - 访问延迟周期 (Cycles)
     - 相对 DRAM 访问加速比
   * - CPU 寄存器组
     - ~1 KB - 2 KB
     - 0 - 1 周期
     - $\approx 200 	imes$
   * - L1 数据缓存 (L1D)
     - 32 KB - 64 KB
     - 4 - 5 周期
     - $\approx 40 	imes - 50 	imes$
   * - L2 本地缓存
     - 512 KB - 1 MB
     - 12 - 14 周期
     - $\approx 15 	imes - 20 	imes$
   * - L3 共享末级缓存 (LLC)
     - 16 MB - 64 MB
     - 35 - 50 周期
     - $\approx 4 	imes - 6 	imes$
   * - DRAM 主存
     - 16 GB - 256 GB
     - 150 - 250 周期
     - $1 	imes$ (基准线)

Cache Line 空间局部性与硬件预取器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 CPU 缓存与主存间的数据搬移以缓存行（Cache Line，主流架构统一为 64 字节）为最小物理原子单元。

1. **空间局部性（Spatial Locality）**：当程序读取地址 $A$ 时，包含 $[A \& \sim 63, (A \& \sim 63) + 63]$ 的整条 64 字节数据块被原子装载入 L1D 缓存。若后续指令持续访问紧邻的 $[A+1, A+63]$，后续全部访问直接命中 L1D，耗时仅 4 周期。
2. **硬件流式预取器（Stream / Stride Prefetcher）**：CPU 内建专用硬件单元监控内存加载指令地址流。当检测到连续或等步长（Stride）的递增/递减访问模式时，预取器在当前指令执行的同时，自动通过系统总线向更深层次缓存提前发出后续缓存行加载请求，实现访问延迟的完全隐藏。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  CPU 缓存行 (Cache Line, 64B) 命中与指针追踪失配对比        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   | [连续存储: std::vector<uint32_t>]                                           |
   |                                                                             |
   |   0x1000        0x1004        0x1008               0x103C                   |
   |   +-------------+-------------+-------------+-- ... --+-------------+       |
   |   | Element 0   | Element 1   | Element 2   |         | Element 15  |       |
   |   +-------------+-------------+-------------+-- ... --+-------------+       |
   |   |<------------------- 1 条 Cache Line (64 字节) ------------------->|      |
   |   * 首次访问 Element 0 产生 L1 Miss; 随后的 1~15 号元素均以 4 周期极速命中! |
   |                                                                             |
   | --------------------------------------------------------------------------- |
   |                                                                             |
   | [分散节点存储: std::list / std::map]                                        |
   |                                                                             |
   |   堆地址 0x3A00 (Node A)      堆地址 0x8F40 (Node B)      堆地址 0x1B80     |
   |   +-----------+------+        +-----------+------+        +-----------+---+ |
   |   | Data A    | Next |------->| Data B    | Next |------->| Data C    |...| |
   |   +-----------+------+        +-----------+------+        +-----------+---+ |
   |         |                           |                           |           |
   |         v                           v                           v           |
   |    Cache Line X                Cache Line Y                Cache Line Z     |
   |   * 每次沿指针步进 (++it) 均跨越至随机堆地址，硬件预取器失效，每次均承受   |
   |     L2/L3/DRAM 高达 40~200 周期的长延迟惩罚 (Pointer Chasing Penalty)。    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

热冷字段分离与结构体紧凑布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当元素对象体积较大且只读扫描仅关注局部属性时，扁平结构体内的冷字段会迅速稀释缓存行有效数据密度。设结构体包含 64 字节，每次仅访问 4 字节状态标志：一条缓存行仅容纳 1 个有效状态。通过将热字段提取为独立紧凑数组（Data-Oriented Design，面向数据设计），单条缓存行可容纳 16 个有效元素，使缓存利用率直接跃升 $1600\%$。

分支预测流水线与算法执行成本
----------------------------

现代超标量处理器具备深度流水线（Pipeline Depth 通常达 14 - 19 级）。为了维持指令吞吐，CPU 在分支条件计算完成前，依托分支目标缓冲器（BTB）与方向预测器执行投机执行（Speculative Execution）。

分支预测失败惩罚与数据依赖
~~~~~~~~~~~~~~~~~~~~~~~~~~

当投机执行方向预测错误时，流水线必须执行冲刷（Pipeline Flush）：已处于译码、重命名与调度阶段的数十条投机微指令全部作废并重新抓取正确分支指令。单次预测错误产生 15 - 20 个周期的空转停顿。

.. list-table:: 典型 STL 访问模式在分支预测器上的物理表现
   :widths: 22 25 25 28
   :header-rows: 1
   :class: tight-table

   * - 算法 / 操作场景
     - 控制流特征
     - 分支预测器状态
     - 微架构性能表现
   * - ``std::find`` 等值扫描
     - 循环继续条件（不等）高度偏置
     - 预测命中率接近 $100\%$
     - 维持每周期多指令发射吞吐
   * - ``std::partition`` 乱序数据
     - 谓词真假呈 $50\%$ 随机分布
     - 预测器处于最大熵震荡
     - 频繁触发流水线冲刷停顿
   * - ``std::partition`` 已排序数据
     - 前半段全真，后半段全假
     - 仅在切换边界产生 1 次错误
     - 极低流水线停顿，运行速度提升数倍
   * - 无分支条件传送（CMOV）
     - 消除条件跳转指令，纯数据依赖
     - 消除分支预测硬件消耗
     - 恒定周期吞吐，性能表现完全确定

虚拟内存分页、TLB 惩罚与内存碎片
--------------------------------

容器的性能边界不仅受 CPU 缓存限制，更深度耦合于操作系统的虚拟内存管理系统。

快表（TLB）命中率与地址转换
~~~~~~~~~~~~~~~~~~~~~~~~~~~

虚拟地址到物理地址的映射依赖多级页表。CPU 芯片内部设有转译后备缓冲器（TLB, Translation Lookaside Buffer）用于加速页表项查询。标准页大小通常为 4 KB。

1. **连续数组的页局部性**：``std::vector`` 占用连续虚拟内存页。访问 100 万个 4 字节整数（4 MB 数据）仅占用 1024 个连续虚拟页。TLB 预取器能够维持极高命中率。
2. **节点容器的页颠簸**：``std::list`` 或 ``std::map`` 的 100 万个节点通过系统的通用分配器分配于堆的各个角落。若节点跨越数万个互不连续的内存页，CPU 遍历链表时不仅承受 L1/L2 Cache Miss，更频繁诱发 DTLB Miss，迫使内存管理单元（MMU）发起代价极其昂贵的多级页表漫游（Page Table Walk）。

堆内存碎片分类与生命周期开销
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

节点容器的高频单节点分配释放会产生两类严重碎片：

- **内部碎片（Internal Fragmentation）**：操作系统底层分配器（如 ptmalloc）按特定大小的 bin（块大小阶梯）提供内存，并为每个已分配 chunk 附加元数据头（Header，8-16 字节）。分配一个 4 字节的节点，实际消耗可能达 24-32 字节，物理内存有效载荷利用率仅 $12.5\%$ - $16.7\%$。
- **外部碎片（External Fragmentation）**：长期运行的服务中，节点以随机时序被释放，使得虚拟内存空间中散落大量微小空闲区间，无法满足连续大块内存分配请求，迫使操作系统提前发起 `brk`/`mmap` 系统调用申请新物理页。

工业级容器正交选型决策树
------------------------

基于微架构物理事实，容器选型不再停留在表面大 $\mathcal{O}$ 复杂度的静态对比，而是基于访问模式、对象移动成本、内存地址稳定性以及查找需求的正交决策推导：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       工业级 STL 容器正交选型判定全景图                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                           [ 明确业务核心主路径 ]                            |
   |                                     |                                       |
   |                 +-------------------+-------------------+                   |
   |                 |                                       |                   |
   |                 v                                       v                   |
   |          [ 序列流动与存储 ]                      [ 键值检索与关联 ]         |
   |                 |                                       |                   |
   |         +-------+-------+                       +-------+-------+           |
   |         |               |                       |               |           |
   |         v               v                       v               v           |
   |   [ 单端连续流动 ]  [ 双端连续流动 ]      [ 精确单键定位 ]  [ 范围/有序检索 ]   |
   |         |               |                       |               |           |
   |         v               v                       v               v           |
   |   std::vector      std::deque           std::unordered_map   std::map       |
   |   (默认首选)       (前后两端高频增删)   (哈希分布均匀时首选) (红黑树/对数边界)  |
   |         |                                       |               |           |
   |         | 是否要求极致轻量与原地编译期存储?      |               |           |
   |         +---> 是: std::array<T, N>              |               |           |
   |         |                                       |               |           |
   |         | 是否存在外部长期持有节点指针且高频    | 是否允许等价键同时存在?   |
   |         | 任意已知位置拼接剪切 (splice)?        +---> 是:       +---> 是:   |
   |         +---> 是: std::list                     multimap        multimap    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: 工业级 STL 核心容器全景物理特征与权衡矩阵
   :widths: 14 18 18 18 16 16
   :header-rows: 1
   :class: tight-table

   * - 容器类别
     - 物理底层布局
     - 遍历缓存局部性
     - 元素扩容迁移成本
     - 指针/引用失效边界
     - 典型适配业务
   * - ``std::vector``
     - 连续单调堆缓冲
     - 极高（硬件预取）
     - 几何倍率重分配迁移
     - 扩容全失效，尾后失效
     - 默认通用序列、批量计算
   * - ``std::deque``
     - 中控 Map + 分段块
     - 较高（块内连续）
     - 仅扩容 Map 指针数组
     - 端点增删仅迭代器失效
     - 双端滑动窗口、消息队列
   * - ``std::list``
     - 独立双向环形节点
     - 极低（指针追踪）
     - 零迁移（指针重织）
     - 仅被删除节点失效
     - 频繁已知节点拼接剪切
   * - ``std::map``
     - 独立红黑树节点
     - 极低（树形跳跃）
     - 零迁移（左旋右旋）
     - 仅被删除节点失效
     - 范围扫描、按序前趋后继
   * - ``std::unordered_map``
     - 桶数组 + 单向链表
     - 混合（单桶链表低）
     - Rehash 仅重织链表
     - Rehash 仅迭代器失效
     - 高吞吐精准单键点查

工业级标准库源码读解方法论
--------------------------

直接阅读主流标准库（GCC libstdc++、LLVM libc++、MSVC STL）源码的开发者常受困于庞大的模板修饰符、平台宏与异常安全样板代码。建立结构化的降噪与逆向方法论是穿透复杂实现的核心武器。

穿透模板噪声的三层过滤技术
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **第一层：具体化代换（Concretization）**：将泛型模板形参（如 ``_Tp``、``_Alloc``、``_Compare``）在思维或调试脚本中直接替换为实际工程类型（如 ``int``、``std::allocator<int>``、``std::less<int>``）。消除概念层抽象带来的认知负荷。
2. **第二层：宏工程分类剥离（Macro Categorization）**：
   - *语言标准版本宏*：如 ``_GLIBCXX20_CONSTEXPR``、``_LIBCPP_CONSTEXPR_SINCE_CXX20``，仅表征语言版本演进，直接视为普通关键字展开。
   - *编译器属性与可见性宏*：如 ``__attribute__((__always_inline__))``、``_NODISCARD``，直接过滤。
   - *诊断与调试代理宏*：如 ASan 毒化标记、调试迭代器检查宏，优先折叠。
3. **第三层：功能分层隔离（Traits Isolation）**：
   - 区分“类型事实查询萃取”（如 ``iterator_traits::value_type``）与“物理执行逻辑”。
   - 将 ``allocator_traits<A>::construct`` 还原为底层的 placement new 表达式；将 ``allocator_traits<A>::allocate`` 还原为底层内存申请原语。

源码逆向四步协议（The Four-Step Protocol）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当切入任意标准库组件实现时，严格按以下步骤展开追踪：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     STL 源码逆向与物理状态追踪四步协议                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 第 1 步: 锁定物理数据拓扑 (Locate Physical Layout) ]                    |
   |   - 寻找类的成员变量声明 (通常位于最底层基类, 如 _Vector_impl_data)         |
   |   - 记录其核心指针与标量尺寸 (如三指针、Map控制数组、节点结构)              |
   |                                 |                                           |
   |                                 v                                           |
   |   [ 第 2 步: 追踪状态变易主干 (Trace Mutation Backbone) ]                   |
   |   - 顺沿公开 API 进入内部核心实现 (如 push_back -> _M_realloc_insert)       |
   |   - 剥离前置容量检查, 提取最深层的内存分配与对象构造核心语句                |
   |                                 |                                           |
   |                                 v                                           |
   |   [ 第 3 步: 审视异常安全回滚边界 (Inspect Exception Rollback) ]            |
   |   - 检索 try-catch 块或基于 RAII 的 Scope Guard 结构                        |
   |   - 明确当构造中间元素发生抛出时, 临时新缓冲区如何释放、旧状态如何恢复      |
   |                                 |                                           |
   |                                 v                                           |
   |   [ 第 4 步: 逆推指针与迭代器失效事实 (Derive Invalidation Invariants) ]    |
   |   - 从物理缓冲区的生命周期变迁 (释放/移动/保留) 直接推导失效契约            |
   |   - 彻底摆脱对文档叙述的死记硬背, 建立微架构直觉                            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级自包含 C++ 性能对比与决策验证实战
---------------------------------------

以下提供一套完全自包含、无外部依赖的生产级性能验证框架与微架构实测代码。程序严格构建了连续存储（Contiguous Buffer）与节点链表（Node Chaining）在单条缓存行穿越与顺序预取上的时钟周期度量器，并交付一套基于访问模式标签编译期推导最优容器选型的决策验证原型：

.. code-block:: cpp

   #include <iostream>
   #include <cstddef>
   #include <cstdint>
   #include <chrono>
   #include <vector>
   #include <numeric>
   #include <random>
   #include <algorithm>
   #include <cassert>
   #include <type_traits>

   namespace hardware_model {

   // ===========================================================================
   // 1. 微架构时钟周期与高精度时间探针
   // ===========================================================================

   class PrecisionTimer {
       using clock_t = std::chrono::high_resolution_clock;
       clock_t::time_point start_point_;

   public:
       PrecisionTimer() noexcept : start_point_(clock_t::now()) {}

       void reset() noexcept {
           start_point_ = clock_t::now();
       }

       [[nodiscard]] double elapsed_microseconds() const noexcept {
           const auto end_point = clock_t::now();
           return std::chrono::duration<double, std::micro>(end_point - start_point_).count();
       }
   };

   // 消除编译器优化对纯读取循环的死代码剥离
   template <typename T>
   inline void do_not_optimize(T const& value) {
       asm volatile("" : : "r,m"(value) : "memory");
   }

   // ===========================================================================
   // 2. 连续存储 vs 节点追踪物理拓扑探针
   // ===========================================================================

   struct alignas(64) CacheAlignedPayload {
       uint32_t active_field{0};
       uint8_t padding[60]{}; // 严密填充占满单条 64 字节缓存行
   };

   struct SimpleNode {
       uint32_t data{0};
       SimpleNode* next{nullptr};
   };

   // 连续内存线性累加器
   uint64_t benchmark_vector_locality(const std::vector<uint32_t>& data) {
       uint64_t sum = 0;
       for (size_t i = 0; i < data.size(); ++i) {
           sum += data[i];
       }
       return sum;
   }

   // 链表指针追踪累加器 (模拟非局部性遍历)
   uint64_t benchmark_list_locality(const SimpleNode* head) {
       uint64_t sum = 0;
       const SimpleNode* curr = head;
       while (curr != nullptr) {
           sum += curr->data;
           curr = curr->next;
       }
       return sum;
   }

   // ===========================================================================
   // 3. 分支预测稳定性度量模型
   // ===========================================================================

   uint64_t benchmark_branch_prediction(const std::vector<uint32_t>& data, uint32_t threshold) {
       uint64_t count = 0;
       for (size_t i = 0; i < data.size(); ++i) {
           // 数据满足特定分布时产生高频分支预测失误
           if (data[i] > threshold) {
               count += data[i];
           }
       }
       return count;
   }

   // ===========================================================================
   // 4. 工业级容器选型推导引擎 (Compile-time Container Selector)
   // ===========================================================================

   enum class AccessPattern {
       SequentialScan,
       DoubleEndedFlow,
       StableNodeSplice,
       DirectKeyLookup,
       OrderedRangeScan
   };

   enum class AddressStabilityRequirement {
       AllowRelocation,
       RequireStableAddresses
   };

   // 编译期选型标签分发系统
   template <AccessPattern Pattern, AddressStabilityRequirement Stability>
   struct ContainerSelectionTraits;

   // 特化：顺序扫描 + 允许重定位 -> std::vector
   template <>
   struct ContainerSelectionTraits<AccessPattern::SequentialScan, AddressStabilityRequirement::AllowRelocation> {
       static constexpr const char* recommendation = "std::vector (连续内存存储, 空间局部性与预取最优)";
   };

   // 特化：双端流动 + 允许重定位 -> std::deque
   template <>
   struct ContainerSelectionTraits<AccessPattern::DoubleEndedFlow, AddressStabilityRequirement::AllowRelocation> {
       static constexpr const char* recommendation = "std::deque (中控分段缓冲, 兼顾双端平摊常数与块内连续)";
   };

   // 特化：稳定节点拼接 -> std::list
   template <AddressStabilityRequirement S>
   struct ContainerSelectionTraits<AccessPattern::StableNodeSplice, S> {
       static constexpr const char* recommendation = "std::list (双向环形节点, 保证 splice 零拷贝与迭代器绝对稳定)";
   };

   // 特化：精确键查 -> std::unordered_map
   template <AddressStabilityRequirement S>
   struct ContainerSelectionTraits<AccessPattern::DirectKeyLookup, S> {
       static constexpr const char* recommendation = "std::unordered_map (拉链法哈希桶, 交付平均常数级寻址)";
   };

   // 特化：有序范围扫描 -> std::map
   template <AddressStabilityRequirement S>
   struct ContainerSelectionTraits<AccessPattern::OrderedRangeScan, S> {
       static constexpr const char* recommendation = "std::map (严格平衡红黑树, 交付有序遍历与对数边界)";
   };

   } // namespace hardware_model

   // ===========================================================================
   // 5. 验证套件主程序
   // ===========================================================================

   int main() {
       std::cout << "=== 启动 STL 硬件级性能模型与微架构分析验证 ===" << std::endl;

       constexpr size_t TEST_ELEMENTS = 500000;

       // -----------------------------------------------------------------------
       // 验证 1: 连续内存预取吞吐 vs 链表指针跳跃延迟
       // -----------------------------------------------------------------------
       std::vector<uint32_t> contig_data(TEST_ELEMENTS);
       for (size_t i = 0; i < TEST_ELEMENTS; ++i) {
           contig_data[i] = static_cast<uint32_t>(i & 0xFF);
       }

       // 构建链表节点 (故意以离散时序分配模拟内存碎片)
       std::vector<hardware_model::SimpleNode> node_pool(TEST_ELEMENTS);
       for (size_t i = 0; i < TEST_ELEMENTS; ++i) {
           node_pool[i].data = static_cast<uint32_t>(i & 0xFF);
           node_pool[i].next = (i + 1 < TEST_ELEMENTS) ? &node_pool[i + 1] : nullptr;
       }

       // 预热缓存
       uint64_t dummy_v = hardware_model::benchmark_vector_locality(contig_data);
       hardware_model::do_not_optimize(dummy_v);

       hardware_model::PrecisionTimer timer;
       uint64_t sum_v = hardware_model::benchmark_vector_locality(contig_data);
       hardware_model::do_not_optimize(sum_v);
       const double time_v = timer.elapsed_microseconds();

       timer.reset();
       uint64_t sum_l = hardware_model::benchmark_list_locality(&node_pool[0]);
       hardware_model::do_not_optimize(sum_l);
       const double time_l = timer.elapsed_microseconds();

       assert(sum_v == sum_l);
       std::cout << "[局部性实测] 连续数组遍历耗时: " << time_v << " us" << std::endl;
       std::cout << "[局部性实测] 链表节点遍历耗时: " << time_l << " us" << std::endl;
       std::cout << "[局部性加速比] 连续预取相对指针遍历加速倍率: " << (time_l / time_v) << "x" << std::endl;

       // -----------------------------------------------------------------------
       // 验证 2: 分支预测器对已排序 vs 随机数据的吞吐冲击
       // -----------------------------------------------------------------------
       std::vector<uint32_t> random_data(TEST_ELEMENTS);
       std::mt19937 rng(1337);
       for (size_t i = 0; i < TEST_ELEMENTS; ++i) {
           random_data[i] = static_cast<uint32_t>(rng() % 1000);
       }

       std::vector<uint32_t> sorted_data = random_data;
       std::sort(sorted_data.begin(), sorted_data.end());

       constexpr uint32_t THRESHOLD = 500;

       timer.reset();
       uint64_t sum_random = hardware_model::benchmark_branch_prediction(random_data, THRESHOLD);
       hardware_model::do_not_optimize(sum_random);
       const double time_random = timer.elapsed_microseconds();

       timer.reset();
       uint64_t sum_sorted = hardware_model::benchmark_branch_prediction(sorted_data, THRESHOLD);
       hardware_model::do_not_optimize(sum_sorted);
       const double time_sorted = timer.elapsed_microseconds();

       assert(sum_random == sum_sorted);
       std::cout << "[分支预测实测] 随机无序数据条件求和耗时: " << time_random << " us" << std::endl;
       std::cout << "[分支预测实测] 预排序数据分支单调求和耗时: " << time_sorted << " us" << std::endl;
       std::cout << "[流水线优化比] 分支预测命中带来的加速倍率: " << (time_random / time_sorted) << "x" << std::endl;

       // -----------------------------------------------------------------------
       // 验证 3: 选型推导引擎静态分发检查
       // -----------------------------------------------------------------------
       using SelectionA = hardware_model::ContainerSelectionTraits<
           hardware_model::AccessPattern::SequentialScan,
           hardware_model::AddressStabilityRequirement::AllowRelocation>;

       using SelectionB = hardware_model::ContainerSelectionTraits<
           hardware_model::AccessPattern::StableNodeSplice,
           hardware_model::AddressStabilityRequirement::RequireStableAddresses>;

       using SelectionC = hardware_model::ContainerSelectionTraits<
           hardware_model::AccessPattern::OrderedRangeScan,
           hardware_model::AddressStabilityRequirement::RequireStableAddresses>;

       std::cout << "[选型决策输出] 场景 A (扫描主路径): " << SelectionA::recommendation << std::endl;
       std::cout << "[选型决策输出] 场景 B (已知节点剪切): " << SelectionB::recommendation << std::endl;
       std::cout << "[选型决策输出] 场景 C (时间范围检索): " << SelectionC::recommendation << std::endl;

       std::cout << "所有硬件性能模型测试与选型断言全部顺利通过!" << std::endl;
       return 0;
   }
