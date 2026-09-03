====================================================================================================
std::basic_string 字符串体系：小字符串优化 (SSO) 内部联合体布局、动态扩容与 COW 历史包袱
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块前四节中，我们先后剖析了动态连续数组 ``std::vector``、静态定长数组 ``std::array``、分段连续双端队列 ``std::deque`` 以及离散链表体系 ``std::list`` 与 ``std::forward_list`` 的物理拓扑与内存模型。在所有标准序列容器中，字符序列容器 **``std::basic_string``**（以 ``std::string`` 为典型代表）在工业级微架构中承受了最为激进的性能优化。字符串在实际业务中呈现出极度偏态的分布特征：绝大多数程序运行期产生的字符串（如标识符、日志标签、URL 路径分段、JSON 字段名）长度通常小于 16 或 24 字节。若对每一个短字符串均向堆内存分配器申请独立空间，将导致严重的系统调用开销与堆内存碎片。为了解决这一痛点，现代 C++ 标准库全面采用了 **小字符串优化（Short / Small String Optimization, SSO）**。本章深入解构 ``std::basic_string`` 的三元模板参数解耦契约、写时复制（Copy-On-Write, COW）在多线程并发场景下的历史局限与被标准废弃的物理成因、主流标准库（GCC libstdc++、LLVM libc++ 与 MSVC STL）内部联合体（Union）与判别位布局、字符串尾部零终止符（Null Terminator, ``\0``）的物理不变性，以及 SSO 模式下移动语义退化为内联字节拷贝的微架构机理。

basic_string 架构：CharT、char_traits 与 Allocator
---------------------------------------------------

``std::basic_string`` 在标准库中被定义为泛型字符序列容器模板：

.. code-block:: cpp

   template <
       typename CharT,
       typename Traits = std::char_traits<CharT>,
       typename Allocator = std::allocator<CharT>
   >
   class basic_string;

三大模板参数的分工与正交契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **``CharT``（字符物理基元）**：
   定义了字符串底层存储的最小定宽数据单元。``std::string`` 对应单字节 ``char``，``std::u8string`` 对应 UTF-8 编码单元 ``char8_t``，``std::u16string`` 对应 16 位 ``char16_t``，``std::u32string`` 对应 32 位 ``char32_t``。容器本身仅负责管理 ``CharT`` 的物理存储序列，不解析复杂的 Unicode 字形簇（Grapheme Clusters）与文本换行语义。
2. **``Traits``（字符操作策略类）**：
   将字符级别的物理操作（如长度计算 ``length``、字典序比较 ``compare``、内存拷贝 ``copy`` 与字符匹配 ``find``）解耦为纯静态成员函数。通过特化 ``char_traits``，调用者可定制不区分大小写的比较策略，而无需修改容器主体代码。
3. **``Allocator``（内存分配器）**：
   负责在大字符串模式下向底层堆空间申请与释放原始连续字节内存。

空字符终结符 (Null-Terminator) 物理不变性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++11 之后，标准严格确立了零终止符物理契约：
对于任何非空的合法字符串对象 ``s``，其底层连续内存区间的 ``s.data()[s.size()]`` 必须恒为合法可访问的 ``CharT(0)``（即 ``\0``），且该末尾空字符不计入 ``size()`` 统计。这一不变性保证了 ``s.c_str()`` 与 ``s.data()`` 可以直接在 $\mathcal{O}(1)$ 常数时间内返回完全兼容 C 原生 API 的零终止字符指针，消除了历史实现中由 ``c_str()`` 触发按需补零的性能隐患。

写时复制 (COW) 机制的历史局限与标准淘汰
---------------------------------------

在 C++98/03 时代，主流标准库（如 GCC 4.x 之前的 libstdc++）广泛采用 **写时复制（Copy-On-Write, COW）** 技术实现 ``std::string``。

COW 的设计意图与引用计数拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

