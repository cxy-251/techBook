====================================================================================================
溢出代码生成与栈槽复用：溢出代价评估、栈槽生命周期重叠判定与微架构热路径保护
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 2 节（``07_register_allocation_stack_and_abi/02_graph_coloring_and_linear_scan_allocation.rst``）中，我们系统剖析了 Chaitin-Briggs 图着色与 Poletto 线性扫描两大经典寄存器分配算法。当程序在某一局部的瞬时并发活跃变量数超出目标机物理可用寄存器上限 $K$ 时，分配器必须在冲突图中挑选候选变量执行 **溢出（Spill）**。然而，未经精细控制的溢出是导致编译产物运行性能严重劣化（Performance Degradation）的首要根源：每一次溢出写入（Spill Store）与重新加载（Reload Load）都意味着将纳秒级 CPU 寄存器访问降级为内存总线事务。如果溢出指令不幸落入内层高频循环中，整个程序的吞吐率将遭受毁灭性打击。此外，若为每个溢出的虚拟变量分配独立的物理栈槽，函数栈帧体积将急剧膨胀，破坏 L1 数据缓存（D-Cache）的局部性。本章深入解构溢出代价（Spill Cost）的循环嵌套权重模型、常量重物化优化（Rematerialization）、活跃区间切分（Live Range Splitting）、基于生命周期冲突图的 **栈槽着色复用（Stack Slot Coloring）** 算法，以及面向硬件存储转发（Store-to-Load Forwarding, STLF）的热路径微架构保护工程。

溢出代价形式化评估模型 (Spill Cost Modeling)
--------------------------------------------

寄存器分配器决定“溢出谁”的依据是精确的 **溢出代价函数 $	ext{SpillCost}(v)$**。其核心目标是：**以最小的运行期内存读写开销为代价，释放出尽可能多的冲突图高阶连接边**。

静态循环嵌套深度权重模型
~~~~~~~~~~~~~~~~~~~~~~~~

在控制流图（CFG）中，处于深层循环内的指令执行频率远高于外层直线代码。标准编译器采用静态循环深度指数加权公式：

.. math::

   	ext{Weight}(I) = 10^{	ext{LoopDepth}(I)}

设虚拟变量 $v$ 在程序中的定值集合为 $	ext{Defs}(v)$，使用点集合为 $	ext{Uses}(v)$，则该变量的总物理访存开销评估为：

.. math::

   	ext{TotalCost}(v) = \sum_{d \in 	ext{Defs}(v)} 	ext{StoreCost} 	imes 10^{	ext{LoopDepth}(d)} + \sum_{u \in 	ext{Uses}(v)} 	ext{LoadCost} 	imes 10^{	ext{LoopDepth}(u)}

Chaitin 溢出权重判定公理
~~~~~~~~~~~~~~~~~~~~~~~~

在图着色简化阶段，Chaitin-Briggs 算法为冲突图中的每个度数 $\ge K$ 的高阶节点计算归一化溢出权重：

.. math::

   	ext{SpillWeight}(v) = \frac{	ext{TotalCost}(v)}{	ext{Degree}(v)}

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     Chaitin 溢出权重评估与仲裁状态机                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 候选变量 A ]: 处于 3 层嵌套循环内 (LoopDepth=3), 冲突度 Degree = 3      |
   |      * TotalCost = (1 store + 2 loads) * 10^3 = 3000                        |
   |      * SpillWeight(A) = 3000 / 3 = 1000.0  <--- 代价极高! 坚决保留在寄存器  |
   |                                                                             |
   |   [ 候选变量 B ]: 处于最外层代码 (LoopDepth=0), 冲突度 Degree = 8           |
   |      * TotalCost = (1 store + 1 load) * 10^0 = 2                            |
   |      * SpillWeight(B) = 2 / 8 = 0.25       <--- 优先牺牲溢出目标!           |
   |                                                                             |
   |   * 决策: 牺牲 B 仅需支付 2 次内存访问，即可同时解除 8 个相邻节点的寄存器争用|
   |                                                                             |
   +-----------------------------------------------------------------------------+

重物化优化 (Rematerialization)：以廉价计算消解溢出访存
------------------------------------------------------

