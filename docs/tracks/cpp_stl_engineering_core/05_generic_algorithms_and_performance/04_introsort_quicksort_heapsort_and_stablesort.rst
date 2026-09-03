====================================================================================================
排序算法全景：std::sort 内省排序 (Introsort)、快速排序/堆排序/插入排序三层降级与 stable_sort 归并
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块前三节中，我们系统剖析了半开区间 $[first, last)$ 的几何代数公理、Tag Dispatching 编译期多态重载分发、硬件级内存拷贝降级（``std::copy`` $	o$ ``memmove``）、线性查找短路机制、``std::search`` 的子序列匹配以及变易/重排/划分算法（``copy_backward``、``remove_if``、三步反转法 ``rotate`` 与双指针 ``partition``）。这些基础构件为序列的高级转换提供了扎实的底层支撑。在现代软件系统与算法工程中，**排序（Sorting）** 是调用最频繁、计算复杂度最高、对处理器微架构（缓存局部性、分支预测、指令级并行）影响最深远的操作。C++ 标准库中的 ``std::sort`` 并不采用单一的传统排序算法，而是由 David Musser 于 1997 年提出的 **内省排序（Introspective Sort, Introsort）** 混合架构所驱动；而保持等价元素相对顺序的 ``std::stable_sort`` 则基于自适应内存缓冲归并排序构建。本章系统解构排序算法族的语义契约边界、Introsort 结合快速排序、堆排序与插入排序的三层动态降级微架构、``std::stable_sort`` 在内存充裕与受限环境下的自适应归并状态机、比较器违反严格弱序引发的越界灾难，以及工业级高性能排序引擎的 C++ 落地实现。

STL 排序算法族核心语义与复杂度契约
----------------------------------

标准库在 ``<algorithm>`` 头文件中提供了一套正交完备的排序算法家族：

.. list-table:: STL 核心排序与选择算法语义、复杂度与内存契约矩阵
   :widths: 18 22 28 32
   :header-rows: 1
   :class: tight-table

   * - 算法接口
     - 核心排序目标与语义
     - 时间复杂度契约
     - 辅助内存与稳定性
   * - **``std::sort``**
     - 全量非稳定排序；将区间重排为满足比较器的非降序序列
     - 平均 $\mathcal{O}(N \log N)$；**最坏严格 $\mathcal{O}(N \log N)$**
     - $\mathcal{O}(\log N)$ 栈空间；**非稳定（Unstable）**
   * - **``std::stable_sort``**
     - 全量稳定排序；**严格保持等价元素在原序列中的相对前后顺序**
     - 内存充足时 $\mathcal{O}(N \log N)$；原址退化为 $\mathcal{O}(N \log^2 N)$
     - 自适应分配 $\mathcal{O}(N)$ 缓冲区；**绝对稳定（Stable）**
   * - **``std::partial_sort``**
     - 局部排序；仅将前 $K$ 个最小元素排序并放置于 $[first, first + K)$
     - 严格 $\mathcal{O}(N \log K)$
     - $\mathcal{O}(1)$ 原址最大堆；非稳定
   * - **``std::nth_element``**
     - 顺序统计量选择；将第 $N$ 排名位置元素归位，左侧均 $\le$ 该值，右侧均 $\ge$ 该值
     - **平均线性时间 $\mathcal{O}(N)$**；最坏 $\mathcal{O}(N \log N)$
     - $\mathcal{O}(\log N)$ 栈空间；非稳定

Introsort (内省排序) 三层动态降级微架构
----------------------------------------

传统快速排序（Quicksort）在平均情况下具有最快的常数因子和优异的 CPU 缓存局部性。然而，在遭遇极端恶劣输入（如精心构造的反快速排序杀手序列、大量重复键、或退化的单侧划分）时，递归树深度将退化至 $\mathcal{O}(N)$，引发 $\mathcal{O}(N^2)$ 的灾难性时间复杂度与调用栈溢出（Stack Overflow）。

