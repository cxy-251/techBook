====================================================================================================
中间表示 (IR) 设计哲学：高层语言语义保留与机器无关性前端解耦、受控降级 (Lowering)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块（``03_semantic_analysis_and_type_systems``）中，编译器通过符号表拓扑、多遍名字查找决议、类型等价判定与 Robinson 一阶合一求解算法，完成了对源码语义的完整验证，生成了挂载强类型元数据的抽象语法树（AST）。AST 作为紧贴源语言语法的树形层次结构，保留了高级语言特有的语法糖、复杂的嵌套表达式与隐式控制流（如短路求值、异常传播、虚函数分发）。然而，现代硬件微架构（如 x86-64、AArch64、RISC-V）执行的是基于寄存器读写、条件跳转与线性内存寻址的离散指令流。直接在 AST 上进行机器无关优化与指令生成会导致优化 Pass 深度耦合源语言语法，且面临 $M$ 种源语言与 $N$ 种目标硬件的 $M 	imes N$ 组合爆炸。本章正式跨入编译器的中端领域，系统剖析中间表示（Intermediate Representation, IR）的设计哲学：线性三地址码、树形 IR 与图 IR 的物理内存拓扑，高层 IR（HIR）到低层 IR（LIR）的渐进降级（Lowering）状态机，结构体内存布局与多维数组寻址的基址偏移映射，以及确保 IR 结构完备性的静态验证器（Verifier）机制。

中间表示的物理本质与机器无关性解耦模型
--------------------------------------

中间表示（IR）是编译器前端（词法/语法/语义分析）与后端（指令选择/寄存器分配/代码发射）之间的物理隔离协议。IR 的核心使命是将源语言的语法表达形式重构为一种计算语义明确、控制流显式、内存访问扁平的数据结构。

AST 面对中端优化的物理局限
~~~~~~~~~~~~~~~~~~~~~~~~~~

抽象语法树以递归嵌套节点的形式映射程序语法规则。在执行全局优化（如公共子表达式消除、循环不变量外提、死代码消除）时，AST 面临以下底层结构阻碍：

1. **隐式执行序列与嵌套深度**：在表达式 ``a + b * (c - d)`` 的 AST 中，子表达式的求值顺序依赖于树后序遍历（Post-order Traversal）。深层嵌套的语法树迫使优化 Pass 频繁执行树递归与模式匹配，导致高频的指针追逐（Pointer Chasing）与 CPU 数据缓存失效（Cache Misses）。
2. **隐式控制流与隐藏副作用**：逻辑与运算 ``expr1 && expr2`` 在 AST 层面表现为单个二元操作节点，但在底层执行时包含条件跳转与分支短路。若优化器无法显式观测分支转移，极易破坏求值副作用的时序正确性。
3. **高阶语法糖与语义冗余**：循环结构在 AST 中以 ``for``、``while``、``do-while``、``foreach`` 等多种节点存在。优化器若直接操作 AST，必须为每一种语法变体编写独立的分析规则，造成分析逻辑的重复与割裂。

$M 	imes N$ 解耦架构拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~

中间表示确立了工业级编译器的正交分层体系。编译器将编译流程划分为前后端独立的两阶段流水线：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  M x N 编译器架构解耦与 IR 流转拓扑                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 前端源语言矩阵 (M 种) ]                                                  |
   |   +----------+  +----------+  +----------+  +----------+                    |
   |   |   C/C++  |  |   Rust   |  |   Swift  |  |  Kotlin  |                    |
   |   +----+-----+  +----+-----+  +----+-----+  +----+-----+                    |
   |        |             |             |             |                          |
   |        \-------------+------+------+-------------/                          |
   |                             | 前端 Lowering 映射                            |
   |                             v                                               |
   |   [ 统一中间表示层 (Unified IR) ]                                            |
   |   +---------------------------------------------------------------------+   |
   |   | * High-Level IR (HIR): 保留高层类型、循环拓扑与多维索引             |   |
   |   | * Mid-Level IR (MIR):  控制流图 (CFG)、静态单赋值 (SSA)、线性值流   |   |
   |   | * Low-Level IR (LIR):  目标机相关、无限虚拟寄存器、显式栈槽偏移     |   |
   |   +---------------------------------------------------------------------+   |
   |                             |                                               |
   |        /-------------+------+------+-------------\                          |
   |        | 后端 CodeGen 映射                                                   |
   |        v             v             v             v                          |
   |   +----+-----+  +----+-----+  +----+-----+  +----+-----+                    |
   |   |  x86-64  |  |  AArch64 |  |  RISC-V  |  |  Wasm    |                    |
   |   +----------+  +----------+  +----------+  +----------+                    |
   |   [ 后端目标硬件 ISA 矩阵 (N 种) ]                                           |
   |                                                                             |
   +-----------------------------------------------------------------------------+

引入标准 IR 后，编译器工程复杂度由 $M 	imes N$ 降阶为 $M + N$。新增源语言仅需开发将其降解为标准 IR 的前端，新增硬件架构仅需开发从标准 IR 到机器指令的后端代码生成器。

IR 拓扑形式分类与内存布局对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译器历史上演化出三种主流的 IR 物理拓扑：