并非所有溢出变量都需要真实地向物理栈写入数据。对于某些特定类型的值，**重新计算该值的指令开销远低于从内存栈槽执行加载（Reload）的延迟**。这种技术称为 **重物化（Rematerialization）**。

.. list-table:: 重物化判定准则与代价值对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 变量值形态
     - 重物化可行性与操作指令
     - 物理微架构收益
   * - **常量立即数** (如 0, 1, 指针偏移)
     - **极高**：单条 ``mov reg, imm`` 或 ``xor reg, reg``（0 周期/单周期）
     - **彻底消除 Spill Store 与 Reload Load**；无内存流量，无栈槽占用
   * - **帧地址 / 全局符号基址**
     - **高**：单条 ``lea reg, [rbp - offset]``
     - 纯 ALU 计算，完全避免 L1 D-Cache 访存竞争
   * - **简单一元/二元算术运算**
     - **中等**：操作数本身若常驻寄存器，可重新发射 ``add/shift``
     - 规避 3~5 周期 Load-to-Use 内存停顿
   * - **不可重物化值** (如内存读入值、函数返回值)
     - **不可行**：必须走真实栈槽 Spill/Reload 流程
     - 保证程序计算语义绝对守恒

溢出代码精准插入与活跃区间切分 (Live Range Splitting)
----------------------------------------------------

当确定虚拟变量 $v$ 必须溢出后，分配器需要对 IR 进行微观指令重写：

溢出代码插入范式
~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     溢出 Store 与 Reload 指令插入物理拓扑                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 原始虚拟指令序列 (Virtual IR) ]:                                        |
   |      %v = ADD64 %a, %b                                                      |
   |      ... (跨越数千条指令与高寄存器压力区域) ...                             |
   |      USE64 %v                                                               |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 插入溢出代码后的机器指令序列 (Spill Lowered MIR) ]:                     |
   |      %v_short1 = ADD64 %a, %b                                               |
   |      MOV64mr [StackSlot_0], %v_short1   <--- 紧随定值点发射 Spill Store     |
   |                                                                             |
   |      ... (中间区域 %v 不再占用任何物理寄存器，压力彻底归零) ...             |
   |                                                                             |
   |      %v_short2 = MOV64rm [StackSlot_0]  <--- 紧邻使用点发射 Reload Load     |
   |      USE64 %v_short2                                                        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

活跃区间切分 (Live Range Splitting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若一个变量跨越了整个函数，但在进入内层热循环时寄存器不足，全量溢出该变量会导致循环体内每次迭代都执行 Reload。
**区间切分** 将长区间在循环入口前切断并溢出入栈，在循环出口后重新加载，**确保循环体内部核心代码不受溢出干扰**。

栈槽着色复用算法 (Stack Slot Coloring)
--------------------------------------

朴素编译器为每一个被溢出的虚拟变量独立分配一个 8 字节栈槽。当函数中有 50 个变量溢出时，栈帧将额外膨胀 400 字节，直接导致局部变量跨越多个 L1 缓存行。

栈槽冲突图与着色定理
~~~~~~~~~~~~~~~~~~~~

**定理（Stack Slot Reusability）**：
两个溢出变量 $v_1$ 与 $v_2$ 的物理栈槽可以被合并复用为同一个内存偏移地址，**当且仅当 $v_1$ 的溢出有效区间（从 Store 到最后一次 Reload）与 $v_2$ 的溢出有效区间完全不重叠（Disjoint）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     栈槽冲突图与着色合并 (Slot Coloring) 状态机             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 时间轴上的溢出区间生命周期 ]:                                           |
   |      Slot A (v1): [ 周期 10 --------> 周期 30 ]                             |
   |      Slot B (v2):               [ 周期 20 --------> 周期 50 ]               |
   |      Slot C (v3):                                  [ 周期 60 ----> 周期 80 ]|
   |                                                                             |
   |   [ 栈槽冲突图 (Slot Interference Graph) ]:                                 |
   |      (Slot A) <--- 冲突边 ---> (Slot B)                                     |
   |      (Slot C) 与 A、B 均无冲突!                                             |
   |                                                                             |
   |   [ 着色合并结果 (Physical Stack Frame Layout) ]:                           |
   |      * 物理栈槽 0 (Offset -8)  : 分配给 Slot A，在周期 30 后复用给 Slot C!   |
   |      * 物理栈槽 1 (Offset -16) : 分配给 Slot B                              |
   |                                                                             |
   |   * 收益: 栈帧溢出空间由 24 字节压缩至 16 字节，内存节省 33.3%              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

