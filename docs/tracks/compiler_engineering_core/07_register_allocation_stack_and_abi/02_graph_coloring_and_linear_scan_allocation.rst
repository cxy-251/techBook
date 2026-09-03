====================================================================================================
寄存器分配核心算法：Chaitin-Briggs 图着色 (Graph Coloring) 与 Poletto 线性扫描 (Linear Scan)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 1 节（``07_register_allocation_stack_and_abi/01_liveness_intervals_and_interference_graphs.rst``）中，我们系统推导了槽位索引离散时间轴（Slot Indexing）、多段活跃区间（Live Intervals）以及干涉冲突图（Interference Graph, $G=(V, E)$）的拓扑构建方法。活跃区间精确标定了虚拟寄存器的物理生命周期，而冲突图形式化锚定了“哪些变量绝对不能共享同一个硬件寄存器”的数学边界。在编译器后端管线中，**寄存器分配（Register Allocation, RA）** 是将无限虚拟寄存器映射至有限目标机物理寄存器集合（容量为 $K$）的核心决策算法。本章深入剖析编译原理史上两大经典分配范式：以极致代码生成质量为目标的 **Chaitin-Briggs 乐观图着色算法（Chaitin-Briggs Graph Coloring with Optimistic Coloring）**，以及以线性时间复杂度适配 JIT 极速编译的 **Poletto 线性扫描算法（Poletto & Sarkar Linear Scan）**。

寄存器分配的数学映射：图 $K$-着色问题 (Graph $K$-Coloring)
------------------------------------------------------------

形式化数学定义
~~~~~~~~~~~~~~

设冲突图为无向图 $G = (V, E)$，其中节点 $V$ 代表待分配的虚拟寄存器，边 $(u, v) \in E$ 代表变量 $u$ 与 $v$ 存在活跃期重叠；目标硬件可用物理寄存器集合为 $\mathcal{C} = \{c_1, c_2, \dots, c_K\}$（$|\mathcal{C}| = K$）。

**寄存器分配问题等价于图的 $K$-着色问题**：寻找一个映射函数 $f: V 	o \mathcal{C}$，满足：

.. math::

   \forall (u, v) \in E, \quad f(u) 
eq f(v)

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     冲突图 K-着色与物理寄存器映射拓扑                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ 冲突图 G = (V, E) ]               [ 物理寄存器池 (K = 3) ]   |
   |                                                                             |
   |                    ( v1 ) --------------------+       +---------------+     |
   |                    /    \                     |       | Color 1 : RAX |     |
   |                   /      \                    |       +---------------+     |
   |                ( v2 ) -- ( v3 )               +-----> | Color 2 : RBX |     |
   |                  |                            |       +---------------+     |
   |                  |                            |       | Color 3 : RCX |     |
   |                ( v4 ) ------------------------+       +---------------+     |
   |                                                                             |
   |   * 染色结果: f(v1) = RAX, f(v2) = RBX, f(v3) = RCX, f(v4) = RAX            |
   |   * 关键: v1 与 v4 无冲突边，成功复用物理寄存器 RAX，且任意相连节点颜色互异 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

NP 完全性与 Kempe 简化启发式法则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 $K \ge 3$ 时，判断任意图是否为 $K$-可着色是著名的 **NP-Complete 问题**。
1879 年数学家 Alfred Kempe 提出了著名的图简化引理（Kempe's Heuristic），奠定了现代图着色编译器的基础：

.. math::

   	ext{deg}(v) < K \implies 	ext{若 } G \setminus \{v\} 	ext{ 是 } K	ext{-可着色的，则 } G 	ext{ 必是 } K	ext{-可着色的}

**引理证明**：
由于节点 $v$ 在图中的相邻冲突节点总数少于 $K$ 个，即使所有相邻节点在 $G \setminus \{v\}$ 中被赋予了互不相同的物理颜色，占用的颜色数最多为 $	ext{deg}(v) \le K - 1$ 种。在 $K$ 种总颜色中，必然至少剩余 1 种可用颜色安全分配给节点 $v$。

