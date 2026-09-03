================================================================================
对象生命周期状态机：存储分配、构造函数家族、赋值重载、临时对象生命周期延长与析构销毁顺序
================================================================================

.. note:: 前置背景与上下文承接
   在前一章《C++ 底层对象模型与内存布局》中，已确立了虚拟地址空间、结构体内存对齐法则、存储期分类以及虚函数表（vtable）的物理拓扑。在这一硬件与编译器布局基石之上，本章进一步解构对象从无到有、状态流转至彻底销毁的完整生命周期状态机。对象生命周期的精确界定，是理解 STL 容器连续内存管理、分配器（Allocator）解耦设计、异常安全回滚机制以及现代 C++ 移动语义的前提。

C++ 语言规范将“存储空间（Storage）”与“有效对象（Live Object）”严格解耦。在物理层面，一块满足尺寸与对齐要求的虚拟内存地址，在执行构造函数机器指令前仅属于原始字节序列；只有当构造函数完成全部成员初始化并返回时，该内存区域才正式进入对象生命周期。同理，当析构函数启动执行时，对象生命周期立即终止，内存回退为原始存储状态。这一精确的生命周期状态机，主导了标准库（STL）中所有顺序容器、节点容器与智能指针的资源管理实现。

对象生命周期的物理分界：未初始化存储、有效对象与已销毁状态
------------------------------------------------------------

在 C++ 内存模型中，对象生命周期的起点与终点由明确的机器指令执行时序界定：

1. **生命周期起点**：
   对于具有非平凡构造函数（Non-trivial Constructor）的类类型，生命周期开始于构造函数执行完成（即构造函数体最末尾指令执行完毕）的瞬间；对于平凡类型（Trivial Type），生命周期开始于其占用的存储空间被分配且按需完成值初始化的时刻。
2. **生命周期终点**：
   对于具有非平凡析构函数（Non-trivial Destructor）的类类型，生命周期在析构函数开始执行（即析构函数首条指令切入）的时刻立即终止；对于平凡类型，生命周期在对象所占用的物理存储被释放或被重用作其他用途时结束。

.. list-table:: C++ 对象生命周期四阶段状态机转换规则与操作约束
   :widths: 18 22 30 30
   :header-rows: 1
   :class: tight-table

   * - 状态阶段
     - 物理内存状态
     - 允许的合法操作
     - 非法操作与未定义行为 (UB)
   * - 1. 未分配存储 (Unallocated)
     - 虚拟地址未映射或处于系统空闲堆/栈外
     - 系统级内存申请 (``malloc`` / ``mmap`` / ``brk``)
     - 任何针对该地址的指针解引用与读写
   * - 2. 原始存储 (Raw Storage)
     - 已分配字节块，满足 ``sizeof(T)`` 与 ``alignof(T)``
     - Placement New、``std::construct_at``、``memcpy`` (仅限平凡类型)
     - 调用非静态成员函数、访问非平凡成员、多态虚函数分发
   * - 3. 有效对象 (Live Object)
     - 构造函数已执行完毕，成员与虚表指针均处于确定状态
     - 成员读取与修改、虚函数调用、取地址、赋值操作、传递引用
     - 重复调用构造函数、直接调用 ``free`` 绕过析构函数
   * - 4. 已销毁存储 (Destroyed Storage)
     - 析构函数已执行完毕，资源已关闭，内存尚未释放
     - 重新执行 Placement New 构造新对象、归还内存 (``deallocate``)
     - 读取对象成员值、调用任何成员函数、通过旧指针直接解引用

当对象处于“原始存储”或“已销毁存储”阶段时，虽然该虚拟内存地址在进程页表中合法存在，但向该地址发起成员函数调用或虚函数分发将导致未定义行为（Undefined Behavior）。

