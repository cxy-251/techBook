====================================================================================================
JIT 动态编译与分层执行：热点探测计数器、推测特化 (Speculative Inlining)、去优化 (Deopt) 与 OSR
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 8 模块第 4 节（``08_linking_runtime_vms_and_jit/04_bytecode_interpreters_and_evaluation_loops``）中，我们深入解构了虚拟机的指令分派循环（Dispatch Loop）、栈式与寄存器式架构在指令密度与分发开销上的物理权衡，以及直接线索化代码（Direct Threaded Code）对 CPU 分支目标缓冲器（BTB）的微架构优化。纯解释执行虽然具备零启动延迟与强跨平台移植性，但其逐条指令解码分发的开销在面对长期运行的计算密集型代码时会产生严重的 CPU 吞吐瓶颈。
   **即时编译（Just-In-Time Compilation, JIT）**通过在程序运行时将高频执行的字节码或中间表示直接编译为宿主处理器的原生机器码，将动态运行时的类型反馈证据转化为深度的硬件级特化优化。本章深入解构现代分层 JIT 编译流水线，剖析热点探测与衰减计数器状态机、基于内联缓存（Inline Cache, IC）的推测特化与去虚化、保护执行假设的 Guard 机制，以及去优化（Deoptimization, Deopt）与栈上替换（On-Stack Replacement, OSR）在机器码栈帧与解释器虚拟栈帧之间的双向动态映射。

JIT 编译时序与分层执行流水线架构
--------------------------------

即时编译器与传统提前编译器（Ahead-Of-Time, AOT）的核心分水岭在于**编译成本的支付时序（Compilation Time-Window）**。AOT 编译在程序交付运行前离线执行，拥有充裕的全局分析窗口；JIT 编译直接侵占用户程序的实时响应预算与 CPU 时间片。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     现代工业级分层 JIT (Tiered JIT) 执行流水线              |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 字节码输入 (Bytecode) ]                                                 |
   |              |                                                              |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Tier 0: 解释器 (Interpreter)                                        |   |
   |   |   - 极低启动延迟，零编译开销                                        |   |
   |   |   - 收集执行统计与类型反馈 (Type Feedback / IC Profiling)           |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                                              |
   |              | (调用计数器 + 回边计数器 > Tier 1 阈值)                      |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Tier 1: 基线 JIT 编译器 (Baseline JIT)                              |   |
   |   |   - 快速单遍线性降级，生成无优化或轻量优化的机器码                  |   |
   |   |   - 剥离解释器分派循环开销，维持与解释器相同的栈布局                |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                                              |
   |              | (热点持续升温，类型反馈高度收敛 > Tier 2 阈值)               |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Tier 2: 优化 JIT 编译器 (Optimizing JIT: SSA + 全局优化)            |   |
   |   |   - 基于类型假设执行推测内联、逃逸分析、GVN、向量化与寄存器分配     |   |
   |   |   - 生成极短 Fast-Path，并在关键假设前插入 Guard 检查               |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                        |                     |
   |              | (Guard 检查通过)                       | (Guard 检查失败:    |
   |              v                                        |  假设破裂 / Deopt)  |
   |   +-----------------------+                           v                     |
   |   | 极致吞吐执行          |                +-----------------------+        |
   |   | (Peak Machine Code)   |                | 状态解构与栈帧重建    |        |
   |   +-----------------------+                | (Frame Reconstruction)|        |
   |                                                       |                     |
   |                                                       v                     |
   |                                            +-----------------------+        |
   |                                            | 安全回退至 Tier 0/1   |        |
   |                                            | (Fallback to Interp)  |        |
   |                                            +-----------------------+        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

分层编译的层级分工与收益代数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工业级 JavaScript 引擎（如 V8: Ignition -> Sparkplug -> Maglev -> TurboFan）与 Java 虚拟机（HotSpot: Template Interpreter -> C1 Client Compiler -> C2 Server Compiler / Graal）均建立在严格的分层执行模型之上。

.. list-table:: 分层编译体系各层级物理特征与权衡矩阵
   :widths: 18 22 25 35
   :header-rows: 1
   :class: tight-table

   * - 执行层级
     - 输入表示
     - 编译耗时与内存开销
     - 优化深度与核心目标
   * - **Tier 0 (解释器)**
     - Bytecode 流
     - 0 字节编译开销，即刻执行
     - 保证首屏渲染与启动极速；在分发点插桩收集调用频次与操作数类型
   * - **Tier 1 (基线 JIT)**
     - Bytecode + 局部元数据
     - 极低（微秒级单遍遍历）
     - 消除 Opcode 派发与 BTB 冲刷开销；保留完整动态分发与慢速通用路径
   * - **Tier 2 (中度优化 JIT)**
     - Bytecode + 轻量 SSA 图
     - 中等（毫秒级）
     - 基于局部类型反馈进行简单类型特化与内联，减少重型 SSA 构建开销
   * - **Tier 3 (峰值优化 JIT)**
     - 深度 SSA IR + 全量反馈
     - 较高（数十至数百毫秒）
     - 实施全套中后端优化（LICM、GVN、逃逸分析、图着色寄存器分配、向量化）