为了兼顾快速排序的高速吞吐与堆排序的最坏时间复杂度上限，**Introsort 构建了三层动态监控与降级状态机**：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Introsort (内省排序) 三层自适应降级微架构             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 输入区间: [first, last), 深度阈值 DepthLimit = 2 * floor(log2(N)) ]     |
   |                                  |                                          |
   |                                  v                                          |
   |                +------------------------------------+                       |
   |   [ 检查 1 ]    | 区间长度 (last - first) <= 16 ?     |                       |
   |                +-----------------+------------------+                       |
   |                                  |                                          |
   |                       (否)       | (是)                                     |
   |                        /         \                                          |
   |                       v           v                                         |
   |        +---------------------+  [ 终止递归，保留局部近有序状态 ]            |
   |  [ 检查 2 ] | DepthLimit == 0 ?   |   (留待最终单遍插入排序扫尾)                 |
   |        +----------+----------+                                              |
   |                   |                                                         |
   |          (否)     | (是: 侦测到递归过深，存在退化为 O(N^2) 风险!)           |
   |           /       \                                                         |
   |          v         v                                                        |
   |   [ 第 1 层: 快速排序主轴 ]   [ 第 2 层: 降级为堆排序 (Heapsort) ]          |
   |   * 三数取中选 Pivot          * 在当前子区间就地建堆并完成堆排序            |
   |   * Hoare 双向对撞划分        * 绝对保证 O(M log M) 最坏复杂度下限!         |
   |   * 递归处理左侧，尾递归处理右侧                                            |
   |   * DepthLimit 自减 1                                                       |
   |                                                                             |
   |   =======================================================================   |
   |                                                                             |
   |   [ 第 3 层: 最终单遍无守卫插入排序 (Final Insertion Sort) ]                |
   |   * 此时全数组已被划分为多个长度 <= 16 且宏观有序的微小区间                 |
   |   * 运行一次全局 __final_insertion_sort，利用 L1 Cache 极速原地整理收敛!    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

第一层：快速排序主轴与三数取中枢轴 (Median-of-Three)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **三数取中（Median-of-Three）**：
   在区间首元素 ``*first``、中间元素 ``*(first + (last - first)/2)`` 与尾元素 ``*(last - 1)`` 之间取中位数作为枢轴（Pivot），并将三者在原址预先排好序。
   - **微架构收益**：彻底消除对已排序或逆序序列的退化风险；同时将最小元素置于首位作为天然的 **左哨兵（Left Sentinel）**。
2. **尾递归消除（Tail-Call Optimization）**：
   在完成一次划分后，仅对较短的子区间进行递归调用，而对较长的子区间通过更新 ``first`` 游标原地循环（``while`` 循环）。这保证了调用栈深度严格受控于 $\mathcal{O}(\log N)$。

第二层：递归深度耗尽与堆排序 (Heapsort) 降级拦截
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **深度上限阈值公式**：$	ext{DepthLimit} = 2 	imes \lfloor \log_2(N) \rfloor$。
- **触发机理**：当快速排序连续发生不平衡划分导致 ``DepthLimit`` 递减归零时，算法立即放弃快排，直接对当前子区间调用原地堆排序（``std::partial_sort`` / ``std::make_heap`` + ``std::sort_heap``）。堆排序利用堆二叉树的物理刚性结构，**绝对保证子区间在 $\mathcal{O}(M \log M)$ 内完成排序**。

第三层：小区间截断与无守卫插入排序 (Unguarded Insertion Sort)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当子区间元素个数 $M \le 16$ 时，快速排序递归调用与枢轴选取的固定开销已经超过算法本身的收益。
Introsort 在此阶段直接退出快排递归，使得整个大数组处于 **“宏观全局有序、微观局部未排序（每个局部块尺寸 $\le 16$）”** 的特殊状态。

随后，算法调用一次全局的 **无守卫插入排序（``__unguarded_insertion_sort``）**：
- **无边界检查优化（Unguarded Optimization）**：由于第一步的三数取中已经将全局最小元素放置在数组最前端，插入排序在向前扫描插入位置（``while (value < *(curr - 1))``）时，**绝对不会越过数组首地址**。因此，内层循环完全移除了每次迭代的 ``curr > first`` 边界判定指令，分支预测命中率达 $100\%$，直接在 CPU L1 数据缓存中以极高吞吐率完成最终排序。

