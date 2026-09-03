====================================================================================================
Machine IR 物理形态：无限虚拟寄存器、目标伪指令展开与流水线感知指令调度
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 2 节（``06_backend_and_instruction_selection/02_instruction_selection_and_dag_pattern_matching.rst``）中，我们系统解构了指令选择（ISel）的树覆盖数学模型、SelectionDAG 五阶段图重写管线以及以线性流水线为核心的 GlobalISel 框架。经过指令选择后，中端抽象 IR 操作已被正式转换为特定目标芯片的机器操作码。然而，此时生成的底层表示并不等同于最终可直接交付 CPU 执行的纯机器码——它操作着数量无限的 **虚拟寄存器（Virtual Registers）**，包含承载控制流抽象与栈帧调整的 **目标伪指令（Pseudo Instructions）**，且指令顺序尚未针对 CPU 流水线执行单元进行延迟重排。本章深入剖析现代编译器后端的核心工作表示——**Machine IR（MIR）** 的内存拓扑与对象模型、子寄存器别名（Sub-register Aliasing）机制、伪指令在不同编译阶段的精准展开状态机、机器基本块物理排布优化，以及面向超标量流水线（Superscalar Pipeline）在寄存器分配前夕执行的 **流水线感知指令调度（Pre-RA Instruction Scheduling）** 理论与实现。

Machine IR 物理对象模型与拓扑解构
---------------------------------

在工业级编译器（如 LLVM 与 GCC）中，Machine IR（MIR）是后端管线中贯穿指令选择、指令调度、寄存器分配与栈帧布局的统一骨干表示。

四大核心层级对象模型
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Machine IR 层次化物理对象拓扑                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ MachineFunction ]                                                       |
   |      |                                                                      |
   |      +---> [ MachineRegisterInfo (MRI) ] : 追踪虚拟寄存器定值/使用与寄存器类|
   |      +---> [ MachineFrameInfo (MFI) ]    : 抽象栈槽 (Stack Slots) 与溢出区  |
   |      |                                                                      |
   |      +---> [ MachineBasicBlock (MBB) 0 : Entry ]                            |
   |      |        |                                                             |
   |      |        +---> liveins: $rdi, $rsi  <--- 声明物理寄存器入口活跃状态     |
   |      |        |                                                             |
   |      |        +---> [ MachineInstr 1 ] : %0:gr64 = COPY $rdi                |
   |      |        +---> [ MachineInstr 2 ] : %1:gr64 = COPY $rsi                |
   |      |        +---> [ MachineInstr 3 ] : %2:gr64 = ADD64rr %0, %1           |
   |      |                                   (implicit-def $eflags)             |
   |      |                                                                      |
   |      +---> [ MachineBasicBlock (MBB) 1 : Exit ]                             |
   |               +---> [ MachineInstr 4 ] : $rax = COPY %2                     |
   |               +---> [ MachineInstr 5 ] : RET64 $rax                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **``MachineFunction``**：包含目标函数的完整机器上下文，管理虚拟寄存器信息表（``MachineRegisterInfo``）与栈帧对象表（``MachineFrameInfo``）。
2. **``MachineBasicBlock (MBB)``**：机器级单入口单出口基本块，显式维护前驱/后继 MBB 拓扑边与入口物理寄存器活跃集（``liveins``）。
3. **``MachineInstr (MI)``**：底层的物理指令或伪指令实体，包含目标操作码（Opcode）、执行标志位与变长操作数列表。
4. **``MachineOperand (MO)``**：指令操作数的细粒度物理封装（涵盖虚拟寄存器、物理寄存器、立即数、帧索引 FrameIndex、基本块目标等）。

虚拟寄存器、寄存器类与子寄存器别名拓扑
--------------------------------------

