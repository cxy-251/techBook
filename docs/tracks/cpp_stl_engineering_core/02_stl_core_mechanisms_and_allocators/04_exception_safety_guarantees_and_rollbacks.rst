==================================================================================================================================
异常安全保证与回滚机制：基本保证/强保证/不抛保证、noexcept 移动判定与 vector 扩容事务一致性
==================================================================================================================================

.. note:: 前置背景与上下文承接
   在第二模块前三章《迭代器核心体系与能力分层》、《内存分配器体系：allocator 接口契约、allocator_traits 统一抽象、未初始化内存批量构造算法》与《std::pmr 多态内存资源体系》中，系统建立了 STL 的游标模型、traits 静态萃取路由、原始内存与生命周期的四阶段状态机以及运行时多态内存资源池化架构。然而，当容器在执行动态扩容、批量元素构造、节点插入或算法重排过程中，若分配器内存耗尽、元素类型的构造函数或移动操作抛出异常，系统必须提供确定性的状态恢复与资源释放保证。本章深入剖析 STL 异常安全保证与事务回滚机制：解构基本保证（Basic Guarantee）、强保证（Strong Guarantee）与不抛保证（No-throw Guarantee）的三级契约边界与物理不变量；剖析 C++ 异常模型在栈展开（Stack Unwinding）过程中的 RAII 资源责任闭合；深入 ``noexcept`` 说明符与 ``noexcept(...)`` 编译期条件判定运算符，探究 ``std::move_if_noexcept`` 在强保证事务回滚与移动性能之间的权衡降级机制；解密 ``std::vector`` 几何扩容与区间插入中的两阶段提交（Two-Phase Commit）事务状态机与三指针原子切换；分析节点式容器（list/map/unordered_map）的单节点隔离分配拓扑与异常回滚 Guard 设计模式，最终通过工业级带原子事务回滚的 Mini-Vector 扩容与插入引擎完成工程落地。

异常安全分级模型与状态一致性契约边界
------------------------------------

在 C++ 工程体系中，异常安全（Exception Safety）描述的是当控制流因异常离开函数或代码块时，相关对象与系统资源所能维持的状态一致性级别。标准库将异常安全划分为三个严格递进的契约等级，外加一个必须排除的未定义行为边界。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                                 C++ STL 异常安全三级契约递进拓扑                                      |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 最高级别: 不抛保证 (No-throw / Nothrow Guarantee) ]                                               |
   |   - 承诺函数绝不向外逃逸任何异常；所有内部故障在函数内部完全闭环处理。                               |
   |   - 物理支点：析构函数、内存释放函数 (deallocate/free)、指针/资源句柄交换 (swap)、提交点操作。       |
   |                                       ^                                                               |
   |                                       | 包含且强化                                                    |
   |   [ 次高级别: 强异常安全保证 (Strong Guarantee / Commit-or-Rollback) ]                                |
   |   - 操作具备事务原子性：要么完全执行成功，要么目标对象完整保持调用前的物理状态与数据值。             |
   |   - 物理支点：两阶段提交（临时缓冲区准备 -> 不抛提交点切换）、RAII 事务回滚守卫。                     |
   |                                       ^                                                               |
   |                                       | 包含且强化                                                    |
   |   [ 基础级别: 基本异常安全保证 (Basic Guarantee) ]                                                    |
   |   - 保证无内存泄漏，所有资源句柄均被合法析构；对象内部不变量仍然成立，处于有效但未指定状态。         |
   |   - 物理支点：RAII 资源封装、智能指针、容器自洽状态重置。                                            |
   |                                       ^                                                               |
   |                                       | 严格防御防线                                                  |
   |   [ 违规状态: 无保证 / 未定义行为 (No Guarantee / Undefined Behavior) ]                               |
   |   - 出现内存泄漏、悬垂指针、破损的虚表、破坏的红黑树平衡因子或双重异常导致的 std::terminate() 崩溃。  |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

基本保证（Basic Exception Safety Guarantee）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

基本保证是所有工业级 C++ 代码必须满足的最低底线：

1. **无资源泄漏（No Resource Leaks）**：所有动态申请的物理内存、文件描述符、互斥锁、套接字句柄等系统资源，在异常发生时均能通过栈展开与 RAII 机制安全归还系统。
2. **对象不变量守恒（Class Invariants Preserved）**：对象在异常抛出后仍处于合法自洽的物理状态。例如，容器的内部大小计数器与其实际容纳的元素数量严格一致，空闲链表指针未断裂，虚表指针未被覆写。
3. **有效但未指定状态（Valid but Unspecified State）**：对象内部存储的具体数据值可能发生改变，但调用方可以安全读取其大小、调用其成员函数、清空容器或执行析构。

