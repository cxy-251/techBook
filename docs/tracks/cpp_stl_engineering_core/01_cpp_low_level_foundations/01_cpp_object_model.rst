================================================================================
C++ 底层对象模型与内存布局：身份、存储期、对齐与虚表拓扑
================================================================================

.. note:: 前置背景与上下文承接
   本章作为《现代C++对象模型与STL工程内核全景深度剖析》的开篇基石，直接从计算机体系结构的物理内存拓扑、CPU 寻址约束与 C++ 语言标准的底层对象模型切入。理解对象在内存中的连续字节分布、对齐规则、生命周期边界与多态分发机制，是深入解构 STL 容器内存布局、分配器策略、迭代器抽象以及异常安全保证的前提。

C++ 程序在运行时的物理本质是操作系统的虚拟地址空间中被划分出的连续内存区域。C++ 编译器并不把“类（Class）”作为一个运行时实体保留，而是将其转化为纯粹的内存排布拓扑、偏移量常量（Offset Constants）以及指向机器指令的函数符号。标准库（STL）中所有容器与算法的吞吐性能、内存利用率和边界安全，均直接受制于 C++ 底层对象模型的物理约束。

对象身份、存储期与有效对象
--------------------------

在 C++ 语言规范与底层编译模型中，“对象（Object）”被定义为占据一段特定大小的连续存储空间（Storage）、拥有确定的数据类型（Type）、并且具备明确生命周期的物理实体。

.. list-table:: C++ 四大存储期物理特征与生命周期边界
   :widths: 15 25 35 25
   :header-rows: 1
   :class: tight-table

   * - 存储期类型
     - 物理内存驻留区域
     - 分配与初始化时机
     - 销毁与内存释放路径
   * - 静态存储期 (Static)
     - 数据段 (``.data``) 或 BSS 段 (``.bss``)
     - 程序启动阶段（或首次进入声明所在的作用域）完成构造
     - 程序退出 (``std::exit`` / ``main`` 返回) 时逆序析构
   * - 线程局部存储期 (Thread-Local)
     - 线程本地存储段 (TLS / ``fs/gs`` 寄存器基址偏移)
     - 线程创建并首次执行到对应控制流时初始化
     - 线程终止 (``pthread_exit`` / 线程函数返回) 时析构
   * - 自动存储期 (Automatic)
     - 线程执行栈帧 (Stack Frame, ``RSP/RBP`` 界定)
     - 执行流进入变量声明所在的作用域块时分配栈槽
     - 执行流离开作用域块时严格按声明逆序执行析构
   * - 动态存储期 (Dynamic)
     - 进程用户堆 (Heap / ``mmap`` / ``brk`` 分配区)
     - 由内存分配操作（如 ``malloc`` / ``operator new``）显式申请
     - 由显式释放操作（如 ``free`` / ``operator delete``）归还

对象的身份（Identity）由其在虚拟内存空间中的首字节地址唯一标识。不同对象在同一时刻必须具备互不相同的内存地址，唯一的语言特例是“空基类优化（Empty Base Optimization, EBO）”与 C++20 引入的 ``[[no_unique_address]]`` 属性修饰成员。

.. code-block:: cpp

   #include <iostream>
   #include <cstdint>

   struct Empty {};

   struct Derived : public Empty {
       int32_t value; // 占据 4 字节
   };

   struct NonEBO {
       Empty e;       // 占据 1 字节
       int32_t value; // 占据 4 字节，前置 3 字节 padding
   };

在 x86-64 体系下，``sizeof(Derived)`` 为 4 字节，编译器应用 EBO 将基类 ``Empty`` 偏移量折叠至偏移 0；而 ``sizeof(NonEBO)`` 为 8 字节，成员 ``e`` 必须分配独立地址（占据 1 字节并产生 3 字节内存填充），以维持不同子对象的物理身份独立性。

对齐、Padding 与 sizeof 物理推导
--------------------------------

现代 CPU 架构通过 64 位或 128 位宽的数据总线从多级缓存（L1/L2/L3 Cache）中批量吞吐数据。若一个 $N$ 字节的数据类型存放于不能被 $N$ 整除的物理地址上，将触发跨缓存行（Cache Line Split）访问，导致 CPU 执行两次内存总线事务并执行移位合并，严重降低吞吐率，甚至在某些 RISC 架构（如 ARM / MIPS）上直接引发硬件对齐陷阱（Alignment Fault）。

C++ 编译器通过以下两条硬性数学约束确定复合结构体的内存布局：

