========================================================================================================================
泛型算法解耦哲学：半开区间 [first, last) 几何契约、迭代器操作分发与可插入策略设计
========================================================================================================================

.. note:: 前置背景与上下文承接
   承接第二模块前四章《迭代器核心体系与能力分层》、《内存分配器体系：allocator 接口契约、allocator_traits 统一抽象、未初始化内存批量构造算法》、《std::pmr 多态内存资源体系》与《异常安全保证与回滚机制》，系统已建立 STL 的游标模型、内存生命周期控制、多态资源管理与异常事务恢复机制。作为第 2 模块的收官之作，本章深入剖析 STL 算法与容器物理存储正交解耦的核心设计哲学：解构半开区间 ``[first, last)`` 拓扑不变量在指针偏移计算、空区间退化判定、循环终止收敛与越界防护中的数学单调性；深入剖析算法模板如何仅通过精简的迭代器表达式（解引用、单步递增、随机跳转）与底层物理内存解耦；剖析 ``iterator_traits`` 与基于类型标签的 ``tag dispatch`` 编译期静态分发拓扑，对比随机访问指针运算与线性链表游标推进的机器指令展开差异；剖析可插入策略（Policy-based Design）、仿函数（Function Objects）、谓词（Predicates）与比较器（Comparators）在内联展开与寄存器分配中的物理优势；解密插入迭代器（``back_inserter`` / ``front_inserter`` / ``inserter``）如何通过代理模式将只读/覆写算法适配为动态扩容容器变易操作；最终通过工业级正交算法引擎完成工程落地。

半开区间 [first, last) 几何契约与指针偏移数学不变量
---------------------------------------------------

在计算机硬件内存模型中，连续寻址空间呈现为线性单向递增的一维字节序列。STL 算法体系将所有区间操作抽象为半开区间（Half-Open Range）数学模型，记作 ``[first, last)``。该模型定义了一个左闭右开的点集：

.. math::

   [first, last) = \{ p \mid first \le p < last \}

其中 ``first`` 与 ``last`` 为指向相同物理容器或相同连续内存流的两个同构迭代器或原生指针。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             半开区间 [first, last) 物理内存拓扑与哨兵布局                             |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   物理内存连续地址空间 (低地址 ------------------------------------------------------------> 高地址)  |
   |                                                                                                       |
   |   first 指针                                                                  last 哨兵指针           |
   |   (指向首个有效元素)                                                          (指向末尾元素之后一位置)|
   |     |                                                                           |                     |
   |     v                                                                           v                     |
   |   +---------------+---------------+---------------+---------------+-----------+---------------+       |
   |   |   Element 0   |   Element 1   |   Element 2   |      ...      | Element N | (Past-The-End)|       |
   |   +---------------+---------------+---------------+---------------+-----------+---------------+       |
   |   |<- 元素 0 内存 ->|<- 元素 1 内存 ->|<- 元素 2 内存 ->|               |<- 元素 N ->| (禁止解引用)  |       |
   |                                                                                                       |
   |   [ 几何不变量判定与收敛特性 ]                                                                        |
   |   1. 元素基数 (Cardinality):  Count = (last - first)                                                  |
   |   2. 空区间退化 (Empty Range): first == last (指针地址相等，循环体零次执行直接返回)                    |
   |   3. 子区间无缝拼接 (Splitting): [first, mid) U [mid, last) == [first, last] (零间隙、零重叠)         |
   |   4. 查找未命中返回值 (Miss Return): 返回 last 哨兵，指示查找遍历已完全穷尽                           |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

半开区间模型的四大几何不变量
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

半开区间设计确立了四项严格的数学与物理不变量：

1. **空区间判定的单指令退化（Zero-overhead Empty State Detection）**：
   当区间内无任何有效元素时，起始位置与终止位置重合，即 ``first == last``。算法在进入循环前仅需执行一次单周期寄存器比较指令（如 x86 的 ``cmp %rdi, %rsi``），若相等则触发条件跳转（``je``）直接退出，无需额外维护独立的计数器字段、有效性标志位或布尔变量。

