====================================================================================================
调用约定与系统 ABI 契约：System V vs MSVC ABI 参数寄存器分发、结构体传参及跨语言调用
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 4 节（``07_register_allocation_stack_and_abi/04_stack_frame_layout_prologue_and_epilogue.rst``）中，我们系统剖析了单函数内部的栈帧六大分区、函数序言与尾声状态机、帧指针省略（FPO）以及 Red Zone 物理保护区。当程序执行跨越函数调用边界、独立编译单元、甚至跨越不同编程语言（如 C/C++、Rust、Swift、Python C 扩展）与不同操作系统（Linux、macOS、Windows）时，底层的二进制交互依赖于严格的 **应用二进制接口（Application Binary Interface, ABI）** 与 **调用约定（Calling Conventions）**。本章深入剖析 System V AMD64 ABI 与 Windows MSVC x64 ABI 的核心参数分发状态机、影子空间（Shadow Space）内存协议、聚合体（结构体）分类与隐藏返回指针（``sret``）机制、以及多语言跨边界调用的二进制兼容性防线。

系统级 ABI 核心契约模型
-----------------------

函数调用在高级源码中表现为参数列表与返回值的传递，但在硬件机器级，它是一组关于机器状态（寄存器与内存）的严密协议。调用者（Caller）与被调用者（Callee）必须对以下五项物理事实达成完全一致：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        系统级 ABI 二进制协议五大核心支柱                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. 参数分发规则 (Parameter Passing) ]                                   |
   |      - 整数、指针、浮点与向量参数映射至物理寄存器的序列与优先级             |
   |      - 超出寄存器容量时的入栈顺序 (从右向左 / 从左向右) 与栈对齐要求         |
   |                                                                             |
   |   [ 2. 返回值承载协议 (Return Value Location) ]                             |
   |      - 标量值存放的主返回寄存器 (如 RAX, XMM0, r0)                          |
   |      - 大结构体返回值使用的隐藏指针 (Hidden sret Pointer) 分配与传递协议     |
   |                                                                             |
   |   [ 3. 寄存器保护责任划分 (Register Preservation Rules) ]                   |
   |      - Caller-saved (Volatile / Scratch): 调用者视其易失，跨调用需自行保护   |
   |      - Callee-saved (Non-volatile / CSR): 被调用者承诺使用前备份、退出前恢复|
   |                                                                             |
   |   [ 4. 栈帧拓扑与对齐契约 (Stack Layout & Alignment) ]                       |
   |      - 函数调用点（call 指令处）必须满足的栈对齐基准 (如 16 字节对齐)        |
   |      - 是否存在预留的影子空间 (Shadow Space / Home Space)                   |
   |      - 叶子函数是否允许使用栈底以下受保护的 Red Zone                        |
   |                                                                             |
   |   [ 5. 跨语言符号与元数据规范 (Symbols & Unwinding) ]                       |
   |      - 符号修饰法则 (Name Mangling) 与 C 语言导出 (extern "C")              |
   |      - DWARF / Windows SEH 异常展开表与栈回溯元数据                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

System V AMD64 ABI vs Windows MSVC x64 ABI 全景对比
---------------------------------------------------

在 x86-64 架构下，两大主流操作系统阵营（类 Unix 的 System V 与 Windows 的 MSVC）采用了截然不同的 ABI 设计范式：

