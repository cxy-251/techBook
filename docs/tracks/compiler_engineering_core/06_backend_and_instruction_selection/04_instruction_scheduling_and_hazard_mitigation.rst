====================================================================================================
指令调度与冒险规避：数据冒险 (RAW/WAR/WAW)、流水线延迟槽、列表调度 (List Scheduling)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 3 节（``06_backend_and_instruction_selection/03_machine_ir_and_pseudo_instruction_expansion.rst``）中，我们系统剖析了 Machine IR（MIR）的物理对象拓扑、子寄存器别名树、目标伪指令分阶段展开状态机以及前置指令调度的基本概念。当指令被合法映射为机器级操作码后，处理器微架构的硬件流水线特性直接决定了指令序列的最终执行吞吐率。在现代超标量（Superscalar）、乱序执行（Out-of-Order, OOO）以及经典按序（In-Order）处理器中，指令之间的硬件冲突与资源争用若未在编译期妥善重排，将引发灾难性的硬件流水线停顿（Pipeline Stalls）。本章深入剖析处理器微架构的三大物理冒险（结构冒险、数据冒险 RAW/WAR/WAW、控制冒险）、经典 RISC 架构的分支延迟槽（Branch Delay Slot）与加载延迟槽填充算法、基于关键路径高度与资源争用矩阵的形式化列表调度（List Scheduling）算法，以及在寄存器分配后（Post-RA）直面物理寄存器约束的后置调度优化。

硬件微架构流水线三大冒险物理模型
--------------------------------

在多级流水线 CPU 中，指令执行被切分为取指（IF）、译码（ID）、执行（EX）、访存（MEM）与写回（WB）等离散时钟周期。当指令流在硬件中推进时，会面临三类物理冒险（Hazards）：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        CPU 流水线三大物理冒险拓扑结构                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. 结构冒险 (Structural Hazard) ]                                       |
   |      多条指令同时争用同一物理执行单元 (如同一时钟周期仅有 1 个 Load/Store 端口)|
   |                                                                             |
   |   [ 2. 数据冒险 (Data Hazard) ]                                             |
   |      - RAW (Read-After-Write) : 真数据依赖 (True Dep)，结果未就绪即被读取    |
   |      - WAR (Write-After-Read) : 反依赖 (Anti Dep)，后指令抢先写覆盖前指令读取|
   |      - WAW (Write-After-Write): 输出依赖 (Output Dep)，后指令抢先写覆盖结果 |
   |                                                                             |
   |   [ 3. 控制冒险 (Control Hazard) ]                                          |
   |      分支跳转目标在流水线深处才能确定，导致后续预取指令全部作废冲刷 (Flush) |
   |                                                                             |
   +-----------------------------------------------------------------------------+

三大数据冒险形式化对比
~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 数据冒险分类、成因与编译器应对策略
   :widths: 18 32 50
   :header-rows: 1
   :class: tight-table

   * - 冒险类型
     - 形式化数学定义
     - 编译器调度与硬件协同机理
   * - **RAW (真依赖)**
     - $I_1: 	ext{Write}(R), \ I_2: 	ext{Read}(R)$，且 $I_1$ 先于 $I_2$
     - **硬性延迟**：$I_2$ 必须等待 $I_1$ 执行完毕并将结果旁路转发（Bypass）；调度器通过插入无关指令拉开两者距离
   * - **WAR (反依赖)**
     - $I_1: 	ext{Read}(R), \ I_2: 	ext{Write}(R)$，且 $I_1$ 先于 $I_2$
     - **伪依赖（名字相关）**：由寄存器名字复用引起；Pre-RA 阶段在虚拟寄存器上不存在；Post-RA 阶段必须严禁将 $I_2$ 跨越 $I_1$ 提前
   * - **WAW (输出依赖)**
     - $I_1: 	ext{Write}(R), \ I_2: 	ext{Write}(R)$，且 $I_1$ 先于 $I_2$
     - **伪依赖（名字相关）**：确保寄存器最终保存 $I_2$ 的最新定值；Post-RA 阶段禁止调换两者先后写入顺序