2. **元素基数与内存跨度的一致性（Cardinality Invariant）**：
   区间所包含的元素总数精确等于终止位置与起始位置的代数差值：

   .. math::

      N = last - first

   对于连续内存随机访问迭代器（如原生指针与 ``std::vector::iterator``），元素数量的获取退化为底层的指针算术减法：

   .. math::

      N = \frac{	ext{reinterpret\_cast<uintptr\_t>}(last) - 	ext{reinterpret\_cast<uintptr\_t>}(first)}{\operatorname{sizeof}(T)}

   该操作在编译后由单条减法指令（``sub``）与右移指令（``sar`` / ``shr``）完成，执行开销为 $O(1)$。

3. **子区间无缝拼接与零重叠划分（Seamless Range Splitting）**：
   对于任意满足 $first \le mid \le last$ 的中间迭代器 $mid$，原始区间可以严格划分为两个连续子区间：

   .. math::

      [first, last) = [first, mid) \cup [mid, last) \quad 	ext{且} \quad [first, mid) \cap [mid, last) = \emptyset

   前一个子区间的终止哨兵 $mid$ 恰好构成后一个子区间的起始位置。这种零重叠且零间隙的拓扑特性，为二分搜索（``std::lower_bound``）、内省排序（``std::sort``）与快速排序分区（``std::partition``）等分治算法提供了严格的数学收敛保证，消除了闭区间 ``[first, last]`` 中 $mid - 1$ 或 $mid + 1$ 带来的下溢/越界风险。

4. **末尾后一位置哨兵（Past-The-End Sentinel）物理可达性**：
   C++ 内存模型规定，指向数组末尾元素之后一个位置的指针（Past-The-End 指针）属于合法的受保护地址，允许参与指针算术运算与比较，但禁止执行解引用操作（Dereference）。当算法执行单向遍历循环时：

   .. code-block:: cpp

      for (; first != last; ++first) {
          // 循环体内仅对有效位置执行解引用
      }

   迭代器 ``first`` 从有效起始地址出发单调向前推移，最终与 ``last`` 精确对齐并终止。若算法未查找到目标元素，统一将 ``last`` 作为查找失败的返回状态，调用侧通过判断 ``result == last`` 即可完成确定性分支分流，无需定义额外的 ``nullptr`` 或特殊错误码枚举。

算法与容器正交解耦模型：$M + N$ 架构与静态多态
----------------------------------------------

在传统的面向对象设计（OOP）中，若存在 $M$ 个容器与 $N$ 个通用算法，通常倾向于在容器基类中声明虚函数，或为每个容器单独实现 $N$ 个成员函数。这种紧耦合模式会导致代码量呈现 $M 	imes N$ 的乘法级膨胀，并且虚函数的动态分发（Dynamic Dispatch）机制引入了间接寻址开销与指令缓存（I-Cache）失效。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             STL 泛型算法与物理容器正交解耦架构 ($M + N$)                             |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ M 种具体物理存储容器 ]                                        [ N 种通用泛型算法 ]                 |
   |                                                                                                       |
   |   +-----------------------+                                       +-----------------------+           |
   |   |   std::vector<T>      |                                       |   std::find / find_if |           |
   |   |   (连续动态数组)      |                                       |   (线性短路查找)      |           |
   |   +-----------------------+                                       +-----------------------+           |
   |   |   std::list<T>        |           [ 抽象粘合层 ]              |   std::sort           |           |
   |   |   (双向循环链表)      | ===>   迭代器游标概念契约   <===      |   (内省快速排序)      |           |
   |   +-----------------------+         Iterator Concepts             +-----------------------+           |
   |   |   std::deque<T>       |                                       |   std::copy / move    |           |
   |   |   (分段缓冲区中控)    |                                       |   (批量序列迁移)      |           |
   |   +-----------------------+                                       +-----------------------+           |
   |   |   T 原生数组 (T[N])   |                                       |   std::transform      |           |
   |   |   (栈/全局连续内存)   |                                       |   (策略映射重构)      |           |
   |   +-----------------------+                                       +-----------------------+           |
   |                                                                                                       |
   |   [ 物理实现规模 ]: M 个容器 + N 个算法 = M + N (编译期静态单态化展开，零运行时虚表开销)              |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