强保证（Strong Exception Safety Guarantee）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

强保证在基本保证的基础上增加了 **事务原子性（Transactional Atomicity）** 约束，即遵循“提交或回滚（Commit-or-Rollback）”语义：

1. **状态完全保持（State Invariance on Failure）**：若操作中途抛出异常，目标对象可观察的状态、元素序列、容量及迭代器均精确保持为调用该操作之前的状态。
2. **瞬态资源完全回收（Ephemeral Resource Clean-up）**：操作执行过程中预先申请的所有临时物理内存与中间构造的对象，在异常发生时被完全析构并释放，系统无任何副作用残留。
3. **调用侧恢复确定性**：调用方捕获异常后，可以直接依据原对象状态继续执行后续业务逻辑，无需重新同步或重建对象。

不抛保证（No-throw / Nothrow Guarantee）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

不抛保证承诺函数在任何输入条件与系统状态下均绝对不会向调用栈外层传播异常：

1. **终止向外传播**：函数签名通常带有 ``noexcept`` 或 ``noexcept(true)`` 约束。内部若发生下层错误，必须在函数体内部完全消化（如通过错误码返回或默认降级）。
2. **作为回滚与清理的绝对基石**：强保证与基本保证的实现完全依赖于析构函数、内存释放函数与指针交换操作的不抛特性。若回滚或析构路径自身抛出异常，栈展开过程将被二次中断，直接触发 ``std::terminate()`` 导致进程硬崩溃。

.. list-table:: 三级异常安全保证与调用侧契约边界矩阵
   :widths: 18 26 26 30
   :header-rows: 1
   :class: tight-table

   * - 保证级别
     - 异常发生后对象状态
     - 资源生命周期责任
     - 典型 STL 场景与架构角色
   * - 基本保证 (Basic)
     - 保持合法自洽，值可能改变
     - 完全闭合，零资源泄漏
     - 容器区间赋值、部分算法就地重排、流输出操作
   * - 强保证 (Strong)
     - 严格恢复为调用前状态
     - 临时分配全量回滚清零
     - ``vector::push_back`` 扩容、单节点插入、事务型赋值
   * - 不抛保证 (Nothrow)
     - 操作必定成功，无状态异常
     - 无需回滚，状态确定性转移
     - 对象析构、``deallocate``、``swap``、移动构造与三指针提交

栈展开 (Stack Unwinding) 与零开销异常模型
-----------------------------------------

现代 64 位平台（如 x86-64 System V ABI 与 Windows x64）广泛采用基于 DWARF / SEH 的 **零开销异常模型（Zero-Cost Exception Model）**。

物理工作机制与指令路径分流
~~~~~~~~~~~~~~~~~~~~~~~~~~

在此模型下，“零开销”意味着当程序正常执行且无异常抛出时，进入和退出 ``try`` 块无需执行任何额外的 CPU 指令（无运行时入栈或全局链表注册开销）。异常开销被全量转移至异常发生时的冷路径（Cold Path）：