热点探测状态机与自适应衰减模型
------------------------------

JIT 运行时依靠**执行计数器（Execution Counters）**与**采样剖析器（Sampling Profiler）**驱动代码晋升。单次函数调用与循环迭代的频次决定了代码的优化收益能否覆盖编译成本。

计数器数学模型与晋升判定
~~~~~~~~~~~~~~~~~~~~~~~~

函数与循环热度由两大核心计数器量化：

1. **函数调用计数器（Invocation Counter, $C_{invoc}$）**：每次进入函数入口时递增。
2. **循环回边计数器（Backedge Counter, $C_{backedge}$）**：每次循环体跳转至循环头时递增。

综合热度得分 $H$ 形式化定义为：

.. math::

   H = C_{invoc} + \gamma \cdot C_{backedge}

其中 $\gamma$ 为回边权重系数（通常取值在 $10 \sim 100$ 之间，以放大长时间运行但调用次数较少的循环代码权重）。

当综合得分达到层级迁移阈值 $\Theta_{tier}$ 时，运行时将该函数或循环加入后台异步编译队列（Compilation Task Queue）：

.. math::

   H \ge \Theta_{tier} \implies 	ext{Enqueue}(	ext{Function}, 	ext{TargetTier})

计数器时间衰减（Decay / Aging）机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止程序在生命周期极长时将偶发执行的冷代码错误累积判定为热点，运行时必须引入衰减机制。在全局安全点（Safepoint）或定期时钟中断下，执行计数器按半衰期规则进行位移衰减：

.. math::

   C_{decayed} = C_{current} \gg 1 = \lfloor \frac{C_{current}}{2} \rfloor

衰减机制确保仅有**在近期时间窗口内保持高频执行的代码段**维持高热度，释放不再活跃代码占用的后台编译资源。

运行时类型反馈与推测特化 (Speculative Inlining)
-----------------------------------------------

动态语言（如 JavaScript、Python、Ruby）与具备多态特性的静态语言（如 Java 接口调用、C++ 虚函数）在源码层面隐藏了确定的底层数据类型与物理内存布局。JIT 编译器的核心性能飞跃源于**将过去的类型观测记录转化为对未来执行的乐观推测（Speculation）**。

内联缓存 (Inline Cache, IC) 物理状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

内联缓存是运行时在字节码调用点或属性访问点部署的轻量级自修改缓存结构。其状态迁移遵循严格的单向或自适应多态演进：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       内联缓存 (Inline Cache, IC) 状态流转                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ 单态未初始化 (Uninitialized: 初始冷状态) ]                   |
   |                                    |                                        |
   |                                    | (首度观测到 Shape A / Class A)         |
   |                                    v                                        |
   |              [ 单态稳定态 (Monomorphic: 命中率 > 99%) ]                     |
   |              - 缓存: [Shape A -> Fixed Offset X]                            |
   |              - 机器码: 单条 cmp + 寄存器相对寻址 load                       |
   |                                    |                                        |
   |                                    | (观测到新类型 Shape B, 累计种类 <= N)  |
   |                                    v                                        |
   |              [ 多态稳定态 (Polymorphic: 2 <= 种类 <= 4) ]                   |
   |              - 缓存: 线性查找表 [(Shape A, Off A), (Shape B, Off B)]        |
   |              - 机器码: 级联条件分支链 (Cascading JCC)                       |
   |                                    |                                        |
   |                                    | (类型种类突破阈值 > 4)                 |
   |                                    v                                        |
   |              [ 超多态退化态 (Megamorphic / Generic) ]                       |
   |              - 缓存: 全局哈希分派表或完全放弃 IC 缓存                       |
   |              - 机器码: 间接调用运行时通用属性查找 Stub 函数                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

对象形状 (Hidden Class / Shape / Map) 机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

动态对象在物理内存中通常由“形状指针（Shape Pointer）+ 属性值扁平数组（Properties Array）”构成。相同属性添加顺序的对象共享同一个全局只读 Shape 描述符：

.. math::

   	ext{Object} = \langle 	ext{ShapeAddress}, 	ext{Slot}_0, 	ext{Slot}_1, \dots, 	ext{Slot}_k \rangle

