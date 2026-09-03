=============================================================================
Copy-and-Patch JIT 原理：Clang 模板编译与机器码拼接
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解构了 CPython 3.13 的 Tier 2 优化器架构，详细推导了宏字节码如何通过 Trace 轨迹投射展开为微指令（uops）线性流，以及基于抽象解释（Abstract Interpretation）消除冗余类型守卫的数据结构模型。经过 Tier 2 优化后，虚拟机获得了一条纯净、紧凑且无冗余分支的微指令执行轨迹。
   
   然而，微指令如果仍然由解释器循环（``_PyUop_Eval``）分发执行，依然无法摆脱函数调用跳转与通用寄存器虚拟化开销。如何将这些高频微指令直接翻译为**CPU 原生机器指令（Native Machine Code）**？
   
   传统 JIT 编译器（如 V8、PyPy、Julia）通常需要在运行时打包庞大的编译后端（如 LLVM 或定制汇编器），带来巨大的内存膨胀与编译延迟。Python 3.13 另辟蹊径，正式引入了基于学术前沿理论的 **Copy-and-Patch JIT 编译器（PEP 744）**。
   
   本章将深入 CPython 核心源码文件 ``Python/jit.c``、``Tools/jit/build.py``、``Tools/jit/_stencils.py`` 以及生成的 ``Python/jit_stencils.h``，全景式剖析 Copy-and-Patch JIT 的编译期模板提炼、Clang ``musttail`` 尾调用消除、运行时二进制 Stencil 内存拼接、跨架构重定位修补（Relocation & Relaxation）引擎，以及 CPU 指令缓存（I-Cache）物理同步机制。

-----------------------------------------------------------------------------
1. JIT 编译器的体系困局与 Copy-and-Patch 理论突破
-----------------------------------------------------------------------------

传统 JIT 架构的致命权衡
~~~~~~~~~~~~~~~~~~~~~~~~

在高级语言虚拟机的 JIT 设计中，长期存在着难以调和的二律背反：
1. **重型 JIT（Heavyweight JIT，如 LLVM / V8 TurboFan / HotSpot C2）**：
   - 优势：编译产出的机器码质量极高，能够充分利用硬件向量化与复杂寄存器分配；
   - 劣势：运行时必须引入数百 MB 的编译器静态库，编译耗时动辄数十毫秒，**JIT 预热开销（Warmup Latency）与内存占用极为恐怖**，对于生命周期短暂的 CLI 工具或批处理脚本甚至是负优化。
2. **轻量模板 JIT（Template JIT，如 Baseline JIT）**：
   - 优势：编译极快，运行时直接顺序发射机器码；
   - 劣势：缺乏指令调度与寄存器优化，生成的机器码包含大量冗余的栈加载与溢出指令，性能提升极为有限（通常仅有 10%~20%）。

Copy-and-Patch 破局革命（PEP 744）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Copy-and-Patch** 编译技术由斯坦福大学学者 Haoran Xu 与 Fredrik Kjolstad 于 2021 年提出（OOPSLA 2021 论文 *Copy-and-Patch Compilation: A Fast Compilation Algorithm for High-Level Languages and Bytecode*），并由 Brandt Bucher 移植实现至 CPython 3.13（PEP 744）：