1. **编译期元数据生成**：编译器为每个函数生成只读的异常解卷表（Unwind Table，存储于 ELF 的 ``.eh_frame`` 与 ``.gcc_except_table`` 段中）。表中记录了指令指针（Instruction Pointer, IP）区间与局部对象生命周期、Landing Pad（着陆区）入口地址的映射关系。
2. **异常抛出入口（``__cxa_throw``）**：当执行 ``throw`` 表达式时，运行时库在全局堆上分配异常对象存储，随后调用栈展开引擎（如 ``_Unwind_RaiseException``）。
3. **两阶段查找与栈展开（Two-Phase Unwinding）**：
   - **阶段一：搜索阶段（Search Phase）**：解卷引擎沿调用栈自顶向下遍历调用帧，查询各帧的异常表，寻找能够匹配该异常类型的 ``catch`` 处理器。若遍历至栈底仍未找到匹配项，直接调用 ``std::terminate()``。
   - **阶段二：清理展开阶段（Cleanup Phase）**：解卷引擎再次自顶向下遍历调用帧，依次跳转至各帧对应的 Landing Pad，按对象构造的逆序逐一调用当前作用域内局部对象的析构函数（RAII 释放），直至控制流安全抵达匹配的 ``catch`` 块。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             零开销异常模型与栈展开 (Stack Unwinding) 流程                             |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 正常指令执行路径 (Zero Cost Happy Path) ]                                                         |
   |     main() ---> funcA() ---> funcB() ---> 执行物理操作 (无额外 try 注册开销)                          |
   |                                                |                                                      |
   |                                                v 发生 throw MyException()                             |
   |   [ 异常触发: __cxa_throw ]                    |                                                      |
   |                                                v                                                      |
   |   [ Phase 1: Search Phase ]                    |                                                      |
   |     遍历 .eh_frame 寻找到 main() 中包含匹配的 catch(MyException) 处理块                              |
   |                                                |                                                      |
   |   [ Phase 2: Cleanup Phase (栈展开执行) ]      v                                                      |
   |     1. funcB 栈帧: 跳转至 Landing Pad -> 逆序析构 funcB 内部局部 RAII Guard 与对象                    |
   |     2. 销毁 funcB 栈帧，回退至 funcA                                                                  |
   |     3. funcA 栈帧: 跳转至 Landing Pad -> 逆序析构 funcA 内部局部 Guard 与对象                         |
   |     4. 销毁 funcA 栈帧，回退至 main                                                                   |
   |     5. 进入 main() 的 catch 块正常执行后续代码                                                        |
   |                                                                                                       |
   |   * 致命边界：若在 Landing Pad 执行析构期间，某个析构函数再次抛出异常，触发 std::terminate() 立即崩溃。 |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

noexcept 说明符与 move_if_noexcept 编译期条件降级
------------------------------------------------------

在 C++11 引入移动语义后，异常安全与性能优化产生了直接的物理交集。``noexcept`` 说明符是连接类型特征与容器异常安全策略的关键桥梁。

noexcept 的双重语义：说明符与运算符
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **说明符（Specifier）**：声明于函数签名尾部（如 ``void swap(T& a, T& b) noexcept``），向编译器和调用方承诺该函数不会抛出异常。
2. **运算符（Operator）**：``noexcept(expr)`` 属于编译期运算符，在编译期静态判定表达式 ``expr`` 是否被声明为不抛异常，求值结果为 ``bool`` 常量：

.. code-block:: cpp

   template <typename T>
   void safe_swap(T& a, T& b) noexcept(noexcept(T(std::move(a))) &&
                                       noexcept(a = std::move(b))) {
       T temp(std::move(a));
       a = std::move(b);
       b = std::move(temp);
   }

编译期优化效应
~~~~~~~~~~~~~~

当函数被标记为 ``noexcept`` 时，编译器可以执行确定性的二进制优化：

- **剔除 Landing Pad 与解卷表项**：编译器确认该函数内部不会向外逃逸异常，因此无需在该函数的作用域生成复杂的异常捕获展开元数据，精简生成的目标代码体积。
- **内联展开与指令重排**：优化器在缺乏潜在异常抛出边界（Potentially Throwing Edges）的控制流图（CFG）中，能够更大胆地执行跨指令调度、公共子表达式消除与寄存器分配。

std::move_if_noexcept 的决策逻辑与源码实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::move_if_noexcept`` 专为标准容器的扩容与重排设计。其核心任务是在 **零拷贝移动性能** 与 **强异常安全保证** 之间建立编译期静态裁决：

.. code-block:: cpp

   template <typename T>
   constexpr std::conditional_t<
       !std::is_nothrow_move_constructible_v<T> && std::is_copy_constructible_v<T>,
       const T&,
       T&&
   > move_if_noexcept(T& x) noexcept {
       return std::move(x);
   }

决策分支分析：

1. **分支一：类型具备不抛移动构造（``is_nothrow_move_constructible_v<T> == true``）**：
   - 返回 ``T&&``（右值引用）。
   - 物理效果：容器扩容时安全执行移动构造，获得极速指针窃取性能，且由于移动过程绝不抛出异常，强保证天然成立。
2. **分支二：类型移动构造可能抛出，但具备拷贝构造（``!is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>``）**：
   - 返回 ``const T&``（左值常量引用）。
   - 物理效果：容器扩容时主动放弃移动语义，降级为执行深拷贝构造。若拷贝过程中发生异常，原缓冲区内的源对象完好无损，容器可安全执行事务回滚，维持强保证。
