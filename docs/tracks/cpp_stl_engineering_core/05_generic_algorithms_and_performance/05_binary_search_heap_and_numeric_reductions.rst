========================================================================================================================
二分收敛、堆操作与数值算法：lower_bound/upper_bound 步进、make_heap 线性建堆与 std::accumulate/reduce 并行归约
========================================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块第 4 节（``05_generic_algorithms_and_performance/04_introsort_quicksort_heapsort_and_stablesort.rst``）中，我们系统剖析了快速排序、堆排序、插入排序与归并排序的微架构设计与 ``std::sort`` 内省排序（Introsort）的三层自适应状态机。当数据序列完成排序或构建为特定树形拓扑后，STL 提供了一系列基于有序性假设的高效算法。本章深入解构 STL 算法体系的三大支柱：对数时间二分搜索（``lower_bound``、``upper_bound``、``equal_range``）在不同迭代器品类下的步进收敛机制、隐式完全二叉树堆算法（``make_heap``、``push_heap``、``pop_heap``）的线性时间（$\mathcal{O}(N)$）建堆数学证明，以及从 C++98 串行左折叠 ``std::accumulate`` 到 C++17 结合律可重排的并行树状归约 ``std::reduce`` 与 ``std::transform_reduce`` 的演进机理。

二分搜索算法族与迭代器分发收敛状态机
------------------------------------

STL 二分搜索算法建立在序列按指定谓词局部有序（Partitioned / Sorted）的先验契约之上。二分搜索族由四大核心算法构成：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     STL 二分搜索算法族语义与返回值契约                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 序列示例 ]:  [ 10,  20,  20,  20,  30,  40 ]                            |
   |                                                                             |
   |   1. std::lower_bound(first, last, 20)                                      |
   |      -> 返回首个满足 !(elem < 20) 的迭代器 (即首个 >= 20 的位置, 索引 1)    |
   |                                                                             |
   |   2. std::upper_bound(first, last, 20)                                      |
   |      -> 返回首个满足 20 < elem 的迭代器 (即首个 > 20 的位置, 索引 4)        |
   |                                                                             |
   |   3. std::equal_range(first, last, 20)                                      |
   |      -> 返回 std::pair(lower_bound, upper_bound)，构成半开区间 [1, 4)       |
   |                                                                             |
   |   4. std::binary_search(first, last, 20)                                    |
   |      -> 返回 bool: (lower_bound != last && !(20 < *lower_bound)) (true)     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

二分搜索算法特性矩阵
~~~~~~~~~~~~~~~~~~~~

.. list-table:: 二分搜索算法族功能、比较准则与复杂度对比
   :widths: 20 28 26 26
   :header-rows: 1
   :class: tight-table

   * - 算法名称
     - 核心判定准则
     - 返回值类型
     - 时间复杂度
   * - ``lower_bound``
     - 首个不小于（$
eg(	ext{elem} < 	ext{val})$）
     - ``ForwardIt``
     - $\mathcal{O}(\log N)$ 比较
   * - ``upper_bound``
     - 首个严格大于（$	ext{val} < 	ext{elem}$）
     - ``ForwardIt``
     - $\mathcal{O}(\log N)$ 比较
   * - ``equal_range``
     - 包含所有等价元素的连续半开区间
     - ``std::pair<ForwardIt, ForwardIt>``
     - $\mathcal{O}(\log N)$ 比较
   * - ``binary_search``
     - 目标元素是否存在于序列中
     - ``bool``
     - $\mathcal{O}(\log N)$ 比较

迭代器能力对二分搜索性能的决定性影响
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

二分搜索要求在每一轮迭代中将当前查找区间 $[first, last)$ 平分为两半。然而，迭代器分类对二分搜索的物理执行代价有着质的差异：

1. **随机访问迭代器（RandomAccessIterator）**：
   - 步进距离计算：$	ext{count} = last - first$ 仅需单周期减法指令。
   - 中间节点定位：$first + \lfloor 	ext{count} / 2 \rfloor$ 仅需单周期指针加法指令。
   - **总体代价**：$\mathcal{O}(\log N)$ 次元素比较，$\mathcal{O}(\log N)$ 次指针位移，达成真正的对数时间复杂度。