- **核心思想：编译期重型优化前置，运行时仅做二进制拼接**；
- 在 **CPython 源码构建期（Build Time）**：使用工业级 C 编译器（Clang ``-O3``）将每个微指令（uop）的 C 代码预编译为一个个高度优化的二进制机器码模板——**模具（Stencils）**；
- 在 **Python 运行时（Runtime）**：当 Tier 2 优化器发射一条 Trace 时，JIT 引擎完全不依赖 LLVM，而是**以接近 ``memcpy`` 的超高吞吐（每秒数 GB 字节）将预编译的 Stencil 机器码复制到可执行内存页中，并就地修补其中的动态操作数与跳转地址（Patching）**！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Copy-and-Patch 编译全生命周期流水线                    |
   +=========================================================================+
   | 【阶段一：源码构建期 Build Time (由开发者/打包机执行)】                  |
   |   Python/bytecodes.c (C 源码)                                           |
   |        │                                                                |
   |        ▼ (Clang -O3 深度编译 + 保证尾调用 __attribute__((musttail)))    |
   |   build/target.o (ELF / Mach-O / COFF 目标文件)                         |
   |        │                                                                |
   |        ▼ (Tools/jit/build.py 解析 DWARF 与 Relocation Table)            |
   |   Python/jit_stencils.h (包含每个 uop 的机器码数组与重定位洞元数据)     |
   +───────────────────────────────────┬─────────────────────────────────────+
                                       │ (编译嵌入最终的 python 二进制文件)
                                       ▼
   +-------------------------------------------------------------------------+
   | 【阶段二：Python 运行时 Runtime (终端用户机器, 0 外部依赖)】            |
   |   Tier 2 优化后的 Uop Trace 序列                                         |
   |        │                                                                |
   |        ▼ (_PyJIT_Compile() 顺序拷贝机器码模具并 Patch 动态地址)         |
   |   mmap RW 内存页 ──► patch_32r / patch_aarch64 ──► mprotect RX 内存页   |
   |        │                                                                |
   |        ▼ (清除 CPU 指令缓存 __builtin___clear_cache)                    |
   |   CPU 直接全速裸跑原生机器码! (微秒级编译延迟, -O3 级代码质量)          |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
2. 编译期模具提炼与 Clang `musttail` 延续传递机制
-----------------------------------------------------------------------------

为什么构建 JIT 必须强制依赖 Clang？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CPython 自身可以用 GCC 或 MSVC 编译，但**构建 JIT 模具（JIT Stencils）必须使用 Clang 编译器**。其根本原因在于 Copy-and-Patch 依赖 C 语言的一项关键扩展特性——**保证尾调用优化（Guaranteed Tail Call Optimization: ``__attribute__((musttail))``）**。

在连续执行多个 uop 机器码模板时，微指令之间通过**延续传递风格（Continuation-Passing Style, CPS）**互相调用：

.. code-block:: c

   // 微指令函数模板示例 (Python/executor_cases.c.h)
   _Py_CODEUNIT *
   _BINARY_OP_ADD_INT(
       _PyExecutorObject *executor,
       _PyInterpreterFrame *frame,
       _PyStackRef *stack_pointer,
       PyThreadState *tstate)
   {
       // 执行整数相加运算...
       PyObject *res = PyLong_FromLong(val_a + val_b);
       stack_pointer[-2] = PyStackRef_FromPyObjectSteal(res);
       stack_pointer--;

       // 尾调用下一条微指令: 编译器必须生成直接跳转 jmp 指令, 严禁新建 C 栈帧!
       __attribute__((musttail)) return next_uop(executor, frame, stack_pointer, tstate);
   }

Clang 的 ``musttail`` 确保生成的汇编指令以单个无条件跳转（如 x86-64 的 ``jmp`` 或 AArch64 的 ``b``）收尾，绝不会生成任何 ``push %rbp``、``sub $rsp`` 或 ``ret`` 指令，从而保证多个模具拼接在一起时，能够形成连续、平坦、零栈开销的原生指令流。

`Tools/jit` 模具生成器架构
~~~~~~~~~~~~~~~~~~~~~~~~~~

构建脚本 ``Tools/jit/build.py`` 执行以下精密工序：
1. **生成包装文件**：将所有微指令包裹在统一的 CPS 签名模板中；
2. **Clang 编译为目标文件**：针对目标平台架构（``x86_64-unknown-linux-gnu``、``aarch64-apple-darwin``、``x86_64-pc-windows-msvc`` 等）生成 ``.o`` 目标文件；
3. **符号与重定位洞提取**：使用 ``llvm-readobj`` 与 ``llvm-objdump`` 解析目标文件的重定位表（Relocation Sections）：
   - 提取代码指令段（``.text``）作为 ``code_size`` 与硬编码十六进制数组；
   - 标记所有需要运行时填入实际地址的位置（称为 **Holes / 重定位洞**，如跳转目标、操作数、常量指针、GOT 槽位）；
4. **生成 `jit_stencils.h`**：将每个 uop 的模具数据结构化输出为 C 数组。

-----------------------------------------------------------------------------
3. 运行时模具拼接与内存安全引擎（`Python/jit.c`）
-----------------------------------------------------------------------------

