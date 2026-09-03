================================================================================
执行范式全景：解释器、AOT 编译、Transpiler 与 JIT 动态反馈的成本支付阶段权衡
================================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们建立了“编译作为表示流转序列”的工程心智模型，剖析了 Token、AST、High-Level IR、Mid-Level SSA IR、Machine IR 到物理目标二进制（ELF/Mach-O）的多级抽象降级与信息守恒规律。本章在此基础上，将视角拓展至程序表示在生命周期各阶段的物理执行范式，系统拆解解释执行（Interpreter）、静态提前编译（AOT Compiler）、源码级转换（Transpiler）与即时编译（JIT Compiler）四大执行策略在编译时（Compile-Time）、加载时（Load-Time）与运行时（Runtime）之间的成本转移规律、微架构执行特征与动态特化物理法则。

程序执行范式的物理本质与成本支付阶段
------------------------------------

计算机程序表示向物理硬件动作映射时，系统架构必须解决一个核心物理问题：**指令流由物理 CPU 译码器直接驱动，还是由常驻内存的宿主软件循环分派驱动？进行程序变换与优化的计算开销，究竟在软件交付前支付，还是在用户运行期间动态支付？**

程序生命周期中存在三个明确的时间边界与阶段成本划分：

1. **编译时（Compile-Time）**：在开发者机器或 CI 编译集群中发生。该阶段具有算力充裕、允许长耗时全局静态分析的特点。编译器执行深度死代码消除、循环向量化与图着色寄存器分配，直接支付高昂的算法计算成本。
2. **加载时（Load-Time）**：在程序由操作系统 execve 系统调用唤起、动态链接器（ld.so）执行符号重定位与虚拟内存映射时发生。该阶段主要支付动态符号绑定、GOT/PLT 表填充以及特定虚拟机的预加载验证成本。
3. **运行时（Runtime）**：CPU 物理指令执行与应用逻辑计算阶段。该阶段对延迟与吞吐高度敏感，任何额外的编译分析、分派跳转与类型检查都会直接挤占物理算力，造成时钟周期损耗与内存带宽争用。

.. list-table:: 四大执行范式的形式化状态机映射与生命周期边界
   :widths: 18 20 20 22 20
   :header-rows: 1
   :class: tight-table

   * - 执行范式
     - 核心输入表示
     - 最终执行载体
     - 主要成本支付阶段
     - 优化依据来源
   * - 解释器 (Interpreter)
     - AST / Bytecode / Threaded Code
     - 宿主 VM 软件分派循环
     - 运行时 (逐条分派开销)
     - 静态语言规范与局部状态
   * - AOT 编译器 (AOT Compiler)
     - 源码 / 静态 SSA IR
     - 物理 CPU (原生机器码)
     - 编译时 (全局分析与寄存器分配)
     - 全局静态代码事实与目标 ISA 约束
   * - 转译器 (Transpiler)
     - 源语言 $ AST / IR
     - 目标语言 $ 源码文本
     - 构建时 (AST 语法重写)
     - 跨语言形式语义等价映射
   * - JIT 编译器 (JIT Compiler)
     - Bytecode / 运行反馈向量
     - 物理 CPU (动态生成机器码)
     - 运行时 (多层编译与去优化)
     - 运行时采样、类型反馈与分支偏置

解释器范式：程序表示的原位逐条解释与分派微架构
----------------------------------------------

解释器（Interpreter）的物理定义是：**接收一种自包含的程序表示，由常驻宿主程序循环读取操作码，直接在宿主进程内存中模拟状态迁移并产生可观察副作用的软件执行引擎。**

解释器消费的内部表示包括树形 AST、线性字节码（Bytecode）或直接穿透式代码（Direct Threaded Code）。解释器跳过了将 IR 降级为目标平台机器码的后端流程，具有极低的前置初始化延迟与极高的跨平台可移植性。

字节码分派循环与 CPU 分支预测器惩罚
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

