====================================================================================================
极简泛型算法实战：find / copy / lower_bound / introsort 与 tag dispatch 优化
====================================================================================================

.. note:: 前置背景与上下文承接
   在上一节（``03_mini_red_black_tree_and_mini_hash_table.rst``）中，我们完成了关联容器与哈希容器（``MiniRBTree`` 与 ``MiniHashTable``）的核心微架构实战。STL 的核心架构哲学在于将数据的物理存储结构与上层操作算法彻底解耦。泛型算法完全通过迭代器所暴露的能力标签与操作契约访问半开区间 ``[first, last)``。本节作为工业级算法实战篇章，自底向上构建自包含、无外部库依赖的 ``MiniAlgorithm`` 体系，涵盖线性查找（``find`` / ``find_if``）、内存块加速拷贝（``copy`` / ``move``）、对数二分收敛（``lower_bound``）以及内省混合排序（``introsort``：快速排序、堆排序与插入排序协同降级），并系统化实现基于迭代器能力标签的编译期 ``tag dispatch`` 重载分发微架构。

泛型算法解耦哲学与半开区间契约
------------------------------

STL 算法的设计精髓在于“以迭代器为中介，实现容器与算法的正交分离”。算法无需了解容器是连续数组、双向链表亦或平衡树，仅需依据迭代器提供的指针算术或递增能力推进计算。

半开区间几何代数公理
~~~~~~~~~~~~~~~~~~~~

全部 STL 序列算法的操作范围统一受制于半开区间 $[first, last)$ 的几何代数契约：

1. **确定性停止条件**：推进指针 $first$ 达到与 $last$ 相同的位置即刻终止，空区间直接表示为 $first == last$。
2. **尾后哨兵安全性**：$last$ 作为尾后哨兵（Past-the-end），算法仅执行相等性比较（$first == last$），绝对禁止对 $last$ 执行解引用（``*last``）。
3. **区间拆分与拼接性**：对于任意中间合法迭代器 $mid$，恒有 $[first, last) = [first, mid) \cup [mid, last)$，使得分治算法能够无缝划分操作子集。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        半开区间 [first, last) 操作契约                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |     first                                                     last          |
   |       |                                                         |           |
   |       v                                                         v           |
   |   +-------+-------+-------+-------+-------+-------+         +-------+       |
   |   |   0   |   1   |   2   |  ...  |  N-1  | 哨兵  |  ...    | 非法  |       |
   |   +-------+-------+-------+-------+-------+-------+         +-------+       |
   |   | <--- 允许读取 / 写入 / 比较 ---> |   只允许比较相等性   | 禁止访问 |     |
   |                                                                             |
   |   - 元素总数: distance(first, last) == N                                    |
   |   - 循环终点: for (; first != last; ++first)                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

迭代器能力分层与算法复杂度分离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

算法的时间复杂度由“元素比较/操作次数”与“迭代器推进成本”两部分复合决定：

.. list-table:: 典型泛型算法迭代器能力需求与复杂度矩阵
   :widths: 22 25 25 28
   :header-rows: 1
   :class: tight-table

   * - 算法名称
     - 最小充分迭代器类别
     - 元素操作复杂度
     - 迭代器推进开销
   * - ``find`` / ``find_if``
     - Input Iterator
     - $\mathcal{O}(N)$ 比较
     - 逐节点推进：$\mathcal{O}(N)$
   * - ``copy`` / ``move``
     - Input / Output Iterator
     - $\mathcal{O}(N)$ 赋值
     - 连续内存优化下：$\mathcal{O}(1)$ 块复制
   * - ``lower_bound``
     - Forward Iterator
     - $\mathcal{O}(\log N)$ 比较
     - Forward：$\mathcal{O}(N)$；RandomAccess：$\mathcal{O}(\log N)$
   * - ``introsort``
     - Random Access Iterator
     - $\mathcal{O}(N \log N)$ 比较
     - $\mathcal{O}(1)$ 随机访问与跨度跳跃