3. **分支三：类型属于纯移动类型且移动可能抛出（Move-Only Throwing: ``!is_nothrow_move_constructible_v<T> && !is_copy_constructible_v<T>``）**：
   - 返回 ``T&&``（右值引用）。
   - 物理效果：由于类型已显式删除（delete）拷贝构造函数，容器别无选择，只能强行调用可能抛出的移动构造函数。此时若发生异常，容器的强异常安全保证将被破坏，降级为基本保证（部分旧对象可能处于 moved-from 状态）。

.. list-table:: std::move_if_noexcept 编译期分支决策与异常安全保证矩阵
   :widths: 22 20 20 38
   :header-rows: 1
   :class: tight-table

   * - 元素类型移动特征
     - 元素类型拷贝特征
     - 萃取返回引用类型
     - 容器扩容所获异常安全保证等级
   * - ``noexcept`` 移动
     - 任意（可拷贝或不可拷贝）
     - ``T&&`` (右值引用)
     - 强保证 (Strong Guarantee) + 最高性能
   * - 可能抛出移动
     - 支持拷贝构造
     - ``const T&`` (常量左值)
     - 强保证 (Strong Guarantee)（通过降级拷贝实现）
   * - 可能抛出移动
     - 删除拷贝构造 (Move-Only)
     - ``T&&`` (右值引用)
     - 降级为基本保证 (Basic Guarantee)

两阶段提交模型与 std::vector 扩容事务状态机
-------------------------------------------

``std::vector`` 在执行追加（``push_back`` / ``emplace_back``）或插入（``insert``）时，若当前元素数量达到了底层分配的容量上限（即 ``finish_ == end_of_storage_``），必须触发重新分配与元素迁移。为了向调用方提供强异常安全保证，标准库实现严格遵循 **两阶段提交（Two-Phase Commit, 2PC）** 状态机。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                       std::vector 扩容两阶段提交 (2PC) 与异常回滚流转拓扑                             |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 原容器状态 (三指针未动) ]                                                                         |
   |   start_                                      finish_                    end_of_storage_              |
   |     |                                            |                              |                     |
   |     v                                            v                              v                     |
   |   +--------------------------------------------+------------------------------+                       |
   |   |  Elem 0  |  Elem 1  |  ...  |  Elem N-1    |      (已耗尽的空闲空间)      |                       |
   |   +--------------------------------------------+------------------------------+                       |
   |                                                                                                       |
   |   ==================== 阶段一：准备阶段 (Preparation Phase - 隔离沙盒) ====================          |
   |                                                                                                       |
   |   1. 申请全新连续物理内存: new_start = AllocTraits::allocate(alloc, new_capacity)                     |
   |   2. 挂载 RAII Buffer Guard: RawBufferGuard guard(alloc, new_start, new_capacity)                     |
   |   3. 构造新增元素: AllocTraits::construct(alloc, new_start + insert_idx, forward<Args>(args)...)     |
   |   4. 迁移旧元素 (按 move_if_noexcept 规则):                                                           |
   |      - 迁移前缀区间 [start_, insert_pos)  ---> [new_start, new_start + insert_idx)                     |
   |      - 迁移后缀区间 [insert_pos, finish_) ---> [new_start + insert_idx + 1, ...)                      |
   |                                                                                                       |
   |          |                                                            |                               |
   |          | 若步骤 1~4 中任意一步抛出异常                              | 全部准备工作无异常成功完成    |
   |          v                                                            v                               |
   |   [ 异常分支: 自动回滚 (Rollback) ]                           [ 准备就绪: 步入提交点 ]                |
   |   - Guard 析构自动触发:                                                                               |
   |     a. 逆序析构新内存中已构造的对象                           ======================================= |
   |     b. deallocate 释放全新物理内存                            阶段二：提交阶段 (Commit Phase - No-throw)|
   |   - 原容器三指针完全未被修改                                  ======================================= |
   |   - 原容器旧元素状态完好无损                                  1. 析构原存储内旧元素                   |
   |   - 向外重抛异常 (强保证达成)                                 2. 释放原存储物理内存                   |
   |                                                               3. 提交三指针原子赋值:                  |
   |                                                                  start_ = new_start;                  |
   |                                                                  finish_ = new_finish;                |
   |                                                                  end_of_storage_ = new_end;           |
   |                                                               4. guard.release() 解除守卫             |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

扩容执行阶段分解
~~~~~~~~~~~~~~~~

