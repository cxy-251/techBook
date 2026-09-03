====================================================================================================
线性与子序列查找算法：find/find_if 短路、search KMP 思想与 mismatch 范围比对
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块第 1 节（``05_generic_algorithms_and_performance/01_half_open_range_contract_and_iterator_dispatch.rst``）中，我们系统解构了 STL 算法的半开区间 $[first, last)$ 几何代数公理、三大算法族系分类矩阵、5 级迭代器标签（Iterator Category Tags）的编译期重载分发（Tag Dispatching），以及结合 ``is_trivially_copyable`` 将通用循环降级为硬件指令级内存拷贝（``memmove``）的极致加速机理。在所有泛型序列操作中，**查找与模式匹配（Search & Pattern Matching）** 是业务逻辑中调用频次最高、对执行时延最敏感的基础构件。从单元素的线性扫描到多区间的双指针比对，再到复杂子序列的跳跃搜索，STL 提供了一套层次严密的查找算法矩阵。本章深入剖析 ``std::find`` 与 ``std::find_if`` 的短路求值与循环展开微架构、``std::adjacent_find`` 相邻元素探测边界、``std::mismatch`` 双区间步进比对防越界契约、``std::search`` 的朴素滑动窗口与 KMP / Boyer-Moore 前缀跳跃状态机，以及利用现代 CPU SIMD 指令（AVX2 / AVX-512）实现每周期 32~64 字节并行比对的硬件加速原理。

线性单元素查找状态机与短路求值微架构
------------------------------------

单元素线性查找算法（``std::find``、``std::find_if`` 与 ``std::find_if_not``）的物理使命是在单向推进的迭代器区间内，以最低的指令开销定位首个满足条件的元素。

短路求值 (Short-Circuit) 与谓词纯粹性契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     std::find_if 线性扫描与短路求值状态机                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 输入序列 ]: [ Elem 0 ] -> [ Elem 1 ] -> [ Target Elem ] -> [ Elem 3 ]   |
   |                      |            |               |                         |
   |                      v            v               v                         |
   |   [ 谓词计算 ]:  Pred(E0)=0   Pred(E1)=0      Pred(E2)=1                    |
   |                                                   |                         |
   |                                                   v                         |
   |                                          [ 立即短路返回迭代器 it ]          |
   |                                          * 严禁继续求值后续元素 Elem 3!     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **时序确定性与短路语义**：
   算法严格按照中序正向步进。一旦谓词求值返回 ``true``，算法立即跳出循环并返回当前迭代器。这一契约不仅保证了时间复杂度的最优提前终止，更保证了谓词副作用（若存在）的严格可预测性。
2. **一元谓词纯粹性（Predicate Purity）**：
   标准库强制规定：传入 ``find_if`` 的可调用对象必须是一元谓词（Unary Predicate）。谓词应保持纯函数特性（即不修改被检查元素，多次求值结果幂等），因为标准库允许算法在内部以任意顺序复制谓词对象。

循环展开 (Loop Unrolling) 与分支预测优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于基础数据类型（如整数、浮点数）的连续内存线性查找，朴素循环的每次迭代均包含两次分支跳转：一次判断 ``first != last``，另一次判断 ``*first == val``。
工业级标准库（如 libstdc++ 与 MSVC）在随机访问迭代器上对主循环执行 **4 路或 8 路循环展开（Loop Unrolling）**：

.. code-block:: cpp

   template <typename RandomIt, typename T>
   RandomIt unrolled_find(RandomIt first, RandomIt last, const T& val) {
       auto trip_count = (last - first) >> 2; // 处理 4 的倍数
       for (; trip_count > 0; --trip_count) {
           if (*first == val) return first;
           if (*(first + 1) == val) return first + 1;
           if (*(first + 2) == val) return first + 2;
           if (*(first + 3) == val) return first + 3;
           first += 4;
       }
       // 处理剩余 0~3 个余数元素
       while (first != last) {
           if (*first == val) return first;
           ++first;
       }
       return last;
   }