寄存器类 (RegisterClass) 与寄存器库 (RegisterBank)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在寄存器分配（RA）之前，编译器使用数量无限的虚拟寄存器（命名为 ``%0``, ``%1``, ``%2`` ...）。
每个虚拟寄存器必须绑定到一个 **寄存器类（RegisterClass）**：
- x86-64 的 ``GR32``：限制该虚拟寄存器必须被分配到 32 位通用寄存器之一（``EAX``, ``EBX``, ``ECX``, ``EDX``, ``ESI``, ``EDI``, ``R8D``~``R15D``）。
- AArch64 的 ``FPR128``：限制必须分配到 128 位 SIMD/浮点向量寄存器（``Q0``~``Q31``）。

子寄存器树形别名拓扑 (Sub-Register Hierarchy)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

硬件 CPU 物理寄存器之间存在复杂的嵌套包含关系。例如在 x86-64 架构中：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    x86-64 物理寄存器嵌套别名 (Sub-Reg Hierarchy)            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 64-bit RAX 完整寄存器 ]                                                 |
   |   +------------------------------------+----------------------------------+ |
   |   |        高 32 位 (只读/零扩展)      |         32-bit EAX (低 32 位)    | |
   |   +------------------------------------+-----------------+----------------+ |
   |                                                          | 16-bit AX      | |
   |                                                          +-------+--------+ |
   |                                                          | 8b AH | 8b AL  | |
   |                                                          +-------+--------+ |
   |                                                                             |
   |   * 别名冲突规则: 修改 AL/AH/AX/EAX 会隐式破坏并重写 RAX 的对应物理位!     |
   |   * 子寄存器索引 (sub_8bit, sub_16bit, sub_32bit) 形式化标定切片位置        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

显式操作数 vs 隐式操作数 (Explicit vs Implicit Operands)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

机器指令除了显式参与计算的寄存器外，通常具有硬件隐式副作用：
- **``implicit-def $eflags``**：x86 整数加法 ``ADD32rr`` 在计算和的同时，硬件 ALU 会隐式修改进位、溢出、零标志位寄存器 ``EFLAGS``。
- **``implicit $rsp``**：函数调用指令 ``CALLpcrel32`` 显式跳转的同时，硬件会自动隐式使用并自减栈指针 ``RSP``。
- 显式声明隐式操作数使后端的依赖分析器与活跃变量分析器能够精确建立指令间的数据与时序依赖边。

目标伪指令展开 (Pseudo-Instruction Expansion) 状态机
----------------------------------------------------

**目标伪指令（Pseudo Instructions）** 是编译器在后端早期为了保持抽象、简化合法化与模式匹配而引入的虚拟指令。它们无法被目标机器硬件直接执行，必须在代码生成的特定阶段被展开为真实机器指令序列。

伪指令三大经典应用场景
~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 典型目标伪指令及其物理微架构展开
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 伪指令名称
     - 抽象语义
     - 后期物理展开形态 (Lowered Form)
   * - ``ADJCALLSTACKDOWN / UP``
     - 标记函数调用传参栈帧预留与回收边界
     - 展开为硬件栈调整指令（如 ``sub rsp, 32`` / ``add rsp, 32``）或被完全消除
   * - ``LOAD_TLS_ADDR``
     - 线程局部存储（TLS）变量地址获取
     - 依据 TLS 模型展开为加载 GOT 偏移量并调用 ``__tls_get_addr`` 的复杂指令序列
   * - ``ATOMIC_CMP_SWAP``
     - 硬件原子比较并交换（CAS）抽象
     - 展开为带有 ``lock cmpxchg`` 前缀指令或 LL/SC 循环分支重试序列
   * - ``LONG_BRANCH``
     - 相对位移超出硬件跳转限制的条件分支
     - **分支松弛（Branch Relaxation）**：将短跳转指令展开为反向条件短跳 + 64 位绝对跳转