正交分解机制
~~~~~~~~~~~~

STL 采用基于模板的静态多态体系，将体系分解为相互正交的两极：

1. **容器职责边界**：容器专注于底层物理内存的分配（通过 Allocator）、对象生命周期构造与析构、节点指针拓扑连接与容量扩缩容。容器仅向外界暴露一对表征边界的迭代器（``begin()`` 与 ``end()``）。
2. **算法职责边界**：算法完全剥离对容器具体内部数据结构（如红黑树根指针、哈希桶数组指针、连续缓冲区指针）的感知。算法函数模板仅接收迭代器实例，并通过迭代器所支持的最小操作集合实现业务逻辑。
3. **实现复杂度优化**：系统整体代码规模从 $M 	imes N$ 骤降至 $M + N$。新增一个数据结构只需提供符合标准的迭代器，即可自动获得全套 $N$ 个算法的支持；新增一个算法只需面向迭代器概念编程，即可立即应用于所有 $M$ 个现有容器。

静态多态与内联代码生成
~~~~~~~~~~~~~~~~~~~~~~

当调用 ``std::find_if(vec.begin(), vec.end(), pred)`` 与 ``std::find_if(lst.begin(), lst.end(), pred)`` 时，C++ 编译器在前端执行模板实例化（Template Instantiation）：

- 对于 ``std::vector<int>``，迭代器类型为原生指针或轻量指针包装类，``++first`` 被直接编译为指针加法指令（如 ``add $0x4, %rdi``）。
- 对于 ``std::list<int>``，迭代器类型为节点指针包装类，``++first`` 被直接编译为加载后继节点指针指令（如 ``mov 0x8(%rdi), %rdi``）。

编译器在优化阶段（如 ``-O2`` / ``-O3``）将整个遍历循环、迭代器操作与谓词逻辑完全内联展开在调用点，彻底消除了函数调用上下文切换、参数入栈与虚函数表寻址的开销。

.. list-table:: 算法操作与迭代器能力依赖映射矩阵
   :widths: 22 26 26 26
   :header-rows: 1
   :class: tight-table

   * - 算法类型
     - 最小迭代器概念要求
     - 核心机器操作集合
     - 适用典型物理容器
   * - 线性查找 (``find``)
     - Input Iterator
     - ``!=``, ``*it`` (读), ``++it``
     - ``vector``, ``list``, ``deque``, ``istream``
   * - 序列逆序 (``reverse``)
     - Bidirectional Iterator
     - ``!=``, ``*it`` (读写), ``++it``, ``--it``
     - ``vector``, ``list``, ``deque``
   * - 内省排序 (``sort``)
     - Random Access Iterator
     - ``it + n``, ``it - n``, ``it[n]``, ``<``, 交换
     - ``vector``, ``deque``, 原生数组
   * - 批量覆写 (``copy``)
     - Input + Output Iterator
     - 读源 ``*in++``, 写目标 ``*out++ = val``
     - 任意合法输入输出迭代器组合

静态分发拓扑：iterator_traits 萃取与 Tag Dispatch 编译期路由
------------------------------------------------------------