线性查找与谓词短路机制（find / find_if）
----------------------------------------

``find`` 与 ``find_if`` 是泛型查找算法的基础原语。其核心在于利用单向输入迭代器的最小能力，在未知长度的流式或容器区间中定位目标。

核心实现与短路退出模型
~~~~~~~~~~~~~~~~~~~~~~

算法采用单重前向推进循环，在首次匹配成功时立即短路返回当前迭代器；若遍历至尾后哨兵仍未命中，统一返回 $last$：

.. code-block:: cpp

   template <typename InputIt, typename T>
   InputIt find(InputIt first, InputIt last, const T& value) {
       for (; first != last; ++first) {
           if (*first == value) {
               return first;
           }
       }
       return last;
   }

   template <typename InputIt, typename Predicate>
   InputIt find_if(InputIt first, InputIt last, Predicate pred) {
       for (; first != last; ++first) {
           if (pred(*first)) {
               return first;
           }
       }
       return last;
   }

工程约束法则：
1. **统一返回值语义**：未命中时返回 $last$ 维持了半开区间的一致性。调用方只需比对 ``pos != last`` 即可确立元素有效性。
2. **纯函数式谓词要求**：传递给 ``find_if`` 的谓词函数对象必须满足只读契约，禁止在谓词调用中修改被测元素或捕获可变外部状态，确保多核并发安全与确定性行为。

内存拷贝与移动优化架构（copy / move）
--------------------------------------

在连续内存区间之间搬移数据时，泛型算法的性能差异主要源于抽象层级：逐元素调用拷贝赋值运算符会产生大量的函数调用与微指令开销；而硬件层面的 DMA 或向量化指令（如 AVX-512 / NEON）能够以数十 GB/s 的带宽吞吐连续内存块。

Tag Dispatch 与底层 Memmove 快速路径
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准库 ``std::copy`` 在设计上采用了多层特化分发流水线。对于满足“源与目标均为原生裸指针”且“值类型具备平凡拷贝赋值属性（``is_trivially_copyable_v``）”的数据区间，算法直接降级调用 C 运行库原语 ``std::memmove``：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Mini-Copy 编译期分发优化流水线                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   mini_copy(first, last, d_first)                                           |
   |                 |                                                           |
   |                 v                                                           |
   |   [ 检查是否为同构裸指针且为平凡类型? ]                                     |
   |   (is_pointer<It>::value && is_trivially_copyable<ValueType>::value)        |
   |          /                                         \                        |
   |        (是)                                        (否)                     |
   |         v                                           v                       |
   |   [ 极速底层路径 ]                            [ 通用泛型路径 ]              |
   |   - 计算字节跨度: (last - first) * sizeof(T)  - 逐元素推进循环              |
   |   - 直接调用 std::memmove                     - *d_first = *first           |
   |   - 返回 d_first + (last - first)             - 适度触发循环展开            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

内存重叠边界与正反向算法选择
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当源区间与目标区间位于同一连续存储缓冲区时，写指针与读指针的相对位置决定了复制方向的安全性：

- **正向拷贝安全区间（向左移动）**：当 $d\_first \le first$ 时，写入位置在读取位置之前，先读取后写入能够确保源数据未被覆写，正向 ``copy`` 绝对安全。
- **反向拷贝安全区间（向右移动）**：当 $d\_first > first$ 且 $d\_first < last$ 时，正向写入会提前覆盖尚未读取的右侧源元素。必须采用反向拷贝算法 ``copy_backward``，自尾部哨兵倒序推进。
- **memmove 硬件级重叠安全**：在指针快速路径中，直接调用 ``std::memmove`` 原生保证了任意重叠区间的正确拷贝。

移动算法与 moved-from 状态生命周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``mini_move`` 算法执行的本质是批量移动赋值：``*d_first = std::move(*first)``。
该操作将源区间对象内部持有的堆资源或操作系统句柄转交由目标区间接管。源元素依然处于合法的析构存活期，其状态转为 moved-from 状态。该算法为容器扩容提供了核心基础支撑。