2. **前向/双向迭代器（ForwardIterator / BidirectionalIterator）**：
   - 步进距离计算：由于无法直接相减，内部维护一个步进计数器 $	ext{count}$，每轮迭代 $	ext{step} = \lfloor 	ext{count} / 2 \rfloor$。
   - 中间节点定位：必须调用 ``std::advance(first, step)`` 逐个节点沿指针链跳转 $	ext{step}$ 次。
   - **总体代价**：虽然元素比较次数依然维持在 $\mathcal{O}(\log N)$ 次，但指针跳转的总次数为 $\sum_{k=1}^{\log_2 N} \frac{N}{2^k} \approx N$。**总体时间复杂度退化为 $\mathcal{O}(N)$ 线性时间**。

.. warning::
   对 ``std::list``、``std::set`` 或 ``std::map`` 使用全局 ``std::lower_bound(l.begin(), l.end(), val)`` 会退化为 $\mathcal{O}(N)$ 遍历并破坏缓存局部性；必须优先调用关联容器自带的成员函数 ``s.lower_bound(val)`` 以利用红黑树内部的父子指针达成 $\mathcal{O}(\log N)$ 检索。

二叉堆拓扑与 make_heap 线性建堆数学证明
---------------------------------------

STL 堆算法将连续线性内存（如 ``std::vector`` 或原生数组）隐式映射为一颗 **完全二叉树（Complete Binary Tree）**。默认情况下构建的是 **大顶堆（Max-Heap）**，满足堆序性公理：任何父节点的值均大于或等于其左右子节点的值。

隐式数组父子节点索引映射公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于以 0 为起始索引的连续数组，节点 $i$ 的拓扑关系严格遵循以下代数公式：

.. math::

   	ext{Parent}(i) = \left\lfloor \frac{i - 1}{2} \right\rfloor, \quad
   	ext{LeftChild}(i) = 2i + 1, \quad
   	ext{RightChild}(i) = 2i + 2

大顶堆的核心操作机制
~~~~~~~~~~~~~~~~~~~~

1. **上滤（Sift-Up / push_heap）**：
   - 当新元素插入数组末尾（索引 $N-1$）时，向上与其父节点比较。若新元素大于父节点，则将父节点下移，形成空穴并继续向上回溯，直到满足堆序性。单次操作耗时 $\mathcal{O}(\log N)$。
2. **下滤（Sift-Down / pop_heap）**：
   - 将堆顶元素（索引 0）与数组末尾元素交换，堆有效尺寸减 1。随后将原末尾元素置于根部，自顶向下在左右子节点中寻找最大者比较下滤，单次操作耗时 $\mathcal{O}(\log N)$。
3. **线性建堆（Bottom-Up Construction / make_heap）**：
   - 忽略所有叶子节点（因为单节点天然成堆），从最后一个非叶子节点 $\lfloor (N - 2) / 2 \rfloor$ 开始，逆序向前直到根节点 0，依次对每个子树执行下滤操作。

make_heap 线性时间复杂度 $\mathcal{O}(N)$ 严格数学证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设有 $N$ 个元素的完全二叉树，树高为 $H = \lfloor \log_2 N \rfloor$。深度为 $h$ 层的节点距离底部的最大下滤步数为 $H - h$。在高度为 $k$（距离叶子层高度，叶子层 $k=0$）的层级上，最多有 $\lceil N / 2^{k+1} \rceil$ 个节点，每个节点最多下滤 $k$ 步。

全树下滤操作的总比较与位移步数 $S(N)$ 为：

.. math::

   S(N) = \sum_{k=0}^{\lfloor \log_2 N \rfloor} \left\lceil \frac{N}{2^{k+1}} \right\rceil \cdot k \le N \sum_{k=0}^{\infty} \frac{k}{2^{k+1}} = \frac{N}{2} \sum_{k=0}^{\infty} \frac{k}{2^k}

令级数 $A = \sum_{k=0}^{\infty} \frac{k}{2^k} = 0 + \frac{1}{2} + \frac{2}{4} + \frac{3}{8} + \frac{4}{16} + \dots$

两边同乘 $\frac{1}{2}$ 得：

.. math::

   \frac{1}{2} A = \sum_{k=0}^{\infty} \frac{k}{2^{k+1}} = 0 + \frac{1}{4} + \frac{2}{8} + \frac{3}{16} + \dots