解释器在运行时的主要微架构损耗源自 **操作码分派循环（Opcode Dispatch Loop）**。以最基础的基于 switch-case 的解释器为例，其物理分派逻辑如下：

.. code-block:: c

   typedef enum {
       OP_LOAD_CONST,
       OP_LOAD_LOCAL,
       OP_MUL,
       OP_ADD,
       OP_RETURN
   } Opcode;

   typedef struct {
       Opcode op;
       int operand;
   } Instruction;

   int interpret_eval(Instruction *code, int *locals, int *constants) {
       int stack[256];
       int sp = -1;
       int pc = 0;

       while (1) {
           Instruction instr = code[pc++];
           switch (instr.op) {
               case OP_LOAD_CONST:
                   stack[++sp] = constants[instr.operand];
                   break;
               case OP_LOAD_LOCAL:
                   stack[++sp] = locals[instr.operand];
                   break;
               case OP_MUL: {
                   int right = stack[sp--];
                   int left = stack[sp--];
                   stack[++sp] = left * right;
                   break;
               }
               case OP_ADD: {
                   int right = stack[sp--];
                   int left = stack[sp--];
                   stack[++sp] = left + right;
                   break;
               }
               case OP_RETURN:
                   return stack[sp--];
           }
       }
   }

在现代超标量 CPU 微架构中，上述 switch-case 语句会被 C 编译器降低为一个间接跳转表（Indirect Jump Table）：jmp *jump_table[%rax]。所有字节码指令共用同一个物理间接跳转指令地址。

这种共用跳转槽的设计引发了严重的 **分支目标缓冲器（Branch Target Buffer, BTB）别名污染**。当字节码序列为 LOAD_LOCAL -> LOAD_CONST -> MUL -> ADD 时，BTB 必须对同一个跳转指令连续预测不同的目标地址，导致硬件分支预测准确率大幅下滑。一次分支预测失败将迫使 CPU 流水线执行清空（Pipeline Flush），支付 15 至 20 个时钟周期的物理停顿惩罚。

直接穿透式分派（Direct Threaded Code）优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工业级解释器（如 CPython 3.12+、Lua 5.4、Dalvik）常利用 GCC/Clang 扩展的 **标签即值（Labels as Values, &&label）** 特性构建直接穿透式解释器：

.. code-block:: c

   int interpret_threaded(Instruction *code, int *locals, int *constants) {
       static const void *dispatch_table[] = {
           &&do_load_const,
           &&do_load_local,
           &&do_mul,
           &&do_add,
           &&do_return
       };

       int stack[256];
       int sp = -1;
       int pc = 0;

       #define DISPATCH() goto *dispatch_table[code[pc++].op]

       DISPATCH();

   do_load_const:
       stack[++sp] = constants[code[pc - 1].operand];
       DISPATCH();

   do_load_local:
       stack[++sp] = locals[code[pc - 1].operand];
       DISPATCH();

   do_mul: {
       int right = stack[sp--];
       int left = stack[sp--];
       stack[++sp] = left * right;
       DISPATCH();
   }

   do_add: {
       int right = stack[sp--];
       int left = stack[sp--];
       stack[++sp] = left + right;
       DISPATCH();
   }

   do_return:
       return stack[sp--];

       #undef DISPATCH
   }

直接穿透式代码将 DISPATCH() 宏展开并复制到每一个操作码处理例程（Handler）的末尾。在物理机器指令层面，每个 Handler 拥有独立的间接跳转指令 jmp *%rax。硬件 BTB 能够为每个 Handler 单独记录其下游的高频跳转目标（如 LOAD_LOCAL 之后大概率跟随 LOAD_CONST），有效隔离分支预测上下文，将指令分派的分支预测失败率降低 40% 至 70%。

栈式 VM 与 寄存器式 VM 的物理拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

字节码虚拟机的内部操作数组织方式直接决定了内存读写频次与指令分派总数：