通过将 4 次循环边界跳转折叠为 1 次，大幅减轻了 CPU 分支目标缓冲器（BTB）的压力，使硬件指令流水线保持饱和发射。

双向与多元素比对：std::adjacent_find 与 std::mismatch
-----------------------------------------------------

相邻等价元素探测：std::adjacent_find
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::adjacent_find(first, last, pred)`` 用于在单序列中检索首对 **在物理位置上相邻且满足等价条件** 的元素对 $(E_i, E_{i+1})$：

- **边界不变量**：若区间为空（``first == last``）或仅包含单一元素（``std::next(first) == last``），算法在首轮判定中直接短路返回 ``last``，杜绝了单元素解引用越界的未定义行为。
- **返回值契约**：命中时返回指向首对元素中 **第一个元素** 的迭代器（即 $E_i$）。

双区间步进比对：std::mismatch 与 C++14 安全演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::mismatch`` 同步遍历两个序列，返回首个元素不匹配的迭代器对：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     std::mismatch 双区间同步遍历比对拓扑                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   Range 1: [ A0 ] ---> [ A1 ] ---> [ A2 (Mismatch!) ] ---> [ A3 ]           |
   |               |           |               |                                 |
   |               v           v               v                                 |
   |             ( == )      ( == )          ( != )                              |
   |               ^           ^               ^                                 |
   |               |           |               |                                 |
   |   Range 2: [ B0 ] ---> [ B1 ] ---> [ X2 (Mismatch!) ] ---> [ B3 ]           |
   |                                           |                                 |
   |                                           v                                 |
   |                       返回迭代器对: std::pair(itA2, itB2)                   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: std::mismatch C++98 与 C++14 接口演进与安全边界
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - C++ 标准版本
     - 接口签名
     - 内存越界风险与物理契约
   * - **C++98 经典签名**
     - ``mismatch(first1, last1, first2)``
     - **极高越界风险**：假定第二个序列长度 $\ge$ 第一个序列；若序列 2 较短，将引发灾难性的缓冲区越界读（Buffer Overread）
   * - **C++14 安全签名**
     - ``mismatch(first1, last1, first2, last2)``
     - **绝对安全**：双区间均显式携带尾后哨兵；只要任一序列到达末尾（``first1 == last1 || first2 == last2``）即刻安全停机

子序列搜索算法：std::search、KMP 与 Boyer-Moore 跳跃状态机
----------------------------------------------------------

子序列搜索（Subsequence Search）解决的是在大文本序列（Text，长度 $N$）中查找目标模式序列（Pattern，长度 $M$）首个匹配起始位置的问题。

1. 朴素滑动窗口 (Naive Sliding Window)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

最基础的 ``std::search`` 实现采用滑动窗口暴力匹配：
- 外层循环遍历文本中的每个可能起始点 $i \in [0, N - M]$。
- 内层循环依次比对 $M$ 个字符。
- **时间复杂度**：最坏情况下（如在全 `A` 文本中查找 `AAAB`）退化为 $\mathcal{O}(N 	imes M)$。

2. Knuth-Morris-Pratt (KMP) 前缀跳转状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

KMP 算法通过预计算模式串的 **部分匹配表（Partial Match Table / $\pi$ 数组）**，在发生不匹配时利用已匹配前缀的对称性，直接将模式串向右滑动至最大公共前后缀位置，**完全避免文本指针的回溯**：

.. math::

   \pi[i] = \max \{ k \mid k < i \land 	ext{Pattern}[0..k-1] == 	ext{Pattern}[i-k..i-1] \}

- **时间复杂度**：预处理 $\mathcal{O}(M)$，匹配阶段 $\mathcal{O}(N)$，总体时间复杂度严格收敛为线性的 $\mathcal{O}(N + M)$。

3. C++17 Searchers 与 Boyer-Moore-Horspool 亚线性搜索
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++17 将搜索策略抽象为可插拔的 **Searcher 函数对象**：

