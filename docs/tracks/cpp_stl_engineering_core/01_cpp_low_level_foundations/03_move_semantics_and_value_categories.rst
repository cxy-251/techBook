================================================================================
右值引用与移动语义深度解析：值类别 (lvalue/xvalue/prvalue)、std::move、完美转发折叠与 moved-from 状态
================================================================================

.. note:: 前置背景与上下文承接
   在前一章《对象生命周期状态机：存储分配、构造函数家族、赋值重载、临时对象生命周期延长与析构销毁顺序》中，已解构了对象从原始存储、有效实体到逆序析构的物理全流程，并推导了 ``std::vector`` 三指针模型下对象的构造与销毁边界。在此基础之上，本章深入剖析现代 C++ 资源管理的核心机制——移动语义（Move Semantics）与值类别（Value Categories）体系。移动语义在硬件层面的物理本质，是通过 CPU 寄存器直接搬迁资源句柄（堆指针、文件描述符、容量计数器等），将时间复杂度为 $O(N)$ 的深拷贝转化为 $O(1)$ 的标量赋值，同时在类型系统中维持严格的对象生命周期与异常安全不变式。

表达式值类别分类学：lvalue、prvalue 与 xvalue 的物理与语义拓扑
------------------------------------------------------------

在 C++11 及后续标准中，值类别（Value Category）是编译器在语法分析阶段赋予每一个**表达式（Expression）**的核心属性。值类别独立于表达式的类型（Type），二者共同决定了重载决议、引用绑定、临时对象物化以及代码生成策略。

ISO C++ 标准基于两个正交的物理维度对表达式进行分类：

1. **拥有身份（Has Identity）**：编译器能够确定该表达式所指代实体的内存地址，允许程序在后续指令中通过指针或引用再次访问该实体。
2. **可移动（Can be Moved From）**：该表达式所指代的资源处于可转移状态，允许移动构造函数或移动赋值运算符窃取其内部句柄。

.. code-block:: text

   +-----------------------------------------------------------------------+
   |                        C++ 表达式值类别拓扑体系                       |
   +-----------------------------------------------------------------------+
   |                        表达式 (Expressions)                           |
   |                                 |                                     |
   |                +----------------+----------------+                    |
   |                |                                 |                    |
   |         泛左值 (glvalue)                   右值 (rvalue)              |
   |         [拥有内存身份]                    [资源可被移动]              |
   |                |                                 |                    |
   |        +-------+-------+                 +-------+-------+            |
   |        |               |                 |               |            |
   |   左值 (lvalue)   亡值 (xvalue)   纯右值 (prvalue)       |            |
   |   [有身份,不可移]  [有身份,可移动]  [无身份,可移动]       |            |
   +-----------------------------------------------------------------------+

这三个基本类别与两个派生类别的严格定义如下：

- **左值 (lvalue, left value)**：具有确定内存身份且不可被隐式移动的表达式。包括具名变量名（如 ``int x`` 中的 ``x``）、返回左值引用的函数调用（如 ``v[i]`` 或 ``std::cout << val``）、解引用表达式（``*ptr``）、左值属性的类成员访问（``obj.member``）以及字符串字面量（类型为 ``const char[N]`` 的左值数组）。
- **纯右值 (prvalue, pure rvalue)**：用于计算值或初始化对象的无身份表达式。包括非字符串字面量（如 ``42``、``true``、``3.14``）、返回非引用类型的函数调用（如 ``make_buffer()``）、算术/逻辑表达式（``a + b``、``a && b``）、Lambda 表达式以及取地址表达式（``&var``）。在 C++17 引入**纯右值物化（Temporary Materialization）**规则后，纯右值在未绑定到引用或未转换为泛左值前，在 AST 层面仅作为初始化器（Initializer）存在，并不直接在栈上开辟临时对象存储空间。
- **亡值 (xvalue, expiring value)**：具有明确内存身份且其持有的资源已明确标记为可转移的表达式。包括显式转换为右值引用的类型转换表达式（``static_cast<Buffer&&>(buf)`` 或 ``std::move(buf)``）、返回右值引用的函数调用（``std::move(x)``）、以及访问右值对象的非静态数据成员表达式（``std::move(obj).member``）。
- **泛左值 (glvalue, generalized lvalue)**：lvalue 与 xvalue 的并集，统指所有具有物理内存身份的表达式。
- **右值 (rvalue, right value)**：prvalue 与 xvalue 的并集，统指所有允许作为移动语义源操作数的表达式。