.. list-table:: 栈式虚拟机与寄存器式虚拟机的物理拓扑与执行特征比对
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - 栈式虚拟机 (Stack-based VM)
     - 寄存器式虚拟机 (Register-based VM)
   * - 典型代表
     - CPython, JVM, WebAssembly, CLR
     - LuaJIT, Lua 5.x, Android Dalvik
   * - 指令编码形态
     - 零地址指令（操作数隐式源自操作数栈顶）
     - 二/三地址指令（显式指定虚拟寄存器编号）
   * - 算术表达式 a = b * 7 + 3 指令数
     - 6 条指令（LOAD_LOCAL, LOAD_CONST, MUL, LOAD_CONST, ADD, STORE_LOCAL）
     - 2 条指令（MUL R0, R_b, K0; ADD R_a, R0, K1）
   * - 字节码体积
     - 极紧凑（单指令 1~2 字节，利于缓存）
     - 较宽（单指令 4 字节，承载操作数索引）
   * - 分派循环总次数
     - 高（指令条数多，分派开销大）
     - 低（分派次数减少 30% 至 50%）
   * - 硬件寄存器映射难度
     - 极难（栈顶频繁变动，栈溢出与栈指针移动密集）
     - 容易（虚拟寄存器阵列可直接映射到物理寄存器）

AOT 编译范式：运行前成本全额支付与硬件直连生成
----------------------------------------------

提前编译（Ahead-of-Time Compilation, AOT）指在程序部署与实际执行前，完成从源码到目标机器物理二进制的全部翻译、优化与链接工作。

AOT 编译器的物理工作模型
~~~~~~~~~~~~~~~~~~~~~~~~

AOT 编译器（如 GCC、Clang/LLVM、Rustc、GHC）将计算资源集中在开发与构建阶段。对函数 int price(int count) { return count * 7 + 3; }，AOT 编译管线执行如下物理降级：

1. **AST 语义构建与类型固化**：确认 count 为 32 位有符号整数，确定运算符重载语义与边界行为。
2. **SSA IR 生成与代数化简**：构建显式控制流图，将算术表达式抽象为 %1 = mul nsw i32 %count, 7 与 %2 = add nsw i32 %1, 3。
3. **目标 ISA 强度折减（Strength Reduction）与寻址模式映射**：在 x86-64 目标机上，编译器识别出乘以 7 可分解为乘以 8 减去 1。结合 x86 独有的 SIB（Scale-Index-Base）复合寻址模式，编译器直接发射 lea 指令完成高效计算。
4. **寄存器分配与调用约定固化**：遵循 System V AMD64 ABI，输入参数 count 放置于 %edi 寄存器，返回值通过 %eax 寄存器传递。

.. code-block:: gas

   .globl price
   .type price, @function
   price:
       # %edi 存放入参 count
       leal (%rdi,%rdi,8), %eax   # %eax = count + count * 8 = count * 9 (若为 8 倍)
       # 针对 count * 7 + 3 的精准指令序列:
       leal (%rdi,%rdi,2), %eax   # %eax = count * 3
       leal 3(%rdi,%rax,2), %eax  # %eax = 3 + count + (count * 3) * 2 = 7 * count + 3
       ret

在上述生成的汇编指令中，乘法与加法被彻底融合成两条物理 lea 指令，零内存访问、零分派跳转、零类型检查，单次调用仅耗费 2 个时钟周期。

AOT 的物理收益与边界约束
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: AOT 编译策略的物理收益与工程约束矩阵
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 评估维度
     - 物理表现
     - 底层微架构原因
   * - 启动延迟 (Startup Time)
     - 零预热（Zero Warm-up）
     - 操作系统直接通过 mmap 将代码段映射为可执行物理内存页，无运行时编译暂停
   * - 稳态吞吐 (Peak Throughput)
     - 极高
     - 充分释放超标量流水线、SIMD 自动向量化与全局寄存器分配潜能
   * - 内存占用 (RSS Footprint)
     - 极小
     - 运行时无需驻留编译器前端、优化器、SSA IR 图节点与符号表
   * - 动态适应性 (Dynamic Adaptability)
     - 刚性
     - 无法获知运行时真实输入的数据分布，无法实施基于运行时单态类型假设的激进内联
   * - 构建开销 (Build Cost)
     - 显著
     - 全局分析与 LTO 链接优化占用数十秒至数小时的编译集群 CPU 与内存

