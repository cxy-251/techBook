====================================================================================================
目标机模型与硬件描述：TargetTriple、DataLayout 字节序/对齐、寻址模式与合法化 (Legalization)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 1 至第 5 模块中，我们系统构建了编译器的前端（词法分词、递归下降/Pratt 解析、符号表与类型推导）与中端优化管线（三地址码 IR、控制流图 CFG、SSA 构造与销毁、格理论数据流分析、GVN/CSE、SCCP、MemorySSA 内存别名与循环优化）。在中端优化期间，编译器基于机器无关的抽象值流展开分析，操作数具有任意合法的位宽（如 ``i1``、``i32``、``i128``），内存访问被建模为抽象的 GEP 指针偏移，控制流表现为纯粹的基本块跳转。然而，编译器的终极使命是将抽象程序语义精准投影至具体的物理硅基芯片（如 x86-64、AArch64、RISC-V、ARM Thumb 等）。从本章开始，我们正式开启全书第 6 模块（``06_backend_and_instruction_selection``），全面进军编译器后端（Backend / Code Generation）。作为连接中端与底层的核心桥梁，本章深入剖析目标机抽象模型、TargetTriple 规范、DataLayout 内存物理排布与自然对齐法则、硬件微架构复杂寻址模式（Addressing Modes）匹配，以及将中端非原生类型与操作降级为目标机物理支持形式的 **合法化（Legalization）** 状态机。

目标机抽象与 TargetTriple 拓扑规范
----------------------------------

编译器后端首先必须知晓目标硬件环境与操作系统契约。现代编译器（如 LLVM 与 GCC）通过 **TargetTriple（目标三元组/四元组）** 形式化定义执行环境。

TargetTriple 四元组拓扑
~~~~~~~~~~~~~~~~~~~~~~~

标准 TargetTriple 采用下划线与短横线分隔的四元组字符串：

.. math::

   	ext{TargetTriple} = \langle 	ext{Architecture} \rangle - \langle 	ext{Vendor} \rangle - \langle 	ext{OperatingSystem} \rangle - \langle 	ext{Environment/ABI} \rangle

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       TargetTriple 四元组拓扑映射结构                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 示例 1: x86_64-unknown-linux-gnu ]                                      |
   |      * Architecture: x86_64 (Intel/AMD 64 位 x86 架构)                      |
   |      * Vendor:       unknown (通用厂商)                                     |
   |      * OS:           linux (Linux 内核系统调用)                             |
   |      * ABI:          gnu (GNU glibc 运行库与 System V AMD64 ABI)            |
   |                                                                             |
   |   [ 示例 2: aarch64-apple-darwin ]                                          |
   |      * Architecture: aarch64 (ARM 64 位 AArch64 架构)                       |
   |      * Vendor:       apple (苹果定制芯片微架构)                             |
   |      * OS:           darwin (macOS / iOS XNU 内核)                          |
   |      * ABI:          (默认 Apple ARM64 Calling Convention)                  |
   |                                                                             |
   |   [ 示例 3: riscv32-unknown-elf ]                                           |
   |      * Architecture: riscv32 (RISC-V 32 位基础整数指令集 RV32I)             |
   |      * Vendor:       unknown                                                |
   |      * OS:           none/elf (裸机固件环境 Bare-Metal)                     |
   |      * ABI:          elf (EABI 静态嵌入式规范)                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

子目标特征 (Subtarget Features) 与 CPU 微架构模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

除了宏观架构外，TargetTriple 进一步结合 **CPU 家族型号（如 ``-mcpu=cortex-a78`` / ``-march=skylake``）** 与 **子特性标志位（Subtarget Features）** 进行精细化硬件描述：
- ``+avx512f`` / ``+avx512vl``：开启 x86 512 位向量指令集。
- ``+neon`` / ``+fp16``：开启 ARM64 高级 SIMD 与半精度浮点硬件加速。
- ``+m`` / ``+a`` / ``+f`` / ``+d`` / ``+c``：声明 RISC-V 的乘除法、原子操作、单双精度浮点与压缩指令扩展。