Chaitin-Briggs 经典图着色寄存器分配架构
---------------------------------------

Gregory Chaitin 于 1981 年首次将图着色应用于编译器，Preston Briggs 于 1989 年提出“乐观着色（Optimistic Coloring）”，形成了现代工业级图着色分配器的黄金标准。

Chaitin-Briggs 六阶段执行流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     Chaitin-Briggs 完整图着色与溢出迭代流水线               |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   +---------------------------------------------------------------------+   |
   |   |                                                                     |   |
   |   v                                                                     |   |
   | [ 1. Build (构图) ]: 计算指令级活跃区间，构建完整冲突图 G               |   |
   |         |                                                               |   |
   |         v                                                               |   |
   | [ 2. Coalesce (合并) ]: 保守消除非冲突 COPY 指令 (Briggs/George 准则)   |   |
   |         |                                                               |   |
   |         v                                                               |   |
   | [ 3. Simplify (简化) ]: 循环寻找 deg(v) < K 的节点压入着色栈并剥离      |   |
   |         |                                                               |   |
   |         +---> 若所有剩余节点均 deg(v) >= K ---> [ 4. Spill (溢出候选) ]  |   |
   |         |                                              |                |   |
   |         |                                              v                |   |
   |         |                      [ Briggs 乐观推栈: 不标记溢出，直接压入栈 ]|   |
   |         v                                              |                |   |
   | [ 5. Select (着色分配) ]: 从栈中逐个弹出节点，赋予合法的物理寄存器颜色  |   |
   |         |                                                               |   |
   |         +---> 遇到无法着色的乐观节点? ----------------------------------+   |
   |         |     (生成真实栈溢出 Store/Reload 代码，重新进入 Build 循环)   |
   |         v                                                                   |
   |   [ 6. 染色成功，退出分配循环 ]                                             |
   |                                                                             |
   +-----------------------------------------------------------------------------+

阶段核心机理与数学判定
~~~~~~~~~~~~~~~~~~~~~~

1. **Conservative Coalescing（保守合并）**：
   合并虚寄存器 $u$ 与 $v$ 可以消除 `COPY %u, %v`，但可能产生度数极大的新节点导致图不可着色。
   - **Briggs 准则**：仅当合并后的节点与所有相邻节点中度数 $\ge K$ 的邻居总数 $< K$ 时，允许合并。
   - **George 准则**：仅当 $u$ 的每一个度数 $\ge K$ 的邻居同时也是 $v$ 的邻居时，允许合并。
2. **Spill Cost 权重计算**：
   当无法继续简化时，算法挑选溢出代价最低的节点：

   .. math::

      	ext{SpillWeight}(v) = \frac{	ext{DefCount}(v) 	imes 10^d + 	ext{UseCount}(v) 	imes 10^d}{	ext{deg}(v)}

   其中 $d$ 为变量所处基本块的 **循环嵌套深度（Loop Nesting Depth）**。内层循环中的变量溢出权重呈几何级数递增，确保关键热点变量留在物理寄存器中。
3. **Briggs Optimistic Coloring（乐观着色）**：
   Chaitin 原始算法直接将高潜溢出节点标记为溢出并插入内存读写；Briggs 乐观算法 **依然将该高度数节点推入选择栈**。在实际出栈着色时，只要该节点的相邻邻居之间存在颜色复用，该节点往往能够奇迹般地获得合法颜色，大幅减少无谓的栈内存溢出！

Poletto & Sarkar 线性扫描寄存器分配 (Linear Scan)
-------------------------------------------------

在即时编译器（JIT，如 JavaScript V8、Java HotSpot、WebAssembly 运行时）与注重极速编译的轻量后端中，构建冲突图与反复图简化的 $\mathcal{O}(V^2) \sim \mathcal{O}(V^3)$ 耗时不可承受。
Poletto 与 Sarkar 于 1999 年提出了 **线性扫描寄存器分配算法（Linear Scan）**，将分配耗时压缩至严格线性的 $\mathcal{O}(V)$ 或 $\mathcal{O}(V \log K)$。