微架构热路径保护：存储转发 (STLF) 优化
--------------------------------------

现代 CPU 包含高效的 **存储到加载转发（Store-to-Load Forwarding, STLF）** 硬件机制。当 CPU 刚刚执行完对某地址的 ``store`` 且数据尚未写回 L1 缓存时，紧随其后的同地址 ``load`` 可以直接从内部 Store Buffer 旁路拉取数据，耗时仅需 1 周期。

STLF 失败的硬件惩罚
~~~~~~~~~~~~~~~~~~~

若编译器生成的溢出指令破坏了对齐或大小匹配规则（例如使用 64 位 ``mov [rsp], rax`` 写入，却紧接着使用 32 位 ``mov ebx, [rsp+2]`` 非对齐读取），硬件转发通道将被阻塞，引发严重的 **STLF 停顿（Stall 耗时达 10~20 周期）**。
- **编译器防御法则**：栈槽着色器必须严格保证每个栈槽的起始地址与其最大访问类型的自然对齐（Natural Alignment）完全吻合。

工业级 C++ 完整溢出生成与栈槽着色复用引擎实现
--------------------------------------------

以下 C++ 源码实现了一套自包含的工业级溢出代码生成器（SpillCodeGenerator）与栈槽着色复用器（StackSlotColorer）。该实现涵盖：
1. 包含循环嵌套深度加权的溢出代价计算器（SpillCostCalculator）。
2. 重物化（Rematerialization）检测与快速常量内联。
3. 溢出指令（`SPILL_STORE`）与重载指令（`RELOAD_LOAD`）精准插入。
4. 基于生命周期区间的栈槽冲突图构建与贪心着色算法（将多个逻辑栈槽折叠为极小物理栈偏移）。
5. 端到端测试套件（验证溢出权重决策、重物化优化与栈槽零冲突物理复用）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <algorithm>
   #include <cmath>
   #include <cstdint>
   #include <cassert>

   namespace spill_engine {

   // =========================================================================
   // 1. 机器指令与变量模型
   // =========================================================================
   enum class Opcode {
       ADD,
       MUL,
       MOV_IMM,      // 可重物化常量
       SPILL_STORE,  // 写入栈槽: store reg, [slot]
       RELOAD_LOAD,  // 读取栈槽: load reg, [slot]
       RET
   };

   struct Instruction {
       uint32_t ID = 0;
       Opcode Op;
       std::string Dest;
       std::vector<std::string> Sources;
       int64_t Immediate = 0;
       int32_t AssignedSlot = -1; // 绑定的栈槽 ID
       uint32_t LoopDepth = 0;    // 所在循环嵌套深度

       std::string toString() const {
           std::string s = "  [ID " + std::to_string(ID) + ", Loop " + std::to_string(LoopDepth) + "] ";
           if (!Dest.empty()) s += Dest + " = ";
           switch (Op) {
               case Opcode::ADD: s += "add " + Sources[0] + ", " + Sources[1]; break;
               case Opcode::MUL: s += "mul " + Sources[0] + ", " + Sources[1]; break;
               case Opcode::MOV_IMM: s += "mov_imm " + std::to_string(Immediate); break;
               case Opcode::SPILL_STORE: s += "spill_store " + Sources[0] + " -> [Slot " + std::to_string(AssignedSlot) + "]"; break;
               case Opcode::RELOAD_LOAD: s += "reload_load [Slot " + std::to_string(AssignedSlot) + "]"; break;
               case Opcode::RET: s += "ret " + Sources[0]; break;
           }
           return s;
       }
   };

   struct VirtualVarInfo {
       std::string Name;
       bool IsRematerializable = false; // 是否可重物化
       int64_t RematValue = 0;
       uint32_t Degree = 1;             // 冲突图度数
       std::vector<uint32_t> DefIDs;
       std::vector<uint32_t> UseIDs;
   };

   // =========================================================================
   // 2. 溢出代价评估器 (Spill Cost Calculator)
   // =========================================================================
   class SpillCostCalculator {
   public:
       static double calculateWeight(
           const VirtualVarInfo& var,
           const std::vector<Instruction>& program)
       {
           // 1. 若可重物化，溢出代价极低 (优先选择重物化，而非内存溢出)
           if (var.IsRematerializable) {
               return 0.001; // 极低权重，最先被选中重物化消解
           }

           double totalCost = 0.0;

           // 统计所有 Def 点的 Store 开销 (按 10^LoopDepth 加权)
           for (uint32_t defId : var.DefIDs) {
               uint32_t depth = program[defId].LoopDepth;
               totalCost += 1.0 * std::pow(10.0, depth);
           }

           // 统计所有 Use 点的 Load 开销
           for (uint32_t useId : var.UseIDs) {
               uint32_t depth = program[useId].LoopDepth;
               totalCost += 1.0 * std::pow(10.0, depth);
           }

           // Chaitin 归一化公式: TotalCost / Degree
           return totalCost / static_cast<double>(std::max(1u, var.Degree));
       }
   };

   // =========================================================================
   // 3. 栈槽冲突与着色复用器 (Stack Slot Colorer)
   // =========================================================================
   struct LogicalSlotInterval {
       int32_t SlotID = -1;
       uint32_t StartTime = 0;
       uint32_t EndTime = 0;
   };

   class StackSlotColorer {
   public:
       // 基于区间重叠判定的贪心栈槽着色算法
       // 返回: 逻辑 SlotID -> 物理栈偏移 (Offset in bytes from RBP, 如 -8, -16)
       static std::unordered_map<int32_t, int32_t> colorSlots(
           const std::vector<LogicalSlotInterval>& intervals,
           size_t slotSize = 8)
       {
           std::unordered_map<int32_t, int32_t> slotToPhysicalOffset;
           if (intervals.empty()) return slotToPhysicalOffset;

           // 1. 按起始时间升序排序
           auto sortedIntervals = intervals;
           std::sort(sortedIntervals.begin(), sortedIntervals.end(),
                     [](const auto& a, const auto& b) { return a.StartTime < b.StartTime; });

           // 物理颜色记录: 颜色索引 (0, 1, 2...) -> 当前该颜色占用的最晚结束时间
           std::vector<uint32_t> colorAvailableAt;

           for (const auto& interval : sortedIntervals) {
               int assignedColor = -1;

               // 寻找首个已经过期的物理颜色
               for (size_t c = 0; c < colorAvailableAt.size(); ++c) {
                   if (colorAvailableAt[c] <= interval.StartTime) {
                       assignedColor = static_cast<int>(c);
                       colorAvailableAt[c] = interval.EndTime; // 更新占用结束时间
                       break;
                   }
               }

               // 若所有已有物理颜色均冲突，分配新物理颜色
               if (assignedColor == -1) {
                   assignedColor = static_cast<int>(colorAvailableAt.size());
                   colorAvailableAt.push_back(interval.EndTime);
               }

               // 映射为负向栈偏移: Color 0 -> -8, Color 1 -> -16 ...
               int32_t offset = -static_cast<int32_t>((assignedColor + 1) * slotSize);
               slotToPhysicalOffset[interval.SlotID] = offset;
           }

           return slotToPhysicalOffset;
       }
   };

   // =========================================================================
   // 4. 溢出代码插入器 (Spill Code Inserter)
   // =========================================================================
   class SpillCodeInserter {
   public:
       static std::vector<Instruction> insertSpillsAndReloads(
           const std::vector<Instruction>& original,
           const std::string& spilledVar,
           int32_t slotID,
           bool isRemat,
           int64_t rematImm)
       {
           std::vector<Instruction> result;
           uint32_t newIdGen = 1000;

           for (const auto& inst : original) {
               // 1. 检查操作数中是否包含需 reload 的变量
               std::vector<std::string> updatedSources;
               for (const auto& src : inst.Sources) {
                   if (src == spilledVar) {
                       std::string reloadReg = spilledVar + "_reload";
                       if (isRemat) {
                           // 重物化: 直接发射立即数加载指令
                           result.push_back({
                               ++newIdGen,
                               Opcode::MOV_IMM,
                               reloadReg,
                               {},
                               rematImm,
                               -1,
                               inst.LoopDepth
                           });
                       } else {
                           // 内存加载: 发射 RELOAD_LOAD
                           result.push_back({
                               ++newIdGen,
                               Opcode::RELOAD_LOAD,
                               reloadReg,
                               {},
                               0,
                               slotID,
                               inst.LoopDepth
                           });
                       }
                       updatedSources.push_back(reloadReg);
                   } else {
                       updatedSources.push_back(src);
                   }
               }

               // 发射原指令 (替换操作数)
               Instruction modifiedInst = inst;
               modifiedInst.Sources = updatedSources;
               result.push_back(modifiedInst);

               // 2. 检查定值目标是否为被溢出的变量
               if (inst.Dest == spilledVar && !isRemat) {
                   // 紧随定值发射 SPILL_STORE
                   result.push_back({
                       ++newIdGen,
                       Opcode::SPILL_STORE,
                       "",
                       {spilledVar},
                       0,
                       slotID,
                       inst.LoopDepth
                   });
               }
           }

           return result;
       }
   };

   } // namespace spill_engine

   // =========================================================================
   // 5. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runSpillAndSlotColoringTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 溢出代价评估、重物化与栈槽着色复用验证套件
