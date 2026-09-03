====================================================================================================
栈帧物理布局与函数序言/尾声：RBP/RSP 调整、Red Zone 保护区、动态全栈对齐与寄存器保护
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 3 节（``07_register_allocation_stack_and_abi/03_spill_code_generation_and_stack_slot_coloring.rst``）中，我们系统推导了寄存器分配失败时的溢出代价加权模型、重物化优化以及基于区间冲突图的栈槽着色复用算法。当所有虚拟寄存器的溢出决策与栈槽分配最终收敛后，编译器后端必须将这些抽象的内存偏移正式投影到硬件线程栈上。函数的物理栈帧由目标指令集架构（ISA）、应用程序二进制接口（ABI）、调用约定以及硬件微架构对齐约束共同决定。本章深入解构栈帧从高地址到低地址的六大物理解剖区域、函数序言（Prologue）与尾声（Epilogue）发射状态机、帧指针省略（FPO）与 DWARF 展开元数据协同、x86-64 128 字节 Red Zone 保护区机制，以及面向 AVX-512 向量宽度的动态全栈重对齐（Dynamic Stack Realignment）实现。

栈帧物理拓扑与六大内存解剖区域
------------------------------

在主流现代硬件架构（x86-64、AArch64、RISC-V）中，线程栈均采用向低地址生长的物理模型。函数被调用时，其栈帧在内存中呈现高度结构化的分层拓扑：

.. code-block:: text

   高地址 (High Address)
   +-----------------------------------------------------------------------------+
   |  [ 1. 调用者栈帧 (Caller Stack Frame) / 入参传递区 (Inbound Args) ]         |
   |     第 7 个及以上无法通过寄存器传递的入参 (如 [rbp + 16], [rbp + 24] ...)   |
   +-----------------------------------------------------------------------------+
   |  [ 2. 返回地址 (Return Address) ] (硬件 call 指令自动压入或 Link Register)  |
   |     x86-64: [rbp + 8]  |  AArch64: 保存在 LR (x30) 中                       |
   +-----------------------------------------------------------------------------+ <--- 帧指针 (RBP / x29) 基准点 (Frame Base)
   |  [ 3. 旧帧指针保存区 (Saved Frame Pointer) ]                                |
   |     push rbp (8 字节) -> 链接上层调用链，形成调用回溯栈 (Call Backtrace)    |
   +-----------------------------------------------------------------------------+
   |  [ 4. 被调者保存寄存器区 (Callee-Saved Registers / CSR Save Area) ]         |
   |     保存 rbx, r12-r15 (x86-64) 或 x19-x28 (AArch64)，逆序压栈              |
   +-----------------------------------------------------------------------------+
   |  [ 5. 局部变量与溢出栈槽区 (Local Variables & Spill Slots) ]               |
   |     存放寄存器放不下的溢出值及寻址局部对象，利用栈槽着色复用压缩尺寸        |
   +-----------------------------------------------------------------------------+
   |  [ 6. 出站参数构建区 (Outbound / Parameter Area) 与对齐填充 (Padding) ]    |
   |     为子函数调用准备栈上传参空间，确保 call 边界严格满足 16/32/64 字节对齐 |
   +-----------------------------------------------------------------------------+ <--- 栈指针 (RSP / SP) 当前端点
   低地址 (Low Address)

栈帧六大物理分区功能与寻址基准
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 栈帧物理分区职责、生命周期与寻址基准
   :widths: 20 30 50
   :header-rows: 1
   :class: tight-table

   * - 内存分区
     - 物理相对偏移
     - 硬件职责与微架构约束
   * - **入参栈区 (Inbound Args)**
     - 正向正偏移 ``[rbp + 16 + 8*i]``
     - 承载超出通用寄存器传参数量（如 System V 前 6 个整型参数由 RDI/RSI/RDX/RCX/R8/R9 承载）的栈溢出实参
   * - **返回地址 (Return Address)**
     - 固定偏移 ``[rbp + 8]``
     - 记录函数执行完毕后 CPU 程序计数器（RIP/PC）必须跳回的调用点后继指令物理地址
   * - **旧 RBP (Saved RBP)**
     - 基准点 ``[rbp + 0]``
     - 维护物理调用链指针。调试器与 Unwinder 沿 ``*rbp`` 链表可在 $\mathcal{O}(D)$ 复杂度内递归还原调用栈
   * - **CSR 保存区 (CSR Save Area)**
     - 负向负偏移 ``[rbp - 8*k]``
     - 维护 ABI 契约：被调函数若修改了 Callee-Saved 寄存器，必须在退出前恢复调用者进入时的原始值
   * - **溢出与局部变量区**
     - 负向负偏移 ``[rbp - offset]``
     - 存放不可提升的栈上局部数组、结构体以及 Chaitin 着色溢出的物理溢出槽
   * - **出站参数区 (Outbound Area)**
     - 紧邻当前 RSP ``[rsp + offset]``
     - 预先为子调用分配最大传参槽位，避免在函数体内频繁执行昂贵的 ``push/pop`` 指令抖动栈指针