当同一个算法逻辑在不同迭代器类型上存在显著性能差异时，STL 必须在编译期静态选择最高效的指令路径。这一过程依赖于 ``std::iterator_traits`` 类型萃取机与基于标签重载的 ``tag dispatch`` 机制。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                        iterator_traits 萃取与 Tag Dispatch 编译期分发流转                             |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 用户调用入口 ]: mini_distance(first, last)                                                        |
   |                                                                                                       |
   |   [ 步骤 1: 类型萃取 ]:                                                                               |
   |     using Category = typename std::iterator_traits<It>::iterator_category;                            |
   |                                                                                                       |
   |   [ 步骤 2: 标签层级拓扑匹配 (编译期重载决议) ]:                                                      |
   |                                                                                                       |
   |               input_iterator_tag                                                                      |
   |                      ^                                                                                |
   |                      | 派生继承                                                                       |
   |             forward_iterator_tag                                                                      |
   |                      ^                                                                                |
   |                      | 派生继承                                                                       |
   |          bidirectional_iterator_tag                                                                   |
   |                      ^                                                                                |
   |                      | 派生继承                                                                       |
   |          random_access_iterator_tag                                                                   |
   |                                                                                                       |
   |     +-----------------------------------------+-----------------------------------------+             |
   |     | 分支 A: random_access_iterator_tag      | 分支 B: input_iterator_tag (兜底基类)   |             |
   |     v                                         v                                         v             |
   |   [ 机器指令展开 ]:                         [ 机器指令展开 ]:                                         |
   |     return last - first;                      difference_type n = 0;                                  |
   |     (单条 sub 指令 + 算术右移, O(1))            for (; first != last; ++first) ++n;                     |
   |                                               (紧凑寄存器循环跳转, O(N))                                |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

Tag 标签继承拓扑与向上转换匹配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准库在 ``<iterator>`` 头文件中定义了五大空结构体标签：

.. code-block:: cpp

   struct input_iterator_tag {};
   struct output_iterator_tag {};
   struct forward_iterator_tag : public input_iterator_tag {};
   struct bidirectional_iterator_tag : public forward_iterator_tag {};
   struct random_access_iterator_tag : public bidirectional_iterator_tag {};
   // C++20 新增：
   struct contiguous_iterator_tag : public random_access_iterator_tag {};

由于类继承关系的存在，当某个算法重载仅提供了 ``input_iterator_tag`` 与 ``random_access_iterator_tag`` 两个版本时：

- 传入 ``forward_iterator_tag`` 或 ``bidirectional_iterator_tag`` 会根据标准转换规则自动向上转型匹配至 ``input_iterator_tag`` 兜底实现。
- 传入 ``random_access_iterator_tag`` 则精确匹配至常量时间复杂度的特化实现。

std::distance 机器码展开对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以计算两迭代器跨度的 ``std::distance`` 为例：

1. **随机访问迭代器分支（如 ``std::vector<int>::iterator`` 或 ``int*``）**：
   重载函数接收 ``random_access_iterator_tag``。
   源码表达：``return last - first;``。
   编译为 x86-64 汇编指令：

   .. code-block:: gas

      movq    %rsi, %rax       # 将 last 指针加载至 rax
      subq    %rdi, %rax       # rax = last - first (字节差值)
      sarq    $2, %rax         # 算术右移 2 位 (除以 sizeof(int) = 4)，耗时 1 周期

2. **输入/双向迭代器分支（如 ``std::list<int>::iterator``）**：
   重载函数接收 ``input_iterator_tag``。
   源码表达：执行线性单步累加递增。
   编译为 x86-64 汇编指令：

   .. code-block:: gas

      xorl    %eax, %eax       # n = 0 (清空累加寄存器)
   .L_LOOP:
      cmpq    %rsi, %rdi       # 比较 first 与 last
      je      .L_EXIT          # 若相等，退出循环
      incq    %rax             # ++n
      movq    8(%rdi), %rdi    # first = first->next (加载链表后继节点)
      jmp     .L_LOOP
   .L_EXIT:
      ret

C++17 if constexpr 编译期分发演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++17 引入 ``if constexpr`` 语法后，编译期分发由传统的辅助重载函数模式演进为单一函数体内的结构化分支：

.. code-block:: cpp

   template <typename InputIt>
   constexpr typename std::iterator_traits<InputIt>::difference_type
   fast_distance(InputIt first, InputIt last) {
       using Category = typename std::iterator_traits<InputIt>::iterator_category;
       if constexpr (std::is_base_of_v<std::random_access_iterator_tag, Category>) {
           return last - first;
       } else {
           typename std::iterator_traits<InputIt>::difference_type count = 0;
           for (; first != last; ++first) {
               ++count;
           }
           return count;
       }
   }