错位相减：

.. math::

   A - \frac{1}{2} A = \frac{1}{2} A = \sum_{k=1}^{\infty} \frac{1}{2^k} = \frac{1/2}{1 - 1/2} = 1 \implies A = 2

代回原式：

.. math::

   S(N) \le \frac{N}{2} \cdot 2 = N = \mathcal{O}(N)

**结论**：自底向上的 ``make_heap`` 复杂度严格收敛于 $\mathcal{O}(N)$ 线性时间，远优于连续执行 $N$ 次 ``push_heap`` 所需的 $\mathcal{O}(N \log N)$ 开销。

数值归约体系：从 accumulate 串行折叠到 reduce 并行树状归约
---------------------------------------------------------

数值算法负责对数据序列进行聚合统计、前缀扫描与变换归约。

accumulate 串行累加模型及其微架构瓶颈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++98 引入的 ``std::accumulate`` 采用严格的 **左折叠（Left Fold）** 语义：

.. math::

   	ext{acc}_{k} = 	ext{op}(	ext{acc}_{k-1}, \ x_k), \quad 	ext{acc}_0 = 	ext{init}

.. code-block:: cpp

   template <class InputIt, class T, class BinaryOp>
   T accumulate(InputIt first, InputIt last, T init, BinaryOp op) {
       for (; first != last; ++first) {
           init = op(init, *first); // 强依赖前一轮循环结果
       }
       return init;
   }

1. **确定性顺序优势**：由于严格按从左到右的顺序执行，对于不满足结合律的操作（如浮点数加法、字符串拼接、多项式迭代），其计算结果在各平台绝对一致。
2. **流水线串行化瓶颈**：每一次循环迭代都存在致命的 **RAW 真数据依赖**（当前加法必须等待上一轮加法写回寄存器）。现代 CPU 的超标量乱序执行引擎与 SIMD 向量化单元（AVX2 / AVX-512 / NEON）完全无法展开并行运算。

C++17 reduce 并行树状归约模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了释放现代多核 CPU 与 SIMD 向量化指令的全部硬件吞吐，C++17 引入了 ``std::reduce`` 与 ``std::transform_reduce``：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |              std::accumulate 串行折叠 vs std::reduce 并行树状归约           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. std::accumulate (串行线性依赖, 深度 = N) ]                           |
   |      ((((init + x0) + x1) + x2) + x3)                                       |
   |                                                                             |
   |   [ 2. std::reduce (树状无序归约, 深度 = log2 N, 支持 SIMD 与多线程并发) ]  |
   |             [ (x0 + x1) ]     +     [ (x2 + x3) ]                           |
   |                   \                     /                                   |
   |                    +-------[ 总和 ]----+                                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **代数公理要求**：``op`` 必须满足 **结合律（Associativity）** 与 **交换律（Commutativity）**，即：

.. math::

   (a \oplus b) \oplus c = a \oplus (b \oplus c), \quad a \oplus b = b \oplus a

2. **SIMD 与并行执行策略**：在满足结合律的前提下，底层运行库（如 Intel TBB 或标准库并行策略 ``std::execution::par_unseq``）可将大数组切分为数千个独立块，在各个 CPU 核心与 SIMD 向量通道中并行累加，最后执行多路树状汇总，将延迟从 $\mathcal{O}(N)$ 降至 $\mathcal{O}(\log N)$。

工业级 C++ 完整二分搜索、二叉堆与数值归约引擎实现
--------------------------------------------------