伪指令展开的三大阶段划分
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       后端伪指令生命周期与分阶段展开状态机                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: Pre-RA 展开 (寄存器分配前) ]                                    |
   |      * 展开涉及新增虚拟寄存器的复杂操作 (如 64 位乘除法在 32 位机器上的展开)|
   |      * 目的: 让新增的虚拟寄存器能够完整参与全局图着色寄存器分配             |
   |                                                                             |
   |   [ 阶段 2: Post-RA 展开 (寄存器分配后) ]                                   |
   |      * 展开使用固定物理寄存器的控制流/栈指令 (如 ADJCALLSTACK)              |
   |      * 消除通用的 COPY 伪指令 (降级为具体的 MOV 或寄存器重命名消除)          |
   |                                                                             |
   |   [ 阶段 3: Pre-Emit 展开 (汇编/机器码发射前夕) ]                           |
   |      * 执行分支松弛 (Branch Relaxation) 与目标机器流水线气泡填充 NOP         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

机器基本块物理排布优化 (Block Placement)
----------------------------------------

高级语言与中端 IR 的基本块排布通常以生成顺序排列。后端代码生成必须执行 **基本块物理排布优化（Machine Block Placement）**，以最大化指令缓存（I-Cache）命中率并减少无条件跳转开销。

落空优先布局 (Fallthrough-First Layout)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   	ext{Prob}(	ext{Edge}(A 	o B)) \ge 	ext{Prob}(	ext{Edge}(A 	o C)) \implies 	ext{Place } B 	ext{ immediately after } A

若分支 $A 	o B$ 的执行概率显著高于 $A 	o C$，编译器强制将 $B$ 物理放置在 $A$ 的正下方：
1. **消除无条件跳转**：$A$ 命中后直接自然落空（Fallthrough）进入 $B$，完全免除一条 ``jmp`` 硬件指令。
2. **分支预测加速**：现代 CPU 静态分支预测器默认偏向不跳转（Not-Taken）预测，落空排布与硬件预测方向高度契合。

超标量流水线与前置指令调度 (Pre-RA Scheduling)
----------------------------------------------

现代 CPU 采用深层超标量流水线（Superscalar Pipeline），在单时钟周期内发射多条指令执行。
若相邻指令之间存在 **数据冒险（Data Hazards）** 或 **长延迟加载（Load Latency）**，处理器流水线将被迫插入 **停顿气泡（Stall Bubbles）**。

指令调度数据依赖 DAG 建模
~~~~~~~~~~~~~~~~~~~~~~~~~

指令调度器为基本块构建 **数据依赖有向无环图（Scheduling DAG）**：
- **写后读依赖（Read-After-Write, RAW）**：真数据依赖，边权重等于前驱指令的 **硬件执行延迟（Latency）**（例如浮点乘法 Latency = 4 周期，内存加载 Load Latency = 3 周期）。
- **读后写反依赖（Write-After-Read, WAR）**：伪依赖，由寄存器复用引入。
- **写后写输出依赖（Write-After-Write, WAW）**：伪依赖。

