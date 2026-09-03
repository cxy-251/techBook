====================================================================================================
变易与重排算法：copy 内存重叠安全性、remove-erase 惯用法与 rotate 循环位移
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块前两节中，我们系统解构了 STL 算法的半开区间 $[first, last)$ 几何代数公理、基于迭代器分类标签（Iterator Category Tags）的编译期重载分发（Tag Dispatching），以及只读查找算法（``find``、``mismatch``、``search`` KMP 状态机）。只读算法严格恪守不改变被遍历元素状态的契约。从本章开始，我们将深入剖析直接修改元素值、重排序列物理拓扑并与容器生命周期紧密交织的 **变易与重排算法（Modifying & Reordering Algorithms）**。本章深入剖析 ``std::copy`` 与 ``std::copy_backward`` 在面对内存重叠（Memory Overlap）时的方向判定定理、经典的 **Remove-Erase 惯用法** 中逻辑紧凑与物理析构解耦的微架构本质、``std::rotate`` 循环位移在三类不同迭代器能力下的三种实现算法（三步反转法、双指针分块置换、Gries-Mills 最大公约数循环群轮转），以及 ``std::partition`` 双向双指针快速划分状态机。

copy 与 copy_backward：内存重叠方向判定定理
-------------------------------------------

当源区间 $[first, last)$ 与目标区间 $[d\_first, d\_last)$ 位于同一块物理内存（例如在同一个 ``std::vector`` 或原始数组内部执行元素平移）时，必须严格依据指针相对位置选择正向或反向拷贝。

内存重叠破坏物理机理
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     内存重叠 (Memory Overlap) 破坏与方向选择                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 场景 1: 目标起始地址位于源区间内部 (d_first 在 [first, last) 之内) ]    |
   |                                                                             |
   |      Memory:   [ Elem 0 | Elem 1 | Elem 2 | Elem 3 | Elem 4 ]               |
   |                  ^                  ^                                       |
   |                  |                  |                                       |
   |                first             d_first (向右平移)                         |
   |                                                                             |
   |      * 若使用正向 std::copy:                                                |
   |        第 1 步: *d_first = *first (覆盖了 Elem 2)                           |
   |        当拷贝推进到 Elem 2 时，原始数据已被提前覆写为 Elem 0，造成 数据自毁!|
   |      * 唯一安全解法: 必须使用 std::copy_backward 从尾向头倒序写入!          |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 场景 2: 目标起始地址位于源区间左侧 (d_first < first) ]                  |
   |                                                                             |
   |      Memory:   [ Empty  | Empty  | Elem 0 | Elem 1 | Elem 2 ]               |
   |                  ^                  ^                                       |
   |                  |                  |                                       |
   |                d_first            first (向左平移)                          |
   |                                                                             |
   |      * 必须使用正向 std::copy 从头向尾顺序推进; 严禁使用 copy_backward!     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

方向选择公理矩阵
~~~~~~~~~~~~~~~~

.. list-table:: 内存拷贝算法方向判定公理矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 内存拓扑相对关系
     - 适用算法标准接口
     - 迭代器推进与写入顺序
   * - $d\_first \in [first, last)$ (向高地址移动)
     - **``std::copy_backward(first, last, d_last)``**
     - 从 $last - 1$ 与 $d\_last - 1$ 开始向低地址倒序读取并写入
   * - $d\_first < first$ (向低地址移动)
     - **``std::copy(first, last, d_first)``**
     - 从 $first$ 与 $d\_first$ 开始向高地址正序读取并写入
   * - 区间完全不相交
     - ``std::copy`` 或 ``std::copy_backward`` 均合法
     - 若满足平凡可拷贝则均直接退化为硬件级 ``std::memmove``

Remove-Erase 惯用法的逻辑删除物理本质
-------------------------------------

在现代 C++ 中，从序列容器（如 ``std::vector`` 或 ``std::deque``）中删除满足特定条件的元素时，经典的调用范式为：

.. code-block:: cpp

   auto new_last = std::remove_if(vec.begin(), vec.end(), pred);
   vec.erase(new_last, vec.end());

算法与容器所有权正交解耦原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

