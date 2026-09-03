================================================================================
编译作为表示流转序列：Token、AST、High-Level IR、Low-Level IR 到 Machine IR 的抽象降级与信息守恒
================================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解析了源码作为结构化系统的物理本质，阐明了字符流、词法 Token、抽象语法树以及未定义行为（UB）为中端优化提供的代数公理基础，并揭示了 DWARF 调试元数据对机器物理状态的逆向重构机理。本章推进至编译器系统内部的核心中枢——**多层表示流转序列（Sequence of Representations）**。我们将系统剖析程序语义如何在 Token 流、抽象语法树（AST）、高层中间表示（High-Level IR）、中层静态单赋值表示（SSA Mid-Level IR）、目标机中间表示（Machine IR）直到最终二进制目标文件（Object File）之间实施受控的抽象降级（Lowering），并揭示各阶段在信息剥离与约束注入过程中的物理规律。

现代编译器的物理本质是一个多阶段表示转换引擎。源码文本并非直接映射为机器指令，而是沿着一条定义严格的表示流转管线逐步降解。每一层中间表示（Intermediate Representation, IR）均采用专门设计的数据结构，精确承载当前分析与变换所需的语义事实，剥离当前阶段的无关细节，并引入下一阶段所需的物理硬件或执行环境约束。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                            现代编译器多层表示流转与抽象降级拓扑全景                                |
   +---------------------------------------------------------------------------------------------------+
     源文件字符流 (Source Stream)
       |
       | [词法分析 (Lexer)] -> 有限状态机匹配、字符切分、位置编码
       v
     Token 序列 (Token Vector)
       |
       | [语法分析 (Parser)] -> 产生式归约、操作符结合性固化、作用域绑定
       v
     抽象语法树 (Clang AST / Rust HIR)
       |
       | [高层语义降低 (High-Level Lowering)] -> 所有权分析、多态单态化、结构化控制流平坦化
       v
     高层中间表示 (Swift SIL / Rust MIR / MLIR Dialects)
       |
       | [中端 IR 生成与 Mem2Reg] -> 栈槽变量提升、SSA 构造、支配边界计算
       v
     中层 SSA IR (LLVM IR / GCC GIMPLE)
       |
       | [指令选择 (ISel) 与 DAG 重写] -> 树形模式匹配、操作码目标化、虚拟寄存器分配
       v
     目标机中间表示 (Machine IR / MIR)
       |
       | [寄存器分配 (RegAlloc) 与序言插入] -> 活跃区间分析、物理寄存器着色、栈帧布局
       v
     物理机器指令流 (MC Layer / Assembler)
       |
       | [目标文件发射 (Object Emitter)] -> ELF 节区编码、重定位项生成、DWARF 符号注入
       v
     可重定位二进制目标文件 (ELF / Mach-O / PE Object File)

贯穿剖析案例定义
----------------

为了精确追踪程序在整套编译管线中的表示演进，本章采用如下包含循环累加、数组内存读取与常量乘法的经典 C 函数作为贯穿分析对象：

.. code-block:: c

   unsigned int scale_sum(const unsigned int *arr, unsigned int len, unsigned int factor) {
       unsigned int acc = 0;
       for (unsigned int i = 0; i < len; ++i) {
           acc += arr[i] * factor;
       }
       return acc;
   }

该函数具备编译管线分析的完整要素：指针参数与数组内存解引用（Load 指令）、循环控制流拓扑（循环头、循环体、回边与退出块）、归纳变量（Induction Variable ``i``）、累加值状态转移（``acc``）以及算术乘加运算。

前端表示层：Token 序列与抽象语法树（AST）的语法固化
---------------------------------------------------

编译器前端的职责是将线性、无结构的源文件文本转换为具备严格语法层次与作用域关联的内存树形拓扑。

Token 流的物理组织与信息截断
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

词法分析器通过扫描内存映射的源文件缓冲区，将字符流聚类为离散的 Token 结构体。在物理内存中，Token 序列通常以连续的数组（如 ``std::vector<Token>`` 或连续内存池）形式存储，以确保高速缓存行（Cache Line）预取效率：