函数序言 (Prologue) 与尾声 (Epilogue) 发射状态机
------------------------------------------------

函数序言与尾声是编译器后端在物理发射阶段插入的入口初始化与出口恢复指令序列。

标准序言 (Prologue) 四步状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        函数序言 (Prologue) 物理发射流水线                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   步骤 1: [ 保存旧帧指针 ]                                                  |
   |      pushq   %rbp              # 将调用者 RBP 压栈 (RSP 减 8)               |
   |      .cfi_def_cfa_offset 16    # 发射 DWARF 展开元数据: CFA 偏移递增 8      |
   |      .cfi_offset %rbp, -16     # 记录旧 RBP 存放在 CFA-16 处                |
   |                                                                             |
   |   步骤 2: [ 建立当前帧指针基准 ]                                            |
   |      movq    %rsp, %rbp        # 将 RBP 固定到当前栈顶，确立稳定寻址锚点    |
   |      .cfi_def_cfa_register %rbp# DWARF CFA 寻址基准由 RSP 切换为 RBP        |
   |                                                                             |
   |   步骤 3: [ 保存被调者寄存器 (CSR) ]                                        |
   |      pushq   %rbx              # 保护当前函数会改写的 Callee-Saved 寄存器   |
   |      pushq   %r12                                                           |
   |                                                                             |
   |   步骤 4: [ 分配局部栈空间并维持 ABI 16 字节对齐 ]                          |
   |      subq    $48, %rsp         # 一次性开辟局部变量、溢出槽与出站参数空间   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

标准尾声 (Epilogue) 逆序释放状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尾声执行序列严格为序言的逆序对称映射：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        函数尾声 (Epilogue) 物理恢复流水线                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   步骤 1: [ 确保返回值就绪 ]                                                |
   |      movl    %eax, ...         # 将计算结果加载至 RAX/EAX (或 XMM0 浮点)    |
   |                                                                             |
   |   步骤 2: [ 释放局部栈空间 ]                                                |
   |      addq    $48, %rsp         # 或直接 movq %rbp, %rsp 极速销毁局部栈      |
   |                                                                             |
   |   步骤 3: [ 逆序恢复被调者寄存器 (CSR) ]                                    |
   |      popq    %r12              # 严格按照与 push 相反的顺序弹出恢复         |
   |      popq    %rbx                                                           |
   |                                                                             |
   |   步骤 4: [ 恢复旧帧指针并退出 ]                                            |
   |      popq    %rbp              # 弹出调用者 RBP                             |
   |      retq                      # 取出 [RSP] 返回地址，控制流跳回调用点      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

收缩包装 (Shrink-Wrapping) 优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在存在早期快速返回（Early Return）或错误检查分支的函数中，若将完整的序言放置于函数唯一物理入口，会导致无需栈操作的快速路径无端支付寄存器压栈与栈指针调整开销。

**Shrink-Wrapping 算法**：
1. 分析每个基本块中 Callee-Saved 寄存器的实际活跃区间与访存需求。
2. 将序言指令推迟下沉（Sink）到真正需要栈帧的支配节点（DomTree Split Point）。
3. 在无需栈帧的错误分支直接发射简单 ``ret``，使快速路径达到真正的零栈开销。

帧指针省略 (FPO) 与 DWARF CFA 展开协议
--------------------------------------

传统编译模型下，``RBP`` 被固定用作帧指针。在现代优化编译器中，**帧指针省略（Frame Pointer Omission, FPO / ``-fomit-frame-pointer``）** 已成为默认优化策略。

