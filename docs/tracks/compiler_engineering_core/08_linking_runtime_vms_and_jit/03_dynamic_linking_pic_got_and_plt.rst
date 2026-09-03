====================================================================================================
动态链接与位置无关代码 (PIC)：Global Offset Table (GOT)、Procedure Linkage Table (PLT) 延迟绑定
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 8 模块第 2 节（``08_linking_runtime_vms_and_jit/02_static_linking_relocations_and_symbol_resolution``）中，我们深入剖析了静态链接器的两遍扫描流水线、符号三集合裁决状态机、强弱符号冲突处理、C++ COMDAT 重复节折叠，以及基于 $S$、$A$、$P$ 三元组的绝对寻址（``R_X86_64_64``）与 PC 相对寻址（``R_X86_64_PC32``）补丁计算。静态链接将所有输入目标文件合并为单一自包含镜像，代码段中的地址在构建期被永久固定。当多个进程同时加载相同的共享库时，静态链接会导致物理内存中存在大量重复代码副本，且无法兼容现代操作系统的地址空间布局随机化（ASLR）。本章深入剖析 **动态链接（Dynamic Linking）** 与 **位置无关代码（Position-Independent Code, PIC）** 的底层物理机制，解构代码段只读共享约束、全局偏移表（Global Offset Table, GOT）数据间接寻址、过程链接表（Procedure Linkage Table, PLT）延迟绑定状态机以及 RELRO 安全加固模型。

共享库内存拓扑与位置无关代码 (PIC) 的物理诉求
---------------------------------------------

现代操作系统（Linux / macOS / Windows）通过虚拟内存管理为每个进程提供独立的地址空间。在多任务并发环境下，动态链接核心解决两大系统级物理约束：

1. **物理内存去重（Physical Page Deduplication）**：多个独立进程同时调用 C 标准库（``libc.so``）时，操作系统的虚拟内存管理器将不同进程的虚拟页映射到同一组物理内存代码页上，页属性标记为 ``PROT_READ | PROT_EXEC``。
2. **地址空间布局随机化（ASLR）防御**：为了抵御缓冲区溢出攻击，内核在每次启动进程或装载共享对象（Shared Object, ``.so`` / ``.dylib`` / ``.dll``）时，随机分配虚拟基址（Load Base Address）。

代码段只读性与运行时重定位的冲突
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若共享库在编译时生成包含绝对虚拟地址引用的机器码，动态加载器（Dynamic Loader, ``ld.so``）在将共享库装载至随机基址后，必须通过就地修改机器指令（Text Relocation）来修正跳转目标与数据地址。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                代码段就地重定位 (Text Relocation) 的物理破坏分析            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 进程 A 地址空间 (Base: 0x7FFF0000) ]     [ 进程 B 地址空间 (Base: 0x55550000) ] |
   |                  |                                          |               |
   |                  v                                          v               |
   |         +------------------+                       +------------------+     |
   |         | call 0x7FFF1234  |                       | call 0x55551234  |     |
   |         +------------------+                       +------------------+     |
   |                  |                                          |               |
   |                  +--------------------+ +-------------------+               |
   |                                       | |                                   |
   |                                       v v                                   |
   |                            +-----------------------+                        |
   |                            | 物理内存共享代码页    |                        |
   |                            | (PROT_READ|PROT_EXEC) |                        |
   |                            +-----------------------+                        |
   |                                       |                                     |
   |   [ 写入冲突与写时复制 (COW) 爆发 ]  |                                     |
   |   1. 动态链接器试图覆写只读代码页以修补地址 -> 触发段错误 (SIGSEGV)         |
   |   2. 若赋予写权限修补 -> 触发内核写时复制 (Copy-On-Write)                   |
   |   3. 每个进程被迫私有化一份修改后的代码页 -> 物理内存共享优势彻底丧失       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

为了消除代码段修改，编译器必须遵循 **代码与数据分离（Separation of Code and Data）** 原则：将所有在运行时可能发生变化的地址指针集中存放在专属的数据段中，而执行代码段严格保持恒定不变。

-fPIC 编译开关的底层生成约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当编译器接收到 ``-fPIC``（Position-Independent Code）选项时，后端指令生成器激活一套特定的寻址规则：