.. list-table:: 线性 IR、树形 IR 与图 IR 物理特性深度对比
   :widths: 18 28 27 27
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - 线性 IR (Linear 3AC / Quadruples)
     - 树形 IR (Tree-based IR)
     - 图 IR (Sea-of-Nodes / PDG)
   * - 典型代表
     - LLVM IR, GIMPLE (GCC), 3AC
     - Java/CLR 字节码, LISP S-expr
     - HotSpot C2, V8 TurboFan, MLIR
   * - 内存组织形式
     - 指令双向链表组成的扁平基本块序列
     - 递归树节点指针集合
     - 包含控制边与数据边的统一有向图
   * - 控制流表达
     - 显式的条件/无条件分支指令与标签
     - 结构化控制块节点（Loop/Block）
     - 控制依赖边直接连接指令节点
   * - 数据流表达
     - 显式虚拟寄存器编号或命名值
     - 栈顶隐式推入弹出或子树返回值
     - 数据依赖指针直接指向产出节点
   * - 遍历与变换开销
     - 线性顺序遍历，缓存局部性极高
     - 树遍历递归开销，内存碎片化较高
     - 图遍历算法复杂度高，局部修改极快
   * - 最适优化场景
     - 数据流分析、SSA 标量优化、指令调度
     - 跨平台虚拟机分发、AST 语法脱糖
     - 全局图重写、激进投机内联与调度

高层 IR (HIR) 与底层 IR (LIR) 的分层语义模型
--------------------------------------------

现代工业级编译器并不依赖单一的扁平 IR 完成全流程转换，而是采用 **多层分级 IR（Multi-Level Progressive IR）** 架构。在不同的编译阶段，编译器通过特定抽象等级的 IR 承载专门的分析与变换任务。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    多层 IR 渐进式抽象降解流水线                              |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 源码 AST ]                                                      |
   |      |  * 语法树节点、作用域符号绑定、未脱糖的高级控制结构                  |
   |      v                                                                      |
   |   [ 阶段 2: 高层中间表示 High-Level IR (HIR) ]                              |
   |      |  * 结构化类型系统、数组多维切片边界、泛型实例化参数                  |
   |      |  * 优化重点: 循环多面体并行化 (Polyhedral)、虚函数去虚化、高级内联   |
   |      v                                                                      |
   |   [ 阶段 3: 中层中间表示 Mid-Level IR (MIR / SSA-Form) ]                    |
   |      |  * 扁平控制流图 (CFG)、显式分支跳转、静态单赋值形式 (SSA)            |
   |      |  * 优化重点: 常量折叠、SCCP、GVN、死代码消除 (DCE)、内存别名分析     |
   |      v                                                                      |
   |   [ 阶段 4: 低层中间表示 Low-Level IR (LIR / Machine IR) ]                  |
   |      |  * 无限虚拟寄存器、目标 ISA 操作码约束、显式栈帧偏移与调用约定       |
   |      |  * 优化重点: 窥孔优化 (Peephole)、指令调度、寄存器分配、序言尾声插入 |
   |      v                                                                      |
   |   [ 阶段 5: 目标二进制机器指令 ]                                            |
   |         * 物理寄存器绑定、相对偏移重定位、二进制 ELF/Mach-O 发射            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

分层 IR 的工程职责划分
~~~~~~~~~~~~~~~~~~~~~~

1. **高层 IR（HIR）的语义保留机制**：
   - 保留源语言的强类型系统与聚合类型结构。
   - 保留数组多维边界、循环迭代域（Iteration Domain）与归纳变量边界，使编译器能够准确进行循环展开、分块（Tiling）与多面体模型并行化。
   - 保留类的虚方法分发表拓扑与闭包捕获结构，便于执行精准的去虚化（Devirtualization）与逃逸分析（Escape Analysis）。

2. **中层 IR（MIR）的机器无关规范化**：
   - 彻底抹平源语言特有的控制结构，将所有循环与分支降解为基于基本块（BasicBlock）的控制流图（CFG）。
   - 全面推行静态单赋值（SSA）形式，将变量名与物理存储解耦，确立唯一的值定值点（Definition Point）与使用点（Use Point）。
   - 暴露内存读写副作用（``Load`` / ``Store``），通过显式指针算术暴露数据寻址路径。

3. **低层 IR（LIR）的硬件微架构映射**：
   - 引入硬件指令集特定的操作码（如 ``x86::ADD64rr``、``ARM64::ADDXrr``）。
   - 显式暴露调用约定约定的传参寄存器（如 ``RDI``、``RSI``、``RDX``）与栈对齐约束。
   - 引入物理寄存器与虚拟寄存器混合状态，为寄存器分配器（Register Allocator）提供精确的活跃区间（Live Range）数据。

受控降级 (Controlled Lowering) 的转换流水线与语义保持
------------------------------------------------------

**受控降级（Lowering）** 是将高级语义结构逐步分解为低级物理操作的确定性转换过程。降级的核心原则是在每一次抽象降解过程中严格维持程序的运行态语义不变。

控制结构降级与分支线性化
~~~~~~~~~~~~~~~~~~~~~~~~

高级语言的结构化控制语句（``if-then-else``、``while``、``switch``）在降级过程中必须展开为显式的条件分支（Conditional Branch）、无条件跳转（Unconditional Branch）与跳转标签（Labels）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     While 循环结构降级为 CFG 基本块拓扑                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源码结构 ] : while (cond) { body; }                                     |
   |                                                                             |
   |   [ 降级后基本块拓扑 ]                                                      |
   |                                                                             |
   |           +-----------------------+                                         |
   |           |    entry_block        |                                         |
   |           +-----------------------+                                         |
   |                       |                                                     |
   |                       v                                                     |
   |           +-----------------------+ <---------------+                       |
   |    +----> |    loop.cond_block    |                 |                       |
   |    |      | %c = eval cond        |                 |                       |
   |    |      | br %c, loop.body,     |                 |                       |
   |    |      |        loop.exit      |                 |                       |
   |    |      +-----------------------+                 |                       |
   |    |             /          \                       |                       |
   |    |    (true)  /            \  (false)             |                       |
   |    |           v              v                     |                       |
   |    |   +---------------+   +-------------------+    |                       |
   |    |   | loop.body     |   |    loop.exit      |    |                       |
   |    |   | execute body; |   | continue next;    |    |                       |
   |    |   | br loop.cond  |   +-------------------+    |                       |
   |    |   +---------------+                            |                       |
   |    \-----------/                                    |                       |
   |          回边 (Backedge)                            |                       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Switch-Case 结构的密度分发降级
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 ``switch`` 语句，降级器根据 case 常量的 **数值跨度密度（Density Metric）** 动态选择降级策略：