.. list-table:: C++ 表达式值类别核心属性与机器级表现对照表
   :widths: 15 15 15 25 30
   :header-rows: 1
   :class: tight-table

   * - 基本值类别
     - 内存身份 (Identity)
     - 可移动 (Movable)
     - 是否允许取地址 (``&expr``)
     - 典型表达式示例与汇编特征
   * - 左值 (lvalue)
     - 是
     - 否
     - 允许 (``&x`` 合法)
     - ``buf``、``*p``、``v[0]``；直接使用栈帧基址寻址 (``[RBP - offset]``)
   * - 亡值 (xvalue)
     - 是
     - 是
     - 允许 (经转换后可取地址)
     - ``std::move(buf)``、``static_cast<T&&>(x)``；寄存器保留原对象基址，标记可重载匹配
   * - 纯右值 (prvalue)
     - 否
     - 是
     - 禁止 (编译期语法错误)
     - ``1024``、``Buffer(32)``、``a + b``；立即数载入寄存器或直接在目标内存槽位就地初始化

理解值类别的核心分界在于区分**声明类型（Declared Type）**与**表达式类别（Expression Value Category）**：

.. code-block:: cpp

   #include <iostream>
   #include <utility>

   struct Packet {
       int payload_id{0};
   };

   void process_packet(Packet& p) {
       std::cout << "Binding: lvalue reference (Packet&)
";
   }

   void process_packet(const Packet& p) {
       std::cout << "Binding: const lvalue reference (const Packet&)
";
   }

   void process_packet(Packet&& p) {
       std::cout << "Binding: rvalue reference (Packet&&)
";
   }

   void route_pipeline(Packet&& input_packet) {
       // input_packet 的声明类型是 Packet&& (右值引用)
       // 但 input_packet 是一个具名变量，其表达式属性为 lvalue
       process_packet(input_packet);             // 触发 process_packet(Packet&)

       // 显式将具名变量转换为 xvalue (亡值)
       process_packet(std::move(input_packet));   // 触发 process_packet(Packet&&)
   }

   int main() {
       Packet local_pkt{101};

       process_packet(local_pkt);                // local_pkt 为 lvalue -> process_packet(Packet&)
       process_packet(Packet{102});              // Packet{102} 为 prvalue -> process_packet(Packet&&)
       process_packet(std::move(local_pkt));     // std::move(local_pkt) 为 xvalue -> process_packet(Packet&&)

       route_pipeline(Packet{103});
   }

引用类型拓扑与重载决议分发机制
------------------------------

C++ 类型系统提供四种核心引用变体：非 const 左值引用（``T&``）、const 左值引用（``const T&``）、右值引用（``T&&``）以及 const 右值引用（``const T&&``）。编译器重载决议引擎依据 ISO C++ [over.ics.rank] 规则，按照严格的隐式转换序列与绑定优先级挑选最佳匹配函数。

.. list-table:: 引用类型对不同值类别实参的绑定能力与重载优先级矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 形参签名
     - 非 const 左值 (lvalue)
     - const 左值 (const lvalue)
     - 纯右值 (prvalue)
     - 亡值 (xvalue)
   * - ``T&``
     - **第 1 优先级 (精确匹配)**
     - 禁止绑定
     - 禁止绑定
     - 禁止绑定
   * - ``const T&``
     - 第 2 优先级
     - **第 1 优先级 (精确匹配)**
     - 第 2 优先级 (生命周期延长)
     - 第 2 优先级
   * - ``T&&``
     - 禁止绑定
     - 禁止绑定
     - **第 1 优先级 (精确匹配)**
     - **第 1 优先级 (精确匹配)**
   * - ``const T&&``
     - 禁止绑定
     - 禁止绑定
     - 第 3 优先级
     - 第 3 优先级

根据重载决议拓扑规则：