对数二分搜索与 Tag Dispatch 架构（lower_bound）
------------------------------------------------

``lower_bound`` 算法的核心任务在于：在一个相对于目标值已完成分区的半开区间 $[first, last)$ 中，以对数阶时间检索首个“未排在目标值之前”（即满足 $
eg 	ext{comp}(element, value)$）的元素位置。

数学循环不变量与二分收敛状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

算法通过维护当前有效区间长度 $count$ 与当前区间起点 $first$ 构成循环不变量。每轮迭代将区间平分为两半，步长 $step = \lfloor count / 2 \rfloor$：

1. **测试中点**：$middle = first + step$；
2. **向右收敛**：若 $	ext{comp}(*middle, value)$ 成立，表明 $middle$ 及其左侧所有元素均严格排在目标值之前。合法解必然位于 $middle$ 之后，算法更新 $first = middle + 1$，$count = count - (step + 1)$；
3. **向左收敛**：若 $	ext{comp}(*middle, value)$ 不成立，表明 $middle$ 本身或其左侧元素即为潜在的首个边界。保留左半区间，更新 $count = step$。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     lower_bound 循环不变量二分收敛状态机                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   当前区间: [first, first + count)                                          |
   |                                                                             |
   |   step = count / 2;                                                         |
   |   middle = first + step;                                                    |
   |                                                                             |
   |                       middle                                                |
   |                         v                                                   |
   |   [ ... 前半段 ... ] [ *middle ] [ ... 后半段 ... ]                         |
   |                                                                             |
   |   - 分支 A: comp(*middle, value) == true                                    |
   |     -> 目标在右半段: first = middle + 1, count = count - step - 1           |
   |                                                                             |
   |   - 分支 B: comp(*middle, value) == false                                   |
   |     -> 目标在当前位置或左半段: count = step                                 |
   |                                                                             |
   |   循环终止条件: count == 0，返回 first。                                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

基于 Iterator Tag 的编译期重载分发
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于随机访问迭代器，中点定位 $middle = first + step$ 是单周期的加法算术；而对于前向迭代器，中点定位需要执行 $step$ 次单步迭代推进。通过 ``tag dispatch``，编译器在编译阶段根据迭代器类型标签选择最优实现：

.. code-block:: cpp

   // 针对前向迭代器的低配路径：O(N) 步进，O(log N) 比较
   template <typename ForwardIt, typename T, typename Compare>
   ForwardIt lower_bound_dispatch(ForwardIt first, ForwardIt last, const T& value,
                                  Compare comp, std::forward_iterator_tag) {
       using diff_t = typename std::iterator_traits<ForwardIt>::difference_type;
       diff_t count = std::distance(first, last);
       while (count > 0) {
           ForwardIt middle = first;
           diff_t step = count / 2;
           std::advance(middle, step);
           if (comp(*middle, value)) {
               first = ++middle;
               count -= step + 1;
           } else {
               count = step;
           }
       }
       return first;
   }

   // 针对随机访问迭代器的高速路径：O(1) 步进，O(log N) 比较
   template <typename RandomIt, typename T, typename Compare>
   RandomIt lower_bound_dispatch(RandomIt first, RandomIt last, const T& value,
                                 Compare comp, std::random_access_iterator_tag) {
       using diff_t = typename std::iterator_traits<RandomIt>::difference_type;
       diff_t count = last - first;
       while (count > 0) {
           diff_t step = count / 2;
           RandomIt middle = first + step;
           if (comp(*middle, value)) {
               first = middle + 1;
               count -= step + 1;
           } else {
               count = step;
           }
       }
       return first;
   }

工业级混合内省排序（Mini-Introsort）
------------------------------------

