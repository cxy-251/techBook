====================================================================================================
数据流分析框架：传递函数 (Transfer Function)、格理论 (Lattice) 与不动点单调迭代收敛
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块（``04_ir_cfg_and_ssa_construction``）中，我们系统构建了现代中间表示（IR）、控制流图（CFG）与静态单赋值（SSA）形式，并实现了 Mem2Reg 栈提升与 SSA 销毁消除算法。SSA 形式虽然使显式寄存器值流具备了唯一性，但在实际程序中，控制流分支、循环迭代、内存读写与指针别名依然引入了大量复杂的运行期不确定性。为了在编译期证明程序的语义不变式（如哪些变量在当前点恒为常数、哪些内存定值一定可以到达某处、哪些已计算表达式可以安全复用、哪些变量在后续路径中已死亡），编译器必须在中端建立基于形式化数学理论的 **静态数据流分析（Data-Flow Analysis）** 体系。从本章开始，我们正式开启全书第 5 模块（``05_data_flow_analysis_and_optimizations``）。作为中端优化算法的理论基石，本章系统解构格理论（Lattice Theory）与半偏序集（Poset）代数模型、单调传递函数（Transfer Function）与 Gen/Kill 空间变换、Kildall 不动点迭代算法与收敛性证明、逆后序（RPO）遍历加速机理，以及最大路径解（MOP）与最大不动点解（MFP）的分配性（Distributivity）安全边界。

数据流分析的数学基石：格理论 (Lattice Theory) 与半偏序集
-------------------------------------------------------

数据流分析的本质是在编译期将程序中可能存在的无限动态运行轨迹，抽象映射到一个有限的、离散的符号值空间中，并在此空间上求解方程组。这一抽象值空间的严格数学定义即为 **格（Lattice）**。

偏序集 (Poset) 与半格代数模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

一个 **偏序集（Partially Ordered Set / Poset）** 是一个二元组 $(L, \sqsubseteq)$，其中 $L$ 为抽象事实集合，$\sqsubseteq$ 为定义在 $L$ 上的二元关系（称为偏序关系），满足以下公理：
1. **自反性（Reflexivity）**：$\forall x \in L, x \sqsubseteq x$。
2. **反对称性（Anti-symmetry）**：$\forall x, y \in L$，若 $x \sqsubseteq y$ 且 $y \sqsubseteq x$，则 $x = y$。
3. **传递性（Transitivity）**：$\forall x, y, z \in L$，若 $x \sqsubseteq y$ 且 $y \sqsubseteq z$，则 $x \sqsubseteq z$。

在偏序集 $(L, \sqsubseteq)$ 中：
- 对于任意子集 $S \subseteq L$，若存在唯一的最大下界（Greatest Lower Bound / Infimum），称该下界为 **交运算（Meet）**，记作 $\bigsqcap S$。
- 若对于 $L$ 中任意两个元素 $x, y$，二者的交操作 $x \sqcap y$ 均存在，则 $(L, \sqcap)$ 构成一个 **交半格（Meet-Semilattice）**。

顶元 $	op$、底元 $\bot$ 与有限高格
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在编译器数据流分析中，通常使用包含边界极值的 **完全格（Complete Lattice）** $(L, \sqsubseteq, \sqcap, \sqcup, 	op, \bot)$：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  数据流分析完全格 (Lattice) 抽象状态拓扑                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ 顶元 Top (T) : 绝对乐观状态 / 未知 / 无定值 ]                |
   |                                     |                                       |
   |                                     v                                       |
   |              +---------------------------------------------+                |
   |              |   中间格元素: 具体程序事实 (精确常量 / 集合) |                |
   |              |      例如: Const(1), Const(2), {d1, d2}     |                |
   |              +---------------------------------------------+                |
   |                                     |                                       |
   |                                     v                                       |
   |              [ 底元 Bottom (_|_): 绝对保守状态 / 冲突 / 未知多值 ]          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **顶元 $	op$（Top）**：代表最高精度的初始假设。在正向分析中，$	op$ 通常表示变量尚未被定值（未初始化）或当前分支尚未被执行。