DataLayout 规范：字节序、指针宽度与对齐约束
--------------------------------------------

**DataLayout（数据布局字符串）** 是编译器中端与后端之间最具约束力的内存排布契约。它严格定义了目标机在内存层面的物理组织规则。

DataLayout 规范编码格式
~~~~~~~~~~~~~~~~~~~~~~~

在 LLVM IR 中，DataLayout 表现为一段由连字符分隔的规格指示符字符串，例如：

.. code-block:: text

   "e-m:e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f64:64:64-a:0:64-n8:16:32:64-S128"

.. list-table:: DataLayout 核心指示符语义与硬件物理映射
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 指示符语法
     - 参数含义
     - 物理微架构意义
   * - ``e`` / ``E``
     - 字节序 (Endianness)
     - ``e``：小端序（Little-Endian，低位字节在低地址，x86/ARM）；``E``：大端序（Big-Endian，IBM s390x）
   * - ``p[n]:size:abi:pref``
     - 地址空间指针排布
     - 地址空间 $n$ 中指针的物理大小为 ``size`` 位，ABI 强制对齐为 ``abi`` 位，硬件首选对齐为 ``pref`` 位
   * - ``iN:size:abi:pref``
     - 整数类型对齐规范
     - $N$ 位整型（如 ``i32``）在内存中的分配大小与对齐约束（如 ``i32:32:32`` 代表占 32 位且 4 字节对齐）
   * - ``fN:size:abi:pref``
     - 浮点类型对齐规范
     - IEEE-754 浮点型（如 ``f64``）占用 64 位且要求 8 字节自然对齐
   * - ``a:size:abi:pref``
     - 聚合体 (Struct) 基础对齐
     - 结构体默认的基础物理对齐下限
   * - ``n8:16:32:64``
     - 原生整数位宽 (Native Ints)
     - 目标 CPU ALU 具备原生单周期计算能力的整数位宽集合
   * - ``S128``
     - 栈帧对齐约束 (Stack Align)
     - 函数调用栈帧在 ``call`` 指令执行前必须保持的物理字节对齐（如 128 位 = 16 字节对齐）

结构体字段填充 (Padding) 与自然对齐计算
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

依据 DataLayout 规则，结构体每个字段的偏移量必须满足其类型的 **自然对齐（Natural Alignment）** 要求：

.. math::

   	ext{Offset}_{k+1} = 	ext{AlignTo}\left( 	ext{Offset}_k + 	ext{Size}_k, 	ext{Align}_{k+1} \right)

其中 $	ext{AlignTo}(X, A) = (X + A - 1) \ \& \ \sim(A - 1)$。
若未对齐，编译器强制在字段之间插入未初始化的填充字节（Padding Bytes）。

硬件寻址模式 (Addressing Modes) 与 GEP 指针折叠
----------------------------------------------

在中端 IR 中，多维数组与结构体的访问表现为通用的 ``getelementptr``（GEP）计算树。
现代 CPU 指令集在硬件硬件微架构中集成了高度专化的 **复杂寻址单元（Address Generation Unit, AGU）**。

常见硬件寻址模式分类
~~~~~~~~~~~~~~~~~~~~