COW 假定字符串对象的拷贝频率远高于修改频率。当执行字符串拷贝 ``std::string b = a;`` 时：
- 容器仅进行浅拷贝，使对象 ``b`` 的内部指针直接指向与 ``a`` 共享的同一块堆内存缓冲区。
- 堆内存头部维护一个共享引用计数器（Reference Count）。
- 只有当某一对象试图通过下标或修改接口写入数据时（如 ``a[0] = 'X';``），容器才真正申请新堆内存并执行数据深拷贝分离（Detach）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     COW 共享引用计数与写时分离物理拓扑                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 对象 a ] ----\                                                          |
   |                  +---> [ 堆内存块: Header(RefCnt=2) | Data: "Hello World" ] |
   |   [ 对象 b ] ----/                                                          |
   |                                                                             |
   |   [ 执行写入: a[0] = 'X' 触发 Detach 分离 ]                                 |
   |                                                                             |
   |   [ 对象 a ] --------> [ 新堆内存: Header(RefCnt=1) | Data: "Xello World" ] |
   |                                                                             |
   |   [ 对象 b ] --------> [ 旧堆内存: Header(RefCnt=1) | Data: "Hello World" ] |
   |                                                                             |
   +-----------------------------------------------------------------------------+

多核并发下的微架构惩罚与 C++11 的彻底废弃
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在多核 CPU 体系结构普及后，COW 的共享模型暴露出致命的硬件级性能缺陷：

1. **伪共享与原子操作总线锁竞争（False Sharing & Atomic Contention）**：
   为了保证多线程并发安全，每次只读拷贝与析构必须对共享引用计数执行原子自增（``atomic_fetch_add``）与原子自减。多核 CPU 在高频只读访问共享字符串时，原子指令强制触发 CPU 缓存一致性协议（MESI）中的缓存行失效（Cache Line Invalidation）与跨核缓存行颠簸（Cache Bouncing），使只读并行性能暴跌。
2. **非 const operator[] 的强制分离惩罚**：
   由于语言层面无法静态区分调用者是通过 ``a[i]`` 执行只读访问还是原地写入，非 const 的 ``operator[]`` 必须悲观地触发全量内存深拷贝与分离，导致纯读操作退化为昂贵的堆分配。
3. **C++11 契约的物理冲突**：
   C++11 标准严格规定：只读操作（包括多线程并发调用只读下标）严禁发生数据竞争，且 ``operator[]`` 必须在 $\mathcal{O}(1)$ 最坏时间复杂度内完成。COW 无法同时满足这些并发与复杂度契约，因此在 C++11 标准中被彻底废止。GCC 5.0 正式引入了全新的 SSO ABI，替代了历史上的 COW 实现。

小字符串优化 (SSO) 内部联合体 (Union) 拓扑
------------------------------------------

现代 C++ 标准库全面推行 **小字符串优化（Short String Optimization, SSO）**。其核心思想是将字符串对象自身占用的栈内存设计为一个大尺寸的联合体（Union），在字符串较短时直接将字符存储在栈上，完全绕过堆内存分配器。

SSO 双态内存布局设计
~~~~~~~~~~~~~~~~~~~~

以 64 位系统下的标准库实现为例，``std::string`` 通常占用固定的 24 字节（LLVM libc++）或 32 字节（GCC libstdc++ / MSVC STL）栈空间：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                 std::string 32 字节栈内存 SSO 双态联合体拓扑                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 状态 1: 长字符串模式 (Long String Mode) - 占用堆内存 ]                  |
   |   +-----------------------+-----------------------+---------------------+   |
   |   |  _M_p (8 Bytes)       |  _M_length (8 Bytes)  | _M_capacity (8 Bytes|   |
   |   |  指向独立堆内存缓冲区 |  当前字符序列有效长度 | 当前已分配堆空间容量|   |
   |   +-----------+-----------+-----------------------+---------------------+   |
   |               |                                                             |
   |               v                                                             |
   |           [ 堆内存: Capacity + 1 Bytes (含末尾 '\0') ]                      |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 状态 2: 短字符串模式 (Short / SSO Mode) - 纯栈内联存储 ]                |
   |   +-----------------------+-----------------------+---------------------+   |
   |   |  _M_local_buf (15/16B)|  (剩余内联字节存储)   |  _M_allocated_cap / |   |
   |   |  直接存储字符与 '\0'  |  直接存储字符数据     |  判别标记位 / 长度  |   |
   |   +-----------------------+-----------------------+---------------------+   |
   |   * 绝对零堆分配 (Zero Heap Allocation)                                     |
   |   * 内存数据直接命中 L1 数据缓存行                                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