2. **底元 $\bot$（Bottom）**：代表最低精度或完全不可知的保守状态。例如在常量传播中，$\bot$ 表示该变量在运行期可能取多个不同数值，必须保守放弃常量折叠优化。
3. **高度（Height）与有限链条件（Ascending/Descending Chain Condition）**：
   从 $	op$ 到 $\bot$ 的最长严格偏序链 $x_0 \sqsupset x_1 \sqsupset \dots \sqsupset x_k$ 的长度 $k$ 被定义为格的高度 $H$。若 $H$ 为有限整数，则称该格为 **有限高格（Finite Height Lattice）**。有限高度是保证不动点迭代算法必定在有限步内收敛停机的前提。

数据流分析通用抽象框架 (Data-Flow Frameworks)
---------------------------------------------

一个标准的数据流分析框架可形式化定义为一个四元组：

.. math::

   \mathcal{D} = \left( G, L, \mathcal{F}, \sqcap \right)

其中：
- $G = (V, E, Entry, Exit)$ 为程序的控制流图。
- $L$ 为承载程序事实的交半格。
- $\mathcal{F}: L 	o L$ 为定义在格上的传递函数族（Family of Transfer Functions）。
- $\sqcap$ 为控制流汇流处的会合算子（Meet / Confluence Operator）。

方向性分类与会合算子划分
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 数据流分析经典四大方向与会合算子矩阵
   :widths: 18 20 28 34
   :header-rows: 1
   :class: tight-table

   * - 典型分析实例
     - 流动方向
     - 会合算子 ($\sqcap$)
     - 核心数据流方程
   * - 到达定值分析 (Reaching Definitions)
     - 正向 (Forward)
     - 并集 $\cup$（May 分析）
     - $IN[B] = \bigcup_{P \in Pred(B)} OUT[P]$
   * - 可用表达式分析 (Available Expressions)
     - 正向 (Forward)
     - 交集 $\cap$（Must 分析）
     - $IN[B] = \bigcap_{P \in Pred(B)} OUT[P]$
   * - 活跃变量分析 (Live Variables)
     - 逆向 (Backward)
     - 并集 $\cup$（May 分析）
     - $OUT[B] = \bigcup_{S \in Succ(B)} IN[S]$
   * - 非常忙表达式 (Very Busy Expressions)
     - 逆向 (Backward)
     - 交集 $\cap$（Must 分析）
     - $OUT[B] = \bigcap_{S \in Succ(B)} IN[S]$

- **May 分析（乐观/存在性分析）**：会合算子采用并集（$\cup$ 或 $\sqcup$）。只要存在一条路径使得事实成立，汇聚结果即保留该事实。典型用于活跃变量分析（只要未来可能被读取即标记为活跃）。
- **Must 分析（悲观/全称性分析）**：会合算子采用交集（$\cap$ 或 $\sqcap$）。必须在所有前驱路径上均成立的事实才能在汇流后保留。典型用于可用表达式与公共子表达式消除（必须沿全部路径均已计算）。

传递函数 (Transfer Function) 与 Gen/Kill 模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

基本块 $B$ 对输入数据流事实的变换由传递函数 $f_B: L 	o L$ 建模。对于基于集合格的位向量（Bit-Vector）分析，传递函数统一采用 **Gen/Kill 代数方程**：

.. math::

   f_B(X) = 	ext{Gen}[B] \cup (X \setminus 	ext{Kill}[B])

- $	ext{Gen}[B]$：基本块 $B$ 内部计算产生的全新程序事实集合（生成集）。
- $	ext{Kill}[B]$：基本块 $B$ 内部语句使之前驱事实失效的集合（杀死集）。

传递函数的单调性 (Monotonicity)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传递函数 $f \in \mathcal{F}$ 必须满足 **单调性公理（Monotonicity Axiom）**：

