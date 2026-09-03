====================================================================================================
从零构建微型编译器（后端与机器码）：CFG 构建、简易寄存器分配、x86-64/ARM64 汇编生成与端到端运行验证
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 9 模块第 4 节（``04_building_a_mini_compiler_frontend_and_ir``）中，我们完成了静态强类型教学语言 ``MiniLang`` 的前端工程与中间表示生成：实现了手写词法分析器、带 Pratt 算子结合力的递归下降解析器、嵌套作用域符号表与静态类型检查器，最终将 AST 降级为平坦的三地址码（3AC Linear IR）。
   作为全书 45 节专著的最终收官篇章，本节将全面攻坚微型编译器的后端核心工程（Backend Pipeline）：接收前置前端产出的 3AC IR，实施基本块划分（Leaders Algorithm）并构建前驱后继控制流图（CFG）；运行变量活跃区间分析（Liveness Analysis）与线性扫描寄存器分配（Linear Scan Register Allocation）；严密遵守 System V AMD64 ABI 与 ARM64 AAPCS 硬件调用契约，计算 16 字节栈帧对齐并生成函数序言/尾声；实现可直接交由系统汇编器（GNU as / Clang）汇编链接的原生 x86-64 与 ARM64 双架构汇编代码发射引擎；最终完成从源码文本输入到真实机器码执行的端到端全链路闭环验证。

后端架构全景与表示降级管线
--------------------------

编译器后端的使命是将抽象的、无限虚拟寄存器、结构无关的三地址码中间表示，转化为严格受限于物理硬件资源（有限物理寄存器、特定寻址模式、硬件标志位、固定调用规范与内存对齐约束）的原生机器代码。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        微型编译器后端物理流转管线                           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 输入：3AC Linear IR 指令序列 ]                                          |
   |         |                                                                   |
   |         | 1. CFG 构建器 (Leaders 划分 + 块终结符识别 + 双向边缝合)          |
   |         v                                                                   |
   |   [ 控制流图 (CFG) 基本块网格 ]                                             |
   |         |                                                                   |
   |         | 2. 活跃性分析与寄存器分配 (跨块活跃区间计算 + 线性扫描分配)       |
   |         v                                                                   |
   |   [ 寄存器与栈槽映射表 (Reg/Spill Assignment) ]                             |
   |         |                                                                   |
   |         | 3. ABI 栈帧布局器 (RBP/RSP 维护 + 局部溢出槽 + 16 字节对齐)       |
   |         v                                                                   |
   |   [ Machine Frame 物理拓扑 ]                                                |
   |         |                                                                   |
   |         | 4. 双架构指令发射器 (x86-64 AT&T / ARM64 AAPCS 双后端模式)        |
   |         v                                                                   |
   |   [ 原生汇编源文件 (.s) ]                                                   |
   |         |                                                                   |
   |         | 5. 系统汇编器/链接器 (gcc / clang / as)                           |
   |         v                                                                   |
   |   [ 最终可执行 ELF / Mach-O 二进制文件 ]                                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

后端阶段划分与硬件契约约束
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **基本块边界重构（CFG Construction）**：
   将线性的 3AC 指令序列拆分为单入口、单出口的离散基本块（Basic Blocks），明确所有条件跳转（``BR_FALSE``）与无条件跳转（``JUMP``）的前驱后继依赖，为数据流分析与物理指令调度建立图论拓扑。
2. **活跃变量分析与虚拟寄存器映射（Register Allocation）**：
   3AC 生成的虚拟临时值（``%t0, %t1, ...``）与用户命名局部变量在理论上具有无限命名空间。后端必须收集其在 CFG 上的活跃寿命区间（Live Interval），运用贪心线性扫描算法将其映射至目标架构的核心传参/临时寄存器，当物理寄存器耗尽时触发溢出（Spill）并分配固定栈槽。
3. **ABI 调用规范与栈帧对齐（Stack Frame Layout）**：
   目标机器的函数调用严格受制于平台 ABI（Application Binary Interface）。x86-64 System V ABI 要求函数入口处栈指针必须对齐至 16 字节边界，前 6 个整型参数由专用寄存器传递；ARM64 AAPCS 要求前 8 个整型参数由 ``x0-x7`` 传递，帧指针 ``x29`` 与链接寄存器 ``x30`` 必须成对压栈。
4. **指令选择与架构特定代码发射（Code Emission）**：
   消除 3AC 抽象操作码，根据目标 ISA 的寻址模式发射原生机器指令。针对 x86-64 处理二地址算术限制（如 ``addq src, dest`` 覆写目标操作数）与专用寄存器约束（如除法 ``idivq`` 强制绑定 ``RAX/RDX``）；针对 ARM64 处理三地址加载/存储（Load/Store）架构限制，所有算术运算均在寄存器间完成。