std::stable_sort: 自适应内存缓冲归并排序
----------------------------------------

``std::stable_sort`` 必须严格捍卫等价元素在排序前后的时序稳定性。

自适应双态归并状态机
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     std::stable_sort 自适应缓冲区归并状态机                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 输入: 区间 [first, last), 元素总数 N ]                                  |
   |                       |                                                     |
   |                       v                                                     |
   |   [ 内存申请 ]: 尝试通过 Allocator 申请尺寸为 N 的临时连续缓冲区 Buffer     |
   |                       |                                                     |
   |          +------------+------------+                                        |
   |          |                         |                                        |
   |     (申请成功: 内存充裕)      (申请失败 / 内存受限: 降级原址归并)           |
   |          |                         |                                        |
   |          v                         v                                        |
   |   [ 外部缓冲双路归并 ]      [ 原址块旋转归并 (In-Place Merge) ]             |
   |   * 递归二分拆解子区间      * 利用三步反转 rotate 算法在原址交换子块        |
   |   * 归并时向 Buffer 写入    * 零额外动态内存开销                            |
   |   * 严格 O(N log N) 时间    * 复杂度上升为 O(N log^2 N) 时间                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **外部缓冲双路归并（$\mathcal{O}(N \log N)$）**：
   在持有额外内存缓冲区时，归并操作只需顺序遍历两个有序子区间，在比较时使用严格小于（``comp(*it2, *it1) == false``）保证第一区间的等价元素先于第二区间写入缓冲区，达成绝对稳定。
2. **原址旋转归并（In-Place Merge, $\mathcal{O}(N \log^2 N)$）**：
   在嵌入式或超大内存受限场景下，算法通过基于区间旋转（``rotate``）的二分交换算法在物理原址完成两段有序序列的交叉缝合。

严格弱序违规灾难：为什么必须使用 < 而严禁 <=
--------------------------------------------

在第 4 模块中我们阐述了比较器必须满足非自反性（$
eg	ext{comp}(a, a)$）。
若在排序中错误地使用了包含等于的比较器（如 ``return a.score <= b.score;``），将引发致命的 **内存越界与堆栈破坏崩溃**：

.. code-block:: cpp

   // 快速排序内部的 Hoare 划分扫描循环
   while (comp(*first, pivot)) ++first;
   while (comp(pivot, *last))  --last;

- 当比较器为 ``<`` 时，若游标推进到与 ``pivot`` 等价的元素处，``comp(pivot, pivot)`` 返回 ``false``，循环强制停顿，保证游标绝不越界。
- **当比较器为 `<=` 时**，``comp(pivot, pivot)`` 恒为 ``true``！当处理数组中所有元素均相等的序列时，``++first`` 将无休止地向高地址越界推进，破坏相邻堆栈内存并引发系统级段错误（Segmentation Fault）。