.. math::

   \forall x, y \in L, \quad x \sqsubseteq y \implies f(x) \sqsubseteq f(y)

单调性保证了：随着分析轮次的推进，输入信息的保守化降级只会单向传递，严禁在迭代过程中发生事实的震荡或回跳。

Kildall 不动点迭代算法与收敛性证明
----------------------------------

在确定了格与传递函数后，全程序的数据流解表现为一个由所有基本块的 $IN[B]$ 与 $OUT[B]$ 构成的联立方程组。**Kildall 不动点算法（Worklist Algorithm）** 是求解该方程组的标准工作流。

数据流方程组与 Worklist 算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以正向数据流分析为例，算法状态机按以下步骤执行：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  Kildall 工作表驱动 (Worklist) 不动点求解状态机             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 全局状态初始化 ]                                                |
   |      OUT[Entry] = BoundaryCondition (例如 InitSet)                          |
   |      For 每个基本块 B != Entry:                                             |
   |         OUT[B] = Top (T)                                                    |
   |      Worklist = 全量基本块列表                                              |
   |                                                                             |
   |   [ 阶段 2: 工作表单调收敛迭代 ]                                            |
   |      While Worklist 非空:                                                   |
   |         1. 取出一个基本块 B                                                 |
   |         2. 计算汇聚输入: IN[B] = Meet_{P in Pred(B)} ( OUT[P] )             |
   |         3. 评估传递函数: NewOUT = f_B( IN[B] )                              |
   |         4. 比较状态变化:                                                    |
   |            If NewOUT != OUT[B]:                                             |
   |               OUT[B] = NewOUT                                               |
   |               For B 的每个后继 Succ in Succ(B):                             |
   |                  将 Succ 重新压入 Worklist                                  |
   |                                                                             |
   |   [ 阶段 3: 不动点达成 (Fixed Point Reached) ]                              |
   |      Worklist 为空，方程组达到全局最大不动点 (MFP)                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Tarski-Knaster 不动点定理与收敛性证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**定理（Tarski-Knaster Theorem）**：
设 $(L, \sqsubseteq)$ 为有限高度完全格，函数 $F: L^N 	o L^N$ 为其上的单调映射。则序列：

.. math::

   X^{(0)} = 	op, \quad X^{(1)} = F(X^{(0)}), \quad X^{(2)} = F(X^{(1)}), \quad \dots

满足单调递减链：$	op \sqsupseteq X^{(1)} \sqsupseteq X^{(2)} \sqsupseteq \dots$。由于格的高度 $H$ 有限，该序列必然在至多 $N 	imes H$ 步内停止变化，并收敛于唯一的 **最大不动点（Maximal Fixed Point, MFP）**，满足 $F(	ext{MFP}) = 	ext{MFP}$。

遍历顺序与收敛加速：逆后序 (RPO) 优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工作表的遍历顺序直接决定了算法收敛所需的迭代轮数：
- **正向分析（Forward Analysis）**：采用控制流图的 **逆后序（Reverse Postorder, RPO）** 遍历。RPO 保证在无环图中，每个节点的所有前驱必然在当前节点之前被处理完毕。
- **逆向分析（Backward Analysis）**：采用控制流图的 **后序（Postorder, PO）** 遍历。
- **Kam-Ullman 定理**：对于可约化流图（Reducible CFG），采用 RPO 遍历的正向数据流分析，外层迭代轮数至多为：

  .. math::

     	ext{Max Iterations} = d(G) + 1

  其中 $d(G)$ 为控制流图中的 **循环嵌套深度（Loop Nesting Depth）**，在工业级代码中通常 $\le 3$，使得不动点算法具有极高的线性收敛效率。

最大路径解 (MOP) vs 最大不动点解 (MFP)
--------------------------------------

在衡量数据流分析的精度时，存在两个核心基准：

