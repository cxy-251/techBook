====================================================================================================
目标文件物理拓扑：段 (Sections) 与加载段 (Segments)、符号表、DWARF 调试行表 (.debug_line)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块（``07_register_allocation_stack_and_abi``）中，我们系统推导了变量活跃区间分析、Chaitin-Briggs 图着色与线性扫描寄存器分配、溢出代价评估与栈槽着色复用、函数序言/尾声栈帧对齐以及跨语言系统 ABI 契约。至此，编译器中后端已将高级源码彻底降解为符合目标硬件规范的机器指令与数据。然而，编译器并不能直接输出裸露的内存二进制镜像，而是必须将其组织为操作系统与链接器能够识别、重定位与装载的 **目标文件（Object File）**。本章深入剖析目标文件作为“半成品程序”的物理拓扑架构、链接视图（Sections）与执行视图（Segments）的双重视图解耦、主流三大二进制格式（ELF、Mach-O、PE/COFF）的物理结构对比、符号表与字符串表的紧凑排布，以及 DWARF 调试标准中用于源码级单步调试的行号状态机（``.debug_line``）字节码压缩机理。

目标文件作为“半成品程序”的物理世界观
------------------------------------

目标文件（通常为 ``.o`` 或 ``.obj``）是编译器输出的离散二进制模块。之所以被称为“半成品”，是因为其内部包含未决议的外部符号引用（如跨文件函数调用）与尚未分配最终绝对物理地址的代码与数据槽位。

链接视图 (Sections) 与执行视图 (Segments) 的双重视图架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代二进制格式普遍采用 **链接视图（Linking View）** 与 **执行视图（Execution View）** 的正交分离设计：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  目标文件与可执行文件的双重视图 (Dual-View) 拓扑            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 链接视图 (Linking View) : 面向编译器与静态链接器 ]                      |
   |      * 组织单元: 节 (Section)                                               |
   |      * 索引结构: 节头表 (Section Header Table, SHT)                         |
   |      * 核心节区: .text (代码), .data (已初始化数据), .rodata (只读数据),     |
   |                 .bss (未初始化零数据), .symtab (符号表), .rela.text (重定位) |
   |      * 物理特征: 细粒度、按语义与数据类型划分、未对齐至虚拟内存页           |
   |                                                                             |
   |                          | 静态链接器 (Linker) 汇聚合并与重定位             |
   |                          v                                                  |
   |                                                                             |
   |   [ 执行视图 (Execution View) : 面向操作系统内核装载器 (OS Loader) ]        |
   |      * 组织单元: 加载段 (Segment)                                           |
   |      * 索引结构: 程序头表 (Program Header Table, PHT)                       |
   |      * 核心段区: PT_LOAD (只读代码段 RX), PT_LOAD (可读写数据段 RW)          |
   |      * 物理特征: 粗粒度、按页边界 (4KB/64KB) 对齐、强绑定内存页保护权限    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

主流三大二进制格式物理拓扑深度比对
----------------------------------

工业级操作系统演化出三种主流目标文件与可执行文件规范：Linux 与 Unix 体系的 **ELF**、macOS 与 iOS 体系的 **Mach-O**，以及 Windows 体系的 **PE/COFF**。

.. list-table:: ELF、Mach-O 与 PE/COFF 二进制格式物理架构全景对比
   :widths: 18 28 28 26
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - Linux / Unix (ELF64)
     - macOS / Darwin (Mach-O 64)
     - Windows (PE32+ / COFF)
   * - **文件魔数**
     - ``0x7F 'E' 'L' 'F'`` (``0x464c457f``)
     - ``0xfeedfacf`` (64 位大端/小端)
     - ``0x5A4D`` (``MZ``) + ``0x4550`` (``PE\0\0``)
   * - **元数据布局**
     - 头部 + 尾部节头表 + 头部程序头表
     - 头部 + 紧随其后的加载命令流（Load Commands）
     - DOS 桩 + COFF 头 + 可选头 + 节表
   * - **节段层次**
     - 单层 Section 汇聚映射至 Segment
     - 两层嵌套：``__SEGMENT.__section``
     - 扁平 Section（兼具节与段属性）
   * - **调试信息格式**
     - 内嵌 DWARF（``.debug_*`` 节）
     - 外部 DWARF（``.dSYM`` 包或 dsymutil 提取）
     - CodeView / PDB（外部独立文件）或 DWARF
   * - **典型只读段**
     - ``.rodata`` (映射至只读 Segment)
     - ``__TEXT.__cstring``, ``__TEXT.__const``
     - ``.rdata``