.. code-block:: cpp

   struct Token {
       TokenKind kind;           // 词法单元类别枚举 (uint16_t)
       uint16_t flags;           // 词法属性标志位（如是否紧随空白符）
       SourceLocation location;  // 源码文件、行、列及绝对字节偏移 (8-16 bytes)
       const char* data_ptr;     // 指向源文件缓冲区的字符指针或符号表条目
       uint32_t length;          // 词素长度
   };

当扫描语句 ``acc += arr[i] * factor;`` 时，词法分析器生成如下有序 Token 序列：

.. code-block:: text

   [IDENT: "acc"] [PLUS_EQUAL: "+="] [IDENT: "arr"] [L_SQUARE: "["] 
   [IDENT: "i"]   [R_SQUARE: "]"]   [STAR: "*"]    [IDENT: "factor"] [SEMI: ";"]

在这一层表示中，源码中的缩进、空格与注释已被完全剥离。Token 流保留了词素类型、词面值以及用于错误诊断的物理源码坐标，但尚未建立任何语法从属关系或运算结合顺序。

AST 的节点拓扑与引用网格
~~~~~~~~~~~~~~~~~~~~~~~~

语法分析器读取 Token 序列，根据语言形式文法将其组装为抽象语法树（AST）。AST 在编译器堆内存中由专用的内存池分配器（如 LLVM 的 ``BumpPtrAllocator``）统一管理，节点之间通过原始指针对接。