.. code-block:: cpp

   #include <iostream>
   #include <memory>
   #include <new>
   #include <cstdint>

   struct alignas(8) PacketHeader {
       uint32_t magic;
       uint32_t length;

       explicit PacketHeader(uint32_t len)
           : magic(0x5A5A5A5A), length(len) {
           // 构造函数体执行完毕后，对象正式进入 Live 状态
       }

       ~PacketHeader() {
           // 析构函数开始执行时，对象立即退出 Live 状态
           magic = 0;
           length = 0;
       }

       uint32_t get_payload_size() const noexcept {
           return length;
       }
   };

   void execute_storage_lifecycle() {
       // 阶段 1 -> 阶段 2：在栈上分配满足对齐的原始字节存储
       alignas(PacketHeader) uint8_t raw_buffer[sizeof(PacketHeader)];

       // 阶段 2 -> 阶段 3：在原始存储上显式调用构造函数 (Placement New)
       PacketHeader* packet_ptr = ::new (static_cast<void*>(raw_buffer)) PacketHeader(1024);

       // 阶段 3：在有效对象生命周期内执行业务逻辑
       uint32_t payload = packet_ptr->get_payload_size();
       std::cout << "Payload size: " << payload << "
";

       // 阶段 3 -> 阶段 4：显式调用析构函数，封闭对象生命周期
       packet_ptr->~PacketHeader();

       // 阶段 4 -> 阶段 3：复用同一块原始存储构造新对象
       PacketHeader* reused_ptr = std::construct_at(reinterpret_cast<PacketHeader*>(raw_buffer), 2048);
       std::destroy_at(reused_ptr);
   }

在 C++20 中，标准库引入了 ``std::construct_at`` 与 ``std::destroy_at``，统一了 Placement New 与显式析构调用的模板表达，并在 ``constexpr`` 评估上下文中提供了编译期对象构造与销毁支持。

构造函数家族微架构：直接构造、拷贝构造与移动构造的物理转移
------------------------------------------------------------

构造函数的核心任务是在指定的物理内存槽位建立合法的类不变式（Class Invariant）。从汇编层面观察，构造函数是一个具有特殊名字修饰（Mangled Name）的过程调用，调用方将目标内存首地址作为隐式第一参数（在 x86-64 System V ABI 下存入 ``RDI`` 寄存器）传入。

构造函数的内部执行时序由编译器强制固定为以下物理步骤：

1. **基类子对象构造**：按照类派生列表中基类的声明顺序，依次调用基类构造函数。
2. **虚函数表指针初始化**：若当前类包含虚函数，编译器在此处生成写内存指令，将当前类的 ``vtable`` 入口地址写入对象的 ``vptr`` 槽位（偏移量 0）。
3. **非静态成员对象初始化**：严格按照数据成员在类定义中的声明顺序（而非成员初始化列表的书写顺序），依次调用各成员的构造函数或应用就地初始化表达式。
4. **构造函数体执行**：执行用户编写在构造函数花括号内的机器指令。

.. list-table:: 构造函数变体在内存拓扑、寄存器开销与所有权流转层面的物理对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 构造函数类别
     - 函数签名与约束
     - 物理操作机制
     - 资源所有权与源对象状态
   * - 默认构造 (Default)
     - ``T()``
     - 零参数初始化成员，写入常量或调用默认构造
     - 无外部源对象，建立独立新资源
   * - 直接构造 (Direct)
     - ``explicit T(Args...)``
     - 依据入参计算成员初值并分配底层资源
     - 消费输入实参，建立独立新资源
   * - 拷贝构造 (Copy)
     - ``T(const T& other)``
     - 读取源对象内存，为新对象申请独立堆内存并复制字节
     - 保持源对象只读与不变式，双副本独立所有权
   * - 移动构造 (Move)
     - ``T(T&& other) noexcept``
     - 浅拷贝源对象指针/句柄，重置源对象句柄为空
     - 窃取源对象资源所有权，源对象转为可析构状态

下面通过一个拥有动态堆内存资源的 ``BufferController`` 类，分析拷贝构造与移动构造在汇编层面的资源分流：

