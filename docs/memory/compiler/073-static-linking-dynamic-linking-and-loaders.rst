第073章：Static Linking, Dynamic Linking, and Loaders
=====================================================

核心知识点
----------

* Linking 决定多个 object files、libraries 和符号引用最终组合成什么程序；loader 则把最终二进制映射成真实进程地址空间。
* Static linking 在程序运行前解析大部分符号、抽取所需 archive members、合并 sections、应用 relocations，并把选中的库代码直接纳入最终产物。
* 静态库本质上是 relocatable objects 的归档集合。Linker 通常根据当前 unresolved symbols 按需抽取成员，而不是机械复制整个 archive。
* Dynamic linking 把一部分符号绑定推迟到加载时或运行时。最终 executable 记录 shared-library dependencies、dynamic symbols、dynamic relocations 和搜索/绑定元数据。
* ``DT_NEEDED`` 一类动态依赖记录表达“运行时还需要哪些 shared objects”；真正装载到哪一份库，由当前平台的 loader/dynamic linker 搜索规则决定。
* Loader 的基础职责是读取可加载描述，映射 code/data segments，设置内存权限，建立初始进程映像，并把控制权交给程序入口或动态链接器。
* ELF 动态程序常通过 ``PT_INTERP`` 指定用户态动态链接器。内核先创建基础映像，再由动态链接器加载依赖、完成动态 relocation 和初始化。
* PIC/PIE 的核心是减少代码对固定绝对地址的依赖，使同一份代码可以被映射到不同虚拟地址，适应 shared libraries 和 ASLR。
* GOT（Global Offset Table）提供可在运行时修正的数据/地址间接槽；PLT（Procedure Linkage Table）常为外部函数调用提供稳定跳板。具体结构和名称依平台格式而异。
* Lazy binding 把某些函数符号解析推迟到第一次调用；eager binding 则在启动阶段完成。前者降低部分启动成本，后者让解析更早、运行时路径更确定。
* Symbol interposition/visibility 会影响动态符号最终绑定到哪个定义。编译器和 linker 只有在符号不可被替换或已知绑定时，才能做更激进的直接调用、内联或去间接化。
* 动态链接的优势是共享代码、独立更新、插件化和按需加载；代价是部署环境、版本、搜索路径、ABI 和启动重定位都成为运行时依赖。
* 静态链接并不等于完全没有运行时平台依赖；系统调用、kernel ABI、运行时初始化和某些 libc 行为仍属于执行环境的一部分。
* 动态加载失败应区分“文件找不到”“符号找不到”“版本/ABI 不兼容”“relocation 失败”和“权限/格式错误”，不能都归为同一种 linker 问题。
* 最终程序身份由 link graph 和 load graph 共同决定：源码声明只是候选关系，真正执行的是 linker 选择并由 loader 映射进进程的那份代码。

关键路径
--------

静态链接：

::

   relocatable objects + static archives
   → collect unresolved symbols
   → extract needed archive members
   → resolve definitions
   → merge/layout sections
   → apply static relocations
   → emit executable/shared output

动态加载：

::

   executable dynamic metadata
   → loader maps main image
   → dynamic linker finds shared libraries
   → map dependent objects
   → resolve dynamic symbols
   → apply GOT/PLT/data relocations
   → run initializers
   → enter program

外部函数调用：

::

   call external symbol
   → static direct binding if resolved early
   → otherwise PLT/GOT or platform equivalent
   → lazy/eager runtime resolution
   → cache resolved target
   → subsequent calls reach actual function

概念辨析
--------

* **Static library 与 shared library**：前者主要提供可被 linker 抽取的 object members；后者是可被 loader/dynamic linker 映射和绑定的独立二进制对象。
* **Linker 与 loader**：linker 构造二进制地址关系，loader 把该关系落实到进程内存；动态链接器处在二者边界之间继续完成运行时绑定。
* **PIC 与 dynamic linking**：PIC 便于共享和随机地址映射，但动态链接还包括符号搜索、relocation、版本和初始化等更多机制。
* **PLT 与 GOT**：PLT 更常作为函数调用跳板，GOT 更常保存可修正地址槽；它们是某些平台的具体实现，不是所有 object formats 的统一命名。
* **Lazy binding 与 unresolved symbol**：lazy binding 是有意延迟合法解析；真正无法找到满足规则的定义则是运行时链接错误。

本章结论
--------

链接和加载共同决定“程序最终由哪些代码组成、这些代码位于哪里”。稳定路径是 ``Objects/Libraries → Symbol Resolution → Relocation/Layout → Executable/Shared Objects → Loader → Dynamic Binding → Process Image``；静态与动态的区别主要在于绑定发生得多早，而正确性始终依赖同一套符号、地址和 ABI 契约。