";
       std::cout << "=======================================================

";

       using namespace spill_engine;

       // 1. 测试循环嵌套溢出代价与重物化判定
       {
           std::vector<Instruction> program = {
               {0, Opcode::MOV_IMM, "%const_val", {}, 42, -1, 0}, // 常量
               {1, Opcode::ADD,     "%hot_val",   {"%a", "%b"}, 0, -1, 2}, // 处于 2 层循环内
               {2, Opcode::ADD,     "%cold_val",  {"%c", "%d"}, 0, -1, 0}, // 外层代码
               {3, Opcode::RET,     "",           {"%hot_val"}, 0, -1, 2}
           };

           VirtualVarInfo varConst{"%const_val", true, 42, 5, {0}, {}};
           VirtualVarInfo varHot{"%hot_val", false, 0, 4, {1}, {3}};
           VirtualVarInfo varCold{"%cold_val", false, 0, 8, {2}, {}};

           double wConst = SpillCostCalculator::calculateWeight(varConst, program);
           double wHot   = SpillCostCalculator::calculateWeight(varHot, program);
           double wCold  = SpillCostCalculator::calculateWeight(varCold, program);

           std::cout << "[测试 1: 溢出代价评估与权重计算]:
"
                     << "  %const_val (可重物化) 权重 = " << wConst << " (极低，优先重物化)
"
                     << "  %hot_val   (2层循环内) 权重 = " << wHot << " (高阻抗，坚决保护在寄存器)
"
                     << "  %cold_val  (外层直线码) 权重 = " << wCold << " (低代价，优先牺牲溢出)

";

           assert(wConst < wCold);
           assert(wCold < wHot);
       }

       // 2. 测试栈槽着色复用 (Stack Slot Coloring)
       {
           // 3 个逻辑栈槽区间:
           // Slot 0: [10 -> 30]
           // Slot 1: [20 -> 50] (与 Slot 0 重叠冲突)
           // Slot 2: [60 -> 90] (与 Slot 0, 1 均不重叠，期望复用 Slot 0 的物理偏移!)
           std::vector<LogicalSlotInterval> intervals = {
               {0, 10, 30},
               {1, 20, 50},
               {2, 60, 90}
           };

           auto slotOffsets = StackSlotColorer::colorSlots(intervals, 8);

           std::cout << "[测试 2: 栈槽生命周期冲突着色与内存复用]:
"
                     << "  逻辑 Slot 0 (周期 10-30) -> 物理栈偏移: " << slotOffsets[0] << " 字节
"
                     << "  逻辑 Slot 1 (周期 20-50) -> 物理栈偏移: " << slotOffsets[1] << " 字节
"
                     << "  逻辑 Slot 2 (周期 60-90) -> 物理栈偏移: " << slotOffsets[2] << " 字节

";

           // 验证断言:
           // Slot 0 与 Slot 1 必须分配不同的物理偏移 (-8 与 -16)
           assert(slotOffsets[0] != slotOffsets[1]);
           // Slot 2 与 Slot 0 无冲突，必须成功复用相同的物理偏移 (-8)
           assert(slotOffsets[2] == slotOffsets[0]);
           std::cout << "  -> 成功将 3 个逻辑溢出槽压缩至 2 个物理栈单元，栈帧体积节省 33.3%。

";
       }

       // 3. 测试溢出 Store 与 Reload 代码精准生成
       {
           std::vector<Instruction> raw = {
               {0, Opcode::ADD, "%spilled", {"%x", "%y"}, 0, -1, 0},
               {1, Opcode::MUL, "%res",     {"%spilled", "%z"}, 0, -1, 0}
           };

           auto lowered = SpillCodeInserter::insertSpillsAndReloads(raw, "%spilled", 0, false, 0);

           std::cout << "[测试 3: 插入溢出与重载代码后生成的机器指令流]:
";
           for (const auto& inst : lowered) std::cout << inst.toString() << "
";

           assert(lowered.size() == 4);
           assert(lowered[1].Op == Opcode::SPILL_STORE && lowered[1].AssignedSlot == 0);
           assert(lowered[2].Op == Opcode::RELOAD_LOAD && lowered[2].AssignedSlot == 0);
           std::cout << "  -> 溢出 Store 与 Reload 指令插入位置完全正确。

";
       }

       std::cout << "  -> 溢出代码生成与栈槽着色复用引擎测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展现了溢出控制与栈槽复用的核心微架构规律：