未被命中的代码分支在编译期直接被语法树修剪丢弃，零生成冗余机器码。

策略模式（Policy-based Design）、仿函数与内联优化
--------------------------------------------------

STL 算法将“数据遍历的物理骨架”与“业务逻辑的判定策略”彻底分离。算法固定了遍历与重排的拓扑步骤，而将具体的过滤条件、变换规则或排序比较作为策略类型参数（Policy Type Parameter）开放给外部注入。

函数对象（Function Objects）对普通函数指针的物理优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C/C++ 底层执行环境中，策略传递存在两种物理载体：函数指针与仿函数（包含 Lambda 闭包结构体）。两者在指令级生成上存在巨大差异：

.. list-table:: 仿函数 vs 函数指针 机器级执行特征对比
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 函数指针 (Function Pointer)
     - 仿函数 / Lambda 闭包类 (Functor / Lambda)
   * - 类型表征
     - 弱化为统一签名指针（如 ``bool(*)(int, int)``）
     - 每个仿函数与 Lambda 拥有全局唯一的独立类型
   * - 调用开销
     - 间接寻址调用（``call *%rax``），阻断流水线
     - 静态解析直接调用，目标地址在编译期确定
   * - 内联能力
     - 无法内联展开，必须经历标准 ABI 栈帧构建
     - 强力强制内联（Inline），消除函数调用指令
   * - 循环优化
     - 阻断编译器寄存器分配、循环展开与向量化
     - 允许循环展开、自动 SIMD 向量化与常量折叠

当 ``std::sort`` 接收一个仿函数策略 ``comp`` 时，比较操作直接嵌入在快速排序的内层双指针扫描循环中。若传入普通函数指针，每次比较均需执行间接跳转与栈帧保护，排序吞吐量通常下降 200% 至 500%。

严格弱序（Strict Weak Ordering）数学契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

所有关联容器与排序相关算法（``std::sort``、``std::lower_bound``、``std::priority_queue``）对其传入的比较策略 ``comp(a, b)`` 提出严格弱序数学要求。定义二元谓词 $\prec$ 为严格弱序关系，当且仅当满足以下四项公理：

1. **非自反性（Irreflexivity）**：对于任意元素 $a$，$\operatorname{comp}(a, a) = 	ext{false}$。
2. **非对称性（Asymmetry）**：若 $\operatorname{comp}(a, b) = 	ext{true}$，则 $\operatorname{comp}(b, a) = 	ext{false}$。
3. **传递性（Transitivity）**：若 $\operatorname{comp}(a, b) = 	ext{true}$ 且 $\operatorname{comp}(b, c) = 	ext{true}$，则 $\operatorname{comp}(a, c) = 	ext{true}$。
4. **不可比性的等价传递性（Transitivity of Incomparability）**：
   定义等价关系 $a \sim b$ 为 $
eg\operatorname{comp}(a, b) \land 
eg\operatorname{comp}(b, a)$。若 $a \sim b$ 且 $b \sim c$，则必有 $a \sim c$。

若破坏非自反性（例如错误编写小于等于比较器 ``return a <= b;``），会导致 $\operatorname{comp}(a, a) = 	ext{true}$。当 ``std::sort`` 执行快速排序的基准值（Pivot）双向哨兵扫描时，游标遇到与 Pivot 相等的元素不会停机，直接冲出合法内存边界，引发段错误（Segmentation Fault）硬崩溃。

变易算法与可插入迭代器（Insert Iterators）代理架构
--------------------------------------------------

STL 的变易算法（如 ``std::copy``、``std::transform``、``std::fill_n``）属于覆写型（Overwriting）算法。这类算法默认目标输出区间已经分配好物理存储，且已构造好有效对象，算法通过解引用输出迭代器执行就地赋值：