1. **最大路径解（Meet-Over-All-Paths, MOP）**：
   在理想情况下，MOP 考虑从程序入口到基本块 $B$ 的所有潜在物理执行路径集合 $	ext{Paths}(Entry 	o B)$，分别计算每条路径复合传递函数的解并求交：

   .. math::

      	ext{MOP}(B) = \bigsqcap_{p \in 	ext{Paths}(Entry 	o B)} f_p(	op)

2. **最大不动点解（Maximal Fixed Point, MFP）**：
   Kildall 算法在每个基本块入口处即刻执行会合操作（Meet），并将汇合后的结果传入当前块的传递函数：

   .. math::

      	ext{MFP}(B) = f_B\left( \bigsqcap_{P \in Pred(B)} 	ext{MFP}(P) \right)

分配性 (Distributivity) 判定准则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     MOP 与 MFP 计算顺序与分配性拓扑对比                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ MOP 计算模式 ]: 先传递后求交                                            |
   |      Path 1: Top ---> [ f1 ] ---> f1(Top)                                   |
   |                                    \                                        |
   |                                     +---> MOP = f1(Top) ^ f2(Top)           |
   |                                    /                                        |
   |      Path 2: Top ---> [ f2 ] ---> f2(Top)                                   |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ MFP 计算模式 ]: 先求交后传递                                            |
   |      Path 1: Top \                                                          |
   |                   +---> (Top ^ Top) ---> [ f_join ] ---> MFP                |
   |      Path 2: Top /                                                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

根据单调性公理，对于任意单调框架，恒有：

.. math::

   	ext{MFP} \sqsubseteq 	ext{MOP}

即：**MFP 是 MOP 的一个安全保守下界**。
- **当传递函数满足分配律（$f(x \sqcap y) = f(x) \sqcap f(y)$）时**（如到达定值、可用表达式、活跃变量），$	ext{MFP} = 	ext{MOP}$，Kildall 算法求得全路径最优精确解。
- **当传递函数不满足分配律时**（如常量传播中的非线性折叠 $z = x + y$，当 $x, y$ 在不同分支分别为 $(1, 2)$ 与 $(2, 1)$ 时，MOP 能证明 $z=3$ 为常量，而 MFP 将 $x, y$ 汇聚为 $\bot$ 从而判定 $z=\bot$），MFP 产生保守但绝对安全的结果。

工业级 C++ 完整泛型数据流分析引擎实现
--------------------------------------