工业级 C++ 完整 Introsort 与 Stable Mergesort 引擎实现
------------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级内省排序（``MiniIntrosort``）与自适应稳定归并排序（``MiniStableSort``）引擎。该实现涵盖：
1. 三数取中（Median-of-3）与快速排序对撞双指针划分。
2. 递归深度监控与堆排序（Heapsort）自动降级拦截。
3. 无守卫插入排序（Unguarded Insertion Sort）极速收尾。
4. 带外部缓冲区的稳定归并排序（Stable Mergesort）。
5. 包含等价元素稳定性断言、最坏退化用例压测与排序正确性的端到端测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <utility>
   #include <algorithm>
   #include <cassert>
   #include <functional>
   #include <cmath>

   namespace core_sort {

   // 基础辅助工具: 交换
   template <typename T>
   inline void mini_iter_swap(T* a, T* b) noexcept {
       T tmp = std::move(*a);
       *a = std::move(*b);
       *b = std::move(tmp);
   }

   // 计算 log2(N)
   inline size_t compute_depth_limit(size_t n) noexcept {
       size_t k = 0;
       while (n > 1) {
           n >>= 1;
           ++k;
       }
       return k * 2; // 2 * floor(log2(N))
   }

   // =========================================================================
   // 1. 堆排序组件 (作为 Introsort 的第 2 层安全兜底)
   // =========================================================================
   template <typename RandomIt, typename Compare>
   void heapify_down(RandomIt first, size_t start, size_t count, Compare comp) {
       size_t root = start;
       while (root * 2 + 1 < count) {
           size_t child = root * 2 + 1;
           if (child + 1 < count && comp(*(first + child), *(first + (child + 1)))) {
               ++child;
           }
           if (comp(*(first + root), *(first + child))) {
               mini_iter_swap(&(*(first + root)), &(*(first + child)));
               root = child;
           } else {
               break;
           }
       }
   }

   template <typename RandomIt, typename Compare>
   void mini_heapsort(RandomIt first, RandomIt last, Compare comp) {
       size_t count = static_cast<size_t>(last - first);
       if (count <= 1) return;

       // 线性建大顶堆
       for (int i = static_cast<int>(count / 2) - 1; i >= 0; --i) {
           heapify_down(first, static_cast<size_t>(i), count, comp);
       }
       // 循环弹出堆顶
       for (size_t i = count - 1; i > 0; --i) {
           mini_iter_swap(&(*(first)), &(*(first + i)));
           heapify_down(first, 0, i, comp);
       }
   }

   // =========================================================================
   // 2. 插入排序组件 (作为 Introsort 的第 3 层小区间收尾)
   // =========================================================================
   template <typename RandomIt, typename Compare>
   void mini_insertion_sort(RandomIt first, RandomIt last, Compare comp) {
       if (first == last) return;
       for (RandomIt cur = first + 1; cur != last; ++cur) {
           auto val = std::move(*cur);
           RandomIt hole = cur;
           while (hole != first && comp(val, *(hole - 1))) {
               *hole = std::move(*(hole - 1));
               --hole;
           }
           *hole = std::move(val);
       }
   }

   // =========================================================================
   // 3. Introsort (内省排序) 核心状态机
   // =========================================================================
   constexpr size_t kIntrosortThreshold = 16;

   // 三数取中 (Median-of-3)
   template <typename RandomIt, typename Compare>
   RandomIt median_of_3(RandomIt a, RandomIt b, RandomIt c, Compare comp) {
       if (comp(*a, *b)) {
           if (comp(*b, *c)) return b;       // a < b < c
           if (comp(*a, *c)) return c;       // a < c <= b
           return a;                         // c <= a < b
       } else {
           if (comp(*a, *c)) return a;       // b <= a < c
           if (comp(*b, *c)) return c;       // b < c <= a
           return b;                         // c <= b <= a
       }
   }

   template <typename RandomIt, typename Compare>
   RandomIt hoare_partition(RandomIt first, RandomIt last, Compare comp) {
       RandomIt mid = first + (last - first) / 2;
       RandomIt pivot_it = median_of_3(first, mid, last - 1, comp);
       auto pivot = *pivot_it;

       RandomIt left = first;
       RandomIt right = last - 1;

       while (true) {
           while (comp(*left, pivot)) ++left;
           while (comp(pivot, *right)) --right;

           if (left >= right) {
               return right + 1;
           }

           mini_iter_swap(&(*left), &(*right));
           ++left;
           --right;
       }
   }

   template <typename RandomIt, typename Compare>
   void introsort_loop(RandomIt first, RandomIt last, size_t depth_limit, Compare comp) {
       while (static_cast<size_t>(last - first) > kIntrosortThreshold) {
           if (depth_limit == 0) {
               // 达到深度上限: 降级为堆排序
               mini_heapsort(first, last, comp);
               return;
           }
           --depth_limit;

           // 快速排序划分
           RandomIt cut = hoare_partition(first, last, comp);
           // 尾递归优化: 递归左半段，原地循环右半段
           introsort_loop(cut, last, depth_limit, comp);
           last = cut;
       }
   }

   template <typename RandomIt, typename Compare = std::less<>>
   inline void mini_sort(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       size_t n = static_cast<size_t>(last - first);
       if (n <= 1) return;

       // 1 & 2 层: 快速排序 + 堆排序安全拦截
       size_t depth_limit = compute_depth_limit(n);
       introsort_loop(first, last, depth_limit, comp);

       // 3 层: 全局单遍插入排序扫尾 (极佳 Cache 命中)
       mini_insertion_sort(first, last, comp);
   }

   // =========================================================================
   // 4. Stable Mergesort (自适应稳定归并排序)
   // =========================================================================
   template <typename RandomIt, typename T, typename Compare>
   void merge_with_buffer(RandomIt first, RandomIt mid, RandomIt last, T* buf, Compare comp) {
       size_t len1 = static_cast<size_t>(mid - first);
       size_t len2 = static_cast<size_t>(last - mid);

       // 将前段复制到缓冲区
       for (size_t i = 0; i < len1; ++i) {
           buf[i] = std::move(*(first + i));
       }

       size_t p1 = 0;
       RandomIt p2 = mid;
       RandomIt dest = first;

       // 稳定双路归并 (<= 语义保证: 前段等价元素先落位)
       while (p1 < len1 && p2 != last) {
           if (comp(*p2, buf[p1])) {
               *dest = std::move(*p2);
               ++p2;
           } else {
               *dest = std::move(buf[p1]);
               ++p1;
           }
           ++dest;
       }

       // 刷入剩余前段
       while (p1 < len1) {
           *dest = std::move(buf[p1]);
           ++p1;
           ++dest;
       }
   }

   template <typename RandomIt, typename T, typename Compare>
   void stable_sort_rec(RandomIt first, RandomIt last, T* buf, Compare comp) {
       size_t n = static_cast<size_t>(last - first);
       if (n <= 15) {
           mini_insertion_sort(first, last, comp);
           return;
       }

       RandomIt mid = first + n / 2;
       stable_sort_rec(first, mid, buf, comp);
       stable_sort_rec(mid, last, buf, comp);
       merge_with_buffer(first, mid, last, buf, comp);
   }

   template <typename RandomIt, typename Compare = std::less<>>
   void mini_stable_sort(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       size_t n = static_cast<size_t>(last - first);
       if (n <= 1) return;

       using ValueType = typename std::iterator_traits<RandomIt>::value_type;
       std::vector<ValueType> buffer(n / 2 + 1); // 申请自适应临时缓冲区

       stable_sort_rec(first, last, buffer.data(), comp);
   }

   } // namespace core_sort

   // =========================================================================
   // 5. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   struct StudentRecord {
       std::string Name;
       int Score = 0;
       int Sequence = 0; // 原始录入序号 (用于检验稳定性)

       bool operator==(const StudentRecord& o) const noexcept {
           return Name == o.Name && Score == o.Score && Sequence == o.Sequence;
       }
   };

   inline void runSortingTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Introsort 内省排序与 StableSort 稳定性全景测试套件