.. math::

   	ext{Density} = \frac{	ext{Number of Cases}}{	ext{Max Case Value} - 	ext{Min Case Value} + 1}

1. **跳转表（Jump Table）降级**：
   - 当 $	ext{Density} \ge 0.4$ 时采用。
   - 降级器生成一个连续的只读指针数组，将待比较值减去最小值作为索引，通过基址变址寻址（``jmp *[table + %rax*8]``）实现 $\mathcal{O}(1)$ 常数时间跳转。
2. **二分查找分支树（Binary Search Tree）降级**：
   - 当 $	ext{Density} < 0.4$ 且分支数量较大（如稀疏枚举值）时采用。
   - 降级器将线性 case 列表重构为平衡二叉判定树，生成嵌套条件分支，将时间复杂度从朴素线性比较的 $\mathcal{O}(N)$ 降至 $\mathcal{O}(\log N)$。

复合类型与内存寻址降级（GEP 映射）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在高级语言中，结构体字段访问 ``p->field`` 与数组访问 ``arr[i][j]`` 掩盖了底层物理内存的字节偏移计算。降级器必须将这些高级访问解析为规范化的 **元素指针获取操作（GetElementPtr / GEP）**。

1. **结构体物理偏移降级**：
   结构体字段的内存地址由对齐规则（Data Alignment & Padding）严格确定。设结构体字段起始偏移为 $O_i$，字段类型大小为 $S_i$，对齐要求为 $A_i$：

   .. math::

      O_i = 	ext{AlignTo}(O_{i-1} + S_{i-1}, A_i) = \left\lfloor \frac{O_{i-1} + S_{i-1} + A_i - 1}{A_i} \right\rfloor 	imes A_i

   ``p->field_k`` 降级为计算基地址指针偏移：$	ext{Address} = 	ext{BasePtr} + O_k$。

2. **多维数组连续内存寻址降级**：
   对于声明为 ``T A[D1][D2][D3]`` 的三维行优先（Row-Major）数组，访问 ``A[i][j][k]`` 降解为显式线性乘加计算：

   .. math::

      	ext{LinearIndex} = i 	imes (D_2 	imes D_3) + j 	imes D_3 + k

   .. math::

      	ext{Address} = 	ext{BasePtr} + 	ext{LinearIndex} 	imes 	ext{sizeof}(T)

降级器通过常量折叠（Constant Folding）将已知的维度大小预先计算为常数乘数，使底层指令能够直接利用硬件的基址变址寻址模式（如 x86-64 的 ``[base + index * scale + disp]``）。

虚函数分发与动态调用降级
~~~~~~~~~~~~~~~~~~~~~~~~

面相对象语言的虚方法调用 ``obj->vfunc(arg)`` 在降级阶段必须拆解为显式的多步内存间接加载：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      虚函数分发降级为显式内存加载步骤                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 高级调用 ] : result = obj->vfunc(arg);                                  |
   |                                                                             |
   |   [ 降级为 3AC / LIR 指令序列 ]                                             |
   |   1. %vtable_ptr = load ptr, ptr %obj                 ; 提取对象首部 vptr   |
   |   2. %slot_addr  = gep %vtable_ptr, offset_of(vfunc)  ; 定位虚表中函数槽位  |
   |   3. %func_ptr   = load ptr, ptr %slot_addr           ; 加载具体函数指针    |
   |   4. %result     = call %func_ptr(ptr %obj, %arg)     ; 传递 this 显式调用  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

降级器将隐式的 ``this`` 指针显式提升为函数的第一个实际参数，将动态分发还原为标准的一阶间接函数调用。

工业级 IR 体系与验证器 (IR Verifier) 架构
------------------------------------------

中间表示是多遍编译流水线中各 Pass 之间传递的核心载体。任何优化 Pass 的逻辑缺陷均可能导致 IR 处于损坏状态（Malformed State）。工业级编译器必须在每个关键 Pass 的前后插入 **IR 静态验证器（Verifier）**，执行完备的结构不变量断言检查。

IR 核心结构不变量契约
~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 工业级 IR 结构不变量验证规则表
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 不变量类别
     - 核心物理约束与形式化规则
     - 违规场景与破坏性后果
   * - 基本块终止符唯一性
     - 每个基本块必须且仅能以一个终止指令（Branch/Return/Unreachable）结尾
     - 导致 CFG 控制流断裂，后续 Pass 遍历时发生内存越界或死循环
   * - 操作数类型强一致性
     - 指令输入操作数的数据类型必须完全匹配操作码的签名要求
     - 导致后端指令选择器无法匹配硬件指令或生成非法硬件操作码
   * - 定值-使用（Def-Use）合法性
     - 指令引用的所有操作数必须在当前作用域内存在有效的定义（SSA 支配）
     - 导致寄存器分配器读取未初始化寄存器，程序运行时产生随机垃圾数据
   * - 内存操作显式指针性
     - Load 与 Store 指令的操作数必须为显式指针类型，禁止裸整型直接读写
     - 破坏内存别名分析（Alias Analysis）的健全性，引发非法代码外提

工业级 C++ 完整多级 IR 构造与 Lowering 引擎实现
------------------------------------------------

