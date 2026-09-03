====================================================================================================
支配关系与自然循环识别：不可达块消除、支配树 (Dominator Tree) 构建与回边 (Backedge) 检测
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 2 节（``04_ir_cfg_and_ssa_construction/02_basic_blocks_terminators_and_cfg_topology.rst``）中，我们系统剖析了基本块（Basic Block）的单入口单出口微架构不变性、首指令（Leaders）判定划分流水线、Terminator 终止指令体系、前驱后继双向指针网格，以及临界边（Critical Edge）分割算法。控制流图（CFG）将扁平的线性指令重构为包含分支、合流与循环回边的有向图。然而，CFG 仅表达了局部的后继跳转关系。为了在后续阶段实现静态单赋值（SSA）形式转换、精确放置 $\phi$ 节点、执行循环不变量外提（LICM）与循环展开（Loop Unrolling），编译器必须在 CFG 之上建立全局的 **支配拓扑（Dominance Topology）** 与 **循环层次模型（Loop Hierarchy）**。本章深入解构不可达基本块的图修剪算法、支配关系（Dominance）与直接支配者（Immediate Dominator, idom）的形式化数学定义、支配树（Dominator Tree）的物理构建算法、支配边界（Dominance Frontier, DF）的迭代收集状态机，以及基于支配回边（Backedge）检测与前置头（Preheader）规范化的自然循环（Natural Loop）识别引擎。

不可达基本块消除与 CFG 拓扑修剪
-------------------------------

在前端 AST 降级、死代码消除或常量条件折叠（如 ``if (false)``）之后，控制流图中常常残留从函数入口节点无法沿任何有向路径到达的基本块。

可达性分析与孤岛节点清理
~~~~~~~~~~~~~~~~~~~~~~~~

不可达基本块不仅浪费机器指令缓存（I-Cache），还会向后续的支配树计算与数据流分析引入无前驱的悬垂变量定值，破坏数据流方程的单调性与收敛性。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     不可达基本块可达性标记与物理清除流水线                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 初始 CFG 拓扑 (含不可达孤岛块) ]                                        |
   |                                                                             |
   |        +-----------------+                                                  |
   |        |   Entry Block   | <--- 算法起点 (Mark Reachable)                   |
   |        +--------+--------+                                                  |
   |                 |                                                           |
   |                 v                                                           |
   |        +-----------------+           +-----------------+                    |
   |        |    Block B1     |           | Dead Block D1   | <--- 不可达孤岛    |
   |        +--------+--------+           +--------+--------+                    |
   |                 |                             |                             |
   |                 v                             v                             |
   |        +-----------------+           +-----------------+                    |
   |        |   Block Exit    | <-------- | Dead Block D2   |                    |
   |        +-----------------+           +-----------------+                    |
   |                                                                             |
   |   [ 阶段 1: 深度优先搜索 (DFS) 遍历染色 ]                                   |
   |      * 从 Entry 遍历可达集合: {Entry, B1, Exit}                             |
   |      * 未染色节点集合: {D1, D2}                                             |
   |                                                                             |
   |   [ 阶段 2: 孤岛节点断开与释放 ]                                            |
   |      1. 扫描未染色节点 D2 的所有后继 (Exit)，从 Exit 的前驱列表中移除 D2     |
   |      2. 若 Exit 包含 phi 节点，移除对应来自 D2 的输入分支                   |
   |      3. 析构 D1 与 D2 内部的所有指令并释放节点内存                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

支配关系 (Dominance) 的形式化代数模型
-------------------------------------

在单入口有向图 $G = (V, E, r)$ 中，其中 $r \in V$ 为唯一的函数入口节点（Entry Block）：

支配 (Dominates) 的形式化定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于任意两个节点 $d, n \in V$，称 **$d$ 支配 $n$**（记作 $d 	ext{ dom } n$），当且仅当：
**从入口节点 $r$ 到节点 $n$ 的每一条有向控制流路径，都必须经过节点 $d$。**