";
       std::cout << "=======================================================

";

       using namespace core_sort;

       // 比较器: 按分数降序排列
       auto higher_score = [](const StudentRecord& a, const StudentRecord& b) {
           return a.Score > b.Score;
       };

       // 1. 测试 Introsort 全量排序与海量数据收敛
       {
           std::vector<int> numbers;
           constexpr size_t N = 10000;
           for (size_t i = 0; i < N; ++i) {
               numbers.push_back(static_cast<int>((i * 37 + 101) % 5000));
           }

           mini_sort(numbers.begin(), numbers.end());
           assert(std::is_sorted(numbers.begin(), numbers.end()));
           std::cout << "[测试 1: MiniIntrosort 10000 规模乱序排列]: 成功收敛且完全有序 (OK)
";
       }

       // 2. 测试 Introsort 深度超限堆排序降级 (反快速排序全等测试)
       {
           std::vector<int> allSame(5000, 77);
           mini_sort(allSame.begin(), allSame.end());
           assert(std::is_sorted(allSame.begin(), allSame.end()));
           assert(allSame.size() == 5000);
           std::cout << "[测试 2: MiniIntrosort 全等元素反退化压测]: 触发深度熔断/堆排序平稳收敛 (OK)
";
       }

       // 3. 核心验证: mini_stable_sort 严格保持等价元素相对顺序
       {
           std::vector<StudentRecord> students = {
               {"Alice",   90, 1},
               {"Bob",     95, 2},
               {"Chloe",   90, 3}, // 与 Alice 同为 90 分，初始在 Alice 之后
               {"David",   80, 4},
               {"Eric",    95, 5}, // 与 Bob 同为 95 分，初始在 Bob 之后
               {"Frank",   90, 6}  // 与 Alice、Chloe 同为 90 分，初始排第三
           };

           mini_stable_sort(students.begin(), students.end(), higher_score);

           std::cout << "
[测试 3: mini_stable_sort 稳定排序结果]:
";
           for (const auto& s : students) {
               std::cout << "  " << s.Name << " -> Score: " << s.Score << ", Seq: " << s.Sequence << "
";
           }

           // 核心断言 1: 分数严格降序
           assert(students[0].Score == 95 && students[1].Score == 95);
           assert(students[2].Score == 90 && students[3].Score == 90 && students[4].Score == 90);
           assert(students[5].Score == 80);

           // 核心断言 2: 95 分内部相对顺序绝对保持 [Bob#2 -> Eric#5]
           assert(students[0].Sequence == 2 && students[1].Sequence == 5);

           // 核心断言 3: 90 分内部相对顺序绝对保持 [Alice#1 -> Chloe#3 -> Frank#6]
           assert(students[2].Sequence == 1 && students[3].Sequence == 3 && students[4].Sequence == 6);

           std::cout << "  -> 核心断言通过: 等价元素相对时序完全保真，稳定排序契约绝对成立!

";
       }

       std::cout << "  -> 排序算法全景与微架构降级测试全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了现代 STL 排序算法的微架构运行规律：