.. code-block:: cpp

   #include <utility>
   #include <cstddef>
   #include <cstring>

   class BufferController {
   public:
       // 直接构造：申请独立堆内存
       explicit BufferController(size_t capacity)
           : size_(0), capacity_(capacity), data_(new uint8_t[capacity]) {}

       // 拷贝构造：深度复制，产生两次独立内存分配
       BufferController(const BufferController& other)
           : size_(other.size_), capacity_(other.capacity_), data_(new uint8_t[other.capacity_]) {
           std::memcpy(data_, other.data_, other.size_);
       }

       // 移动构造：所有权窃取，零堆内存分配开销
       BufferController(BufferController&& other) noexcept
           : size_(other.size_),
             capacity_(other.capacity_),
             data_(std::exchange(other.data_, nullptr)) {
           other.size_ = 0;
           other.capacity_ = 0;
       }

       ~BufferController() {
           delete[] data_;
       }

   private:
       size_t size_;
       size_t capacity_;
       uint8_t* data_;
   };

当 ``BufferController`` 发生移动构造时，CPU 仅执行 3 次 64 位整数寄存器加载与存储指令（移动 ``size_``、``capacity_`` 以及指针 ``data_``），并将 ``other.data_`` 覆写为 0。整个过程无须介入操作系统的堆内存管理器（如 ``ptmalloc`` 或 ``jemalloc``），执行耗时控制在单个时钟周期级别。

移动构造函数标注 ``noexcept`` 是 STL 容器实现异常安全性的关键。若移动构造函数声明可能抛出异常，``std::vector`` 在执行扩容搬迁时将强制退化为调用拷贝构造函数（通过 ``std::move_if_noexcept`` 萃取判定），以保证强异常安全承诺（Strong Exception Safety Guarantee）。

赋值操作符家族：拷贝赋值、移动赋值与异常安全强保证
----------------------------------------------------

赋值操作与构造函数的本质物理差异在于：**赋值操作的目标对象已经是一个处于有效生命周期内的实体，其内部通常已经持有活跃的系统资源与内存指针**。

一次完整的赋值操作必须严格调度以下三项物理事务：

1. **处理目标对象持有的旧资源**：释放目标对象先前占用的堆内存、文件描述符或互斥锁。
2. **转移或复制源对象的新状态**：分配新内存并复制数据，或直接窃取右值资源指针。
3. **维护对象的异常安全不变式**：在分配失败或发生异常时，确保目标对象不处于损坏状态（Dangling Pointer 或 Double Free）。

.. list-table:: 拷贝赋值与移动赋值的执行流水线与异常安全性对比
   :widths: 18 27 27 28
   :header-rows: 1
   :class: tight-table

   * - 赋值类别
     - 自赋值防御机制
     - 资源重构顺序
     - 异常发生时的物理状态
   * - 传统拷贝赋值
     - ``if (this == &other) return *this;``
     - 先申请新资源，再释放旧指针，最后提交成员
     - 保持原有旧状态不变（强异常保证）
   * - Copy-and-Swap 赋值
     - 由传值形参天然防御自赋值
     - 构造临时副本，利用 ``std::swap`` 交换指针所有权
     - 强异常保证，旧资源在临时对象析构时释放
   * - 移动赋值 (Move Assignment)
     - ``if (this == &other) return *this;``
     - 释放目标旧资源，交换指针，置空源对象句柄
     - 标注 ``noexcept``，无内存申请动作，保证不抛出异常

在工程实现中，Copy-and-Swap 惯用法通过参数传递触发拷贝或移动构造，将内存申请逻辑完全封装在进入函数体之前：

.. code-block:: cpp

   #include <algorithm>
   #include <utility>

   class SafeBuffer {
   public:
       explicit SafeBuffer(size_t cap)
           : capacity_(cap), data_(new char[cap]) {}

       SafeBuffer(const SafeBuffer& other)
           : capacity_(other.capacity_), data_(new char[other.capacity_]) {
           std::copy_n(other.data_, capacity_, data_);
       }

       SafeBuffer(SafeBuffer&& other) noexcept
           : capacity_(other.capacity_), data_(std::exchange(other.data_, nullptr)) {
           other.capacity_ = 0;
       }

       ~SafeBuffer() {
           delete[] data_;
       }

       // 友好交换函数：保证 noexcept 且仅操作指针与标量
       friend void swap(SafeBuffer& lhs, SafeBuffer& rhs) noexcept {
           using std::swap;
           swap(lhs.capacity_, rhs.capacity_);
           swap(lhs.data_, rhs.data_);
       }

       // 统一赋值操作符：参数按值传递 (Pass-by-value)
       SafeBuffer& operator=(SafeBuffer other) noexcept {
           swap(*this, other);
           return *this;
           // other 在离开作用域时析构，自动释放目标对象原先持有的旧内存
       }

   private:
       size_t capacity_{0};
       char* data_{nullptr};
   };

