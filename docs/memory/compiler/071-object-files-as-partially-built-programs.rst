第071章：Object Files as Partially Built Programs
=================================================

核心知识点
----------

* Object file 是已经包含机器级代码和数据、但地址关系尚未完全闭合的程序容器。它处在代码生成之后、最终链接和加载之前。
* 一个 ``.o``/``.obj`` 不是“纯机器码”。它通常同时包含 code、data、symbols、relocations、unwind/debug metadata 和平台格式头。
* 编译器在生成 object file 时通常已经完成 instruction selection、register allocation、stack-frame lowering 和机器指令编码；尚未确定的是跨编译单元符号地址、最终 section 布局和部分运行时绑定。
* 未定义外部符号在 relocatable object 中是正常状态。当前文件只需记录“这里需要某个 symbol”，后续 linker 再寻找兼容定义。
* Relocatable object 的核心能力是可组合：每个编译单元只保存自身内容和对外连接点，linker 再把多个局部视图合成全局程序。
* Object file 中常见内容可分为 executable code、writable data、read-only data、zero-initialized storage、symbol tables、relocation records 和 debug/unwind metadata。
* 已初始化全局数据需要实际初始字节；零初始化对象常只记录大小和属性，由 loader 在运行时提供清零内存，从而避免文件中保存大量零字节。
* Symbol table 把名字关联到 section、偏移、大小、binding 和定义状态；relocation table 则描述哪些机器字段需要在地址确定后重新计算。
* Relocatable object、executable 和 shared library 是不同阶段角色。前者主要服务 linker，后两者已经具备 loader 可消费的进程映像信息，并可能保留动态重定位。
* ELF 中常用 ``ET_REL``、``ET_EXEC``、``ET_DYN`` 区分这些角色；其它平台格式字段不同，但“可重定位输入—可加载产物”的阶段边界相同。
* Section 主要是 linking view：按用途组织代码、数据、符号、重定位和调试材料；segment/program-loading description 主要是 loading view：说明哪些文件范围如何映射到内存以及具有什么权限。
* 多个 sections 可以被装入同一个 loadable segment。分析链接关系应优先看 section/symbol/relocation，分析运行时映射和权限应优先看 segment/load description。
* Object file 保留的是后续工具链仍需消费的程序事实，而不是源码原始形状。源码局部变量、表达式和控制结构可以已经消失，只要机器语义和必要元数据仍可继续处理。

关键路径
--------

从源码到可执行文件：

::

   source translation unit
   → frontend / middle-end / backend
   → machine code + data
   → relocatable object
   → symbol resolution + relocation + layout
   → executable / shared library
   → loader maps process image

Object file 内部关系：

::

   machine instructions / data bytes
   → place into sections
   → attach symbols to section-relative locations
   → record unresolved address references as relocations
   → preserve debug/unwind metadata
   → hand container to linker

链接视图与加载视图：

::

   sections / symbols / relocations
   → linker merges and assigns addresses
   → output load descriptions / segments
   → loader maps file ranges with permissions
   → runtime addresses become executable state

概念辨析
--------

* **Object file 与 machine code**：machine code 只是 object file 中的一类内容；object file 还保存名字、修正规则和工具元数据。
* **Undefined symbol 与 compile error**：在 relocatable object 中，外部符号未定义可以完全合法，只要最终链接能找到定义。
* **Section 与 segment**：section 主要服务链接组织，segment 主要服务运行时映射；二者不是同一层概念。
* **Relocatable object 与 executable**：前者仍以“可合并”为核心，后者以“可加载”为核心。
* **File offset 与 runtime address**：object file 中的 section 偏移不是最终进程虚拟地址，必须经过链接和加载布局解释。

本章结论
--------

Object file 是“程序已经机器化，但地址关系尚未完全闭合”的中间产物。稳定理解路径是 ``Machine Code/Data → Sections → Symbols/Relocations → Link Layout → Loadable Segments``；只有同时看到内容、名字、待修正地址和加载描述，才能判断一个二进制文件当前处在编译、链接还是加载阶段。