.. list-table:: System V AMD64 ABI 与 Windows MSVC x64 ABI 核心物理特性对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - System V AMD64 ABI (Linux / macOS / FreeBSD)
     - Microsoft MSVC x64 ABI (Windows)
   * - **通用参数寄存器**
     - **6 个**：``%rdi, %rsi, %rdx, %rcx, %r8, %r9``
     - **4 个**：``%rcx, %rdx, %r8, %r9``
   * - **浮点参数寄存器**
     - **8 个**：``%xmm0 - %xmm7``
     - **4 个**：``%xmm0 - %xmm3``
   * - **参数槽位绑定机制**
     - **双池独立分类**：整数与浮点参数分别在各自寄存器池内独立按序填充
     - **位置严格绑定**：第 1~4 个参数槽位一一对应（如第 1 参数为浮点则占 XMM0，此时 RCX 作废不可用于第 2 参数）
   * - **影子空间 (Shadow Space)**
     - **无**
     - **必须分配 32 字节**：调用者必须在栈顶为前 4 个寄存器参数预留 32 字节溢出槽
   * - **Red Zone 保护区**
     - **支持 128 字节**（位于 ``%rsp`` 以下）
     - **无**（中断随时可能破坏栈顶下方内存）
   * - **被调用者保护寄存器 (CSR)**
     - ``%rbx, %rsp, %rbp, %r12, %r13, %r14, %r15``
     - ``%rbx, %rbp, %rdi, %rsi, %rsp, %r12, %r13, %r14, %r15, %xmm6-%xmm15 (低64位)``
   * - **可变参数函数协议**
     - ``%al`` 存放使用的 SSE 浮点寄存器数量（0~8）
     - 浮点参数若位于前 4 个槽位，调用者须同时向对应通用寄存器备份位模式

参数分发状态机与影子空间微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了直观展现两者差异，考虑如下函数调用：

.. code-block:: c

   void example(double a, int b, double c, int d, int e);

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |             System V 与 Windows x64 参数落位物理映射对比                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ System V AMD64 ABI ]:                                                   |
   |      - 参数 1 (double a) -> %xmm0 (浮点池第 1 个)                           |
   |      - 参数 2 (int b)    -> %rdi  (整数池第 1 个)                           |
   |      - 参数 3 (double c) -> %xmm1 (浮点池第 2 个)                           |
   |      - 参数 4 (int d)    -> %rsi  (整数池第 2 个)                           |
   |      - 参数 5 (int e)    -> %rdx  (整数池第 3 个)                           |
   |      * 全部 5 个参数完整放入寄存器，栈消耗 = 0 字节!                        |
   |                                                                             |
   |   [ Windows MSVC x64 ABI ]:                                                 |
   |      - 槽位 1 (double a) -> %xmm0 (RCX 闲置)                                |
   |      - 槽位 2 (int b)    -> %rdx  (XMM1 闲置)                               |
   |      - 槽位 3 (double c) -> %xmm2 (R8 闲置)                                 |
   |      - 槽位 4 (int d)    -> %r9   (XMM3 闲置)                               |
   |      - 槽位 5 (int e)    -> [RSP + 32] (溢出至栈上)                         |
   |      * 调用者必须在栈上开辟 32 字节 Shadow Space + 8 字节参数 5 = 40 字节!   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

ARM64 AAPCS64 标准模型
~~~~~~~~~~~~~~~~~~~~~~

在 64 位 ARM（AArch64）架构中，AAPCS64 规定了更宽的寄存器窗口：
- **通用参数/返回值**：``x0 - x7``（前 8 个整数或指针参数，同时 ``x0``/``x1`` 作为返回值）。
- **浮点/向量参数**：``v0 - v7``（前 8 个浮点或 SIMD 向量参数）。
- **间接结果位置寄存器 (XR)**：``x8``，专门用于承载大结构体返回值的内存地址指针。
- **帧指针与链接寄存器**：``x29``（FP）与 ``x30``（LR，存放返回地址）。

结构体传参分类与隐藏返回指针 (sret)
-----------------------------------

当参数或返回值为复合聚合体（结构体、联合体、数组）时，ABI 规定了严密的分类算法：

Eightbyte 八字节分类算法 (System V)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

System V 将结构体按 8 字节对齐的切片（Eightbyte）递归打散分类：
1. **尺寸判定**：若结构体尺寸超过 16 字节（2 个 Eightbyte），或者包含不可拆分的未对齐字段，直接归类为 ``MEMORY``，全部通过栈传递。
2. **切片分类**：若尺寸 $\le 16$ 字节，分别分析每个 8 字节切片内部的字段类型：
   - 全为整型/指针 $	o$ ``INTEGER``（占用 1 个通用参数寄存器，如 ``%rdi``）。
   - 全为浮点型 $	o$ ``SSE``（占用 1 个 XMM 寄存器，如 ``%xmm0``）。
   - 混合型 $	o$ 优先级合并：只要包含整型，该 8 字节切片即提升为 ``INTEGER``。