1. **准备阶段（Preparation Phase - 隔离操作）**：
   - 计算几何增长后的新容量（通常为旧容量的 1.5 倍或 2 倍），通过分配器申请新内存块 ``new_start``。
   - 立即建立栈上 RAII 事务守卫（``RawBufferGuard``），由其代理新内存的所有权与已构造元素计数。
   - 在新内存的目标偏移处就地放置构造新插入的元素。
   - 遍历原容器中的已有元素，使用 ``std::move_if_noexcept`` 将其依次构造到新内存的对应位置。
   - **关键特性**：在此阶段，原容器的内部成员指针（``start_``、``finish_``、``end_of_storage_``）完全保持原值，处于受保护状态。
2. **提交点（Commit Point - 零风险切换）**：
   - 当新内存上的所有元素（包括新增元素与迁移元素）全部成功构造后，进入提交点。
   - 提交点内的所有操作必须具备 **不抛保证（``noexcept``）**。
   - 依次析构旧内存中的原元素，调用分配器释放旧存储。
   - 更新容器的成员指针，使其正式指向新存储的首尾地址。
   - 调用 ``guard.release()`` 解除守卫的自动析构责任。

节点式容器与关联容器的异常安全拓扑
----------------------------------

与连续内存容器（``std::vector``、``std::deque``）不同，节点式容器（Node-based Containers，如 ``std::list``、``std::forward_list``、``std::map``、``std::set``、``std::unordered_map``）在物理内存中呈现离散分布的拓扑结构。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             节点式容器单节点隔离分配与异常安全拓扑                                    |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 步骤 1: 孤岛节点分配与构造 (Isolated Allocation) ]                                                |
   |     Node* p = NodeAlloc::allocate(1);                                                                 |
   |     NodeAlloc::construct(p, key, value);  <--- 若构造或比较抛出异常，立即释放 p，主结构分毫不损       |
   |                                                                                                       |
   |   [ 步骤 2: 查找插入拓扑位置 (Tree/List Traversal) ]                                                  |
   |     auto [parent, insert_pos] = find_insert_location(key);                                            |
   |                                                                                                       |
   |   [ 步骤 3: 指针重新链接与平衡修复 (No-throw Linkage & Rebalance) ]                                   |
   |     - 纯指针赋值操作 (p->left = ..., parent->right = p, p->color = RED)                               |
   |     - 红黑树左旋/右旋平衡修复 (严禁抛出异常，noexcept)                                                |
   |                                                                                                       |
   |   [ 步骤 4: 递增节点计数器 (Commit) ]                                                                 |
   |     ++node_count_;                                                                                    |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

单节点隔离分配的天然强保证优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

节点式容器在插入单个元素时，具备天然的强异常安全优势：

1. **内存分配故障隔离**：插入新元素时，容器仅需分配一个孤立的节点结构体（包含数据与链接指针）。若此时分配器抛出 ``std::bad_alloc``，原容器的节点链表拓扑未受到任何接触。
2. **元素构造故障隔离**：在未连接到主链表或主树结构之前，新节点处于“孤岛”状态。若用户数据类型的构造函数抛出异常，容器通过局部 catch 或 RAII 守卫直接销毁该孤岛节点并释放其内存，主数据结构保持绝对完整。
3. **指针挂载原子性**：节点构造完毕后，将其插入红黑树或双向链表的操作仅涉及纯粹的指针赋值（Pointer Swizzling）与着色旋转。这些指针操作均具备严格的 ``noexcept`` 语义，操作一旦开始便必定成功提交。

哈希容器与节点重排（Rehash）的异常边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 ``std::unordered_map`` 等哈希容器：

- **哈希函数与等价谓词的异常风险**：若用户自定义的 Hash 仿函数或 Key 比较谓词在插入或查找时抛出异常，容器必须保证内部桶数组（Bucket Array）与已有节点链表不发生断裂。
- **动态扩容 Rehash 的异常安全**：当负载因子超标触发 rehash 时，标准库实现通常先分配全新的桶指针数组。在将旧节点逐个重新哈希并挂载到新桶数组的过程中，由于节点本身已经存在，无需重新构造数据对象。若 Hash 函数计算抛出异常，容器需要能够安全回滚或维持基本保证。

工业级带事务回滚的 Mini-Vector 完整实现
----------------------------------------