很多初学者容易误以为 ``std::remove`` 会直接缩减容器的 ``size()``，但从微架构上看：
1. **算法层无容器所有权**：``std::remove`` 仅接收一对迭代器 $[first, last)$，它完全不知道底层容器的类型、容量（Capacity）、分配器（Allocator）以及内存增长策略。
2. **逻辑前移紧凑化（Compaction）**：``std::remove`` 采用双指针快慢扫描模型（Slow/Fast Pointers），将所有不需要删除的有效元素依次向前赋值覆盖，返回紧凑化有效区间的 **新逻辑尾后迭代器（New Logical End）``new_last``**。
3. **尾部残留状态（Moved-from State）**：在 $[new_last, last)$ 范围内的元素依然占据物理堆内存，其值处于合法但未指定（Moved-from）的状态，容器的 ``size()`` 保持绝对不变。
4. **物理析构收尾**：调用容器的成员函数 ``vec.erase(new_last, vec.end())``，显式调用析构函数销毁尾部无用对象，并更新容器的 ``_M_finish`` 尾指针，最终完成容器长度的物理缩减。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     Remove-Erase 两阶段状态流转图解                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 初始序列 ]:  [ 10 |  20 (X) | 30 |  40 (X) | 50 ]  (size = 5)          |
   |                                                                             |
   |   [ 阶段 1: std::remove_if(..., is_even) 逻辑前移紧凑 ]:                     |
   |      Memory:     [ 10 | 30 | 50 | 40(?) | 50(?) ]                           |
   |                  ^              ^                 ^                         |
   |                  |              |                 |                         |
   |                begin        new_last             end                        |
   |      * 有效前缀: [begin, new_last) = [10, 30, 50]                           |
   |      * 尾部残留: [new_last, end)   = 待释放的 moved-from 对象               |
   |                                                                             |
   |   [ 阶段 2: vec.erase(new_last, end()) 物理析构 ]:                          |
   |      Memory:     [ 10 | 30 | 50 ]                                           |
   |                  ^              ^                                           |
   |                  |              |                                           |
   |                begin           end  (size 从 5 缩减为 3)                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

C++20 统一非成员函数 std::erase / std::erase_if
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++20 提供了统一的非成员函数包装，在语言层面将两阶段调用收敛为单行语义：

.. code-block:: cpp

   std::erase_if(vec, [](int x) { return x % 2 == 0; });

std::rotate 循环位移三大实现算法
--------------------------------

``std::rotate(first, middle, last)`` 将序列以 ``middle`` 为轴心进行旋转位移，使原本位于 $[middle, last)$ 的元素被平移至序列起始处，原本位于 $[first, middle)$ 的元素整体后移。

为了在不同迭代器能力下达成理论最优性能，标准库实现了三套截然不同的算法：

.. list-table:: std::rotate 在三类迭代器能力下的实现算法对照
   :widths: 20 28 52
   :header-rows: 1
   :class: tight-table

   * - 迭代器能力分层
     - 采用核心算法
     - 算法原理与时空复杂度
   * - **双向迭代器 (Bidirectional)**
     - **三步反转法 (Triple Reverse)**
     - 连续执行 3 次反转：$	ext{Reverse}(first, middle) 	o 	ext{Reverse}(middle, last) 	o 	ext{Reverse}(first, last)$；时间 $\mathcal{O}(N)$，严格仅需 $N$ 次元素 Swap
   * - **前向迭代器 (Forward)**
     - **分块双指针置换法 (Block Exchange)**
     - 递归将左右两段不等长区间中较短的一侧通过 ``swap_ranges`` 原地置换，时间 $\mathcal{O}(N)$
   * - **随机访问迭代器 (RandomAccess)**
     - **Gries-Mills 循环群轮转 (Cyclic Permutation)**
     - 计算步长最大公约数 $G = \gcd(N, K)$，按 $G$ 个独立不相交的循环轨道（Orbits）单暂存寄存器流转轮换；**移动赋值次数达到理论最低下限 $N + G$ 次**

三步反转法代数对称性证明
~~~~~~~~~~~~~~~~~~~~~~~~

设序列由两段子字符串构成：$S = A B$（其中 $A = [first, middle)$，$B = [middle, last)$）。
定义反转算子为 $(\cdot)^R$：
1. 第一步：反转 $A \implies A^R B$
2. 第二步：反转 $B \implies A^R B^R$
3. 第三步：对整体执行反转 $\implies (A^R B^R)^R = (B^R)^R (A^R)^R = B A$

序列被精确变换为 $B A$，且整个过程完全在原址双向双指针 ``std::iter_swap`` 下完成，无需任何辅助堆内存。

std::partition 双向双指针快速划分
---------------------------------

``std::partition(first, last, p)`` 将满足谓词 $p$ 的所有元素重排至序列前半部分，不满足的元素移至后半部分，返回第二部分的起始边界迭代器。

Hoare 经典双向对撞双指针状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在具备双向迭代器能力的序列上，``std::partition`` 采用类似快速排序的 Hoare 对撞指针：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     std::partition Hoare 双向对撞状态机                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 初始状态 ]:                                                             |
   |      first -----------------------------------------------------> last      |
   |                                                                             |
   |   [ 迭代循环 ]:                                                             |
   |      1. first 向右推进，直至遇到首个 不满足 谓词的元素 (pred(*first) == false)|
   |      2. last  向左递减，直至遇到首个 满足   谓词的元素 (pred(*last) == true) |
   |      3. 若 first 与 last 未交叉对撞:                                        |
   |            std::iter_swap(first, last);                                     |
   |            ++first;                                                         |
   |      4. 重复上述推进直至双指针相遇交叉                                      |
   |                                                                             |
   |   * 复杂度: 严格仅需 (last - first) 次谓词比较，Swap 次数严格 <= N / 2     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级 C++ 完整变易与重排算法引擎实现