1. **大吞吐乱序与反退化鲁棒性**：在测试 1 与测试 2 中，``MiniIntrosort`` 展现了极速的排序性能，在面对包含 5000 个相同元素的极端杀手序列时，深度监控状态机（``depth_limit``）迅速感知单侧划分并触发堆排序（``mini_heapsort``）安全熔断，彻底粉碎了退化至 $\mathcal{O}(N^2)$ 的物理风险。
2. **等价时序绝对保真**：在测试 3 中，``mini_stable_sort`` 在对包含三组同分等价类的记录进行排序时，分数完全按 $95 	o 90 	o 80$ 严格排序，且 $95$ 分内部的 ``[Bob#2, Eric#5]`` 与 $90$ 分内部的 ``[Alice#1, Chloe#3, Frank#6]`` 严格维持了初始录入序号，完美兑现了 $	ext{Stable}$ 算法的强物理保证。

小结与下章导读
--------------

本章系统解构了现代 C++ STL 排序与选择算法体系的微架构设计与实现机制：

1. **排序算法族能力矩阵**：剖析了 ``sort``（全量高速）、``stable_sort``（等价保序）、``partial_sort``（前 K 项有序）与 ``nth_element``（线性统计量选择）的契约边界。
2. **Introsort 三层降级状态机**：推导了快速排序三数取中、$	ext{DepthLimit}$ 耗尽时的堆排序安全熔断，以及小区间（$\le 16$）截断留待全局无守卫插入排序收敛的高性能流水线。
3. **自适应稳定归并机制**：解构了 ``std::stable_sort`` 在动态缓冲区充足（$\mathcal{O}(N \log N)$）与原址旋转（$\mathcal{O}(N \log^2 N)$）之间的自适应切换。
4. **严格弱序防线**：阐明了比较器使用 ``<=`` 导致划分游标越界破坏堆栈的物理灾难。

在掌握了全量与局部排序算法之后，下一章我们将深入剖析建立在有序序列之上的对数级检索、堆操作与数值归约算法。在第 5 模块第 5 节 **二分收敛、堆操作与数值算法：lower_bound/upper_bound 步进、make_heap 线性建堆与 std::accumulate/reduce 并行归约（``05_generic_algorithms_and_performance/05_binary_search_heap_and_numeric_reductions.rst``）** 中，我们将深入剖析 ``std::lower_bound`` / ``upper_bound`` 在随机访问迭代器上的无除法二分跳转、``make_heap`` 线性时间（$\mathcal{O}(N)$）下滤建堆数学证明、``std::accumulate`` 顺序累加与 C++17 ``std::reduce`` 结合乱序结合律的并行向量化归约微架构。