Transpiler 范式：源码到源码映射与生态桥接转换
----------------------------------------------

转译器（Transpiler / Source-to-Source Compiler）的物理定义是：**接收高级源语言 $ 的语法与语义表示，输出等价的高级目标语言 $ 源码文本的编译系统。**

Transpiler 的核心职责是抹平平台运行时差异、消除高级语言语法糖、实施静态类型擦除（Type Erasure）或将领域专有语言（DSL）接入通用系统生态。

类型擦除与降级转换模型
~~~~~~~~~~~~~~~~~~~~~~

以 TypeScript 到 JavaScript 的转译器（tsc 或 esbuild）为例，转译器在构建时执行如下状态迁移：

.. code-block:: typescript

   // 源语言 TypeScript: 包含静态类型约束与类字段
   class PricingEngine {
       private baseTax: number = 3;

       public calculate(count: number): number {
           return count * 7 + this.baseTax;
       }
   }

.. code-block:: javascript

   // 目标语言 ECMAScript 5 (降级转译产物)
   var PricingEngine = /** @class */ (function () {
       function PricingEngine() {
           this.baseTax = 3;
       }
       PricingEngine.prototype.calculate = function (count) {
           return count * 7 + this.baseTax;
       }
       return PricingEngine;
   }());

在上述转译过程中：

1. **类型标记完全擦除**：: number 与访问修饰符 private/public 在目标代码中消失。静态检查的不变性在转译阶段由前端独立验证完毕。
2. **语法树结构降级**：ES6 class 结构被降级为 ES5 的闭包自执行函数（IIFE）与原型链（Prototype）挂载。
3. **运行时开销委托**：转译产物依然是文本源码，其词法分析、语法解析、JIT 编译及垃圾回收开销完全委托给下游的 JavaScript 引擎（如 V8、JavaScriptCore）。

Source Map 的物理拓扑与双向位置映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于 Transpiler 会重写变量名、合并多行表达式并注入 Helper 函数，运行时报错堆栈将与开发者的原始源码完全脱节。为此，Transpiler 必须生成 **Source Map 物理映射表**。

Source Map 利用 **变长数量（Variable-Length Quantity, VLQ）** 进行 Base64 紧凑编码，在磁盘上构建高密度的五元组空间索引映射：

.. code-block:: text

   (生成的行号, 生成的列号) ---> (源文件索引, 原始行号, 原始列号, 原始符号索引)

当运行时抛出未捕获异常时，调试工具通过解析 Source Map 逆向重构出原始调用栈帧行号，确保开发者心智模型与生成代码物理拓扑的双向解耦。

JIT 编译范式：运行时动态反馈、分层编译与自适应特化
--------------------------------------------------

即时编译（Just-In-Time Compilation, JIT）的物理定义是：**在宿主程序运行期间，实时监测代码执行热点，动态将高频执行的字节码或 IR 编译为宿主 CPU 物理机器指令并写入可执行内存页的混合执行系统。**

JIT 的核心物理优势在于拥有 **运行时动态反馈（Runtime Dynamic Feedback）**，能够获取静态编译器无法知晓的运行时事实（精确类型分布、分支走向概率、多态调用目标单态化）。

现代工业级 JIT 的分层编译流水线（Tiered Compilation）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以 V8 引擎（执行 JavaScript）与 HotSpot 虚拟机（执行 Java）为代表的现代 JIT 引擎普遍采用多层分层执行架构：