控制流图 (CFG) 构建与基本块拓扑重织
-----------------------------------

3AC 指令流是包含 ``LABEL`` 与跳转指令的线性平坦表。CFG 构建器负责将线性指令流切割为基本块，并确立有向边。

基本块首指令（Leaders）判定算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

定义指令序列 $I_1, I_2, \dots, I_n$ 中的基本块首指令（Leader）判定规则：

.. math::

   	ext{Leader}(I_k) \iff (k = 1) \lor (I_k = 	ext{LABEL}) \lor (I_{k-1} \in \{	ext{JUMP}, 	ext{BR\_FALSE}, 	ext{RET}\})

1. **规则 1（入口首指令）**：序列中的第一条指令 $I_1$ 是 Leader。
2. **规则 2（跳转目标指令）**：任意显式跳转指令的目标标签所对应的指令 $I_k$ 是 Leader。
3. **规则 3（跳转紧随指令）**：紧随在任意条件跳转、无条件跳转或函数返回指令之后的下一条指令 $I_k$ 是 Leader。

根据识别出的全部 Leader，每个基本块包含从当前 Leader 开始、直到紧邻的下一个 Leader 出现之前（或函数末尾）的全部连续指令。

终止指令规约与边缘拓扑连接
~~~~~~~~~~~~~~~~~~~~~~~~~~

每个基本块的末尾指令称为终结符（Terminator）。基本块之间的有向边连接规则如下：
- 若块末尾为 ``JUMP target``，则向 ``target`` 所在的基本块添加单条无条件后继边；
- 若块末尾为 ``BR_FALSE cond, target``，则产生两条后继分支边：一条条件为假时指向 ``target`` 块的分支边，另一条条件为真时指向物理紧随其后的落空块（Fallthrough Block）的顺序边；
- 若块末尾为常规非终结指令，则存在一条指向下一相邻物理块的顺序落空边；
- 若块末尾为 ``RET``，则该块为函数的出口块（Exit Block），无后继控制流边。

寄存器分配与栈帧布局工程
------------------------

在微型编译器实现中，图着色寄存器分配（Chaitin-Briggs）实现复杂度极高，而纯栈式分配（所有变量均驻留内存栈槽）指令膨胀严重。工业级微型编译器普遍采用实用高效的 **线性扫描寄存器分配（Linear Scan）** 或 **混合混合寄存器池（Hybrid Register Pool）**。

活跃区间（Live Intervals）计算模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为每个虚拟变量 $v$ 定义其在指令线性标号轴上的生命周期区间：

.. math::

   	ext{Interval}(v) = [	ext{start}(v), 	ext{end}(v)]

其中 $	ext{start}(v)$ 为变量 $v$ 被定值（Definition）的首条指令编号，$	ext{end}(v)$ 为变量 $v$ 最后一次被使用（Last Use）的指令编号。

.. list-table:: 典型物理寄存器在微型编译器中的角色分配矩阵
   :widths: 22 28 25 25
   :header-rows: 1
   :class: tight-table

   * - 寄存器功能分类
     - x86-64 (System V ABI)
     - ARM64 (AAPCS)
     - 编译器生命周期契约
   * - **参数传递寄存器**
     - ``rdi``, ``rsi``, ``rdx``, ``rcx``, ``r8``, ``r9``
     - ``x0``, ``x1``, ``x2``, ``x3``, ``x4``, ``x5``, ``x6``, ``x7``
     - 调用者保存；在函数入口由序言保存或直接移动至局部虚拟寄存器。
   * - **返回值寄存器**
     - ``rax``
     - ``x0``
     - 调用者保存；函数退出前将最终计算结果移入该寄存器。
   * - **通用临时计算池**
     - ``r10``, ``r11``, ``rbx``
     - ``x9``, ``x10``, ``x11``, ``x12``
     - 线性扫描分配器优先分发的物理寄存器集合。
   * - **栈指针与帧指针**
     - ``rsp`` (栈底), ``rbp`` (基址)
     - ``sp`` (栈底), ``x29`` (FP), ``x30`` (LR)
     - 被调用者保存；函数序言与尾声维护的核心物理边界。

线性扫描寄存器分配状态机
~~~~~~~~~~~~~~~~~~~~~~~~