当调用 ``a = b;`` 时，实参 ``b`` 匹配拷贝构造函数生成形参 ``other``；若内存不足，异常在进入 ``operator=`` 函数体之前抛出，对象 ``a`` 毫发无损。进入函数体后，``swap`` 操作仅交换寄存器与内存指针，保证绝对不抛异常。随后局部变量 ``other`` 携带 ``a`` 的旧数据在完整表达式末尾执行析构，实现确定性的延迟清理。

临时对象求值边界与生命周期延长拓扑
----------------------------------

在 C++ 表达式求值过程中，纯右值（prvalue）具象化（Materialization）所产生的临时对象（Temporary Object）具有极其严格的物理驻留周期。

标准规定：**临时对象的生命周期在包含该临时对象创建点的完整表达式（Full-Expression）求值结束时（即分号处）立即终止，并启动析构函数**。

语言标准定义了一条关键的生命周期扩展（Lifetime Extension）规则：当一个纯右值临时对象被直接绑定至一个局部作用域的 ``const`` 左值引用（``const T&``）或右值引用（``T&&``）时，该临时对象的生命周期将被延长至与该引用变量本身的作用域一致。

.. list-table:: 临时对象在不同引用绑定场景下的生命周期终点与悬垂风险分析
   :widths: 22 28 25 25
   :header-rows: 1
   :class: tight-table

   * - 绑定场景
     - 代码模式
     - 物理生命周期终点
     - 内存访问安全性
   * - 默认无绑定临时对象
     - ``process(Resource(10));``
     - 完整表达式结束分号处
     - 安全（函数调用期间有效）
   * - 直接绑定局部引用
     - ``const Resource& r = Resource(10);``
     - 引用变量所在作用域离开时
     - 安全（栈帧生命期延长生效）
   * - 函数返回值透传临时引用
     - ``const Resource& f() { return Resource(10); }``
     - 函数返回跳转（``RET`` 指令）完成时
     - **极危：悬垂引用 (Dangling)**
   * - 结构体成员初始化绑定
     - ``struct Holder { const Resource& ref; };``
     - 构造函数初始化表达式求值结束时
     - **极危：悬垂引用 (Dangling)**
   * - 经由三目运算符绑定
     - ``const auto& r = cond ? Resource(1) : Resource(2);``
     - 选中的分支临时对象生命周期延长
     - 安全（标准明确定义延长语义）

分析以下汇编层面的生命周期陷阱：

.. code-block:: cpp

   #include <iostream>
   #include <string>

   struct Node {
       std::string name;
       explicit Node(std::string n) : name(std::move(n)) {}
   };

   // 陷阱 1：返回局部临时对象的引用
   const std::string& get_dangling_name() {
       return Node("temporary_node").name; 
       // Node 对象在 return 语句评估后立即析构，返回的引用指向已释放的栈/堆内存
   }

   void test_lifetime_extension() {
       // 正确场景：直接绑定局部引用，生命周期延长至当前块结束
       const Node& valid_node = Node("extended_node");

       // 陷阱 2：链式访问成员导致生命周期延长失效
       const std::string& dangling_str = Node("chained_node").name;
       // 标准规定：生命周期延长仅作用于最外层临时对象。
       // 此处 Node 临时对象在分号处析构，dangling_str 立即成为悬垂引用！

       std::cout << valid_node.name << "
"; // 安全访问
   }