线性扫描核心算法状态机
~~~~~~~~~~~~~~~~~~~~~~

线性扫描放弃了全局冲突图的构建，仅依赖按起始位置严格单调排序的活跃区间列表：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Poletto 线性扫描算法时间轴推进状态机                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. 预处理: 将所有变量的活跃区间按 start 点升序排序: [ I_1, I_2, ..., I_n ] |
   |   2. 维护活跃区间集合 active (按 end 点升序排序，容量上限为 K)              |
   |                                                                             |
   |   3. 遍历每个未处理区间 i:                                                  |
   |      a. [ ExpireOldIntervals ]:                                             |
   |         遍历 active 集合中所有 end(j) < start(i) 的过期区间:                |
   |         - 将区间 j 从 active 移除，回收其占用的物理寄存器。                 |
   |                                                                             |
   |      b. [ 分配或溢出判定 ]:                                                 |
   |         - 若 |active| < K (存在空闲物理寄存器):                             |
   |              为 i 分配一个可用物理寄存器，将 i 加入 active 集合。           |
   |         - 若 |active| == K (物理寄存器耗尽，发生冲突):                      |
   |              [ SpillAtInterval ]:                                           |
   |              找到 active 集合中结束位置最晚的区间 candidate (max end(j));   |
   |              * 若 end(candidate) > end(i):                                  |
   |                   溢出 candidate (剥夺其物理寄存器并放入栈槽);              |
   |                   将腾出的物理寄存器分配给当前区间 i，将 i 插入 active;     |
   |              * 否则 (当前区间 i 存活时间最长):                              |
   |                   直接将当前区间 i 标记为溢出至栈槽。                       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

两大经典分配范式工业级综合对比
------------------------------

.. list-table:: 图着色算法 vs 线性扫描算法全景工程对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - Chaitin-Briggs 图着色分配器
     - Poletto 线性扫描分配器
   * - **时间复杂度**
     - $\mathcal{O}(V^2)$ 到 $\mathcal{O}(V^3)$（构图与循环迭代溢出）
     - **$\mathcal{O}(V \log K)$ 或严格线性 $\mathcal{O}(V)$**
   * - **代码生成质量**
     - **极致（Near-Optimal）**：深入考虑跨基本块冲突、环路权重与全局寄存器复用
     - 良好至中等：局部贪心启发式，可能产生次优的溢出决策
   * - **编译期内存开销**
     - 巨大（需维护 $V 	imes V$ 冲突矩阵与稠密邻接表）
     - **极小（仅维护简短的活跃区间与 active 优先队列）**
   * - **典型应用生态**
     - AOT 工业级优化编译器（LLVM GreedyRegAlloc、GCC IRA/LRA）
     - JIT 即时编译器（V8 TurboFan、JVM C1/HotSpot、LLVM FastRegAlloc）

工业级 C++ 完整图着色与线性扫描双引擎实现
-----------------------------------------