1. 当传入可修改的左值表达式时，编译器优先选择 ``T&``；若未定义 ``T&``，则降级匹配 ``const T&``。
2. 当传入右值表达式（prvalue 或 xvalue）时，编译器优先选择 ``T&&``；若未定义 ``T&&``，则无缝回退匹配至 ``const T&``（拷贝路径）。
3. ``const T&&`` 虽然在语法上合法，但在工程架构中属于反模式：它能够绑定右值，但由于附加了 ``const`` 修饰符，函数体内部无法修改源对象成员，导致资源所有权窃取失败，最终被迫退化执行深拷贝。

.. code-block:: cpp

   #include <iostream>
   #include <string>

   struct Channel {
       std::string name;

       // 入口 1：只读借用，保持源对象状态不变
       void push(const std::string& msg) {
           std::cout << "[Copy Path] deep copying: " << msg << "
";
           name = msg; // 触发 std::string 拷贝赋值
       }

       // 入口 2：所有权转移，接管右值内部堆指针
       void push(std::string&& msg) {
           std::cout << "[Move Path] stealing buffer: " << msg << "
";
           name = std::move(msg); // 触发 std::string 移动赋值，指针瞬间置换
       }
   };

   void execute_channel_dispatch() {
       Channel ch;
       std::string persistent_msg = "sensor_heartbeat_payload_data_block";

       ch.push(persistent_msg);                // 匹配 push(const std::string&) -> 产生堆内存分配与深拷贝
       ch.push(std::string("transient_event")); // 匹配 push(std::string&&) -> 零内存申请，窃取临时字符串指针
       ch.push(std::move(persistent_msg));     // 匹配 push(std::string&&) -> 窃取 persistent_msg 底层堆内存
   }

std::move 的物理本质与 moved-from 对象的合法状态机
--------------------------------------------------

在汇编与机器指令层面，``std::move`` **不产生任何运行时指令，不分配内存，不调用构造函数，也不执行指针置空**。

``std::move`` 在标准库中的物理实现是一个纯粹的编译期静态类型转换模板。其核心作用是将传入实参的静态类型转换为对应的右值引用类型，从而在编译器 AST 节点上将该表达式的值类别显式标记为亡值（xvalue）：

.. code-block:: cpp

   // GCC libstdc++ / LLVM libc++ 核心实现精简模型
   template <typename T>
   [[nodiscard]] constexpr std::remove_reference_t<T>&& move(T&& t) noexcept {
       return static_cast<std::remove_reference_t<T>&&>(t);
   }

当编译器处理 ``auto y = std::move(x);`` 时，代码生成分为明确的两阶段：

1. **编译期阶段**：``std::move(x)`` 经由 ``static_cast`` 将表达式类别从 lvalue 提升为 xvalue。重载决议引擎据此选择调用目标类型的移动构造函数 ``Y::Y(Y&&)`` 而非拷贝构造函数 ``Y::Y(const Y&)``。
2. **运行期阶段**：执行被选中的移动构造函数体指令，完成内存指针、文件句柄与标量字段的寄存器级搬迁，并将源对象相关字段写入中立状态值（如 ``nullptr`` 或 ``0``）。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   | std::move 触发的所有权窃取与内存拓扑变迁                                      |
   +-------------------------------------------------------------------------------+
   | [初始状态]                                                                    |
   |   src_buffer (栈地址: 0x7ffd01) --------> [ 动态堆内存块: 0x55a000 (1024B) ]  |
   |                                                                               |
   | [执行 std::move(src_buffer) 后 (编译期 AST 标记，物理指针不变)]               |
   |   表达式变为 xvalue，定位同一物理实体 0x7ffd01                                |
   |                                                                               |
   | [执行 Buffer dst(std::move(src_buffer)) 移动构造完成]                         |
   |   dst_buffer (栈地址: 0x7ffd20) --------> [ 动态堆内存块: 0x55a000 (1024B) ]  |
   |   src_buffer (栈地址: 0x7ffd01) --------> nullptr (有效可析构状态)            |
   +-------------------------------------------------------------------------------+

ISO C++ 标准在 [lib.types.movedfrom] 中对标准库类型的“被移动后状态（moved-from state）”制定了严格契约：

- **类不变式成立（Class Invariant Preservation）**：对象处于有效状态（Valid State），其内部数据结构不处于崩溃或未定义内存对齐破坏状态。
- **安全析构保证（Destructible Guarantee）**：对象离开作用域时，析构函数必须能够正常运行且绝不发生重复释放（Double Free）。
- **允许重新赋值（Assignable Guarantee）**：对象可被赋予新值或作为拷贝/移动赋值的目标操作数。
- **无前置条件操作合法（Precondition-Free Operations）**：所有对对象状态无特定前提假设的成员函数（如 ``clear()``、``size() == 0``、``empty()``）均可安全调用；具有前置条件的操作（如 ``std::vector::operator[]`` 或 ``std::optional::value()``）则不可访问。