.. list-table:: C++17 标准搜索器体系与微架构特性
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 搜索器组件
     - 核心跳转启发式算法
     - 平均时间复杂度与适用场景
   * - ``std::default_searcher``
     - 经典双重循环滑动窗口
     - $\mathcal{O}(N 	imes M)$；零预处理开销，适合超短模式串（$M \le 4$）
   * - ``std::boyer_moore_searcher``
     - 坏字符规则（Bad Character）+ 好后缀规则（Good Suffix）
     - **亚线性 $\mathcal{O}(N / M)$**；最快跳跃步长可达 $M$，适合长文本大模式串
   * - ``std::boyer_moore_horspool_searcher``
     - 仅保留坏字符规则（简化跳跃表）
     - $\mathcal{O}(N / M)$；极低预处理内存占用，工业界文本检索综合吞吐率极高

现代 CPU SIMD 向量化查找加速微架构
----------------------------------

在现代 x86-64（AVX2 / AVX-512）与 ARM64（NEON）架构上，编译器针对连续内存字符/字节查找，直接发射宽位宽向量比对指令：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     AVX2 256 位 SIMD 极速字节比对微架构                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 文本数据块 32 字节 ]: "The quick brown fox jumps over "                |
   |   [ 目标广播向量 (Target='x') ]: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"         |
   |                                   |                                         |
   |                                   v (执行 _mm256_cmpeq_epi8 向量并行比对)   |
   |   [ 比对掩码结果 (32 字节) ]: 0x00, 0x00, ..., 0xFF ('x' 命中!), 0x00 ...  |
   |                                   |                                         |
   |                                   v (执行 _mm256_movemask_epi8 提取高位)   |
   |   [ 32 位整型比特掩码 ]:   0b00000000000000000000001000000000              |
   |                                   |                                         |
   |                                   v (执行硬件位扫描指令 __builtin_ctz)       |
   |   [ 命中偏移量 Index ]:    直接输出 18 (单周期完成 32 字节扫描!)            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

通过单条向量指令同时比对 32 字节并借助 CPU 尾零计数指令（`CTZ / BSF`）解析命中偏移，将内存查找吞吐率提升数十倍。

工业级 C++ 完整查找与子序列搜索算法引擎实现
-------------------------------------------