.. code-block:: text

   FunctionDecl: scale_sum (Type: unsigned int (const unsigned int *, unsigned int, unsigned int))
   |-- ParmVarDecl: arr (Type: const unsigned int *)
   |-- ParmVarDecl: len (Type: unsigned int)
   |-- ParmVarDecl: factor (Type: unsigned int)
   `-- CompoundStmt
       |-- DeclStmt
       |   `-- VarDecl: acc (Type: unsigned int, Init: 0)
       |-- ForStmt
       |   |-- DeclStmt
       |   |   `-- VarDecl: i (Type: unsigned int, Init: 0)
       |   |-- BinaryOperator: < (Type: bool)
       |   |   |-- ImplicitCastExpr: LValueToRValue -> unsigned int
       |   |   |   `-- DeclRefExpr: i -> ParmVarDecl(i)
       |   |   `-- ImplicitCastExpr: LValueToRValue -> unsigned int
       |   |       `-- DeclRefExpr: len -> ParmVarDecl(len)
       |   |-- UnaryOperator: ++ (Prefix)
       |   |   `-- DeclRefExpr: i -> ParmVarDecl(i)
       |   `-- CompoundStmt
       |       `-- CompoundAssignOperator: += (Type: unsigned int)
       |           |-- DeclRefExpr: acc -> VarDecl(acc)
       |           `-- BinaryOperator: * (Type: unsigned int)
       |               |-- ImplicitCastExpr: LValueToRValue -> unsigned int
       |               |   `-- ArraySubscriptExpr (Type: const unsigned int)
       |               |       |-- ImplicitCastExpr: ArrayToPointerDecay
       |               |       |   `-- DeclRefExpr: arr -> ParmVarDecl(arr)
       |               |       `-- ImplicitCastExpr: LValueToRValue
       |               |           `-- DeclRefExpr: i -> VarDecl(i)
       |               `-- ImplicitCastExpr: LValueToRValue -> unsigned int
       |                   `-- DeclRefExpr: factor -> ParmVarDecl(factor)
       `-- ReturnStmt
           `-- ImplicitCastExpr: LValueToRValue -> unsigned int
               `-- DeclRefExpr: acc -> VarDecl(acc)

在 AST 节点拓扑中：

1. **结构语法固化**：操作符优先级通过树的分支深度予以确定。乘法节点位于加法赋值节点的子树深处，确保了求值先后的拓扑结构。
2. **符号与类型解析**：每个 ``DeclRefExpr``（声明引用表达式）均包含一个指向对应 ``VarDecl`` 或 ``ParmVarDecl`` 内存地址的直接指针，完成变量名字决议。
3. **类型转换显式化**：隐式类型转换（如左值到右值的加载转换 ``LValueToRValue``、数组名退化为指针 ``ArrayToPointerDecay``）在 AST 中被实例化为显式包装节点。

AST 保留了高层语言的完整类型签名、语义结构与源文件映射，适合用于静态类型检查、语义分析、代码重构与 IDE 语言服务。由于 AST 依然维持嵌套的树状结构，控制流分支隐藏于语法节点语义内部（例如 ``ForStmt`` 隐含了循环初始化、条件判断、步进迭代与循环体的流转逻辑），中端优化器难以在 AST 上直接执行全局数据流分析、支配树构建与指令重排。

高层与中层中间表示：SSA 形式与控制流图（CFG）
----------------------------------------------

为了支持高效的机器无关优化，编译器将树状 AST 转换为基于控制流图（CFG）与静态单赋值（SSA）形式的中端中间表示。

高层 IR（High-Level IR）的领域特化语义承载
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代多层编译器（如 Rust、Swift、MLIR）中，AST 在进入低层平坦 IR 之前，首先降级为保留特定语言高层语义的高层 IR：

* **Swift SIL（Swift Intermediate Language）**：保留引用计数操作、虚函数表查找、泛型签名与确定性初始化（Definite Initialization）事实。
* **Rust MIR（Mid-level Intermediate Representation）**：基于控制流图表达借用检查（Borrow Checker）、生命周期推导（Lifetimes）与析构清理（Drop Flags）逻辑。
* **MLIR Affine / Linalg Dialects**：显式保留多维多面体循环嵌套边界（Polyhedral Loop Bounds）与张量结构，便于直接实施循环分块（Tiling）与算子融合（Operator Fusion）。

平坦化控制流图（CFG）与基本块拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

中端编译管线将 AST 中的嵌套控制结构展开为平坦的有向控制流图（Control Flow Graph, CFG）。CFG 的基础构建单元是 **基本块（Basic Block）**。基本块是一段连续执行的指令序列，严格满足单入口（Single Entry）与单出口（Single Exit）物理约束：程序控制流只能从第一条指令进入，并只能由最后一条终止指令（Terminator Instruction）离开。

贯穿示例中的 ``ForStmt`` 结构在控制流图中被展开为 4 个互联的基本块：

.. code-block:: text

   +-------------------------------------------------------------+
   | entry:                                                      |
   |   %acc.0 = 0                                                |
   |   %i.0 = 0                                                  |
   |   br label %for.cond                                        |
   +-------------------------------------------------------------+
                               |
                               v
   +-------------------------------------------------------------+
   | for.cond:                                                   |
   |   %cmp = icmp ult i32 %i, %len                              |
   |   br i1 %cmp, label %for.body, label %for.end               |
   +-------------------------------------------------------------+
             |                                       |
       (true) |                                       | (false)
             v                                       v
   +---------------------------------------+   +-----------------+
   | for.body:                             |   | for.end:        |
   |   %elem.ptr = getelementptr ...       |   |   ret i32 %acc  |
   |   %elem = load i32, %elem.ptr         |   +-----------------+
   |   %prod = mul i32 %elem, %factor      |
   |   %acc.next = add i32 %acc, %prod     |
   |   %i.next = add i32 %i, 1             |
   |   br label %for.cond                  |
   +---------------------------------------+

SSA 形式下的值标识与 Use-Def 链
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在标准 C 源码中，变量 ``acc`` 和 ``i`` 在循环迭代过程中被反复覆写。在 SSA 形式（以 LLVM IR 为例）下，每一个变量槽位被拆解为全局唯一的不可变数值定义（Value Definition）。

当多个控制流分支汇聚至同一基本块时，编译器通过插入 **$\phi$ 节点（Phi Node）** 实施动态数据流合并：

.. code-block:: llvm

   define i32 @scale_sum(ptr nocapture readonly %arr, i32 %len, i32 %factor) local_unnamed_addr {
   entry:
     %cmp.not6 = icmp eq i32 %len, 0
     br i1 %cmp.not6, label %for.cond.cleanup, label %for.body.preheader

   for.body.preheader:                               ; 前置头块，提供循环外不变量准备
     br label %for.body

   for.cond.cleanup:                                 ; 循环退出块
     %acc.0.lcssa = phi i32 [ 0, %entry ], [ %add, %for.body ]
     ret i32 %acc.0.lcssa

   for.body:                                         ; 核心循环体
     %i.08 = phi i32 [ %inc, %for.body ], [ 0, %for.body.preheader ]
     %acc.07 = phi i32 [ %add, %for.body ], [ 0, %for.body.preheader ]
     %idxprom = zext i32 %i.08 to i64
     %arrayidx = getelementptr inbounds i32, ptr %arr, i64 %idxprom
     %0 = load i32, ptr %arrayidx, align 4
     %mul = mul i32 %0, %factor
     %add = add i32 %mul, %acc.07
     %inc = add nuw i32 %i.08, 1
     %exitcond.not = icmp eq i32 %inc, %len
     br i1 %exitcond.not, label %for.cond.cleanup, label %for.body
   }

SSA 形式的核心物理价值体现在：

1. **明确的值依赖关系**：每个 SSA 值（如 ``%mul``）拥有唯一定义它的指令节点。指令与操作数之间建立双向指针链接：``llvm::Instruction`` 继承自 ``llvm::User``，其内部维护指向被使用值（``llvm::Value``）的 ``Use`` 数组，同时每个 ``llvm::Value`` 维护反向的 ``use_iterator`` 链表。
2. **优化的线性时间复杂度**：死代码消除（DCE）、稀疏条件常量传播（SCCP）与公共子表达式消除（CSE）能够直接沿 Use-Def 链跳跃遍历，无需构建昂贵且低效的内存别名迭代数据流格。

后端抽象与目标机中间表示（Machine IR）：从虚拟寄存器到硬件约束
--------------------------------------------------------------

中端 SSA IR 依然假定存在无限数量的虚拟寄存器，且指令操作码为目标平台无关的抽象算子（如 ``add``、``mul``、``load``）。当进入编译器后端时，代码生成器（CodeGen）必须将这些抽象算子逐步映射至受限的物理硬件。

指令选择（Instruction Selection）与 DAG 降级
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

指令选择阶段将平台无关的 IR 降解为目标处理器的机器指令拓扑。在 LLVM 体系中，该过程通过 **SelectionDAG**（基于有向无环图的模式匹配）或 **GlobalISel**（全局指令选择管线）完成：

1. **基本块图化**：将线性 IR 指令展开为表达数据依赖（Data Flow Edge）与执行次序约束（Glue / Chain 依赖边）的 DAG 图。
2. **类型合法化（Legalization）**：将目标硬件不支持的数据类型（如 128 位整型在 32 位 CPU 上）拆解为合法位宽的运算序列。
3. **节点模式覆盖（Pattern Matching & Emitting）**：利用目标机器描述文件（TableGen 规则库），将 DAG 中的节点聚类匹配为单条物理机器指令。例如，连续的乘法与加法节点在支持 FMA/MAD 扩展的硬件上直接折叠为单条乘加指令；数组指针偏移计算 ``getelementptr`` 与 ``load`` 在 x86 目标上直接折叠为基址变址寻址（Base-Index-Scale-Disp）。

Machine IR（MIR）数据结构
~~~~~~~~~~~~~~~~~~~~~~~~~

指令选择完成后，程序被表示为特定目标架构下的 Machine IR。在 LLVM 后端中，这体现为由 ``MachineFunction``、``MachineBasicBlock``、``MachineInstr`` 和 ``MachineOperand`` 构成的树状双向链表：

.. code-block:: text

   MachineFunction: scale_sum (Target: x86_64-unknown-linux-gnu)
     MachineBasicBlock #0 (%bb.0) [entry]:
       successors: %bb.2(0x30000000), %bb.1(0x50000000)
       TEST32rr %esi, %esi, implicit-def $eflags
       JE_1 %bb.2, implicit $eflags
     
     MachineBasicBlock #1 (%bb.1) [for.body]:
       predecessors: %bb.0, %bb.1
       successors: %bb.2(0x04000000), %bb.1(0x7c000000)
       ; 此时处于虚拟寄存器表示态
       %0:gr32 = PHI %1:gr32, %bb.1, 0, %bb.0
       %2:gr32 = PHI %3:gr32, %bb.1, 0, %bb.0
       %4:gr64 = SUBREG_TO_REG 0, %2:gr32, %subreg.sub_32bit
       %5:gr32 = MOV32rm %rdi, 4, %4:gr64, 0, $noreg :: (load (s32) from %ir.arrayidx)
       %6:gr32 = IMUL32rr %5:gr32, %edx, implicit-def dead $eflags
       %1:gr32 = ADD32rr %0:gr32, %6:gr32, implicit-def dead $eflags
       %3:gr32 = ADD32ri8 %2:gr32, 1, implicit-def $eflags
       CMP32rr %3:gr32, %esi, implicit-def $eflags
       JNE_1 %bb.1, implicit $eflags

此时的 MIR 具有如下物理特征：

* 指令操作码已转为目标 CPU 的真实微架构指令（如 ``MOV32rm``、``IMUL32rr``、``TEST32rr``）。
* 操作数（``MachineOperand``）处于虚拟寄存器（``%0:gr32``）与物理寄存器（``$rdi``、``$esi``、``$edx``，用于承载 ABI 传入参数）的混合状态。
* 明确记录了底层硬件标志位（``$eflags``）的隐式定义与隐式消费关系。

寄存器分配、栈帧布局与物理机器码发射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Machine IR 随后经历核心的物理约束施加阶段：

1. **活跃区间分析（Liveness Analysis）**：计算每个虚拟寄存器从首次定义到最后一次消费之间的指令区间，构建寄存器冲突图（Interference Graph）。
2. **寄存器分配（Register Allocation）**：运行图着色算法（Chaitin-Briggs）或贪心线性扫描算法，将虚拟寄存器映射至目标架构有限的物理通用寄存器集合（x86-64 的 RAX、RCX、RDX、RBX、R8-R15 等）。无法分配物理寄存器的值被生成溢出代码（Spill Code），写入栈帧内存。
3. **函数序言与尾声插入（Prologue/Epilogue Insertion, PEI）**：计算最终函数所需的栈空间大小，生成调整栈指针（``sub rsp, N``）、保护被调用者保存寄存器（``push rbx``）与返回恢复（``pop rbx; ret``）的物理指令序列。

最终发射的 x86-64 目标汇编代码如下：

.. code-block:: nasm

   .globl  scale_sum
   .type   scale_sum,@function
   scale_sum:
       .cfi_startproc
       ; 参数分发：RDI = arr, ESI = len, EDX = factor
       test    esi, esi                ; 检查 len 是否为 0
       je      .LBB0_3                 ; 若为 0 直接跳转至退出点
       
       ; 循环初始化：EAX 承载累加值 acc，ECX 承载循环变量 i
       xor     eax, eax                ; acc = 0
       xor     ecx, ecx                ; i = 0
   .LBB0_2:                            ; 循环体核心
       ; 利用基址变址寻址直接完成加载，并执行乘法
       mov     r8d, dword ptr [rdi + 4*rcx]
       imul    r8d, edx
       add     eax, r8d                ; acc += (arr[i] * factor)
       inc     rcx                     ; ++i
       cmp     esi, ecx                ; 比较 i 与 len
       jne     .LBB0_2                 ; 若未达到边界则继续循环
       ret
   .LBB0_3:
       xor     eax, eax                ; 返回 0
       ret
       .cfi_endproc

表示流转中的信息守恒与抽象降级矩阵
----------------------------------

在整套编译管线中，程序形态发生了深刻的物理重组。理解编译器架构的核心在于把握 **“每一层表示保留了什么、丢弃了什么、增加了什么约束”**。

.. list-table:: 编译器多层中间表示流转全景对照矩阵
   :widths: 14 18 24 22 22
   :header-rows: 1
   :class: tight-table

   * - 表示层级 (Representation)
     - 核心物理内存数据结构
     - 保留的核心语义事实
     - 剥离/丢弃的表层信息
     - 注入的系统/硬件约束
   * - Token Stream
     - 连续紧凑结构体数组 (Token Vector)
     - 词法类别 (TokenKind)、词素文本指针、源码坐标 (SourceLocation)
     - 源码排版缩进、注释、无意义空白字符
     - 词法规则与字符编码边界
   * - AST (抽象语法树)
     - 异构节点指针树 (Arena-Allocated AST Nodes)
     - 语言完整类型定义、声明引用绑定关系、嵌套语法范围
     - 具体语法括号、分隔符语法糖、宏展开前原始标记
     - 语言规范类型系统、作用域可见性规则
   * - High-Level IR (SIL/MIR/MLIR)
     - 领域特化图/区域结构 (Regions, Blocks, Ops)
     - 高级语言专有语义（借用生命周期、泛型字典、多维张量维度）
     - 源码语法表面结构、格式化声明层次
     - 语言特化资源管理约束（RAII、确定性释放）
   * - Mid-Level SSA IR (LLVM IR)
     - 基本块图与双向 Use-Def 链表网格 (LLVM Module)
     - 显式控制流拓扑 (CFG)、数值计算依赖、明确数据位宽、内存指针解引用
     - 变量源码名称、局部变量栈槽形态、隐式控制结构
     - 静态单赋值约束 (SSA Invariant)、内存抽象模型、严格类型位宽
   * - Machine IR (MIR)
     - 指令/操作数拓扑双向链表 (MachineFunction)
     - 目标机器操作码、虚拟寄存器依赖、底层硬件状态标志位 (Flags)
     - 平台无关抽象算子、SSA 唯一赋值属性（寄存器分配后）
     - 目标 ISA 操作码集合、寻址模式限制、调用约定参数寄存器分发
   * - Object Binary (ELF)
     - 二进制字节段与重定位表 (ELF Sections & Relocations)
     - 机器可执行字节码、导出全局符号、重定位偏移量、DWARF 调试映射表
     - 编译器中端分析元数据、虚拟寄存器与临时 Pass 状态
     - 操作系统装载规范、ABI 二进制接口、内存对齐与段加载权限 (R/W/X)

抽象降级（Lowering）的工程必要性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译系统设计选择多层表示连续降级，其工程根基在于控制系统复杂度：

1. **避免维度爆炸（$M 	imes N$ 问题）**：若从前端 AST 直接生成物理机器码，支持 $M$ 种高级语言与 $N$ 种目标硬件需要编写 $M 	imes N$ 个独立转换器。引入统一的 Mid-Level SSA IR 后，编译器架构解耦为 $M$ 个前端与 $N$ 个后端，系统复杂度降低为 $M + N$。
2. **优化关注点分离（Separation of Concerns）**：
   * 在 AST 层实施重命名与类型推导；
   * 在 High-Level IR 层实施泛型特化与生命周期验证；
   * 在 Mid-Level SSA IR 层实施死代码消除、内联、自动向量化与循环展开；
   * 在 Machine IR 层实施针对流水线冒险的指令调度与物理寄存器着色。
   每个优化 Pass 仅针对最适合其拓扑结构的数据模型编码，大幅提升了算法稳定性与执行效率。

小结与下章导读
--------------

本章系统剖析了现代编译器在多层表示流转序列中的抽象降级机制：

1. **表示序列演进**：程序从字符流出发，依次经历 Token 序列的词法切分、AST 的语法结构固化、High-Level IR 的领域语义建模、Mid-Level SSA IR 的数据流与控制流解耦、Machine IR 的硬件约束适配，最终编码为 ELF 二进制目标文件。
2. **信息守恒与约束注入**：每一层表示均是有损转换（剥离上层语法细节）与有增转换（引入底层硬件与 ABI 执行约束）的结合体，语义保持不变量是串联整套管线的数学核心。
3. **数据结构适配**：编译器的核心理解能力完全内嵌于其当前维护的数据结构之中（Token 数组、AST 指针图、SSA Use-Def 网格、MachineInstr 链表）。

在下一章中，我们将深入探讨 **执行范式全景：解释器、AOT 编译、Transpiler 与 JIT 动态反馈的成本支付阶段权衡（04_interpreter_compiler_transpiler_and_jit.rst）**，系统分析不同执行引擎在编译时（Compile-Time）、加载时（Load-Time）与运行时（Runtime）之间的成本转移规律与架构选型物理法则。