.. list-table:: 典型 STL 核心组件 moved-from 状态物理表现与合法操作边界
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - STL 类型
     - moved-from 内部指针状态
     - 标量与容量状态
     - 合法操作集合
   * - ``std::unique_ptr<T>``
     - 内部原生指针置为 ``nullptr``
     - 无多余状态
     - ``reset()``、重新赋值、``operator bool() == false``、析构
   * - ``std::vector<T>``
     - ``start_ = finish_ = end_ = nullptr``
     - ``size() == 0``, ``capacity() == 0``
     - ``push_back()``、``clear()``、``reserve()``、重新赋值、析构
   * - ``std::string``
     - 动态堆指针置空 / SSO 缓冲首字节置 ``\0``
     - ``size() == 0``, ``capacity()`` 依 SSO 策略
     - ``append()``、``c_str()`` 返回空串、赋值、析构
   * - ``std::shared_ptr<T>``
     - 资源指针与控制块指针均置为 ``nullptr``
     - ``use_count() == 0``
     - ``reset()``、赋值、``use_count()`` 查询、析构

在工业级工程实践中，移动构造函数与移动赋值运算符应统一采用原子交换原语 ``std::exchange`` 编写，确保在单指令周期内完成指针转移与源字段置空：

.. code-block:: cpp

   #include <utility>
   #include <cstddef>
   #include <algorithm>

   class HardwareRingBuffer {
   public:
       explicit HardwareRingBuffer(size_t capacity)
           : capacity_(capacity),
             head_(0),
             tail_(0),
             storage_(new uint8_t[capacity]) {}

       ~HardwareRingBuffer() noexcept {
           delete[] storage_;
       }

       // 移动构造函数：必须标注 noexcept，使用 std::exchange 实现安全置空
       HardwareRingBuffer(HardwareRingBuffer&& other) noexcept
           : capacity_(std::exchange(other.capacity_, 0)),
             head_(std::exchange(other.head_, 0)),
             tail_(std::exchange(other.tail_, 0)),
             storage_(std::exchange(other.storage_, nullptr)) {
           // other 内部指针置为 nullptr，离开作用域执行 delete[] nullptr 绝对安全
       }

       // 移动赋值运算符：处理自赋值并安全释放当前持有的旧硬件内存
       HardwareRingBuffer& operator=(HardwareRingBuffer&& other) noexcept {
           if (this == &other) {
               return *this; // 自赋值防御
           }

           // 1. 释放当前持有的物理存储
           delete[] storage_;

           // 2. 窃取源对象全部控制字段
           capacity_ = std::exchange(other.capacity_, 0);
           head_     = std::exchange(other.head_, 0);
           tail_     = std::exchange(other.tail_, 0);
           storage_  = std::exchange(other.storage_, nullptr);

           return *this;
       }

       // 禁用拷贝以强化独占所有权模型
       HardwareRingBuffer(const HardwareRingBuffer&) = delete;
       HardwareRingBuffer& operator=(const HardwareRingBuffer&) = delete;

       [[nodiscard]] bool is_valid() const noexcept {
           return storage_ != nullptr;
       }

   private:
       size_t capacity_{0};
       size_t head_{0};
       size_t tail_{0};
       uint8_t* storage_{nullptr};
   };

万能引用 (Forwarding Reference)、引用折叠与 std::forward 物理实现
----------------------------------------------------------------

在泛型编程与工厂函数（如 ``std::make_unique``、``std::vector::emplace_back``）中，包装函数必须将外部调用者传入的实参类别完整无损地透传至底层构造函数：若外部传入左值，底层应按左值引用接收；若外部传入右值，底层应按右值引用接收并触发移动。

具名形参在函数体内部始终作为左值存在。直接传递形参将导致右值属性丢失。为解决该问题，现代 C++ 建立了**万能引用（Forwarding Reference，通用引用）**与**引用折叠（Reference Collapsing）**机制。