`_PyJIT_Compile()` 两遍扫描物理算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 Tier 2 优化器决定将一段 Trace 编译为机器码时，在 ``Python/jit.c`` 中触发核心编译函数 ``_PyJIT_Compile()``：

.. code-block:: c

   int
   _PyJIT_Compile(_PyExecutorObject *executor, const _PyUOpInstruction trace[], size_t length)
   {
       /* 1. 第一遍扫描 (Pass 1): 预计算内存总容量与依赖跳板 */
       size_t code_size = 0, data_size = 0;
       jit_state state = {0};
       for (size_t i = 0; i < length; i++) {
           const StencilGroup *group = &stencil_groups[trace[i].opcode];
           state.instruction_starts[i] = code_size;
           code_size += group->code_size;
           data_size += group->data_size;
           combine_symbol_mask(group->trampoline_mask, state.trampolines.mask);
           combine_symbol_mask(group->got_mask, state.got_symbols.mask);
       }
       // 加上终止保护模具 _FATAL_ERROR
       code_size += stencil_groups[_FATAL_ERROR_r00].code_size;

       /* 2. 计算页面对齐总尺寸并分配 RW 匿名内存页 */
       size_t page_size = get_page_size();
       size_t total_size = align_to_page(code_size + trampolines_size + data_size + got_size);
       unsigned char *memory = jit_alloc(total_size); /* mmap(PROT_READ | PROT_WRITE) */

       /* 3. 第二遍扫描 (Pass 2): 模具拷贝与重定位修补 (Copy & Patch) */
       unsigned char *code = memory;
       unsigned char *data = memory + code_size + trampolines_size;
       for (size_t i = 0; i < length; i++) {
           const StencilGroup *group = &stencil_groups[trace[i].opcode];
           group->emit(code, data, executor, &trace[i], &state);
           code += group->code_size;
           data += group->data_size;
       }

       /* 4. 内存保护属性翻转与 CPU 指令缓存同步 */
       if (mark_executable(memory, total_size)) { /* mprotect(PROT_READ | PROT_EXEC) */
           jit_free(memory, total_size);
           return -1;
       }

       executor->jit_code = memory;
       executor->jit_size = total_size;
       return 0;
   }

W^X（Write XOR Execute）安全策略与指令缓存同步
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代操作系统（如 Linux 的 SELinux、macOS 的 Hardened Runtime、Windows DEP）中，**内存页严禁同时具备可写（W）与可执行（X）权限**：
1. **分配阶段**：``jit_alloc()`` 通过 ``mmap`` 或 ``VirtualAlloc`` 申请纯可读可写内存（``PROT_READ | PROT_WRITE``），供 JIT 引擎执行安全的机器码拷贝与 Patch 操作；
2. **执行阶段**：在 Patch 完成后，``mark_executable()`` 立即调用 ``mprotect(..., PROT_READ | PROT_EXEC)`` 将内存锁定为只读可执行，杜绝任何代码注入攻击；
3. **硬件指令缓存冲刷（I-Cache Flush）**：
   - 现代 CPU 具有分离的指令缓存（I-Cache）与数据缓存（D-Cache）；
   - JIT 写入的数据停留在 D-Cache 中，若不显式同步，CPU 执行单元将从 I-Cache 中读取到过期的陈旧指令导致崩溃；
   - CPython 必须调用 GCC/Clang 内建函数 ``__builtin___clear_cache()``（Windows 上调用 ``FlushInstructionCache()``），强制将 D-Cache 回写至物理内存并失效 I-Cache，确保硬件流水线精确加载最新机器码。

-----------------------------------------------------------------------------
4. 跨架构重定位修补与指令松弛（Relocation & Relaxation）
-----------------------------------------------------------------------------

重定位修补算子矩阵
~~~~~~~~~~~~~~~~~~