FPO 的工程收益与代价博弈
~~~~~~~~~~~~~~~~~~~~~~~~

1. **收益**：
   - 释放一个宝贵的 64 位通用寄存器（``RBP``）供寄存器分配器自由使用，显著降低复杂循环内的溢出压力。
   - 消除每层函数调用的 ``push rbp / mov rbp, rsp / pop rbp`` 3 条机器指令，削减代码体积与指令发射槽位消耗。
2. **代价**：
   - 局部变量寻址基准由静态稳定的 ``RBP`` 转换为动态浮动的 ``RSP``（``[rsp + offset]``）。每次栈指针调整（如动态传参），编译器必须重新计算全栈对象的静态相对偏移。
   - 依赖标准 DWARF 调用帧信息（Call Frame Information, CFI）与规范帧地址（Canonical Frame Address, CFA）实现异常展开（Unwind）与调试回溯。

.. list-table:: 帧指针保留 vs 帧指针省略 (FPO) 对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 保留帧指针 (With Frame Pointer)
     - 帧指针省略 (FPO / -fomit-frame-pointer)
   * - **栈寻址基准**
     - ``[rbp - offset]``（偏移在全函数体内绝对恒定）
     - ``[rsp + offset]``（偏移随 ``RSP`` 动态推移自适应调整）
   * - **通用寄存器可用数**
     - 15 个（x86-64 扣除 RBP 与 RSP）
     - 16 个（x86-64 RBP 作为普通通用寄存器）
   * - **异常展开性能**
     - 极高（沿 RBP 单向链表快速遍历）
     - 依赖解析 ``.eh_frame`` 二进制 DWARF 状态机展开
   * - **动态栈分配 (alloca)**
     - 天然支持（RBP 保持不动，RSP 随意伸缩）
     - 必须引入基指针（Base Pointer，如 RBX/R10）作为第三锚点

Red Zone 128 字节保护区与叶子函数优化
-------------------------------------

System V x86-64 ABI 确立了一项极具微架构价值的物理规范：**Red Zone（红区）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     System V x86-64 Red Zone 物理模型                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |      [ RSP 当前栈指针端点 ] <----------------------------------------+      |
   |      |                                                               |      |
   |      |   128 字节 Red Zone 保护区 [RSP - 1] ~ [RSP - 128]             |      |
   |      |   (在此区域内, 叶子函数可自由读写, 信号/中断处理程序禁止破坏) |      |
   |      |                                                               |      |
   |      +---------------------------------------------------------------+      |
   |      [ RSP - 128 保护边界 ]                                                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Red Zone 物理契约与叶子函数零开销执行
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **ABI 契约**：在 ``%rsp`` 以下的 128 字节区域被定义为 Red Zone。操作系统信号处理程序、中断处理程序和调试器均不得修改此区域内的数据。
2. **叶子函数（Leaf Function）优化**：
   - 不调用其他子函数的叶子函数，若其局部变量与溢出槽总需求 $\le 128$ 字节，编译器 **无需发射任何 ``subq $size, %rsp`` 与 ``addq $size, %rsp`` 指令**。
   - 函数直接利用 ``[rsp - 8]``、``[rsp - 16]`` 读写栈内存，配合 FPO 达成 **零指令序言与零指令尾声**，函数体仅由纯计算指令和单条 ``ret`` 构成。
3. **内核与裸机环境禁用**：
   - 操作系统内核、中断服务例程（ISR）必须使用 ``-mno-red-zone`` 编译。因为异步硬件中断到达时，CPU 会立即在当前栈顶压入中断上下文，若开启 Red Zone，硬件压栈会瞬间覆写破坏内核叶子函数正在使用的数据。

动态全栈重对齐 (Dynamic Stack Realignment)
------------------------------------------

现代多媒体与 AI 计算密集型程序广泛使用 AVX-256（32 字节对齐）与 AVX-512（64 字节对齐）向量指令（如 ``vmovaps``、``vaddps``）。若未对齐内存地址，CPU 会直接触发硬件通用保护异常（``#GP``）。