万能引用的成立必须严格满足两项语法条件：

1. 形参形式必须严格为 ``T&&``（或变长参数包 ``Args&&...``）。
2. ``T`` 必须是当前**函数模板直接推导的类型参数**，且不能带有 ``const`` 或 ``volatile`` 限定符。

.. code-block:: cpp

   template <typename T>
   void func_universal(T&& param);        // 万能引用：T 发生模板推导

   template <typename T>
   void func_rvalue(const T&& param);     // 右值引用：带有 const 修饰

   template <typename T>
   class Container {
       void insert(T&& param);            // 右值引用：T 由类模板实例化确定，此处不发生推导

       template <typename U>
       void emplace(U&& param);           // 万能引用：U 在成员函数调用时独立推导
   };

当实参传入万能引用形参时，编译器执行特殊的模板类型推导规则：

- 若实参为类型 ``X`` 的左值表达式，``T`` 被推导为左值引用类型 ``X&``。
- 若实参为类型 ``X`` 的右值表达式，``T`` 被推导为不带引用的原始类型 ``X``。

推导过程中产生的“引用的引用”由编译器按照**引用折叠规则（Reference Collapsing Rules）**归一化：

.. list-table:: 引用折叠组合矩阵与最终类型映射
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 中间推导类型
     - 语法表达式
     - 折叠后实际类型
     - 发生场景
   * - ``&`` 遇 ``&``
     - ``(T&)&``
     - ``T&`` (左值引用)
     - 左值实参传入万能引用
   * - ``&`` 遇 ``&&``
     - ``(T&)&&``
     - ``T&`` (左值引用)
     - ``std::forward<T&>`` 内部类型实例化
   * - ``&&`` 遇 ``&``
     - ``(T&&)&``
     - ``T&`` (左值引用)
     - 右值引用别名绑定左值
   * - ``&&`` 遇 ``&&``
     - ``(T&&)&&``
     - ``T&&`` (右值引用)
     - 右值实参传入万能引用及 ``std::forward<T>``

**引用折叠的简要物理法则**：只要引用组合中出现一个左值引用 ``&``，折叠结果必为左值引用 ``&``；只有当两端均为右值引用 ``&&`` 时，折叠结果才为右值引用 ``&&``。

``std::forward`` 借由引用折叠机制实现条件静态类型转换。标准库中通过重载实现对左值与右值引用的精准还原：

.. code-block:: cpp

   // 重载 1：处理左值与右值实参透传
   template <typename T>
   [[nodiscard]] constexpr T&& forward(std::remove_reference_t<T>& t) noexcept {
       return static_cast<T&&>(t);
   }

   // 重载 2：拦截纯右值临时对象，禁止将左值通过显式右值模板参数转发
   template <typename T>
   [[nodiscard]] constexpr T&& forward(std::remove_reference_t<T>&& t) noexcept {
       static_assert(!std::is_lvalue_reference_v<T>,
           "std::forward cannot forward an rvalue as an lvalue reference");
       return static_cast<T&&>(t);
   }

分析 ``std::forward`` 在不同实参下的推导流水线：

- **场景 A：传入左值实参 ``buf``**：
  模板推导得出 ``T = Buffer&``。形参 ``t`` 类型为 ``Buffer&``。``std::forward<Buffer&>(t)`` 执行 ``static_cast<Buffer& &&>(t)``。经引用折叠，返回类型为 ``Buffer&``（左值）。
- **场景 B：传入右值实参 ``Buffer(1024)``**：
  模板推导得出 ``T = Buffer``。形参 ``t`` 类型为 ``Buffer&``。``std::forward<Buffer>(t)`` 执行 ``static_cast<Buffer&&>(t)``。返回类型为 ``Buffer&&``（亡值 xvalue）。