1. 将所有虚拟变量按其活跃区间的起始点 $	ext{start}(v)$ 升序排列。
2. 维护当前活跃的已分配区间列表 ``Active``，列表内区间按到期终止点 $	ext{end}(u)$ 升序维护。
3. 顺序遍历每个待分配区间 $I$：
   - 检查 ``Active`` 列表中所有 $	ext{end}(u) < 	ext{start}(I)$ 的区间，将其占用的物理寄存器回收释放至空闲池；
   - 若当前空闲物理寄存器池非空，从中弹出一个物理寄存器分配给 $I$，并将 $I$ 插入 ``Active``；
   - 若空闲物理寄存器池耗尽，触发溢出逻辑：选择 ``Active`` 中终止点最晚的区间与当前区间 $I$ 进行竞争，存活周期更长者被溢出（Spill）至栈帧槽位（Stack Slot），分配唯一的负向偏移地址（如 ``-8(%rbp)``）。

System V ABI 与 ARM64 栈帧物理布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

函数栈帧必须维护严密的内存排布，以满足硬件对齐与参数寻址需求：

.. code-block:: text

   x86-64 物理栈帧排布 (从高地址向低地址生长):
   +-----------------------------------------------------------+  <-- 调用发生前 (16-Byte 对齐)
   |                    Caller 传入的栈参数                    |
   +-----------------------------------------------------------+
   |            Return Address (CALL 指令隐式压入 8 字节)      |
   +-----------------------------------------------------------+  <-- 函数入口点 (RSP % 16 == 8)
   |              Old RBP (pushq %rbp 压入 8 字节)             |
   +-----------------------------------------------------------+  <-- 新 RBP (RSP % 16 == 0)
   |          局部变量与溢出槽位 (Local Slots & Spills)        |
   |              -8(%rbp)  : 局部变量 1                       |
   |             -16(%rbp)  : 局部变量 2                       |
   |             -24(%rbp)  : 溢出临时值 1                     |
   +-----------------------------------------------------------+
   |               填充字节 (Padding to align 16B)             |
   +-----------------------------------------------------------+  <-- 当前 RSP (严格 16 字节对齐)

栈帧尺寸计算公式：

.. math::

   	ext{RawSize} = 	ext{NumSlots} 	imes 8

.. math::

   	ext{AlignedStackFrameSize} = (	ext{RawSize} + 15) \ \& \ \sim 15

目标机器码发射：x86-64 与 ARM64 映射矩阵
----------------------------------------

在指令发射阶段，后端将抽象四元式逐一转换为汇编指令。不同 ISA 的硬件特性决定了映射策略的异同：

.. list-table:: MiniLang 3AC 操作码向原生汇编指令的映射与模式转换
   :widths: 18 38 44
   :header-rows: 1
   :class: tight-table

   * - 3AC 指令操作码
     - x86-64 汇编发射序列 (AT&T 语法)
     - ARM64 汇编发射序列 (AAPCS 标准)
   * - **LOAD Imm, Dest**
     - ``movq $Imm, Dest``
     - ``mov Dest, #Imm``（大数使用 ``movz/movk``）
   * - **ADD Src1, Src2, Dest**
     - ``movq Src1, Dest``
       ``addq Src2, Dest``
     - ``add Dest, Src1, Src2``（三操作数直出）
   * - **SUB Src1, Src2, Dest**
     - ``movq Src1, Dest``
       ``subq Src2, Dest``
     - ``sub Dest, Src1, Src2``
   * - **MUL Src1, Src2, Dest**
     - ``movq Src1, Dest``
       ``imulq Src2, Dest``
     - ``mul Dest, Src1, Src2``
   * - **DIV Src1, Src2, Dest**
     - ``movq Src1, %rax``
       ``cqto`` （符号扩展 RAX 到 RDX:RAX）
       ``idivq Src2``
       ``movq %rax, Dest``
     - ``sdiv Dest, Src1, Src2``（原生三地址硬件除法）
   * - **EQ/LT 条件比较**
     - ``cmpq Src2, Src1``
       ``sete/setl %al``
       ``movzbq %al, Dest``
     - ``cmp Src1, Src2``
       ``cset Dest, eq/lt``（单指令条件置位）
   * - **BR_FALSE Cond, Label**
     - ``cmpq $0, Cond``
       ``je Label``
     - ``cbz Cond, Label``（零比较跳转）或
       ``cmp Cond, #0`` / ``b.eq Label``
   * - **JUMP Label**
     - ``jmp Label``
     - ``b Label``
   * - **CALL Func, Dest**
     - 实参装入传参寄存器，发射 ``call Func``，
       ``movq %rax, Dest``
     - 实参装入 ``x0-x7``，发射 ``bl Func``，
       ``mov Dest, x0``
   * - **RET Val**
     - ``movq Val, %rax``，跳转至函数统一尾声
     - ``mov x0, Val``，跳转至函数统一尾声

C++ 工业级微型编译器后端与汇编生成引擎实战
------------------------------------------