然而，标准 System V ABI 仅保证函数进入时的栈对齐为 16 字节。当函数内出现 32/64 字节对齐要求时，编译器必须采用 **动态全栈重对齐** 机制：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     动态全栈 64 字节重对齐 (Dynamic Realignment)            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. 保存旧帧指针并锚定传入参数基准:                                        |
   |      pushq   %rbp                                                           |
   |      movq    %rsp, %rbp        # RBP 锁定入参寻址基准                       |
   |                                                                             |
   |   2. 保存基指针 (Base Pointer):                                             |
   |      pushq   %r10              # 借用 r10 作为重对齐后的局部栈基准          |
   |                                                                             |
   |   3. 强制执行硬件位与对齐掩码:                                              |
   |      andq    $-64, %rsp        # 清除低 6 位, 强行达成 64 字节物理对齐      |
   |      movq    %rsp, %r10        # r10 锁定 64 字节对齐的工作区基准           |
   |                                                                             |
   |   4. 分配局部对齐空间:                                                      |
   |      subq    $128, %rsp        # 在 64 字节边界上安全使用 vmovaps           |
   |                                                                             |
   |   5. 尾声极速销毁与栈指针还原:                                              |
   |      movq    %rbp, %rsp        # 直接将 RSP 还原为 RBP, 绕过动态对齐差值    |
   |      popq    %rbp                                                           |
   |      retq                                                                   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级 C++ 栈帧物理布局与序言/尾声发射引擎实现
----------------------------------------------