.. code-block:: text

   +----------------+
   |   Source Code  |
   +----------------+
           | (Fast Parse)
           v
   +----------------+     Cold (Tier 0)     +---------------------------+
   |    Bytecode    | --------------------> | Interpreter (Ignition/C0) |
   +----------------+                       +---------------------------+
           |                                              |
           | Invocation Counter >= Threshold 1            | Collect Type Feedback
           v                                              v (Inline Cache Vector)
   +------------------------------------+   Warm (Tier 1) +---------------------------+
   | Baseline JIT (Sparkplug / JVM C1)  | --------------> | Fast Machine Code Gen     |
   +------------------------------------+                 +---------------------------+
           |                                              |
           | Hot Loop / Counter >= Threshold 2            | Continuous Profiling
           v                                              v
   +------------------------------------+   Hot (Tier 2)  +---------------------------+
   | Optimizing JIT (TurboFan / JVM C2) | --------------> | Speculative Optimized Code|
   +------------------------------------+                 +---------------------------+
           |                                                            |
           + <--------------- [ Deoptimization / Bailout ] <------------+
                                (Guard Condition Failed)

1. **Tier 0（解释器层）**：
   程序启动时立即以解释模式执行，确保毫秒级冷启动响应。在解释执行的同时，解释器通过在每个函数调用点与循环回边处递增调用计数器（Invocation Counter / Backedge Counter），并向 **反馈向量（Feedback Vector）** 写入操作数类型分布。

2. **Tier 1（基线 JIT 编译器）**：
   当计数器超过第一级阈值时，触发基线编译。基线编译器直接线性遍历字节码，机械发射未优化的原生机器码，完全剔除解释器的分派循环与栈操作开销。

3. **Tier 2（激进优化 JIT 编译器）**：
   当函数成为高频热点（Hot Spot）时，触发优化编译。编译器将字节码升格为 SSA IR 图，利用前面收集的类型反馈实施 **推测性投机优化（Speculative Optimization）**：
   * **单态内联（Monomorphic Inlining）**：若反馈向量显示某虚方法调用点 99.9% 均为单一具体类，直接将目标方法代码内联展开，消除虚表查询（vtable lookup）。
   * **循环剥离与无保护算术（Unchecked Arithmetic）**：推测循环计数器始终处于 32 位整型安全区间，消除每次加法操作的溢出检查与动态类型装箱（Boxing）。

投机优化守护条件（Guard）与去优化（Deoptimization）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

推测性优化依赖于对未来的假设。一旦运行环境出现异常输入（例如传入了预期外的对象形态或浮点数），已优化的机器码将处于非法状态。为了维护语言规范定义的严格语义，JIT 必须在所有投机优化路径前插入 **守护检查（Guard）**。

当 Guard 判定失败时，JIT 触发 **去优化（Deoptimization / Bailout）**：

.. list-table:: 去优化（Bailout）的物理执行步骤与状态重建
   :widths: 15 35 50
   :header-rows: 1
   :class: tight-table

   * - 步骤编号
     - 物理操作
     - 微架构状态迁移细节
   * - 1. 捕获失败
     - 触发 Guard 失败分支
     - 条件跳转指令判定失败，执行流从优化机器码代码段跳转至 Deopt Handler 入口
   * - 2. 栈帧逆映射
     - 解析 Safepoint / Scope Map
     - 根据当前机器码指令偏移量，在预生成的元数据表中查找对应的字节码 PC 与变量位置映射
   * - 3. 栈帧物理重建
     - 释放机器码栈帧，构造 VM 栈帧
     - 从物理寄存器和物理栈槽中提取运行时变量值，在宿主内存中申请并填充解释器 Frame 结构体
   * - 4. 状态热迁移
     - 恢复虚拟 PC 与操作数栈
     - 将重建后的虚拟寄存器和操作数栈指针同步至解释器执行上下文
   * - 5. 降级执行
     - 恢复解释执行模式
     - 解释器从失败点对应的下一条字节码开始继续执行，并将反馈向量标记为多态（Polymorphic）