1. **模块内跳转与局部数据寻址**：强制使用指令指针相对寻址（PC-Relative Addressing）。在 x86-64 架构下，使用 ``%rip`` 相对寻址指令（如 ``leaq offset(%rip), %rax``）；在 ARM64 架构下，使用 ``ADRP`` 页面基址定位加 ``ADD`` 页内偏移指令。无论模块被加载至何种绝对虚拟基址，代码段内部各指令与常量数据之间的相对距离保持恒定。
2. **跨模块全局变量访问**：代码段不得直接嵌入目标变量的绝对地址或固定的相对偏移。代码首先通过 PC 相对寻址读取位于数据段内的指针表条目，再通过解引用该指针完成数据读写。
3. **跨模块函数调用**：通过过程链接表进行间接跳转，控制流首先命中固定的局部代码桩，再经由数据段中的函数指针跳向目标实体。

全局偏移表 (Global Offset Table, GOT) 架构
------------------------------------------

全局偏移表（GOT）是链接器在共享库或位置无关可执行文件（PIE）的数据段中开辟的连续指针数组。其在 ELF 规范中主要细分为 ``.got`` 与 ``.got.plt`` 两个物理节区。

代码段与 GOT 的相对距离守恒性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ELF 文件的链接拓扑中，代码加载段（Text Segment）与数据加载段（Data Segment）在链接期由链接脚本紧凑排列。当内核的动态加载器将整个共享库映射进进程虚拟地址空间时，操作系统保持各 Segment 之间的相对偏移恒定：

.. math::

   \Delta = 	ext{VAddr}(	ext{.got}) - 	ext{VAddr}(	ext{Instruction}) = 	ext{Constant}

因此，代码段中的任何一条机器指令，均能在编译链接期通过固定的 PC 相对偏移精确定位到属于自己的 GOT 表项。

.. list-table:: GOT 核心节区分工与重定位类型
   :widths: 18 22 28 32
   :header-rows: 1
   :class: tight-table

   * - 节区名称
     - 内存访问权限
     - 存储数据内容
     - 关联重定位类型 (x86-64)
   * - **.got**
     - 可读写（或 RELRO 只读）
     - 全局变量指针、外部数据对象地址
     - ``R_X86_64_GLOB_DAT``, ``R_X86_64_RELATIVE``
   * - **.got.plt**
     - 可读写
     - 外部函数入口地址、动态解析桩指针
     - ``R_X86_64_JUMP_SLOT``
   * - **.data.rel.ro**
     - 只读（装载重定位后封闭）
     - 包含指针的常量结构体、虚表 vtable
     - ``R_X86_64_64``, ``R_X86_64_RELATIVE``

全局数据访问的汇编执行链路
~~~~~~~~~~~~~~~~~~~~~~~~~~

考虑共享库中访问外部全局整型变量 ``extern int g_external_counter;`` 的场景。

非 PIC 模式下的机器码生成（绝对重定位）：

.. code-block:: nasm

   ; 非 PIC 代码：直接使用绝对 32 位/64 位地址
   movl 0x601040, %eax        ; 0x601040 为硬编码地址，依赖 R_X86_64_32 重定位修改代码段
   addl $1, %eax
   movl %eax, 0x601040

PIC 模式下的机器码生成（GOT 间接寻址）：

.. code-block:: nasm

   ; PIC 代码：通过 %rip 相对寻址定位 GOT 表项
   movq g_external_counter@GOTPCREL(%rip), %rax ; 1. 从 .got 读出变量的真实 64 位地址
   movl (%rax), %ecx                            ; 2. 解引用指针读取数值
   addl $1, %ecx                                ; 3. 执行核心计算
   movl %ecx, (%rax)                            ; 4. 写回目标内存

在此指令序列中，``g_external_counter@GOTPCREL(%rip)`` 转化为 ``movq 0x2008ac(%rip), %rax``。动态加载器装载共享库时，仅需将 ``g_external_counter`` 的实际虚拟地址写入 ``.got`` 对应的 8 字节槽位（触发 ``R_X86_64_GLOB_DAT`` 重定位），代码段的字节流全程保持只读，满足多进程物理页完全共享。

过程链接表 (PLT) 与延迟绑定 (Lazy Binding)
------------------------------------------

大型现代程序与复杂运行库包含成千上万个动态导出函数。在常规运行路径中，程序往往仅调用其中极小一部分函数。若在程序启动阶段由动态链接器遍历并解析全部函数符号，将引入显著的进程启动延迟。

**延迟绑定（Lazy Binding）** 将外部函数的符号查找与地址修补推迟到该函数被应用代码 **首次执行** 的时刻完成。

PLT 与 .got.plt 协同拓扑结构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了支持延迟绑定，ELF 引入了过程链接表（``.plt`` 代码节）与函数全局偏移表（``.got.plt`` 数据节）的紧密协作拓扑。