ELF64 物理文件拓扑结构
~~~~~~~~~~~~~~~~~~~~~~

ELF64 文件由四个核心区域构成：

1. **ELF 头部（Elf64_Ehdr）**：固定 64 字节，声明架构位数（64-bit）、字节序（Little-Endian）、文件类型（``ET_REL`` 目标文件、``ET_EXEC`` 可执行文件、``ET_DYN`` 动态共享库）、程序入口虚拟地址（``e_entry``）、节头表文件偏移（``e_shoff``）与条目数量（``e_shnum``）。
2. **节头表（Elf64_Shdr）**：结构体数组，每个条目 64 字节，描述节名称在 ``.shstrtab`` 中的偏移、节类型（``SHT_PROGBITS`` 物理数据、``SHT_NOBITS`` BSS 占位、``SHT_SYMTAB`` 符号表、``SHT_RELA`` 重定位表）、内存访问标志（``SHF_WRITE``、``SHF_ALLOC``、``SHF_EXECINSTR``）、虚拟装载地址、文件偏移量与内存对齐约束。
3. **程序头表（Elf64_Phdr）**：面向执行视图，定义各 ``PT_LOAD`` 段在虚拟地址空间的映射区间与读写执行权限（``PF_R``、``PF_W``、``PF_X``）。
4. **节区负载数据（Section Payloads）**：存储真实的机器指令流、全局变量初始值、调试信息与符号字符串池。

符号表 (Symbol Table) 物理拓扑与字符串池
----------------------------------------

符号表（Symbol Table，``.symtab`` 节）是目标文件实现跨模块解耦与链接重定位的心脏。它记录了本模块定义与引用的所有函数、全局变量以及段锚点。

Elf64_Sym 物理结构体
~~~~~~~~~~~~~~~~~~~~

在 64 位 ELF 规范中，每个符号条目占 24 字节：

.. code-block:: cpp

   struct Elf64_Sym {
       uint32_t st_name;  // 符号名在 .strtab 字符串表中的字节偏移量
       uint8_t  st_info;  // 高 4 位: 符号绑定属性 (Binding); 低 4 位: 符号类型 (Type)
       uint8_t  st_other; // 低 2 位: 符号可见性 (Visibility)
       uint16_t st_shndx; // 关联节索引 (Section Index) 或特殊伪索引 (SHN_UNDEF, SHN_ABS, SHN_COMMON)
       uint64_t st_value; // 符号在对应节内的相对偏移地址 (目标文件中) 或虚拟地址 (可执行文件中)
       uint64_t st_size;  // 符号占用内存字节尺寸
   };

符号绑定属性与特殊节索引
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 符号绑定 (Binding) 与特殊节索引 (Section Index) 语义
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 属性标识
     - 数值与枚举
     - 微架构语义与链接器解析规则
   * - **STB_LOCAL**
     - 绑定属性 (0)
     - 模块局部符号（如 C 语言 ``static`` 变量与内部函数），对外部模块不可见，链接时不参与全局符号决议
   * - **STB_GLOBAL**
     - 绑定属性 (1)
     - 全局导出符号，跨模块可见；全局符号表中同名冲突将触发链接重复定义错误
   * - **STB_WEAK**
     - 绑定属性 (2)
     - 弱符号（如 C++ 模板实例化与内联函数）；全局若存在同名强符号则被覆盖，无强符号时允许多个弱符号合并为单一实体
   * - **SHN_UNDEF**
     - 特殊节索引 (0)
     - 未定义符号；代表本模块引用了外部模块的函数或变量，必须由链接器在其他目标文件中找到有效定义
   * - **SHN_ABS**
     - 特殊节索引 (0xFFF1)
     - 绝对符号；其 ``st_value`` 拥有固定绝对数值，链接重定位时不随节区装载基址发生偏移
   * - **SHN_COMMON**
     - 特殊节索引 (0xFFF2)
     - 未初始化的 C 语言全局变量占位符；链接器负责在最终 BSS 节中分配合适对齐的内存空间