以下源码实现了一套自包含的工业级模板库，涵盖：
1. 适配随机访问迭代器的高性能二分搜索（``mini_lower_bound``、``mini_upper_bound``、``mini_equal_range``）。
2. 基于空穴移动（Hole Propagation）优化的大顶堆算法集（``mini_push_heap``、``mini_pop_heap``、``mini_make_heap``、``mini_sort_heap``）。
3. 串行左折叠 ``mini_accumulate`` 与分块并行树状归约 ``mini_reduce``。
4. 全量验证测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <utility>
   #include <functional>
   #include <numeric>
   #include <cstdint>
   #include <cassert>
   #include <algorithm>

   namespace generic_algo_engine {

   // =========================================================================
   // 1. 二分搜索算法族实现 (针对随机访问迭代器优化)
   // =========================================================================

   template <typename RandomIt, typename T, typename Compare = std::less<T>>
   RandomIt mini_lower_bound(RandomIt first, RandomIt last, const T& value, Compare comp = Compare{}) {
       auto len = last - first;
       while (len > 0) {
           auto half = len / 2;
           RandomIt middle = first + half;
           if (comp(*middle, value)) {
               first = middle + 1;
               len = len - half - 1;
           } else {
               len = half;
           }
       }
       return first;
   }

   template <typename RandomIt, typename T, typename Compare = std::less<T>>
   RandomIt mini_upper_bound(RandomIt first, RandomIt last, const T& value, Compare comp = Compare{}) {
       auto len = last - first;
       while (len > 0) {
           auto half = len / 2;
           RandomIt middle = first + half;
           if (!comp(value, *middle)) {
               first = middle + 1;
               len = len - half - 1;
           } else {
               len = half;
           }
       }
       return first;
   }

   template <typename RandomIt, typename T, typename Compare = std::less<T>>
   std::pair<RandomIt, RandomIt> mini_equal_range(RandomIt first, RandomIt last, const T& value, Compare comp = Compare{}) {
       return {mini_lower_bound(first, last, value, comp),
               mini_upper_bound(first, last, value, comp)};
   }

   // =========================================================================
   // 2. 二叉堆算法族实现 (基于连续内存的大顶堆)
   // =========================================================================

   // 上滤算法: 将位于 holeIndex 处的元素向上渗透
   template <typename RandomIt, typename Distance, typename T, typename Compare>
   void __push_heap_aux(RandomIt first, Distance holeIndex, Distance topIndex, T value, Compare comp) {
       Distance parent = (holeIndex - 1) / 2;
       while (holeIndex > topIndex && comp(*(first + parent), value)) {
           *(first + holeIndex) = std::move(*(first + parent));
           holeIndex = parent;
           if (holeIndex == 0) break;
           parent = (holeIndex - 1) / 2;
       }
       *(first + holeIndex) = std::move(value);
   }

   template <typename RandomIt, typename Compare = std::less<typename std::iterator_traits<RandomIt>::value_type>>
   void mini_push_heap(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       using Distance = typename std::iterator_traits<RandomIt>::difference_type;
       using ValueType = typename std::iterator_traits<RandomIt>::value_type;
       Distance count = last - first;
       if (count > 1) {
           ValueType value = std::move(*(last - 1));
           __push_heap_aux(first, count - 1, Distance(0), std::move(value), comp);
       }
   }

   // 下滤算法: 将位于 holeIndex 处的空穴向下渗透
   template <typename RandomIt, typename Distance, typename T, typename Compare>
   void __adjust_heap(RandomIt first, Distance holeIndex, Distance len, T value, Compare comp) {
       Distance topIndex = holeIndex;
       Distance secondChild = 2 * holeIndex + 2;

       while (secondChild < len) {
           if (comp(*(first + secondChild), *(first + (secondChild - 1)))) {
               secondChild--;
           }
           *(first + holeIndex) = std::move(*(first + secondChild));
           holeIndex = secondChild;
           secondChild = 2 * (secondChild + 1);
       }
       if (secondChild == len) {
           *(first + holeIndex) = std::move(*(first + (secondChild - 1)));
           holeIndex = secondChild - 1;
       }
       __push_heap_aux(first, holeIndex, topIndex, std::move(value), comp);
   }

   template <typename RandomIt, typename Compare = std::less<typename std::iterator_traits<RandomIt>::value_type>>
   void mini_pop_heap(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       using Distance = typename std::iterator_traits<RandomIt>::difference_type;
       using ValueType = typename std::iterator_traits<RandomIt>::value_type;
       Distance count = last - first;
       if (count > 1) {
           ValueType value = std::move(*(last - 1));
           *(last - 1) = std::move(*first);
           __adjust_heap(first, Distance(0), count - 1, std::move(value), comp);
       }
   }

   template <typename RandomIt, typename Compare = std::less<typename std::iterator_traits<RandomIt>::value_type>>
   void mini_make_heap(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       using Distance = typename std::iterator_traits<RandomIt>::difference_type;
       using ValueType = typename std::iterator_traits<RandomIt>::value_type;
       Distance len = last - first;
       if (len < 2) return;

       Distance parent = (len - 2) / 2;
       while (true) {
           ValueType value = std::move(*(first + parent));
           __adjust_heap(first, parent, len, std::move(value), comp);
           if (parent == 0) return;
           parent--;
       }
   }

   template <typename RandomIt, typename Compare = std::less<typename std::iterator_traits<RandomIt>::value_type>>
   void mini_sort_heap(RandomIt first, RandomIt last, Compare comp = Compare{}) {
       while (last - first > 1) {
           mini_pop_heap(first, last, comp);
           --last;
       }
   }

   // =========================================================================
   // 3. 数值算法: 串行 accumulate 与分块并行 reduce
   // =========================================================================

   template <typename InputIt, typename T, typename BinaryOp = std::plus<T>>
   T mini_accumulate(InputIt first, InputIt last, T init, BinaryOp op = BinaryOp{}) {
       for (; first != last; ++first) {
           init = op(std::move(init), *first);
       }
       return init;
   }

   // 模拟 C++17 结合律可重排的二叉树分治并行归约
   template <typename RandomIt, typename T, typename BinaryOp = std::plus<T>>
   T mini_reduce(RandomIt first, RandomIt last, T init, BinaryOp op = BinaryOp{}) {
       auto len = last - first;
       if (len == 0) return init;
       if (len <= 4) { // 小块阈值: 展开为局部求和
           T acc = *first;
           for (auto it = first + 1; it != last; ++it) {
               acc = op(std::move(acc), *it);
           }
           return op(std::move(init), std::move(acc));
       }

       // 二叉树分治归约 (模拟多核与 SIMD 树状计算)
       auto mid = first + len / 2;
       T leftSum = mini_reduce(first, mid, T{}, op);
       T rightSum = mini_reduce(mid, last, T{}, op);
       return op(std::move(init), op(std::move(leftSum), std::move(rightSum)));
   }

   } // namespace generic_algo_engine

   // =========================================================================
   // 4. 端到端测试套件
   // =========================================================================
   namespace test {

   inline void runBinarySearchAndHeapTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 二分搜索、大顶堆操作与数值算法微架构测试套件
";
       std::cout << "=======================================================

";

       using namespace generic_algo_engine;

       // 1. 测试二分搜索族
       std::vector<int> sortedData = {10, 20, 20, 20, 30, 40, 50};
       std::cout << "[测试 1: 二分搜索收敛性]:
  序列: ";
       for (int v : sortedData) std::cout << v << " ";
       std::cout << "
";

       auto lb = mini_lower_bound(sortedData.begin(), sortedData.end(), 20);
       auto ub = mini_upper_bound(sortedData.begin(), sortedData.end(), 20);
       auto range = mini_equal_range(sortedData.begin(), sortedData.end(), 20);

       assert(lb - sortedData.begin() == 1);
       assert(ub - sortedData.begin() == 4);
       assert(range.first == lb && range.second == ub);
       std::cout << "  -> lower_bound(20) 索引 = " << (lb - sortedData.begin()) << " (元素: " << *lb << ")
";
       std::cout << "  -> upper_bound(20) 索引 = " << (ub - sortedData.begin()) << " (元素: " << *ub << ")
";
       std::cout << "  -> 等价区间长度 = " << (ub - lb) << " (全部通过)

";

       // 2. 测试线性建堆与堆排序
       std::vector<int> heapData = {15, 3, 42, 8, 23, 16, 99, 4};
       std::cout << "[测试 2: make_heap 线性建堆与堆排序]:
  原始乱序: ";
       for (int v : heapData) std::cout << v << " ";
       std::cout << "
";

       mini_make_heap(heapData.begin(), heapData.end());
       std::cout << "  建堆后 (根节点为最大值): ";
       for (int v : heapData) std::cout << v << " ";
       std::cout << "
";
       assert(heapData[0] == 99); // 大顶堆根必须为最大值

       // 插入新元素 105
       heapData.push_back(105);
       mini_push_heap(heapData.begin(), heapData.end());
       assert(heapData[0] == 105);
       std::cout << "  push_heap(105) 后根节点 = " << heapData[0] << "
";

       // 弹出最大值
       mini_pop_heap(heapData.begin(), heapData.end());
       assert(heapData.back() == 105);
       heapData.pop_back();
       assert(heapData[0] == 99);
       std::cout << "  pop_heap 后移除 105，新堆顶 = " << heapData[0] << "
";

       // 全量堆排序
       mini_sort_heap(heapData.begin(), heapData.end());
       std::cout << "  sort_heap 完成升序序列: ";
       for (int v : heapData) std::cout << v << " ";
       std::cout << "
";
       assert(std::is_sorted(heapData.begin(), heapData.end()));
       std::cout << "  -> 堆算法与堆排序断言完全正确。

";

       // 3. 测试数值算法
       std::vector<int64_t> numData(100);
       std::iota(numData.begin(), numData.end(), 1); // 1 到 100

       int64_t sumSeq = mini_accumulate(numData.begin(), numData.end(), int64_t(0));
       int64_t sumPar = mini_reduce(numData.begin(), numData.end(), int64_t(0));

       std::cout << "[测试 3: 数值归约 (1..100 求和)]:
";
       std::cout << "  mini_accumulate 结果 = " << sumSeq << "
";
       std::cout << "  mini_reduce     结果 = " << sumPar << "
";
       assert(sumSeq == 5050);
       assert(sumPar == 5050);
       std::cout << "  -> 串行与树状并行归约结果绝对一致。

";

       std::cout << "  -> 二分搜索、堆算法与数值归约验证全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了三大算法族的核心物理契约：

1. **二分收敛精准度**：在测试 1 中，面对包含连续重复元素的序列，``mini_lower_bound`` 与 ``mini_upper_bound`` 分别在 $\mathcal{O}(\log N)$ 次指针位移内精准收敛于等价区间的左闭界（索引 1）与右开界（索引 4），为有序容器与多重映射区间定位提供了坚实基石。
2. **堆不变量与原地排序**：在测试 2 中，``mini_make_heap`` 在 $\mathcal{O}(N)$ 线性时间内将乱序数组重构为满足堆序性的大顶堆，根节点瞬时上浮为 99。随后的 ``mini_sort_heap`` 通过连续 $N$ 次堆顶交换与下滤，在零额外堆内存分配的前提下原址达成了升序序列。
3. **数值归约等价性**：在测试 3 中，针对 $1 \sim 100$ 的求和，树状分治的 ``mini_reduce`` 成功解除了顺序依赖，计算结果与严格串行左折叠的 ``mini_accumulate`` 保持完全一致（5050），证明了在满足结合律时并行展开的安全性。

小结与下章导读
--------------

本章系统解构了现代 C++ STL 在二分检索、完全二叉堆与数值归约领域的算法精髓：

1. **二分搜索族收敛状态机**：剖析了 ``lower_bound``、``upper_bound`` 与 ``equal_range`` 的边界判定契约，阐释了随机访问迭代器（对数级指针位移）与前向迭代器（线性级跳转）的底层性能代沟。
2. **完全二叉堆物理模型**：推导了基于平铺数组的父子节点代数映射，严格证明了自底向上 ``make_heap`` 的 $\mathcal{O}(N)$ 线性建堆时间复杂度。
3. **数值归约模型演进**：对比了 C++98 ``std::accumulate`` 严格串行左折叠的确定性与 C++17 ``std::reduce`` 基于结合律/交换律的树状并行分治模型。

本章的完工标志着 **第 5 模块（泛型算法、双指针与内省排序）全量圆满收官**。在接下来的 **第 6 模块：可调用对象、类型擦除与模板元编程 (06_callables_and_template_metaprogramming)** 中，我们将步入现代 C++ 最具表现力的高阶抽象内核。在第 6 模块第 1 节 **仿函数与 Lambda 闭包机制：operator() 重载、编译器生成闭包类、捕获列表内存布局与泛型 lambda（``06_callables_and_template_metaprogramming/01_function_objects_and_lambda_closures.rst``）** 中，我们将深入剖析可调用对象（Callables）的重载决议、编译器为 Lambda 表达式生成的匿名闭包类结构、值捕获与引用捕获在栈帧中的物理排布，以及 C++14/C++20 泛型 Lambda 与模板参数包的底层生成机理。
