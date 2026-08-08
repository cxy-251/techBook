第074章：ELF, Mach-O, COFF, and Platform Formats
=================================================

核心知识点
----------

* Object/executable format 是平台工具链的持久化二进制契约。它连接 compiler、assembler、linker、loader、debugger、profiler 和签名/安全工具。
* 不同格式字段和命名差异很大，但都必须回答同一组问题：文件是什么、面向什么架构、代码和数据在哪里、符号如何表示、哪些地址待修正、如何加载、调试信息在哪里。
* ELF 常见于 Linux/Unix-like 平台，核心结构包括 ELF header、section headers、program headers、symbols、relocations 和 dynamic metadata。
* ELF 的 section view 主要服务链接，program-header/segment view 主要服务加载。分析 ``.o`` 时常看 section/symbol/relocation；分析进程映像时常看 ``PT_LOAD``、``PT_DYNAMIC`` 等 program headers。
* Mach-O 是 Apple 平台核心格式，中心结构是 Mach header + load commands，再指向 segments、sections、symbols、relocations、dyld metadata 和 code-signing 信息。
* Mach-O 的 load command 是理解 Apple 二进制的关键入口：它描述 segment 映射、动态库依赖、入口、符号/动态链接数据、平台版本和签名等运行时信息。
* Apple universal/fat binary 可以在一个外层容器中保存多个架构 slice；真正执行时 loader 选择当前平台可用的 Mach-O slice。
* COFF 主要承担 Windows 可重定位 object 的链接表示，PE 则在其基础上形成 Windows executable/DLL 的可加载映像。
* PE 的 DOS stub/header、PE signature、COFF header、optional header、section table 和 data directories 共同描述架构、入口、映像布局、imports/exports、relocations、resources 和异常等信息。
* Windows 的 import/export tables 和 base relocation directory 承担部分 ELF dynamic symbols/relocations、Mach-O dyld binding 信息相似的职责，但结构和绑定协议不能混用解释。
* 三类格式都会把 code/data 分区、symbol identity、relocation rules 和 loader metadata 写入文件；差异主要来自平台 ABI、动态链接模型、安全机制和历史设计。
* Debug format 也与平台生态有关。Unix/Apple 工具链常大量使用 DWARF；Windows 原生工具链常使用 CodeView/PDB。Object format 与 debug format 是相关但不同的协议层。
* Binary format 是 ABI 的磁盘表达之一：machine type、alignment、relocation type、symbol visibility、unwind、TLS、dynamic-library metadata 等都把平台二进制规则固化到文件中。
* 文件扩展名不能替代 header 事实。判断未知二进制时应先读 magic/header，再确认 architecture/file type，避免用错误平台工具和字段模型分析。
* 格式不匹配、architecture mismatch、unsupported relocation、缺失 load metadata 或错误 import/export 信息，都会在 link/load 阶段形成明确失败，而不是源语言级错误。

关键路径
--------

通用二进制检查：

::

   binary file
   → read magic / file header
   → identify format + architecture + file type
   → inspect sections / segments / load commands
   → inspect symbols / imports / exports
   → inspect relocations / binding metadata
   → inspect loader + debug/unwind metadata
   → reconstruct toolchain state

ELF：

::

   ELF header
   → section headers for linking view
   → symbols + relocations
   → program headers for loading view
   → dynamic section / shared-object metadata
   → loader maps PT_LOAD segments

Mach-O / PE：

::

   platform header
   → Mach-O load commands or PE optional-header/data-directories
   → segment/section layout
   → dynamic-library or import/export metadata
   → relocation/binding information
   → platform loader constructs image

概念辨析
--------

* **Object format 与 ISA**：ISA 规定机器指令；object format 规定这些指令、数据和元数据如何存放并交给工具链处理。
* **Section 与 segment/load command**：section 更偏内容组织和链接，segment/load description 更偏运行时映射；不同格式表达方式不同。
* **COFF 与 PE**：COFF 常指 Windows object/linking 基础结构，PE 是最终 executable/DLL 的可加载格式体系。
* **Mach-O 与 universal binary**：Mach-O 是单个架构 slice 的格式；fat/universal container 可以包住多个 Mach-O slices。
* **Object format 与 debug format**：ELF/Mach-O/PE 描述二进制容器，DWARF/CodeView 等描述源码级调试关系，二者可以组合但不是同一协议。

本章结论
--------

ELF、Mach-O、COFF/PE 是同一个编译器问题的不同平台答案：怎样把机器级程序、符号、重定位、加载和调试契约写入文件。稳定分析方法不是背 section 名，而是沿 ``Header → Content Layout → Symbols/Relocations → Load Metadata → Runtime Image`` 追踪；格式差异最终都服务于各自平台 ABI 和 loader 规则。