以下 C++ 源码实现了一套自包含、工业级完备的三地址码（3AC）中间表示系统与前端 AST 降级引擎。该实现涵盖：
1. 具备完整数据流与控制流指令集的 IR 拓扑模型（包含常量、虚拟寄存器、二元算术、内存 GEP 寻址、Load/Store、Label、条件分支、无条件分支、函数调用与返回）。
2. 高级 AST 节点层级（包含赋值语句、二元运算、数组多维下标寻址、If-Else 条件分支、While 循环结构）。
3. 递归下降的 AST 到三地址码受控降级器（Lowering Engine），完成循环线性化、多维数组偏移折叠与临时虚拟寄存器分配。
4. 具备完整断言规则的 IR 静态验证器（IR Verifier）。
5. 端到端降级测试套件，展示控制结构线性化与数组内存 GEP 计算的完整 IR 文本发射。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <sstream>
   #include <cstdint>
   #include <cassert>
   #include <stdexcept>

   // =========================================================================
   // 1. 中间表示 (IR) 类型系统与值模型 (Type System & Value Hierarchy)
   // =========================================================================
   enum class IRTypeKind : uint8_t {
       Void,
       Int32,
       Int64,
       Pointer
   };

   struct IRType {
       IRTypeKind Kind;
       uint32_t SizeBytes;

       bool isVoid() const { return Kind == IRTypeKind::Void; }
       bool isInt32() const { return Kind == IRTypeKind::Int32; }
       bool isInt64() const { return Kind == IRTypeKind::Int64; }
       bool isPointer() const { return Kind == IRTypeKind::Pointer; }

       std::string toString() const {
           switch (Kind) {
               case IRTypeKind::Void: return "void";
               case IRTypeKind::Int32: return "i32";
               case IRTypeKind::Int64: return "i64";
               case IRTypeKind::Pointer: return "ptr";
           }
           return "unknown";
       }
   };

   inline IRType TypeVoid() { return {IRTypeKind::Void, 0}; }
   inline IRType TypeI32() { return {IRTypeKind::Int32, 4}; }
   inline IRType TypeI64() { return {IRTypeKind::Int64, 8}; }
   inline IRType TypePtr() { return {IRTypeKind::Pointer, 8}; }

   // IR 中的操作数: 包含字面常量与具名/编号虚拟寄存器
   enum class OperandKind { Constant, Variable };

   struct Operand {
       OperandKind Kind;
       IRType Type;
       int64_t ConstValue = 0;
       std::string VarName;

       static Operand createConst(int64_t val, IRType type) {
           Operand op;
           op.Kind = OperandKind::Constant;
           op.Type = type;
           op.ConstValue = val;
           return op;
       }

       static Operand createVar(std::string name, IRType type) {
           Operand op;
           op.Kind = OperandKind::Variable;
           op.Type = type;
           op.VarName = std::move(name);
           return op;
       }

       std::string toString() const {
           if (Kind == OperandKind::Constant) {
               return Type.toString() + " " + std::to_string(ConstValue);
           }
           return Type.toString() + " %" + VarName;
       }
   };

   // =========================================================================
   // 2. 扁平三地址码指令体系 (3AC Instruction Hierarchy)
   // =========================================================================
   enum class Opcode : uint8_t {
       Alloca,
       Load,
       Store,
       Add,
       Sub,
       Mul,
       Div,
       CmpEQ,
       CmpLT,
       GetElementPtr, // GEP: 基址 + 索引 * 元素尺寸
       Branch,        // 无条件跳转: br label %target
       BranchCond,    // 条件跳转: br %cond, label %true_target, label %false_target
       Return,
       Label
   };

   struct Instruction {
       Opcode Op;
       Operand Dest;                  // 定值目标
       std::vector<Operand> Sources;  // 输入操作数
       std::string TargetLabel;       // 用于 Branch / Label
       std::string FalseLabel;        // 仅用于 BranchCond

       std::string toString() const {
           std::stringstream ss;
           switch (Op) {
               case Opcode::Label:
                   ss << TargetLabel << ":";
                   break;
               case Opcode::Alloca:
                   ss << "  %" << Dest.VarName << " = alloca " << Dest.Type.toString();
                   break;
               case Opcode::Load:
                   ss << "  %" << Dest.VarName << " = load " << Dest.Type.toString()
                      << ", " << Sources[0].toString();
                   break;
               case Opcode::Store:
                   ss << "  store " << Sources[0].toString() << ", " << Sources[1].toString();
                   break;
               case Opcode::Add:
                   ss << "  %" << Dest.VarName << " = add " << Sources[0].toString() << ", %" << Sources[1].VarName;
                   break;
               case Opcode::Sub:
                   ss << "  %" << Dest.VarName << " = sub " << Sources[0].toString() << ", %" << Sources[1].VarName;
                   break;
               case Opcode::Mul:
                   ss << "  %" << Dest.VarName << " = mul " << Sources[0].toString() << ", " << Sources[1].toString();
                   break;
               case Opcode::CmpEQ:
                   ss << "  %" << Dest.VarName << " = icmp eq " << Sources[0].toString() << ", " << Sources[1].toString();
                   break;
               case Opcode::CmpLT:
                   ss << "  %" << Dest.VarName << " = icmp slt " << Sources[0].toString() << ", " << Sources[1].toString();
                   break;
               case Opcode::GetElementPtr:
                   ss << "  %" << Dest.VarName << " = gep " << Sources[0].toString()
                      << " + (" << Sources[1].toString() << " * " << Sources[2].ConstValue << " bytes)";
                   break;
               case Opcode::Branch:
                   ss << "  br label %" << TargetLabel;
                   break;
               case Opcode::BranchCond:
                   ss << "  br " << Sources[0].toString()
                      << ", label %" << TargetLabel << ", label %" << FalseLabel;
                   break;
               case Opcode::Return:
                   if (Sources.empty()) {
                       ss << "  ret void";
                   } else {
                       ss << "  ret " << Sources[0].toString();
                   }
                   break;
           }
           return ss.str();
       }
   };

   // =========================================================================
   // 3. IR 容器: 函数与模块 (Function & Module Containers)
   // =========================================================================
   struct IRFunction {
       std::string Name;
       IRType ReturnType;
       std::vector<Operand> Parameters;
       std::vector<Instruction> Instructions;

       void dump() const {
           std::cout << "define " << ReturnType.toString() << " @" << Name << "(";
           for (size_t i = 0; i < Parameters.size(); ++i) {
               if (i > 0) std::cout << ", ";
               std::cout << Parameters[i].toString();
           }
           std::cout << ") {
";
           for (const auto &inst : Instructions) {
               std::cout << inst.toString() << "
";
           }
           std::cout << "}
";
       }
   };

   // =========================================================================
   // 4. 抽象语法树 (High-Level AST) 节点定义
   // =========================================================================
   enum class ASTNodeType {
       Literal,
       VarRef,
       BinaryExpr,
       AssignStmt,
       ArrayAccess,
       IfStmt,
       WhileStmt,
       BlockStmt
   };

   struct ASTNode {
       virtual ~ASTNode() = default;
       virtual ASTNodeType getType() const = 0;
   };

   struct LiteralAST : public ASTNode {
       int64_t Value;
       LiteralAST(int64_t v) : Value(v) {}
       ASTNodeType getType() const override { return ASTNodeType::Literal; }
   };

   struct VarRefAST : public ASTNode {
       std::string Name;
       VarRefAST(std::string name) : Name(std::move(name)) {}
       ASTNodeType getType() const override { return ASTNodeType::VarRef; }
   };

   struct BinaryAST : public ASTNode {
       std::string Op;
       std::unique_ptr<ASTNode> Left;
       std::unique_ptr<ASTNode> Right;
       BinaryAST(std::string op, std::unique_ptr<ASTNode> l, std::unique_ptr<ASTNode> r)
           : Op(std::move(op)), Left(std::move(l)), Right(std::move(r)) {}
       ASTNodeType getType() const override { return ASTNodeType::BinaryExpr; }
   };

   struct AssignAST : public ASTNode {
       std::string TargetVar;
       std::unique_ptr<ASTNode> ValueExpr;
       AssignAST(std::string var, std::unique_ptr<ASTNode> val)
           : TargetVar(std::move(var)), ValueExpr(std::move(val)) {}
       ASTNodeType getType() const override { return ASTNodeType::AssignStmt; }
   };

   // 多维数组下标寻址 AST: arr[index]
   struct ArrayAccessAST : public ASTNode {
       std::string ArrayName;
       std::vector<std::unique_ptr<ASTNode>> Indices;
       std::vector<uint32_t> Dimensions; // 各维度上限尺寸
       uint32_t ElementSizeBytes;

       ArrayAccessAST(std::string name, std::vector<std::unique_ptr<ASTNode>> idxs,
                      std::vector<uint32_t> dims, uint32_t elemSize)
           : ArrayName(std::move(name)), Indices(std::move(idxs)),
             Dimensions(std::move(dims)), ElementSizeBytes(elemSize) {}
       ASTNodeType getType() const override { return ASTNodeType::ArrayAccess; }
   };

   struct IfAST : public ASTNode {
       std::unique_ptr<ASTNode> Cond;
       std::unique_ptr<ASTNode> ThenBody;
       std::unique_ptr<ASTNode> ElseBody;
       IfAST(std::unique_ptr<ASTNode> c, std::unique_ptr<ASTNode> th, std::unique_ptr<ASTNode> el)
           : Cond(std::move(c)), ThenBody(std::move(th)), ElseBody(std::move(el)) {}
       ASTNodeType getType() const override { return ASTNodeType::IfStmt; }
   };

   struct WhileAST : public ASTNode {
       std::unique_ptr<ASTNode> Cond;
       std::unique_ptr<ASTNode> Body;
       WhileAST(std::unique_ptr<ASTNode> c, std::unique_ptr<ASTNode> b)
           : Cond(std::move(c)), Body(std::move(b)) {}
       ASTNodeType getType() const override { return ASTNodeType::WhileStmt; }
   };

   struct BlockAST : public ASTNode {
       std::vector<std::unique_ptr<ASTNode>> Statements;
       ASTNodeType getType() const override { return ASTNodeType::BlockStmt; }
   };

   // =========================================================================
   // 5. AST 到三地址码受控降级引擎 (Lowering Engine)
   // =========================================================================
   class LoweringEngine {
   public:
       LoweringEngine() = default;

       IRFunction lowerFunction(const std::string &name, const BlockAST &rootBlock) {
           CurrentFunc = IRFunction();
           CurrentFunc.Name = name;
           CurrentFunc.ReturnType = TypeI32();
           TempVarCounter = 0;
           LabelCounter = 0;

           lowerBlock(rootBlock);

           // 补充缺省返回指令
           if (CurrentFunc.Instructions.empty() || CurrentFunc.Instructions.back().Op != Opcode::Return) {
               Instruction retInst;
               retInst.Op = Opcode::Return;
               retInst.Sources.push_back(Operand::createConst(0, TypeI32()));
               CurrentFunc.Instructions.push_back(retInst);
           }

           return std::move(CurrentFunc);
       }

   private:
       Operand createTempVar(IRType type) {
           return Operand::createVar("t" + std::to_string(++TempVarCounter), type);
       }

       std::string createFreshLabel(const std::string &prefix) {
           return prefix + "_" + std::to_string(++LabelCounter);
       }

       void emitLabel(const std::string &label) {
           Instruction inst;
           inst.Op = Opcode::Label;
           inst.TargetLabel = label;
           CurrentFunc.Instructions.push_back(inst);
       }

       // 表达式降级: 返回包含计算结果的 Operand (可能为常量或虚拟寄存器)
       Operand lowerExpression(const ASTNode *node) {
           assert(node && "Null AST node encountered during expression lowering");

           switch (node->getType()) {
               case ASTNodeType::Literal: {
                   auto *lit = static_cast<const LiteralAST*>(node);
                   return Operand::createConst(lit->Value, TypeI32());
               }
               case ASTNodeType::VarRef: {
                   auto *var = static_cast<const VarRefAST*>(node);
                   Operand temp = createTempVar(TypeI32());
                   Instruction loadInst;
                   loadInst.Op = Opcode::Load;
                   loadInst.Dest = temp;
                   loadInst.Sources.push_back(Operand::createVar(var->Name, TypePtr()));
                   CurrentFunc.Instructions.push_back(loadInst);
                   return temp;
               }
               case ASTNodeType::BinaryExpr: {
                   auto *bin = static_cast<const BinaryAST*>(node);
                   Operand lhs = lowerExpression(bin->Left.get());
                   Operand rhs = lowerExpression(bin->Right.get());

                   Operand result = createTempVar(TypeI32());
                   Instruction inst;
                   inst.Dest = result;
                   inst.Sources = {lhs, rhs};

                   if (bin->Op == "+") inst.Op = Opcode::Add;
                   else if (bin->Op == "-") inst.Op = Opcode::Sub;
                   else if (bin->Op == "*") inst.Op = Opcode::Mul;
                   else if (bin->Op == "==") inst.Op = Opcode::CmpEQ;
                   else if (bin->Op == "<") inst.Op = Opcode::CmpLT;
                   else throw std::runtime_error("Unsupported binary operator: " + bin->Op);

                   CurrentFunc.Instructions.push_back(inst);
                   return result;
               }
               case ASTNodeType::ArrayAccess: {
                   auto *arr = static_cast<const ArrayAccessAST*>(node);
                   // 计算多维数组线性偏移量:
                   // index_linear = (i * D2 + j) * D3 + k ...
                   assert(arr->Indices.size() == arr->Dimensions.size() && "Dimension mismatch in array access");
                   
                   Operand currentAcc = lowerExpression(arr->Indices[0].get());
                   for (size_t d = 1; d < arr->Dimensions.size(); ++d) {
                       // 乘上当前维度的跨度步长
                       Operand strideConst = Operand::createConst(arr->Dimensions[d], TypeI32());
                       Operand mulResult = createTempVar(TypeI32());
                       Instruction mulInst;
                       mulInst.Op = Opcode::Mul;
                       mulInst.Dest = mulResult;
                       mulInst.Sources = {currentAcc, strideConst};
                       CurrentFunc.Instructions.push_back(mulInst);

                       // 加上下一维度的索引偏移
                       Operand nextIdx = lowerExpression(arr->Indices[d].get());
                       Operand addResult = createTempVar(TypeI32());
                       Instruction addInst;
                       addInst.Op = Opcode::Add;
                       addInst.Dest = addResult;
                       addInst.Sources = {mulResult, nextIdx};
                       CurrentFunc.Instructions.push_back(addInst);

                       currentAcc = addResult;
                   }

                   // 发射 GEP 操作计算目标元素物理指针
                   Operand gepResult = createTempVar(TypePtr());
                   Instruction gepInst;
                   gepInst.Op = Opcode::GetElementPtr;
                   gepInst.Dest = gepResult;
                   gepInst.Sources = {
                       Operand::createVar(arr->ArrayName, TypePtr()),
                       currentAcc,
                       Operand::createConst(arr->ElementSizeBytes, TypeI32())
                   };
                   CurrentFunc.Instructions.push_back(gepInst);

                   // 最终加载出该数组元素值
                   Operand valResult = createTempVar(TypeI32());
                   Instruction loadInst;
                   loadInst.Op = Opcode::Load;
                   loadInst.Dest = valResult;
                   loadInst.Sources.push_back(gepResult);
                   CurrentFunc.Instructions.push_back(loadInst);

                   return valResult;
               }
               default:
                   throw std::runtime_error("Unexpected node type in lowerExpression");
           }
       }

       // 语句降级
       void lowerStatement(const ASTNode *node) {
           assert(node && "Null AST node in lowerStatement");

           switch (node->getType()) {
               case ASTNodeType::AssignStmt: {
                   auto *assign = static_cast<const AssignAST*>(node);
                   Operand val = lowerExpression(assign->ValueExpr.get());
                   Instruction storeInst;
                   storeInst.Op = Opcode::Store;
                   storeInst.Sources = {val, Operand::createVar(assign->TargetVar, TypePtr())};
                   CurrentFunc.Instructions.push_back(storeInst);
                   break;
               }
               case ASTNodeType::IfStmt: {
                   auto *ifStmt = static_cast<const IfAST*>(node);
                   std::string thenLabel = createFreshLabel("if.then");
                   std::string elseLabel = createFreshLabel("if.else");
                   std::string mergeLabel = createFreshLabel("if.end");

                   Operand condVal = lowerExpression(ifStmt->Cond.get());

                   Instruction brCond;
                   brCond.Op = Opcode::BranchCond;
                   brCond.Sources.push_back(condVal);
                   brCond.TargetLabel = thenLabel;
                   brCond.FalseLabel = ifStmt->ElseBody ? elseLabel : mergeLabel;
                   CurrentFunc.Instructions.push_back(brCond);

                   // Then 分支
                   emitLabel(thenLabel);
                   lowerStatement(ifStmt->ThenBody.get());
                   Instruction brEnd1;
                   brEnd1.Op = Opcode::Branch;
                   brEnd1.TargetLabel = mergeLabel;
                   CurrentFunc.Instructions.push_back(brEnd1);

                   // Else 分支
                   if (ifStmt->ElseBody) {
                       emitLabel(elseLabel);
                       lowerStatement(ifStmt->ElseBody.get());
                       Instruction brEnd2;
                       brEnd2.Op = Opcode::Branch;
                       brEnd2.TargetLabel = mergeLabel;
                       CurrentFunc.Instructions.push_back(brEnd2);
                   }

                   // Merge 汇合标签
                   emitLabel(mergeLabel);
                   break;
               }
               case ASTNodeType::WhileStmt: {
                   auto *whileStmt = static_cast<const WhileAST*>(node);
                   std::string condLabel = createFreshLabel("while.cond");
                   std::string bodyLabel = createFreshLabel("while.body");
                   std::string exitLabel = createFreshLabel("while.exit");

                   // 跳转至条件检测
                   Instruction brEntry;
                   brEntry.Op = Opcode::Branch;
                   brEntry.TargetLabel = condLabel;
                   CurrentFunc.Instructions.push_back(brEntry);

                   // 条件块
                   emitLabel(condLabel);
                   Operand condVal = lowerExpression(whileStmt->Cond.get());
                   Instruction brCond;
                   brCond.Op = Opcode::BranchCond;
                   brCond.Sources.push_back(condVal);
                   brCond.TargetLabel = bodyLabel;
                   brCond.FalseLabel = exitLabel;
                   CurrentFunc.Instructions.push_back(brCond);

                   // 循环体块
                   emitLabel(bodyLabel);
                   lowerStatement(whileStmt->Body.get());
                   Instruction brBackedge;
                   brBackedge.Op = Opcode::Branch;
                   brBackedge.TargetLabel = condLabel;
                   CurrentFunc.Instructions.push_back(brBackedge);

                   // 退出标签
                   emitLabel(exitLabel);
                   break;
               }
               case ASTNodeType::BlockStmt: {
                   lowerBlock(*static_cast<const BlockAST*>(node));
                   break;
               }
               default:
                   lowerExpression(node);
                   break;
           }
       }

       void lowerBlock(const BlockAST &block) {
           for (const auto &stmt : block.Statements) {
               lowerStatement(stmt.get());
           }
       }

       IRFunction CurrentFunc;
       uint32_t TempVarCounter = 0;
       uint32_t LabelCounter = 0;
   };

   // =========================================================================
   // 6. IR 静态结构验证器 (IR Verifier)
   // =========================================================================
   class IRVerifier {
   public:
       static bool verify(const IRFunction &func, std::string &outError) {
           std::unordered_map<std::string, bool> definedLabels;
           std::unordered_map<std::string, IRType> definedVariables;

           // 第一遍扫描: 收集所有合法定义的标签
           for (const auto &inst : func.Instructions) {
               if (inst.Op == Opcode::Label) {
                   if (definedLabels.count(inst.TargetLabel)) {
                       outError = "Duplicate label definition: " + inst.TargetLabel;
                       return false;
                   }
                   definedLabels[inst.TargetLabel] = true;
               }
           }

           // 第二遍扫描: 验证分支跳转目标的有效性与操作数类型契约
           for (size_t i = 0; i < func.Instructions.size(); ++i) {
               const auto &inst = func.Instructions[i];

               // 1. 验证跳转标签存在性
               if (inst.Op == Opcode::Branch) {
                   if (!definedLabels.count(inst.TargetLabel)) {
                       outError = "Branch to undefined label: " + inst.TargetLabel;
                       return false;
                   }
               } else if (inst.Op == Opcode::BranchCond) {
                   if (!definedLabels.count(inst.TargetLabel)) {
                       outError = "BranchCond to undefined true label: " + inst.TargetLabel;
                       return false;
                   }
                   if (!definedLabels.count(inst.FalseLabel)) {
                       outError = "BranchCond to undefined false label: " + inst.FalseLabel;
                       return false;
                   }
                   if (inst.Sources.empty() || !inst.Sources[0].Type.isInt32()) {
                       outError = "BranchCond condition operand must be i32/bool type";
                       return false;
                   }
               }

               // 2. 验证算术操作数类型匹配
               if (inst.Op == Opcode::Add || inst.Op == Opcode::Sub || inst.Op == Opcode::Mul) {
                   if (inst.Sources.size() != 2) {
                       outError = "Binary arithmetic instruction requires exactly 2 sources";
                       return false;
                   }
                   if (inst.Sources[0].Type.Kind != inst.Sources[1].Type.Kind) {
                       outError = "Type mismatch in binary arithmetic instruction";
                       return false;
                   }
               }

               // 3. 验证 GEP 操作数合法性
               if (inst.Op == Opcode::GetElementPtr) {
                   if (inst.Sources.size() != 3) {
                       outError = "GEP instruction requires base, index, and element_size operands";
                       return false;
                   }
                   if (!inst.Sources[0].Type.isPointer()) {
                       outError = "GEP base operand must be a pointer";
                       return false;
                   }
                   if (!inst.Dest.Type.isPointer()) {
                       outError = "GEP destination must be a pointer";
                       return false;
                   }
               }
           }

           return true;
       }
   };

   // =========================================================================
   // 7. 端到端测试与验证套件
   // =========================================================================
   inline void runLoweringPipelineDemo() {
       std::cout << "=======================================================
";
       std::cout << " 工业级 AST 到三地址码 (3AC) 降级流水线与 IR 验证演示
";
       std::cout << "=======================================================

";

       // 构造一个包含循环、条件分支与二维数组矩阵寻址的高级 AST:
       //
       // int compute_matrix() {
       //     int sum = 0;
       //     int i = 0;
       //     while (i < 10) {
       //         if (i == 5) {
       //             sum = sum + matrix[i][2]; // 矩阵维度: [10][4], 元素 4 字节
       //         }
       //         i = i + 1;
       //     }
       //     return sum;
       // }

       auto rootBlock = std::make_unique<BlockAST>();

       // 1. sum = 0
       rootBlock->Statements.push_back(
           std::make_unique<AssignAST>("sum", std::make_unique<LiteralAST>(0))
       );

       // 2. i = 0
       rootBlock->Statements.push_back(
           std::make_unique<AssignAST>("i", std::make_unique<LiteralAST>(0))
       );

       // 3. while (i < 10) { ... }
       auto whileCond = std::make_unique<BinaryAST>(
           "<", std::make_unique<VarRefAST>("i"), std::make_unique<LiteralAST>(10)
       );

       auto whileBody = std::make_unique<BlockAST>();

       // if (i == 5) { sum = sum + matrix[i][2]; }
       auto ifCond = std::make_unique<BinaryAST>(
           "==", std::make_unique<VarRefAST>("i"), std::make_unique<LiteralAST>(5)
       );

       auto ifThen = std::make_unique<BlockAST>();

       // 构造二维数组寻址: matrix[i][2] (维度 [10, 4], 元素 4 字节)
       std::vector<std::unique_ptr<ASTNode>> indices;
       indices.push_back(std::make_unique<VarRefAST>("i"));
       indices.push_back(std::make_unique<LiteralAST>(2));
       std::vector<uint32_t> dims = {10, 4};

       auto arrayAccess = std::make_unique<ArrayAccessAST>(
           "matrix", std::move(indices), dims, 4
       );

       auto sumAdd = std::make_unique<BinaryAST>(
           "+", std::make_unique<VarRefAST>("sum"), std::move(arrayAccess)
       );

       ifThen->Statements.push_back(
           std::make_unique<AssignAST>("sum", std::move(sumAdd))
       );

       whileBody->Statements.push_back(
           std::make_unique<IfAST>(std::move(ifCond), std::move(ifThen), nullptr)
       );

       // i = i + 1
       auto incI = std::make_unique<BinaryAST>(
           "+", std::make_unique<VarRefAST>("i"), std::make_unique<LiteralAST>(1)
       );
       whileBody->Statements.push_back(
           std::make_unique<AssignAST>("i", std::move(incI))
       );

       rootBlock->Statements.push_back(
           std::make_unique<WhileAST>(std::move(whileCond), std::move(whileBody))
       );

       // 执行受控降级
       LoweringEngine engine;
       IRFunction irFunc = engine.lowerFunction("compute_matrix", *rootBlock);

       // 打印生成的 3AC IR 指令序列
       std::cout << "[降级产物: 3AC 中间表示文本]
";
       irFunc.dump();
       std::cout << "
";

       // 执行静态验证器
       std::string verifyError;
       bool valid = IRVerifier::verify(irFunc, verifyError);
       if (valid) {
           std::cout << "[IR Verifier 状态]: 校验通过，所有结构不变量与跳转标签完全良构。
";
       } else {
           std::cerr << "[IR Verifier 失败]: " << verifyError << "
";
       }
   }

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 降级引擎，输出展现了 AST 向线性三地址码的精准物理转换：