在 STL 字符串与容器视图设计（如 ``std::string_view`` 与 ``std::span``）中，这一物理边界极为关键。``std::string_view`` 内部仅包含一个指针和长度标量，它不属于语言层面的引用类型，因此**无法触发编译器的生命周期延长机制**。将临时 ``std::string`` 隐式转换为 ``std::string_view`` 并持久化保存，会导致严重的野指针读取故障。

析构拓扑、作用域逆序销毁与 RAII 资源控制律
------------------------------------------

析构函数是保障 C++ 程序确定性资源管理的核心机制。当执行流离开作用域块、堆对象被 ``delete`` 显式触发、或异常引发栈展开（Stack Unwinding）时，析构执行流水线严格按照构造顺序的**完全逆序**展开。

析构调用的物理执行拓扑包含以下四步逆序链条：

1. **执行用户自定义析构函数体**：运行类中 ``~ClassName()`` 定义的代码，关闭用户层句柄。
2. **非静态成员对象逆序析构**：按照数据成员在类声明中的出现顺序，从后向前依次调用每个成员的析构函数。
3. **直接基类逆序析构**：按照派生列表中基类的声明顺序，从右向左依次调用各基类的析构函数。
4. **虚基类逆序析构**：最终按照虚基类继承树的拓扑排序逆序销毁虚基类子对象。

.. list-table:: 复合类结构析构时序执行链（基于声明拓扑）
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 构件单元
     - 构造执行顺序 (正序)
     - 析构执行顺序 (逆序)
     - 物理资源生命状态
   * - 虚基类 (Virtual Base)
     - 最先构造 (Step 1)
     - 最后析构 (Step 6)
     - 跨继承体系共享的公共状态
   * - 非虚基类 (Non-Virtual Base)
     - 依声明从左到右 (Step 2)
     - 依声明从右到左 (Step 5)
     - 基类专属字段与 vptr 处于有效状态
   * - 成员变量 A (Member A)
     - 类体声明排首位 (Step 3)
     - 成员中排最后析构 (Step 4)
     - 被后续成员引用的基础依赖项
   * - 成员变量 B (Member B)
     - 类体声明排第二 (Step 4)
     - 成员中排最先析构 (Step 3)
     - 依赖成员 A 的高层组件
   * - 派生类函数体 (Derived Body)
     - 最后进入函数体 (Step 5)
     - 最先切入执行 (Step 1)
     - 所有成员与基类均处于完整有效状态