当 IC 处于单态（Monomorphic）时，原本需要数十个时钟周期的哈希查找或原型链遍历，在机器码中被特化为两条紧凑指令：

.. code-block:: nasm

   ; 单态属性读取机器码特化 (obj.x)
   movq   0(%rdi), %rax          ; 提取对象的 Shape 指针
   cmpq   $Shape_Point2D, %rax   ; Shape Guard: 校验是否为预期的 Shape_Point2D
   jne    .Ldeopt_bailout        ; 校验失败: 触发去优化或慢速路径
   movq   8(%rdi), %rax          ; Fast-Path: 直接从固定偏移 8 字节读取字段 x

推测内联 (Speculative Inlining) 与去虚化 (Devirtualization)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于虚函数调用或动态函数调用，当类型反馈证明调用目标高度收敛至单一具体函数 $F_{target}$ 时，优化 JIT 编译器执行两项深度转换：

1. **去虚化（Devirtualization）**：消除间接函数指针查找（``call *%rax``），替换为带守卫的直接跳转。
2. **推测内联（Speculative Inlining）**：将 $F_{target}$ 的整个控制流图与 SSA IR 展开并缝合至调用者函数内部。

内联彻底抹平了函数调用边界，使得常数传播、公共子表达式消除（CSE）、死代码消除以及循环不变量外提能够跨越原函数调用点展开全局穿透优化。

守卫 (Guards) 与去优化 (Deoptimization)
---------------------------------------

推测优化建立在“过去的执行特征将延续至未来”的经验假设之上。然而，动态语言的运行语义允许程序在任意时刻引入新类型、重写对象原型或修改全局变量。**Guard 指令是维系推测优化合法性与程序语义精确保持的物理闸门**。

Guard 的物理形态与分类
~~~~~~~~~~~~~~~~~~~~~~

Guard 在机器码中体现为轻量级的条件校验与条件跳转指令：

.. list-table:: JIT 优化中核心 Guard 类型与语义保持目标
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - Guard 类别
     - 校验条件
     - 保护的高级优化假设
   * - **Shape / Class Guard**
     - ``Obj->Shape == ExpectedShape``
     - 保护对象字段在固定物理偏移处的直接寻址，防止属性缺失或错位
   * - **Type Guard**
     - ``IsSmi(Val)`` / ``IsDouble(Val)``
     - 消除动态装箱/拆箱（Boxing/Unboxing）与多态类型分发
   * - **Overflow Guard**
     - ``jo .Ldeopt`` (检查溢出标志 OF)
     - 将 64 位整数运算限制在 32 位机器寄存器内，溢出时回退至大数对象处理
   * - **Array Bounds Guard**
     - ``Index < Array->Length``
     - 消除后续循环内冗余的数组越界检查（BCE 优化）
   * - **Global Assumption Guard**
     - ``DependencyContext->IsValid()``
     - 保护单态原型链假设与未被重写的内建全局函数（如 ``Array.prototype.push``）

去优化 (Deoptimization) 状态机与物理栈帧重建
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 Guard 条件判定失败时，当前优化机器码的执行假设瞬间宣告破裂。JIT 必须**原子性地中止当前机器码的执行，并将优化栈帧完全解构、还原为解释器或基线 JIT 能够理解的虚拟栈帧状态**，随后无缝恢复执行。该过程称为**去优化（Deopt）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     去优化 (Deopt) 物理栈帧解构与重建流水线                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 优化 JIT 物理栈帧 (Optimized Physical Frame) ]                          |
   |   +---------------------------------------------------------------------+   |
   |   | RSP -> 物理寄存器: RAX=x (未装箱), RBX=y, R12=i (循环变量)           |   |
   |   |        溢出栈槽: Spill[0], Spill[1]                                 |   |
   |   |        (包含多个内联函数压平后的混合物理上下文)                      |   |
   |   +---------------------------------------------------------------------+   |
   |                                    |                                        |
   |                                    | (Guard 失败: 触发 Deopt Bailout)       |
   |                                    v                                        |
   |   [ 查阅 Safepoint / Deopt 映射元数据表 (Deopt Table) ]                     |
   |   - 根据触发 Deopt 的机器码指令偏移 (Bailout PC) 定位 Safepoint 条目:       |
   |     * 确定对应的 Bytecode PC 位置                                           |
   |     * 提取内联调用深度与各内联函数的作用域描述符                            |
   |     * 解析每个虚拟局部变量在物理寄存器或溢出槽中的映射表达式                |
   |                                    |                                        |
   |                                    v                                        |
   |   [ 运行时栈重构器 (Stack Frame Reconstructor / Deoptimizer) ]             |
   |   - 在宿主栈上分配 N 个连续的解释器虚拟栈帧 (Interpreter Frames)            |
   |   - 对寄存器内的裸数值执行装箱 (Boxing)，填充至对应解释器 Frame->Locals     |
   |   - 重建解释器的操作数求值栈 (Operand Stack) 深度与元素                     |
   |   - 调整解释器 PC 指针，精准指向触发 Bailout 的那条 Bytecode 指令          |
   |                                    |                                        |
   |                                    v                                        |
   |   [ 切换执行引擎: 启动解释器从指定 Bytecode PC 继续推进执行 ]               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