主流标准库 SSO 容量差异
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 主流标准库 std::string SSO 内部拓扑与内联容量对比
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 标准库实现
     - 对象栈大小 (sizeof)
     - SSO 最大内联字符容量与判别机制
   * - GCC libstdc++ (C++11 ABI)
     - 32 字节
     - 最大容纳 **15 字节**（加 1 字节 ``\0`` 共 16 字节内联缓冲）；通过判断 ``_M_p == _M_local_buf`` 确定是否处于 SSO 态
   * - LLVM libc++
     - 24 字节
     - 最大容纳 **22 字节**；利用最低有效位（LSB Flag）作为长/短态判别标志，极限压缩内部结构体
   * - MSVC STL
     - 32 字节
     - 最大容纳 **15 字节**；内部使用 ``union { _Buf[16], _Ptr }`` 配合 ``_Mysize`` 与 ``_Myres`` 字段管理

SSO 模式下移动语义的微架构退化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于处于堆模式的大字符串，移动构造函数（``std::string(std::string&&)``）仅需交换三个裸指针（浅拷贝所有权），耗时仅为几纳秒。

然而，**对于处于 SSO 模式的短字符串，移动操作无法窃取堆指针**：
- 由于字符数据实际内嵌在源对象的栈帧中，将源对象移动至目标对象必须通过 ``memcpy`` 将 16 字节内联缓冲区整体拷贝至新对象的栈空间。
- 这一微架构特性表明：对于 SSO 短字符串，移动操作的开销与深拷贝完全等价，均表现为栈内字节拷贝。

动态扩容与迭代器/引用失效边界
-----------------------------

``std::basic_string`` 的连续存储特性使其在变易操作下的失效规则与 ``std::vector`` 高度相似，但受 SSO 状态迁移的影响更为复杂。

.. list-table:: std::string 变易操作对迭代器与引用的失效规则
   :widths: 22 30 48
   :header-rows: 1
   :class: tight-table

   * - 容器操作
     - 内部状态变迁
     - 迭代器、指针、引用与 string_view 失效状态
   * - ``append`` / ``push_back``
     - SSO 空间充足（未跨越 15 字节）
     - 仅末尾迭代器失效；指向既有字符的指针与引用 **依然有效**
   * - ``append`` / ``push_back``
     - **触发 SSO 向堆模式跃迁**
     - **全量失效**：底层存储由栈内存迁移至新堆内存，所有既有指针/引用/视图全部失效
   * - ``append`` / ``push_back``
     - 堆模式下触发几何扩容
     - **全量失效**：堆地址重新分配并迁移
   * - ``operator[]`` / ``data()``
     - 只读访问
     - 不引发任何失效；多线程并发只读安全
   * - ``reserve(n)``
     - $n > 	ext{capacity}()$ 触发堆重分配
     - **全量失效**

工业级 C++ 完整 Mini-String 内核实现
------------------------------------