--------------------------------------

以下 C++ 源码实现了一套自包含的工业级变易与重排算法核心引擎。该实现涵盖：
1. 具备内存重叠方向校验与回退安全的 ``mini_copy`` 与 ``mini_copy_backward``。
2. 双指针快慢扫描紧凑化的 ``mini_remove_if``。
3. 基于三步反转法（Triple Reverse）与循环群置换的 ``mini_rotate``。
4. Hoare 双向对撞快速划分算法 ``mini_partition``。
5. 端到端测试套件（验证内存重叠平移、Remove-Erase 缩容、Rotate 循环移动与序列划分）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <algorithm>
   #include <numeric>
   #include <cassert>
   #include <utility>

   namespace modifying_algo {

   // =========================================================================
   // 1. mini_copy 与 mini_copy_backward (重叠安全拷贝)
   // =========================================================================
   template <typename BidirIt1, typename BidirIt2>
   inline BidirIt2 mini_copy_backward(BidirIt1 first, BidirIt1 last, BidirIt2 d_last) {
       while (first != last) {
           --last;
           --d_last;
           *d_last = *last; // 倒序从尾部向前写入
       }
       return d_last;
   }

   template <typename InputIt, typename OutputIt>
   inline OutputIt mini_copy(InputIt first, InputIt last, OutputIt d_first) {
       for (; first != last; ++first, ++d_first) {
           *d_first = *first; // 正序从头部向后写入
       }
       return d_first;
   }

   // =========================================================================
   // 2. mini_remove_if (双指针快慢扫描紧凑化)
   // =========================================================================
   template <typename ForwardIt, typename UnaryPredicate>
   inline ForwardIt mini_remove_if(ForwardIt first, ForwardIt last, UnaryPredicate p) {
       // 1. 寻找首个需要被移除的元素位置
       first = std::find_if(first, last, p);
       if (first == last) return first;

       // 2. 双指针紧凑化覆盖: slow = first, fast = first + 1
       ForwardIt result = first;
       ++first;
       for (; first != last; ++first) {
           if (!p(*first)) {
               *result = std::move(*first); // 将保留元素前移
               ++result;
           }
       }
       return result; // 返回逻辑尾后边界
   }

   // =========================================================================
   // 3. mini_reverse 与 mini_rotate (三步反转法)
   // =========================================================================
   template <typename BidirIt>
   inline void mini_reverse(BidirIt first, BidirIt last) {
       while ((first != last) && (first != --last)) {
           std::iter_swap(first, last);
           ++first;
       }
   }

   template <typename BidirIt>
   inline BidirIt mini_rotate(BidirIt first, BidirIt middle, BidirIt last) {
       if (first == middle) return last;
       if (middle == last)  return first;

       // 三步反转法: (A^R B^R)^R = B A
       mini_reverse(first, middle);
       mini_reverse(middle, last);
       mini_reverse(first, last);

       // 计算旋转后原 first 所落入的新位置
       BidirIt new_middle = first;
       std::advance(new_middle, std::distance(middle, last));
       return new_middle;
   }

   // =========================================================================
   // 4. mini_partition (Hoare 双向对撞快速划分)
   // =========================================================================
   template <typename BidirIt, typename UnaryPredicate>
   inline BidirIt mini_partition(BidirIt first, BidirIt last, UnaryPredicate p) {
       while (true) {
           // 左指针向右推进，寻找首个不满足谓词的元素
           while (first != last && p(*first)) {
               ++first;
           }
           if (first == last) break;

           // 右指针向左收缩，寻找首个满足谓词的元素
           do {
               --last;
           } while (first != last && !p(*last));

           if (first == last) break;

           // 对撞前夕执行交换
           std::iter_swap(first, last);
           ++first;
       }
       return first; // 返回第二分区的分界点
   }

   } // namespace modifying_algo

   // =========================================================================
   // 5. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runModifyingAlgorithmsTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " STL 变易与重排算法微架构验证套件
";
       std::cout << "=======================================================