支配关系在图论代数上满足以下三条偏序性质：
1. **自反性（Reflexivity）**：$n 	ext{ dom } n$，任何节点支配其自身。
2. **传递性（Transitivity）**：若 $a 	ext{ dom } b$ 且 $b 	ext{ dom } c$，则 $a 	ext{ dom } c$。
3. **反对称性（Anti-symmetry）**：若 $a 	ext{ dom } b$ 且 $b 	ext{ dom } a$，则 $a = b$。

严格支配 (Strict Dominance) 与直接支配者 (idom)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **严格支配（Strict Dominance）**：
   若 $d 	ext{ dom } n$ 且 $d 
eq n$，则称 $d$ 严格支配 $n$（记作 $d 	ext{ sdom } n$ 或 $d \gg n$）。
2. **直接支配者（Immediate Dominator, $idom(n)$）**：
   在所有严格支配 $n$ 的节点集合中，存在且仅存在一个离 $n$ “最近”的节点 $p$，满足 $p$ 不严格支配任何其他严格支配 $n$ 的节点。该唯一节点 $p$ 被定义为 $n$ 的 **直接支配者（Immediate Dominator）**，记作 $idom(n) = p$。

直接支配者构成了树形结构的父子关系指针：除了根节点 $r$ 没有直接支配者外，CFG 中每一个可达节点拥有且仅拥有一个唯一的 $idom$。

支配树 (Dominator Tree) 拓扑与性质
----------------------------------

以入口节点 $r$ 为根，以 $idom(n) 	o n$ 为有向有根树的有向边，所构成的树形结构被称为 **支配树（Dominator Tree, DomTree）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       CFG 控制流图向支配树 (DomTree) 映射                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ CFG 有向图拓扑 ]                          [ 对应的支配树 DomTree ]      |
   |                                                                             |
   |           +-------+                                   +-------+             |
   |           | Entry |                                   | Entry |             |
   |           +---+---+                                   +---+---+             |
   |              / \                                         / \                |
   |             /   \                                       /   \               |
   |            v     v                                     v     v              |
   |        +----+   +----+                             +----+   +----+          |
   |        | B1 |   | B2 |                             | B1 |   | B2 |          |
   |        +----+   +----+                             +----+   +----+          |
   |            \     /                                            |             |
   |             v   v                                             v             |
   |            +-----+                                         +-----+          |
   |            | B3  |                                         | B3  |          |
   |            +-----+                                         +-----+          |
   |               |                                               |             |
   |               v                                               v             |
   |            +-----+                                         +-----+          |
   |            | B4  |                                         | B4  |          |
   |            +-----+                                         +-----+          |
   |                                                                             |
   |   * 在 CFG 中 B3 拥有两个前驱 (B1, B2)        * 在 DomTree 中:              |
   |   * 到达 B3 的路径必须经过 Entry              * idom(B3) = Entry            |
   |   * 因此 Entry 直接支配 B3                    * idom(B4) = B3               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

支配树的核心性质
~~~~~~~~~~~~~~~~

1. **祖先判定定理**：在支配树中，节点 $d$ 支配节点 $n$，当且仅当 $d$ 是 $n$ 在支配树上的祖先节点（Ancestor）。
2. **DFS 时间戳与常数时间支配查询**：
   通过对支配树执行一次深度优先搜索，记录每个节点的进入时间戳 $	ext{DFS\_In}(u)$ 与离开时间戳 $	ext{DFS\_Out}(u)$。判断 $u 	ext{ dom } v$ 可在 $\mathcal{O}(1)$ 常数时间内完成：

   .. math::

      u 	ext{ dom } v \iff 	ext{DFS\_In}(u) \le 	ext{DFS\_In}(v) \quad \land \quad 	ext{DFS\_Out}(u) \ge 	ext{DFS\_Out}(v)