经典流水线延迟槽 (Delay Slots) 填充算法
---------------------------------------

在经典 RISC 处理器（如 MIPS、SPARC）中，为了最大化流水线效率，硬件在分支指令或加载指令之后紧跟一个时钟周期的 **延迟槽（Delay Slot）**。

分支延迟槽执行语义
~~~~~~~~~~~~~~~~~~

**硬件契约**：无论条件分支是否发生跳转（Taken 或 Not-Taken），紧随其后的分支延迟槽内的指令 **无条件必然被执行**。

分支延迟槽四大填充策略
~~~~~~~~~~~~~~~~~~~~~~

编译器通过以下四级策略寻找安全指令填充延迟槽，以避免浪费地发射空操作 ``NOP``：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     分支延迟槽 (Branch Delay Slot) 四大填充策略             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 策略 1: 自前驱代码段上提 (From Before Branch) - 最优策略 ]              |
   |      * 在分支之前寻找一条与分支条件无依赖关系的独立指令                     |
   |      * 将其下移填入延迟槽，分支前执行等价于槽内执行                         |
   |                                                                             |
   |   [ 策略 2: 自跳转目标块复制 (From Target / Taken Path) ]                   |
   |      * 从跳转目标基本块的头部复制第一条指令填入延迟槽                       |
   |      * 约束: 若分支未命中，该指令不能产生破坏落空路径的不可逆副作用         |
   |                                                                             |
   |   [ 策略 3: 自落空路径提拔 (From Fallthrough Path) ]                        |
   |      * 从分支未命中的紧邻后继块提取首条指令填入延迟槽                       |
   |      * 约束: 若分支命中跳转，该指令不能破坏跳转目标的状态                   |
   |                                                                             |
   |   [ 策略 4: NOP 兜底保底 (Fallback NOP) ]                                   |
   |      * 当上述优化均无法证明安全性时，填充单条 NOP 空操作保证正确性          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

依赖有向无环图 (SchedDAG) 与列表调度 (List Scheduling)
------------------------------------------------------

**列表调度（List Scheduling）** 是编译器后端最基础且最具威力的启发式指令重排算法。它将基本块内的指令依赖抽象为带权有向无环图（Scheduling DAG, SchedDAG）。

SchedDAG 数据依赖图构建
~~~~~~~~~~~~~~~~~~~~~~~

SchedDAG 节点为机器指令 $I_i$，有向边 $e = (I_1 	o I_2)$ 表示执行偏序约束，边权重 $w(e)$ 表示 **流水线执行延迟（Latency）**：

.. math::

   w(I_1 	o I_2) = 	ext{Latency}(I_1)

若 $I_1$ 为内存加载指令（Latency = 3），$I_2$ 消费其结果，则边权重为 3，代表 $I_2$ 必须在 $I_1$ 发射至少 3 个周期后方可发射。

节点高度 (Height / Critical Path) 与就绪优先级
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在调度中始终优先推进最耗时的关键执行链路，调度器递归计算每个节点到汇聚节点（Sink）的 **关键路径高度（Height）**：

.. math::

   	ext{Height}(u) = \max \left( 	ext{Latency}(u), \ \max_{v \in 	ext{Succs}(u)} (	ext{Height}(v) + w(u 	o v)) \right)

- $	ext{Height}(u)$ 越大的节点，代表其后续拖拽的依赖链路越长，在就绪队列中拥有 **最高调度优先级**。