1. **热路径零溢出保护**：``SpillCostCalculator`` 通过静态循环加权，准确为处于 2 层循环内的变量赋予高达 $50.0$ 的代价权重，而在外层直线的变量代价仅为 $0.125$。这使分配器坚决保护热点变量长驻寄存器，彻底杜绝了循环内频繁访存导致的性能塌陷。
2. **栈槽着色物理折叠**：在测试 2 中，``StackSlotColorer`` 精准检测到逻辑槽 2 的生命周期起始（周期 60）晚于逻辑槽 0 的生命周期结束（周期 30），果断将物理偏移 ``-8`` 分配给槽 2。这从数学上证明了图着色原理不仅适用于寄存器，同样能够大幅压缩物理栈帧空间，使函数工作集紧凑驻留在 CPU L1 数据缓存中。

小结与下章导读
--------------

本章系统解构了现代编译器后端在寄存器分配溢出处理中的核心理论与工程技术：

1. **溢出代价加权模型**：推导了基于循环嵌套指数加权的 $	ext{TotalCost}$ 计算与 Chaitin 节点度数归一化仲裁法则。
2. **重物化优化机制**：阐明了利用单周期立即数加载与帧地址计算替代内存栈读写的性能优势。
3. **溢出指令插入时序**：解构了紧随定值点的 Spill Store 与紧邻使用点的 Reload Load 生成规范及活跃区间切分策略。
4. **栈槽着色复用算法**：形式化证明了非重叠溢出区间的物理栈偏移合并定理，展示了栈帧压缩对 L1 D-Cache 命中率的提升。

在完成了寄存器分配与溢出栈槽的收敛后，编译器后端必须正式构建函数的物理栈帧结构。在第 7 模块第 4 节 **栈帧物理布局与函数序言/尾声：RBP/RSP 调整、Red Zone 保护区、动态全栈对齐与寄存器保护（``07_register_allocation_stack_and_abi/04_stack_frame_layout_prologue_and_epilogue.rst``）** 中，我们将深入剖析标准栈帧布局模型、Callee-Saved 寄存器保存与恢复时序、函数序言（Prologue）与尾声（Epilogue）发射、x86-64 128 字节 Red Zone 优化，以及面向 SIMD 向量指令的动态全栈对齐（Dynamic Stack Realignment）实现。
