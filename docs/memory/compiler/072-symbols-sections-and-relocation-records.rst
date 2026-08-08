第072章：Symbols, Sections, and Relocation Records
==================================================

核心知识点
----------

* Section 是 object file 中按用途组织内容的区域；symbol 是对代码或数据位置的命名记录；relocation record 是对“地址稍后再修正”的显式描述。
* 三者共同构成 separate compilation 的连接协议：section 提供内容位置，symbol 提供名字与定义关系，relocation 提供跨地址空间修正规则。
* ``.text`` 常保存机器指令，``.data`` 保存已初始化可写数据，``.bss`` 表示零初始化空间，``.rodata`` 保存只读常量，``.debug_*`` 保存调试元数据。
* Symbol table 中常见事实包括 name、type、binding、size、所在 section/特殊状态以及 value。对 relocatable object 而言，symbol value 通常首先解释为 section-relative offset，而不是最终虚拟地址。
* Local symbol 主要在当前 object 内部参与定位；global symbol 可以参与跨文件解析；weak symbol 允许更弱的定义优先级；undefined symbol 表示当前文件只有引用需求。
* Common symbol 是某些传统 object/语言工具链中的未分配全局存储声明形式，最终如何合并和分配由链接规则决定；现代编译选项也可能直接把此类对象放入 BSS/普通定义。
* Symbol type 和 binding 影响 linker 的解析规则。函数、对象、section、TLS 等实体可能采用不同类型，不能只按名字字符串判断其语义。
* Relocation record 至少需要描述：待修改位置、关联 symbol、relocation type，以及格式允许时的 addend。
* Relocation type 是目标架构和 ABI 规则的一部分。它决定 linker 是写绝对地址、PC-relative displacement、GOT/PLT reference、TLS offset，还是其它机器相关值。
* 典型 PC-relative relocation 可抽象成 ``S + A - P``：``S`` 是 symbol 最终地址，``A`` 是 addend，``P`` 是 relocation place。具体公式必须以目标 ABI 的 relocation type 为准。
* 编译器可以知道“这里引用哪个 symbol”，却不知道最终 ``S``；因此先生成占位编码并留下 relocation，linker 在全局布局确定后再完成计算。
* 对当前 object 内部的 symbol 也可能需要 relocation，因为 section 最终地址、合并顺序和位置无关代码策略仍未确定。
* Linker 的 symbol resolution 和 relocation 是两个相连但不同的动作：先决定一个引用绑定到哪个定义，再根据最终布局修正使用该定义的机器字段。
* Symbol visibility、weak/strong 规则、archive member extraction、COMDAT/linkonce 等机制都可能影响“哪个定义最终胜出”；relocation 只能在绑定关系确定后正确落值。
* Relocation error 往往不是“地址没找到”这么简单。溢出、字段位宽不足、错误 relocation type、架构不匹配都可能导致 linker 无法编码最终值。

关键路径
--------

符号解析：

::

   object files / libraries
   → read symbol tables
   → collect definitions and undefined references
   → apply local/global/weak/visibility rules
   → choose definition for each reference
   → produce resolved symbol graph

重定位：

::

   relocation entry
   → locate patch site in section
   → resolve referenced symbol
   → obtain final symbol address S
   → apply target relocation formula/type
   → range/encoding check
   → write patched machine field

独立编译到统一地址空间：

::

   per-file sections + symbols
   → linker merges compatible sections
   → assign output addresses
   → resolve cross-file names
   → apply relocations
   → emit one coherent program image

概念辨析
--------

* **Symbol 与 address**：symbol 是带 binding/type/section 状态的命名实体，不等于一个已经固定的绝对地址。
* **Section offset 与 virtual address**：可重定位文件中的偏移只在当前 section 语境下有意义，最终地址由链接布局决定。
* **Undefined symbol 与 weak symbol**：undefined 表示当前文件没有定义；weak 表示定义/引用采用较弱绑定规则，二者不是一回事。
* **Symbol resolution 与 relocation**：前者回答“引用绑定谁”，后者回答“绑定后机器字段写什么值”。
* **Relocation 与 runtime patching**：relocation 可以在静态链接时完成，也可以部分保留到 loader/dynamic linker；时机不同，核心都是根据最终地址关系修正字段。

本章结论
--------

Separate compilation 能成立，靠的是 ``Section Content + Symbol Identity + Relocation Rule`` 三件事。Linker 先把名字解析成最终定义，再把 section 布局转换成地址，最后按目标 ABI 的 relocation 类型修正机器字段；因此跨文件链接本质上是把多个局部地址空间闭合成一个统一程序地址关系。