.. code-block:: cpp

   *out_first = *in_first; // 纯覆写赋值，绝不触发容器扩容

若目标容器为空且调用方直接传入 ``vec.begin()``，解引用空容器的起始位置将直接触发越界未定义行为。为了将“覆写语义算法”透明适配为“动态插入扩容语义”，STL 引入了插入迭代器适配器（Insert Iterators）体系。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                       插入迭代器适配器 (Insert Iterator) 代理转发与扩容机制                           |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   std::copy(src.begin(), src.end(), std::back_inserter(dest));                                        |
   |                                                                                                       |
   |   [ std::copy 算法视角 ]                                    [ 插入迭代器内部物理转换 ]                |
   |     *out_it = value;      == 代理重载转译 ==>                container->push_back(value);            |
   |                                                               (触发底层 Allocator 内存分配与构造)     |
   |     ++out_it;             == 代理重载转译 ==>                return *this; (空操作，返回自身引用)     |
   |                                                                                                       |
   |   +-----------------------------------------------------------------------------------------------+   |
   |   | 三大插入迭代器代理行为矩阵                                                                    |   |
   |   | 1. back_insert_iterator  (std::back_inserter)  ---> 代理调用 container.push_back(val)         |   |
   |   | 2. front_insert_iterator (std::front_inserter) ---> 代理调用 container.push_front(val)        |   |
   |   | 3. insert_iterator       (std::inserter)       ---> 代理调用 pos = container.insert(pos, val)  |   |
   |   +-----------------------------------------------------------------------------------------------+   |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

插入迭代器通过操作符重载技巧，向算法伪装出合法的 Output Iterator 接口：

1. **``operator*()`` 重载**：直接返回自身引用（``*this``），使得后续的赋值表达式 ``*it = val`` 绑定到迭代器的赋值操作符重载上。
2. **``operator=(const T& value)`` 重载**：截获赋值右值，将其转化为底层容器的成员函数调用（如 ``container->push_back(value)``）。
3. **``operator++()`` 与 ``operator++(int)`` 重载**：直接返回自身引用，不执行任何指针物理偏移，因为容器在执行 ``push_back`` 时已自动递增其内部大小。

工业级正交泛型算法与策略引擎完整工程实现
----------------------------------------

本节给出一个完整的工业级 C++17/20 生产级实现：构建一套涵盖核心 Traits 萃取、编译期 Tag Dispatch 分发、半开区间几何遍历、可插拔策略映射以及自定义插入迭代器代理的轻量泛型算法引擎 ``engine::algo``。