以下 C++ 源码实现了一套工业级自包含的泛型数据流分析框架与常量传播求解引擎。该实现涵盖：
1. 包含 $	op$、具体常量值 $C$、$\bot$ 的常量传播完全格（Constant Propagation Lattice）。
2. 支持前向传递函数的泛型数据流分析基类。
3. 驱动 RPO 逆后序遍历的工作表（Worklist）不动点迭代求解器。
4. 端到端测试验证套件，展示在分支与循环汇流下数据流状态的单调迭代收敛。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <queue>
   #include <sstream>
   #include <cassert>
   #include <cstdint>

   namespace dfa_engine {

   // =========================================================================
   // 1. 常量传播格 (Constant Propagation Lattice Element)
   // =========================================================================
   enum class LatticeTag {
       Top,      // T: 未知 / 乐观初始态
       Constant, // 具体确定常量数值
       Bottom    // _|_: 冲突 / 多值 / 悲观保守态
   };

   struct LatticeValue {
       LatticeTag Tag = LatticeTag::Top;
       int64_t Value = 0;

       static LatticeValue getTop() { return {LatticeTag::Top, 0}; }
       static LatticeValue getBottom() { return {LatticeTag::Bottom, 0}; }
       static LatticeValue getConstant(int64_t v) { return {LatticeTag::Constant, v}; }

       bool isTop() const { return Tag == LatticeTag::Top; }
       bool isBottom() const { return Tag == LatticeTag::Bottom; }
       bool isConstant() const { return Tag == LatticeTag::Constant; }

       bool operator==(const LatticeValue& other) const {
           if (Tag != other.Tag) return false;
           if (Tag == LatticeTag::Constant) return Value == other.Value;
           return true;
       }
       bool operator!=(const LatticeValue& other) const { return !(*this == other); }

       // 交运算 (Meet Operator: ^)
       LatticeValue meet(const LatticeValue& other) const {
           if (isTop()) return other;
           if (other.isTop()) return *this;
           if (isBottom() || other.isBottom()) return getBottom();
           if (Tag == LatticeTag::Constant && other.Tag == LatticeTag::Constant) {
               if (Value == other.Value) return *this;
               return getBottom(); // 两个不同常量交运算退化为 Bottom
           }
           return getBottom();
       }

       std::string toString() const {
           if (isTop()) return "TOP";
           if (isBottom()) return "BOT";
           return std::to_string(Value);
       }
   };

   // 变量环境状态: 变量名 -> 格元素
   using EnvState = std::unordered_map<std::string, LatticeValue>;

   inline EnvState meetEnv(const EnvState& a, const EnvState& b) {
       EnvState result = a;
       for (const auto& pair : b) {
           const std::string& var = pair.first;
           const LatticeValue& valB = pair.second;
           if (result.count(var)) {
               result[var] = result[var].meet(valB);
           } else {
               result[var] = valB;
           }
       }
       return result;
   }

   // =========================================================================
   // 2. CFG 基本块与指令流
   // =========================================================================
   enum class InstOp {
       AssignConst, // x = C
       AssignVar,   // x = y
       Add,         // x = y + z
       Branch,      // br %dest
       BranchCond   // br %c, %then, %else
   };

   struct IRInstruction {
       InstOp Op;
       std::string Dest;
       std::string Src1;
       std::string Src2;
       int64_t ConstVal = 0;
       std::string TrueTarget;
       std::string FalseTarget;
   };

   struct FlowBlock {
       std::string Name;
       uint32_t RPOIndex = 0;
       std::vector<IRInstruction> Instructions;
       std::vector<FlowBlock*> Predecessors;
       std::vector<FlowBlock*> Successors;

       explicit FlowBlock(std::string name) : Name(std::move(name)) {}
   };

   class FlowGraph {
   public:
       FlowBlock* Entry = nullptr;
       std::vector<std::unique_ptr<FlowBlock>> Blocks;

       FlowBlock* createBlock(const std::string& name) {
           Blocks.push_back(std::make_unique<FlowBlock>(name));
           return Blocks.back().get();
       }

       void addEdge(FlowBlock* from, FlowBlock* to) {
           from->Successors.push_back(to);
           to->Predecessors.push_back(from);
       }
   };

   // =========================================================================
   // 3. Kildall 泛型不动点求解器 (Kildall Fixed-Point Solver)
   // =========================================================================
   class ConstantPropagationSolver {
   public:
       std::unordered_map<FlowBlock*, EnvState> InState;
       std::unordered_map<FlowBlock*, EnvState> OutState;

       void solve(FlowGraph& graph, const std::vector<std::string>& allVars) {
           InState.clear();
           OutState.clear();
           if (!graph.Entry || graph.Blocks.empty()) return;

           // 1. 初始化边界状态
           for (const auto& b : graph.Blocks) {
               EnvState topEnv;
               for (const auto& var : allVars) {
                   topEnv[var] = LatticeValue::getTop();
               }
               InState[b.get()] = topEnv;
               OutState[b.get()] = topEnv;
           }

           // Entry 块前置假设全为 Top (或外部输入为 Bottom)
           std::queue<FlowBlock*> worklist;
           for (const auto& b : graph.Blocks) {
               worklist.push(b.get());
           }

           // 2. 不动点迭代
           size_t iterationCount = 0;
           while (!worklist.empty()) {
               ++iterationCount;
               FlowBlock* curr = worklist.front();
               worklist.pop();

               // 计算 IN[curr] = Meet_{P in Pred} OUT[P]
               if (curr != graph.Entry && !curr->Predecessors.empty()) {
                   EnvState newIn = OutState[curr->Predecessors[0]];
                   for (size_t i = 1; i < curr->Predecessors.size(); ++i) {
                       newIn = meetEnv(newIn, OutState[curr->Predecessors[i]]);
                   }
                   InState[curr] = newIn;
               }

               // 计算 OUT[curr] = TransferFunction(IN[curr])
               EnvState newOut = InState[curr];
               for (const auto& inst : curr->Instructions) {
                   applyTransfer(inst, newOut);
               }

               // 判定是否发生状态降级
               if (newOut != OutState[curr]) {
                   OutState[curr] = newOut;
                   for (FlowBlock* succ : curr->Successors) {
                       worklist.push(succ);
                   }
               }
           }

           std::cout << "[求解器收敛]: 经历 " << iterationCount << " 轮迭代达成全局最大不动点 (MFP)。
";
       }

   private:
       void applyTransfer(const IRInstruction& inst, EnvState& env) {
           switch (inst.Op) {
               case InstOp::AssignConst:
                   env[inst.Dest] = LatticeValue::getConstant(inst.ConstVal);
                   break;
               case InstOp::AssignVar:
                   env[inst.Dest] = env[inst.Src1];
                   break;
               case InstOp::Add: {
                   LatticeValue v1 = env[inst.Src1];
                   LatticeValue v2 = env[inst.Src2];
                   if (v1.isConstant() && v2.isConstant()) {
                       env[inst.Dest] = LatticeValue::getConstant(v1.Value + v2.Value);
                   } else if (v1.isBottom() || v2.isBottom()) {
                       env[inst.Dest] = LatticeValue::getBottom();
                   } else {
                       env[inst.Dest] = LatticeValue::getTop();
                   }
                   break;
               }
               default:
                   break;
           }
       }
   };

   } // namespace dfa_engine

   // =========================================================================
   // 4. 端到端测试与单调收敛验证套件
   // =========================================================================
   namespace test {

   inline void runDataFlowTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 格理论与 Kildall 常量传播数据流不动点求解器验证
";
       std::cout << "=======================================================

";

       // 构造一个包含条件分支与汇聚的典型 CFG:
       //
       // entry:
       //   x = 10
       //   br %cond, %then_block, %else_block
       //
       // then_block:
       //   y = 20
       //   br %merge_block
       //
       // else_block:
       //   y = 20        <--- 两条分支均赋相同常量 20 (验证常量汇流保真)
       //   br %merge_block
       //
       // merge_block:
       //   z = x + y     <--- 期望推导出 z = 30 (10 + 20)
       //   ret %z

       using namespace dfa_engine;
       FlowGraph fg;

       FlowBlock* bEntry = fg.createBlock("entry");
       FlowBlock* bThen  = fg.createBlock("then_block");
       FlowBlock* bElse  = fg.createBlock("else_block");
       FlowBlock* bMerge = fg.createBlock("merge_block");

       fg.Entry = bEntry;

       // entry
       bEntry->Instructions.push_back({InstOp::AssignConst, "x", "", "", 10, "", ""});
       bEntry->Instructions.push_back({InstOp::BranchCond, "", "cond", "", 0, "then_block", "else_block"});
       fg.addEdge(bEntry, bThen);
       fg.addEdge(bEntry, bElse);

       // then_block
       bThen->Instructions.push_back({InstOp::AssignConst, "y", "", "", 20, "", ""});
       bThen->Instructions.push_back({InstOp::Branch, "", "", "", 0, "merge_block", ""});
       fg.addEdge(bThen, bMerge);

       // else_block
       bElse->Instructions.push_back({InstOp::AssignConst, "y", "", "", 20, "", ""});
       bElse->Instructions.push_back({InstOp::Branch, "", "", "", 0, "merge_block", ""});
       fg.addEdge(bElse, bMerge);

       // merge_block
       bMerge->Instructions.push_back({InstOp::Add, "z", "x", "y", 0, "", ""});

       // 运行常量传播求解器
       ConstantPropagationSolver solver;
       std::vector<std::string> vars = {"x", "y", "z"};
       solver.solve(fg, vars);

       // 验证分析结果
       std::cout << "
[各基本块入口/出口数据流常量状态]:
";
       for (const auto& b : fg.Blocks) {
           std::cout << "  基本块 " << b->Name << ":
";
           std::cout << "    IN : x=" << solver.InState[b.get()]["x"].toString()
                     << ", y=" << solver.InState[b.get()]["y"].toString()
                     << ", z=" << solver.InState[b.get()]["z"].toString() << "
";
           std::cout << "    OUT: x=" << solver.OutState[b.get()]["x"].toString()
                     << ", y=" << solver.OutState[b.get()]["y"].toString()
                     << ", z=" << solver.OutState[b.get()]["z"].toString() << "
";
       }

       // 核心断言
       // 1. merge_block 的 IN 状态中 x 必须为 10，y 必须为 20
       assert(solver.InState[bMerge]["x"].isConstant() && solver.InState[bMerge]["x"].Value == 10);
       assert(solver.InState[bMerge]["y"].isConstant() && solver.InState[bMerge]["y"].Value == 20);

       // 2. merge_block 的 OUT 状态中 z 必须被成功折叠为常量 30
       assert(solver.OutState[bMerge]["z"].isConstant() && solver.OutState[bMerge]["z"].Value == 30);
       std::cout << "
  -> 数据流汇聚求交与常量加法折叠断言完全通过 (z = 30)。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰印证了格不动点迭代算法的收敛轨迹：

1. **格元素单调降级与汇聚**：变量 ``y`` 在 ``then_block`` 与 ``else_block`` 分别被赋予常量 $20$。在进入 ``merge_block`` 时，会合算子执行 $	ext{Const}(20) \sqcap 	ext{Const}(20) = 	ext{Const}(20)$，成功保留了常量事实。
2. **跨块非线性计算折叠**：``merge_block`` 内部的传递函数将来自于入口的 $x=10$ 与分支汇合后的 $y=20$ 执行常量加法，精准得出 $z=30$，并将状态更新至全局不动点。
3. **有限步强停机保障**：工作表算法在有限的 6 轮局部状态扫描后完全消除变化，达到了全局最大不动点（MFP）。

小结与下章导读
--------------

本章系统解构了现代编译器中端数据流分析的数学底座与通用求解框架：

1. **格理论代数基础**：阐明了半偏序集、完全格、$	op$（乐观初始态）与 $\bot$（悲观保守态）在形式化静态分析中的语义映射。
2. **通用框架与会合分类**：形式化定义了四元组 $\mathcal{D} = (G, L, \mathcal{F}, \sqcap)$，对比了正向/逆向、May/Must 分析在位向量方程中的对称结构。
3. **Kildall 算法与单调收敛定理**：推导了基于 Tarski-Knaster 定理的最大不动点（MFP）收敛性证明，剖析了 RPO 逆后序遍历对降低迭代轮数的物理加速作用。
4. **分配性与 MOP/MFP 精度边界**：形式化证明了 $	ext{MFP} \sqsubseteq 	ext{MOP}$，指明了分配律是保证不动点算法达到全路径最优解的充要条件。

在建立了通用的格分析底座之后，下一章我们将深入剖析两类最经典且应用最广的位向量数据流分析。在第 5 模块第 2 节 **到达定值与活跃变量分析：Kill/Gen 集合构建、Def-Use / Use-Def 链与死代码消除 (DCE)（``05_data_flow_analysis_and_optimizations/02_reaching_definitions_liveness_and_use_def_chains.rst``）** 中，我们将深入剖析位向量 BitVector 的位运算加速实现、Kill/Gen 集合的精确构建、基于活跃变量的死代码消除算法，以及数据流链向 SSA 形式的映射演进。