支配树构建算法：不动点迭代 vs Lengauer-Tarjan
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 支配树构建算法特性对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 算法名称
     - 算法原理与时间复杂度
     - 适用场景与工程权衡
   * - 数据流不动点迭代算法 (Iterative Dom)
     - 基于方程 $Dom(n) = \{n\} \cup \left( \bigcap_{p \in Pred(n)} Dom(p) \right)$，逆后序迭代；复杂度 $\mathcal{O}(|V|^2)$
     - 代码实现极简（百行内），节点规模较小（$|V| < 100$）时常数极小
   * - Lengauer-Tarjan (LT) 算法
     - 利用深度优先生成树、半支配者（Semi-dominator）定理与带权并查集（Union-Find）路径压缩；复杂度 $\mathcal{O}(|E| \alpha(|E|, |V|))$
     - 工业级编译器（LLVM、GCC）标准实现，超大规模控制流图下维持近线性性能

支配边界 (Dominance Frontier) 与 SSA 放置点
--------------------------------------------

支配边界是连接控制流图与静态单赋值（SSA）形式的核心数学纽带。它精确指明了：**某个基本块内部定义的变量值，在何处必须插入 $\phi$ 节点进行汇流合并。**

支配边界 (DF) 的严格定义
~~~~~~~~~~~~~~~~~~~~~~~~

节点 $X$ 的 **支配边界（Dominance Frontier, $DF(X)$）** 定义为所有满足以下两个条件的节点 $Y$ 组成的集合：
1. $X$ 支配 $Y$ 的某一个直接前驱节点 $P \in 	ext{Pred}(Y)$（即 $X 	ext{ dom } P$）；
2. $X$ **并不严格支配** $Y$ 自身（即 $
eg(X 	ext{ sdom } Y)$）。

形式化集合表达式为：

.. math::

   DF(X) = \{ Y \in V \mid \exists P \in 	ext{Pred}(Y) 	ext{ s.t. } (X 	ext{ dom } P) \land 
eg(X 	ext{ sdom } Y) \}

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    支配边界 (Dominance Frontier) 物理几何拓扑               |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              +-----------------------------------------------+              |
   |              | X 的支配域 (Dominance Region of X):           |              |
   |              | 包含所有被 X 严格支配的节点 (X dom P)         |              |
   |              |                                               |              |
   |              |           +---------+                         |              |
   |              |           |    X    |                         |              |
   |              |           +----+----+                         |              |
   |              |                |                              |              |
   |              |                v                              |              |
   |              |           +---------+                         |              |
   |              |           |    P    |                         |              |
   |              |           +----+----+                         |              |
   |              +----------------|------------------------------+              |
   |                               |                                             |
   |                  控制流跨出支配域边界: 边 (P -> Y)                          |
   |                               |                                             |
   |                               v                                             |
   |                        +-------------+ <--- 节点 Y 属于 DF(X)               |
   |                        |   Block Y   |      (X 支配 P, 但 X 不严格支配 Y)   |
   |                        +-------------+                                      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

支配边界的计算算法 (Cytron 算法)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

利用支配树后序遍历，可在 $\mathcal{O}(|V| + |E|)$ 时间内收集全图的支配边界：

1. 寻找 CFG 中所有拥有多个前驱的节点 $Y$（即 $|	ext{Pred}(Y)| \ge 2$）。
2. 对于 $Y$ 的每一个前驱节点 $P$：
   - 沿支配树向上追溯当前游标 $X = P$。
   - 当 $X 
eq idom(Y)$ 时：
     - 将 $Y$ 加入 $DF(X)$。
     - $X \leftarrow idom(X)$（继续向上爬升至父节点）。

自然循环 (Natural Loops) 与回边 (Backedge) 检测
-----------------------------------------------

高级语言的 ``for``、``while``、``do-while`` 结构在降级为 CFG 后统一体现为环路拓扑。然而，并非有向图中的任意环路都能直接作为循环进行安全优化。编译器重点关注具备单一入口的 **自然循环（Natural Loop）**。

回边 (Backedge) 的判定条件
~~~~~~~~~~~~~~~~~~~~~~~~~~

在控制流图 $G$ 中，一条有向边 $e = (A, B) \in E$ 被判定为 **回边（Backedge）**，当且仅当：
**目标节点 $B$ 支配源节点 $A$（即 $B 	ext{ dom } A$）。**