大结构体返回与隐藏参数 (sret) 状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当函数返回一个无法放入寄存器的大结构体（如 24 字节对象）时，编译器执行 **结构体返回降级（Struct Return Lowering, sret）**：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      sret 隐藏返回指针物理流转状态机                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. [ 调用者 (Caller) 准备缓冲区 ]:                                        |
   |      Caller 在自身局部栈帧中开辟 24 字节内存空间: `lea -24(%rbp), %rdi`     |
   |                                                                             |
   |   2. [ 隐式参数注入 ]:                                                      |
   |      Caller 将该缓冲区指针作为 **第 1 个隐式实参** 写入 %rdi (System V)     |
   |      或 %rcx (MSVC)，原有的显式参数依次顺延向后移动一个槽位!                |
   |                                                                             |
   |   3. [ 被调用者 (Callee) 写入数据 ]:                                        |
   |      Callee 接收隐式指针，计算出字段结果并直接写入该内存区域。              |
   |                                                                             |
   |   4. [ 返回值同步 ]:                                                        |
   |      Callee 将该内存指针复制回 %rax 并执行 `retq`，Caller 直接无拷贝使用。  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

跨语言调用 (FFI) 与 ABI 稳定性防线
----------------------------------

在现代工程中，C++、Rust、Swift 与 Python 经常在同一进程空间内互相调用。跨语言边界能够正常通信的物理基石是 **C 语言 ABI 标准**：

.. list-table:: 跨语言 FFI 关键防线与常见踩坑边界
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 跨语言交互维度
     - 潜在破坏性缺陷
     - 工业级防御策略
   * - **符号修饰 (Mangling)**
     - C++ / Rust 编译器默认对函数名进行重载与命名空间编码，导致 C 链接器无法解析
     - 显式声明 ``extern "C"``（C++）或 ``#[no_mangle] pub extern "C"``（Rust）抑制修饰
   * - **结构体内存对齐与填充**
     - 不同语言编译器对结构体 Padding 策略不一致导致字段偏移错位
     - 显式标注 ``#pragma pack``、``alignas`` 或 Rust ``#[repr(C)]`` 确保内存拓扑绝对一致
   * - **异常与栈展开 (Unwind)**
     - C++ 异常跨越 C ABI 边界抛出会导致栈展开器找不到 Landing Pad 触发程序崩溃
     - 在跨语言导出函数外部全量包裹 ``catch (...)``，通过返回值错误码传递失败
   * - **非平凡类型 (Non-Trivial)**
     - 包含自定义析构函数或拷贝构造函数的 C++ 类在参数传递时会破坏 ABI 寄存器降级
     - 跨边界仅传递 POD（Plain Old Data）标量、裸指针或不透明句柄（Opaque Pointer）

工业级 C++ 完整 ABI 参数分发与结构体分类器实现
----------------------------------------------