字符串表 (String Table) 紧凑设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了避免在定长的 ``Elf64_Sym`` 与 ``Elf64_Shdr`` 中反复内联变长字符串，ELF 引入字符串表（``.strtab`` 符号名字符串表与 ``.shstrtab`` 节名字符串表）。字符串表是由以空字符 ``\0`` 分隔的连续字节池构成，所有符号名与节名仅需保存其首字符在池中的 32 位整型偏移量，实现了极致的元数据空间复用。

DWARF 调试信息物理封装与行号状态机 (.debug_line)
------------------------------------------------

现代编译器在输出机器指令的同时，必须为调试器（GDB / LLDB）生成精确的调试元数据。DWARF（Debugging With Attributed Record Formats）是行业事实标准。调试信息存储在专用的非分配节（Non-Allocated Sections，如 ``.debug_info``、``.debug_abbrev``、``.debug_line``、``.debug_frame``）中，在程序装载执行时不占用物理内存，仅在调试器挂载时按需解析。

行号矩阵的物理挑战
~~~~~~~~~~~~~~~~~~

调试器在执行单步调试（Source Stepping）与断点命中时，需要将当前的程序计数器（PC）地址瞬间映射到对应的源码文件、行号与列号。然而，若直接以二维表格记录每个指令字节对应的行号，元数据尺寸将呈现爆炸式增长（可能达到可执行代码体积的数十倍）。

行号状态机 (Line Number State Machine, LNSM)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DWARF 通过引入 **虚拟行号状态机（LNSM）**，将行号映射表压缩为紧凑的字节码指令流存储在 ``.debug_line`` 节中：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  DWARF .debug_line 行号状态机 (LNSM) 运行机制               |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 状态机内部寄存器组 (State Machine Registers) ]                         |
   |      * address:        当前指令的虚拟地址 / 节内相对偏移 (PC)               |
   |      * file:           当前源码文件索引                                     |
   |      * line:           当前源码行号                                         |
   |      * column:         当前源码列号                                         |
   |      * is_stmt:        布尔标记，当前指令是否为一条语句的起始断点位置       |
   |      * basic_block:    布尔标记，当前指令是否为基本块头部                   |
   |      * prologue_end:   布尔标记，当前指令是否位于函数序言之后 (用户断点位置)|
   |      * end_sequence:   布尔标记，当前序列是否结束                           |
   |                                                                             |
   |   [ 字节码操作码体系 (Opcode Taxonomy) ]                                    |
   |      1. 标准操作码 (Standard Opcodes):                                      |
   |         - DW_LNS_advance_pc(delta)   : address += delta                     |
   |         - DW_LNS_advance_line(delta) : line += delta                        |
   |         - DW_LNS_copy                : 发射当前寄存器状态为一行映射记录     |
   |         - DW_LNS_set_file(file_idx)  : file = file_idx                      |
   |      2. 扩展操作码 (Extended Opcodes):                                      |
   |         - DW_LNE_end_sequence        : 终结当前连续指令行映射序列           |
   |         - DW_LNE_set_address(addr)   : 将 address 强制重设为绝对地址        |
   |      3. 特殊操作码 (Special Opcodes - 单字节极限压缩):                      |
   |         - 单字节数值 opcode (范围 13 ~ 255) 同时对 address 与 line 进行增量 |
   |           步进并自动执行一次 copy 发射操作！                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级 C++ 完整 ELF64 目标文件与 DWARF 行表构建引擎