此时，节点 $B$ 被称为循环的 **头节点（Header）**，节点 $A$ 被称为循环的 **回跳节点（Latch）**。

自然循环的定义与节点收集算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由回边 $A 	o B$ 所唯一确定的 **自然循环（Natural Loop）** 是满足以下条件的最小节点子图：
1. 节点 $B$ 是循环唯一的入口头节点（Header）。外部控制流只能进入 $B$，严禁直接跳入循环体内部其他节点。
2. 循环节点集合由 $B$ 以及所有能够沿着 CFG 边到达 $A$ 且路径上不经过 $B$ 的节点组成。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     自然循环 (Natural Loop) 节点逆向追溯算法                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 输入回边 ]: Latch -> Header (Header dom Latch)                          |
   |                                                                             |
   |   [ 逆向工作表算法 (Worklist Algorithm) ]:                                  |
   |      1. 初始化 LoopNodes = { Header, Latch }                                |
   |      2. 初始化 Worklist = [ Latch ]                                         |
   |      3. While Worklist 非空:                                                |
   |           Pop 当前节点 N                                                    |
   |           For 每一个前驱 Pred in Pred(N):                                   |
   |             If Pred 不在 LoopNodes 中:                                      |
   |               LoopNodes.insert(Pred)                                        |
   |               Worklist.push(Pred)                                           |
   |                                                                             |
   |   [ 输出 ]: 完整的自然循环基本块集合 LoopNodes                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

循环规范化：Preheader 与 Latch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了使循环优化 Pass（如循环展开、LICM 循环不变量外提、矢量化）能够安全安放前置初始代码，工业级编译器在检测到自然循环后，会执行 **循环简化（Loop Simplify）规范化**：

1. **插入前置头（Preheader）**：
   在 Header 块之前插入一个唯一的辅助块 Preheader。所有来自循环外部指向 Header 的边全部重定向至 Preheader，而 Header 仅保留来自 Preheader 的唯一起始入边和来自 Latch 的回边。Preheader 提供了安放循环不变量外提指令的专属安全空间。
2. **唯一回跳块（Dedicated Latch）**：
   若一个 Header 对应多条回边，将所有回跳源节点汇流至一个统一的 Latch 块。

可约化流图 (Reducible) vs 不可约化流图 (Irreducible)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若 CFG 中的每一个环路都拥有唯一支配全部环内节点的 Header，则该流图为 **可约化流图（Reducible CFG）**。若存在包含多个入口的环路（如使用 ``goto`` 交叉跳入循环体内部），该图为 **不可约化流图（Irreducible CFG）**。现代优化管线通常先通过循环复制（Node Splitting）将不可约化流图转化为可约化流图，再开展深度循环变换。

工业级 C++ 完整支配树与循环分析引擎实现
----------------------------------------