.. list-table:: 主流硬件架构寻址模式对照
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 寻址模式分类
     - 汇编语法形态 (Assembly)
     - 硬件计算语义与指令集支持
   * - **基址 + 偏移量 (Base + Disp)**
     - ``[RBP - 8]`` / ``[X0, #16]``
     - $	ext{Addr} = 	ext{Reg}_{	ext{base}} + 	ext{Imm}$（全架构标配）
   * - **基址 + 变址 (Base + Index)**
     - ``[RAX + RCX]`` / ``[X0, X1]``
     - $	ext{Addr} = 	ext{Reg}_{	ext{base}} + 	ext{Reg}_{	ext{index}}$
   * - **比例变址寻址 (SIB 字节)**
     - ``[RAX + RCX * 4 + 32]``
     - $	ext{Addr} = 	ext{Base} + 	ext{Index} 	imes 	ext{Scale} + 	ext{Disp}$（x86 专有，Scale $\in \{1, 2, 4, 8\}$）
   * - **前变址自增 (Pre-Indexed)**
     - ``ldr x0, [x1, #8]!``
     - $	ext{Addr} = x_1 + 8$，且执行后原子写回 $x_1 \leftarrow x_1 + 8$（ARM64 专有）
   * - **后变址自增 (Post-Indexed)**
     - ``ldr x0, [x1], #8``
     - $	ext{Addr} = x_1$，且执行后原子写回 $x_1 \leftarrow x_1 + 8$（ARM64 专有）

GEP 指针算术向硬件寻址操作数折叠
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在指令选择前夕，后端的一大核心优化是将多条连续的 GEP 乘法与加法计算，**整体折叠入单一内存加载指令的寻址操作数中**：

.. code-block:: text

   [ 中端分离的 GEP 算术指令流 ]
   1. %offset = mul i64 %idx, 4
   2. %ptr = add i64 %base, %offset
   3. %addr = add i64 %ptr, 32
   4. %val = load i32, ptr %addr

   ====== 经过后端寻址模式折叠 (Address Folding) ======

   [ 最终生成的单条 x86-64 机器指令 ]
   mov eax, dword ptr [rdi + rsi * 4 + 32]

三条算术指令被彻底消除，ALU 负载归零，寻址计算完全由硬件 AGU 硬件流水线在加载周期的同一拍内并行完成。

类型与操作合法化 (Legalization) 状态机
--------------------------------------

中端 IR 是完全无约束的强类型系统（支持任意位宽的整型如 ``i1``、``i7``、``i128``、任意向量类型如 ``v16f32``）。
然而，具体的物理 CPU 寄存器和 ALU 只能直接处理有限的原生合法类型（Legal Types，如 32 位与 64 位整数）。
**合法化（Legalization）** 是后端进入指令选择之前的刚性预处理阶段，负责将非法类型与不支持的操作重构为硬件原生的合法指令形态。

类型合法化的四大处理动作 (Type Legalization Actions)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 类型合法化核心转换策略
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 转换动作
     - 适用场景特征
     - 物理转换状态机
   * - **提升 (Promote)**
     - 非法小位宽整数（如 ``i1``、``i8``、``i16`` 在 32 位机器上）
     - 将变量位宽扩充至合法的较大原生寄存器（通过符号扩展 ``SIGN_EXTEND`` 或零扩展 ``ZERO_EXTEND`` 提升至 ``i32``）
   * - **展开 / 拆分 (Expand)**
     - 非法超大位宽整数（如 64 位架构上的 ``i128``，或 32 位架构上的 ``i64``）
     - 将大类型切分为多个高低位独立的小合法类型（如 ``i128`` 切分为 ``Lo_i64`` 与 ``Hi_i64``），通过带进位加法（``ADD`` + ``ADC``）实现运算
   * - **软件模拟 (Soft-Float)**
     - 目标机无硬件浮点协处理器（FPU）
     - 将浮点算术替换为对编译器运行时支持库（如 ``compiler-rt`` / ``libgcc``）的运行时函数调用（如调用 ``__adddf3``）
   * - **标量化 (Scalarize)**
     - 目标机不支持 SIMD 向量类型（如 ``<4 x i32>``）
     - 将向量解构为 4 个独立的标量运算依次执行

操作合法化的四大分类 (Operation Legalization)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于某个具体的抽象操作码（如 ``SDiv``、``BSwap``、``FMax``）：
1. **``Legal``**：目标机原生支持，直接交付指令选择。
2. **``Custom``**：目标后端提供了自定义的 C++ 降级 Lowering 挂钩。
3. **``Expand``**：通用后端管线自动将其展开为更基础的等价运算组合（例如将除以常数展开为乘以魔数倒数 ``Magic Constant`` 加移位）。
4. **``LibCall``**：生成标准的 ABI 运行时库函数调用。

工业级 C++ 目标机模型与合法化引擎实现
--------------------------------------

以下 C++ 源码实现了一套自包含的工业级目标机描述模型（TargetMachine）与类型合法化器（TypeLegalizer）。该实现涵盖：
1. TargetTriple 架构解析（支持 x86-64、AArch64、RISC-V 32）。
2. DataLayout 内存排布与结构体自然对齐填充计算器。
3. 针对超大位宽整数（``i128``）的低/高位双寄存器拆分与带进位（Add-with-Carry）展开合法化器。
4. 包含 DataLayout 对齐计算与 128 位加法进位降级验证的端到端测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <sstream>
   #include <cstdint>
   #include <cassert>
   #include <algorithm>

   namespace backend_engine {

   // =========================================================================
   // 1. TargetTriple 与架构描述
   // =========================================================================
   enum class ArchType {
       X86_64,
       AArch64,
       RISCV32
   };

   enum class Endianness {
       LittleEndian,
       BigEndian
   };

   struct TargetTriple {
       ArchType Arch = ArchType::X86_64;
       std::string Vendor = "unknown";
       std::string OS = "linux";
       std::string Environment = "gnu";

       static TargetTriple parse(const std::string& tripleStr) {
           TargetTriple tt;
           if (tripleStr.find("x86_64") != std::string::npos) tt.Arch = ArchType::X86_64;
           else if (tripleStr.find("aarch64") != std::string::npos) tt.Arch = ArchType::AArch64;
           else if (tripleStr.find("riscv32") != std::string::npos) tt.Arch = ArchType::RISCV32;
           return tt;
       }

       [[nodiscard]] size_t getPointerSizeInBits() const noexcept {
           return (Arch == ArchType::RISCV32) ? 32 : 64;
       }
   };

   // =========================================================================
   // 2. DataLayout 内存排布与结构体对齐计算器
   // =========================================================================
   class DataLayout {
   public:
       Endianness Endian = Endianness::LittleEndian;
       std::unordered_map<std::string, size_t> TypeAlignments; // 类型 -> 对齐字节数
       std::unordered_map<std::string, size_t> TypeSizes;      // 类型 -> 大小字节数

       DataLayout() {
           // 默认 64 位小端序布局
           Endian = Endianness::LittleEndian;
           TypeSizes["i1"]  = 1; TypeAlignments["i1"]  = 1;
           TypeSizes["i8"]  = 1; TypeAlignments["i8"]  = 1;
           TypeSizes["i16"] = 2; TypeAlignments["i16"] = 2;
           TypeSizes["i32"] = 4; TypeAlignments["i32"] = 4;
           TypeSizes["i64"] = 8; TypeAlignments["i64"] = 8;
           TypeSizes["ptr"] = 8; TypeAlignments["ptr"] = 8;
           TypeSizes["f64"] = 8; TypeAlignments["f64"] = 8;
       }

       [[nodiscard]] size_t alignTo(size_t offset, size_t alignment) const noexcept {
           assert(alignment > 0);
           return (offset + alignment - 1) & ~(alignment - 1);
       }

       // 计算结构体物理大小与各字段字节偏移 (自动插入 Padding)
       struct StructLayout {
           size_t TotalSize = 0;
           size_t StructAlignment = 1;
           std::vector<size_t> FieldOffsets;
       };

       [[nodiscard]] StructLayout computeStructLayout(const std::vector<std::string>& fieldTypes) const {
           StructLayout layout;
           size_t currentOffset = 0;
           size_t maxAlign = 1;

           for (const auto& ftype : fieldTypes) {
               assert(TypeSizes.count(ftype) && "Unknown type in DataLayout");
               size_t fSize = TypeSizes.at(ftype);
               size_t fAlign = TypeAlignments.at(ftype);

               maxAlign = std::max(maxAlign, fAlign);
               currentOffset = alignTo(currentOffset, fAlign); // 对齐当前字段

               layout.FieldOffsets.push_back(currentOffset);
               currentOffset += fSize;
           }

           layout.StructAlignment = maxAlign;
           layout.TotalSize = alignTo(currentOffset, maxAlign); // 尾部填充使结构体总长为其对齐倍数
           return layout;
       }
   };

   // =========================================================================
   // 3. 机器级虚拟指令与合法化展开器
   // =========================================================================
   enum class LegalOp {
       Add,       // 原生加法
       AddWithCarry, // 带进位加法 (ADC)
       MovImm,    // 立即数加载
       Ret
   };

   struct MachineInst {
       LegalOp Op;
       std::string Dest;
       std::string Src1;
       std::string Src2;
       int64_t Imm = 0;

       std::string toString() const {
           std::stringstream ss;
           switch (Op) {
               case LegalOp::Add:
                   ss << "  " << Dest << " = add " << Src1 << ", " << Src2;
                   break;
               case LegalOp::AddWithCarry:
                   ss << "  " << Dest << " = adc " << Src1 << ", " << Src2;
                   break;
               case LegalOp::MovImm:
                   ss << "  " << Dest << " = mov " << Imm;
                   break;
               case LegalOp::Ret:
                   ss << "  ret " << Src1;
                   break;
           }
           return ss.str();
       }
   };

   class TypeLegalizer {
   public:
       // 将 64 位硬件上非法的 i128 加法降级为合法的双 64 位加法序列
       // %res_128 = add i128 %a_128, %b_128
       // ===>
       // %res_lo = add %a_lo, %b_lo
       // %res_hi = adc %a_hi, %b_hi
       static std::vector<MachineInst> legalizeAddI128(
           const std::string& dest,
           const std::string& src1,
           const std::string& src2)
       {
           std::vector<MachineInst> insts;

           // 低 64 位普通加法 (更新硬件 Carry 进位标志)
           insts.push_back({
               LegalOp::Add,
               dest + "_lo",
               src1 + "_lo",
               src2 + "_lo",
               0
           });

           // 高 64 位带进位加法 (消耗 Carry 标志)
           insts.push_back({
               LegalOp::AddWithCarry,
               dest + "_hi",
               src1 + "_hi",
               src2 + "_hi",
               0
           });

           return insts;
       }
   };

   } // namespace backend_engine

   // =========================================================================
   // 4. 端到端测试与合法化验证套件
   // =========================================================================
   namespace test {

   inline void runBackendLegalizationTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 目标机描述、DataLayout 排布与类型合法化验证套件
";
       std::cout << "=======================================================

";

       using namespace backend_engine;

       // 1. 测试 TargetTriple 解析
       TargetTriple tt = TargetTriple::parse("x86_64-apple-darwin");
       assert(tt.Arch == ArchType::X86_64);
       assert(tt.getPointerSizeInBits() == 64);
       std::cout << "[测试 1: TargetTriple 解析]: 成功识别 64 位架构 x86_64, 指针位宽: 64 bits

";

       // 2. 测试 DataLayout 结构体自动对齐与 Padding 计算
       // 结构体定义:
       // struct SensorPacket {
       //     char flag;      // 1 字节, 对齐 1
       //     // 3 字节 Padding
       //     int id;         // 4 字节, 对齐 4
       //     double reading; // 8 字节, 对齐 8
       //     short tag;      // 2 字节, 对齐 2
       //     // 6 字节 Padding (使总大小满足 8 的倍数)
       // };
       DataLayout dl;
       std::vector<std::string> fields = {"i8", "i32", "f64", "i16"};
       auto layout = dl.computeStructLayout(fields);

       std::cout << "[测试 2: DataLayout 结构体对齐排布计算]:
";
       std::cout << "  字段 0 (i8):  偏移 = " << layout.FieldOffsets[0] << " 字节
";
       std::cout << "  字段 1 (i32): 偏移 = " << layout.FieldOffsets[1] << " 字节 (插入 3 字节填充)
";
       std::cout << "  字段 2 (f64): 偏移 = " << layout.FieldOffsets[2] << " 字节
";
       std::cout << "  字段 3 (i16): 偏移 = " << layout.FieldOffsets[3] << " 字节
";
       std::cout << "  结构体总大小 = " << layout.TotalSize << " 字节 (总对齐 = " << layout.StructAlignment << " 字节)

";

       assert(layout.FieldOffsets[0] == 0);
       assert(layout.FieldOffsets[1] == 4);
       assert(layout.FieldOffsets[2] == 8);
       assert(layout.FieldOffsets[3] == 16);
       assert(layout.TotalSize == 24); // (16 + 2 = 18) -> 对齐到 8 的倍数 = 24

       // 3. 测试超大类型 i128 加法合法化展开
       std::cout << "[测试 3: i128 非法类型加法合法化拆分]:
";
       auto legalInsts = TypeLegalizer::legalizeAddI128("val128_res", "val128_a", "val128_b");
       for (const auto& inst : legalInsts) {
           std::cout << inst.toString() << "
";
       }

       assert(legalInsts.size() == 2);
       assert(legalInsts[0].Op == LegalOp::Add);
       assert(legalInsts[1].Op == LegalOp::AddWithCarry);
       std::cout << "  -> 成功将单条 i128 运算展开为硬件支持的 ADD + ADC 进位链。

";

       std::cout << "  -> 目标机模型与后端合法化引擎测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展现了编译器后端接手代码生成时的核心转换：

1. **精准内存对齐计算**：``DataLayout`` 引擎准确为包含 ``char``、``int``、``double`` 与 ``short`` 的异构复合结构体插入了 3 字节与 6 字节填充，将其总大小收敛至严格满足 8 字节对齐的 24 字节，确保了生成的加载指令绝不发生非对齐硬件惩罚（Misaligned Access Penalty）。
2. **非法类型无损展开**：``TypeLegalizer`` 成功捕获了 64 位硬件不支持的 ``i128`` 抽象加法，并将其拆解为低位 ``add`` 与高位 ``adc``（带进位加法）的机器指令对，保证了算术进位链（Carry Chain）在硬件寄存器层面的精确传递。

小结与下章导读
--------------

本章系统解构了现代编译器后端直面目标硬件微架构的物理基石与契约模型：

1. **TargetTriple 拓扑模型**：剖析了架构、厂商、OS 与环境四元组，阐明了硬件 Subtarget Features 对开启 AVX/NEON 特性的指导作用。
2. **DataLayout 内存物理规范**：形式化定义了大小端序、指针宽度、原生类型对齐以及结构体 Padding 填充计算公式。
3. **硬件寻址模式与 GEP 折叠**：展示了基址变址比例寻址（SIB）与自增寻址的硬件优势，剖析了将多条 GEP 算术指令折叠入单条内存操作数的微架构过程。
4. **合法化状态机**：推导了提升（Promote）、展开（Expand）、软浮点（Soft-Float）与标量化（Scalarize）的类型降级机理。

在确立了目标机模型并完成类型合法化之后，编译器的核心任务便是将中端抽象操作映射为最优的目标指令序列。在第 6 模块第 2 节 **指令选择算法：树形覆盖匹配、SelectionDAG 图重写与 GlobalISel 现代后端管线（``06_backend_and_instruction_selection/02_instruction_selection_and_dag_pattern_matching.rst``）** 中，我们将深入剖析树形覆盖（Tree Parsing）动态规划算法、Maximal Munch 贪心算法、SelectionDAG 节点图重写折叠，以及 LLVM 全新一代 GlobalISel 线性流水线架构。