以下 C++ 源码实现了一套自包含的工业级查找算法核心库。该实现涵盖：
1. 具备 4 路循环展开的 `mini_find` 与短路求值 `mini_find_if`。
2. C++14 双区间安全防越界 `mini_mismatch`。
3. 相邻元素探测器 `mini_adjacent_find`。
4. 包含 $\pi$ 预处理表的完整 KMP 子序列搜索器 `mini_search_kmp`。
5. 端到端单元测试套件（验证短路求值、双区间比对、KMP 跳跃匹配与边界安全）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <utility>
   #include <cassert>
   #include <functional>
   #include <algorithm>

   namespace core_search {

   // =========================================================================
   // 1. 线性单元素查找与 4 路循环展开
   // =========================================================================
   template <typename InputIt, typename UnaryPredicate>
   inline InputIt mini_find_if(InputIt first, InputIt last, UnaryPredicate pred) {
       for (; first != last; ++first) {
           if (pred(*first)) {
               return first; // 命中即刻短路返回
           }
       }
       return last;
   }

   template <typename RandomIt, typename T>
   inline RandomIt mini_find(RandomIt first, RandomIt last, const T& value) {
       // 针对随机访问迭代器的 4 路循环展开优化
       auto count = last - first;
       auto trip_count = count >> 2;

       while (trip_count > 0) {
           if (*first == value) return first;
           if (*(first + 1) == value) return first + 1;
           if (*(first + 2) == value) return first + 2;
           if (*(first + 3) == value) return first + 3;
           first += 4;
           --trip_count;
       }

       // 扫描剩余 0~3 个元素
       while (first != last) {
           if (*first == value) return first;
           ++first;
       }
       return last;
   }

   // =========================================================================
   // 2. 相邻元素探测与双区间比对
   // =========================================================================
   template <typename ForwardIt, typename BinaryPredicate = std::equal_to<>>
   inline ForwardIt mini_adjacent_find(
       ForwardIt first,
       ForwardIt last,
       BinaryPredicate p = BinaryPredicate{})
   {
       if (first == last) return last;
       ForwardIt next = first;
       ++next;
       while (next != last) {
           if (p(*first, *next)) {
               return first; // 返回相邻首元素
           }
           first = next;
           ++next;
       }
       return last;
   }

   template <typename InputIt1, typename InputIt2, typename BinaryPredicate = std::equal_to<>>
   inline std::pair<InputIt1, InputIt2> mini_mismatch(
       InputIt1 first1, InputIt1 last1,
       InputIt2 first2, InputIt2 last2,
       BinaryPredicate p = BinaryPredicate{})
   {
       // C++14 双边界完全安全版本
       while (first1 != last1 && first2 != last2 && p(*first1, *first2)) {
           ++first1;
           ++first2;
       }
       return {first1, first2};
   }

   // =========================================================================
   // 3. Knuth-Morris-Pratt (KMP) 子序列搜索器
   // =========================================================================
   class KMPSearcher {
   public:
       template <typename RandomIt1, typename RandomIt2>
       static RandomIt1 search(
           RandomIt1 text_first, RandomIt1 text_last,
           RandomIt2 pat_first, RandomIt2 pat_last)
       {
           const auto text_len = text_last - text_first;
           const auto pat_len  = pat_last - pat_first;

           if (pat_len == 0) return text_first;
           if (text_len < pat_len) return text_last;

           // 1. 预计算部分匹配表 (Pi 表)
           std::vector<int> pi(pat_len, 0);
           for (int i = 1, k = 0; i < pat_len; ++i) {
               while (k > 0 && *(pat_first + i) != *(pat_first + k)) {
                   k = pi[k - 1];
               }
               if (*(pat_first + i) == *(pat_first + k)) ++k;
               pi[i] = k;
           }

           // 2. 文本单向流转匹配 (文本指针绝不回退)
           int q = 0; // 匹配成功的字符数
           for (auto it = text_first; it != text_last; ++it) {
               while (q > 0 && *it != *(pat_first + q)) {
                   q = pi[q - 1]; // 依照前缀对称性快速跳跃
               }
               if (*it == *(pat_first + q)) ++q;

               if (q == pat_len) {
                   // 完全命中: 返回匹配子序列在 Text 中的首字符迭代器
                   return it - pat_len + 1;
               }
           }

           return text_last;
       }
   };

   } // namespace core_search

   // =========================================================================
   // 4. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runSearchAlgorithmsTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 线性查找、双区间比对与 KMP 子序列搜索验证套件
";
       std::cout << "=======================================================