本节给出一个完整的工业级 C++17/20 生产级实现：构建一个具备完整强异常安全保证、两阶段提交事务机制、``noexcept`` 条件移动降级判定与精确回滚守卫的 ``MiniVector<T, Alloc>``。

.. code-block:: cpp

   #include <cstddef>
   #include <cstdlib>
   #include <iostream>
   #include <limits>
   #include <memory>
   #include <new>
   #include <stdexcept>
   #include <type_traits>
   #include <utility>

   namespace engine::core {

   // =========================================================================
   // 1. 工业级未初始化存储事务回滚守卫：TransactionBufferGuard
   // =========================================================================
   template <typename T, typename Alloc>
   class TransactionBufferGuard {
   public:
       using AllocTraits = std::allocator_traits<Alloc>;

       TransactionBufferGuard(Alloc& alloc, std::size_t capacity)
           : alloc_(alloc),
             storage_(nullptr),
             capacity_(capacity),
             constructed_count_(0),
             committed_(false) {
           if (capacity_ > 0) {
               storage_ = AllocTraits::allocate(alloc_, capacity_);
           }
       }

       ~TransactionBufferGuard() noexcept {
           if (!committed_ && storage_) {
               // 回滚路径：严格按逆序析构所有已成功构造的新对象
               for (std::size_t i = constructed_count_; i > 0; --i) {
                   AllocTraits::destroy(alloc_, storage_ + (i - 1));
               }
               // 释放已申请的原始连续内存块
               AllocTraits::deallocate(alloc_, storage_, capacity_);
           }
       }

       TransactionBufferGuard(const TransactionBufferGuard&) = delete;
       TransactionBufferGuard& operator=(const TransactionBufferGuard&) = delete;

       [[nodiscard]] T* get() const noexcept { return storage_; }

       void notify_constructed() noexcept {
           ++constructed_count_;
       }

       // 事务成功提交：解除守卫对新存储的析构与释放责任
       T* release() noexcept {
           committed_ = true;
           return storage_;
       }

   private:
       Alloc&      alloc_;
       T*          storage_;
       std::size_t capacity_;
       std::size_t constructed_count_;
       bool        committed_;
   };

   // =========================================================================
   // 2. 强异常安全 MiniVector 实现 (遵循两阶段提交与 noexcept 决策模型)
   // =========================================================================
   template <typename T, typename Alloc = std::allocator<T>>
   class MiniVector {
   public:
       using value_type      = T;
       using allocator_type  = Alloc;
       using size_type       = std::size_t;
       using difference_type = std::ptrdiff_t;
       using reference       = value_type&;
       using const_reference = const value_type&;
       using pointer         = typename std::allocator_traits<Alloc>::pointer;
       using const_pointer   = typename std::allocator_traits<Alloc>::const_pointer;
       using AllocTraits     = std::allocator_traits<Alloc>;

       MiniVector() noexcept(noexcept(Alloc()))
           : alloc_(), start_(nullptr), finish_(nullptr), end_of_storage_(nullptr) {}

       explicit MiniVector(const Alloc& alloc) noexcept
           : alloc_(alloc), start_(nullptr), finish_(nullptr), end_of_storage_(nullptr) {}

       ~MiniVector() noexcept {
           clear_and_deallocate();
       }

       // 禁用拷贝以保持代码聚焦，重点展示移动与强异常安全插入
       MiniVector(const MiniVector&) = delete;
       MiniVector& operator=(const MiniVector&) = delete;

       MiniVector(MiniVector&& other) noexcept
           : alloc_(std::move(other.alloc_)),
             start_(other.start_),
             finish_(other.finish_),
             end_of_storage_(other.end_of_storage_) {
           other.start_ = nullptr;
           other.finish_ = nullptr;
           other.end_of_storage_ = nullptr;
       }

       MiniVector& operator=(MiniVector&& other) noexcept {
           if (this != &other) {
               clear_and_deallocate();
               alloc_ = std::move(other.alloc_);
               start_ = other.start_;
               finish_ = other.finish_;
               end_of_storage_ = other.end_of_storage_;
               other.start_ = nullptr;
               other.finish_ = nullptr;
               other.end_of_storage_ = nullptr;
           }
           return *this;
       }

       [[nodiscard]] size_type size() const noexcept {
           return static_cast<size_type>(finish_ - start_);
       }

       [[nodiscard]] size_type capacity() const noexcept {
           return static_cast<size_type>(end_of_storage_ - start_);
       }

       [[nodiscard]] bool empty() const noexcept {
           return start_ == finish_;
       }

       reference operator[](size_type idx) noexcept {
           return start_[idx];
       }

       const_reference operator[](size_type idx) const noexcept {
           return start_[idx];
       }

       // ---------------------------------------------------------------------
       // 强异常安全保证扩容预留：reserve
       // ---------------------------------------------------------------------
       void reserve(size_type new_cap) {
           if (new_cap <= capacity()) {
               return;
           }
           reallocate_exact(new_cap);
       }

       // ---------------------------------------------------------------------
       // 强异常安全保证追加：emplace_back
       // ---------------------------------------------------------------------
       template <typename... Args>
       reference emplace_back(Args&&... args) {
           if (finish_ != end_of_storage_) {
               // 快速路径：现有容量充足，直接在尾部未初始化内存构造
               AllocTraits::construct(alloc_, finish_, std::forward<Args>(args)...);
               reference ref = *finish_;
               ++finish_; // 不抛提交
               return ref;
           }

           // 慢速路径：容量耗尽，触发两阶段提交几何扩容
           const size_type old_size = size();
           const size_type new_cap = (old_size == 0) ? 1 : old_size * 2;
           return reallocate_emplace_back(new_cap, std::forward<Args>(args)...);
       }

       void push_back(const T& value) {
           emplace_back(value);
       }

       void push_back(T&& value) {
           emplace_back(std::move(value));
       }

   private:
       // ---------------------------------------------------------------------
       // 核心事务状态机：reallocate_emplace_back
       // ---------------------------------------------------------------------
       template <typename... Args>
       reference reallocate_emplace_back(size_type new_cap, Args&&... args) {
           const size_type old_size = size();

           // 阶段一：准备阶段 (在隔离的 TransactionBufferGuard 中分配与构造)
           TransactionBufferGuard<T, Alloc> guard(alloc_, new_cap);
           T* new_storage = guard.get();

           // 1. 先在新内存末尾偏移处构造新增元素
           AllocTraits::construct(alloc_, new_storage + old_size, std::forward<Args>(args)...);
           guard.notify_constructed();

           // 2. 迁移已有旧元素 (根据 move_if_noexcept 判定走移动或拷贝)
           for (size_type i = 0; i < old_size; ++i) {
               AllocTraits::construct(
                   alloc_,
                   new_storage + i,
                   std::move_if_noexcept(start_[i])
               );
               guard.notify_constructed();
           }

           // 阶段二：提交阶段 (新状态全部就绪，执行不抛原子切换)
           T* old_start = start_;
           T* old_finish = finish_;
           size_type old_cap = capacity();

           start_ = new_storage;
           finish_ = new_storage + old_size + 1;
           end_of_storage_ = new_storage + new_cap;

           guard.release(); // 提交成功，解除守卫

           // 阶段三：清理阶段 (安全释放原存储)
           if (old_start) {
               for (T* p = old_start; p != old_finish; ++p) {
                   AllocTraits::destroy(alloc_, p);
               }
               AllocTraits::deallocate(alloc_, old_start, old_cap);
           }

           return *(finish_ - 1);
       }

       void reallocate_exact(size_type new_cap) {
           const size_type old_size = size();
           TransactionBufferGuard<T, Alloc> guard(alloc_, new_cap);
           T* new_storage = guard.get();

           for (size_type i = 0; i < old_size; ++i) {
               AllocTraits::construct(
                   alloc_,
                   new_storage + i,
                   std::move_if_noexcept(start_[i])
               );
               guard.notify_constructed();
           }

           T* old_start = start_;
           T* old_finish = finish_;
           size_type old_cap = capacity();

           start_ = new_storage;
           finish_ = new_storage + old_size;
           end_of_storage_ = new_storage + new_cap;

           guard.release();

           if (old_start) {
               for (T* p = old_start; p != old_finish; ++p) {
                   AllocTraits::destroy(alloc_, p);
               }
               AllocTraits::deallocate(alloc_, old_start, old_cap);
           }
       }

       void clear_and_deallocate() noexcept {
           if (start_) {
               for (T* p = start_; p != finish_; ++p) {
                   AllocTraits::destroy(alloc_, p);
               }
               AllocTraits::deallocate(alloc_, start_, static_cast<size_type>(end_of_storage_ - start_));
               start_ = nullptr;
               finish_ = nullptr;
               end_of_storage_ = nullptr;
           }
       }

       Alloc   alloc_;
       T*      start_;
       T*      finish_;
       T*      end_of_storage_;
   };

   } // namespace engine::core