急切去优化 (Eager Deopt) 与惰性去优化 (Lazy Deopt)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **急切去优化（Eager Deoptimization）**：由当前正在执行的优化机器码内部的 Guard 触发。执行流同步离开机器码并立即重建解释器帧。
- **惰性去优化（Lazy Deoptimization）**：由外部异步事件触发（例如动态加载了新的子类破坏了类层次结构分析 CHA 假设，或全局原型链被用户代码污染）。
  此时该函数可能正在调用栈深处挂起等待返回。运行时通过**栈帧修补（On-Stack Patching）**将该优化栈帧的返回地址（Return Address）重写为通用的 ``DeoptTrampoline`` 跳板入口。当被调用函数返回时，控制流自动落入跳板并触发栈帧重构。

栈上替换 (On-Stack Replacement, OSR)
------------------------------------

通常的 JIT 编译以函数为粒度，优化后的机器码在下一次函数调用时生效。如果一个函数仅被调用一次，但其内部包含执行数百万次的重量级长循环，单纯依赖函数入口编译将永远无法加速当前调用。

**栈上替换（On-Stack Replacement, OSR）**允许程序在**循环正在执行的某一轮迭代中，将活跃的解释器栈帧动态替换为优化后的机器码栈帧，并在不退出函数的前提下无缝切换至机器码执行**。

OSR 编译与入口状态同步
~~~~~~~~~~~~~~~~~~~~~~

1. **回边触发**：解释器在循环回边（Loop Backedge）发现计数器溢出，判定当前循环为超级热点，触发 OSR 编译请求。
2. **状态捕获**：JIT 编译器以当前循环头（Loop Header）为入口点，将循环头部所有活跃的局部变量与操作数栈状态定义为 OSR 入口参数。
3. **机器码生成与栈转移**：
   - 编译器生成具备专用 OSR 入口（OSR Entry Stub）的机器码。
   - 运行时分配新的物理栈帧，将解释器局部变量槽中的值按寄存器分配方案装载入物理寄存器或栈槽。
   - 修改 CPU 的程序计数器（RIP）与栈指针（RSP），直接跳转至机器码循环体内开始原生执行。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     解释执行向机器码的 OSR 栈上热迁移时序                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   解释器循环执行:                                                           |
   |     for (i = 0; i < 10000000; i++) {                                        |
   |       Sum += arr[i];                                                        |
   |       [Backedge Counter++] -> 当 i = 1000 时达到 OSR 阈值                   |
   |     }                                                                       |
   |                                                                             |
   |   OSR 栈帧迁移点 (Migration Point at i = 1000):                             |
   |                                                                             |
   |   [ 解释器栈帧 (Interpreter Frame) ]                                        |
   |   - Locals[0] (arr) = 0x7fff0010                                            |
   |   - Locals[1] (i)   = 1000                                                  |
   |   - Locals[2] (Sum) = 499500                                                |
   |          |                                                                  |
   |          | (OSR Frame Translation: 将局部变量值搬迁至机器物理寄存器)        |
   |          v                                                                  |
   |   [ JIT 优化机器码执行上下文 (OSR Machine Context) ]                        |
   |   - RDI = 0x7fff0010 (arr 指针)                                             |
   |   - RSI = 1000       (循环索引 i)                                           |
   |   - RAX = 499500     (累加器 Sum)                                           |
   |          |                                                                  |
   |          v                                                                  |
   |   JMP *OSR_Loop_Header_Entry -> 纯原生 SIMD 机器码从 i=1000 循环至结束      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

代码缓存 (Code Cache) 与可执行内存生命周期管理
----------------------------------------------

JIT 编译生成的原生机器码直接写入操作系统的内存堆空间中，必须接受操作系统的内存保护机制与 CPU 指令缓存一致性约束。

可执行内存保护 (W^X / DEP 规范)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代操作系统（Linux、macOS、Windows）严格执行**W^X（Write XOR Execute, 写异或执行）**安全策略。一块物理内存页绝不允许同时具备可写（``PROT_WRITE``）与可执行（``PROT_EXEC``）权限，以防御缓冲区溢出代码注入攻击。