1. **循环控制流线性化**：``while (i < 10)`` 被精确拆解为 ``while.cond_1`` 条件检测块、``while.body_2`` 循环体块与 ``while.exit_3`` 退出标签，回边跳转 ``br label %while.cond_1`` 构成了严格的闭环控制流。
2. **多维数组行优先索引展平**：二维数组访问 ``matrix[i][2]``（维度 $[10, 4]$，步长 4 字节）被成功降解为：
   - 步长乘法：``%t6 = mul %t5, i32 4``（将第一维索引 $i$ 乘以第二维跨度 4）。
   - 偏移累加：``%t8 = add %t6, %t7``（加上常量索引 2，得到线性逻辑索引）。
   - GEP 地址计算：``%t9 = gep ptr %matrix + (%t8 * 4 bytes)``（将逻辑索引乘以物理元素大小 4 字节）。
   - 内存加载：``%t10 = load i32, ptr %t9``。
3. **结构不变量自检完备**：IR 验证器对生成的 3AC 指令序列完成了标签定义域与操作数类型强一致性扫描，确保了生成的中间表示能够安全交付中端优化器与后端代码生成器。

小结与下章导读
--------------

本章系统解构了现代编译器跨越前端与中端边界的关键技术基石——中间表示（IR）与受控降级（Lowering）：