.. code-block:: cpp

   #include <iostream>
   #include <memory>
   #include <utility>

   struct NodePayload {
       NodePayload(const std::string& name, int weight) {
           std::cout << "Construct NodePayload via (const std::string&, int)
";
       }

       NodePayload(std::string&& name, int weight) {
           std::cout << "Construct NodePayload via (std::string&&, int)
";
       }
   };

   // 工业级完美转发工厂模板
   template <typename Target, typename... Args>
   std::unique_ptr<Target> make_unique_node(Args&&... args) {
       // 使用 std::forward<Args>(args)... 展开参数包，保留每个独立参数的值类别
       return std::unique_ptr<Target>(new Target(std::forward<Args>(args)...));
   }

   void execute_forwarding_demo() {
       std::string persistent_label = "cluster_master_node";

       // 参数 1 为左值 persistent_label，参数 2 为 prvalue 100
       // make_unique_node 将参数 1 完美转发为 const std::string&
       auto node1 = make_unique_node<NodePayload>(persistent_label, 100);

       // 参数 1 为 xvalue std::move(persistent_label)，参数 2 为 prvalue 200
       // make_unique_node 将参数 1 完美转发为 std::string&&，触发移动构造
       auto node2 = make_unique_node<NodePayload>(std::move(persistent_label), 200);
   }

移动语义与异常安全在 STL 容器中的协同：noexcept 契约与 std::move_if_noexcept
---------------------------------------------------------------------------

在 ``std::vector``、``std::deque`` 等动态容器的扩容流水线中，移动语义与强异常安全保证（Strong Exception Safety Guarantee）之间存在直接的工程冲突。

**物理冲突场景剖析**：

当 ``std::vector<T>`` 容量耗尽并申请新内存块后，容器必须将旧内存块中的 $N$ 个已构造对象迁移至新内存块。

假设容器盲目对旧元素调用 ``std::move``：
若在迁移第 $K$ 个元素（$0 \le K < N$）时，类型 ``T`` 的移动构造函数抛出异常，新内存块中已有 $0 \dots K-1$ 个元素构造成功，而旧内存块中的前 $K-1$ 个元素已经被修改为 moved-from 状态。由于异常发生，扩容事务被迫中断；但由于旧数据已被破坏，容器无法将状态无损回滚至扩容前的状态，导致强异常安全保证彻底破裂。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   | std::vector 扩容元素迁移中的异常安全破坏场景                                  |
   +-------------------------------------------------------------------------------+
   | 旧内存块: [ Elem 0 (Moved) ] [ Elem 1 (Moved) ] [ Elem 2 (活跃) ] [ Elem 3 ]  |
   |                                                        |                      |
   |                                            移动构造抛出异常 (Throw!)          |
   |                                                        v                      |
   | 新内存块: [ Elem 0 (有效)  ] [ Elem 1 (有效)  ] [ 构造失败槽位 ] [ 未初始化  ]  |
   |                                                                               |
   | 结果：新内存回滚释放后，旧内存中 Elem 0 与 Elem 1 数据已丢失，无法恢复原状！  |
   +-------------------------------------------------------------------------------+

为保证强异常安全承诺，STL 容器通过类型特征萃取工具 ``std::move_if_noexcept`` 制定了动态分流策略：

- 当类型 ``T`` 声明了 ``noexcept`` 移动构造函数，或者类型 ``T`` 不具备拷贝构造函数时，返回右值引用（``T&&``），触发高效移动。
- 当类型 ``T`` 的移动构造函数未声明 ``noexcept``（可能抛出异常）且具备合法拷贝构造函数时，强制降级返回 const 左值引用（``const T&``），触发深拷贝迁移。在拷贝迁移过程中，若发生异常，旧内存块中的数据毫发无损，容器仅需析构新内存块已构造的临时副本即可实现无损事务回滚。

.. code-block:: cpp

   // std::move_if_noexcept 核心标准实现模型
   template <typename T>
   [[nodiscard]] constexpr std::conditional_t<
       !std::is_nothrow_move_constructible_v<T> && std::is_copy_constructible_v<T>,
       const T&,
       T&&
   > move_if_noexcept(T& x) noexcept {
       return std::move(x);
   }

.. list-table:: 元素类型特征对 STL 容器扩容策略与异常安全等级的决定性影响
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 移动构造 noexcept 属性
     - 拷贝构造可用性
     - 扩容采用的操作路径
     - 异常安全承诺等级
   * - 显式声明 ``noexcept``
     - 具备或不具备
     - 移动迁移 (Move Relocation)
     - 强异常安全保证 (事务不抛异常)
   * - 未声明 ``noexcept`` (可能抛出)
     - 具备可用拷贝构造
     - 降级为拷贝迁移 (Copy Fallback)
     - 强异常安全保证 (支持事务回滚)
   * - 未声明 ``noexcept`` (可能抛出)
     - 禁用拷贝 (Move-Only 类型)
     - 强制移动迁移 (无可替代方案)
     - **基本异常安全保证 (数据可能处于 moved-from 状态)**