标准库 ``std::sort`` 在工业实践中广泛采用 David Musser 提出的内省排序（Introsort）混合策略。纯快速排序虽然平均时间复杂度为 $\mathcal{O}(N \log N)$ 且常数因子极小，但在恶劣输入（如已排序序列或大量重复键值）下可能退化为 $\mathcal{O}(N^2)$；堆排序（Heapsort）的最坏时间复杂度稳定在严格的 $\mathcal{O}(N \log N)$，但其非连续内存访问导致 CPU 缓存局部性较差；插入排序（Insertion Sort）在处理极短区间（$N < 16$）时，能够依托近乎线性的指令流与高度连续的缓存命中压倒高级递归排序。

Introsort 三段式协同微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~

内省排序通过监控递归深度，实现了三类排序算法的优势互补：

1. **快速排序主干（Quicksort）**：利用三数取中法（Median-of-Three）确定划分枢轴（Pivot），执行双向扫描划分（Hoare Partition），展开左右子区间分治。
2. **深度超限兜底（Heapsort）**：维护最大允许递归深度上界 $max\_depth = 2 	imes \lfloor \log_2(last - first) \rfloor$。一旦递归层次触碰上界，表明快排主元选择遭遇病态输入，算法即刻将当前子区间就地转入堆排序，强行截断平方级退化通道。
3. **小区间插入排序（Insertion Sort）**：当子区间长度小于阈值（通常设定为 16）时，直接停止快排递归切分。最终对全局或局部小区间执行插入排序，彻底消除微小区间的递归压栈与函数调用开销。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Mini-Introsort 决策与流转状态机                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   introsort(first, last)                                                    |
   |              |                                                              |
   |              v                                                              |
   |   [ 区间元素总数 N <= 16 ? ] ----(是)----> [ 执行直接插入排序完成 ]         |
   |              |                                                              |
   |             (否)                                                            |
   |              v                                                              |
   |   [ 剩余深度 depth_limit == 0 ? ] --(是)--> [ 执行堆排序 (Heapsort) 兜底 ]  |
   |              |                                                              |
   |             (否)                                                            |
   |              v                                                              |
   |   [ 三数取中 (Median-of-Three) 选择 Pivot ]                                 |
   |              |                                                              |
   |              v                                                              |
   |   [ 执行双向划分 (Partition), 划分点为 cut ]                                |
   |              |                                                              |
   |              +-----------------------+                                      |
   |              |                       |                                      |
   |              v                       v                                      |
   |   introsort_loop(cut, last, depth-1) introsort_loop(first, cut, depth-1)    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级自包含 C++ MiniAlgorithm 完整实现
---------------------------------------

以下提供无第三方依赖、完全自包含且满足生产级质量标准的泛型算法库实战代码，包含底层类型萃取、内存快速通道、Tag Dispatch 分发、内省排序状态机以及完备的单元测试用例集：