以下 C++ 源码实现了一套工业级自包含的支配树构建、支配边界计算与自然循环识别引擎。该实现涵盖：
1. 图可达性判定与孤岛基本块修剪。
2. 基于支配方程不动点迭代的直接支配者（$idom$）计算与支配树节点拓扑构建。
3. 支配树 DFS 时间戳生成与 $\mathcal{O}(1)$ 快速支配查询（``dominates(A, B)``）。
4. Cytron 支配边界（Dominance Frontier）收集器。
5. 回边探测与自然循环（Natural Loop）节点集合重构器。
6. 端到端测试套件，展示包含条件分支与嵌套循环的复杂 CFG 的完整分析输出。

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
   #include <cassert>
   #include <sstream>

   namespace dom_loop_engine {

   // =========================================================================
   // 1. CFG 节点与图模型
   // =========================================================================
   struct BlockNode {
       std::string Name;
       uint32_t Id = 0;
       std::vector<BlockNode*> Predecessors;
       std::vector<BlockNode*> Successors;

       explicit BlockNode(std::string name, uint32_t id)
           : Name(std::move(name)), Id(id) {}
   };

   class FlowGraph {
   public:
       BlockNode* Entry = nullptr;
       std::vector<std::unique_ptr<BlockNode>> Nodes;

       BlockNode* addBlock(const std::string& name) {
           uint32_t id = static_cast<uint32_t>(Nodes.size());
           Nodes.push_back(std::make_unique<BlockNode>(name, id));
           return Nodes.back().get();
       }

       void addEdge(BlockNode* from, BlockNode* to) {
           assert(from && to);
           from->Successors.push_back(to);
           to->Predecessors.push_back(from);
       }

       // 阶段 1: 不可达基本块修剪
       void eliminateUnreachableBlocks() {
           if (!Entry) return;

           std::unordered_set<BlockNode*> reachable;
           std::queue<BlockNode*> worklist;

           reachable.insert(Entry);
           worklist.push(Entry);

           while (!worklist.empty()) {
               BlockNode* curr = worklist.front();
               worklist.pop();

               for (BlockNode* succ : curr->Successors) {
                   if (reachable.insert(succ).second) {
                       worklist.push(succ);
                   }
               }
           }

           // 从后继节点的前驱列表中剥离不可达前驱
           for (auto& node : Nodes) {
               if (reachable.find(node.get()) == reachable.end()) {
                   for (BlockNode* succ : node->Successors) {
                       succ->Predecessors.erase(
                           std::remove(succ->Predecessors.begin(), succ->Predecessors.end(), node.get()),
                           succ->Predecessors.end()
                       );
                   }
               }
           }

           // 移除未到达节点
           Nodes.erase(
               std::remove_if(Nodes.begin(), Nodes.end(), [&](const std::unique_ptr<BlockNode>& ptr) {
                   return reachable.find(ptr.get()) == reachable.end();
               }),
               Nodes.end()
           );

           // 重新整理 Node Id
           for (size_t i = 0; i < Nodes.size(); ++i) {
               Nodes[i]->Id = static_cast<uint32_t>(i);
           }
       }
   };

   // =========================================================================
   // 2. 支配树 (Dominator Tree) 与支配边界 (Dominance Frontier)
   // =========================================================================
   struct DomTreeNode {
       BlockNode* Block = nullptr;
       DomTreeNode* IDom = nullptr;
       std::vector<DomTreeNode*> Children;
       uint32_t DFSIn = 0;
       uint32_t DFSOut = 0;
   };

   class DominatorTree {
   public:
       std::unordered_map<BlockNode*, std::unique_ptr<DomTreeNode>> NodeMap;
       DomTreeNode* Root = nullptr;
       std::unordered_map<BlockNode*, std::unordered_set<BlockNode*>> DominanceFrontiers;

       void build(FlowGraph& graph) {
           NodeMap.clear();
           DominanceFrontiers.clear();
           if (!graph.Entry || graph.Nodes.empty()) return;

           for (const auto& b : graph.Nodes) {
               auto dtNode = std::make_unique<DomTreeNode>();
               dtNode->Block = b.get();
               NodeMap[b.get()] = std::move(dtNode);
           }
           Root = NodeMap[graph.Entry].get();

           computeImmediateDominators(graph);
           computeDFSIntervals(Root, 0);
           computeDominanceFrontiers(graph);
       }

       // O(1) 常数时间支配判定
       bool dominates(BlockNode* a, BlockNode* b) const {
           if (!a || !b) return false;
           if (a == b) return true;
           auto itA = NodeMap.find(a);
           auto itB = NodeMap.find(b);
           if (itA == NodeMap.end() || itB == NodeMap.end()) return false;

           const DomTreeNode* nodeA = itA->second.get();
           const DomTreeNode* nodeB = itB->second.get();
           return nodeA->DFSIn <= nodeB->DFSIn && nodeA->DFSOut >= nodeB->DFSOut;
       }

       bool strictlyDominates(BlockNode* a, BlockNode* b) const {
           return (a != b) && dominates(a, b);
       }

   private:
       // 基于迭代交集的直接支配者计算
       void computeImmediateDominators(FlowGraph& graph) {
           size_t n = graph.Nodes.size();
           std::vector<BlockNode*> idom(n, nullptr);
           idom[graph.Entry->Id] = graph.Entry;

           bool changed = true;
           while (changed) {
               changed = false;
               for (const auto& b : graph.Nodes) {
                   if (b.get() == graph.Entry) continue;

                   // 寻找第一个已分配 idom 的前驱作为基准
                   BlockNode* newIdom = nullptr;
                   for (BlockNode* p : b->Predecessors) {
                       if (idom[p->Id] != nullptr) {
                           newIdom = p;
                           break;
                       }
                   }

                   if (!newIdom) continue;

                   // 与其余已分配 idom 的前驱求支配交集
                   for (BlockNode* p : b->Predecessors) {
                       if (p != newIdom && idom[p->Id] != nullptr) {
                           newIdom = intersect(p, newIdom, idom);
                       }
                   }

                   if (idom[b->Id] != newIdom) {
                       idom[b->Id] = newIdom;
                       changed = true;
                   }
               }
           }

           // 挂接支配树父子指针
           for (const auto& b : graph.Nodes) {
               if (b.get() == graph.Entry) continue;
               BlockNode* parentBlock = idom[b->Id];
               if (parentBlock) {
                   DomTreeNode* child = NodeMap[b.get()].get();
                   DomTreeNode* parent = NodeMap[parentBlock].get();
                   child->IDom = parent;
                   parent->Children.push_back(child);
               }
           }
       }

       BlockNode* intersect(BlockNode* b1, BlockNode* b2, const std::vector<BlockNode*>& idom) {
           BlockNode* finger1 = b1;
           BlockNode* finger2 = b2;
           while (finger1 != finger2) {
               while (finger1->Id > finger2->Id) {
                   finger1 = idom[finger1->Id];
               }
               while (finger2->Id > finger1->Id) {
                   finger2 = idom[finger2->Id];
               }
           }
           return finger1;
       }

       uint32_t computeDFSIntervals(DomTreeNode* curr, uint32_t time) {
           if (!curr) return time;
           curr->DFSIn = ++time;
           for (DomTreeNode* child : curr->Children) {
               time = computeDFSIntervals(child, time);
           }
           curr->DFSOut = ++time;
           return time;
       }

       // 阶段 3: Cytron 支配边界算法
       void computeDominanceFrontiers(FlowGraph& graph) {
           for (const auto& b : graph.Nodes) {
               if (b->Predecessors.size() >= 2) {
                   for (BlockNode* p : b->Predecessors) {
                       BlockNode* runner = p;
                       DomTreeNode* bDom = NodeMap[b.get()]->IDom;
                       BlockNode* idomBlock = bDom ? bDom->Block : nullptr;

                       while (runner != idomBlock && runner != nullptr) {
                           DominanceFrontiers[runner].insert(b.get());
                           DomTreeNode* runnerDom = NodeMap[runner]->IDom;
                           runner = runnerDom ? runnerDom->Block : nullptr;
                       }
                   }
               }
           }
       }
   };

   // =========================================================================
   // 3. 自然循环 (Natural Loop) 分析器
   // =========================================================================
   struct NaturalLoop {
       BlockNode* Header = nullptr;
       BlockNode* Latch = nullptr;
       std::unordered_set<BlockNode*> Blocks;

       bool contains(BlockNode* b) const {
           return Blocks.find(b) != Blocks.end();
       }
   };

   class LoopInfo {
   public:
       std::vector<NaturalLoop> Loops;

       void analyzeLoops(FlowGraph& graph, const DominatorTree& domTree) {
           Loops.clear();

           // 1. 探测回边: 边 (A -> B) 且 B dom A
           for (const auto& block : graph.Nodes) {
               for (BlockNode* succ : block->Successors) {
                   if (domTree.dominates(succ, block.get())) {
                       // 命中回边: block -> succ
                       NaturalLoop loop;
                       loop.Header = succ;
                       loop.Latch = block.get();
                       constructLoopNodes(loop);
                       Loops.push_back(std::move(loop));
                   }
               }
           }
       }

   private:
       // 逆向工作表追溯循环体所有成员节点
       void constructLoopNodes(NaturalLoop& loop) {
           loop.Blocks.insert(loop.Header);
           loop.Blocks.insert(loop.Latch);

           std::queue<BlockNode*> worklist;
           if (loop.Latch != loop.Header) {
               worklist.push(loop.Latch);
           }

           while (!worklist.empty()) {
               BlockNode* curr = worklist.front();
               worklist.pop();

               for (BlockNode* pred : curr->Predecessors) {
                   if (loop.Blocks.insert(pred).second) {
                       worklist.push(pred);
                   }
               }
           }
       }
   };

   } // namespace dom_loop_engine

   // =========================================================================
   // 4. 端到端测试与拓扑验证套件
   // =========================================================================
   namespace test {

   inline void runDomAndLoopTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 支配树、支配边界 (DF) 与自然循环 (Natural Loop) 验证
";
       std::cout << "=======================================================

";

       // 构造一个经典的多重分支与循环控制流图:
       //
       //        [ Entry (0) ]
       //              |
       //              v
       //        [ Header (1) ] <---------+ (Loop Backedge)
       //             / \                 |
       //    (true)  /   \ (false)        |
       //           v     v               |
       //       [ Body (2) ] [ Exit (3) ] |
       //           |                     |
       //           v                     |
       //       [ Latch (4) ] ------------+
       //
       // 附加一个不可达孤岛块: [ Dead (5) ] -> [ Exit (3) ]

       using namespace dom_loop_engine;
       FlowGraph fg;

       BlockNode* bEntry = fg.addBlock("entry");
       BlockNode* bHeader = fg.addBlock("loop.header");
       BlockNode* bBody = fg.addBlock("loop.body");
       BlockNode* bExit = fg.addBlock("loop.exit");
       BlockNode* bLatch = fg.addBlock("loop.latch");
       BlockNode* bDead = fg.addBlock("dead.block");

       fg.Entry = bEntry;

       // 建立有效边
       fg.addEdge(bEntry, bHeader);
       fg.addEdge(bHeader, bBody);
       fg.addEdge(bHeader, bExit);
       fg.addEdge(bBody, bLatch);
       fg.addEdge(bLatch, bHeader); // 回边: Latch -> Header

       // 建立不可达边
       fg.addEdge(bDead, bExit);

       std::cout << "[测试 1: 不可达基本块修剪]
";
       std::cout << "  修剪前节点总数: " << fg.Nodes.size() << "
";
       fg.eliminateUnreachableBlocks();
       std::cout << "  修剪后节点总数: " << fg.Nodes.size() << "
";
       assert(fg.Nodes.size() == 5);
       std::cout << "  -> 成功移除孤岛节点 dead.block。

";

       // 2. 构建支配树
       std::cout << "[测试 2: 支配树构建与支配关系判定]
";
       DominatorTree domTree;
       domTree.build(fg);

       // 验证支配关系: Entry 支配全图所有节点
       for (const auto& n : fg.Nodes) {
           assert(domTree.dominates(bEntry, n.get()));
       }

       // 验证 Header 严格支配 Body 与 Latch
       assert(domTree.strictlyDominates(bHeader, bBody));
       assert(domTree.strictlyDominates(bHeader, bLatch));

       // 验证 Body 不支配 Exit
       assert(!domTree.dominates(bBody, bExit));

       std::cout << "  Entry dom all nodes: OK
";
       std::cout << "  Header sdom Body & Latch: OK
";
       std::cout << "  Body dom Exit: FALSE (符合预期)
";
       std::cout << "  -> 支配树层次构建验证通过。

";

       // 3. 支配边界 (DF) 计算验证
       std::cout << "[测试 3: 支配边界 (Dominance Frontier) 计算]
";
       // 在该 CFG 中:
       // Latch 支配由其自身到达 Header 的前驱边，但 Header 不被 Latch 严格支配 (Header 支配 Latch)
       // 因此: DF(Latch) 应包含 { loop.header }
       const auto& dfLatch = domTree.DominanceFrontiers[bLatch];
       std::cout << "  DF(loop.latch) 包含节点: ";
       for (BlockNode* dfNode : dfLatch) {
           std::cout << dfNode->Name << " ";
       }
       std::cout << "
";
       assert(dfLatch.count(bHeader) == 1);
       std::cout << "  -> 支配边界集合验证通过。

";

       // 4. 自然循环与回边识别
       std::cout << "[测试 4: 自然循环 (Natural Loop) 与回边探测]
";
       LoopInfo loopInfo;
       loopInfo.analyzeLoops(fg, domTree);

       assert(loopInfo.Loops.size() == 1);
       const auto& loop = loopInfo.Loops[0];
       std::cout << "  检测到自然循环: Header = " << loop.Header->Name
                 << ", Latch = " << loop.Latch->Name << "
";
       std::cout << "  循环包含的基本块集合: ";
       for (BlockNode* b : loop.Blocks) {
           std::cout << b->Name << " ";
       }
       std::cout << "
";

       assert(loop.Header == bHeader);
       assert(loop.Latch == bLatch);
       assert(loop.contains(bHeader) && loop.contains(bBody) && loop.contains(bLatch));
       assert(!loop.contains(bExit)); // Exit 不属于循环体
       std::cout << "  -> 自然循环识别与节点提取完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了各图论算法的运行轨迹：

1. **不可达孤岛剔除**：DFS 标记成功捕获了缺乏入口可达路径的 ``dead.block``，并在安全解绑其对 ``loop.exit`` 的前驱边后予以物理释放，净化了输入流图。
2. **直接支配者拓扑确立**：算法精准求解了 $idom(	ext{loop.header}) = 	ext{entry}$、$idom(	ext{loop.body}) = 	ext{loop.header}$，以及 $idom(	ext{loop.exit}) = 	ext{loop.header}$，并在 $\mathcal{O}(1)$ 内完成了祖先支配范围判定。
3. **支配边界映射与 SSA 准备**：精确计算出 $	ext{DF}(	ext{loop.latch}) = \{	ext{loop.header}\}$，证明了在循环体内被修改的变量必须在 ``loop.header`` 处放置 $\phi$ 节点进行历史值合并。
4. **自然循环闭环重构**：逆向工作表算法精准圈定了循环体包含节点集合 $\{	ext{loop.header}, 	ext{loop.body}, 	ext{loop.latch}\}$，并将出口块 ``loop.exit`` 排除在外。

小结与下章导读
--------------

本章系统解构了现代编译器中端从局部控制流向全局支配与循环拓扑升维的核心机理：

1. **不可达代码图剪枝**：阐明了 DFS/BFS 可达性分析对清理无用基本块、消除悬垂前驱与维护数据流单调性的基础作用。
2. **支配关系与支配树拓扑**：形式化定义了 $d 	ext{ dom } n$ 与直接支配者 $idom(n)$，推导了利用 DFS 进入/离开时间戳实现 $\mathcal{O}(1)$ 常数时间支配查询的高效机制。
3. **支配边界（DF）理论**：解构了变量定值离开其支配区域的数学边界，确立了 SSA 形式下 $\phi$ 节点最小化放置的算法基石。
4. **自然循环与回边检测**：建立了基于 $B 	ext{ dom } A$ 判定的回边模型，阐释了单入口 Header、Latch 逆向节点收集以及 Preheader 规范化对循环优化的重要支撑。

在掌握了支配树与支配边界之后，编译器的中端表示将迎来现代优化历史上最核心的飞跃——**静态单赋值（SSA）形式**。在第 4 模块第 4 节 **SSA 静态单赋值形式核心：变量槽位向唯一计算值映射、Phi 节点语义与 Mem2Reg 栈提升（``04_ir_cfg_and_ssa_construction/04_ssa_form_value_identity_and_phi_nodes.rst``）** 中，我们将深入剖析为何传统变量覆盖赋值会破坏数据依赖链、Cytron 最小化 $\phi$ 节点插入算法、变量重命名（Variable Renaming）状态机，以及将栈上分配（``alloca``）彻底提升为纯粹寄存器值流的 Mem2Reg Pass 物理实现。