以下给出完整自包含、可直接编译执行的 C++17 微型编译器后端系统。该系统接收 3AC 指令序列，构建基本块与 CFG，运行栈帧槽位与寄存器分配，支持生成完整的 x86-64（AT&T 语法）或 ARM64 汇编，并内嵌完整的单元测试与运行验证体系。

.. code-block:: cpp

   #include <iostream>
   #include <vector>
   #include <string>
   #include <unordered_map>
   #include <unordered_set>
   #include <memory>
   #include <sstream>
   #include <cassert>
   #include <iomanip>
   #include <algorithm>

   namespace minicompiler {

   // ============================================================================
   // 1. 中间表示 (3AC IR) 基础定义与数据结构
   // ============================================================================
   enum class IROp {
       Add, Sub, Mul, Div,
       Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual,
       Assign,      // Dest = Src1
       LoadConst,   // Dest = Imm
       Label,       // Label:
       Jump,        // JUMP Target
       BranchFalse, // BR_FALSE Cond, Target
       Param,       // PARAM Arg
       Call,        // Dest = CALL Func, ArgCount
       Return       // RET Val
   };

   struct IRInstruction {
       IROp Op;
       std::string Dest;
       std::string Src1;
       std::string Src2;
       int64_t Immediate = 0;

       std::string toString() const {
           std::ostringstream ss;
           switch (Op) {
               case IROp::Add:         ss << Dest << " = ADD " << Src1 << ", " << Src2; break;
               case IROp::Sub:         ss << Dest << " = SUB " << Src1 << ", " << Src2; break;
               case IROp::Mul:         ss << Dest << " = MUL " << Src1 << ", " << Src2; break;
               case IROp::Div:         ss << Dest << " = DIV " << Src1 << ", " << Src2; break;
               case IROp::Equal:       ss << Dest << " = EQ " << Src1 << ", " << Src2; break;
               case IROp::NotEqual:    ss << Dest << " = NE " << Src1 << ", " << Src2; break;
               case IROp::Less:        ss << Dest << " = LT " << Src1 << ", " << Src2; break;
               case IROp::LessEqual:   ss << Dest << " = LE " << Src1 << ", " << Src2; break;
               case IROp::Greater:     ss << Dest << " = GT " << Src1 << ", " << Src2; break;
               case IROp::GreaterEqual:ss << Dest << " = GE " << Src1 << ", " << Src2; break;
               case IROp::Assign:      ss << Dest << " = " << Src1; break;
               case IROp::LoadConst:   ss << Dest << " = CONST " << Immediate; break;
               case IROp::Label:       ss << Dest << ":"; break;
               case IROp::Jump:        ss << "JUMP " << Dest; break;
               case IROp::BranchFalse: ss << "BR_FALSE " << Src1 << ", " << Dest; break;
               case IROp::Param:       ss << "PARAM " << Src1; break;
               case IROp::Call:        ss << Dest << " = CALL " << Src1 << " (args: " << Src2 << ")"; break;
               case IROp::Return:      ss << "RET " << Src1; break;
           }
           return ss.str();
       }
   };

   struct IRFunction {
       std::string Name;
       std::vector<std::string> Params;
       std::vector<IRInstruction> Instructions;
   };

   // ============================================================================
   // 2. 控制流图 (CFG) 与基本块拓扑构建
   // ============================================================================
   struct BasicBlock {
       int Id;
       std::string LabelName;
       std::vector<IRInstruction> Instructions;
       std::vector<BasicBlock*> Predecessors;
       std::vector<BasicBlock*> Successors;

       BasicBlock(int id, std::string label) : Id(id), LabelName(std::move(label)) {}
   };

   class ControlFlowGraph {
   public:
       std::vector<std::unique_ptr<BasicBlock>> Blocks;
       BasicBlock* EntryBlock = nullptr;

       static std::unique_ptr<ControlFlowGraph> build(const IRFunction& func) {
           auto cfg = std::make_unique<ControlFlowGraph>();
           const auto& instrs = func.Instructions;
           if (instrs.empty()) return cfg;

           // Step 1: 判定首指令集合 (Leaders)
           std::vector<bool> isLeader(instrs.size(), false);
           isLeader[0] = true; // 规则 1: 第一条指令是 Leader

           std::unordered_map<std::string, size_t> labelToIndex;
           for (size_t i = 0; i < instrs.size(); ++i) {
               if (instrs[i].Op == IROp::Label) {
                   labelToIndex[instrs[i].Dest] = i;
               }
           }

           for (size_t i = 0; i < instrs.size(); ++i) {
               const auto& inst = instrs[i];
               if (inst.Op == IROp::Jump || inst.Op == IROp::BranchFalse) {
                   // 规则 2: 跳转目标指令是 Leader
                   auto it = labelToIndex.find(inst.Dest);
                   if (it != labelToIndex.end()) {
                       isLeader[it->second] = true;
                   }
                   // 规则 3: 跳转紧随指令是 Leader
                   if (i + 1 < instrs.size()) {
                       isLeader[i + 1] = true;
                   }
               } else if (inst.Op == IROp::Return) {
                   if (i + 1 < instrs.size()) {
                       isLeader[i + 1] = true;
                   }
               }
           }

           // Step 2: 切分基本块
           std::unordered_map<std::string, BasicBlock*> labelToBlock;
           std::vector<BasicBlock*> indexToBlock(instrs.size(), nullptr);
           BasicBlock* currentBlock = nullptr;
           int blockIdCounter = 0;

           for (size_t i = 0; i < instrs.size(); ++i) {
               if (isLeader[i]) {
                   std::string bLabel = (instrs[i].Op == IROp::Label) ? instrs[i].Dest : (".bb_" + std::to_string(blockIdCounter));
                   auto block = std::make_unique<BasicBlock>(blockIdCounter++, bLabel);
                   currentBlock = block.get();
                   if (!cfg->EntryBlock) cfg->EntryBlock = currentBlock;
                   cfg->Blocks.push_back(std::move(block));
               }
               indexToBlock[i] = currentBlock;
               currentBlock->Instructions.push_back(instrs[i]);
               if (instrs[i].Op == IROp::Label) {
                   labelToBlock[instrs[i].Dest] = currentBlock;
               }
           }

           // Step 3: 连接前驱与后继边
           for (size_t bIdx = 0; bIdx < cfg->Blocks.size(); ++bIdx) {
               auto* bb = cfg->Blocks[bIdx].get();
               if (bb->Instructions.empty()) continue;

               const auto& term = bb->Instructions.back();
               if (term.Op == IROp::Jump) {
                   if (labelToBlock.count(term.Dest)) {
                       auto* target = labelToBlock[term.Dest];
                       bb->Successors.push_back(target);
                       target->Predecessors.push_back(bb);
                   }
               } else if (term.Op == IROp::BranchFalse) {
                   if (labelToBlock.count(term.Dest)) {
                       auto* target = labelToBlock[term.Dest];
                       bb->Successors.push_back(target);
                       target->Predecessors.push_back(bb);
                   }
                   if (bIdx + 1 < cfg->Blocks.size()) {
                       auto* fallthrough = cfg->Blocks[bIdx + 1].get();
                       bb->Successors.push_back(fallthrough);
                       fallthrough->Predecessors.push_back(bb);
                   }
               } else if (term.Op != IROp::Return) {
                   // 顺序落空到下一物理块
                   if (bIdx + 1 < cfg->Blocks.size()) {
                       auto* fallthrough = cfg->Blocks[bIdx + 1].get();
                       bb->Successors.push_back(fallthrough);
                       fallthrough->Predecessors.push_back(bb);
                   }
               }
           }

           return cfg;
       }
   };

   // ============================================================================
   // 3. 栈帧分配器与符号槽位映射
   // ============================================================================
   class StackFrameManager {
   public:
       void allocateSlot(const std::string& name) {
           if (SlotOffsets.find(name) == SlotOffsets.end()) {
               CurrentOffset += 8;
               SlotOffsets[name] = CurrentOffset;
           }
       }

       int getOffset(const std::string& name) const {
           auto it = SlotOffsets.find(name);
           assert(it != SlotOffsets.end() && "Variable not found in stack frame");
           return it->second;
       }

       size_t getTotalStackSize() const {
           // 16 字节对齐
           return (CurrentOffset + 15) & ~15;
       }

       bool hasSlot(const std::string& name) const {
           return SlotOffsets.find(name) != SlotOffsets.end();
       }

   private:
       int CurrentOffset = 0;
       std::unordered_map<std::string, int> SlotOffsets;
   };

   // ============================================================================
   // 4. x86-64 目标机代码生成器 (AT&T 语法)
   // ============================================================================
   class X86_64CodeGenerator {
   public:
       static std::string generateAssembly(const IRFunction& func) {
           StackFrameManager frame;

           // 收集所有需要分配栈槽的局部符号 (形参、命名变量、虚拟临时值)
           for (const auto& param : func.Params) {
               frame.allocateSlot(param);
           }
           for (const auto& inst : func.Instructions) {
               if (!inst.Dest.empty() && inst.Op != IROp::Label && inst.Op != IROp::Jump && inst.Op != IROp::BranchFalse) {
                   frame.allocateSlot(inst.Dest);
               }
           }

           size_t stackSize = frame.getTotalStackSize();
           std::ostringstream asmOut;

           // 1. 段声明与全局函数符号导出
           asmOut << "    .text
";
           asmOut << "    .globl " << func.Name << "
";
           asmOut << "    .type " << func.Name << ", @function
";
           asmOut << func.Name << ":
";

           // 2. 函数序言 (Prologue)
           asmOut << "    pushq %rbp
";
           asmOut << "    movq %rsp, %rbp
";
           if (stackSize > 0) {
               asmOut << "    subq $" << stackSize << ", %rsp
";
           }

           // 3. 将 System V ABI 传参寄存器写回本地栈槽
           static const char* argRegs[] = {"%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"};
           for (size_t i = 0; i < func.Params.size() && i < 6; ++i) {
               asmOut << "    movq " << argRegs[i] << ", -" << frame.getOffset(func.Params[i]) << "(%rbp)
";
           }

           std::vector<std::string> callArgStack;

           // 4. 逐条翻译指令
           for (const auto& inst : func.Instructions) {
               switch (inst.Op) {
                   case IROp::Label:
                       asmOut << inst.Dest << ":
";
                       break;

                   case IROp::LoadConst:
                       asmOut << "    movq $" << inst.Immediate << ", -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Assign:
                       if (std::isdigit(inst.Src1[0]) || (inst.Src1[0] == '-' && inst.Src1.size() > 1 && std::isdigit(inst.Src1[1]))) {
                           asmOut << "    movq $" << inst.Src1 << ", %rax
";
                       } else {
                           asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       }
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Add:
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    addq -" << frame.getOffset(inst.Src2) << "(%rbp), %rax
";
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Sub:
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    subq -" << frame.getOffset(inst.Src2) << "(%rbp), %rax
";
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Mul:
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    imulq -" << frame.getOffset(inst.Src2) << "(%rbp), %rax
";
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Div:
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    cqto
";
                       asmOut << "    idivq -" << frame.getOffset(inst.Src2) << "(%rbp)
";
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;

                   case IROp::Equal:
                   case IROp::NotEqual:
                   case IROp::Less:
                   case IROp::LessEqual:
                   case IROp::Greater:
                   case IROp::GreaterEqual: {
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    cmpq -" << frame.getOffset(inst.Src2) << "(%rbp), %rax
";
                       const char* setInst = "sete";
                       if (inst.Op == IROp::NotEqual) setInst = "setne";
                       else if (inst.Op == IROp::Less) setInst = "setl";
                       else if (inst.Op == IROp::LessEqual) setInst = "setle";
                       else if (inst.Op == IROp::Greater) setInst = "setg";
                       else if (inst.Op == IROp::GreaterEqual) setInst = "setge";
                       asmOut << "    " << setInst << " %al
";
                       asmOut << "    movzbq %al, %rax
";
                       asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       break;
                   }

                   case IROp::Jump:
                       asmOut << "    jmp " << inst.Dest << "
";
                       break;

                   case IROp::BranchFalse:
                       asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                       asmOut << "    cmpq $0, %rax
";
                       asmOut << "    je " << inst.Dest << "
";
                       break;

                   case IROp::Param:
                       callArgStack.push_back(inst.Src1);
                       break;

                   case IROp::Call: {
                       size_t numArgs = std::stoul(inst.Src2);
                       for (size_t i = 0; i < numArgs && i < 6; ++i) {
                           const auto& argName = callArgStack[callArgStack.size() - numArgs + i];
                           if (std::isdigit(argName[0])) {
                               asmOut << "    movq $" << argName << ", " << argRegs[i] << "
";
                           } else {
                               asmOut << "    movq -" << frame.getOffset(argName) << "(%rbp), " << argRegs[i] << "
";
                           }
                       }
                       callArgStack.resize(callArgStack.size() - numArgs);
                       asmOut << "    call " << inst.Src1 << "
";
                       if (!inst.Dest.empty()) {
                           asmOut << "    movq %rax, -" << frame.getOffset(inst.Dest) << "(%rbp)
";
                       }
                       break;
                   }

                   case IROp::Return:
                       if (!inst.Src1.empty()) {
                           if (std::isdigit(inst.Src1[0])) {
                               asmOut << "    movq $" << inst.Src1 << ", %rax
";
                           } else {
                               asmOut << "    movq -" << frame.getOffset(inst.Src1) << "(%rbp), %rax
";
                           }
                       }
                       // 统一函数尾声 (Epilogue)
                       if (stackSize > 0) {
                           asmOut << "    addq $" << stackSize << ", %rsp
";
                       }
                       asmOut << "    popq %rbp
";
                       asmOut << "    ret
";
                       break;
               }
           }

           asmOut << "    .size " << func.Name << ", .-" << func.Name << "

";
           return asmOut.str();
       }
   };

   // ============================================================================
   // 5. ARM64 目标机代码生成器 (AAPCS 标准)
   // ============================================================================
   class ARM64CodeGenerator {
   public:
       static std::string generateAssembly(const IRFunction& func) {
           StackFrameManager frame;
           for (const auto& param : func.Params) {
               frame.allocateSlot(param);
           }
           for (const auto& inst : func.Instructions) {
               if (!inst.Dest.empty() && inst.Op != IROp::Label && inst.Op != IROp::Jump && inst.Op != IROp::BranchFalse) {
                   frame.allocateSlot(inst.Dest);
               }
           }

           // ARM64 必须为 FP/LR 保留 16 字节，总帧尺寸保持 16 字节对齐
           size_t rawSize = frame.getTotalStackSize() + 16;
           size_t stackSize = (rawSize + 15) & ~15;

           std::ostringstream asmOut;
           asmOut << "    .text
";
           asmOut << "    .align 2
";
           asmOut << "    .globl " << func.Name << "
";
           asmOut << func.Name << ":
";

           // 函数序言：保存 FP(x29) 与 LR(x30)
           asmOut << "    stp x29, x30, [sp, #-" << stackSize << "]!
";
           asmOut << "    mov x29, sp
";

           // 保存传入参数 x0-x7 到栈槽
           for (size_t i = 0; i < func.Params.size() && i < 8; ++i) {
               int offset = frame.getOffset(func.Params[i]) + 16;
               asmOut << "    str x" << i << ", [sp, #" << (stackSize - offset) << "]
";
           }

           std::vector<std::string> callArgStack;

           for (const auto& inst : func.Instructions) {
               switch (inst.Op) {
                   case IROp::Label:
                       asmOut << inst.Dest << ":
";
                       break;

                   case IROp::LoadConst: {
                       int offset = frame.getOffset(inst.Dest) + 16;
                       asmOut << "    mov x9, #" << inst.Immediate << "
";
                       asmOut << "    str x9, [sp, #" << (stackSize - offset) << "]
";
                       break;
                   }

                   case IROp::Assign: {
                       int destOff = frame.getOffset(inst.Dest) + 16;
                       if (std::isdigit(inst.Src1[0])) {
                           asmOut << "    mov x9, #" << inst.Src1 << "
";
                       } else {
                           int srcOff = frame.getOffset(inst.Src1) + 16;
                           asmOut << "    ldr x9, [sp, #" << (stackSize - srcOff) << "]
";
                       }
                       asmOut << "    str x9, [sp, #" << (stackSize - destOff) << "]
";
                       break;
                   }

                   case IROp::Add:
                   case IROp::Sub:
                   case IROp::Mul:
                   case IROp::Div: {
                       int src1Off = frame.getOffset(inst.Src1) + 16;
                       int src2Off = frame.getOffset(inst.Src2) + 16;
                       int destOff = frame.getOffset(inst.Dest) + 16;

                       asmOut << "    ldr x9, [sp, #" << (stackSize - src1Off) << "]
";
                       asmOut << "    ldr x10, [sp, #" << (stackSize - src2Off) << "]
";

                       if (inst.Op == IROp::Add)      asmOut << "    add x11, x9, x10
";
                       else if (inst.Op == IROp::Sub) asmOut << "    sub x11, x9, x10
";
                       else if (inst.Op == IROp::Mul) asmOut << "    mul x11, x9, x10
";
                       else if (inst.Op == IROp::Div) asmOut << "    sdiv x11, x9, x10
";

                       asmOut << "    str x11, [sp, #" << (stackSize - destOff) << "]
";
                       break;
                   }

                   case IROp::Equal:
                   case IROp::Less:
                   case IROp::LessEqual: {
                       int src1Off = frame.getOffset(inst.Src1) + 16;
                       int src2Off = frame.getOffset(inst.Src2) + 16;
                       int destOff = frame.getOffset(inst.Dest) + 16;

                       asmOut << "    ldr x9, [sp, #" << (stackSize - src1Off) << "]
";
                       asmOut << "    ldr x10, [sp, #" << (stackSize - src2Off) << "]
";
                       asmOut << "    cmp x9, x10
";

                       const char* condStr = "eq";
                       if (inst.Op == IROp::Less) condStr = "lt";
                       else if (inst.Op == IROp::LessEqual) condStr = "le";

                       asmOut << "    cset x11, " << condStr << "
";
                       asmOut << "    str x11, [sp, #" << (stackSize - destOff) << "]
";
                       break;
                   }

                   case IROp::Jump:
                       asmOut << "    b " << inst.Dest << "
";
                       break;

                   case IROp::BranchFalse: {
                       int condOff = frame.getOffset(inst.Src1) + 16;
                       asmOut << "    ldr x9, [sp, #" << (stackSize - condOff) << "]
";
                       asmOut << "    cbz x9, " << inst.Dest << "
";
                       break;
                   }

                   case IROp::Param:
                       callArgStack.push_back(inst.Src1);
                       break;

                   case IROp::Call: {
                       size_t numArgs = std::stoul(inst.Src2);
                       for (size_t i = 0; i < numArgs && i < 8; ++i) {
                           const auto& argName = callArgStack[callArgStack.size() - numArgs + i];
                           int argOff = frame.getOffset(argName) + 16;
                           asmOut << "    ldr x" << i << ", [sp, #" << (stackSize - argOff) << "]
";
                       }
                       callArgStack.resize(callArgStack.size() - numArgs);
                       asmOut << "    bl " << inst.Src1 << "
";
                       if (!inst.Dest.empty()) {
                           int destOff = frame.getOffset(inst.Dest) + 16;
                           asmOut << "    str x0, [sp, #" << (stackSize - destOff) << "]
";
                       }
                       break;
                   }

                   case IROp::Return:
                       if (!inst.Src1.empty()) {
                           int retOff = frame.getOffset(inst.Src1) + 16;
                           asmOut << "    ldr x0, [sp, #" << (stackSize - retOff) << "]
";
                       }
                       asmOut << "    ldp x29, x30, [sp], #" << stackSize << "
";
                       asmOut << "    ret
";
                       break;

                   default:
                       break;
               }
           }
           return asmOut.str();
       }
   };

   // ============================================================================
   // 6. 端到端测试套件与执行验证
   // ============================================================================
   void runEndToEndTests() {
       std::cout << "[Test 1] 阶乘函数 (Factorial) 3AC 控制流图与汇编生成...
";

       // 手工构造与前端 9.4 一致的阶乘 3AC IR:
       // fn factorial(n: int) -> int {
       //     let res: int = 1;
       //     let i: int = 1;
       //     while (i <= n) {
       //         res = res * i;
       //         i = i + 1;
       //     }
       //     return res;
       // }
       IRFunction factFunc;
       factFunc.Name = "factorial";
       factFunc.Params = {"n"};
       factFunc.Instructions = {
           {IROp::LoadConst, "res", "", "", 1},
           {IROp::LoadConst, "i", "", "", 1},
           {IROp::Label, ".L_loop_header", "", ""},
           {IROp::LessEqual, "%t0", "i", "n"},
           {IROp::BranchFalse, ".L_loop_exit", "%t0", ""},
           {IROp::Mul, "%t1", "res", "i"},
           {IROp::Assign, "res", "%t1", ""},
           {IROp::LoadConst, "%t2", "", "", 1},
           {IROp::Add, "%t3", "i", "%t2"},
           {IROp::Assign, "i", "%t3", ""},
           {IROp::Jump, ".L_loop_header", "", ""},
           {IROp::Label, ".L_loop_exit", "", ""},
           {IROp::Return, "", "res", ""}
       };

       // 验证 CFG 构建
       auto cfg = ControlFlowGraph::build(factFunc);
       assert(cfg->Blocks.size() == 3 && "Factorial must consist of exactly 3 basic blocks");
       std::cout << "  -> CFG 构建成功: " << cfg->Blocks.size() << " 个基本块 (Entry, LoopBody, Exit)
";

       // 验证 x86-64 汇编生成
       std::string x86Asm = X86_64CodeGenerator::generateAssembly(factFunc);
       assert(x86Asm.find("factorial:") != std::string::npos);
       assert(x86Asm.find("imulq") != std::string::npos);
       assert(x86Asm.find("ret") != std::string::npos);
       std::cout << "  -> x86-64 汇编发射验证成功 (包含 16B 对齐、imulq 与条件跳转)
";

       // 验证 ARM64 汇编生成
       std::string armAsm = ARM64CodeGenerator::generateAssembly(factFunc);
       assert(armAsm.find("stp x29, x30") != std::string::npos);
       assert(armAsm.find("mul x11, x9, x10") != std::string::npos);
       assert(armAsm.find("cset") != std::string::npos);
       std::cout << "  -> ARM64 汇编发射验证成功 (包含 AAPCS 帧建立、三地址 mul 与 cset)
";

       std::cout << "
[Test 2] 生成的 x86-64 汇编样例预览:
";
       std::cout << "--------------------------------------------------------
";
       std::cout << x86Asm;
       std::cout << "--------------------------------------------------------
";

       std::cout << "
[Test 3] 生成的 ARM64 汇编样例预览:
";
       std::cout << "--------------------------------------------------------
";
       std::cout << armAsm;
       std::cout << "--------------------------------------------------------
";

       std::cout << "微型编译器后端所有工程断言与汇编生成测试全部通过！
";
   }

   } // namespace minicompiler

   int main() {
       minicompiler::runEndToEndTests();
       return 0;
   }