1. **成员对齐约束**：结构体内每个成员相对于结构体首地址的偏移量（Offset），必须能被该成员自身的自然对齐值（``alignof(T)``）整除。若不满足，编译器在成员前自动插入未初始化填充字节（Padding Bytes）。
2. **结构体整体对齐约束**：结构体的总尺寸（``sizeof(Struct)``）必须能被其所有成员中最大的对齐值整除。若尾部存在空隙，编译器在结构体尾部插入 Tail Padding，以确保结构体数组中所有连续元素的起始地址均满足对齐要求。

.. list-table:: 典型基本数据类型在 x86-64 System V ABI 下的对齐与尺寸
   :widths: 20 20 20 40
   :header-rows: 1
   :class: tight-table

   * - 数据类型
     - 占用字节数 (sizeof)
     - 对齐要求 (alignof)
     - 物理地址合法性条件
   * - ``char / uint8_t``
     - 1 字节
     - 1 字节
     - 任意字节地址
   * - ``short / int16_t``
     - 2 字节
     - 2 字节
     - ``Address % 2 == 0``
   * - ``int / int32_t / float``
     - 4 字节
     - 4 字节
     - ``Address % 4 == 0``
   * - ``int64_t / double / pointer``
     - 8 字节
     - 8 字节
     - ``Address % 8 == 0``
   * - ``__m128 / long double``
     - 16 字节
     - 16 字节
     - ``Address % 16 == 0``

分析以下复合结构体的实际内存分布：

.. code-block:: cpp

   struct BadLayout {
       char a;       // offset 0, size 1. [padding: 3 字节]
       int b;        // offset 4, size 4.
       short c;      // offset 8, size 2. [padding: 6 字节]
       double* ptr;  // offset 16, size 8.
   }; // 总尺寸 = 24 字节，有效载荷 = 15 字节，浪费 = 9 字节 (37.5%)

   struct OptimizedLayout {
       double* ptr;  // offset 0, size 8.
       int b;        // offset 8, size 4.
       short c;      // offset 12, size 2.
       char a;       // offset 14, size 1. [tail padding: 1 字节]
   }; // 总尺寸 = 16 字节，有效载荷 = 15 字节，浪费 = 1 字节 (6.25%)

STL 内部的 ``std::pair``、``std::tuple`` 与容器节点通过模板元编程重排继承顺序或应用内存紧凑技术，正是为了压榨此处的 Padding 空间，降低缓存缺失率。

栈对象、堆对象与所有权边界
--------------------------

对象在不同内存区域的实例化路径决定了其析构清理责任的所有权归属。

.. list-table:: 栈对象与堆对象的物理机制与生命周期对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 判定维度
     - 栈上对象 (Automatic Storage)
     - 堆上对象 (Dynamic Storage)
   * - 分配成本
     - 单条 CPU 指令移动栈指针 (``sub rsp, N``)，耗时 < 1 纳秒
     - 涉及堆管理器空闲链表检索、锁竞争与系统调用，耗时数十至数百纳秒
   * - 寻址效率
     - 极高。栈顶内存大概率常驻 CPU L1 Data Cache
     - 易引发缓存缺失与内存碎片（Heap Fragmentation）
   * - 销毁确定性
     - 严格受编译器控制。栈展开（Stack Unwinding）保证逆序析构
     - 必须显式调用 ``delete``，若所有权断裂直接导致物理内存泄漏
   * - STL 容器承载
     - 容器本身常作为栈对象分配（如 ``std::vector`` 控制块占据 24 字节栈空间）
     - 容器内部元素存储于堆内存区，由容器析构函数负责封锁生命周期

STL 容器设计的核心哲学即是 **RAII（Resource Acquisition Is Initialization）**：将堆内存的所有权绑定至栈对象的生命周期中。当包含堆指针的栈上容器超出作用域时，其析构函数被调用栈展开机制强制触发，进而遍历销毁堆上的每一个元素并调用 ``deallocate`` 归还底层连续虚拟地址空间。

this 指针、成员函数与对象状态
------------------------------

在编译后的二进制代码中，非静态成员函数与普通全局函数在指令形态上完全一致。编译器通过执行 **Name Mangling（名字修饰）** 将类名与参数类型编码入符号名，并隐式将调用该函数的对象地址作为首个参数传递。

在 x86-64 System V AMD64 ABI 约定下，首个整型/指针参数通过 ``RDI`` 寄存器传递。成员函数内部的 ``this`` 指针即是存放于 ``RDI`` 中的物理地址。