列表调度状态机算法全流程
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        列表调度 (List Scheduling) 算法状态机                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. [ 构建 SchedDAG ]: 遍历基本块指令，生成 RAW、WAR、WAW 与内存屏障依赖边|
   |                                                                             |
   |   2. [ 计算节点高度 ]: 自底向上拓扑反向遍历，计算每条指令的 Height          |
   |                                                                             |
   |   3. [ 初始化就绪队列 (ReadyQueue) ]: 将所有入度 InDegree == 0 的节点压入优先队列 |
   |      (优先队列按 Height 降序排列)                                           |
   |                                                                             |
   |   4. [ 模拟时钟时序推进 (Cycle-by-Cycle Loop) ]:                           |
   |      While (已发射指令数 < 总指令数):                                       |
   |         * 检查当前就绪队列中是否存在无流水线停顿的节点:                     |
   |            - 若存在: 弹出 Height 最高且资源端口匹配的节点 I 发射;           |
   |                      记录其完成时钟 CycleFinish = CurrentCycle + Latency(I);|
   |            - 若不存在 (所有就绪指令前驱仍在执行中): 产生 1 周期停顿 (Stall)  |
   |         * CurrentCycle++;                                                   |
   |         * 检查已完成指令，将其后继节点的 InDegree 递减;                     |
   |         * 若后继节点 InDegree == 0，将其正式推入 ReadyQueue;                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Pre-RA 调度 vs Post-RA 调度全景对比
-----------------------------------

工业级后端通常在寄存器分配的前后各执行一次列表调度：

.. list-table:: Pre-RA 指令调度与 Post-RA 指令调度核心差异
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - Pre-RA 调度 (寄存器分配前)
     - Post-RA 调度 (寄存器分配后)
   * - **操作寄存器对象**
     - 无限虚拟寄存器（Virtual Registers）
     - 有限物理寄存器（Physical Registers）
   * - **依赖边模型**
     - 仅包含纯粹的 RAW 数据依赖与内存屏障
     - 显式包含物理寄存器复用引入的 WAR 与 WAW 伪依赖
   * - **调度核心目标**
     - **平衡 ILP 吞吐与寄存器压力**，避免将活跃区间拉得过长导致溢出
     - **精准对齐硬件发射端口与精确时钟延迟**，消除溢出读写引入的微架构气泡
   * - **执行自由度**
     - 极高（不受物理寄存器分配方案的束缚）
     - 较低（受物理寄存器拓扑强约束）

工业级 C++ 完整列表调度与延迟槽填充引擎实现
--------------------------------------------