.. code-block:: cpp

   #include <cassert>
   #include <cstddef>
   #include <iostream>
   #include <iterator>
   #include <list>
   #include <string>
   #include <type_traits>
   #include <utility>
   #include <vector>

   namespace engine::algo {

   // =========================================================================
   // 1. 编译期 Tag Dispatch 距离计算引擎：mini_distance
   // =========================================================================
   namespace detail {

   template <typename InputIt>
   constexpr typename std::iterator_traits<InputIt>::difference_type
   do_distance(InputIt first, InputIt last, std::input_iterator_tag) {
       typename std::iterator_traits<InputIt>::difference_type count = 0;
       for (; first != last; ++first) {
           ++count;
       }
       return count;
   }

   template <typename RandomIt>
   constexpr typename std::iterator_traits<RandomIt>::difference_type
   do_distance(RandomIt first, RandomIt last, std::random_access_iterator_tag) {
       return last - first;
   }

   } // namespace detail

   template <typename It>
   constexpr typename std::iterator_traits<It>::difference_type
   mini_distance(It first, It last) {
       using Category = typename std::iterator_traits<It>::iterator_category;
       return detail::do_distance(first, last, Category{});
   }

   // =========================================================================
   // 2. 编译期步进引擎：mini_advance
   // =========================================================================
   namespace detail {

   template <typename InputIt, typename Distance>
   constexpr void do_advance(InputIt& it, Distance n, std::input_iterator_tag) {
       while (n > 0) {
           --n;
           ++it;
       }
   }

   template <typename BidirectionalIt, typename Distance>
   constexpr void do_advance(BidirectionalIt& it, Distance n, std::bidirectional_iterator_tag) {
       if (n >= 0) {
           while (n > 0) {
               --n;
               ++it;
           }
       } else {
           while (n < 0) {
               ++n;
               --it;
           }
       }
   }

   template <typename RandomIt, typename Distance>
   constexpr void do_advance(RandomIt& it, Distance n, std::random_access_iterator_tag) {
       it += n;
   }

   } // namespace detail

   template <typename It, typename Distance>
   constexpr void mini_advance(It& it, Distance n) {
       using Category = typename std::iterator_traits<It>::iterator_category;
       detail::do_advance(it, n, Category{});
   }

   // =========================================================================
   // 3. 半开区间核心算法实现：find_if / copy / transform
   // =========================================================================

   // 线性条件查找：满足 Input Iterator 最小操作集契约
   template <typename InputIt, typename UnaryPredicate>
   constexpr InputIt mini_find_if(InputIt first, InputIt last, UnaryPredicate pred) {
       for (; first != last; ++first) {
           if (pred(*first)) {
               return first; // 命中立即短路返回当前游标
           }
       }
       return last; // 未命中返回末尾哨兵
   }

   // 序列批量覆写迁移
   template <typename InputIt, typename OutputIt>
   constexpr OutputIt mini_copy(InputIt first, InputIt last, OutputIt d_first) {
       for (; first != last; ++first, ++d_first) {
           *d_first = *first;
       }
       return d_first;
   }

   // 一元策略映射变换
   template <typename InputIt, typename OutputIt, typename UnaryOperation>
   constexpr OutputIt mini_transform(InputIt first, InputIt last, OutputIt d_first, UnaryOperation op) {
       for (; first != last; ++first, ++d_first) {
           *d_first = op(*first);
       }
       return d_first;
   }

   // 二元策略映射变换
   template <typename InputIt1, typename InputIt2, typename OutputIt, typename BinaryOperation>
   constexpr OutputIt mini_transform(InputIt1 first1, InputIt1 last1, InputIt2 first2, OutputIt d_first, BinaryOperation op) {
       for (; first1 != last1; ++first1, ++first2, ++d_first) {
           *d_first = op(*first1, *first2);
       }
       return d_first;
   }

   // =========================================================================
   // 4. 自定义工业级尾部插入迭代器适配器：MiniBackInsertIterator
   // =========================================================================
   template <typename Container>
   class MiniBackInsertIterator {
   public:
       using iterator_category = std::output_iterator_tag;
       using value_type        = void;
       using difference_type   = std::ptrdiff_t;
       using pointer           = void;
       using reference         = void;
       using container_type    = Container;

       explicit MiniBackInsertIterator(Container& c) noexcept : container_(&c) {}

       // 核心转译赋值：将算法的写入重定向为容器的 push_back
       MiniBackInsertIterator& operator=(const typename Container::value_type& value) {
           container_->push_back(value);
           return *this;
       }

       MiniBackInsertIterator& operator=(typename Container::value_type&& value) {
           container_->push_back(std::move(value));
           return *this;
       }

       // 伪装操作符：解引用返回自身以承接 operator=
       [[nodiscard]] MiniBackInsertIterator& operator*() noexcept {
           return *this;
       }

       // 自增空操作：容器内部已维护 size
       MiniBackInsertIterator& operator++() noexcept {
           return *this;
       }

       MiniBackInsertIterator operator++(int) noexcept {
           return *this;
       }

   protected:
       Container* container_;
   };

   // 辅助工厂函数
   template <typename Container>
   [[nodiscard]] constexpr MiniBackInsertIterator<Container> mini_back_inserter(Container& c) noexcept {
       return MiniBackInsertIterator<Container>(c);
   }

   } // namespace engine::algo

   // =========================================================================
   // 5. 验证套件：正交解耦、Tag Dispatch 与插入适配器集成测试
   // =========================================================================
   namespace test {

   struct TaskItem {
       int priority;
       std::string title;
   };

   struct HigherPriorityComparator {
       constexpr bool operator()(const TaskItem& a, const TaskItem& b) const noexcept {
           return a.priority > b.priority; // 严格弱序
       }
   };

   void run_generic_algorithm_decoupling_test() {
       using namespace engine::algo;

       // 测试 1: 原生数组与 vector 的 Tag Dispatch 距离计算 (O(1) 随机访问)
       int raw_array[6] = {10, 20, 30, 40, 50, 60};
       assert(mini_distance(&raw_array[0], &raw_array[6]) == 6);

       std::vector<int> vec = {1, 2, 3, 4, 5};
       assert(mini_distance(vec.begin(), vec.end()) == 5);

       // 测试 2: std::list 的线性 Tag Dispatch 距离计算 (O(N) 线性遍历)
       std::list<int> lst = {100, 200, 300};
       assert(mini_distance(lst.begin(), lst.end()) == 3);

       // 测试 3: mini_find_if 短路搜索与哨兵返回值验证
       auto it_vec = mini_find_if(vec.begin(), vec.end(), [](int val) { return val == 3; });
       assert(it_vec != vec.end() && *it_vec == 3);

       auto it_miss = mini_find_if(vec.begin(), vec.end(), [](int val) { return val == 999; });
       assert(it_miss == vec.end()); // 命中 last 哨兵

       // 测试 4: mini_transform 结合自定义 mini_back_inserter 动态扩容
       std::vector<int> transformed_vec;
       mini_transform(vec.begin(), vec.end(), mini_back_inserter(transformed_vec), [](int x) {
           return x * 10;
       });
       assert(transformed_vec.size() == 5);
       assert(transformed_vec[0] == 10 && transformed_vec[4] == 50);

       // 测试 5: 策略仿函数与复杂结构体解耦筛选
       std::vector<TaskItem> tasks = {
           {1, "Low Priority Job"},
           {5, "Critical Kernel Task"},
           {3, "Background Sync"}
       };
       auto crit_it = mini_find_if(tasks.begin(), tasks.end(), [](const TaskItem& t) {
           return t.priority >= 5;
       });
       assert(crit_it != tasks.end() && crit_it->title == "Critical Kernel Task");
   }

   } // namespace test