.. code-block:: cpp

   class Counter {
       int32_t value{0};
   public:
       void increment(int32_t step) {
           this->value += step;
       }
   };

   // 编译后的汇编等价逻辑：
   // void _ZN7Counter9incrementEi(Counter* const this [[rdi]], int32_t step [[esi]]) {
   //     mov eax, dword ptr [rdi]
   //     add eax, esi
   //     mov dword ptr [rdi], eax
   //     ret
   // }

成员函数本身不占据类实例对象的任何存储空间。类对象的尺寸完全由非静态数据成员、虚表指针以及对齐填充决定。

虚函数表与多态对象布局 (vptr & vtable)
--------------------------------------

当一个类声明或继承了至少一个虚函数（``virtual``）时，编译器在对象头部隐式插入一个虚表指针（Virtual Table Pointer, 简称 ``vptr``）。

在 Itanium C++ ABI（Linux / macOS Clang & GCC 通用规范）中，对象的内存布局遵从以下拓扑：

1. **vptr 插入位置**：``vptr`` 位于对象内存空间的最起始偏移量（Offset 0），占据 8 字节（64 位系统）。
2. **虚函数表 (vtable) 结构**：虚表是位于只读数据段（``.rodata``）的函数指针数组。其负偏移量处存放 RTTI（运行时类型信息，``std::type_info``）指针与 ``offset-to-top``（基类偏移修正量）；正偏移量处按声明顺序存放各虚函数的物理入口地址。
3. **动态分发开销**：多态虚函数调用 ``ptr->virtual_func()`` 转化为两次内存间接寻址指令：
   
   $$	ext{Call Target} = *(*(ptr + 0) + 	ext{Index} 	imes 8)$$

.. code-block:: text

   +-------------------------------------------------------------+
   | 单继承多态对象物理内存拓扑 (Base -> Derived)                |
   +-------------------------------------------------------------+
   | Offset 0:  vptr [8 Bytes] ------> +-----------------------+ |
   |                                   | -16: Offset-to-top(0) | |
   |                                   | -8:  typeinfo pointer | |
   |                                   |  0:  &Derived::funcA  | |
   |                                   |  8:  &Derived::funcB  | |
   |                                   +-----------------------+ |
   | Offset 8:  Base::member1   [4 Bytes]                        |
   | Offset 12: Base::member2   [4 Bytes]                        |
   | Offset 16: Derived::member3[8 Bytes]                        |
   +-------------------------------------------------------------+

多重继承与虚继承引入更复杂的 ``this`` 指针偏移调整（Thunk 机制）与虚基类表指针（``vbtbl / vbase_offset``），导致对象尺寸显著膨胀并破坏连续内存局部性。

对象模型对 STL 实现的物理约束
------------------------------

C++ 标准库的设计全面围绕底层对象模型展开，形成了极其严苛的工程实现边界：

1. **禁止在容器内部存储多态切片对象**：
   若将派生类对象直接存入 ``std::vector<Base>``，由于 ``vector`` 按 ``sizeof(Base)`` 连续划分内存槽位，写入派生类时仅会拷贝基类成员并覆盖 ``vptr``（发生对象切片 Object Slicing），导致派生类特有成员被物理截断。因此多态集合必须通过指针容器 ``std::vector<std::unique_ptr<Base>>`` 实现。

2. **Trivially Copyable 类型的极致汇编特化**：
   若对象满足 ``std::is_trivially_copyable<T>::value``（无自定义拷贝构造、无虚函数、无非平凡成员），STL 算法（如 ``std::copy``）与容器扩容操作通过 SFINAE / Concepts 自动分支至底层 ``std::memmove`` 或 CPU 向量化搬运指令，彻底规避逐元素调用构造函数的函数调用开销。

3. **内存分配与构造解耦 (Uninitialized Memory)**：
   标准库容器绝不在申请内存时直接调用 ``new T[N]``（这会强制触发默认构造），而是使用 ``allocator::allocate`` 申请原始未初始化字节块，随后根据插入语义在目标内存地址上通过 Placement New（``new (static_cast<void*>(p)) T(args...)``）按需构造对象。

小结与下章导读
--------------

本章系统解构了 C++ 对象的物理存储期、内存对齐数学法则、函数调用底层机制以及多态虚表拓扑。这一物理视图为分析标准库容器的内存开销与性能极限提供了底层判据。

下一章我们将深入 **对象生命周期状态机（02_object_lifetime.rst）**，全面追踪从未初始化原始存储、构造函数家族、赋值重载、临时对象生命周期延长到析构销毁的全链路状态变迁。