在 ``group->emit()`` 过程中，JIT 引擎需要将各种动态物理地址精确写入机器指令的位域中：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                      JIT 跨架构重定位修补算子表                         |
   +====================+====================================================+
   | 修补算子           | 物理语义与架构实现                                 |
   +====================+====================================================+
   | patch_32           | 32 位绝对物理地址直接覆写 (memcpy 4B)              |
   +--------------------+----------------------------------------------------+
   | patch_32r          | 32 位相对 PC 偏移量修补: value - location          |
   +--------------------+----------------------------------------------------+
   | patch_64           | 64 位绝对物理地址直接覆写 (memcpy 8B)              |
   +--------------------+----------------------------------------------------+
   | patch_aarch64_21r  | ARM64 ADRP 21 位页面差值计算: (val>>12)-(loc>>12)  |
   +--------------------+----------------------------------------------------+
   | patch_aarch64_12   | ARM64 ADD/LDR 12 位页内立即数偏移修补              |
   +--------------------+----------------------------------------------------+
   | patch_aarch64_26r  | ARM64 B/BL 26 位相对跳转指令修补 (±128MB 范围)     |
   +--------------------+----------------------------------------------------+

指令松弛优化（Instruction Relaxation）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了保证通用性，Clang 编译的代码默认使用全局偏移表（GOT）进行符号间接访问。但在 JIT 运行时，目标符号的物理地址可能非常接近当前代码段。JIT 引擎引入了**动态指令松弛（Instruction Relaxation）**，在 Patch 阶段就地重写指令：

1. **x86-64 松弛（`patch_x86_64_32rx`）**：
   - 原始指令：``mov reg, dword ptr [rip + GOT_OFFSET]``（通过 GOT 内存间接加载，耗费一次内存总线访问）；
   - 松弛重写：若目标地址在 $\pm 2	ext{GB}$ 范围内，直接将操作码字节 ``0x8B`` 原地改写为 ``0x8D``（``lea reg, [rip + OFFSET]``），**直接省去一次内存访存**！
   - 若为函数调用，将 ``call [rip + GOT]``（``0xFF 0x15``）松弛改写为直接跳转 ``nop; call OFFSET``（``0x90 0xE8``）。
2. **AArch64 松弛（`patch_aarch64_33rx`）**：
   - 原始指令对：``adrp reg, PAGE; ldr reg, [reg + OFFSET]``；
   - 松弛重写：若加载的值在 16 位整数范围内，直接将两条昂贵指令改写为单条立即数装载指令 ``movz reg, VALUE; nop``！

跨页跳转跳板（Trampoline Injection）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 AArch64（相对跳转仅支持 $\pm 128	ext{MB}$）或 macOS x86-64 调试构建中，当 JIT 代码需要跳转到一个极远的运行时 C 函数（如 ``PyLong_FromLong``）时，相对偏移量会超出指令位宽限制。

CPython JIT 在每个编译块尾部开辟了 **跳板区（Trampolines Area）**：
- 当检测到目标地址超出范围时，JIT 动态生成一段 16 字节的直接跳转跳板（Trampoline）：

.. code-block:: nasm

   ; AArch64 远跳转跳板物理拓扑
   ldr  x8, 8             ; 从后方 8 字节处加载 64 位绝对目标地址
   br   x8                ; 绝对间接跳转
   .quad 0x7fff12345678   ; 目标绝对物理地址

- 将原指令的相对跳转目标指向跳板首地址，成功化解了长距离寻址溢出问题。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ Copy-and-Patch JIT 编译器的底层物理拓扑与运行机制：
1. Copy-and-Patch 理论如何通过将 Clang 重型优化前置至编译期，破解传统 JIT 内存膨胀与预热延迟的矛盾；
2. Clang ``__attribute__((musttail))`` 保证尾调用消除与延续传递风格（CPS）无栈帧流水线；
3. ``Tools/jit/build.py`` 提取二进制机器码 Stencil 模具与重定位洞元数据；
4. ``_PyJIT_Compile()`` 的两遍扫描算法、W^X 内存安全保护翻转与 CPU 指令缓存（I-Cache）硬件同步；
5. x86-64 与 AArch64 上的重定位修补算子、动态指令松弛（GOT 寻址降解为立即数/直接跳转）与长跳转跳板（Trampoline）机制。

通过 Copy-and-Patch，CPython 获得了极速生成原生机器码的超强能力。然而，原生机器码在执行过程中如何感知对象的动态类型突变并保证安全？在下一章——全书最终大结局章节中，我们将深入剖析—— **07_jit_and_advanced_execution/03_jit_guard_and_deoptimization.rst（JIT 守卫 Guard 指令、去优化 Deoptimization 与回退机制）**。