JIT 编译器的内存写入流水线必须遵循严格的三阶段状态切换：

.. math::

   	ext{mmap}(	ext{PROT\_READ} \mid 	ext{PROT\_WRITE}) \xrightarrow{	ext{Emitting Machine Code}} 	ext{mprotect}(	ext{PROT\_READ} \mid 	ext{PROT\_EXEC}) \xrightarrow{	ext{Execution}} 	ext{Clear Cache}

在 macOS（Apple Silicon）平台上，JIT 引擎需调用底层专用硬件指令快速切换线程级写保护：

.. code-block:: c

   pthread_jit_write_protect_np(0); // 开启写权限（禁止执行）
   // 向 Code Cache 写入机器码字节流
   memcpy(code_ptr, generated_bytes, size);
   pthread_jit_write_protect_np(1); // 恢复执行权限（禁止写入）
   sys_icache_invalidate(code_ptr, size); // 强制刷出 CPU 指令缓存 (I-Cache Flush)

指令缓存一致性 (I-Cache / D-Cache Coherency)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代超标量处理器采用哈佛结构（Harvard Architecture）或分离式一级缓存（L1-I 指令缓存与 L1-D 数据缓存）。
当 JIT 编译器通过数据存储指令（Store）将机器码写入内存时，新指令仅停留在 CPU 的 **L1 数据缓存** 中。如果不进行显式同步，**L1 指令缓存** 可能仍保留着旧的陈旧数据或无效条目。
因此，在将控制流跳转至新生成的 JIT 机器码前，**必须显式执行指令缓存失效指令**（如 ARM 架构上的 ``ISB`` / ``DSB`` 指令，或 x86 架构上的隐式流水线同步），以确保 CPU 取指单元从物理内存中拉取最新的有效指令。

C++ 工业级分层 JIT、推测特化与去优化微内核实战
----------------------------------------------

