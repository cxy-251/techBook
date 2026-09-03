====================================================================================================
变量生命周期与冲突图：活跃区间 (Live Interval) 分析、冲突边建立与寄存器压力评估
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 1 至第 6 模块中，我们系统剖析了编译器前端解析、中端 SSA 数据流优化以及后端代码生成基础设施（目标机模型、SelectionDAG / GlobalISel 指令选择、Machine IR 物理对象模型与指令调度）。在指令选择与前期调度阶段，指令操作数被无拘无束地赋予无限数量的 **虚拟寄存器（Virtual Registers，如 ``%0``, ``%1``, ``%2`` ...）**。然而，物理 CPU 芯片上的高速寄存器文件（Register File）是极其稀缺的硬件计算资源（例如 x86-64 仅有 16 个通用寄存器，ARM64 仅有 31 个通用寄存器）。从本章开始，我们正式开启全书第 7 模块（``07_register_allocation_stack_and_abi``），攻克编译器后端最具算法挑战性的核心领域——**寄存器分配（Register Allocation, RA）**、栈帧物理布局与 ABI 调用约定。作为寄存器分配的前提与数学基石，本章深入剖析离散程序点标定（Program Points）、跨基本块的多段活跃区间（Live Range / Live Intervals）构建、干涉冲突图（Interference Graph）拓扑形式化，以及评估微架构并发资源争用的 **寄存器压力（Register Pressure）** 评估模型。

离散程序点标定与槽位索引 (Program Points & Slot Indexing)
---------------------------------------------------------

为了精确刻画变量从被计算（Def）到被最后一次消费（Last Use）的时间跨度，编译器后端必须对机器基本块内的所有指令赋予单调递增的 **离散程序点索引（Program Points / Slot Indexes）**。

步长为 4 的四槽位索引体系
~~~~~~~~~~~~~~~~~~~~~~~~~

在工业级编译器（如 LLVM 的 ``SlotIndexes`` 分析）中，每条物理指令通常分配步长为 4 的整数索引区间 $[4k, 4k+3]$：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      LLVM 步长为 4 的细粒度槽位索引体系                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 指令 k : %v2 = ADD32rr %v0, %v1 ]                                       |
   |                                                                             |
   |      Slot 4k + 0 : EarlyClobber 槽位                                        |
   |                    用于标记在输入读取前即被破坏的特定物理寄存器             |
   |                                                                             |
   |      Slot 4k + 1 : Register / Use 槽位                                      |
   |                    操作数输入读取点 (读取 %v0 与 %v1 的物理时刻)            |
   |                                                                             |
   |      Slot 4k + 2 : Def 槽位                                                 |
   |                    指令目标值产生点 (产出 %v2 的定值时刻)                   |
   |                                                                             |
   |      Slot 4k + 3 : Dead 槽位 / 预留插入缝隙                                 |
   |                    为寄存器分配阶段就地插入溢出代码 (Spill Store/Reload)    |
   |                    以及寄存器拷贝指令 (Reg Copy) 预留空隙，无需重排全图索引 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

这种离散化设计使得编译器能够精准区分“同一条指令内输入消费与输出产出的时间先后”，并为后续插入溢出内存读写提供充裕的标定空间。

活跃范围与多段活跃区间 (Live Range & Live Intervals)
----------------------------------------------------

一个虚拟寄存器 $V$ 的 **活跃范围（Live Range）** 定义为：程序中所有能够沿控制流图到达某一使用点、且该点引用的值来自同一组定值的程序点集合。

多段连续子区间模型 (Multi-Segment Intervals)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在包含分支与循环的控制流图中，变量的活跃范围并非简单的单一连续线段，而是由多个半开区间组成的并集：

.. math::

   	ext{LiveInterval}(V) = [s_1, e_1) \cup [s_2, e_2) \cup \dots \cup [s_m, e_m)

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     控制流分支导致的多段活跃区间 (Live Range Holes)         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ BB0: Entry ] ---> 定值 %v1 (Slot 4)                                     |
   |         |                                                                   |
   |         +-----------------------+                                           |
   |         |                       |                                           |
   |         v                       v                                           |
   |   [ BB1: ThenBlock ]      [ BB2: ElseBlock ]                                |
   |   未引用 %v1              使用 %v1 (Slot 36)                                |
   |   (产生活跃空洞 Hole)           |                                           |
   |         |                       |                                           |
   |         +-----------------------+                                           |
   |         |                                                                   |
   |         v                                                                   |
   |   [ BB3: MergeBlock ] ---> 最终消费 %v1 (Slot 64)                           |
   |                                                                             |
   |   * %v1 活跃区间物理集合: [4, 16) U [32, 64)                                |
   |   * BB1 内部 [16, 32) 属于活跃空洞，物理寄存器在此区间可被其他变量安全复用! |
   |                                                                             |
   +-----------------------------------------------------------------------------+