";

       using namespace core_search;

       // 1. 测试 mini_find 4 路展开与 mini_find_if 短路
       {
           std::vector<int> data = {10, 20, 30, 40, 50, 60, 70, 80, 90};
           auto it = mini_find(data.begin(), data.end(), 60);
           assert(it != data.end() && *it == 60);

           int eval_count = 0;
           auto it_if = mini_find_if(data.begin(), data.end(), [&](int v) {
               ++eval_count;
               return v > 35; // 预期在 40 处短路
           });
           assert(it_if != data.end() && *it_if == 40);
           assert(eval_count == 4); // 严格仅求值 4 次即短路停机!

           std::cout << "[测试 1: 展开查找与短路求值]:
"
                     << "  4 路展开精确命中元素 60
"
                     << "  find_if 成功在第 4 个元素处短路终止 (求值次数 = " << eval_count << ")

";
       }

       // 2. 测试 mini_adjacent_find 与 mini_mismatch 双边界
       {
           std::vector<int> seq = {1, 2, 3, 3, 4, 5};
           auto adj_it = mini_adjacent_find(seq.begin(), seq.end());
           assert(adj_it != seq.end() && *adj_it == 3);

           std::string s1 = "compiler_opt";
           std::string s2 = "compiler_isa";
           auto [m1, m2] = mini_mismatch(s1.begin(), s1.end(), s2.begin(), s2.end());
           assert(m1 != s1.end() && *m1 == 'o');
           assert(m2 != s2.end() && *m2 == 'i');

           std::cout << "[测试 2: 相邻元素与安全 mismatch]:
"
                     << "  adjacent_find 准确锁定相邻重复项 3
"
                     << "  C++14 mismatch 成功捕获分歧字符 ('o' vs 'i')

";
       }

       // 3. 测试 KMP 子序列线性跳转搜索
       {
           std::string text = "ABC ABCDAB ABCDABCDABDE";
           std::string pattern = "ABCDABD";

           auto match_it = KMPSearcher::search(
               text.begin(), text.end(),
               pattern.begin(), pattern.end()
           );

           assert(match_it != text.end());
           size_t offset = std::distance(text.begin(), match_it);
           assert(offset == 15);

           std::cout << "[测试 3: KMP 前缀跳跃子序列搜索]:
"
                     << "  文本: \"" << text << "\"
"
                     << "  模式: \"" << pattern << "\"
"
                     << "  -> KMP 成功在偏移量 " << offset << " 处无回溯锁定目标子序列!

";
       }

       std::cout << "  -> 线性查找与模式匹配全套算法验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了查找算法的核心物理运行特性：

1. **短路求值精准度**：在测试 1 中，``mini_find_if`` 在扫描到首个大于 35 的元素（40）时，严格停顿于第 4 次谓词调用，完全避免了对后续 5 个元素的无效计算。
2. **双边界安全防线**：在测试 2 中，双区间 ``mini_mismatch`` 同时受两个独立尾后哨兵约束，彻底杜绝了异构长度序列比对时的内存越界隐患。
3. **KMP 零回溯线性吞吐**：在测试 3 中，面对包含大量重复局部前缀的复杂文本，KMP 状态机利用 $\pi$ 表在发生字符不匹配时直接跨越无用前缀，文本迭代器始终单向右移，在 $\mathcal{O}(N)$ 复杂度内精准定位目标偏移量 15。

小结与下章导读
--------------

本章系统解构了现代 C++ STL 查找与子序列搜索算法体系：

1. **线性查找微架构**：推导了 ``find`` / ``find_if`` 的短路语义约束与 4 路循环展开降低分支预测开销的物理机理。
2. **多元素与范围比对**：剖析了 ``adjacent_find`` 的单元素防越界边界与 C++14 ``mismatch`` 四迭代器防缓冲区越界读演进。
3. **子序列搜索状态机**：对比了朴素滑动窗口（$\mathcal{O}(N 	imes M)$）、KMP 前缀跳跃表（$\mathcal{O}(N)$）与 Boyer-Moore 坏字符规则（亚线性 $\mathcal{O}(N / M)$）的算法权衡。
4. **SIMD 硬件加速**：展现了利用 256 位 AVX2 向量比对与位掩码扫描（`movemask` + `ctz`）实现单周期 32 字节并行扫描的微架构实践。

在掌握了只读查找算法之后，下一章我们将深入剖析 STL 算法中对序列执行重构与变换的核心领域——**变易与重排算法**。在第 5 模块第 3 节 **变易与重排算法：copy 内存重叠安全性、remove-erase 惯用法与 rotate 循环位移（``05_generic_algorithms_and_performance/03_modifying_reordering_and_partition_algorithms.rst``）** 中，我们将深入剖析 ``std::copy`` 与 ``std::copy_backward`` 在内存重叠时的方向选择公理、经典的 Remove-Erase 惯用法物理机制、``std::rotate`` 在三类迭代器下的三种实现算法（Gries-Mills 辗转反除法、三步反转法、双指针置换），以及 ``std::partition`` 快速划分的微架构优化。