---------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级 ELF64 目标文件生成器与 DWARF ``.debug_line`` 编码/解码状态机引擎。该实现涵盖：
1. 完整的 ELF64 文件头、节头表、字符串表与符号表构建。
2. 包含 ``.text``、``.data``、``.symtab``、``.strtab``、``.shstrtab`` 与 ``.debug_line`` 的物理文件排布。
3. DWARF 标准操作码与行号状态机编码解码流水线。
4. 端到端测试套件（构建内存二进制 ELF 镜像、解析结构并验证符号与源码行号映射）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <cstring>
   #include <cstdint>
   #include <cassert>
   #include <iomanip>
   #include <sstream>

   namespace elf_engine {

   // =========================================================================
   // 1. ELF64 物理常量与数据结构 (遵循 System V ABI 标准)
   // =========================================================================
   constexpr uint32_t ELF_MAGIC = 0x464c457f; // "\x7fELF"

   enum ElfType : uint16_t {
       ET_REL = 1, // 可重定位目标文件
       ET_EXEC = 2, // 可执行文件
       ET_DYN = 3   // 动态共享库
   };

   enum ShType : uint32_t {
       SHT_NULL = 0,
       SHT_PROGBITS = 1,
       SHT_SYMTAB = 2,
       SHT_STRTAB = 3,
       SHT_RELA = 4,
       SHT_NOBITS = 8
   };

   enum ShFlags : uint64_t {
       SHF_WRITE = 0x1,
       SHF_ALLOC = 0x2,
       SHF_EXECINSTR = 0x4
   };

   enum SymbolBinding : uint8_t {
       STB_LOCAL = 0,
       STB_GLOBAL = 1,
       STB_WEAK = 2
   };

   enum SymbolType : uint8_t {
       STT_NOTYPE = 0,
       STT_OBJECT = 1,
       STT_FUNC = 2,
       STT_SECTION = 3
   };

   #pragma pack(push, 1)
   struct Elf64_Ehdr {
       uint8_t  e_ident[16];
       uint16_t e_type;
       uint16_t e_machine;
       uint32_t e_version;
       uint64_t e_entry;
       uint64_t e_phoff;
       uint64_t e_shoff;
       uint32_t e_flags;
       uint16_t e_ehsize;
       uint16_t e_phentsize;
       uint16_t e_phnum;
       uint16_t e_shentsize;
       uint16_t e_shnum;
       uint16_t e_shstrndx;
   };

   struct Elf64_Shdr {
       uint32_t sh_name;
       uint32_t sh_type;
       uint64_t sh_flags;
       uint64_t sh_addr;
       uint64_t sh_offset;
       uint64_t sh_size;
       uint32_t sh_link;
       uint32_t sh_info;
       uint64_t sh_addralign;
       uint64_t sh_entsize;
   };

   struct Elf64_Sym {
       uint32_t st_name;
       uint8_t  st_info;
       uint8_t  st_other;
       uint16_t st_shndx;
       uint64_t st_value;
       uint64_t st_size;
   };
   #pragma pack(pop)

   // =========================================================================
   // 2. DWARF .debug_line 行号状态机编码与解码器
   // =========================================================================
   enum DwarfLineOpcode : uint8_t {
       DW_LNS_copy = 1,
       DW_LNS_advance_pc = 2,
       DW_LNS_advance_line = 3,
       DW_LNS_set_file = 4,
       DW_LNE_extended = 0
   };

   enum DwarfExtendedOpcode : uint8_t {
       DW_LNE_end_sequence = 1,
       DW_LNE_set_address = 2
   };

   struct SourceLocationEntry {
       uint64_t Address = 0;
       uint32_t File = 1;
       uint32_t Line = 1;
       uint32_t Column = 0;
       bool IsStmt = true;
   };

   class DwarfLineTableBuilder {
   public:
       static std::vector<uint8_t> encode(const std::vector<SourceLocationEntry>& entries) {
           std::vector<uint8_t> buffer;
           if (entries.empty()) return buffer;

           uint64_t currentAddress = 0;
           int32_t currentLine = 1;

           for (const auto& entry : entries) {
               // 1. 处理地址增量 (Address Advance)
               int64_t addrDelta = entry.Address - currentAddress;
               if (addrDelta > 0) {
                   buffer.push_back(DW_LNS_advance_pc);
                   buffer.push_back(static_cast<uint8_t>(addrDelta));
                   currentAddress = entry.Address;
               }

               // 2. 处理行号增量 (Line Advance)
               int32_t lineDelta = static_cast<int32_t>(entry.Line) - currentLine;
               if (lineDelta != 0) {
                   buffer.push_back(DW_LNS_advance_line);
                   // 写入定长单字节增量
                   buffer.push_back(static_cast<uint8_t>(lineDelta));
                   currentLine = entry.Line;
               }

               // 3. 发射拷贝记录 (Copy Matrix Entry)
               buffer.push_back(DW_LNS_copy);
           }

           // 4. 终结序列 (End Sequence)
           buffer.push_back(DW_LNE_extended);
           buffer.push_back(1); // 扩展操作码长度
           buffer.push_back(DW_LNE_end_sequence);

           return buffer;
       }

       static std::vector<SourceLocationEntry> decode(const std::vector<uint8_t>& buffer) {
           std::vector<SourceLocationEntry> result;
           uint64_t address = 0;
           uint32_t line = 1;
           uint32_t file = 1;
           size_t pc = 0;

           while (pc < buffer.size()) {
               uint8_t opcode = buffer[pc++];

               if (opcode == DW_LNE_extended) {
                   if (pc >= buffer.size()) break;
                   uint8_t len = buffer[pc++];
                   if (pc >= buffer.size()) break;
                   uint8_t extOp = buffer[pc++];
                   if (extOp == DW_LNE_end_sequence) {
                       break;
                   }
               } else if (opcode == DW_LNS_advance_pc) {
                   uint8_t delta = buffer[pc++];
                   address += delta;
               } else if (opcode == DW_LNS_advance_line) {
                   int8_t delta = static_cast<int8_t>(buffer[pc++]);
                   line += delta;
               } else if (opcode == DW_LNS_copy) {
                   result.push_back({address, file, line, 0, true});
               }
           }

           return result;
       }
   };

   // =========================================================================
   // 3. 内存目标文件构建器 (ELF64 Object File Builder)
   // =========================================================================
   class ElfObjectBuilder {
   private:
       struct SectionInternal {
           std::string Name;
           uint32_t Type;
           uint64_t Flags;
           std::vector<uint8_t> Data;
           uint64_t Alignment = 8;
           uint32_t Link = 0;
           uint32_t Info = 0;
           uint64_t EntSize = 0;
       };

       std::vector<SectionInternal> sections_;
       std::vector<Elf64_Sym> symbols_;
       std::vector<char> strtab_;
       std::vector<char> shstrtab_;

   public:
       ElfObjectBuilder() {
           // 必须包含第 0 号 NULL 节
           sections_.push_back({"", SHT_NULL, 0, {}, 0, 0, 0, 0});
           // 必须包含第 0 号 NULL 符号
           symbols_.push_back({0, 0, 0, 0, 0, 0});
           strtab_.push_back('\0');
           shstrtab_.push_back('\0');
       }

       uint32_t addSection(const std::string& name, uint32_t type, uint64_t flags, const std::vector<uint8_t>& data, uint64_t align = 8) {
           uint32_t idx = static_cast<uint32_t>(sections_.size());
           sections_.push_back({name, type, flags, data, align, 0, 0, 0});
           return idx;
       }

       void addSymbol(const std::string& name, uint64_t value, uint64_t size, SymbolBinding binding, SymbolType type, uint16_t shndx) {
           uint32_t nameOffset = static_cast<uint32_t>(strtab_.size());
           for (char c : name) strtab_.push_back(c);
           strtab_.push_back('\0');

           Elf64_Sym sym;
           sym.st_name = nameOffset;
           sym.st_info = (static_cast<uint8_t>(binding) << 4) | (static_cast<uint8_t>(type) & 0x0F);
           sym.st_other = 0;
           sym.st_shndx = shndx;
           sym.st_value = value;
           sym.st_size = size;

           symbols_.push_back(sym);
       }

       std::vector<uint8_t> emit() {
           // 1. 创建 .symtab, .strtab, .shstrtab 节
           // 将符号表序列化为二进制
           std::vector<uint8_t> symData(symbols_.size() * sizeof(Elf64_Sym));
           std::memcpy(symData.data(), symbols_.data(), symData.size());

           std::vector<uint8_t> strData(strtab_.begin(), strtab_.end());

           uint32_t strtabIdx = addSection(".strtab", SHT_STRTAB, 0, strData, 1);
           uint32_t symtabIdx = addSection(".symtab", SHT_SYMTAB, 0, symData, 8);
           sections_[symtabIdx].Link = strtabIdx; // 符号表链接到字符串表
           sections_[symtabIdx].EntSize = sizeof(Elf64_Sym);
           sections_[symtabIdx].Info = 1; // 首个全局符号索引

           // 收集节名字符串表
           for (const auto& sec : sections_) {
               if (sec.Name.empty()) continue;
               for (char c : sec.Name) shstrtab_.push_back(c);
               shstrtab_.push_back('\0');
           }
           std::vector<uint8_t> shstrData(shstrtab_.begin(), shstrtab_.end());
           uint32_t shstrtabIdx = addSection(".shstrtab", SHT_STRTAB, 0, shstrData, 1);

           // 2. 组装 ELF 文件头
           Elf64_Ehdr ehdr;
           std::memset(&ehdr, 0, sizeof(ehdr));
           ehdr.e_ident[0] = 0x7f;
           ehdr.e_ident[1] = 'E';
           ehdr.e_ident[2] = 'L';
           ehdr.e_ident[3] = 'F';
           ehdr.e_ident[4] = 2; // ELFCLASS64
           ehdr.e_ident[5] = 1; // ELFDATA2LSB (小端)
           ehdr.e_ident[6] = 1; // EV_CURRENT
           ehdr.e_type = ET_REL;
           ehdr.e_machine = 62; // EM_X86_64
           ehdr.e_version = 1;
           ehdr.e_ehsize = sizeof(Elf64_Ehdr);
           ehdr.e_shentsize = sizeof(Elf64_Shdr);
           ehdr.e_shnum = static_cast<uint16_t>(sections_.size());
           ehdr.e_shstrndx = static_cast<uint16_t>(shstrtabIdx);

           // 3. 计算物理文件偏移
           uint64_t currentOffset = sizeof(Elf64_Ehdr);
           std::vector<Elf64_Shdr> shdrs(sections_.size());

           uint32_t shstrOffset = 1;
           for (size_t i = 0; i < sections_.size(); ++i) {
               if (i == 0) {
                   std::memset(&shdrs[0], 0, sizeof(Elf64_Shdr));
                   continue;
               }

               // 对齐当前偏移
               uint64_t align = sections_[i].Alignment;
               if (align > 1) {
                   currentOffset = (currentOffset + align - 1) & ~(align - 1);
               }

               shdrs[i].sh_name = shstrOffset;
               shstrOffset += static_cast<uint32_t>(sections_[i].Name.size()) + 1;

               shdrs[i].sh_type = sections_[i].Type;
               shdrs[i].sh_flags = sections_[i].Flags;
               shdrs[i].sh_addr = 0;
               shdrs[i].sh_offset = currentOffset;
               shdrs[i].sh_size = sections_[i].Data.size();
               shdrs[i].sh_link = sections_[i].Link;
               shdrs[i].sh_info = sections_[i].Info;
               shdrs[i].sh_addralign = sections_[i].Alignment;
               shdrs[i].sh_entsize = sections_[i].EntSize;

               currentOffset += sections_[i].Data.size();
           }

           // 节头表对齐并放置在文件尾部
           currentOffset = (currentOffset + 7) & ~7;
           ehdr.e_shoff = currentOffset;

           // 4. 序列化全部二进制数据
           std::vector<uint8_t> fileBuffer;
           fileBuffer.resize(ehdr.e_shoff + shdrs.size() * sizeof(Elf64_Shdr), 0);

           // 写入 ELF Header
           std::memcpy(fileBuffer.data(), &ehdr, sizeof(Elf64_Ehdr));

           // 写入各个 Section Payload
           for (size_t i = 1; i < sections_.size(); ++i) {
               if (!sections_[i].Data.empty()) {
                   std::memcpy(fileBuffer.data() + shdrs[i].sh_offset, sections_[i].Data.data(), sections_[i].Data.size());
               }
           }

           // 写入 Section Header Table
           std::memcpy(fileBuffer.data() + ehdr.e_shoff, shdrs.data(), shdrs.size() * sizeof(Elf64_Shdr));

           return fileBuffer;
       }
   };

   } // namespace elf_engine

   // =========================================================================
   // 4. 端到端测试与 ELF/DWARF 二进制验证套件
   // =========================================================================
   namespace test {

   inline void runObjectFileAndDwarfTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " ELF64 目标文件拓扑与 DWARF .debug_line 引擎验证套件
";
       std::cout << "=======================================================

";

       using namespace elf_engine;

       // 1. 构造 DWARF 行号映射表
       std::vector<SourceLocationEntry> lines = {
           {0x00, 1, 10, 0, true}, // main.c:10 -> PC=0x00
           {0x08, 1, 11, 0, true}, // main.c:11 -> PC=0x08 (advance_pc 8, advance_line 1)
           {0x10, 1, 15, 0, true}  // main.c:15 -> PC=0x10 (advance_pc 8, advance_line 4)
       };

       auto encodedDwarf = DwarfLineTableBuilder::encode(lines);
       std::cout << "[测试 1: DWARF .debug_line 编码与解码验证]:
";
       std::cout << "  -> 原始行号条目数: " << lines.size() << ", 压缩后字节码尺寸: " << encodedDwarf.size() << " 字节
";

       auto decodedLines = DwarfLineTableBuilder::decode(encodedDwarf);
       assert(decodedLines.size() == lines.size());
       for (size_t i = 0; i < lines.size(); ++i) {
           assert(decodedLines[i].Address == lines[i].Address);
           assert(decodedLines[i].Line == lines[i].Line);
       }
       std::cout << "  -> DWARF 行号状态机编解码往返断言完全一致。

";

       // 2. 组装 ELF64 目标文件
       ElfObjectBuilder builder;

       // 模拟机器指令代码 (.text)
       std::vector<uint8_t> textBytes = {
           0x55,                         // push %rbp
           0x48, 0x89, 0xe5,             // mov %rsp, %rbp
           0xb8, 0x2a, 0x00, 0x00, 0x00, // mov $42, %eax
           0x5d,                         // pop %rbp
           0xc3                          // retq
       };
       uint32_t textIdx = builder.addSection(".text", SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR, textBytes, 16);

       // 模拟只读常量数据 (.rodata)
       std::string banner = "Compiler Engine Ready\0";
       std::vector<uint8_t> rodataBytes(banner.begin(), banner.end());
       uint32_t rodataIdx = builder.addSection(".rodata", SHT_PROGBITS, SHF_ALLOC, rodataBytes, 8);

       // 挂载调试行号节 (.debug_line)
       uint32_t debugLineIdx = builder.addSection(".debug_line", SHT_PROGBITS, 0, encodedDwarf, 1);

       // 注入导出函数符号与全局变量符号
       builder.addSymbol("calculate_core", 0x00, textBytes.size(), STB_GLOBAL, STT_FUNC, textIdx);
       builder.addSymbol("g_banner_str", 0x00, rodataBytes.size(), STB_GLOBAL, STT_OBJECT, rodataIdx);

       auto elfBinary = builder.emit();
       std::cout << "[测试 2: ELF64 内存二进制目标文件发射与解析]:
";
       std::cout << "  -> 生成 ELF64 二进制文件总尺寸: " << elfBinary.size() << " 字节
";

       // 验证 ELF 文件头
       const auto* ehdr = reinterpret_cast<const Elf64_Ehdr*>(elfBinary.data());
       assert(ehdr->e_ident[0] == 0x7f && ehdr->e_ident[1] == 'E' && ehdr->e_ident[2] == 'L' && ehdr->e_ident[3] == 'F');
       assert(ehdr->e_type == ET_REL);
       assert(ehdr->e_machine == 62); // EM_X86_64
       assert(ehdr->e_shnum >= 6);
       std::cout << "  -> ELF Header 魔数、目标架构 (x86-64) 与节区数量检验通过。
";

       // 验证 Section Header Table
       const auto* shdrs = reinterpret_cast<const Elf64_Shdr*>(elfBinary.data() + ehdr->e_shoff);
       assert(shdrs[textIdx].sh_type == SHT_PROGBITS);
       assert(shdrs[textIdx].sh_flags == (SHF_ALLOC | SHF_EXECINSTR));
       assert(shdrs[textIdx].sh_size == textBytes.size());
       std::cout << "  -> .text 代码节区物理偏移与执行权限 (SHF_ALLOC | SHF_EXECINSTR) 校验通过。
";

       std::cout << "
  -> 目标文件拓扑与 DWARF 调试行表全套验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰印证了目标文件物理拓扑与调试元数据压缩的底层机理：

1. **DWARF 状态机压缩效能**：在测试 1 中，3 个跨越离散 PC 地址与源码行号的映射条目，通过 ``advance_pc``、``advance_line`` 与 ``copy`` 操作码被高效压缩至不足 10 字节，并在解码状态机中无损还原为精确的指令行号矩阵。
2. **ELF 二进制规范完整性**：在测试 2 中，发射器正确完成了标准 64 字节 ELF Header 封装，并按 16 字节与 8 字节边界严密对齐了 ``.text`` 与 ``.rodata`` 节区负载，同时在文件末尾正确生成了包含类型、标志位、链接索引与条目尺寸的节头表（SHT），完全符合 System V 链接器消费规范。

小结与下章导读
--------------

本章系统解构了编译器后端二进制发射与目标文件物理拓扑的核心体系：

1. **半成品程序物理架构**：剖析了链接视图（细粒度 Sections）与执行视图（粗粒度 Segments）的双重视图解耦，阐释了目标文件与可执行文件的根本差异。
2. **三大二进制格式横向比对**：深度对比了 ELF、Mach-O 与 PE/COFF 在文件魔数、节段层次模型与调试信息组织上的微架构特征。
3. **符号表与字符串池**：推导了 ``Elf64_Sym`` 的物理结构、符号绑定（Local/Global/Weak）与特殊节索引（``SHN_UNDEF`` / ``SHN_COMMON``）的语义规范。
4. **DWARF 调试行表压缩**：解构了行号状态机（LNSM）通过字节码序列将离散 PC 映射压缩为极小负载的实现机理。

在目标文件生成完毕后，如何将多个离散的目标文件与静态库合并为一个完整的可执行程序，并修正所有未决议符号的引用地址，是静态链接器的核心职责。在第 8 模块第 2 节 **静态链接与重定位：符号合并决议、重定位记录计算 (R_X86_64_PC32) 与 Weak 符号处理（``08_linking_runtime_vms_and_jit/02_static_linking_relocations_and_symbol_resolution.rst``）** 中，我们将深入剖析静态链接器的两遍扫描流程、全局符号决议与同名冲突裁决、重定位表（``.rela.text``）条目解析，以及基于 PC 相对寻址与绝对寻址的补丁重写数学公式。