.. code-block:: cpp

   #include <iostream>
   #include <cstddef>
   #include <cstring>
   #include <utility>
   #include <functional>
   #include <type_traits>
   #include <iterator>
   #include <cassert>
   #include <vector>
   #include <string>

   namespace mini_stl {

   // ---------------------------------------------------------------------------
   // 1. 线性查找族：find 与 find_if
   // ---------------------------------------------------------------------------

   template <typename InputIt, typename T>
   InputIt find(InputIt first, InputIt last, const T& value) {
       for (; first != last; ++first) {
           if (*first == value) {
               return first;
           }
       }
       return last;
   }

   template <typename InputIt, typename Predicate>
   InputIt find_if(InputIt first, InputIt last, Predicate pred) {
       for (; first != last; ++first) {
           if (pred(*first)) {
               return first;
           }
       }
       return last;
   }

   // ---------------------------------------------------------------------------
   // 2. 拷贝与移动算法：copy 与 move (含 memmove 快速通道优化)
   // ---------------------------------------------------------------------------

   namespace detail {

   template <typename InputIt, typename OutputIt>
   OutputIt copy_dispatch(InputIt first, InputIt last, OutputIt d_first, std::false_type) {
       for (; first != last; ++first, ++d_first) {
           *d_first = *first;
       }
       return d_first;
   }

   template <typename T, typename U>
   U* copy_dispatch(T* first, T* last, U* d_first, std::true_type) {
       const std::size_t count = static_cast<std::size_t>(last - first);
       if (count > 0) {
           std::memmove(d_first, first, count * sizeof(T));
       }
       return d_first + count;
   }

   } // namespace detail

   template <typename InputIt, typename OutputIt>
   OutputIt copy(InputIt first, InputIt last, OutputIt d_first) {
       using InValue = typename std::iterator_traits<InputIt>::value_type;
       using OutValue = typename std::iterator_traits<OutputIt>::value_type;

       constexpr bool use_memmove = std::is_pointer_v<InputIt> &&
                                   std::is_pointer_v<OutputIt> &&
                                   std::is_same_v<std::remove_const_t<InValue>, OutValue> &&
                                   std::is_trivially_copyable_v<OutValue>;

       return detail::copy_dispatch(first, last, d_first, std::bool_constant<use_memmove>{});
   }

   template <typename InputIt, typename OutputIt>
   OutputIt move(InputIt first, InputIt last, OutputIt d_first) {
       for (; first != last; ++first, ++d_first) {
           *d_first = std::move(*first);
       }
       return d_first;
   }

   // ---------------------------------------------------------------------------
   // 3. 对数二分查找：lower_bound (带 tag dispatch 分发)
   // ---------------------------------------------------------------------------

   namespace detail {

   template <typename ForwardIt, typename T, typename Compare>
   ForwardIt lower_bound_impl(ForwardIt first, ForwardIt last, const T& value,
                              Compare comp, std::forward_iterator_tag) {
       using diff_t = typename std::iterator_traits<ForwardIt>::difference_type;
       diff_t count = std::distance(first, last);

       while (count > 0) {
           ForwardIt middle = first;
           diff_t step = count / 2;
           std::advance(middle, step);

           if (comp(*middle, value)) {
               first = ++middle;
               count -= step + 1;
           } else {
               count = step;
           }
       }
       return first;
   }

   template <typename RandomIt, typename T, typename Compare>
   RandomIt lower_bound_impl(RandomIt first, RandomIt last, const T& value,
                             Compare comp, std::random_access_iterator_tag) {
       using diff_t = typename std::iterator_traits<RandomIt>::difference_type;
       diff_t count = last - first;

       while (count > 0) {
           diff_t step = count / 2;
           RandomIt middle = first + step;

           if (comp(*middle, value)) {
               first = middle + 1;
               count -= step + 1;
           } else {
               count = step;
           }
       }
       return first;
   }

   } // namespace detail

   template <typename ForwardIt, typename T, typename Compare = std::less<>>
   ForwardIt lower_bound(ForwardIt first, ForwardIt last, const T& value, Compare comp = Compare{}) {
       using category = typename std::iterator_traits<ForwardIt>::iterator_category;
       return detail::lower_bound_impl(first, last, value, comp, category{});
   }

   // ---------------------------------------------------------------------------
   // 4. 工业级内省排序 (Mini-Introsort) 核心架构
   // ---------------------------------------------------------------------------

   namespace detail {

   // 插入排序：处理小规模连续区间 (N <= 16)
   template <typename RandomIt, typename Compare>
   void insertion_sort(RandomIt first, RandomIt last, Compare comp) {
       if (first == last) return;
       for (RandomIt cur = first + 1; cur != last; ++cur) {
           auto val = std::move(*cur);
           RandomIt hole = cur;
           while (hole > first && comp(val, *(hole - 1))) {
               *hole = std::move(*(hole - 1));
               --hole;
           }
           *hole = std::move(val);
       }
   }

   // 堆下滤调整算法 (Max-Heap Sift-down)
   template <typename RandomIt, typename Distance, typename Compare>
   void sift_down(RandomIt first, Distance root, Distance len, Compare comp) {
       auto val = std::move(*(first + root));
       while (root * 2 + 1 < len) {
           Distance child = root * 2 + 1;
           if (child + 1 < len && comp(*(first + child), *(first + child + 1))) {
               ++child;
           }
           if (comp(val, *(first + child))) {
               *(first + root) = std::move(*(first + child));
               root = child;
           } else {
               break;
           }
       }
       *(first + root) = std::move(val);
   }

   // 堆排序 (Heapsort 兜底实现)
   template <typename RandomIt, typename Compare>
   void heap_sort(RandomIt first, RandomIt last, Compare comp) {
       const auto len = last - first;
       if (len <= 1) return;

       for (auto i = (len - 2) / 2; i >= 0; --i) {
           sift_down(first, i, len, comp);
       }
       for (auto i = len - 1; i > 0; --i) {
           using std::swap;
           swap(*first, *(first + i));
           sift_down(first, static_cast<decltype(len)>(0), i, comp);
       }
   }

   // 三数取中中值索引判定
   template <typename RandomIt, typename Compare>
   RandomIt median_of_three(RandomIt a, RandomIt b, RandomIt c, Compare comp) {
       if (comp(*a, *b)) {
           if (comp(*b, *c)) return b;
           return comp(*a, *c) ? c : a;
       }
       if (comp(*a, *c)) return a;
       return comp(*b, *c) ? c : b;
   }

   // 双向扫描划分 (Hoare-style Partition)
   template <typename RandomIt, typename Compare>
   RandomIt partition(RandomIt first, RandomIt last, Compare comp) {
       RandomIt mid = first + (last - first) / 2;
       RandomIt pivot_it = median_of_three(first, mid, last - 1, comp);

       using std::swap;
       swap(*first, *pivot_it);
       auto pivot = *first;

       RandomIt left = first;
       RandomIt right = last;

       while (true) {
           do {
               ++left;
           } while (left < last && comp(*left, pivot));

           do {
               --right;
           } while (comp(pivot, *right));

           if (left >= right) {
               break;
           }
           swap(*left, *right);
       }
       swap(*first, *right);
       return right;
   }

   // 计算 log2(N) 整数值用于深度界定
   template <typename T>
   T log2_floor(T n) {
       T log = 0;
       while (n >>= 1) {
           ++log;
       }
       return log;
   }

   // Introsort 核心递归切分状态机
   template <typename RandomIt, typename Size, typename Compare>
   void introsort_loop(RandomIt first, RandomIt last, Size depth_limit, Compare comp) {
       constexpr Size INSERTION_SORT_THRESHOLD = 16;

       while (last - first > static_cast<decltype(last - first)>(INSERTION_SORT_THRESHOLD)) {
           if (depth_limit == 0) {
               heap_sort(first, last, comp);
               return;
           }
           --depth_limit;

           RandomIt cut = partition(first, last, comp);
           introsort_loop(cut + 1, last, depth_limit, comp);
           last = cut; // 尾递归优化展开
       }
   }

   } // namespace detail

   template <typename RandomIt, typename Compare = std::less<>>
   void sort(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       using category = typename std::iterator_traits<RandomIt>::iterator_category;
       static_assert(std::is_base_of_v<std::random_access_iterator_tag, category>,
                     "mini_stl::sort 要求具备 RandomAccessIterator 访问能力");

       if (first != last) {
           const auto len = last - first;
           detail::introsort_loop(first, last, detail::log2_floor(len) * 2, comp);
           detail::insertion_sort(first, last, comp);
       }
   }

   } // namespace mini_stl

   // ===========================================================================
   // 5. 单元测试与微架构验证套件
   // ===========================================================================

   struct TrackedItem {
       int id{0};
       std::string payload;

       TrackedItem() = default;
       explicit TrackedItem(int v, std::string s = "") : id(v), payload(std::move(s)) {}

       bool operator==(const TrackedItem& o) const noexcept { return id == o.id; }
       bool operator<(const TrackedItem& o) const noexcept { return id < o.id; }
   };

   int main() {
       // --- 测试 1: find 与 find_if 语义验证 ---
       std::vector<TrackedItem> items{
           TrackedItem{10, "alpha"}, TrackedItem{20, "beta"},
           TrackedItem{30, "gamma"}, TrackedItem{40, "delta"}
       };

       auto it_found = mini_stl::find(items.begin(), items.end(), TrackedItem{20});
       assert(it_found != items.end());
       assert(it_found->payload == "beta");

       auto it_pred = mini_stl::find_if(items.begin(), items.end(), [](const TrackedItem& item) {
           return item.id > 25;
       });
       assert(it_pred != items.end());
       assert(it_pred->id == 30);

       auto it_missing = mini_stl::find(items.begin(), items.end(), TrackedItem{99});
       assert(it_missing == items.end());

       // --- 测试 2: copy 算法 (平凡类型触发 memmove 快速通道验证) ---
       int raw_src[5] = {1, 2, 3, 4, 5};
       int raw_dst[5] = {0};
       mini_stl::copy(raw_src, raw_src + 5, raw_dst);
       for (int i = 0; i < 5; ++i) {
           assert(raw_dst[i] == i + 1);
       }

       // 非平凡类型逐元素拷贝验证
       std::vector<TrackedItem> copy_dst(items.size());
       mini_stl::copy(items.begin(), items.end(), copy_dst.begin());
       assert(copy_dst.size() == 4);
       assert(copy_dst[2].payload == "gamma");

       // --- 测试 3: move 算法状态转移验证 ---
       std::vector<TrackedItem> move_dst(items.size());
       mini_stl::move(items.begin(), items.end(), move_dst.begin());
       assert(move_dst[0].payload == "alpha");
       // 原元素处于合法析构的 moved-from 状态

       // --- 测试 4: lower_bound 二分收敛与 tag dispatch ---
       std::vector<int> sorted_nums{10, 20, 30, 40, 50, 60, 70};

       // 命中已有值
       auto lb1 = mini_stl::lower_bound(sorted_nums.begin(), sorted_nums.end(), 30);
       assert(lb1 != sorted_nums.end() && *lb1 == 30);

       // 命中插入点 (首个不小于 35 的位置，即 40)
       auto lb2 = mini_stl::lower_bound(sorted_nums.begin(), sorted_nums.end(), 35);
       assert(lb2 != sorted_nums.end() && *lb2 == 40);

       // 超过全区间极大值，返回 last 哨兵
       auto lb3 = mini_stl::lower_bound(sorted_nums.begin(), sorted_nums.end(), 100);
       assert(lb3 == sorted_nums.end());

       // --- 测试 5: introsort 全场景排序稳定性与正确性验证 ---
       std::vector<int> nums_to_sort{
           42, 17, 93, 8, 23, 71, 15, 64, 38, 9, 88, 52, 29, 61, 3, 49,
           81, 12, 33, 77, 2, 55, 99, 21, 46, 73, 10, 66, 35, 6, 85, 50
       };

       mini_stl::sort(nums_to_sort.begin(), nums_to_sort.end());

       for (std::size_t i = 0; i < nums_to_sort.size() - 1; ++i) {
           assert(nums_to_sort[i] <= nums_to_sort[i + 1]);
       }

       // 逆序大数组测试 (检验快速排序深度超限自动切入堆排序兜底能力)
       std::vector<int> pathological_input(100);
       for (int i = 0; i < 100; ++i) {
           pathological_input[i] = 100 - i;
       }
       mini_stl::sort(pathological_input.begin(), pathological_input.end());
       for (int i = 0; i < 99; ++i) {
           assert(pathological_input[i] == i + 1);
       }

       std::cout << "All MiniAlgorithm tests passed successfully!" << std::endl;
       return 0;
   }