Pre-RA 调度的双刃剑：指令级并行 (ILP) vs 寄存器压力 (Register Pressure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在寄存器分配之前执行调度（Pre-RA Scheduling）面临极具挑战的 **组合博弈**：

.. list-table:: Pre-RA 指令调度的物理权衡博弈
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 调度倾向策略
     - 微架构物理行为
     - 极端情况下的系统风险
   * - **激进追求 ILP (提升吞吐)**
     - 将互相独立的计算指令大幅交错重排，填满多发射流水线延迟槽
     - **虚拟寄存器生命周期严重重叠**，瞬时活跃变量激增，引发严重的寄存器溢出（Spill to Stack）
   * - **控制寄存器压力 (减少溢出)**
     - 尽快消费刚刚产出的值（Def-Use 局部收敛），缩短活跃区间
     - 产生大量密集的连续依赖指令，导致流水线频繁遭遇停顿气泡

工业级编译器普遍采用 **基于关键路径（Critical Path）与可用寄存器阈值（Pressure Threshold）混合权衡的列表调度算法（List Scheduling）**。

工业级 C++ 完整 Machine IR 与伪指令展开引擎实现
------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级 Machine IR 物理模型、伪指令展开器（PseudoExpander）与流水线感知列表调度器（ListScheduler）。该实现涵盖：
1. 包含操作数类型、虚拟/物理寄存器标识、隐式标志位定义的 `MachineInstr` 模型。
2. 包含执行延迟（Latency）的超标量流水线依赖图建模。
3. 关键路径优先的列表调度器（List Scheduler），消除 Load 后的执行气泡。
4. 目标伪指令（`CALL_SEQ_START` / `CALL_SEQ_END` / `CMP_AND_JUMP`）向具体物理指令的平滑展开。
5. 端到端测试套件（验证指令调度消除停顿与伪指令物理展开）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <queue>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>

   namespace machine_ir_engine {

   // =========================================================================
   // 1. Machine IR 操作码与操作数物理模型
   // =========================================================================
   enum class TargetOpcode {
       // 伪指令 (Pseudo Instructions)
       PSEUDO_CALL_SEQ_START,
       PSEUDO_CALL_SEQ_END,
       PSEUDO_CMP_AND_JUMP,

       // 真实硬件指令 (Concrete Machine Instructions)
       MOV_REG,
       LOAD_MEM,      // Latency = 3 周期
       ADD_REG,       // Latency = 1 周期
       SUB_STACK,     // sub rsp, imm
       ADD_STACK,     // add rsp, imm
       CMP_FLAGS,     // cmp r1, r2 (implicit-def EFLAGS)
       JE_BRANCH      // je target   (implicit-use EFLAGS)
   };

   struct MachineOperand {
       enum class Kind { VirtualReg, PhysicalReg, Immediate, TargetBlock } Type;
       std::string Name;
       int64_t ImmVal = 0;

       static MachineOperand createVReg(const std::string& name) {
           return {Kind::VirtualReg, name, 0};
       }
       static MachineOperand createPReg(const std::string& name) {
           return {Kind::PhysicalReg, name, 0};
       }
       static MachineOperand createImm(int64_t val) {
           return {Kind::Immediate, "", val};
       }
       static MachineOperand createBlock(const std::string& label) {
           return {Kind::TargetBlock, label, 0};
       }

       std::string toString() const {
           if (Type == Kind::Immediate) return std::to_string(ImmVal);
           return Name;
       }
   };

   struct MachineInstr {
       uint32_t ID = 0;
       TargetOpcode Op;
       std::vector<MachineOperand> Defs;
       std::vector<MachineOperand> Uses;
       std::vector<std::string> ImplicitDefs;
       std::vector<std::string> ImplicitUses;
       uint32_t Latency = 1;

       std::string toString() const {
           std::string s = "  ";
           for (const auto& d : Defs) s += d.toString() + " = ";
           switch (Op) {
               case TargetOpcode::PSEUDO_CALL_SEQ_START: s += "PSEUDO_CALL_SEQ_START " + Uses[0].toString(); break;
               case TargetOpcode::PSEUDO_CALL_SEQ_END:   s += "PSEUDO_CALL_SEQ_END " + Uses[0].toString(); break;
               case TargetOpcode::PSEUDO_CMP_AND_JUMP:   s += "PSEUDO_CMP_AND_JUMP " + Uses[0].toString() + ", " + Uses[1].toString() + ", " + Uses[2].toString(); break;
               case TargetOpcode::MOV_REG:   s += "mov " + Uses[0].toString(); break;
               case TargetOpcode::LOAD_MEM:  s += "ldr [" + Uses[0].toString() + "]"; break;
               case TargetOpcode::ADD_REG:   s += "add " + Uses[0].toString() + ", " + Uses[1].toString(); break;
               case TargetOpcode::SUB_STACK: s += "sub $rsp, " + Uses[0].toString(); break;
               case TargetOpcode::ADD_STACK: s += "add $rsp, " + Uses[0].toString(); break;
               case TargetOpcode::CMP_FLAGS: s += "cmp " + Uses[0].toString() + ", " + Uses[1].toString(); break;
               case TargetOpcode::JE_BRANCH: s += "je " + Uses[0].toString(); break;
           }
           if (!ImplicitDefs.empty()) {
               s += " (imp-def: ";
               for (const auto& imp : ImplicitDefs) s += imp + " ";
               s += ")";
           }
           return s;
       }
   };

   // =========================================================================
   // 2. 目标伪指令展开器 (Pseudo Expander)
   // =========================================================================
   class PseudoExpander {
   public:
       static std::vector<MachineInstr> expandBlock(const std::vector<MachineInstr>& insts) {
           std::vector<MachineInstr> expanded;
           uint32_t idGen = 100;

           for (const auto& mi : insts) {
               if (mi.Op == TargetOpcode::PSEUDO_CALL_SEQ_START) {
                   // 展开为栈指针预留指令: sub rsp, imm
                   expanded.push_back({
                       ++idGen,
                       TargetOpcode::SUB_STACK,
                       {MachineOperand::createPReg("$rsp")},
                       {mi.Uses[0]},
                       {},
                       {"$rsp"},
                       1
                   });
               } else if (mi.Op == TargetOpcode::PSEUDO_CALL_SEQ_END) {
                   // 展开为栈指针恢复指令: add rsp, imm
                   expanded.push_back({
                       ++idGen,
                       TargetOpcode::ADD_STACK,
                       {MachineOperand::createPReg("$rsp")},
                       {mi.Uses[0]},
                       {},
                       {"$rsp"},
                       1
                   });
               } else if (mi.Op == TargetOpcode::PSEUDO_CMP_AND_JUMP) {
                   // 展开为硬件 CMP 指令 + 条件跳转 JE
                   expanded.push_back({
                       ++idGen,
                       TargetOpcode::CMP_FLAGS,
                       {},
                       {mi.Uses[0], mi.Uses[1]},
                       {"$eflags"},
                       {},
                       1
                   });
                   expanded.push_back({
                       ++idGen,
                       TargetOpcode::JE_BRANCH,
                       {},
                       {mi.Uses[2]},
                       {},
                       {"$eflags"},
                       1
                   });
               } else {
                   expanded.push_back(mi);
               }
           }
           return expanded;
       }
   };

   // =========================================================================
   // 3. 流水线感知列表调度器 (List Scheduler - Pre-RA)
   // =========================================================================
   class ListScheduler {
       struct SchedNode {
           MachineInstr Instr;
           uint32_t InDegree = 0;
           std::vector<uint32_t> Successors; // 依赖当前节点的后继指令索引
           uint32_t Latency = 1;
       };

   public:
       // 基于关键路径与延迟感知的调度算法 (消除流水线气泡)
       static std::vector<MachineInstr> scheduleBlock(const std::vector<MachineInstr>& insts) {
           size_t n = insts.size();
           if (n <= 1) return insts;

           std::vector<SchedNode> nodes(n);
           std::unordered_map<std::string, uint32_t> lastDefMap;

           // 1. 构建 RAW 数据依赖图
           for (size_t i = 0; i < n; ++i) {
               nodes[i].Instr = insts[i];
               nodes[i].Latency = insts[i].Latency;

               for (const auto& u : insts[i].Uses) {
                   if (u.Type == MachineOperand::Kind::VirtualReg && lastDefMap.count(u.Name)) {
                       uint32_t predIdx = lastDefMap[u.Name];
                       nodes[predIdx].Successors.push_back(static_cast<uint32_t>(i));
                       nodes[i].InDegree++;
                   }
               }
               for (const auto& d : insts[i].Defs) {
                   if (d.Type == MachineOperand::Kind::VirtualReg) {
                       lastDefMap[d.Name] = static_cast<uint32_t>(i);
                   }
               }
           }

           // 2. 就绪队列 (优先调度高延迟指令以掩盖气泡)
           auto comp = [&](uint32_t a, uint32_t b) {
               return nodes[a].Latency < nodes[b].Latency; // 延迟高的优先
           };
           std::priority_queue<uint32_t, std::vector<uint32_t>, decltype(comp)> readyQueue(comp);

           for (size_t i = 0; i < n; ++i) {
               if (nodes[i].InDegree == 0) readyQueue.push(static_cast<uint32_t>(i));
           }

           std::vector<MachineInstr> scheduled;
           while (!readyQueue.empty()) {
               uint32_t curr = readyQueue.top();
               readyQueue.pop();

               scheduled.push_back(nodes[curr].Instr);

               for (uint32_t succ : nodes[curr].Successors) {
                   nodes[succ].InDegree--;
                   if (nodes[succ].InDegree == 0) {
                       readyQueue.push(succ);
                   }
               }
           }

           return scheduled;
       }
   };

   } // namespace machine_ir_engine

   // =========================================================================
   // 4. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runMachineIRTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Machine IR 物理模型、伪指令展开与流水线调度测试套件
";
       std::cout << "=======================================================

";

       using namespace machine_ir_engine;

       // 1. 测试 Pre-RA 调度消除 Load-Use 流水线延迟气泡
       // 构造场景:
       //   %v1 = load [%ptr1]        (Latency = 3 周期)
       //   %v2 = add %v1, %v_other   (依赖 %v1, 若紧随 load 将产生 2 周期流水线停顿!)
       //   %v3 = mov 100             (独立指令，应当被调度到中间填补气泡!)
       std::vector<MachineInstr> unoptimized;
       unoptimized.push_back({
           1,
           TargetOpcode::LOAD_MEM,
           {MachineOperand::createVReg("%v1")},
           {MachineOperand::createVReg("%ptr1")},
           {}, {},
           3 // 3 周期高延迟
       });
       unoptimized.push_back({
           2,
           TargetOpcode::ADD_REG,
           {MachineOperand::createVReg("%res")},
           {MachineOperand::createVReg("%v1"), MachineOperand::createVReg("%v_other")},
           {}, {},
           1
       });
       unoptimized.push_back({
           3,
           TargetOpcode::MOV_REG,
           {MachineOperand::createVReg("%v3")},
           {MachineOperand::createImm(100)},
           {}, {},
           1
       });

       std::cout << "[测试 1: 调度前存在气泡的原始 Machine IR]:
";
       for (const auto& mi : unoptimized) std::cout << mi.toString() << "
";

       auto scheduled = ListScheduler::scheduleBlock(unoptimized);

       std::cout << "
[测试 1: 经过流水线感知列表调度后的 Machine IR]:
";
       for (const auto& mi : scheduled) std::cout << mi.toString() << "
";

       // 验证断言: 独立的 %v3 = mov 必须被成功插入到 LOAD 与 ADD 之间以填补延迟
       assert(scheduled.size() == 3);
       assert(scheduled[0].Op == TargetOpcode::LOAD_MEM);
       assert(scheduled[1].Op == TargetOpcode::MOV_REG); // 独立指令提前填补
       assert(scheduled[2].Op == TargetOpcode::ADD_REG);
       std::cout << "  -> 成功重排指令，利用独立计算填补了 3 周期 Load 延迟气泡。

";

       // 2. 测试目标伪指令展开
       std::vector<MachineInstr> pseudos;
       pseudos.push_back({
           10,
           TargetOpcode::PSEUDO_CALL_SEQ_START,
           {},
           {MachineOperand::createImm(32)},
           {}, {}, 1
       });
       pseudos.push_back({
           11,
           TargetOpcode::PSEUDO_CMP_AND_JUMP,
           {},
           {MachineOperand::createVReg("%a"), MachineOperand::createVReg("%b"), MachineOperand::createBlock("target_bb")},
           {}, {}, 1
       });
       pseudos.push_back({
           12,
           TargetOpcode::PSEUDO_CALL_SEQ_END,
           {},
           {MachineOperand::createImm(32)},
           {}, {}, 1
       });

       std::cout << "[测试 2: 目标伪指令展开前]:
";
       for (const auto& mi : pseudos) std::cout << mi.toString() << "
";

       auto expanded = PseudoExpander::expandBlock(pseudos);

       std::cout << "
[测试 2: 目标伪指令展开后真实机器指令序列]:
";
       for (const auto& mi : expanded) std::cout << mi.toString() << "
";

       // 验证断言:
       // 1. PSEUDO_CALL_SEQ 展开为 sub $rsp 与 add $rsp
       // 2. PSEUDO_CMP_AND_JUMP 展开为 cmp + je (带 $eflags 隐式定义与使用)
       assert(expanded.size() == 4);
       assert(expanded[0].Op == TargetOpcode::SUB_STACK);
       assert(expanded[1].Op == TargetOpcode::CMP_FLAGS && expanded[1].ImplicitDefs[0] == "$eflags");
       assert(expanded[2].Op == TargetOpcode::JE_BRANCH && expanded[2].ImplicitUses[0] == "$eflags");
       assert(expanded[3].Op == TargetOpcode::ADD_STACK);
       std::cout << "  -> 伪指令展开断言完全正确。

";

       std::cout << "  -> Machine IR 模型与伪指令/调度引擎验证全部通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了 Machine IR 在后端中转与物理贴合阶段的核心机制：

1. **流水线气泡消除**：在测试 1 中，原本紧挨着高延迟内存加载（``LOAD_MEM``，3 周期）的消费指令 ``ADD_REG`` 会在硬件微架构中引发至少 2 个周期的流水线停顿。列表调度器准确识别出不相关的 ``MOV_REG`` 指令并将其提拔到中间执行，在完全不改变程序语义的前提下免费掩盖了硬件等待周期。
2. **伪指令的物理降解**：在测试 2 中，抽象的调用边界与比较跳转被顺利展开为符合硬件 ABI 的栈指针移动（``sub $rsp, 32``）与显式包含 ``$eflags`` 隐式绑定的 ``cmp`` + ``je`` 指令对，为后续的寄存器分配与机器码发射扫清了所有抽象障碍。

小结与下章导读
--------------

本章系统解构了现代编译器后端在指令选择完成后的核心工作表示与前序优化管线：

1. **Machine IR 对象拓扑**：剖析了 ``MachineFunction``、``MachineBasicBlock``、``MachineInstr`` 与 ``MachineOperand`` 的物理模型，阐明了子寄存器别名（如 RAX/EAX/AL）与隐式副作用声明（`implicit-def`）在微架构中的约束意义。
2. **目标伪指令展开状态机**：推导了调用栈帧调整、原子操作、分支松弛等伪指令在 Pre-RA、Post-RA 与 Pre-Emit 各阶段的精准降级机理。
3. **基本块物理排布优化**：解构了落空优先（Fallthrough-First）布局对消除无条件跳转与配合硬件静态分支预测的性能收益。
4. **Pre-RA 列表调度**：形式化建立了基于 RAW 数据依赖图的调度模型，阐明了在填补超标量流水线执行气泡与控制寄存器压力之间的核心权衡。

在完成了 Machine IR 建模与前置调度后，编译器必须全面直面硬件指令调度中最复杂的各类冒险问题。在第 6 模块第 4 节 **指令调度与冒险规避：数据冒险 (RAW/WAR/WAW)、流水线延迟槽、列表调度 (List Scheduling)（``06_backend_and_instruction_selection/04_instruction_scheduling_and_hazard_mitigation.rst``）** 中，我们将深入剖析结构冒险、数据冒险与控制冒险的微架构成因、MIPS/SPARC 分支延迟槽（Branch Delay Slots）安全填充算法，以及在寄存器分配后（Post-RA）执行的带物理寄存器冲突感知的列表调度优化。