基于后向数据流分析的活跃区间构建算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

活跃区间的构建依赖逆向数据流方程：
1. **活跃出口与活跃入口（LiveOut / LiveIn）**：

   .. math::

      	ext{LiveOut}(B) = \bigcup_{S \in 	ext{Succs}(B)} 	ext{LiveIn}(S)

   .. math::

      	ext{LiveIn}(B) = 	ext{Gen}(B) \cup (	ext{LiveOut}(B) \setminus 	ext{Kill}(B))

2. 针对每个基本块，从其底部 $	ext{LiveOut}$ 出发逆向向上扫描每条指令：
   - 若指令定值了变量 $V$，则截断 $V$ 的当前活跃子区间头部：$[4k+2, 	ext{curr\_end})$。
   - 若指令消费了变量 $U$，则开启或延伸 $U$ 的活跃子区间：$[4k+1, 	ext{curr\_end})$。

冲突图 (Interference Graph) 形式化与构建
----------------------------------------

**冲突图（Interference Graph / Conflict Graph）** 是图着色寄存器分配的绝对核心数据结构，形式化定义为一个无向图 $G = (V, E)$。

冲突图拓扑定义
~~~~~~~~~~~~~~

1. **节点集合 $V$**：
   - 包含函数内所有的虚拟寄存器（$	ext{VRegs}$）。
   - 包含所有参与调用约定或指令硬性绑定的预着色物理寄存器（Pre-colored Physical Registers，如 ``$rdi``, ``$rax``）。
2. **冲突边集合 $E$**：
   - 若两个虚拟寄存器 $u$ 与 $v$ 属于相同的寄存器类，且它们的活跃区间在时间线上存在非空交集：

   .. math::

      	ext{LiveInterval}(u) \cap 	ext{LiveInterval}(v) 
eq \emptyset \implies (u, v) \in E

   - **物理意义**：$(u, v) \in E$ 意味着 $u$ 与 $v$ 在某一时刻同时处于活跃状态，**二者绝对不能被分配给同一个物理寄存器**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       冲突图 (Interference Graph) 拓扑与着色                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 活跃区间重叠时间线 ]:                                                   |
   |      Slot:  0    4    8    12   16   20   24   28   32                      |
   |      %v1:   [========================)                                      |
   |      %v2:        [========================)                                 |
   |      %v3:                  [========================)                       |
   |      %v4:                                      [====)                       |
   |                                                                             |
   |   [ 派生的冲突图 G = (V, E) ]:                                              |
   |                                                                             |
   |             (%v1: Color 1) <======== 冲突边 ========> (%v2: Color 2)        |
   |                   \                                      /                  |
   |                    \                                    /                   |
   |                   冲突边                              冲突边                |
   |                      \                                /                     |
   |                       v                              v                      |
   |                                 (%v3: Color 3)                              |
   |                                       |                                     |
   |                                     冲突边                                  |
   |                                       |                                     |
   |                                       v                                     |
   |                                 (%v4: Color 1)  <--- 与 %v1 无冲突，可复用! |
   |                                                                             |
   +-----------------------------------------------------------------------------+