```

异常故障注入与事务一致性验证
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为验证上述 ``MiniVector`` 在异常抛出时的强异常安全保证与回滚完整性，设计以下具有确定性抛出注入能力的测试结构体：

.. code-block:: cpp

   #include <cassert>
   #include <iostream>
   #include <string>

   namespace test {

   struct FaultInjectionItem {
       static inline int live_instances = 0;
       static inline int throw_countdown = -1; // 负数表示不抛出

       int id;
       std::string tag;

       FaultInjectionItem(int i, std::string t) : id(i), tag(std::move(t)) {
           check_and_throw();
           ++live_instances;
       }

       FaultInjectionItem(const FaultInjectionItem& other) : id(other.id), tag(other.tag) {
           check_and_throw();
           ++live_instances;
       }

       // 移动构造声明为可能抛出，强制测试回滚链路
       FaultInjectionItem(FaultInjectionItem&& other) noexcept(false)
           : id(other.id), tag(std::move(other.tag)) {
           check_and_throw();
           ++live_instances;
       }

       ~FaultInjectionItem() noexcept {
           --live_instances;
       }

   private:
       void check_and_throw() {
           if (throw_countdown > 0) {
               --throw_countdown;
               if (throw_countdown == 0) {
                   throw std::runtime_error("Simulated Fault Injection: Constructor Failed!");
               }
           }
       }
   };

   void run_strong_exception_safety_test() {
       using namespace engine::core;

       MiniVector<FaultInjectionItem> vec;
       vec.emplace_back(101, "Node_A");
       vec.emplace_back(102, "Node_B");
       vec.emplace_back(103, "Node_C");

       assert(vec.size() == 3);
       assert(FaultInjectionItem::live_instances == 3);

       // 设置在下一次构造时（即扩容迁移或构造新元素时）触发异常
       FaultInjectionItem::throw_countdown = 2;

       bool exception_caught = false;
       try {
           // 此操作将触发扩容 (容量由 4 扩容至 8 或类似)，并在迁移过程中抛出异常
           vec.emplace_back(104, "Node_D_Bomb");
       } catch (const std::runtime_error& e) {
           exception_caught = true;
       }

       // 验证强异常安全契约：
       // 1. 成功捕获异常
       assert(exception_caught);
       // 2. 容器内部状态未发生任何改变 (大小依然为 3)
       assert(vec.size() == 3);
       assert(vec[0].id == 101 && vec[0].tag == "Node_A");
       assert(vec[1].id == 102 && vec[1].tag == "Node_B");
       assert(vec[2].id == 103 && vec[2].tag == "Node_C");
       // 3. 活跃对象实例计数完全平衡，临时对象已全量逆序析构，零内存泄漏
       assert(FaultInjectionItem::live_instances == 3);
   }

   } // namespace test

小结与下章导读
--------------

本章系统解构了现代 C++ STL 的异常安全保证体系与底层事务回滚机制：从基本保证（状态自洽与零泄漏）、强保证（提交或回滚事务一致性）到不抛保证（物理基石约束）的三级契约分层；从零开销异常模型在 DWARF ``.eh_frame`` 与 Landing Pad 中的展开机制，到 ``noexcept`` 说明符与运算符对编译器优化和代码生成的影响；从 ``std::move_if_noexcept`` 基于 ``is_nothrow_move_constructible`` 的编译期条件降级策略，到 ``std::vector`` 几何扩容中的两阶段提交（2PC）状态机与三指针原子切换；从离散节点容器（list/map）依托孤岛节点分配实现的天然强异常安全，到 RAII 事务守卫对未初始化内存构造的精确逆序析构与释放管理；最终通过工业级带故障注入测试的 Mini-Vector 完成了底层状态机的工程闭环。

在掌握了迭代器、静态与多态内存分配器以及异常安全防御体系后，下一章我们将深入 STL 架构设计的灵魂支柱 —— **泛型算法解耦哲学：半开区间 [first, last) 几何契约、迭代器操作分发与可插入策略设计（``02_stl_core_mechanisms_and_allocators/05_generic_algorithm_decoupling_philosophy.rst``）**，剖析半开区间不变量在边界防护与空区间处理中的数学优雅性，以及算法与容器物理存储彻底分离的模板策略模型。