去优化保证了 JIT 编译器能够以极其激进的假设生成紧凑机器码，同时在数学上严格保持语言全量动态特性的语义正确性。

执行范式选型的多维工程权衡与成本收益模型
----------------------------------------

编译器工程中不存在万能的执行范式。选择特定的执行策略，本质是在硬件物理约束与业务工作负载之间做出精准的取舍平衡。

.. list-table:: 四大执行范式全维度工程指标对比矩阵
   :widths: 16 16 17 17 17 17
   :header-rows: 1
   :class: tight-table

   * - 工程指标
     - 解释执行
     - 静态 AOT 编译
     - 源码转译 (Transpiler)
     - 分层 JIT 编译
   * - 冷启动时间
     - 最低（毫秒级直接运行）
     - 极低（直接装载二进制）
     - 视下游工具链而定
     - 较低（先解释后编译）
   * - 稳态计算性能
     - 极低（受制于分派开销）
     - 最高（全局静态极限优化）
     - 视下游执行引擎而定
     - 极高（可超越纯静态编译）
   * - 运行时内存占用
     - 低（仅需维护 VM 状态）
     - 最低（仅保留运行时二进制）
     - 低（无额外编译器常驻）
     - 极高（需常驻 IR、JIT 编译线程与代码缓存）
   * - 跨平台部署成本
     - 极低（分发通用字节码）
     - 极高（需针对各 ISA 交叉编译）
     - 最低（分发通用源码）
     - 中等（需针对目标架构移植 JIT 后端）
   * - 平台安全约束
     - 完全兼容 W^X 安全策略
     - 完全兼容 W^X 安全策略
     - 完全兼容
     - 需动态申请可执行内存页（iOS 等平台受限）

现代工业级混合架构演进
~~~~~~~~~~~~~~~~~~~~~~

现代生产级执行引擎普遍跨越了单一范式的边界，演化为多策略深度融合的混合系统：

1. **CPython 3.13+ 的分层演进**：在保持标准字节码解释器的同时，引入自适应特化字节码（Specialized Adaptive Bytecode）与轻量级 Copy-and-Patch JIT，在零高昂编译开销前提下提升数值计算吞吐。
2. **WebAssembly 的双模部署**：既可以在浏览器端通过 V8/Liftoff 进行毫秒级 JIT 编译，也可以在服务端通过 Wasmtime / Lucet 进行全量 AOT 编译为原生 ELF 二进制。
3. **AI 图编译器的全栈贯通（如 PyTorch 2.0 Dynamo / Inductor）**：Python 源码首先在 CPython 解释器中运行；TorchDynamo 通过字节码分析拦截张量计算图；TorchInductor 将捕获的图 Lowering 到 C++/Triton 源码（Transpiler 行为）；最终调用 GCC/Clang 或 NVCC 进行 AOT 编译生成机器码共享库供运行时直接调用。

小结与下章导读
--------------

本章系统解构了现代编译器与运行时系统的四大执行范式及其物理微架构机理：

1. **成本转移法则**：执行范式的选择本质是编译分析成本在编译时、加载时与运行时之间的分配决策。
2. **微架构瓶颈差异**：解释器的瓶颈在于分支预测器与分派循环开销；AOT 的优势在于全额提前支付静态分析与硬件指令调度成本；JIT 的优势在于利用运行时反馈突破静态信息孤岛；Transpiler 专注于高层语义映射与生态桥接。
3. **动态特化与安全回退**：JIT 编译器通过 Inline Cache、Guard 守护与 Deoptimization 栈帧逆重构，在动态灵活性与物理执行效率之间达成了工程统一。

在下一章中，我们将深入剖析 **编译器工程契约：语义保持正确性、编译耗时/产物性能取舍与诊断调试信息保留（05_compiler_correctness_performance_and_developer_experience.rst）**，系统探讨工业级编译器在正确性验证、未定义行为利用、编译时与运行时平衡以及 DWARF 调试元数据生成中的工程契约与权衡体系。