以下 C++ 源码实现了一套自包含的 ABI 参数分发引擎。该实现涵盖：
1. 数据类型与复合结构体模型。
2. System V AMD64 双池分类状态机。
3. Windows MSVC x64 四槽位位置绑定与 32 字节影子空间调度。
4. 大结构体 ``sret`` 隐藏指针自动提升。
5. 端到端测试套件（验证 System V vs MSVC 的物理寄存器与栈槽映射差异）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <cstdint>
   #include <cassert>

   namespace abi_engine {

   // =========================================================================
   // 1. 数据类型与参数模型
   // =========================================================================
   enum class BaseType {
       INTEGER,   // 8/16/32/64 位整数或指针
       FLOAT_FP,  // 32/64 位浮点数 (float, double)
       STRUCT     // 聚合结构体
   };

   struct TypeInfo {
       BaseType Kind;
       uint32_t SizeBytes;
       uint32_t Alignment;
       std::vector<TypeInfo> FieldTypes; // 用于 STRUCT
   };

   enum class LocKind {
       REG_GP,    // 通用寄存器
       REG_XMM,   // XMM 浮点寄存器
       STACK_SLOT // 栈槽
   };

   struct ArgLocation {
       LocKind Kind;
       std::string RegName;
       int32_t StackOffset = 0;
       bool IsHiddenSret = false;

       std::string toString() const {
           if (Kind == LocKind::REG_GP || Kind == LocKind::REG_XMM) {
               return RegName + (IsHiddenSret ? " (sret)" : "");
           } else {
               return "Stack[+" + std::to_string(StackOffset) + "]";
           }
       }
   };

   // =========================================================================
   // 2. System V AMD64 ABI 分发器
   // =========================================================================
   class SystemVDispatcher {
   public:
       static std::vector<ArgLocation> lowerFunctionArgs(const std::vector<TypeInfo>& argTypes,
                                                        const TypeInfo& returnType) {
           std::vector<ArgLocation> locations;
           std::vector<std::string> gpRegs = {"%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"};
           std::vector<std::string> xmmRegs = {"%xmm0", "%xmm1", "%xmm2", "%xmm3", "%xmm4", "%xmm5", "%xmm6", "%xmm7"};

           uint32_t gpIdx = 0;
           uint32_t xmmIdx = 0;
           uint32_t stackOffset = 0;

           // 1. 检查返回值是否为大结构体 (> 16 字节)
           if (returnType.Kind == BaseType::STRUCT && returnType.SizeBytes > 16) {
               // 占用首个通用寄存器作为 sret
               locations.push_back({LocKind::REG_GP, gpRegs[gpIdx++], 0, true});
           }

           // 2. 分发各显式参数
           for (const auto& type : argTypes) {
               if (type.Kind == BaseType::INTEGER) {
                   if (gpIdx < gpRegs.size()) {
                       locations.push_back({LocKind::REG_GP, gpRegs[gpIdx++], 0, false});
                   } else {
                       locations.push_back({LocKind::STACK_SLOT, "", static_cast<int32_t>(stackOffset), false});
                       stackOffset += 8;
                   }
               } else if (type.Kind == BaseType::FLOAT_FP) {
                   if (xmmIdx < xmmRegs.size()) {
                       locations.push_back({LocKind::REG_XMM, xmmRegs[xmmIdx++], 0, false});
                   } else {
                       locations.push_back({LocKind::STACK_SLOT, "", static_cast<int32_t>(stackOffset), false});
                       stackOffset += 8;
                   }
               } else if (type.Kind == BaseType::STRUCT) {
                   if (type.SizeBytes <= 16 && gpIdx < gpRegs.size()) {
                       // 简化模拟: 8 字节结构体直接走通用寄存器
                       locations.push_back({LocKind::REG_GP, gpRegs[gpIdx++], 0, false});
                   } else {
                       locations.push_back({LocKind::STACK_SLOT, "", static_cast<int32_t>(stackOffset), false});
                       stackOffset += ((type.SizeBytes + 7) / 8) * 8;
                   }
               }
           }

           return locations;
       }
   };

   // =========================================================================
   // 3. Windows MSVC x64 ABI 分发器
   // =========================================================================
   class MSVCx64Dispatcher {
   public:
       static std::vector<ArgLocation> lowerFunctionArgs(const std::vector<TypeInfo>& argTypes,
                                                        const TypeInfo& returnType,
                                                        uint32_t& outShadowSpaceBytes) {
           std::vector<ArgLocation> locations;
           std::vector<std::string> gpSlots = {"%rcx", "%rdx", "%r8", "%r9"};
           std::vector<std::string> xmmSlots = {"%xmm0", "%xmm1", "%xmm2", "%xmm3"};

           outShadowSpaceBytes = 32; // Windows x64 强制保留 32 字节影子空间
           uint32_t slotIdx = 0;
           uint32_t stackOffset = 32; // 栈上参数排在 32 字节影子空间之后

           // 1. 检查返回值是否需要 sret (> 8 字节结构体)
           if (returnType.Kind == BaseType::STRUCT && returnType.SizeBytes > 8) {
               locations.push_back({LocKind::REG_GP, gpSlots[slotIdx++], 0, true});
           }

           // 2. 按槽位严格分发
           for (const auto& type : argTypes) {
               if (slotIdx < 4) {
                   if (type.Kind == BaseType::FLOAT_FP) {
                       locations.push_back({LocKind::REG_XMM, xmmSlots[slotIdx], 0, false});
                   } else {
                       locations.push_back({LocKind::REG_GP, gpSlots[slotIdx], 0, false});
                   }
                   slotIdx++;
               } else {
                   locations.push_back({LocKind::STACK_SLOT, "", static_cast<int32_t>(stackOffset), false});
                   stackOffset += 8;
               }
           }

           return locations;
       }
   };

   } // namespace abi_engine

   // =========================================================================
   // 4. 端到端测试与 ABI 差异验证套件
   // =========================================================================
   namespace test {

   inline void runCallingConventionTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 系统 ABI (System V vs Windows x64) 参数分发验证套件
";
       std::cout << "=======================================================

";

       using namespace abi_engine;

       // 混合参数签名: void test(double a, int b, double c, int d, int e)
       std::vector<TypeInfo> mixedArgs = {
           {BaseType::FLOAT_FP, 8, 8, {}}, // a (double)
           {BaseType::INTEGER,  4, 4, {}}, // b (int)
           {BaseType::FLOAT_FP, 8, 8, {}}, // c (double)
           {BaseType::INTEGER,  4, 4, {}}, // d (int)
           {BaseType::INTEGER,  4, 4, {}}  // e (int)
       };
       TypeInfo voidRet = {BaseType::INTEGER, 0, 0, {}};

       // 1. 验证 System V AMD64 参数双池分发
       std::cout << "[测试 1: System V 混合参数分发 (void foo(double, int, double, int, int))]:
";
       auto sysvLocs = SystemVDispatcher::lowerFunctionArgs(mixedArgs, voidRet);
       for (size_t i = 0; i < sysvLocs.size(); ++i) {
           std::cout << "  Arg " << (i + 1) << " -> " << sysvLocs[i].toString() << "
";
       }

       assert(sysvLocs.size() == 5);
       assert(sysvLocs[0].RegName == "%xmm0"); // 浮点池 0
       assert(sysvLocs[1].RegName == "%rdi");  // 整数池 0
       assert(sysvLocs[2].RegName == "%xmm1"); // 浮点池 1
       assert(sysvLocs[3].RegName == "%rsi");  // 整数池 1
       assert(sysvLocs[4].RegName == "%rdx");  // 整数池 2
       std::cout << "  -> System V 成功将全部 5 个参数打包进物理寄存器 (零栈开销)。

";

       // 2. 验证 Windows MSVC x64 四槽位与影子空间
       std::cout << "[测试 2: MSVC x64 混合参数分发 (同一签名)]:
";
       uint32_t shadowBytes = 0;
       auto msvcLocs = MSVCx64Dispatcher::lowerFunctionArgs(mixedArgs, voidRet, shadowBytes);
       for (size_t i = 0; i < msvcLocs.size(); ++i) {
           std::cout << "  Arg " << (i + 1) << " -> " << msvcLocs[i].toString() << "
";
       }
       std::cout << "  Shadow Space = " << shadowBytes << " 字节
";

       assert(msvcLocs.size() == 5);
       assert(msvcLocs[0].RegName == "%xmm0");       // 槽位 1 (Float)
       assert(msvcLocs[1].RegName == "%rdx");        // 槽位 2 (Int)
       assert(msvcLocs[2].RegName == "%xmm2");       // 槽位 3 (Float)
       assert(msvcLocs[3].RegName == "%r9");         // 槽位 4 (Int)
       assert(msvcLocs[4].Kind == LocKind::STACK_SLOT && msvcLocs[4].StackOffset == 32); // 溢出至栈
       assert(shadowBytes == 32);
       std::cout << "  -> MSVC x64 严格按 4 槽位映射，参数 5 正确溢出至 Shadow Space 之后。

";

       // 3. 验证大结构体 sret 隐藏指针注入
       // BigStruct (24 字节): struct { long x, y, z; };
       TypeInfo bigStructRet = {BaseType::STRUCT, 24, 8, {}};
       std::vector<TypeInfo> simpleArgs = {{BaseType::INTEGER, 8, 8, {}}}; // (long seed)

       std::cout << "[测试 3: 大结构体返回 (BigStruct foo(long seed))]:
";
       auto sretLocs = SystemVDispatcher::lowerFunctionArgs(simpleArgs, bigStructRet);
       for (size_t i = 0; i < sretLocs.size(); ++i) {
           std::cout << "  Entry " << (i + 1) << " -> " << sretLocs[i].toString() << "
";
       }

       assert(sretLocs.size() == 2);
       assert(sretLocs[0].IsHiddenSret && sretLocs[0].RegName == "%rdi"); // sret 占领第 1 参数
       assert(sretLocs[1].RegName == "%rsi");                            // 原始参数 seed 顺延至 %rsi
       std::cout << "  -> sret 隐藏指针成功注入 %rdi，显式参数无缝后移。

";

       std::cout << "  -> ABI 与调用约定全套分发引擎验证全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰印证了现代编译器在应对不同操作系统 ABI 规范时的底层分发机制：

1. **寄存器池架构对比**：在测试 1 与测试 2 中，面对完全相同的 C 语言签名 ``(double, int, double, int, int)``，System V 引擎凭借整数与浮点双池独立计数，成功将全部 5 个参数打入 2 个 XMM 与 3 个 GP 寄存器；而 MSVC 引擎由于 4 槽位绝对绑定，第 3 槽位为浮点导致 ``%r8`` 报废，最终导致第 5 个参数被迫压入栈中，且强制开辟了 32 字节的影子空间。
2. **sret 隐藏参数穿透**：在测试 3 中，针对 24 字节的大结构体返回，引擎自动将调用者的栈缓冲区地址提升为第 1 隐式实参占据 ``%rdi``，并将开发者编写的第一个显式参数 ``seed`` 顺延调整至 ``%rsi``，在二进制层严密维持了跨模块调用的契约一致性。

小结与下章导读
--------------

本章系统解构了现代编译器在跨越函数边界与语言边界时的系统级 ABI 契约：

1. **ABI 五大支柱**：深入分析了参数分发、返回值承载、Caller/Callee-saved 寄存器保护、栈帧拓扑对齐与跨语言符号修饰的核心模型。
2. **System V 与 MSVC 物理博弈**：对比了 6 GP/8 XMM 双池独立映射与 4 槽位严格绑定加 32 字节影子空间的体系差异。
3. **结构体降级与 sret 机制**：推导了 Eightbyte 分类算法与隐藏返回指针自动注入的状态机。
4. **跨语言 FFI 安全防线**：确立了 ``extern "C"``、内存对齐统一、异常截断与仅传递平凡类型的多语言互操作准则。

至此，本书 **第 7 模块（07_register_allocation_stack_and_abi）全量完工结项**。在完成了中间代码优化、指令选择、指令调度、寄存器分配与 ABI 降级后，编译器输出的机器指令必须被固化为操作系统可识别的二进制目标文件，并由链接器最终装配。在下一模块第 1 节 **第 8 模块第 1 节：目标文件物理拓扑：段 (Sections) 与加载段 (Segments)、符号表、DWARF 调试行表 (.debug_line)（``08_linking_runtime_vms_and_jit/01_object_file_formats_elf_macho_and_pe.rst``）** 中，我们将深入剖析 ELF、Mach-O 与 PE 格式的底层物理文件拓扑、节头/程序头表、符号重定位以及 DWARF 调试元数据的封装机理。