``.got.plt`` 预留头部三元组条目：
- **``GOT[0]``**：存储 ``.dynamic`` 节区的虚拟地址，供动态链接器识别自身运行时元数据。
- **``GOT[1]``**：存储当前模块的标识信息（``link_map`` 结构体指针，内部包含模块依赖链、符号表基址与重定位表入口）。
- **``GOT[2]``**：存储动态链接器运行时解析入口函数（``_dl_runtime_resolve``）的绝对地址。

``.plt`` 代码段结构排布：
- **``PLT0``（公共解析入口桩）**：负责将 ``link_map`` 指针与符号重定位偏移压入栈，随后跳转入 ``_dl_runtime_resolve``。
- **``PLTn``（各函数专属入口桩）**：每个被调用的外部函数（如 ``printf``、``malloc``）对应一个 16 字节的独立 PLT 条目。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  PLT 与 .got.plt 初始拓扑与延迟绑定流转图                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 用户代码段 ]                                                            |
   |   0x401050: call 0x401020 <puts@plt>                                        |
   |                   |                                                         |
   |                   v                                                         |
   |   [ .plt 节区 (只读代码段) ]                                                |
   |   +---------------------------------------------------------------------+   |
   |   | PLT0:                                                               |   |
   |   |   pushq 0x200802(%rip)   ; 将 GOT[1] (link_map) 压栈               |   |
   |   |   jmpq *0x200804(%rip)   ; 间接跳转至 GOT[2] (_dl_runtime_resolve) |   |
   |   +---------------------------------------------------------------------+   |
   |   | puts@plt (PLT1):                                                    |   |
   |   |   jmpq *0x20080a(%rip)   ; [跳转 A] 间接跳向 GOT[3]                 |   |
   |   |   pushq $0x00            ; [回跳 B] 压入 puts 的重定位索引 (RelocID)|   |
   |   |   jmpq 0x401000 <PLT0>   ; [跳转 C] 跳往 PLT0 公共解析入口          |   |
   |   +---------------------------------------------------------------------+   |
   |                   |                       ^                                 |
   |                   | (初始指针回指向)      |                                 |
   |                   v                       |                                 |
   |   [ .got.plt 节区 (可读写数据段) ]        |                                 |
   |   +---------------------------------------+-----------------------------+   |
   |   | GOT[0]: .dynamic 节区虚拟地址                                       |   |
   |   | GOT[1]: 模块 link_map 指针                                          |   |
   |   | GOT[2]: _dl_runtime_resolve 解析器入口地址                          |   |
   |   | GOT[3]: 0x401026 (初始状态严格指向 puts@plt 的第二条指令 pushq!)    |   |
   |   +---------------------------------------------------------------------+   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

首次调用（First Call）状态迁移轨迹
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当程序执行 ``call puts@plt`` 时，硬件时钟周期与寄存器状态按以下确定序流转：

1. **步进 1（进入 PLT 条目）**：CPU 跳入 ``puts@plt``，执行第一条指令 ``jmpq *GOT[3](%rip)``。
2. **步进 2（初始回跳）**：在初始未绑定状态下，静态链接器预先将 ``GOT[3]`` 的数值填为 ``puts@plt + 6``（即 ``pushq $0x00`` 的物理地址）。因此间接跳转立即跳回 ``puts@plt`` 内部的第二条指令。
3. **步进 3（压入符号重定位索引）**：执行 ``pushq $0x00``，将该函数在动态重定位表（``.rela.plt``）中的重定位条目索引（Relocation Index）压入执行栈。
4. **步进 4（转入公共 PLT0）**：执行 ``jmpq PLT0``，进入公共解析代码块。
5. **步进 5（压入模块上下文并进入解析器）**：``PLT0`` 执行 ``pushq GOT[1]`` 将 ``link_map`` 结构指针压栈，随后执行 ``jmpq *GOT[2]`` 跳入动态链接器的核心符号解析函数 ``_dl_runtime_resolve(link_map, reloc_index)``。
6. **步进 6（符号决议与 GOT 回写）**：
   - 动态链接器依据 ``reloc_index`` 提取目标符号字符串 ``"puts"``。
   - 遍历全局依赖库搜索链（Search Scope），在 ``libc.so`` 的动态符号表（``.dynsym``）中检索到 ``puts`` 的真实虚拟地址（如 ``0x7ffff7a84000``）。
   - **将解析所得的绝对真实地址直接覆盖写入 ``GOT[3]`` 内存槽位**。
7. **步进 7（控制流转移）**：动态链接器恢复此前暂存的所有通用寄存器与条件标志位，直接跳转至 ``libc.so`` 中的 ``puts`` 实际入口执行业务逻辑。