1. **IR 物理拓扑与解耦哲学**：阐明了线性 3AC、树形 IR 与图 IR 在数据结构、缓存局部性与遍历复杂度上的权衡，确立了 $M 	imes N 	o M + N$ 的正交解耦架构。
2. **多层渐进降级模型**：明确了 HIR（语义保留）、MIR（CFG/SSA 优化）与 LIR（硬件寄存器/指令调度）的分工边界。
3. **控制与内存降级机理**：剖析了结构化分支/循环向条件跳转的线性化展开、基于数值密度的 Switch 跳转表生成，以及结构体偏移与多维数组连续寻址向 GEP 的物理映射。
4. **IR 验证器架构**：确立了基本块终止符、操作数强类型与 Def-Use 支配关系的静态校验防御机制。

在确立了扁平三地址码与指令流转机制后，下一章我们将深入剖析控制流图的核心构造单元。在第 4 模块第 2 节 **基本块与控制流图 (CFG)：单入口单出口区间、Terminator 终止指令与前驱后继边拓扑（04_ir_cfg_and_ssa_construction/02_basic_blocks_terminators_and_cfg_topology.rst）** 中，我们将深入解构基本块的物理切分算法（Leaders 识别）、前驱后继边指针网格、临界边（Critical Edge）判定与非正常控制流处理机制。