以下 C++ 源码实现了自包含的图着色分配器（涵盖 Kempe 简化、Briggs 乐观着色与栈染色）与线性扫描分配器。该实现涵盖：
1. 冲突图邻接表模型与活跃区间定义。
2. 包含 `Simplify`、`Optimistic Select` 与 `Spill` 的 `ChaitinBriggsAllocator`。
3. 包含 `ExpireOldIntervals` 与 `SpillAtInterval` 的 `LinearScanAllocator`。
4. 端到端测试套件，验证在物理寄存器紧缺（$K=2$ 与 $K=3$）场景下的着色无冲突性与最优溢出判定。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <algorithm>
   #include <stack>
   #include <cassert>

   namespace reg_alloc_engine {

   // =========================================================================
   // 1. 活跃区间与冲突图模型
   // =========================================================================
   struct LiveInterval {
       std::string Var;
       int Start = 0;
       int End = 0;
       double SpillWeight = 1.0;

       bool operator<(const LiveInterval& o) const {
           return Start < o.Start;
       }
   };

   class InterferenceGraph {
   public:
       std::unordered_set<std::string> Nodes;
       std::unordered_map<std::string, std::unordered_set<std::string>> Adj;
       std::unordered_map<std::string, double> Weights;

       void addNode(const std::string& u, double weight = 1.0) {
           Nodes.insert(u);
           Weights[u] = weight;
           if (!Adj.count(u)) Adj[u] = {};
       }

       void addEdge(const std::string& u, const std::string& v) {
           if (u == v) return;
           addNode(u);
           addNode(v);
           Adj[u].insert(v);
           Adj[v].insert(u);
       }

       [[nodiscard]] size_t degree(const std::string& u) const {
           return Adj.at(u).size();
       }
   };

   // =========================================================================
   // 2. Chaitin-Briggs 乐观图着色分配器
   // =========================================================================
   class ChaitinBriggsAllocator {
   public:
       struct AllocationResult {
           std::unordered_map<std::string, int> ColorMap; // 变量 -> 物理寄存器 ID (0..K-1)
           std::unordered_set<std::string> SpilledNodes;  // 溢出到栈的变量集合
       };

       static AllocationResult allocate(InterferenceGraph graph, int K) {
           AllocationResult result;
           std::stack<std::string> selectStack;
           std::unordered_set<std::string> remaining = graph.Nodes;
           std::unordered_map<std::string, std::unordered_set<std::string>> workingAdj = graph.Adj;

           // 1. Simplify & Optimistic Spill 循环
           while (!remaining.empty()) {
               // 寻找度数 < K 的节点
               std::string lowDegreeNode = "";
               for (const auto& node : remaining) {
                   if (workingAdj[node].size() < static_cast<size_t>(K)) {
                       lowDegreeNode = node;
                       break;
                   }
               }

               if (!lowDegreeNode.empty()) {
                   // Simplify 阶段: 压栈并从当前图中剥离
                   selectStack.push(lowDegreeNode);
                   remaining.erase(lowDegreeNode);
                   for (const auto& neighbor : workingAdj[lowDegreeNode]) {
                       workingAdj[neighbor].erase(lowDegreeNode);
                   }
                   workingAdj.erase(lowDegreeNode);
               } else {
                   // Spill 阶段: 挑选 SpillWeight 最小的高潜溢出节点
                   std::string spillCandidate = "";
                   double minWeight = 1e18;

                   for (const auto& node : remaining) {
                       double w = graph.Weights[node] / static_cast<double>(workingAdj[node].size());
                       if (w < minWeight) {
                           minWeight = w;
                           spillCandidate = node;
                       }
                   }

                   // Briggs 乐观着色: 不直接标记溢出，依然压入选择栈!
                   selectStack.push(spillCandidate);
                   remaining.erase(spillCandidate);
                   for (const auto& neighbor : workingAdj[spillCandidate]) {
                       workingAdj[neighbor].erase(spillCandidate);
                   }
                   workingAdj.erase(spillCandidate);
               }
           }

           // 2. Select 阶段: 逐个弹栈并分配物理颜色
           while (!selectStack.empty()) {
               std::string node = selectStack.top();
               selectStack.pop();

               // 收集所有已分配邻居的颜色
               std::vector<bool> usedColors(K, false);
               for (const auto& neighbor : graph.Adj[node]) {
                   if (result.ColorMap.count(neighbor)) {
                       int c = result.ColorMap[neighbor];
                       if (c >= 0 && c < K) {
                           usedColors[c] = true;
                       }
                   }
               }

               // 寻找第一个未使用的物理颜色
               int assignedColor = -1;
               for (int c = 0; c < K; ++c) {
                   if (!usedColors[c]) {
                       assignedColor = c;
                       break;
                   }
               }

               if (assignedColor != -1) {
                   result.ColorMap[node] = assignedColor; // 染色成功 (包括乐观着色成功的节点)
               } else {
                   result.SpilledNodes.insert(node);      // 乐观着色失败，触发真实溢出
               }
           }

           return result;
       }
   };

   // =========================================================================
   // 3. Poletto 线性扫描寄存器分配器 (Linear Scan)
   // =========================================================================
   class LinearScanAllocator {
   public:
       struct Result {
           std::unordered_map<std::string, int> Allocation;
           std::unordered_set<std::string> Spills;
       };

       static Result allocate(std::vector<LiveInterval> intervals, int K) {
           Result res;
           if (intervals.empty()) return res;

           // 1. 按 Start 点严格升序排序
           std::sort(intervals.begin(), intervals.end());

           // 活跃队列: 保存当前已分配物理寄存器的区间 (pair<End, pair<Var, RegID>>)
           std::vector<std::pair<int, std::pair<std::string, int>>> active;
           std::vector<int> freeRegisters;
           for (int r = K - 1; r >= 0; --r) freeRegisters.push_back(r);

           for (const auto& current : intervals) {
               // a. ExpireOldIntervals: 释放已结束的区间
               auto it = active.begin();
               while (it != active.end()) {
                   if (it->first <= current.Start) {
                       freeRegisters.push_back(it->second.second); // 回收物理寄存器
                       it = active.erase(it);
                   } else {
                       ++it;
                   }
               }

               // b. 分配或溢出判定
               if (!freeRegisters.empty()) {
                   int reg = freeRegisters.back();
                   freeRegisters.pop_back();
                   res.Allocation[current.Var] = reg;
                   active.push_back({current.End, {current.Var, reg}});
                   // 保持 active 按 End 升序
                   std::sort(active.begin(), active.end());
               } else {
                   // 物理寄存器耗尽，比较当前区间与 active 中结束最晚的区间
                   auto& latestActive = active.back();
                   if (latestActive.first > current.End) {
                       // 溢出 latestActive，将寄存器转让给 current
                       res.Spills.insert(latestActive.second.first);
                       res.Allocation.erase(latestActive.second.first);

                       int stolenReg = latestActive.second.second;
                       active.pop_back();

                       res.Allocation[current.Var] = stolenReg;
                       active.push_back({current.End, {current.Var, stolenReg}});
                       std::sort(active.begin(), active.end());
                   } else {
                       // 溢出当前区间
                       res.Spills.insert(current.Var);
                   }
               }
           }

           return res;
       }
   };

   } // namespace reg_alloc_engine

   // =========================================================================
   // 4. 端到端测试与算法性能验证套件
   // =========================================================================
   namespace test {

   inline void runRegisterAllocationTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Chaitin-Briggs 图着色与 Poletto 线性扫描验证套件
";
       std::cout << "=======================================================

";

       using namespace reg_alloc_engine;

       // 1. 测试 Chaitin-Briggs 乐观着色能力 (K = 3)
       // 构造完全环形冲突图: v1-v2, v2-v3, v3-v4, v4-v1, 附加 v1-v3
       // 所有节点度数均为 2 或 3
       InterferenceGraph ig;
       ig.addEdge("v1", "v2");
       ig.addEdge("v2", "v3");
       ig.addEdge("v3", "v4");
       ig.addEdge("v4", "v1");
       ig.addEdge("v1", "v3"); // v1-v2-v3 构成三角形 (必须 3 种颜色)

       std::cout << "[测试 1: Chaitin-Briggs 图着色 (K = 3)]:
";
       auto cbResult = ChaitinBriggsAllocator::allocate(ig, 3);

       for (const auto& pair : cbResult.ColorMap) {
           std::cout << "  Variable: " << pair.first << " -> Physical Color: " << pair.second << "
";
       }
       std::cout << "  溢出变量总数: " << cbResult.SpilledNodes.size() << "
";

       // 验证断言:
       // 1. 无任何变量溢出
       assert(cbResult.SpilledNodes.empty());
       // 2. 存在冲突边的节点颜色绝对不同
       assert(cbResult.ColorMap["v1"] != cbResult.ColorMap["v2"]);
       assert(cbResult.ColorMap["v2"] != cbResult.ColorMap["v3"]);
       assert(cbResult.ColorMap["v1"] != cbResult.ColorMap["v3"]);
       assert(cbResult.ColorMap["v4"] != cbResult.ColorMap["v1"]);
       assert(cbResult.ColorMap["v4"] != cbResult.ColorMap["v3"]);
       std::cout << "  -> 图着色约束完全满足，相邻冲突节点颜色互异。

";

       // 2. 测试 Poletto 线性扫描算法与溢出决策 (K = 2)
       // 构造 3 个高度重叠的区间:
       //   vA: [1, 10)  (长生命周期)
       //   vB: [2, 5)   (短生命周期)
       //   vC: [3, 8)   (中生命周期)
       std::vector<LiveInterval> intervals = {
           {"vA", 1, 10, 1.0},
           {"vB", 2, 5, 1.0},
           {"vC", 3, 8, 1.0}
       };

       std::cout << "[测试 2: Poletto 线性扫描分配 (K = 2 紧张资源)]:
";
       auto lsResult = LinearScanAllocator::allocate(intervals, 2);

       for (const auto& pair : lsResult.Allocation) {
           std::cout << "  Variable: " << pair.first << " -> Register: R" << pair.second << "
";
       }
       for (const auto& sp : lsResult.Spills) {
           std::cout << "  Spilled to Stack: " << sp << "
";
       }

       // 验证断言:
       // 由于 K=2，在 t=3 时 vA, vB, vC 同时活跃，结束最晚的 vA (end=10) 必须被精准挑选溢出
       assert(lsResult.Spills.count("vA") == 1);
       assert(lsResult.Allocation.count("vB") == 1);
       assert(lsResult.Allocation.count("vC") == 1);
       std::cout << "  -> 线性扫描准确溢出结束最晚的区间 vA，将物理寄存器让给短活跃期变量。

";

       std::cout << "  -> 寄存器分配两大经典核心算法验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了两大核心分配算法的内在机理：

1. **图着色冲突消除与寄存器复用**：在测试 1 中，面对包含 3-团（Triangle Clique）的复杂冲突图，Chaitin-Briggs 算法在 $K=3$ 的严格物理约束下，成功将无冲突的 ``v4`` 与 ``v2`` 赋予相同的物理颜色，达成了零溢出（Zero Spills）的最优解。
2. **线性扫描的高效溢出仲裁**：在测试 2 中，当活跃区间瞬时并发度达到 3 且物理寄存器上限仅为 $K=2$ 时，线性扫描算法通过比较活跃集合中的结束时间戳，果断剥夺了横跨整个生命周期的长区间 ``vA``（End=10）的寄存器所有权，将其置换入栈槽，确保了短生命周期局部计算的高速推进。

小结与下章导读
--------------

本章系统解构了现代编译器后端核心的寄存器分配算法体系：

1. **图着色数学本质**：形式化阐明了冲突图向图 $K$-着色问题的规约，推导了 Kempe 启发式图简化定理。
2. **Chaitin-Briggs 状态机**：剖析了构建、保守合并（Briggs/George 准则）、简化、溢出权重计算与 Briggs 乐观着色的完整六阶段管线。
3. **Poletto 线性扫描算法**：推导了基于时间轴单向推进的区间过期与晚结束区间溢出决策状态机，展示了其在 JIT 编译器中的极致线性吞吐优势。
4. **工业级决策选型矩阵**：确立了 AOT 优化编译（图着色）与 JIT 极速编译（线性扫描）在算法复杂度与生成代码质量之间的权衡准则。

在寄存器分配过程中，当物理寄存器不足时被标记为溢出的变量必须落入物理内存栈帧中。在第 7 模块第 3 节 **溢出代码生成与栈槽复用：溢出代价评估、栈槽生命周期重叠判定与微架构热路径保护（``07_register_allocation_stack_and_abi/03_spill_code_generation_and_stack_slot_coloring.rst``）** 中，我们将深入剖析溢出权重精细化计算、溢出指令（Spill Store / Reload）插入时序、基于区间重叠的栈槽着色复用（Stack Slot Coloring），以及保护 CPU L1 数据缓存与执行热路径的物理工程实践。