二次及后续调用（Subsequent Calls）的零延迟路径
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当程序后续再次执行 ``call puts@plt`` 时：
1. CPU 跳入 ``puts@plt``，执行 ``jmpq *GOT[3](%rip)``。
2. 由于 ``GOT[3]`` 已在首次调用时被固化为 ``0x7ffff7a84000``，CPU 单周期直接跳入 ``libc.so`` 中的 ``puts`` 实体。
3. ``pushq $reloc_index`` 与 ``PLT0`` 解析路径被彻底旁路，调用开销仅增加一次内存指针间接解引用。

动态重定位类型与符号查找流水线
------------------------------

动态链接过程依赖专用重定位记录指引地址修补。在 64 位 ELF 共享库中，核心动态重定位类型如下：

.. list-table:: 典型 ELF 动态重定位类型定义与语义
   :widths: 22 18 30 30
   :header-rows: 1
   :class: tight-table

   * - 重定位类型标识
     - 适用节区
     - 计算公式与行为
     - 触发时机
   * - **R_X86_64_GLOB_DAT**
     - ``.got``
     - $	ext{Value} = S$
     - 模块加载时，立即查询全局符号表并填入变量绝对地址
   * - **R_X86_64_JUMP_SLOT**
     - ``.got.plt``
     - $	ext{Value} = S$
     - 首次调用触发延迟绑定，或在立即绑定模式下启动时全量解析
   * - **R_X86_64_RELATIVE**
     - ``.got`` / ``.data``
     - $	ext{Value} = B + A$ ($B$ 为加载基址)
     - 模块加载时，根据实际 ASLR 基址重定位内部绝对指针，无需符号字符串比对
   * - **R_X86_64_DTPMOD64**
     - ``.got``
     - $	ext{Value} = 	ext{ModuleID}$
     - 线程局部存储（TLS）所属模块 ID 分配
   * - **R_X86_64_DTPOFF64**
     - ``.got``
     - $	ext{Value} = 	ext{Offset}$
     - 线程局部变量在所属 TLS 块内的相对偏移

符号查找链与符号插入（Symbol Interposition）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

动态链接器执行符号查找时，遵循确定性的作用域优先级序列：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     动态链接全局符号查找流水线                              |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 优先级 1: LD_PRELOAD 预加载对象 ]                                       |
   |      - 用户显式注入的拦截库，最高优先级介入所有外部符号决议                 |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 优先级 2: 主可执行文件全局符号表 (Main Executable) ]                   |
   |      - 主程序定义的全局符号优先覆盖共享库中的同名符号                       |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 优先级 3: DT_NEEDED 依赖库广度优先遍历链 (Breadth-First Search) ]       |
   |      - 按 ELF 动态段声明的依赖顺序，广度优先遍历各 .so 导出符号表           |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 优先级 4: RTLD_LOCAL 独立作用域 (针对 dlopen 显式加载模块) ]            |
   |      - 隔离在私有句柄链表中，不污染全局命名空间                             |
   |                                                                             |
   +-----------------------------------------------------------------------------+

符号插入（Interposition）特性允许主程序或预加载库通过定义同名函数（如自定义 ``malloc``）截断对底层系统库的调用。若共享库在编译时指定了 ``-Bsymbolic`` 标志，编译器将库内部对同模块导出函数的调用直接绑定至内部相对偏移，跳过全局介入机制。

现代链接安全加固：RELRO 机制
----------------------------

在传统的延迟绑定模型中，``.got.plt`` 必须在整个程序生命周期内保持物理内存可写（``PROT_WRITE``），以便 ``_dl_runtime_resolve`` 在运行时动态填入解析后的函数地址。

GOT 覆写攻击（GOT Overwrite Exploit）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

内存安全漏洞（如任意地址写、格式化字符串漏洞或堆溢出）攻击者常将目标函数的 GOT 条目（如 ``free@GOT``）覆写为恶意注入的 Shellcode 地址或 ``system`` 函数入口。随后当程序正常调用 ``free(ptr)`` 时，控制流劫持发生。

只读重定位（RELRO, Read-Only Relocations）防御模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代编译器与安全链接器提供两级 RELRO 防御方案：

1. **Partial RELRO（部分只读重定位，GCC 默认开启）**：
   - 链接器将 ELF 内部的初始化节区（``.init_array``、``.fini_array``、``.jcr``）以及非 PLT 的全局偏移表（``.got``）聚集至专门的内存页。
   - 动态链接器在程序加载初始化完成后，调用内核系统调用 ``mprotect(addr, len, PROT_READ)`` 将上述页区强制设为只读。
   - **防御局限**：``.got.plt`` 仍保留写权限以支持延迟绑定，仍存在局部被覆写风险。