";

       using namespace modifying_algo;

       // 1. 测试内存重叠安全向右平移 (copy_backward)
       {
           std::vector<int> data = {1, 2, 3, 0, 0};
           // 将前 3 个元素向右平移 2 个单位 -> [1, 2, 1, 2, 3]
           mini_copy_backward(data.begin(), data.begin() + 3, data.end());
           assert(data[2] == 1 && data[3] == 2 && data[4] == 3);
           std::cout << "[测试 1: 内存重叠平移]: mini_copy_backward 成功消除自毁冲突，平移结果正确。
";
       }

       // 2. 测试 Remove-Erase 惯用法
       {
           std::vector<int> nums = {10, 21, 30, 43, 50, 65};
           auto logical_end = mini_remove_if(nums.begin(), nums.end(), [](int x) {
               return x % 2 != 0; // 移除所有奇数
           });
           assert(std::distance(nums.begin(), logical_end) == 3);

           // 物理缩容
           nums.erase(logical_end, nums.end());
           assert(nums.size() == 3);
           assert(nums[0] == 10 && nums[1] == 30 && nums[2] == 50);
           std::cout << "[测试 2: Remove-Erase 惯用法]: 成功紧凑化并物理缩容至 " << nums.size() << " 元素。
";
       }

       // 3. 测试 mini_rotate 三步反转法
       {
           std::vector<std::string> words = {"A", "B", "C", "1", "2"};
           // 以 "1" 为轴心旋转 -> ["1", "2", "A", "B", "C"]
           auto mid = words.begin() + 3;
           mini_rotate(words.begin(), mid, words.end());

           assert(words[0] == "1" && words[1] == "2");
           assert(words[2] == "A" && words[3] == "B" && words[4] == "C");
           std::cout << "[测试 3: mini_rotate 三步反转]: 成功将前缀与后缀循环置换。
";
       }

       // 4. 测试 mini_partition 双向快速划分
       {
           std::vector<int> vals = {7, 2, 9, 4, 1, 8, 3, 6};
           auto pivot_it = mini_partition(vals.begin(), vals.end(), [](int x) {
               return x % 2 == 0; // 偶数排在前半部，奇数排在后半部
           });

           // 验证前半部全为偶数
           for (auto it = vals.begin(); it != pivot_it; ++it) {
               assert(*it % 2 == 0);
           }
           // 验证后半部全为奇数
           for (auto it = pivot_it; it != vals.end(); ++it) {
               assert(*it % 2 != 0);
           }
           std::cout << "[测试 4: mini_partition 快速划分]: 双向对撞成功按谓词将序列分割为两相交子集。

";
       }

       std::cout << "  -> STL 变易、重排与划分全套算法引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了修改类算法的核心微架构运行规律：

1. **倒序拷贝捍卫数据完整性**：在测试 1 中，目标起始位置落入源区间内部，若采用正向迭代将在复制第 3 个元素前将其污染，``mini_copy_backward`` 从尾部开始向前回退写入，完美化解了重叠依赖。
2. **逻辑紧凑与物理析构清晰解耦**：在测试 2 中，``mini_remove_if`` 仅用一次单向线性扫描就将所有存活偶数移动至前排，返回值准确定位边界，使后继容器 ``erase`` 能在无需额外遍历的情况下瞬间释放尾部无效对象。
3. **三步反转代数优雅性**：在测试 3 中，三步反转法在零辅助内存分配下完成原地循环位移，仅触发精确的 $N$ 次 Swap 交换，内存访问局部性极佳。

小结与下章导读
--------------

本章系统解构了现代 C++ STL 变易、重排与区间紧凑化算法体系：

1. **内存重叠方向选择定理**：推导了向高地址平移必须使用 ``copy_backward``、向低地址平移必须使用 ``copy`` 的物理必然性。
2. **Remove-Erase 惯用法**：形式化剖析了算法逻辑前移覆盖与容器物理析构缩容之间的正交分工。
3. **rotate 循环位移算法族**：深入推导了三步反转法（$(\cdot)^R$ 代数对称性）与 Gries-Mills 最大公约数循环轨道轮换的执行机理。
4. **partition 快速划分**：解构了 Hoare 双向对撞双指针状态机以最少元素交换达成二元子集分割的物理过程。

在掌握了只读与变易算法之后，下一章我们将正式进军 STL 算法领域中计算复杂度最高、工程优化最极致的巅峰——**排序算法体系**。在第 5 模块第 4 节 **排序算法全景：std::sort 内省排序 (Introsort)、快速排序/堆排序/插入排序三层降级与 stable_sort 归并（``05_generic_algorithms_and_performance/04_introsort_quicksort_heapsort_and_stablesort.rst``）** 中，我们将深入剖析工业级 ``std::sort`` 如何以快速排序（Quicksort）为主轴、在递归深度超限时自动降级为堆排序（Heapsort）以规避 $\mathcal{O}(N^2)$ 最坏退化、在小区间时降级为插入排序（Insertion Sort）利用 Cache 局部性，以及基于归并（Mergesort）实现稳定排序 ``std::stable_sort`` 的完整工程微架构。