下面实现一个具备异常安全回滚机制的底层内存迁移管道，演示 ``std::move_if_noexcept`` 在工业级容器中的完整落地：

.. code-block:: cpp

   #include <iostream>
   #include <memory>
   #include <type_traits>
   #include <utility>

   struct HeavyResource {
       int id{0};
       bool noexcept_move{true};

       explicit HeavyResource(int val, bool nothrow)
           : id(val), noexcept_move(nothrow) {}

       HeavyResource(const HeavyResource& other) : id(other.id), noexcept_move(other.noexcept_move) {
           std::cout << "-> Copy Construct HeavyResource " << id << "
";
       }

       // 条件 noexcept 声明
       HeavyResource(HeavyResource&& other) noexcept
           : id(std::exchange(other.id, -1)), noexcept_move(other.noexcept_move) {
           std::cout << "-> Move Construct HeavyResource (noexcept) " << id << "
";
       }
   };

   template <typename T, typename Alloc = std::allocator<T>>
   class RelocationEngine {
   public:
       using Traits = std::allocator_traits<Alloc>;

       static void migrate_elements(Alloc& alloc, T* old_mem, size_t count, T* new_mem) {
           size_t migrated = 0;
           try {
               for (; migrated < count; ++migrated) {
                   // 依据 noexcept 属性自动决定转移语义
                   Traits::construct(alloc, new_mem + migrated, std::move_if_noexcept(old_mem[migrated]));
               }
           } catch (...) {
               // 异常回滚分支：仅销毁新内存中已经构造的副本
               for (size_t i = 0; i < migrated; ++i) {
                   Traits::destroy(alloc, new_mem + i);
               }
               throw; // 重新抛出异常，保持 old_mem 中的对象完整无损
           }

           // 迁移成功后，销毁旧内存中的所有对象
           for (size_t i = 0; i < count; ++i) {
               Traits::destroy(alloc, old_mem + i);
           }
       }
   };

   int main() {
       std::allocator<HeavyResource> alloc;
       constexpr size_t count = 3;

       // 1. 分配并构造旧存储
       HeavyResource* old_buffer = alloc.allocate(count);
       for (size_t i = 0; i < count; ++i) {
           std::allocator_traits<decltype(alloc)>::construct(alloc, old_buffer + i, static_cast<int>(i + 1), true);
       }

       // 2. 申请新存储并执行安全迁移
       HeavyResource* new_buffer = alloc.allocate(count * 2);
       std::cout << "Executing Exception-Safe Migration:
";
       RelocationEngine<HeavyResource>::migrate_elements(alloc, old_buffer, count, new_buffer);

       // 3. 资源清理
       for (size_t i = 0; i < count; ++i) {
           std::allocator_traits<decltype(alloc)>::destroy(alloc, new_buffer + i);
       }
       alloc.deallocate(old_buffer, count);
       alloc.deallocate(new_buffer, count * 2);
   }

通过将移动构造函数标记为 ``noexcept``，开发者显式建立了类型与标准库容器之间的信任契约。这一机制使得现代 C++ 在维持严格强异常安全保证的前提下，完全释放了底层连续内存容器的搬迁性能。

小结与下章导读
--------------

本章系统解析了现代 C++ 移动语义与值类别体系的底层物理拓扑：从 lvalue、prvalue、xvalue 的正交分类学与纯右值物化机制，到引用类型的重载决议优先级矩阵；从 ``std::move`` 编译期类型转换本质与 moved-from 对象的有效状态机，到万能引用、引用折叠与 ``std::forward`` 的精准转发链路，最后深入探讨了 ``noexcept`` 契约对 STL 容器扩容强异常安全保证的决定性支撑。

在掌握了对象生命周期与移动语义的微架构后，下一章我们将切入 **物理内存管理体系与 RAII 哲学（04_memory_management_primitives_and_raii.rst）**，系统解构 ``malloc / free`` 与 ``new / delete`` 表达式的机器级拆解、Placement New 原位构造、未初始化内存批量操作算法（``std::uninitialized_*``）以及硬件缓存局部性对内存分配器设计的深度约束。