以下 C++ 源码实现了一套自包含的工业级列表调度器（ListScheduler）与分支延迟槽填充器（DelaySlotFiller）。该实现涵盖：
1. 包含 RAW 延迟权重的 SchedDAG 依赖图构建器。
2. 递归关键路径高度（Critical Path Height）计算。
3. 模拟时钟推进的优先队列列表调度状态机。
4. 基于前驱指令上提的分支延迟槽安全填充算法。
5. 端到端测试套件（验证多周期 Load 延迟掩盖与分支延迟槽 NOP 消除）。

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

   namespace scheduler_engine {

   // =========================================================================
   // 1. 指令模型与 SchedDAG 依赖图
   // =========================================================================
   enum class OpType {
       LOAD,      // 内存加载: Latency = 3 周期
       ALU_ADD,   // 整数加法: Latency = 1 周期
       ALU_MUL,   // 整数乘法: Latency = 2 周期
       BRANCH,    // 控制分支: Latency = 1 周期
       NOP        // 空操作:   Latency = 1 周期
   };

   struct SchedInstruction {
       uint32_t ID = 0;
       OpType Op;
       std::string Dest;
       std::vector<std::string> Sources;
       uint32_t Latency = 1;
       bool HasSideEffects = false;

       std::string toString() const {
           std::string s = "  [ID " + std::to_string(ID) + "] ";
           if (!Dest.empty()) s += Dest + " = ";
           switch (Op) {
               case OpType::LOAD:    s += "load [" + Sources[0] + "]"; break;
               case OpType::ALU_ADD: s += "add " + Sources[0] + ", " + Sources[1]; break;
               case OpType::ALU_MUL: s += "mul " + Sources[0] + ", " + Sources[1]; break;
               case OpType::BRANCH:  s += "branch " + Sources[0]; break;
               case OpType::NOP:     s += "nop"; break;
           }
           s += " (Latency=" + std::to_string(Latency) + ")";
           return s;
       }
   };

   struct DAGEdge {
       uint32_t ToNode = 0;
       uint32_t Latency = 1;
   };

   struct DAGNode {
       SchedInstruction Instr;
       uint32_t InDegree = 0;
       std::vector<DAGEdge> Successors;
       uint32_t Height = 0; // 关键路径高度
       uint32_t EarliestCycle = 0; // 最早可发射周期
   };

   // =========================================================================
   // 2. 列表调度器 (List Scheduler)
   // =========================================================================
   class ListScheduler {
   public:
       static std::vector<SchedInstruction> schedule(const std::vector<SchedInstruction>& instrs) {
           if (instrs.size() <= 1) return instrs;

           size_t n = instrs.size();
           std::vector<DAGNode> dag(n);
           std::unordered_map<std::string, uint32_t> lastDef;

           // 1. 构建 SchedDAG 并建立 RAW 依赖
           for (size_t i = 0; i < n; ++i) {
               dag[i].Instr = instrs[i];

               for (const auto& src : instrs[i].Sources) {
                   if (lastDef.count(src)) {
                       uint32_t producer = lastDef[src];
                       uint32_t lat = instrs[producer].Latency;
                       dag[producer].Successors.push_back({static_cast<uint32_t>(i), lat});
                       dag[i].InDegree++;
                   }
               }
               if (!instrs[i].Dest.empty()) {
                   lastDef[instrs[i].Dest] = static_cast<uint32_t>(i);
               }
           }

           // 2. 自底向上计算关键路径高度 (Height)
           for (int i = static_cast<int>(n) - 1; i >= 0; --i) {
               uint32_t maxChildHeight = 0;
               for (const auto& edge : dag[i].Successors) {
                   uint32_t childH = dag[edge.ToNode].Height + edge.Latency;
                   maxChildHeight = std::max(maxChildHeight, childH);
               }
               dag[i].Height = dag[i].Instr.Latency + maxChildHeight;
           }

           // 3. 就绪队列调度状态机
           auto cmp = [&](uint32_t a, uint32_t b) {
               // 关键路径越长，优先级越高
               return dag[a].Height < dag[b].Height;
           };
           std::priority_queue<uint32_t, std::vector<uint32_t>, decltype(cmp)> readyQueue(cmp);

           for (size_t i = 0; i < n; ++i) {
               if (dag[i].InDegree == 0) readyQueue.push(static_cast<uint32_t>(i));
           }

           std::vector<SchedInstruction> scheduled;
           uint32_t currentCycle = 0;
           std::unordered_map<uint32_t, uint32_t> finishCycle;

           while (scheduled.size() < n) {
               // 寻找满足最早发射周期的最高优先级节点
               std::vector<uint32_t> tempStash;
               int chosen = -1;

               while (!readyQueue.empty()) {
                   uint32_t candidate = readyQueue.top();
                   readyQueue.pop();

                   if (dag[candidate].EarliestCycle <= currentCycle) {
                       chosen = static_cast<int>(candidate);
                       break;
                   } else {
                       tempStash.push_back(candidate);
                   }
               }

               // 将未选中的就绪节点归还队列
               for (uint32_t stashed : tempStash) {
                   readyQueue.push(stashed);
               }

               if (chosen != -1) {
                   // 发射选中的指令
                   scheduled.push_back(dag[chosen].Instr);
                   uint32_t finishTime = currentCycle + dag[chosen].Instr.Latency;
                   finishCycle[chosen] = finishTime;

                   // 解除后继依赖并更新后继的最早发射时间
                   for (const auto& edge : dag[chosen].Successors) {
                       dag[edge.ToNode].EarliestCycle = std::max(dag[edge.ToNode].EarliestCycle, finishTime);
                       dag[edge.ToNode].InDegree--;
                       if (dag[edge.ToNode].InDegree == 0) {
                           readyQueue.push(edge.ToNode);
                       }
                   }
               }
               // 时钟推进
               currentCycle++;
           }

           return scheduled;
       }
   };

   // =========================================================================
   // 3. 分支延迟槽填充器 (Branch Delay Slot Filler)
   // =========================================================================
   class DelaySlotFiller {
   public:
       static std::vector<SchedInstruction> fillDelaySlots(const std::vector<SchedInstruction>& instrs) {
           std::vector<SchedInstruction> result;

           for (size_t i = 0; i < instrs.size(); ++i) {
               if (instrs[i].Op == OpType::BRANCH) {
                   // 策略 1: 尝试从前驱代码中寻找一条与分支条件无依赖的指令下移填入延迟槽
                   if (!result.empty() && result.back().Op != OpType::BRANCH && !result.back().HasSideEffects) {
                       const auto& candidate = result.back();
                       // 检查 candidate 的 Dest 是否被分支使用
                       bool isUsedInBranch = false;
                       for (const auto& src : instrs[i].Sources) {
                           if (candidate.Dest == src) {
                               isUsedInBranch = true;
                               break;
                           }
                       }

                       if (!isUsedInBranch) {
                           SchedInstruction delaySlotInst = result.back();
                           result.pop_back(); // 从分支前移出
                           result.push_back(instrs[i]);       // 发射分支指令
                           result.push_back(delaySlotInst);   // 填入延迟槽!
                           continue;
                       }
                   }

                   // 无法前移时，使用 NOP 兜底
                   result.push_back(instrs[i]);
                   result.push_back({999, OpType::NOP, "", {}, 1, false});
               } else {
                   result.push_back(instrs[i]);
               }
           }

           return result;
       }
   };

   } // namespace scheduler_engine

   // =========================================================================
   // 4. 端到端测试与微架构调度验证套件
   // =========================================================================
   namespace test {

   inline void runInstructionSchedulingTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 列表调度 (List Scheduling) 与分支延迟槽填充验证套件
";
       std::cout << "=======================================================

";

       using namespace scheduler_engine;

       // 1. 测试列表调度消除 RAW 加载延迟气泡
       // 原始序列:
       //   [1] r1 = load [ptr] (Latency = 3)
       //   [2] r2 = add r1, r0 (依赖 r1, 需要等待 3 周期)
       //   [3] r3 = mul x, y   (Latency = 2, 独立长耗时指令)
       //   [4] r4 = add a, b   (Latency = 1, 独立指令)
       std::vector<SchedInstruction> rawBlock;
       rawBlock.push_back({1, OpType::LOAD, "r1", {"ptr"}, 3, false});
       rawBlock.push_back({2, OpType::ALU_ADD, "r2", {"r1", "r0"}, 1, false});
       rawBlock.push_back({3, OpType::ALU_MUL, "r3", {"x", "y"}, 2, false});
       rawBlock.push_back({4, OpType::ALU_ADD, "r4", {"a", "b"}, 1, false});

       std::cout << "[测试 1: 列表调度前原始指令序列]:
";
       for (const auto& inst : rawBlock) std::cout << inst.toString() << "
";

       auto scheduled = ListScheduler::schedule(rawBlock);

       std::cout << "
[测试 1: 列表调度后优化序列 (关键路径优先)]:
";
       for (const auto& inst : scheduled) std::cout << inst.toString() << "
";

       // 核心断言: 乘法与无关加法必须被提拔到 LOAD 与 ADD 之间以完全掩盖 3 周期 Load 延迟
       assert(scheduled.size() == 4);
       assert(scheduled[0].ID == 1); // load [ptr]
       assert(scheduled[1].ID == 3); // mul x, y 优先抢占 (Height 高)
       assert(scheduled[2].ID == 4); // add a, b 紧随其后
       assert(scheduled[3].ID == 2); // r2 = add r1, r0 在 r1 就绪后最后执行
       std::cout << "  -> 关键路径列表调度成功消除全部 3 周期 Load 停顿气泡。

";

       // 2. 测试分支延迟槽安全填充
       // 序列:
       //   [10] r_calc = add x, y (独立安全指令)
       //   [11] branch r_cond     (分支指令)
       std::vector<SchedInstruction> branchSeq;
       branchSeq.push_back({10, OpType::ALU_ADD, "r_calc", {"x", "y"}, 1, false});
       branchSeq.push_back({11, OpType::BRANCH, "", {"r_cond"}, 1, false});

       std::cout << "[测试 2: 分支延迟槽填充前]:
";
       for (const auto& inst : branchSeq) std::cout << inst.toString() << "
";

       auto filled = DelaySlotFiller::fillDelaySlots(branchSeq);

       std::cout << "
[测试 2: 分支延迟槽填充后 (无 NOP 零开销插入)]:
";
       for (const auto& inst : filled) std::cout << inst.toString() << "
";

       assert(filled.size() == 2);
       assert(filled[0].ID == 11); // branch 指令排在首位
       assert(filled[1].ID == 10); // r_calc = add x, y 安全下移填入延迟槽
       std::cout << "  -> 成功将独立前驱算术指令移动至分支延迟槽，完全消除了 NOP 浪费。

";

       std::cout << "  -> 指令调度与冒险规避全套引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰印证了指令调度器在微架构层面的优化实效：

1. **关键路径延迟完美掩盖**：在测试 1 中，原本耗时为 $3 + 1 + 2 + 1 = 7$ 个周期的停顿序列，通过 SchedDAG 关键路径高度计算，调度器将长延迟的独立乘法（``MUL``，Height=2）与加法（``ADD``，Height=1）精准插入到 ``LOAD`` 与消费指令之间。在硬件执行时，4 条指令紧密重叠发射，总执行耗时直接压缩至理论极限的 4 个时钟周期，性能提升超 $40\%$。
2. **零开销分支延迟槽利用**：在测试 2 中，延迟槽填充器在证明了 ``r_calc = add x, y`` 与分支判定条件 ``r_cond`` 完全独立后，果断将其移入分支延迟槽，既保持了程序语义，又避免了发射无意义的 ``NOP`` 指令。

小结与下章导读
--------------

本章系统解构了现代编译器后端指令调度与微架构冒险规避的核心体系：

1. **流水线物理冒险模型**：剖析了结构冒险、控制冒险与数据冒险（RAW 真依赖、WAR 反依赖、WAW 输出依赖）的微架构成因。
2. **延迟槽填充策略**：推导了分支延迟槽自前驱上提、自目标复制与自落空提拔的四级安全策略。
3. **SchedDAG 与列表调度算法**：建立了以关键路径高度（Height）驱动的优先队列状态机，演示了循环周期模拟与后继依赖解锁的物理执行流。
4. **Pre-RA 与 Post-RA 调度博弈**：厘清了虚拟寄存器生命周期压力与物理寄存器伪依赖约束在不同阶段的优化分工。

在掌握了指令选择、Machine IR 建模与指令调度之后，编译器后端还必须确保生成代码在底层硬件语义层面的绝对正确性。在第 6 模块第 5 节 **后端正确性保证：ISA 标志位溢出语义、分支条件码折叠与机器码验证（``06_backend_and_instruction_selection/05_backend_correctness_and_target_flags.rst``）** 中，我们将深入剖析硬件标志位（Flags/Condition Codes）的隐式修改生命周期、分支条件码逆转折叠、溢出未定义行为在后端的保留，以及发射前的机器码健全性验证。