特殊场景：寄存器拷贝指令 (COPY Coalescing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于寄存器拷贝指令 ``%v2 = COPY %v1``：
- 虽然在拷贝点处 ``%v1`` 与 ``%v2`` 同时存在，但如果二者在此后不与其他变量发生相交冲突，编译器可以通过 **寄存器合并（Coalescing）** 将 ``%v1`` 与 ``%v2`` 合并为同一个节点，完全消除这一无谓的物理搬移指令。

寄存器压力 (Register Pressure) 评估模型
---------------------------------------

**寄存器压力（Register Pressure）** 是指在程序某一特定执行时刻，同时存活并争用物理寄存器的变量总数。

瞬时压力计算公式
~~~~~~~~~~~~~~~~

在程序点 $p$ 处，寄存器类 $R$ 的瞬时寄存器压力定义为覆盖该点的活跃区间集合的基数：

.. math::

   	ext{Pressure}_R(p) = \Big| \big\{ v \in 	ext{VRegs}(R) \ \big| \ p \in 	ext{LiveInterval}(v) \big\} \Big|

.. list-table:: 寄存器压力状态分类与微架构决策矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 压力状态
     - 判定准则 ($K$ 为可用物理寄存器数)
     - 后端编译器微架构决策
   * - **安全低压区**
     - $\max_{p} 	ext{Pressure}(p) \le K$
     - **全量无损分配**：所有虚拟寄存器均可直接着色，绝对不发生栈内存溢出（Zero Spills）
   * - **局部过载区**
     - 仅在局部循环或基本块中 $	ext{Pressure}(p) > K$
     - **活跃区间切分（Live Range Splitting）**：在过载区域边缘将变量溢出至栈槽，离开过载区后重新载入寄存器
   * - **全局高压溢出**
     - 大范围连续区域 $	ext{Pressure}(p) \gg K$
     - **溢出代码生成（Spill Code Generation）**：挑选溢出权重最低（Loop Weight / Spill Cost 最低）的变量全局降级为栈内存访问

工业级 C++ 完整活跃区间与冲突图引擎实现
----------------------------------------

以下 C++ 源码实现了一套自包含的工业级活跃区间分析器（LivenessAnalyzer）、冲突图构建器（InterferenceGraph）与寄存器压力评估器（RegisterPressureTracker）。该实现涵盖：
1. 具备 Def/Use 细粒度槽位索引的机器指令模型。
2. 包含多段连续区间的 `LiveInterval` 物理数据结构。
3. 基于邻接表与度数统计的冲突图（Interference Graph）构建。
4. 逐程序点瞬时寄存器压力计算与峰值过载探测。
5. 端到端测试套件（验证区间重叠判定、冲突边建立与着色冲突度）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>

   namespace liveness_engine {

   // =========================================================================
   // 1. 槽位索引与活跃区间数据结构
   // =========================================================================
   struct LiveSegment {
       uint32_t Start = 0; // 包含
       uint32_t End   = 0; // 不包含 (半开区间 [Start, End))

       bool contains(uint32_t pt) const noexcept {
           return pt >= Start && pt < End;
       }

       bool overlaps(const LiveSegment& o) const noexcept {
           return std::max(Start, o.Start) < std::min(End, o.End);
       }
   };

   class LiveInterval {
   public:
       std::string RegName;
       std::vector<LiveSegment> Segments;

       explicit LiveInterval(std::string name) : RegName(std::move(name)) {}

       void addSegment(uint32_t start, uint32_t end) {
           if (start >= end) return;
           LiveSegment seg{start, end};
           // 保持区间有序并合并相邻重叠段
           std::vector<LiveSegment> merged;
           bool inserted = false;
           for (const auto& s : Segments) {
               if (!inserted && seg.End < s.Start) {
                   merged.push_back(seg);
                   inserted = true;
               }
               if (seg.overlaps(s) || seg.End == s.Start || s.End == seg.Start) {
                   seg.Start = std::min(seg.Start, s.Start);
                   seg.End   = std::max(seg.End, s.End);
               } else {
                   merged.push_back(s);
               }
           }
           if (!inserted) merged.push_back(seg);
           Segments = std::move(merged);
       }

       [[nodiscard]] bool liveAt(uint32_t pt) const noexcept {
           for (const auto& seg : Segments) {
               if (seg.contains(pt)) return true;
           }
           return false;
       }

       [[nodiscard]] bool overlaps(const LiveInterval& other) const noexcept {
           for (const auto& s1 : Segments) {
               for (const auto& s2 : other.Segments) {
                   if (s1.overlaps(s2)) return true;
               }
           }
           return false;
       }

       std::string toString() const {
           std::string s = RegName + ": ";
           for (const auto& seg : Segments) {
               s += "[" + std::to_string(seg.Start) + ", " + std::to_string(seg.End) + ") ";
           }
           return s;
       }
   };

   // =========================================================================
   // 2. 冲突图 (Interference Graph) 物理模型
   // =========================================================================
   class InterferenceGraph {
   public:
       std::vector<std::string> Nodes;
       std::unordered_map<std::string, std::unordered_set<std::string>> AdjacencyList;

       void addNode(const std::string& node) {
           if (!AdjacencyList.count(node)) {
               Nodes.push_back(node);
               AdjacencyList[node] = {};
           }
       }

       void addEdge(const std::string& u, const std::string& v) {
           if (u == v) return;
           addNode(u);
           addNode(v);
           AdjacencyList[u].insert(v);
           AdjacencyList[v].insert(u);
       }

       [[nodiscard]] bool hasEdge(const std::string& u, const std::string& v) const {
           if (!AdjacencyList.count(u)) return false;
           return AdjacencyList.at(u).count(v) != 0;
       }

       [[nodiscard]] size_t degree(const std::string& node) const {
           if (!AdjacencyList.count(node)) return 0;
           return AdjacencyList.at(node).size();
       }

       void dump() const {
           std::cout << "Interference Graph Topology (Nodes = " << Nodes.size() << "):
";
           for (const auto& u : Nodes) {
               std::cout << "  " << u << " (deg=" << degree(u) << ") -> { ";
               for (const auto& v : AdjacencyList.at(u)) {
                   std::cout << v << " ";
               }
               std::cout << "}
";
           }
       }
   };

   // =========================================================================
   // 3. 活跃性分析器与寄存器压力追踪器
   // =========================================================================
   struct SimpleInstruction {
       uint32_t Slot = 0;
       std::vector<std::string> Defs;
       std::vector<std::string> Uses;
   };

   class LivenessAnalyzer {
   public:
       static std::unordered_map<std::string, LiveInterval>
       computeIntervals(const std::vector<SimpleInstruction>& instrs) {
           std::unordered_map<std::string, uint32_t> firstDef;
           std::unordered_map<std::string, uint32_t> lastUse;
           std::unordered_set<std::string> allVars;

           for (const auto& inst : instrs) {
               for (const auto& d : inst.Defs) {
                   allVars.insert(d);
                   if (!firstDef.count(d)) firstDef[d] = inst.Slot;
               }
               for (const auto& u : inst.Uses) {
                   allVars.insert(u);
                   lastUse[u] = inst.Slot + 1; // 延伸到当前指令的使用槽位
               }
           }

           std::unordered_map<std::string, LiveInterval> intervals;
           for (const auto& var : allVars) {
               uint32_t start = firstDef.count(var) ? firstDef[var] : 0;
               uint32_t end   = lastUse.count(var) ? lastUse[var] : (start + 2);
               LiveInterval li(var);
               li.addSegment(start, end);
               intervals.insert({var, li});
           }

           return intervals;
       }

       static InterferenceGraph buildGraph(const std::unordered_map<std::string, LiveInterval>& intervals) {
           InterferenceGraph g;
           std::vector<const LiveInterval*> list;
           for (const auto& pair : intervals) {
               g.addNode(pair.first);
               list.push_back(&pair.second);
           }

           for (size_t i = 0; i < list.size(); ++i) {
               for (size_t j = i + 1; j < list.size(); ++j) {
                   if (list[i]->overlaps(*list[j])) {
                       g.addEdge(list[i]->RegName, list[j]->RegName);
                   }
               }
           }

           return g;
       }

       static size_t computePeakPressure(
           const std::unordered_map<std::string, LiveInterval>& intervals,
           uint32_t maxSlot)
       {
           size_t peak = 0;
           for (uint32_t pt = 0; pt <= maxSlot; ++pt) {
               size_t current = 0;
               for (const auto& pair : intervals) {
                   if (pair.second.liveAt(pt)) ++current;
               }
               peak = std::max(peak, current);
           }
           return peak;
       }
   };

   } // namespace liveness_engine

   // =========================================================================
   // 4. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   inline void runLivenessAndInterferenceTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 活跃区间 (Live Intervals) 与冲突图构建测试套件
";
       std::cout << "=======================================================

";

       using namespace liveness_engine;

       // 模拟直线指令序列 (槽位以 4 递增):
       //   [Slot 4]  %v1 = LOAD [a]
       //   [Slot 8]  %v2 = LOAD [b]
       //   [Slot 12] %v3 = ADD %v1, %v2
       //   [Slot 16] %v4 = MUL %v3, %v2   <--- %v2 在此最后使用
       //   [Slot 20] %v5 = ADD %v3, %v4   <--- %v3 在此最后使用
       //   [Slot 24] RET %v5
       std::vector<SimpleInstruction> instrs = {
           {4,  {"%v1"}, {}},
           {8,  {"%v2"}, {}},
           {12, {"%v3"}, {"%v1", "%v2"}},
           {16, {"%v4"}, {"%v3", "%v2"}},
           {20, {"%v5"}, {"%v3", "%v4"}},
           {24, {},      {"%v5"}}
       };

       auto intervals = LivenessAnalyzer::computeIntervals(instrs);

       std::cout << "[测试 1: 变量活跃区间分析结果]:
";
       for (const auto& pair : intervals) {
           std::cout << "  " << pair.second.toString() << "
";
       }

       // 验证断言:
       // 1. %v1 存活于 [4, 13)
       // 2. %v2 存活于 [8, 17)
       // 3. %v3 存活于 [12, 21)
       // 4. %v4 存活于 [16, 21)
       // 5. %v5 存活于 [20, 25)
       assert(intervals.at("%v1").liveAt(10));
       assert(!intervals.at("%v1").liveAt(14)); // 14 处 %v1 已死亡

       // 构建冲突图
       auto graph = LivenessAnalyzer::buildGraph(intervals);
       std::cout << "
[测试 2: 冲突图构建输出]:
";
       graph.dump();

       // 验证冲突边:
       // %v1 与 %v2 在 [8, 13) 重叠 -> 存在边
       assert(graph.hasEdge("%v1", "%v2"));
       // %v1 与 %v3 在 [12, 13) 重叠 -> 存在边
       assert(graph.hasEdge("%v1", "%v3"));
       // %v1 与 %v4 (16开始) 无重叠 -> 绝无冲突边! (可复用同物理寄存器)
       assert(!graph.hasEdge("%v1", "%v4"));
       // %v2 与 %v3, %v4 均有重叠
       assert(graph.hasEdge("%v2", "%v3"));
       assert(graph.hasEdge("%v2", "%v4"));

       std::cout << "  -> 核心冲突边断言完全通过 (%v1 与 %v4 成功证明无干涉，可安全复用物理槽位)。

";

       // 计算峰值寄存器压力
       size_t peakPressure = LivenessAnalyzer::computePeakPressure(intervals, 28);
       std::cout << "[测试 3: 峰值寄存器压力评估]: Peak Pressure = " << peakPressure << " 个同时活跃变量
";
       // 在 Slot 12 附近，%v1, %v2, %v3 同时存活，峰值压力 = 3
       assert(peakPressure == 3);
       std::cout << "  -> 峰值寄存器压力计算准确。

";

       std::cout << "  -> 活跃区间与冲突图全套引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展现了活跃性分析与图构建的核心机制：

1. **生命周期精准标定**：``LivenessAnalyzer`` 准确捕获了变量从首次定义到最后一次消费的离散时间跨度。例如 ``%v1`` 的生命周期为 $[4, 13)$，在 Slot 13 之后物理空间被安全释放。
2. **冲突图紧凑收敛**：通过区间重叠判定，算法准确为并发存活的变量（如 ``%v1`` 与 ``%v2``、``%v2`` 与 ``%v3``）建立了干涉边；同时成功证明了生命周期不相交的 ``%v1`` 与 ``%v4`` 之间不存在冲突边，为后续图着色阶段将二者绑定到同一个物理寄存器提供了不可动摇的数学证明。
3. **峰值压力确定性量化**：压力评估器测得全段最大并发变量数为 3。若目标机器拥有 4 个物理寄存器（$K=4$），则该函数可在零栈内存溢出（Zero Spills）的极致性能下完成寄存器分配。

小结与下章导读
--------------

本章系统解构了现代编译器后端攻克寄存器分配难题的前提数据结构与分析算法：

1. **槽位索引模型**：推导了步长为 4 的离散程序点体系，阐释了 EarlyClobber、Use、Def 与 Dead 槽位的物理分工。
2. **多段活跃区间**：形式化定义了由半开区间并集构成的活跃范围，阐明了逆向数据流方程构建区间的过程。
3. **冲突图拓扑体系**：建立了 $G=(V, E)$ 无向图模型，确立了区间重叠到冲突边的映射准则与寄存器合并（Coalescing）优化空间。
4. **寄存器压力评估**：推导了瞬时并发变量数与可用寄存器阈值 $K$ 之间的容量关系，揭示了过载触发溢出代码生成的底层依据。

在建立了活跃区间与冲突图之后，下一章我们将深入剖析编译原理史上最璀璨的经典算法——**图着色与线性扫描寄存器分配**。在第 7 模块第 2 节 **寄存器分配核心算法：Chaitin-Briggs 图着色 (Graph Coloring) 与 Poletto 线性扫描 (Linear Scan)（``07_register_allocation_stack_and_abi/02_graph_coloring_and_linear_scan_allocation.rst``）** 中，我们将深入剖析 Kempe 启发式图简化（Simplify）、乐观着色（Optimistic Coloring）、溢出成本加权选择（Spill Weight），以及面向 JIT 极速编译的 Poletto 线性扫描算法。