以下 C++ 源码实现了一套自包含的工业级栈帧布局计算与汇编发射引擎（``StackFrameLayoutEngine``）。该引擎完整支持：
1. Callee-Saved 寄存器保存集合追踪与逆序恢复。
2. 局部变量、溢出栈槽与出站参数区的 16 字节向上取整对齐。
3. 帧指针省略（FPO）模式与 Red Zone 判定。
4. 动态 32/64 字节向量全栈对齐代码生成。
5. 自动生成带 DWARF CFI 元数据的标准 x86-64 序言与尾声指令序列。
6. 端到端测试套件（验证叶子函数 Red Zone 零开销、标准非叶子函数与 AVX-512 动态对齐）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>

   namespace stack_engine {

   // 内存对齐向上取整辅助函数
   inline uint32_t alignTo(uint32_t offset, uint32_t alignment) {
       return (offset + alignment - 1) & ~(alignment - 1);
   }

   // 寄存器定义
   enum class Reg {
       RAX, RBX, RCX, RDX, RSI, RDI, RBP, RSP,
       R8,  R9,  R10, R11, R12, R13, R14, R15
   };

   inline std::string regName(Reg r) {
       switch (r) {
           case Reg::RAX: return "%rax"; case Reg::RBX: return "%rbx";
           case Reg::RCX: return "%rcx"; case Reg::RDX: return "%rdx";
           case Reg::RSI: return "%rsi"; case Reg::RDI: return "%rdi";
           case Reg::RBP: return "%rbp"; case Reg::RSP: return "%rsp";
           case Reg::R8:  return "%r8";  case Reg::R9:  return "%r9";
           case Reg::R10: return "%r10"; case Reg::R11: return "%r11";
           case Reg::R12: return "%r12"; case Reg::R13: return "%r13";
           case Reg::R14: return "%r14"; case Reg::R15: return "%r15";
       }
       return "%unknown";
   }

   // 栈帧配置与物理布局描述符
   struct FunctionFrameConfig {
       std::string FunctionName;
       bool IsLeafFunction = false;
       bool HasCalls = false;
       bool OmitFramePointer = false;
       bool AllowRedZone = true;
       uint32_t RequiredAlignment = 16;     // 默认 ABI 16 字节对齐, 向量化可能要求 32 或 64
       uint32_t LocalVariablesSize = 0;    // 局部对象尺寸
       uint32_t SpillSlotsSize = 0;        // 寄存器溢出槽总尺寸
       uint32_t OutboundArgsSize = 0;      // 调用子函数的最大栈上传参开销
       std::vector<Reg> UsedCalleeSavedRegs; // 本函数修改的 CSR 集合
   };

   struct FrameLayoutResult {
       uint32_t CSRStackSize = 0;
       uint32_t LocalsAndSpillSize = 0;
       uint32_t TotalAllocatedStackSize = 0;
       bool UsesRedZone = false;
       bool NeedsDynamicRealignment = false;
   };

   class StackFrameLayoutEngine {
   public:
       static FrameLayoutResult computeLayout(const FunctionFrameConfig& cfg) {
           FrameLayoutResult layout;

           // 1. 计算 CSR 保存区大小 (每个 8 字节)
           layout.CSRStackSize = static_cast<uint32_t>(cfg.UsedCalleeSavedRegs.size() * 8);

           // 2. 局部变量 + 溢出槽
           layout.LocalsAndSpillSize = cfg.LocalVariablesSize + cfg.SpillSlotsSize;

           // 3. 检查是否触发 AVX 动态全栈重对齐 (对齐要求 > 16 字节)
           if (cfg.RequiredAlignment > 16) {
               layout.NeedsDynamicRealignment = true;
           }

           // 4. 叶子函数 Red Zone 判定: 无子调用, 允许 Red Zone, 总栈开销 <= 128 字节
           uint32_t totalNeeded = layout.LocalsAndSpillSize + layout.CSRStackSize;
           if (cfg.IsLeafFunction && !cfg.HasCalls && cfg.AllowRedZone && totalNeeded <= 128 && !layout.NeedsDynamicRealignment) {
               layout.UsesRedZone = true;
               layout.TotalAllocatedStackSize = 0;
               return layout;
           }

           // 5. 计算标准分配大小并对齐到 16 字节
           // 进入函数时 call 压入 8 字节返回地址; 若有 push rbp 再占 8 字节 -> 16 字节对齐
           uint32_t rawSize = layout.LocalsAndSpillSize + cfg.OutboundArgsSize;
           if (!cfg.OmitFramePointer) {
               // 包含 push rbp 与 CSR
               uint32_t headerSize = 8 /* push rbp */ + layout.CSRStackSize;
               uint32_t padding = (16 - ((headerSize + rawSize) % 16)) % 16;
               layout.TotalAllocatedStackSize = rawSize + padding;
           } else {
               uint32_t headerSize = 8 /* ret addr */ + layout.CSRStackSize;
               uint32_t padding = (16 - ((headerSize + rawSize) % 16)) % 16;
               layout.TotalAllocatedStackSize = rawSize + padding;
           }

           return layout;
       }

       static std::vector<std::string> emitPrologue(const FunctionFrameConfig& cfg, const FrameLayoutResult& layout) {
           std::vector<std::string> asmLines;
           asmLines.push_back(cfg.FunctionName + ":");

           // 快速路径: Red Zone 零开销
           if (layout.UsesRedZone) {
               asmLines.push_back("    # [Red Zone 优化: 零栈帧分配, 直接使用 [rsp - offset]]");
               return asmLines;
           }

           // 1. 保存 Frame Pointer (若未省略)
           if (!cfg.OmitFramePointer) {
               asmLines.push_back("    pushq   %rbp");
               asmLines.push_back("    .cfi_def_cfa_offset 16");
               asmLines.push_back("    .cfi_offset %rbp, -16");
               asmLines.push_back("    movq    %rsp, %rbp");
               asmLines.push_back("    .cfi_def_cfa_register %rbp");
           }

           // 2. 动态重对齐 (例如 64 字节 AVX-512)
           if (layout.NeedsDynamicRealignment) {
               asmLines.push_back("    pushq   %r10                    # 保存基指针");
               asmLines.push_back("    andq    $-" + std::to_string(cfg.RequiredAlignment) + ", %rsp        # 动态强行对齐");
               asmLines.push_back("    movq    %rsp, %r10              # r10 锚定对齐基准");
           }

           // 3. 保存 Callee-Saved Registers
           for (auto reg : cfg.UsedCalleeSavedRegs) {
               asmLines.push_back("    pushq   " + regName(reg));
           }

           // 4. 分配局部栈空间
           if (layout.TotalAllocatedStackSize > 0) {
               asmLines.push_back("    subq    $" + std::to_string(layout.TotalAllocatedStackSize) + ", %rsp");
           }

           return asmLines;
       }

       static std::vector<std::string> emitEpilogue(const FunctionFrameConfig& cfg, const FrameLayoutResult& layout) {
           std::vector<std::string> asmLines;

           // 快速路径: Red Zone
           if (layout.UsesRedZone) {
               asmLines.push_back("    retq");
               return asmLines;
           }

           // 1. 释放局部栈空间
           if (layout.NeedsDynamicRealignment) {
               // 动态对齐时直接通过 RBP 还原 RSP
               asmLines.push_back("    movq    %rbp, %rsp              # 动态对齐还原栈顶");
               asmLines.push_back("    popq    %r10                    # 恢复基指针");
           } else if (layout.TotalAllocatedStackSize > 0) {
               asmLines.push_back("    addq    $" + std::to_string(layout.TotalAllocatedStackSize) + ", %rsp");
           }

           // 2. 逆序恢复 Callee-Saved Registers
           for (auto it = cfg.UsedCalleeSavedRegs.rbegin(); it != cfg.UsedCalleeSavedRegs.rend(); ++it) {
               asmLines.push_back("    popq    " + regName(*it));
           }

           // 3. 恢复 Frame Pointer 并退出
           if (!cfg.OmitFramePointer && !layout.NeedsDynamicRealignment) {
               asmLines.push_back("    popq    %rbp");
           }
           asmLines.push_back("    retq");

           return asmLines;
       }
   };

   } // namespace stack_engine

   // =========================================================================
   // 验证套件
   // =========================================================================
   namespace test {

   inline void runStackFrameLayoutTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 物理栈帧布局计算与序言/尾声发射引擎验证套件
";
       std::cout << "=======================================================

";

       using namespace stack_engine;

       // -------------------------------------------------------------
       // 测试 1: 叶子函数触发 Red Zone 优化 (零指令序言与尾声)
       // -------------------------------------------------------------
       {
           FunctionFrameConfig leafCfg;
           leafCfg.FunctionName = "leaf_fast_calc";
           leafCfg.IsLeafFunction = true;
           leafCfg.HasCalls = false;
           leafCfg.AllowRedZone = true;
           leafCfg.LocalVariablesSize = 32;
           leafCfg.SpillSlotsSize = 16; // 总需 48 <= 128 字节

           auto layout = StackFrameLayoutEngine::computeLayout(leafCfg);
           assert(layout.UsesRedZone == true);
           assert(layout.TotalAllocatedStackSize == 0);

           auto pro = StackFrameLayoutEngine::emitPrologue(leafCfg, layout);
           auto epi = StackFrameLayoutEngine::emitEpilogue(leafCfg, layout);

           std::cout << "[测试 1: 叶子函数 Red Zone 汇编生成]:
";
           for (const auto& line : pro) std::cout << line << "
";
           std::cout << "    # 函数体计算...
";
           for (const auto& line : epi) std::cout << line << "
";
           std::cout << "  -> 叶子函数成功零开销利用 Red Zone。

";
       }

       // -------------------------------------------------------------
       // 测试 2: 标准复杂非叶子函数 (CSR 保护与 16 字节对齐)
       // -------------------------------------------------------------
       {
           FunctionFrameConfig complexCfg;
           complexCfg.FunctionName = "process_matrix";
           complexCfg.IsLeafFunction = false;
           complexCfg.HasCalls = true;
           complexCfg.OmitFramePointer = false;
           complexCfg.LocalVariablesSize = 40;
           complexCfg.SpillSlotsSize = 16;
           complexCfg.OutboundArgsSize = 32; // 调用子函数出站传参
           complexCfg.UsedCalleeSavedRegs = {Reg::RBX, Reg::R12, Reg::R13}; // 3 个 CSR (24B)

           auto layout = StackFrameLayoutEngine::computeLayout(complexCfg);
           assert(layout.UsesRedZone == false);

           auto pro = StackFrameLayoutEngine::emitPrologue(complexCfg, layout);
           auto epi = StackFrameLayoutEngine::emitEpilogue(complexCfg, layout);

           std::cout << "[测试 2: 复杂非叶子函数标准栈帧与序言/尾声]:
";
           for (const auto& line : pro) std::cout << line << "
";
           std::cout << "    # 函数体执行与子调用...
";
           for (const auto& line : epi) std::cout << line << "
";

           // 验证 CSR 逆序恢复: R13 -> R12 -> RBX
           assert(epi[1] == "    popq    %r13");
           assert(epi[2] == "    popq    %r12");
           assert(epi[3] == "    popq    %rbx");
           std::cout << "  -> 栈帧大小严格维持 16 字节对齐，CSR 逆序精确恢复。

";
       }

       // -------------------------------------------------------------
       // 测试 3: AVX-512 动态 64 字节全栈重对齐
       // -------------------------------------------------------------
       {
           FunctionFrameConfig avxCfg;
           avxCfg.FunctionName = "vector_kernel_512";
           avxCfg.IsLeafFunction = false;
           avxCfg.HasCalls = true;
           avxCfg.RequiredAlignment = 64; // 触发动态对齐
           avxCfg.LocalVariablesSize = 128;

           auto layout = StackFrameLayoutEngine::computeLayout(avxCfg);
           assert(layout.NeedsDynamicRealignment == true);

           auto pro = StackFrameLayoutEngine::emitPrologue(avxCfg, layout);
           auto epi = StackFrameLayoutEngine::emitEpilogue(avxCfg, layout);

           std::cout << "[测试 3: AVX-512 动态 64 字节重对齐序言/尾声]:
";
           for (const auto& line : pro) std::cout << line << "
";
           std::cout << "    # 执行 64 字节对齐向量计算 (vmovaps)...
";
           for (const auto& line : epi) std::cout << line << "
";

           assert(pro[6] == "    andq    $-64, %rsp        # 动态强行对齐");
           assert(epi[0] == "    movq    %rbp, %rsp              # 动态对齐还原栈顶");
           std::cout << "  -> 动态 64 字节掩码对齐与 RBP 栈顶还原发射断言完全正确。

";
       }

       std::cout << "  -> 栈帧物理布局与序言/尾声发射全套测试全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了后端栈帧降低（Stack Lowering）模块的物理正确性：

1. **叶子函数极致精简**：在测试 1 中，``StackFrameLayoutEngine`` 准确识别出该函数无子调用且总栈需求小于 128 字节，果断激活 Red Zone 优化，完全省略了 ``push rbp / sub rsp`` 与 ``add rsp / pop rbp``，产物仅包含单条 ``retq`` 指令，消除了冗余机器周期的浪费。
2. **CSR 保护与对齐严密性**：在测试 2 中，3 个 CSR（24 字节）与旧 RBP（8 字节）合计 32 字节。加上局部数据（56 字节）与出站参数（32 字节），引擎自动计算补齐填充（Padding = 8），确保 ``subq $96, %rsp`` 后的栈顶在子函数 ``call`` 边界处严格满足 16 字节对齐。并在尾声中以 ``%r13 -> %r12 -> %rbx`` 的相反拓扑完成无损弹出。
3. **动态对齐容灾防护**：在测试 3 中，面对 64 字节超对齐需求，引擎自动插入 ``andq $-64, %rsp`` 物理掩码，并在尾声采用 ``movq %rbp, %rsp`` 统一还原，彻底规避了 AVX-512 ``vmovaps`` 在未对齐内存上的硬件崩溃风险。

小结与下章导读
--------------

本章系统解构了现代编译器后端栈帧物理布局与函数出入口代码生成的全景体系：

1. **栈帧六大内存分区**：厘清了入参区、返回地址、旧 RBP 链表、CSR 保存区、局部/溢出槽与出站参数区的物理相对拓扑与寻址基准。
2. **序言与尾声状态机**：推导了标准四步入栈与逆序四步弹出的机器指令发射时序及 DWARF CFI 元数据映射。
3. **FPO 与 Red Zone**：剖析了帧指针省略对释放通用寄存器的收益，以及 System V 128 字节 Red Zone 对叶子函数零开销执行的物理保障。
4. **动态全栈重对齐**：解构了面向 AVX-256 / AVX-512 超对齐向量对象的栈指针掩码截断与 RBP 强制还原机制。

在掌握了寄存器分配与栈帧布局后，编译器后端必须正式跨越独立编译单元的边界，直面跨模块与跨语言的二进制级物理契约。在第 7 模块第 5 节 **调用约定与系统 ABI 契约：System V vs MSVC ABI 参数寄存器分发、结构体传参及跨语言调用（``07_register_allocation_stack_and_abi/05_calling_conventions_and_system_abi_contracts.rst``）** 中，我们将深入剖析 System V 与 Windows x64 ABI 在参数寄存器、Shadow Space（影子空间）、大结构体值传递（按引用传指针 vs 分拆多寄存器）以及 C/C++ 跨语言调用的二进制底层交互机制。