以下 C++ 源码实现了一套自包含的工业级分层 JIT 编译与执行微内核系统：
1. **虚拟机解释器（Tier 0）**：支持基本算术、对象属性访问、调用与回边计数器插桩。
2. **内联缓存（IC）与类型反馈系统**：记录对象 Shape 并自动迁移状态（Uninitialized -> Monomorphic -> Megamorphic）。
3. **JIT 编译器（Tier 1）**：生成包含 Shape Guard、固定偏移直接访问与溢出保护的优化机器码指令流。
4. **Deoptimizer 栈重构引擎**：当传入异构对象触发 Guard 失败时，模拟精准的去优化（Deopt Bailout）流程，从机器物理上下文解构并无缝重建解释器栈帧，完成剩余执行。
5. **配套单元测试套件**：涵盖冷启动解释、热点识别晋升、单态机器码加速、异构数据输入触发 Deopt 并在解释器中安全恢复的全闭环验证。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <cstdint>
   #include <cassert>
   #include <memory>
   #include <unordered_map>
   #include <iomanip>
   #include <functional>

   namespace jit_core {

   // =========================================================================
   // 1. 对象模型与 Shape (Hidden Class) 体系
   // =========================================================================
   struct Shape {
       uint32_t ShapeId;
       std::string ClassName;
       std::unordered_map<std::string, size_t> PropertyOffsets;

       Shape(uint32_t id, std::string name) : ShapeId(id), ClassName(std::move(name)) {}
   };

   struct DynamicObject {
       const Shape* ObjectShape;
       std::vector<int64_t> PropertyStorage;

       DynamicObject(const Shape* shape) : ObjectShape(shape) {
           PropertyStorage.resize(shape->PropertyOffsets.size(), 0);
       }

       void setProperty(const std::string& name, int64_t val) {
           auto it = ObjectShape->PropertyOffsets.find(name);
           assert(it != ObjectShape->PropertyOffsets.end() && "Property not found in shape!");
           PropertyStorage[it->second] = val;
       }

       int64_t getPropertyGeneric(const std::string& name) const {
           auto it = ObjectShape->PropertyOffsets.find(name);
           assert(it != ObjectShape->PropertyOffsets.end() && "Property not found in shape!");
           return PropertyStorage[it->second];
       }
   };

   // =========================================================================
   // 2. 字节码指令集与内联缓存 (Inline Cache, IC)
   // =========================================================================
   enum BytecodeOp : uint8_t {
       BC_LOAD_LOCAL = 0,   // [slot] -> Push Locals[slot]
       BC_STORE_LOCAL,      // [slot] -> Locals[slot] = Pop()
       BC_LOAD_CONST,      // [const_val] -> Push const_val
       BC_GET_PROPERTY,     // [prop_name_idx, ic_slot] -> Pop obj, Push obj.prop
       BC_ADD,              // Pop b, Pop a -> Push a + b
       BC_LOOP_BACKEDGE,    // [target_pc] -> 回边计数递增, if continue goto target
       BC_RETURN            // 结束执行并返回栈顶
   };

   enum ICState {
       IC_UNINITIALIZED,
       IC_MONOMORPHIC,
       IC_MEGAMORPHIC
   };

   struct InlineCacheSlot {
       ICState State = IC_UNINITIALIZED;
       const Shape* CachedShape = nullptr;
       size_t CachedOffset = 0;
       uint64_t HitCount = 0;
       uint64_t MissCount = 0;

       void recordAccess(const DynamicObject* obj, const std::string& propName) {
           if (State == IC_UNINITIALIZED) {
               State = IC_MONOMORPHIC;
               CachedShape = obj->ObjectShape;
               CachedOffset = obj->ObjectShape->PropertyOffsets.at(propName);
               HitCount++;
           } else if (State == IC_MONOMORPHIC) {
               if (obj->ObjectShape == CachedShape) {
                   HitCount++;
               } else {
                   State = IC_MEGAMORPHIC;
                   CachedShape = nullptr;
                   MissCount++;
               }
           } else {
               MissCount++;
           }
       }
   };

   struct BytecodeInst {
       BytecodeOp Op;
       int32_t Arg0;
       int32_t Arg1;
   };

   // =========================================================================
   // 3. 解释器与 JIT 虚拟机状态机
   // =========================================================================
   class JITExecutionEngine {
   public:
       // 编译阈值
       static constexpr uint64_t JIT_INVOCATION_THRESHOLD = 5;
       static constexpr uint64_t JIT_BACKEDGE_THRESHOLD = 100;

       std::vector<std::string> StringTable;
       std::vector<BytecodeInst> Bytecode;
       std::vector<InlineCacheSlot> ICSlots;

       // 剖析计数器
       uint64_t InvocationCount = 0;
       uint64_t BackedgeCount = 0;
       bool IsJITCompiled = false;

       // JIT 统计指标
       uint64_t JITFastPathHits = 0;
       uint64_t DeoptCount = 0;

       JITExecutionEngine() = default;

       // 3.1 解释器执行路径 (Tier 0)
       int64_t interpret(const std::vector<DynamicObject*>& points) {
           InvocationCount++;
           if (InvocationCount >= JIT_INVOCATION_THRESHOLD && !IsJITCompiled) {
               compileToJIT();
           }

           // 如果已经 JIT 编译且处于优化态，则直接派发至 JIT Fast Path
           if (IsJITCompiled) {
               return runJITMachineCode(points);
           }

           std::vector<int64_t> operandStack;
           std::vector<int64_t> locals(8, 0);
           // Local 0: points array (虚拟指针模拟)
           // Local 1: sum = 0
           // Local 2: index = 0

           size_t pc = 0;
           while (pc < Bytecode.size()) {
               const auto& inst = Bytecode[pc++];
               switch (inst.Op) {
                   case BC_LOAD_CONST:
                       operandStack.push_back(inst.Arg0);
                       break;
                   case BC_LOAD_LOCAL:
                       operandStack.push_back(locals[inst.Arg0]);
                       break;
                   case BC_STORE_LOCAL: {
                       int64_t v = operandStack.back();
                       operandStack.pop_back();
                       locals[inst.Arg0] = v;
                       break;
                   }
                   case BC_GET_PROPERTY: {
                       size_t currentIdx = static_cast<size_t>(locals[2]);
                       DynamicObject* obj = points[currentIdx];
                       std::string propName = StringTable[inst.Arg0];
                       auto& ic = ICSlots[inst.Arg1];

                       ic.recordAccess(obj, propName);

                       int64_t val = 0;
                       if (ic.State == IC_MONOMORPHIC && obj->ObjectShape == ic.CachedShape) {
                           // IC 命中: 直接按偏移读取
                           val = obj->PropertyStorage[ic.CachedOffset];
                       } else {
                           // 通用降级读取
                           val = obj->getPropertyGeneric(propName);
                       }
                       operandStack.push_back(val);
                       break;
                   }
                   case BC_ADD: {
                       int64_t b = operandStack.back(); operandStack.pop_back();
                       int64_t a = operandStack.back(); operandStack.pop_back();
                       operandStack.push_back(a + b);
                       break;
                   }
                   case BC_LOOP_BACKEDGE: {
                       BackedgeCount++;
                       locals[2]++; // index++
                       if (static_cast<size_t>(locals[2]) < points.size()) {
                           pc = inst.Arg0; // 跳回循环头
                       }
                       break;
                   }
                   case BC_RETURN:
                       return locals[1]; // 返回 sum
               }
           }
           return locals[1];
       }

       // 3.2 JIT 编译器 (Tier 1 优化特化)
       void compileToJIT() {
           // 检查 IC 是否收敛为单态
           if (!ICSlots.empty() && ICSlots[0].State == IC_MONOMORPHIC) {
               IsJITCompiled = true;
               std::cout << "  >>> [JIT 编译引擎]: 函数达到热点阈值 (调用 " 
                         << InvocationCount << " 次), IC 反馈收敛于 ShapeId=" 
                         << ICSlots[0].CachedShape->ShapeId << " (" 
                         << ICSlots[0].CachedShape->ClassName << "), 生成推测特化机器码!
";
           }
       }

       // 3.3 JIT 优化机器码与 Guard 校验执行 (Tier 1 Fast Path)
       int64_t runJITMachineCode(const std::vector<DynamicObject*>& points) {
           const Shape* expectedShape = ICSlots[0].CachedShape;
           size_t fastOffset = ICSlots[0].CachedOffset;

           int64_t sum = 0;
           for (size_t i = 0; i < points.size(); ++i) {
               DynamicObject* obj = points[i];

               // -------------------------------------------------------------
               // SHAPE GUARD 校验: 检查实际运行时对象的 Shape 是否与假设一致
               // -------------------------------------------------------------
               if (__builtin_expect(obj->ObjectShape == expectedShape, 1)) {
                   // [FAST PATH]: 纯原生直接寻址，消除所有字典查找与分发
                   sum += obj->PropertyStorage[fastOffset];
                   JITFastPathHits++;
               } else {
                   // ---------------------------------------------------------
                   // GUARD 破裂 -> 触发去优化 (Deoptimization Bailout)
                   // ---------------------------------------------------------
                   DeoptCount++;
                   std::cout << "  >>> [DEOPT BAILOUT]: 遇到异构对象 ShapeId=" 
                             << obj->ObjectShape->ShapeId << " (" << obj->ObjectShape->ClassName 
                             << "), 破坏单态假设! 触发去优化并无缝回退至解释器...
";

                   // 栈帧重建与解释器恢复执行
                   return executeDeoptRecovery(points, i, sum);
               }
           }
           return sum;
       }

       // 3.4 去优化栈帧重建器 (Deoptimizer & State Reconstruction)
       int64_t executeDeoptRecovery(const std::vector<DynamicObject*>& points, 
                                    size_t currentIdx, 
                                    int64_t currentSum) {
           std::cout << "  >>> [栈帧重建器]: 将当前物理状态 (Index=" << currentIdx 
                     << ", Sum=" << currentSum << ") 映射还原为解释器虚拟栈帧 Locals[1]=Sum, Locals[2]=Index
";

           // 废黜 JIT 优化代码 (Invalidate JIT Code)
           IsJITCompiled = false;
           ICSlots[0].State = IC_MEGAMORPHIC;

           // 建立解释器虚拟上下文
           std::vector<int64_t> locals(8, 0);
           locals[1] = currentSum;  // 恢复累加和
           locals[2] = currentIdx;  // 恢复循环索引

           // 从当前断点继续以解释器模式推进剩余迭代
           for (size_t i = currentIdx; i < points.size(); ++i) {
               DynamicObject* obj = points[i];
               // 解释器通用读取路径 (满足完整多态语义)
               int64_t val = obj->getPropertyGeneric(StringTable[Bytecode[1].Arg0]);
               locals[1] += val;
               locals[2]++;
           }

           std::cout << "  >>> [解释器恢复完成]: 成功保持程序绝对语义正确性，返回最终结果。
";
           return locals[1];
       }
   };

   } // namespace jit_core

   // =========================================================================
   // 4. 端到端分层 JIT、特化与去优化测试套件
   // =========================================================================
   namespace test {

   inline void runJITArchitectureTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 分层 JIT 编译、推测特化与去优化 (Deopt) 全链路物理验证
";
       std::cout << "=======================================================

";

       using namespace jit_core;

       // 1. 初始化对象形状系统
       Shape shapePoint2D(1, "Point2D");
       shapePoint2D.PropertyOffsets["x"] = 0;
       shapePoint2D.PropertyOffsets["y"] = 1;

       Shape shapePoint3D(2, "Point3D_Extended");
       shapePoint3D.PropertyOffsets["name_tag"] = 0;
       shapePoint3D.PropertyOffsets["y"] = 1;
       shapePoint3D.PropertyOffsets["x"] = 2; // 注意 x 位于偏移 2

       // 2. 初始化 JIT 执行引擎并组装字节码 (对应 totalX 函数)
       JITExecutionEngine engine;
       engine.StringTable.push_back("x"); // String #0 = "x"
       engine.ICSlots.resize(1);          // 分配 1 个 IC 槽位

       // 组装等价字节码流
       engine.Bytecode = {
           {BC_LOAD_CONST, 0, 0},     // 0: push 0 (sum 初始值)
           {BC_STORE_LOCAL, 1, 0},    // 1: Locals[1] (sum) = 0
           {BC_LOAD_CONST, 0, 0},     // 2: push 0 (index 初始值)
           {BC_STORE_LOCAL, 2, 0},    // 3: Locals[2] (index) = 0
           // LoopHeader (PC: 4)
           {BC_GET_PROPERTY, 0, 0},   // 4: 读取 points[index].x (使用 String#0, IC#0)
           {BC_LOAD_LOCAL, 1, 0},     // 5: push sum
           {BC_ADD, 0, 0},            // 6: sum + points[index].x
           {BC_STORE_LOCAL, 1, 0},    // 7: sum = pop()
           {BC_LOOP_BACKEDGE, 4, 0},  // 8: loop back to PC 4
           {BC_RETURN, 0, 0}          // 9: return sum
       };

       // 3. 构建同构 Point2D 点集测试数据 (每个点的 x 均为 10)
       std::vector<std::unique_ptr<DynamicObject>> homogeneousPool;
       std::vector<DynamicObject*> homogeneousBatch;
       for (int i = 0; i < 100; ++i) {
           auto p = std::make_unique<DynamicObject>(&shapePoint2D);
           p->setProperty("x", 10);
           p->setProperty("y", 20);
           homogeneousBatch.push_back(p.get());
           homogeneousPool.push_back(std::move(p));
       }

       std::cout << "--- [阶段 1: 解释执行启动与类型反馈收集 (Tier 0)] ---
";
       for (int i = 0; i < 4; ++i) {
           int64_t res = engine.interpret(homogeneousBatch);
           assert(res == 1000);
       }
       std::cout << "  [解释器执行完毕]: 当前调用次数 = " << engine.InvocationCount 
                 << ", IC 命中 = " << engine.ICSlots[0].HitCount 
                 << ", JIT 编译状态 = " << (engine.IsJITCompiled ? "已编译" : "未编译") << "

";

       std::cout << "--- [阶段 2: 达到阈值触发 JIT 编译与推测特化 (Tier 1)] ---
";
       // 第 5 次调用，将触发 JIT 编译
       int64_t res5 = engine.interpret(homogeneousBatch);
       assert(res5 == 1000);
       assert(engine.IsJITCompiled == true);

       // 第 6 次调用，走完全特化的 JIT Fast Path
       int64_t res6 = engine.interpret(homogeneousBatch);
       assert(res6 == 1000);
       std::cout << "  [JIT 机器码执行完毕]: JIT Fast-Path 极速命中次数 = " 
                 << engine.JITFastPathHits << " 次 (零开销内存偏移直接寻址)

";

       std::cout << "--- [阶段 3: 注入异构对象触发 Guard 失败与去优化 (Deopt)] ---
";
       // 构建包含 Point3D 异构对象的数据批次
       std::vector<std::unique_ptr<DynamicObject>> mixedPool;
       std::vector<DynamicObject*> mixedBatch;
       for (int i = 0; i < 100; ++i) {
           if (i == 50) {
               // 在第 50 个元素注入异构对象 (x 偏移不同，值为 500)
               auto p3d = std::make_unique<DynamicObject>(&shapePoint3D);
               p3d->setProperty("name_tag", 999);
               p3d->setProperty("y", 20);
               p3d->setProperty("x", 500);
               mixedBatch.push_back(p3d.get());
               mixedPool.push_back(std::move(p3d));
           } else {
               auto p2d = std::make_unique<DynamicObject>(&shapePoint2D);
               p2d->setProperty("x", 10);
               p2d->setProperty("y", 20);
               mixedBatch.push_back(p2d.get());
               mixedPool.push_back(std::move(p2d));
           }
       }

       // 预期结果: 99 * 10 + 1 * 500 = 990 + 500 = 1490
       int64_t mixedResult = engine.interpret(mixedBatch);
       std::cout << "  [去优化执行结果]: 计算总和 = " << mixedResult 
                 << " (预期 1490, 校验完全精确!)
";
       assert(mixedResult == 1490);
       assert(engine.DeoptCount == 1);
       assert(engine.IsJITCompiled == false);

       std::cout << "
=======================================================
";
       std::cout << " JIT 编译、推测内联特化与去优化状态机全部断言通过!
";
       std::cout << "=======================================================
";
   }

   } // namespace test