2. **Full RELRO（完全只读重定位，通过 ``-Wl,-z,relro,-z,now`` 开启）**：
   - **废除运行时延迟绑定**：链接器设置 ``DT_BIND_NOW`` 标志位，强制动态链接器在程序启动装载阶段解析 **全部** ``.got.plt`` 函数槽位（Immediate Binding）。
   - **全局设为只读**：在将控制权移交给程序入口（``main``）之前，动态链接器将 ``.got`` 与 ``.got.plt`` 整体执行 ``mprotect(..., PROT_READ)``。
   - **安全收益**：运行期间任何试图修改 GOT 条目的指令均触发硬件 MMU 缺页异常并被内核直接终止（SIGSEGV），彻底消除 GOT 覆写攻击面。

C++ 工业级动态链接、GOT 与 PLT 延迟绑定模拟引擎实战
---------------------------------------------------

以下 C++ 源码构建了一套自包含的工业级动态链接器与 PLT/GOT 延迟绑定模拟引擎。实现覆盖：
1. 位置无关共享库对象（Shared Object）内存模型。
2. ``.got``、``.got.plt`` 与 ``.plt`` 结构体拓扑布局。
3. 动态符号查找与 ``_dl_runtime_resolve`` 延迟绑定状态机。
4. 首次调用解析回写 vs 二次调用直接寻址时钟周期对比验证。
5. RELRO（Partial 与 Full）内存页保护模拟与写违规检测。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <unordered_map>
   #include <functional>
   #include <cstdint>
   #include <cassert>
   #include <cstring>
   #include <iomanip>
   #include <memory>

   namespace dynamic_linker_engine {

   // =========================================================================
   // 1. 物理结构与内存页权限定义
   // =========================================================================
   enum PagePermission : uint32_t {
       PROT_NONE  = 0,
       PROT_READ  = 1 << 0,
       PROT_WRITE = 1 << 1,
       PROT_EXEC  = 1 << 2
   };

   struct DynamicSymbol {
       std::string Name;
       uint64_t Address; // 目标函数或变量在共享库内部的相对偏移
       bool IsFunction;
   };

   // 模拟共享对象 (.so)
   struct SharedLibrary {
       std::string LibraryName;
       uint64_t BaseAddress = 0; // 加载基址 (模拟 ASLR)
       std::unordered_map<std::string, DynamicSymbol> ExportTable;

       void addExport(const std::string& name, uint64_t offset, bool isFunc = true) {
           ExportTable[name] = DynamicSymbol{name, offset, isFunc};
       }
   };

   // =========================================================================
   // 2. PLT 与 GOT 运行时内存拓扑结构
   // =========================================================================
   struct GotEntry {
       uint64_t Value = 0;
   };

   struct PltEntry {
       std::string SymbolName;
       uint32_t RelocIndex;
       uint64_t PltStubAddress;
   };

   class DynamicLinker;

   // 运行时可执行模块上下文 (Main Binary 或 Shared Object)
   class ExecutableModule {
   public:
       std::string ModuleName;
       uint64_t BaseAddress;

       // 内存布局结构
       std::vector<GotEntry> GOT;        // .got (全局数据指针)
       std::vector<GotEntry> GOT_PLT;    // .got.plt (函数调用指针)
       std::vector<PltEntry> PLT;        // .plt 桩代码元数据

       uint32_t GotPageProtection = PROT_READ | PROT_WRITE;
       uint32_t GotPltPageProtection = PROT_READ | PROT_WRITE;

       std::unordered_map<std::string, size_t> SymbolToGotIndex;
       std::unordered_map<std::string, size_t> SymbolToPltIndex;

       ExecutableModule(const std::string& name, uint64_t baseAddr)
           : ModuleName(name), BaseAddress(baseAddr) {
           // 初始化 GOT_PLT 头部三个固定保留槽位
           GOT_PLT.resize(3);
           GOT_PLT[0].Value = baseAddr + 0x2000; // 模拟指向 .dynamic 节区
           GOT_PLT[1].Value = reinterpret_cast<uint64_t>(this); // 模拟 link_map 结构体指针
           GOT_PLT[2].Value = 0; // 运行前由动态链接器填入 _dl_runtime_resolve 地址
       }

       void registerExternalFunction(const std::string& symName) {
           size_t pltIdx = PLT.size();
           size_t gotPltIdx = GOT_PLT.size();

           // 初始状态：.got.plt 条目填入该函数专属 PLT 桩中 push 指令的虚拟地址
           uint64_t pltStubAddr = BaseAddress + 0x1000 + (pltIdx + 1) * 16;
           uint64_t pushInstAddr = pltStubAddr + 6; // 模拟 PLT 条目内部回跳偏移

           GOT_PLT.push_back(GotEntry{pushInstAddr});
           PLT.push_back(PltEntry{symName, static_cast<uint32_t>(pltIdx), pltStubAddr});

           SymbolToPltIndex[symName] = pltIdx;
           SymbolToGotIndex[symName] = gotPltIdx;
       }
   };

   // =========================================================================
   // 3. 动态链接器与运行时符号解析器 (_dl_runtime_resolve)
   // =========================================================================
   class DynamicLinker {
   private:
       std::vector<std::shared_ptr<SharedLibrary>> loadedLibraries_;
       uint64_t resolveCount_ = 0;

   public:
       void loadLibrary(const std::shared_ptr<SharedLibrary>& lib, uint64_t baseAddress) {
           lib->BaseAddress = baseAddress;
           loadedLibraries_.push_back(lib);
           std::cout << "  [动态链接器] 映射共享库: " << lib->LibraryName
                     << " -> 基址: 0x" << std::hex << lib->BaseAddress << std::dec << "
";
       }

       // 模拟全局符号检索机制 (广度优先扫描依赖链)
       uint64_t lookupSymbol(const std::string& symbolName) {
           for (const auto& lib : loadedLibraries_) {
               auto it = lib->ExportTable.find(symbolName);
               if (it != lib->ExportTable.end()) {
                   uint64_t resolvedAddress = lib->BaseAddress + it->second.Address;
                   return resolvedAddress;
               }
           }
           return 0; // 未找到符号
       }

       // 核心: _dl_runtime_resolve 运行时延迟绑定处理入口
       static uint64_t dl_runtime_resolve(ExecutableModule* module, uint32_t relocIndex, DynamicLinker* linker) {
           assert(module != nullptr && linker != nullptr);
           linker->resolveCount_++;

           const auto& pltEntry = module->PLT[relocIndex];
           const std::string& symName = pltEntry.SymbolName;

           std::cout << "
  >>> [进入 _dl_runtime_resolve] 首次解析外部符号: " << symName
                     << " (模块: " << module->ModuleName << ", 重定位索引: " << relocIndex << ") <<<
";

           // 1. 查找全局符号实际虚拟地址
           uint64_t resolvedAddr = linker->lookupSymbol(symName);
           if (resolvedAddr == 0) {
               std::cerr << "  [致命错误]: 运行时无法解析符号: " << symName << "
";
               std::exit(1);
           }

           std::cout << "      -> 符号 [" << symName << "] 匹配成功，目标虚拟地址: 0x"
                     << std::hex << resolvedAddr << std::dec << "
";

           // 2. 检查 .got.plt 页面写权限 (检测 RELRO 违规)
           if (!(module->GotPltPageProtection & PROT_WRITE)) {
               std::cerr << "  [段错误 SIGSEGV]: 尝试写入只读 GOT 页面! (Full RELRO 保护生效)
";
               std::exit(139);
           }

           // 3. 回写目标地址至 .got.plt 槽位
           size_t gotIndex = module->SymbolToGotIndex[symName];
           module->GOT_PLT[gotIndex].Value = resolvedAddr;
           std::cout << "      -> 成功回写 .got.plt[" << gotIndex << "] = 0x"
                     << std::hex << resolvedAddr << std::dec << " (完成延迟绑定固化)
";

           // 4. 返回目标地址以继续执行
           return resolvedAddr;
       }

       // 应用安全加固: Partial RELRO
       void applyPartialRelro(ExecutableModule& module) {
           module.GotPageProtection = PROT_READ; // .got 设为只读
           module.GotPltPageProtection = PROT_READ | PROT_WRITE; // .got.plt 保持可写支持延迟绑定
           std::cout << "  [安全加固] 模块 [" << module.ModuleName << "] 应用 Partial RELRO: .got 已锁定为只读
";
       }

       // 应用安全加固: Full RELRO (-z now)
       void applyFullRelro(ExecutableModule& module) {
           std::cout << "  [安全加固] 模块 [" << module.ModuleName << "] 启用 Full RELRO (-z now): 立即解析所有符号...
";
           for (const auto& plt : module.PLT) {
               uint64_t addr = lookupSymbol(plt.SymbolName);
               assert(addr != 0);
               size_t gotIdx = module.SymbolToGotIndex[plt.SymbolName];
               module.GOT_PLT[gotIdx].Value = addr;
           }
           // 将 .got 与 .got.plt 整体封闭为只读
           module.GotPageProtection = PROT_READ;
           module.GotPltPageProtection = PROT_READ;
           std::cout << "  [安全加固] 全量符号解析完毕，.got 与 .got.plt 整体锁定为 PROT_READ
";
       }

       uint64_t getResolveCount() const { return resolveCount_; }
   };

   // =========================================================================
   // 4. 模拟 CPU 硬件执行跳转状态机
   // =========================================================================
   class ExecutionCpu {
   public:
       // 模拟执行 call func@plt 指令
       static void executePltCall(ExecutableModule& module, const std::string& functionName, DynamicLinker& linker) {
           std::cout << "
[CPU 硬件时钟周期] 执行指令: call " << functionName << "@plt
";

           size_t pltIdx = module.SymbolToPltIndex[functionName];
           size_t gotIdx = module.SymbolToGotIndex[functionName];
           const auto& pltEntry = module.PLT[pltIdx];

           // 1. 读取 .got.plt 目标指针
           uint64_t targetPointer = module.GOT_PLT[gotIdx].Value;
           std::cout << "  -> 步进 1: 间接读取 GOT_PLT[" << gotIdx << "] = 0x"
                     << std::hex << targetPointer << std::dec << "
";

           // 2. 判定是否命中初始桩代码 (延迟绑定未就绪)
           uint64_t initialPushAddr = pltEntry.PltStubAddress + 6;
           if (targetPointer == initialPushAddr) {
               std::cout << "  -> 步进 2: 检测到指针未绑定，控制流回跳至 PLT 存根第二条指令 (push RelocID)
";
               std::cout << "  -> 步进 3: 跳转至 PLT0 -> 触发动态链接器延迟绑定解析...
";

               // 触发 _dl_runtime_resolve
               uint64_t finalAddr = DynamicLinker::dl_runtime_resolve(&module, pltEntry.RelocIndex, &linker);

               std::cout << "  -> 步进 4: 转移控制流至目标函数实体: 0x" << std::hex << finalAddr << std::dec << "
";
           } else {
               // 已经绑定过，零延迟直接跳向真实地址
               std::cout << "  -> 步进 2 (快速路径): GOT 已命中已解析绝对地址，直接跨模块跳转至: 0x"
                         << std::hex << targetPointer << std::dec << " (无需介入动态链接器)
";
           }
       }
   };

   } // namespace dynamic_linker_engine

   // =========================================================================
   // 5. 端到端测试套件与断言验证
   // =========================================================================
   namespace test {

   inline void runDynamicLinkingTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 动态链接、GOT/PLT 延迟绑定与 RELRO 物理断言验证套件
";
       std::cout << "=======================================================

";

       using namespace dynamic_linker_engine;

       // 1. 构建共享库环境 (模拟 libc.so 与 libmath.so)
       auto libc = std::make_shared<SharedLibrary>();
       libc->LibraryName = "libc.so.6";
       libc->addExport("puts", 0x1200, true);
       libc->addExport("malloc", 0x2400, true);

       auto libmath = std::make_shared<SharedLibrary>();
       libmath->LibraryName = "libm.so.6";
       libmath->addExport("sin", 0x3100, true);

       DynamicLinker dynamicLoader;
       // 模拟 ASLR 加载随机基址
       dynamicLoader.loadLibrary(libc, 0x7FFF10000000);
       dynamicLoader.loadLibrary(libmath, 0x7FFF20000000);

       // 2. 构建主执行模块 (main_app)
       ExecutableModule app("main_app", 0x55550000);
       app.registerExternalFunction("puts");
       app.registerExternalFunction("sin");

       // 设置 GOT_PLT[2] 解析入口
       app.GOT_PLT[2].Value = 0x7FFF0000DEAD; // 标识 _dl_runtime_resolve 虚拟入口

       // 应用 Partial RELRO
       dynamicLoader.applyPartialRelro(app);

       std::cout << "
--- [测试 1: puts 首次调用延迟绑定与 GOT 回写校验] ---
";
       size_t putsGotIdx = app.SymbolToGotIndex["puts"];
       uint64_t initialGotVal = app.GOT_PLT[putsGotIdx].Value;

       // 初始时 GOT 表项必须指向 PLT 桩内部
       assert(initialGotVal == app.PLT[app.SymbolToPltIndex["puts"]].PltStubAddress + 6);
       assert(dynamicLoader.getResolveCount() == 0);

       // 首次触发 puts
       ExecutionCpu::executePltCall(app, "puts", dynamicLoader);

       // 断言：解析器被调用且 GOT 表项被修改为 libc 中的真实绝对地址
       assert(dynamicLoader.getResolveCount() == 1);
       uint64_t expectedPutsAddr = libc->BaseAddress + 0x1200; // 0x7FFF10001200
       assert(app.GOT_PLT[putsGotIdx].Value == expectedPutsAddr);

       std::cout << "
--- [测试 2: puts 二次调用命中快速路径零解析开销] ---
";
       // 二次触发 puts
       ExecutionCpu::executePltCall(app, "puts", dynamicLoader);

       // 断言：解析器未被调用，计数器仍为 1
       assert(dynamicLoader.getResolveCount() == 1);
       assert(app.GOT_PLT[putsGotIdx].Value == expectedPutsAddr);
       std::cout << "  -> 二次调用快速路径断言通过，无任何动态解析开销。
";

       std::cout << "
--- [测试 3: Full RELRO 立即绑定与写保护断言] ---
";
       ExecutableModule secureApp("secure_app", 0x55558000);
       secureApp.registerExternalFunction("malloc");
       dynamicLoader.applyFullRelro(secureApp);

       size_t mallocGotIdx = secureApp.SymbolToGotIndex["malloc"];
       uint64_t expectedMallocAddr = libc->BaseAddress + 0x2400;
       assert(secureApp.GOT_PLT[mallocGotIdx].Value == expectedMallocAddr);
       assert(secureApp.GotPltPageProtection == PROT_READ);

       std::cout << "  -> Full RELRO 立即绑定与页权限断言完全吻合。

";
       std::cout << "  -> 动态链接与 GOT/PLT 状态机全套物理测试全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 动态链接模拟引擎，控制台输出清晰地印证了动态链接的物理流转过程：

1. **ASLR 随机基址装载**：``libc.so.6`` 被装载在 ``0x7fff10000000``，``libm.so.6`` 被装载在 ``0x7fff20000000``。
2. **首次调用解析（puts）**：``call puts@plt`` 读取 ``GOT_PLT[3]`` 发现其存储初始桩地址，触发控制流转移至 ``_dl_runtime_resolve``。加载器在 ``libc.so.6`` 中查得绝对地址 ``0x7fff10001200``，将其覆盖写入 ``GOT_PLT[3]``。
3. **二次调用快速执行（puts）**：后续调用直接从 ``GOT_PLT[3]`` 读取 ``0x7fff10001200`` 并完成跳转，动态解析器调用计数保持为 1，实现了后续调用的零动态开销。
4. **Full RELRO 安全加固验证**：``secure_app`` 启用 ``-z now`` 后，所有符号在装载时全量完成解析绑定，``.got.plt`` 内存页权限被立即收紧为 ``PROT_READ``，在底层根绝了运行期恶意指针篡改隐患。

小结与下章导读
--------------

本章系统解构了动态链接、位置无关代码与运行时调用的核心底层机制：

1. **代码与数据解耦**：阐明了只读共享代码段在多进程物理内存去重与 ASLR 约束下的物理要求，推导了 ``-fPIC`` 编译器选项对 PC 相对寻址生成的强制约束。
2. **全局偏移表 (GOT)**：推导了代码段与数据段之间相对距离恒定守恒定律，深入剖析了 ``.got`` 对跨模块全局数据读写的间接指针桥接机理。
3. **过程链接表 (PLT) 延迟绑定**：详尽拆解了 ``PLT0`` 与 ``PLTn`` 的指令流转，追踪了首次调用触发 ``_dl_runtime_resolve`` 回写 GOT 与二次调用单周期直接跳转的确定性状态机。
4. **动态重定位与 RELRO**：分析了 ``R_X86_64_GLOB_DAT``、``R_X86_64_JUMP_SLOT`` 与 ``R_X86_64_RELATIVE`` 重定位类型的行为，推导了 Partial RELRO 与 Full RELRO 在阻断 GOT 覆写攻击中的安全防御模型。

在掌握了机器级目标文件与动态链接加载机制后，现代编译体系在处理高级动态语言、跨平台中间代码或高性能执行环境时，广泛采用虚拟机与字节码解释执行架构。在第 8 模块第 4 节 **字节码解释器与分发循环：栈式 vs 寄存器式 VM、Switch-Case 与 Direct Threaded Code 效率（``08_linking_runtime_vms_and_jit/04_bytecode_interpreters_and_evaluation_loops.rst``）** 中，我们将深入剖析字节码虚拟机的核心拓扑、栈式虚拟机（Stack-based VM，如 JVM/CPython）与寄存器式虚拟机（Register-based VM，如 LuaJIT/Dalvik）的指令集特征、指令分发主循环（Evaluation Loop）的 CPU 分支预测开销，以及直接线索化代码（Direct Threaded Code）对硬件分支目标缓冲器（BTB）的利用机理。