以下 C++ 源码实现了一套工业级自包含的 ``MiniString`` 容器。该实现涵盖：
1. 包含 15 字节内联栈缓冲区（SSO Buffer）与长字符串堆指针的严格 Union 内存布局。
2. 零终止符 ``\0`` 的物理不变性维护。
3. SSO 模式向动态堆模式的平滑扩容跃迁与几何增长策略。
4. 区分 SSO 栈内拷贝与堆指针窃取的移动构造与移动赋值状态机。
5. 完整的端到端测试套件（覆盖 SSO 状态验证、堆跃迁边界、移动语义计数与 C 接口兼容性）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cstring>
   #include <cstddef>
   #include <cassert>
   #include <algorithm>
   #include <stdexcept>

   namespace core_stl {

   class MiniString {
   public:
       using size_type = std::size_t;
       static constexpr size_type SSOCapacity = 15; // 栈上内联最大容纳 15 字符 (+1 字节 '\0')

   private:
       // 长字符串堆内存布局 (24 Bytes)
       struct HeapLayout {
           char* _M_p;
           size_type _M_size;
           size_type _M_capacity;
       };

       // 内部联合体 (总大小固定为 24 字节)
       union {
           HeapLayout _M_heap;
           char _M_local_buf[SSOCapacity + 1]; // 16 字节
       };

       // 标记当前是否处于堆模式 (在 64 位下紧随 union 之后，整体结构 32 字节)
       bool _M_is_heap = false;

   public:
       // =====================================================================
       // 构造与析构体系
       // =====================================================================
       MiniString() noexcept {
           _M_is_heap = false;
           _M_local_buf[0] = '\0';
           set_sso_size(0);
       }

       MiniString(const char* s) {
           assert(s && "Null pointer passed to MiniString constructor");
           size_type len = std::strlen(s);
           init_from_buffer(s, len);
       }

       MiniString(const char* s, size_type len) {
           assert(s && "Null pointer passed to MiniString constructor");
           init_from_buffer(s, len);
       }

       ~MiniString() {
           clear_storage();
       }

       // 拷贝构造函数
       MiniString(const MiniString& other) {
           init_from_buffer(other.data(), other.size());
       }

       // 移动构造函数: 区分 SSO 内联拷贝与堆指针所有权转移
       MiniString(MiniString&& other) noexcept {
           if (other._M_is_heap) {
               // 堆模式: 常数时间指针窃取
               _M_heap = other._M_heap;
               _M_is_heap = true;

               other._M_is_heap = false;
               other._M_local_buf[0] = '\0';
           } else {
               // SSO 模式: 栈内字节拷贝
               _M_is_heap = false;
               std::memcpy(_M_local_buf, other._M_local_buf, SSOCapacity + 1);
               other._M_local_buf[0] = '\0';
           }
       }

       // 拷贝赋值
       MiniString& operator=(const MiniString& other) {
           if (this != &other) {
               MiniString tmp(other);
               swap(tmp);
           }
           return *this;
       }

       // 移动赋值
       MiniString& operator=(MiniString&& other) noexcept {
           if (this != &other) {
               clear_storage();
               if (other._M_is_heap) {
                   _M_heap = other._M_heap;
                   _M_is_heap = true;

                   other._M_is_heap = false;
                   other._M_local_buf[0] = '\0';
               } else {
                   _M_is_heap = false;
                   std::memcpy(_M_local_buf, other._M_local_buf, SSOCapacity + 1);
                   other._M_local_buf[0] = '\0';
               }
           }
           return *this;
       }

       // =====================================================================
       // 状态与访问接口
       // =====================================================================
       [[nodiscard]] size_type size() const noexcept {
           return _M_is_heap ? _M_heap._M_size : std::strlen(_M_local_buf);
       }

       [[nodiscard]] size_type length() const noexcept { return size(); }

       [[nodiscard]] size_type capacity() const noexcept {
           return _M_is_heap ? _M_heap._M_capacity : SSOCapacity;
       }

       [[nodiscard]] bool empty() const noexcept {
           return size() == 0;
       }

       [[nodiscard]] bool is_sso() const noexcept {
           return !_M_is_heap;
       }

       const char* data() const noexcept {
           return _M_is_heap ? _M_heap._M_p : _M_local_buf;
       }

       char* data() noexcept {
           return _M_is_heap ? _M_heap._M_p : _M_local_buf;
       }

       const char* c_str() const noexcept {
           return data();
       }

       char& operator[](size_type index) noexcept {
           assert(index <= size() && "Index out of range");
           return data()[index];
       }

       const char& operator[](size_type index) const noexcept {
           assert(index <= size() && "Index out of range");
           return data()[index];
       }

       // =====================================================================
       // 核心变易与动态扩容
       // =====================================================================
       void push_back(char c) {
           append(&c, 1);
       }

       void append(const char* str, size_type len) {
           size_type curr_len = size();
           size_type new_len = curr_len + len;

           if (new_len > capacity()) {
               // 1.5 倍几何级扩容
               size_type new_cap = std::max(new_len, capacity() + (capacity() >> 1));
               reallocate(new_cap);
           }

           char* dest = data() + curr_len;
           std::memcpy(dest, str, len);
           dest[len] = '\0'; // 维持空终止符不变性

           if (_M_is_heap) {
               _M_heap._M_size = new_len;
           }
       }

       void append(const char* str) {
           append(str, std::strlen(str));
       }

       void swap(MiniString& other) noexcept {
           // 交换联合体与标记位
           char tmp_buf[sizeof(MiniString)];
           std::memcpy(tmp_buf, this, sizeof(MiniString));
           std::memcpy(this, &other, sizeof(MiniString));
           std::memcpy(&other, tmp_buf, sizeof(MiniString));
       }

   private:
       void set_sso_size(size_type len) noexcept {
           _M_local_buf[len] = '\0';
       }

       void clear_storage() noexcept {
           if (_M_is_heap && _M_heap._M_p) {
               delete[] _M_heap._M_p;
               _M_heap._M_p = nullptr;
               _M_is_heap = false;
           }
       }

       void init_from_buffer(const char* s, size_type len) {
           if (len <= SSOCapacity) {
               _M_is_heap = false;
               std::memcpy(_M_local_buf, s, len);
               _M_local_buf[len] = '\0';
           } else {
               _M_is_heap = true;
               _M_heap._M_p = new char[len + 1];
               _M_heap._M_size = len;
               _M_heap._M_capacity = len;
               std::memcpy(_M_heap._M_p, s, len);
               _M_heap._M_p[len] = '\0';
           }
       }

       void reallocate(size_type new_capacity) {
           assert(new_capacity > SSOCapacity);

           char* new_p = new char[new_capacity + 1];
           size_type curr_len = size();

           std::memcpy(new_p, data(), curr_len);
           new_p[curr_len] = '\0';

           clear_storage();

           _M_is_heap = true;
           _M_heap._M_p = new_p;
           _M_heap._M_size = curr_len;
           _M_heap._M_capacity = new_capacity;
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 2. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runStringTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniString 小字符串优化 (SSO) 与内存跃迁测试套件
";
       std::cout << "=======================================================

";

       // 1. 测试短字符串 SSO 模式 (零堆分配)
       {
           core_stl::MiniString short_str = "Hello SSO";
           assert(short_str.is_sso());
           assert(short_str.size() == 9);
           assert(short_str.capacity() == 15);
           assert(short_str[short_str.size()] == '\0'); // 校验末尾零终止符

           // 验证数据指针落在自身栈地址区间内
           const char* internal_ptr = short_str.data();
           const char* obj_ptr = reinterpret_cast<const char*>(&short_str);
           assert(internal_ptr >= obj_ptr && internal_ptr < obj_ptr + sizeof(short_str));

           std::cout << "[测试 1: 短字符串 SSO 内联存储验证]:
"
                     << "  字符串: \"" << short_str.c_str() << "\", 长度: " << short_str.size()
                     << ", 处于 SSO 模式: " << (short_str.is_sso() ? "YES" : "NO") << "

";
       }

       // 2. 测试边界追加与向堆模式的动态跃迁
       {
           core_stl::MiniString str = "12345678"; // 8 字符 (SSO)
           assert(str.is_sso());

           // 追加至 15 字符 (SSO 极限边界)
           str.append("9012345");
           assert(str.size() == 15);
           assert(str.is_sso());
           std::cout << "[测试 2: SSO 满载边界 (15 字节)]: 仍处于 SSO 模式
";

           // 再次追加 1 字符，突破 15 字节阈值，强制跃迁至堆内存模式
           str.push_back('X');
           assert(str.size() == 16);
           assert(!str.is_sso()); // 成功跃迁至堆模式
           assert(str.capacity() >= 16);
           assert(str[16] == '\0');

           std::cout << "  -> 突破 15 字节，成功跃迁至堆内存模式 (容量 = "
                     << str.capacity() << ", 内容 = \"" << str.c_str() << "\")

";
       }

       // 3. 测试移动语义在 SSO 与 Heap 双态下的行为差异
       {
           // 堆模式移动测试 (指针窃取)
           core_stl::MiniString long_a = "This is a very long string exceeding fifteen bytes threshold!";
           assert(!long_a.is_sso());
           const char* heap_addr_before = long_a.data();

           core_stl::MiniString long_b = std::move(long_a);
           assert(!long_b.is_sso());
           assert(long_b.data() == heap_addr_before); // 堆地址零拷贝转移

           // SSO 模式移动测试 (栈内字节拷贝)
           core_stl::MiniString sso_a = "Short";
           assert(sso_a.is_sso());
           core_stl::MiniString sso_b = std::move(sso_a);
           assert(sso_b.is_sso());
           assert(sso_b.data() != sso_a.data()); // 栈内拷贝，目标地址不同

           std::cout << "[测试 3: 移动语义双态验证]:
"
                     << "  堆模式移动: 保持堆指针地址绝对恒定 (零拷贝窃取)
"
                     << "  SSO 模式移动: 栈内 16 字节内联拷贝

";
       }

       std::cout << "  -> MiniString 字符串体系与 SSO 内存拓扑验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了 ``std::basic_string`` 的现代微架构核心机制：

1. **SSO 内联零分配**：在长度 $\le 15$ 字节时，数据首地址 ``data()`` 严格落在对象自身的 32 字节栈内存物理区间内，消除了对堆内存分配器的系统调用。
2. **状态机单向无缝跃迁**：当追加操作使字符长度突破 15 字节时，容器自动分配堆内存并将原内联字符复制到新堆空间，原子切换 ``_M_is_heap`` 状态并扩充容量。
3. **移动语义双态分发**：对于大字符串，移动操作实现了纳秒级的指针解绑与所有权窃取；对于短字符串，移动操作安全回退为微秒级的栈内字节搬移，严格维持了对象的内存独立性与生命周期安全。

小结与全模块结项导读
--------------------

本章系统解构了现代 C++ 字符序列容器 ``std::basic_string`` 的底层微架构与内存模型：

1. **模板架构解耦**：阐明了 ``CharT``、``char_traits`` 与 ``Allocator`` 的正交分工，推导了末尾零终止符（``\0``）物理不变性对 C API 零开销兼容的必要性。
2. **COW 机制被废弃的本质**：剖析了写时复制在多核并发下引发的原子引用计数总线锁竞争、CPU 缓存颠簸与非 const 下标强制分离缺陷，论证了 C++11 废除 COW 的底层物理原因。
3. **SSO 联合体设计与容量拓扑**：解构了 64 位系统下 15/22 字节栈内嵌缓冲区的实现原理，分析了短字符串移动操作退化为栈内字节拷贝的微架构特性。
4. **状态迁移与失效边界**：归纳了字符串从 SSO 向堆内存跃迁时引发的全量迭代器与指针失效规则。

========================================================================
第 3 模块：顺序容器物理拓扑与实现全量完工结项
========================================================================

至此，《现代C++对象模型与STL工程内核全景深度剖析》**第 3 模块（03_sequence_containers_internals）的 5 节核心专著章节已全部全量完工落盘**：
- **01 节**：std::vector 连续内存动态数组：三指针状态模型、几何级扩容迁移、异常安全强保证与 vector<bool> 特化边界
- **02 节**：std::array 固定大小连续内存：聚合初始化、零运行时开销、constexpr 编译期支持与原生数组退化边界
- **03 节**：std::deque 分段连续双端队列：中控 map 指针数组、固定块缓冲 (block)、复合迭代器寻址与两端常数扩容
- **04 节**：链表体系物理拓扑：std::list 环形双向带哨兵节点与 splice 零拷贝剪切、std::forward_list 极简单向链表
- **05 节**：std::basic_string 字符串体系：小字符串优化 (SSO) 内部联合体布局、动态扩容与 COW 历史包袱

在接下来的 **第 4 模块：关联容器、红黑树与哈希表内核（04_associative_and_hash_containers）** 中，我们将正式跨入基于非线性数据结构的关联容器世界。在第 4 模块第 1 节 **红黑树底层平衡机制：五大不变量、黑高约束、左旋右旋拓扑变换与插入/删除重新着色平衡修复（``04_associative_and_hash_containers/01_red_black_tree_invariants_and_balance_repair.rst``）** 中，我们将深入剖析严格弱序、红黑树五大不变性公理、左旋右旋指针变换以及插入/删除后的 4 种失衡场景修复状态机。