小结与下章导读
--------------

本章系统解构了现代 C++ STL 的泛型算法解耦哲学与底层正交架构：从半开区间 ``[first, last)`` 拓扑在单指令空状态判定、内存跨度求值与分治子区间无缝拼接中的数学单调性；从面向对象 $M 	imes N$ 虚表开销到泛型模板 $M + N$ 编译期单态化内联展开的正交解耦机制；从 ``std::iterator_traits`` 与 ``tag dispatch`` 在常量时间指针算术与线性循环跳转间的静态机器码分发；从仿函数（Function Object）拥有独立强类型并消除间接调用开销的内联优化，到严格弱序（Strict Weak Ordering）对排序算法越界崩溃的数学约束；从变易算法的就地覆写语义，到插入迭代器适配器（``back_inserter`` / ``inserter``）通过代理模式将写入操作透明转换为容器动态内存分配与构造的工程技巧。

至此，第 2 模块《STL 核心机制与内存子系统》全量完工。我们已经建立了迭代器能力分层、内存分配器生命周期管理、PMR 多态内存池化、强异常安全回滚以及泛型算法正交解耦的完整底层体系。下一章我们将正式开启全书第 3 模块《顺序容器物理拓扑与实现》的第一篇 —— **std::vector 连续内存动态数组：三指针状态模型、几何级扩容迁移、异常安全强保证与 vector<bool> 特化边界（``03_sequence_containers_internals/01_vector_three_pointer_model_and_growth.rst``）**，深入剖析 ``_M_start``、``_M_finish`` 与 ``_M_end_of_storage`` 三指针微架构、1.5/2 倍几何增长动力学、移动语义条件迁移与代理引用的位压缩实现。