.. code-block:: cpp

   #include <iostream>

   struct DependencyA {
       DependencyA() { std::cout << "Construct A
"; }
       ~DependencyA() { std::cout << "Destruct A
"; }
   };

   struct DependencyB {
       explicit DependencyB(DependencyA& a) { std::cout << "Construct B (using A)
"; }
       ~DependencyB() { std::cout << "Destruct B (cleaning up before A dies)
"; }
   };

   class CompositeService {
   public:
       CompositeService() : a_(), b_(a_) {
           std::cout << "Construct CompositeService Body
";
       }

       ~CompositeService() {
           std::cout << "Destruct CompositeService Body
";
       }

   private:
       // 成员声明顺序决定物理析构顺序：b_ 依赖 a_，故 a_ 必须先声明，b_ 后声明
       DependencyA a_;
       DependencyB b_;
   };

   void execute_stack_destruction() {
       CompositeService service;
       // 退出作用域输出：
       // 1. Destruct CompositeService Body
       // 2. Destruct B (cleaning up before A dies)
       // 3. Destruct A
   }

在栈展开（Stack Unwinding）过程中，当某个函数抛出 C++ 异常，Itanium C++ ABI 的异常分发引擎（``_Unwind_RaiseException``）将借助编译期生成的 DWARF Call Frame Information (CFI) 展开调用栈。运行时系统精准定位当前指令指针（``RIP``）所在的作用域范围，并强制调用该作用域内所有已完成构造的局部对象的析构函数。

RAII（Resource Acquisition Is Initialization）的设计哲学即基于此：**将堆内存、操作系统句柄、套接字与线程锁的所有权严格绑定于栈上对象的生命周期**。无论控制流通过常规 ``return``、``break``、``goto`` 还是通过异常抛出离开代码块，栈展开均能提供确定性的资源回收保障。

STL 容器内核中的对象生命周期管理机制
------------------------------------

标准库容器在设计上与常规面向对象代码具有本质分界：**STL 容器绝不使用 ``new T[N]`` 分配元素，而是将原始内存分配与元素对象生命周期严格解耦**。

以核心顺序容器 ``std::vector<T>`` 为例，其内部物理拓扑由三个核心指针维系：

- ``T* start_``：指向已分配连续内存的首地址，同时也是首个有效元素的构造起始点。
- ``T* finish_``：指向已构造有效元素范围的尾后地址（即下一个可用槽位的构造点）。
- ``T* end_of_storage_``：指向已分配原始存储区间的物理上限边界。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   | std::vector 内部物理存储与对象生命周期双态划分                                |
   +-------------------------------------------------------------------------------+
   | [ start_ ]                               [ finish_ ]     [ end_of_storage_ ]  |
   |     |                                         |                  |            |
   |     v                                         v                  v            |
   |  +------------+------------+------------+-----------+-----------+             |
   |  |   Elem 0   |   Elem 1   |   Elem 2   | (Raw Mem) | (Raw Mem) |             |
   |  +------------+------------+------------+-----------+-----------+             |
   |  <----- 有效对象生命周期区间 [Live Objects] -----> <--- 原始存储区间 [Storage] ---> |
   |  <------------- size() = 3 ------------->                                     |
   |  <--------------------------- capacity() = 5 --------------------------->     |
   +-------------------------------------------------------------------------------+

在 ``std::vector`` 的整个生命周期内，针对容器的不同操作引发了严密的状态机迁移：

1. **``reserve(N)`` 操作**：
   仅当 $N > 	ext{capacity}$ 时触发系统内存分配，获取满足对齐要求的未初始化内存块。该操作**不构造任何 ``T`` 类型的对象**，仅将 ``end_of_storage_`` 推进至新位置。
2. **``emplace_back(args...)`` 操作**：
   在 ``finish_`` 所指向的原始存储槽位上，通过 ``std::allocator_traits<Alloc>::construct`` 直接调用 Placement New 原位构造对象；对象构造成功后，执行原子性指针步进 ``++finish_``。若构造抛出异常，``finish_`` 保持原位，容器内已存在元素不受破坏。
3. **几何级扩容（Reallocation / Growth）六阶段事务**：
   当 ``finish_ == end_of_storage_`` 时触发扩容流水线：
   
   - **分配阶段**：调用 ``allocator::allocate`` 申请 $2 	imes 	ext{OldCapacity}$ 的原始未初始化空间。
   - **判定阶段**：查询 ``std::is_nothrow_move_constructible<T>::value``。
   - **迁移阶段**：若类型具备 ``noexcept`` 移动构造函数，使用移动构造将旧元素逐一迁入新存储；否则使用拷贝构造迁入新存储。若拷贝中途抛出异常，立即销毁新存储中已构造的元素并归还新内存，旧容器维持原状（强异常安全保证）。
   - **插入阶段**：在新存储的对应槽位原位构造用户请求的新元素。
   - **销毁阶段**：调用 ``std::allocator_traits<Alloc>::destroy`` 逆序销毁旧存储中的所有元素。
   - **提交阶段**：释放旧原始存储内存，更新 ``start_``、``finish_`` 与 ``end_of_storage_`` 指针。
4. **``clear()`` 与 ``erase()`` 操作**：
   ``clear()`` 沿 ``[start_, finish_)`` 区间遍历调用元素析构函数，将 ``finish_`` 指针重置为 ``start_``；此时有效对象数量降为 0，但底层的 ``capacity_`` 原始存储完整保留。``erase(pos)`` 则将 ``[pos + 1, finish_)`` 范围内的元素向前移动赋值，并在尾部析构最后一个多余对象，随后执行 ``--finish_``。

.. code-block:: cpp

   #include <memory>
   #include <utility>
   #include <cstddef>

   template <typename T, typename Alloc = std::allocator<T>>
   class CoreVector {
   public:
       using AllocTraits = std::allocator_traits<Alloc>;

       CoreVector() = default;

       explicit CoreVector(size_t capacity, const Alloc& alloc = Alloc())
           : alloc_(alloc) {
           start_ = AllocTraits::allocate(alloc_, capacity);
           finish_ = start_;
           end_of_storage_ = start_ + capacity;
       }

       template <typename... Args>
       void emplace_back(Args&&... args) {
           if (finish_ == end_of_storage_) {
               reallocate_grow();
           }
           // 在 finish_ 未初始化槽位上构造对象
           AllocTraits::construct(alloc_, finish_, std::forward<Args>(args)...);
           // 构造成功后推进 finish_，正式纳入容器有效元素范围
           ++finish_;
       }

       void pop_back() noexcept {
           --finish_;
           // 销毁对象生命周期，回退为原始存储
           AllocTraits::destroy(alloc_, finish_);
       }

       ~CoreVector() {
           clear();
           if (start_) {
               AllocTraits::deallocate(alloc_, start_, end_of_storage_ - start_);
           }
       }

       void clear() noexcept {
           // 仅析构有效对象，不释放底层存储容量
           while (finish_ != start_) {
               --finish_;
               AllocTraits::destroy(alloc_, finish_);
           }
       }

       size_t size() const noexcept { return finish_ - start_; }
       size_t capacity() const noexcept { return end_of_storage_ - start_; }

   private:
       void reallocate_grow() {
           size_t old_cap = capacity();
           size_t new_cap = (old_cap == 0) ? 1 : old_cap * 2;
           T* new_start = AllocTraits::allocate(alloc_, new_cap);
           T* new_finish = new_start;

           try {
               // 依据 noexcept 属性执行异常安全的元素迁移
               for (T* p = start_; p != finish_; ++p) {
                   if constexpr (std::is_nothrow_move_constructible_v<T> || !std::is_copy_constructible_v<T>) {
                       AllocTraits::construct(alloc_, new_finish, std::move(*p));
                   } else {
                       AllocTraits::construct(alloc_, new_finish, *p);
                   }
                   ++new_finish;
               }
           } catch (...) {
               // 回滚事务：销毁新内存中已构造的元素并释放存储
               while (new_finish != new_start) {
                   --new_finish;
                   AllocTraits::destroy(alloc_, new_finish);
               }
               AllocTraits::deallocate(alloc_, new_start, new_cap);
               throw; // 向上抛出异常，保持原 vector 状态完全不变
           }

           // 销毁旧对象并释放旧内存
           clear();
           if (start_) {
               AllocTraits::deallocate(alloc_, start_, old_cap);
           }

           start_ = new_start;
           finish_ = new_finish;
           end_of_storage_ = new_start + new_cap;
       }

       Alloc alloc_;
       T* start_{nullptr};
       T* finish_{nullptr};
       T* end_of_storage_{nullptr};
   };

通过上述代码实现可见，STL 容器将对象的物理分配（``allocate / deallocate``）与生命周期状态变迁（``construct / destroy``）进行了严格正交的解耦控制。理解这一对象状态机，是排查内存泄漏、野指针访问、迭代器失效以及容器异常崩溃问题的最底层物理视角。

小结与下章导读
--------------

本章系统剖析了 C++ 对象生命周期状态机的底层流转机制：从原始存储分配、构造函数在汇编层的执行时序，到赋值操作符的异常安全规划、临时对象的生命周期延长边界，再到逆序析构与 RAII 资源控制律，最后深入解构了 STL 容器中原始内存与有效对象分离的三指针内核模型。

下一章我们将进入 **右值引用与移动语义深度解析（03_move_semantics_and_value_categories.rst）**，全面解构 C++ 表达式的值类别分类学（lvalue / xvalue / prvalue）、``std::move`` 与 ``std::forward`` 的编译期类型转换本质、万能引用与引用折叠拓扑，以及 moved-from 对象的物理状态约束。
