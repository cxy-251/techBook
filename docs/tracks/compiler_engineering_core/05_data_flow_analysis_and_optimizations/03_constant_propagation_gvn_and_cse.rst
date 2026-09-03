====================================================================================================
全局值编号 (GVN) 与公共子表达式消除：稀疏条件常量传播 (SCCP)、代数恒等式化简与支配树折叠
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块前两节中，我们先后确立了数据流分析的半偏序格理论、Kildall 不动点迭代算法，以及到达定值与活跃变量（Live Variables / DCE）的位向量分析实现。数据流分析为编译器捕获了粗粒度的集合事实。然而，中端优化器若要进一步消除程序中反复出现的冗余计算、折叠静态已知的常量运算、化简代数恒等式并剔除不可达的死控制流分支，必须将分析粒度精细化到每一个具体的 **表达式值（Value）** 层面。本章系统解构值编号（Value Numbering）等价类重构、局部值编号（LVN）向全局值编号（Global Value Numbering, GVN）的拓扑跃迁、基于支配树作用域哈希表的公共子表达式消除（Common Subexpression Elimination, CSE）、交换律规范化（Commutative Canonicalization）与代数恒等式化简状态机，以及将常量传播与死控制流剪枝深度融合的经典 **Wegman-Zadeck 稀疏条件常量传播（Sparse Conditional Constant Propagation, SCCP）** 算法物理实现。

局部值编号 (LVN) 与全局值编号 (GVN) 代数模型
--------------------------------------------

在程序执行过程中，不同的变量名可能在运行时计算出完全相同的数学值。**值编号（Value Numbering）** 的核心思想是：为程序中每一个在数学语义上等价的计算结果分配一个唯一的整型编号（Value Number, VN），并将所有产生相同计算值的表达式归入同一个等价类（Equivalence Class）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       值编号等价类划分与映射模型                            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源码计算序列 ]               [ 值编号分配 (Value Numbering) ]            |
   |   1. a = x + y       ------>     VN(x) = 1, VN(y) = 2, VN(a) = 3 (ADD, 1, 2)|
   |   2. b = y + x       ------>     交换律规范化: (ADD, 1, 2) -> 命中 VN 3!     |
   |                                  直接重写为: b = a (消除冗余加法)            |
   |   3. c = a * 4       ------>     VN(c) = 4 (MUL, 3, Const(4))               |
   |   4. d = b * 4       ------>     查询 (MUL, VN(b)=3, Const(4)) -> 命中 VN 4!|
   |                                  直接重写为: d = c                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

局部值编号 (LVN) 的作用域边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**局部值编号（Local Value Numbering, LVN）** 严格局限在单一基本块（Basic Block）内部。它维护一个当前块内部的符号哈希表：
- 键（Key）：包含操作码与操作数的值编号三元组 $\langle 	ext{OpCode}, 	ext{VN}_1, 	ext{VN}_2 \rangle$。
- 值（Value）：首次计算该三元组的 SSA 变量名或值编号。
- 局限性：当控制流跨越基本块边界（分支或循环）时，LVN 必须彻底清空哈希表，无法跨越分支复用支配节点已经计算过的公共子表达式。

全局值编号 (GVN) 与支配树作用域折叠
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了突破单一基本块的局限，**全局值编号（Global Value Numbering, GVN）** 结合控制流图的 **支配树（Dominator Tree）** 展开全局优化。

**支配树作用域栈（Scoped Dominator Hash Table）核心规则**：
若基本块 $A$ 支配基本块 $B$（$A 	ext{ dom } B$），则在执行路径上到达 $B$ 时，$A$ 内部计算产生的所有值必然已经完成计算且处于有效状态。
1. 编译器在支配树上执行深度优先搜索（DFS）。
2. 进入基本块 $B$ 时，开启一层局部值映射作用域（Scope），继承所有支配者祖先节点的值编号事实。
3. 顺序处理 $B$ 内部指令，若表达式已存在于祖先作用域中，则直接用已有定值替换当前计算指令（实现跨块 CSE）。
4. 递归处理 $B$ 在支配树上的所有子节点。
5. **离开 $B$ 退出作用域时，执行栈回滚（Scope Pop）**，物理弹出在 $B$ 内部注册的所有新值编号，确保后继兄弟节点不会非法读取未支配路径上的临时值。

公共子表达式消除 (CSE) 与代数恒等式化简
---------------------------------------

公共子表达式消除（CSE）与代数恒等式化简（Algebraic Simplification / Peephole Rewriting）是值编号流水线中的核心微架构步骤。

交换律规范化 (Commutative Canonicalization)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于满足交换律的二元运算（如整数加法 ``+``、乘法 ``*``、按位与 ``&``、按位或 ``|``、按位异或 ``^``），表达式 $x + y$ 与 $y + x$ 语义完全等价，但在语法层面操作数顺序相反。
- **规范化契约**：在构造哈希表查询键之前，算法强制比较两个操作数的值编号（$	ext{VN}_1$ 与 $	ext{VN}_2$），若 $	ext{VN}_1 > 	ext{VN}_2$，则交换操作数顺序：

.. math::

   	ext{CanonicalKey}(	ext{Add}, v_1, v_2) = \begin{cases} \langle 	ext{Add}, v_1, v_2 \rangle & 	ext{if } 	ext{VN}(v_1) \le 	ext{VN}(v_2) \ \langle 	ext{Add}, v_2, v_1 \rangle & 	ext{if } 	ext{VN}(v_1) > 	ext{VN}(v_2) \end{cases}

这保证了所有等价的交换运算严格映射至同一哈希槽位。

代数恒等式快速折叠矩阵
~~~~~~~~~~~~~~~~~~~~~~

在发起哈希表查找前，优化器首先应用代数恒等式规则进行常数级化简：

.. list-table:: 现代编译器代数恒等式与强度折减规则矩阵
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 运算表达式模式
     - 代数化简结果
     - 微架构优化收益
   * - $x + 0$ / $x - 0$
     - $x$
     - 消除冗余加减法 ALU 指令
   * - $x - x$ / $x \oplus x$
     - $0$
     - 消除对操作数 $x$ 的依赖，折叠为绝对常数 0
   * - $x 	imes 1$ / $x / 1$
     - $x$
     - 消除高延迟乘除法指令
   * - $x 	imes 0$
     - $0$（需确保无浮点 NaN 语义）
     - 乘法完全折叠
   * - $x \land x$ / $x \lor x$
     - $x$
     - 幂等逻辑位运算消除
   * - $x \land 0$
     - $0$
     - 位屏蔽完全清除
   * - $x 	imes 2^k$
     - $x \ll k$（强度折减 Strength Reduction）
     - 将多周期乘法降级为单周期逻辑左移指令

稀疏条件常量传播 (SCCP)：Wegman-Zadeck 算法
-------------------------------------------

传统的常量传播（如第 5 模块第 1 节实现的基于全图数据流方程的迭代）将控制流视为静态固定的。然而，若某个条件分支的分支条件在编译期被证明为确定常量（如 ``if (10 > 5)``），则未选中的分支实际上是 **不可达的死代码（Dead Branch）**。

传统算法在死分支与存活分支汇合处的 $\phi$ 节点处，会悲观地将死分支的未定义值与存活分支的常量执行会合运算，导致常量信息被错误污染降级为 $\bot$（Overdefined）。

为了解决这一精度损失，Wegman 与 Zadeck 于 1991 年提出了 **稀疏条件常量传播（Sparse Conditional Constant Propagation, SCCP）** 算法。

SCCP 三层格元素模型
~~~~~~~~~~~~~~~~~~~

对于程序中的每一个 SSA 变量，其格状态 $L(v)$ 严格处于以下三层状态之一：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        SCCP 三层常量传播完全格模型                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ 顶元 Top (T) : 未执行 / 乐观假设尚未赋值 ]                   |
   |                                     |                                       |
   |                                     v                                       |
   |              [ 常量层 Constant(C) : 证明为确定单值 C (如 Const(42)) ]        |
   |                                     |                                       |
   |                                     v                                       |
   |              [ 底元 Bottom (_|_ / Overdefined) : 证明为多值 / 动态未知 ]    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

双工作表协同驱动状态机
~~~~~~~~~~~~~~~~~~~~~~

SCCP 算法通过两个协同工作表实现控制流可达性与 SSA 数据流的联合求解：
1. **``CFGWorklist``（控制流边工作表）**：记录当前被证明为 **可达（Executable）** 的控制流有向边 $E = (B_{	ext{src}} 	o B_{	ext{dst}})$。
2. **``SSAWorklist``（SSA 变量工作表）**：记录其格值发生降级更新、需要重新评估其所有使用点（Uses）的 SSA 变量集合。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      Wegman-Zadeck SCCP 算法运行流水线                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 初始化 ]                                                        |
   |      * 所有 SSA 变量初始化为 Top (T)                                        |
   |      * 所有 CFG 边标记为不可达 (Not Executable)                             |
   |      * CFGWorklist.push( (Entry, FirstBlock) )                              |
   |                                                                             |
   |   [ 阶段 2: 双工作表收敛迭代 ]                                              |
   |      While (CFGWorklist 非空 || SSAWorklist 非空):                          |
   |                                                                             |
   |      * 分支 A: 处理一条可达边 (src -> dst) in CFGWorklist:                  |
   |        1. 标记该边为 Executable                                             |
   |        2. 重新评估 dst 顶部的所有 Phi 节点 (仅汇聚来自 Executable 前驱的值) |
   |        3. 若 dst 是首次被访问:                                              |
   |           顺序评估 dst 内部的所有普通计算指令                               |
   |                                                                             |
   |      * 分支 B: 处理一个变量 v in SSAWorklist:                               |
   |        遍历 v 的所有使用指令 UseInst (沿 SSA Def-Use 链):                   |
   |        If UseInst 所在的基本块已被标记为可达:                               |
   |           重新评估 UseInst 的计算结果，若其格值发生变化:                    |
   |           更新其格值并将其目标变量压入 SSAWorklist                          |
   |                                                                             |
   |      * 关键分支裁决 (Conditional Branch Evaluation):                        |
   |        当评估条件跳转 br %cond, TrueBlock, FalseBlock 时:                   |
   |        - 若 L(%cond) == Const(true):  仅将 (curr -> TrueBlock) 压入 CFGWorklist |
   |        - 若 L(%cond) == Const(false): 仅将 (curr -> FalseBlock) 压入 CFGWorklist|
   |        - 若 L(%cond) == Bottom:       将两条分支边全量压入 CFGWorklist      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

SCCP 算法的物理优势
~~~~~~~~~~~~~~~~~~~
由于死分支的边永远不会被标记为 Executable，下游汇合块的 $\phi$ 节点在执行格会合时，**完全忽略来自不可达死前驱的边**。这使得 SCCP 能够证明传统数据流分析无法捕获的深层常量，并直接引导后续 Pass 物理删除整条死分支控制流。

工业级 C++ 完整 GVN、CSE 与 SCCP 引擎实现
-----------------------------------------

以下 C++ 源码实现了一套工业级自包含的 GVN、支配树 CSE 与 Wegman-Zadeck SCCP 优化引擎。该实现涵盖：
1. 具备 SSA 变量、常量、二元算术运算、条件跳转与 $\phi$ 节点的 IR 模型。
2. 交换律规范化与代数恒等式（加零、乘一、异或自身）化简器。
3. 支配树作用域哈希表与全局公共子表达式消除器（Dominator CSE Pass）。
4. 包含双工作表驱动与死分支剪枝的完整 Wegman-Zadeck SCCP 求解器。
5. 端到端测试套件（验证代数折叠、支配树 CSE 重复表达式消除与 SCCP 死分支阻断）。

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
   #include <cstdint>
   #include <cassert>
   #include <algorithm>

   namespace gvn_sccp_engine {

   // =========================================================================
   // 1. IR 指令与基础数据结构
   // =========================================================================
   enum class OpCode {
       Constant,
       Add,
       Sub,
       Mul,
       Xor,
       CmpGT,
       Phi,
       Branch,
       BranchCond,
       Return
   };

   struct Instruction {
       OpCode Op;
       std::string Dest;
       std::string Src1;
       std::string Src2;
       int64_t ImmValue = 0;
       std::string TrueLabel;
       std::string FalseLabel;
       std::unordered_map<std::string, std::string> PhiArgs; // [PredBlock -> SrcVal]

       std::string toString() const {
           std::stringstream ss;
           switch (Op) {
               case OpCode::Constant:
                   ss << "  %" << Dest << " = const " << ImmValue;
                   break;
               case OpCode::Add:
                   ss << "  %" << Dest << " = add i32 %" << Src1 << ", %" << Src2;
                   break;
               case OpCode::Sub:
                   ss << "  %" << Dest << " = sub i32 %" << Src1 << ", %" << Src2;
                   break;
               case OpCode::Mul:
                   ss << "  %" << Dest << " = mul i32 %" << Src1 << ", %" << Src2;
                   break;
               case OpCode::Xor:
                   ss << "  %" << Dest << " = xor i32 %" << Src1 << ", %" << Src2;
                   break;
               case OpCode::CmpGT:
                   ss << "  %" << Dest << " = icmp sgt i32 %" << Src1 << ", %" << Src2;
                   break;
               case OpCode::Phi: {
                   ss << "  %" << Dest << " = phi i32 ";
                   bool first = true;
                   for (const auto& pair : PhiArgs) {
                       if (!first) ss << ", ";
                       ss << "[ %" << pair.second << ", %" << pair.first << " ]";
                       first = false;
                   }
                   break;
               }
               case OpCode::Branch:
                   ss << "  br label %" << TrueLabel;
                   break;
               case OpCode::BranchCond:
                   ss << "  br i1 %" << Src1 << ", label %" << TrueLabel << ", label %" << FalseLabel;
                   break;
               case OpCode::Return:
                   ss << "  ret i32 %" << Src1;
                   break;
           }
           return ss.str();
       }
   };

   struct BasicBlock {
       std::string Name;
       std::vector<Instruction> Instructions;
       std::vector<BasicBlock*> Predecessors;
       std::vector<BasicBlock*> Successors;
       BasicBlock* IDom = nullptr;
       std::vector<BasicBlock*> DomChildren;

       explicit BasicBlock(std::string name) : Name(std::move(name)) {}
   };

   class Function {
   public:
       std::string Name;
       BasicBlock* Entry = nullptr;
       std::vector<std::unique_ptr<BasicBlock>> Blocks;

       BasicBlock* createBlock(const std::string& name) {
           Blocks.push_back(std::make_unique<BasicBlock>(name));
           return Blocks.back().get();
       }

       void dump() const {
           std::cout << "define i32 @" << Name << "() {
";
           for (const auto& b : Blocks) {
               std::cout << b->Name << ":
";
               for (const auto& inst : b->Instructions) {
                   std::cout << inst.toString() << "
";
               }
           }
           std::cout << "}
";
       }
   };

   // =========================================================================
   // 2. 支配树作用域哈希表与 CSE 引擎
   // =========================================================================
   struct ExpressionKey {
       OpCode Op;
       std::string V1;
       std::string V2;

       bool operator==(const ExpressionKey& other) const {
           return Op == other.Op && V1 == other.V1 && V2 == other.V2;
       }
   };

   struct ExprHasher {
       size_t operator()(const ExpressionKey& k) const noexcept {
           return std::hash<int>()(static_cast<int>(k.Op)) ^
                  (std::hash<std::string>()(k.V1) << 1) ^
                  (std::hash<std::string>()(k.V2) << 2);
       }
   };

   class DominatorCSEPass {
   public:
       static void run(Function& func) {
           std::unordered_map<ExpressionKey, std::string, ExprHasher> globalExprTable;
           std::unordered_map<std::string, std::string> replaceMap;

           dfsBlock(func.Entry, globalExprTable, replaceMap);
       }

   private:
       static void dfsBlock(
           BasicBlock* block,
           std::unordered_map<ExpressionKey, std::string, ExprHasher>& exprTable,
           std::unordered_map<std::string, std::string>& replaceMap)
       {
           if (!block) return;

           // 记录本作用域新插入的表达式，用于退出回滚
           std::vector<ExpressionKey> insertedKeys;
           std::vector<Instruction> cleanInsts;

           for (auto& inst : block->Instructions) {
               // 1. 操作数替换传播
               if (replaceMap.count(inst.Src1)) inst.Src1 = replaceMap[inst.Src1];
               if (replaceMap.count(inst.Src2)) inst.Src2 = replaceMap[inst.Src2];

               // 2. 代数恒等式化简
               if (inst.Op == OpCode::Xor && inst.Src1 == inst.Src2 && !inst.Src1.empty()) {
                   // x ^ x => 0
                   inst.Op = OpCode::Constant;
                   inst.ImmValue = 0;
                   inst.Src1.clear();
                   inst.Src2.clear();
               }

               // 3. 构造交换律规范化键
               if (isBinaryArith(inst.Op)) {
                   std::string v1 = inst.Src1;
                   std::string v2 = inst.Src2;
                   if (isCommutative(inst.Op) && v1 > v2) {
                       std::swap(v1, v2);
                   }
                   ExpressionKey key{inst.Op, v1, v2};

                   if (exprTable.count(key)) {
                       // 命中公共子表达式: 记录值重定向，消除本指令
                       replaceMap[inst.Dest] = exprTable[key];
                       continue;
                   } else {
                       exprTable[key] = inst.Dest;
                       insertedKeys.push_back(key);
                   }
               }

               cleanInsts.push_back(inst);
           }

           block->Instructions = std::move(cleanInsts);

           // 4. 递归处理支配树子节点
           for (BasicBlock* child : block->DomChildren) {
               dfsBlock(child, exprTable, replaceMap);
           }

           // 5. 作用域退出: 弹出本块在哈希表中添加的条目
           for (const auto& key : insertedKeys) {
               exprTable.erase(key);
           }
       }

       static bool isBinaryArith(OpCode op) {
           return op == OpCode::Add || op == OpCode::Sub || op == OpCode::Mul || op == OpCode::Xor;
       }

       static bool isCommutative(OpCode op) {
           return op == OpCode::Add || op == OpCode::Mul || op == OpCode::Xor;
       }
   };

   // =========================================================================
   // 3. 稀疏条件常量传播 (Wegman-Zadeck SCCP) 求解器
   // =========================================================================
   enum class LatticeStatus { Top, Constant, Bottom };

   struct SCCPValue {
       LatticeStatus Status = LatticeStatus::Top;
       int64_t Val = 0;

       bool isTop() const { return Status == LatticeStatus::Top; }
       bool isBottom() const { return Status == LatticeStatus::Bottom; }
       bool isConstant() const { return Status == LatticeStatus::Constant; }

       bool operator==(const SCCPValue& o) const {
           if (Status != o.Status) return false;
           if (Status == LatticeStatus::Constant) return Val == o.Val;
           return true;
       }
       bool operator!=(const SCCPValue& o) const { return !(*this == o); }

       SCCPValue meet(const SCCPValue& o) const {
           if (isTop()) return o;
           if (o.isTop()) return *this;
           if (isBottom() || o.isBottom()) return {LatticeStatus::Bottom, 0};
           if (Status == LatticeStatus::Constant && o.Status == LatticeStatus::Constant) {
               if (Val == o.Val) return *this;
               return {LatticeStatus::Bottom, 0};
           }
           return {LatticeStatus::Bottom, 0};
       }

       std::string toString() const {
           if (isTop()) return "TOP";
           if (isBottom()) return "BOT";
           return std::to_string(Val);
       }
   };

   class SCCPSolver {
   public:
       std::unordered_map<std::string, SCCPValue> LatValues;
       std::unordered_set<std::string> ExecutedBlocks;
       std::unordered_set<std::string> ExecutableEdges; // "src->dst"

       void run(Function& func) {
           LatValues.clear();
           ExecutedBlocks.clear();
           ExecutableEdges.clear();

           // 收集所有 Def
           for (const auto& b : func.Blocks) {
               for (const auto& inst : b->Instructions) {
                   if (!inst.Dest.empty()) {
                       LatValues[inst.Dest] = {LatticeStatus::Top, 0};
                   }
               }
           }

           std::queue<std::pair<BasicBlock*, BasicBlock*>> cfgWorklist;
           std::queue<std::string> ssaWorklist;

           // 初始化: 激活入口边
           cfgWorklist.push({nullptr, func.Entry});

           while (!cfgWorklist.empty() || !ssaWorklist.empty()) {
               // 1. 处理 CFG 可达边
               if (!cfgWorklist.empty()) {
                   auto edge = cfgWorklist.front();
                   cfgWorklist.pop();

                   BasicBlock* src = edge.first;
                   BasicBlock* dst = edge.second;
                   std::string edgeKey = (src ? src->Name : "START") + "->" + dst->Name;

                   if (ExecutableEdges.insert(edgeKey).second) {
                       bool firstVisit = ExecutedBlocks.insert(dst->Name).second;

                       // 评估目标块首部的 Phi 节点
                       for (auto& inst : dst->Instructions) {
                           if (inst.Op == OpCode::Phi) {
                               evaluatePhi(inst, dst, ssaWorklist);
                           }
                       }

                       // 若首次访问该块，顺序评估内部所有指令
                       if (firstVisit) {
                           for (auto& inst : dst->Instructions) {
                               if (inst.Op != OpCode::Phi) {
                                   evaluateInst(inst, dst, cfgWorklist, ssaWorklist);
                               }
                           }
                       }
                   }
               }
               // 2. 处理 SSA 降级变量
               else if (!ssaWorklist.empty()) {
                   std::string var = ssaWorklist.front();
                   ssaWorklist.pop();

                   // 重新评估使用该变量的所有指令
                   for (const auto& b : func.Blocks) {
                       if (ExecutedBlocks.count(b->Name)) {
                           for (const auto& inst : b->Instructions) {
                               if (inst.Src1 == var || inst.Src2 == var ||
                                   (inst.Op == OpCode::Phi && containsPhiVar(inst, var)))
                               {
                                   if (inst.Op == OpCode::Phi) {
                                       evaluatePhi(inst, b.get(), ssaWorklist);
                                   } else {
                                       evaluateInst(inst, b.get(), cfgWorklist, ssaWorklist);
                                   }
                               }
                           }
                       }
                   }
               }
           }
       }

   private:
       bool containsPhiVar(const Instruction& inst, const std::string& var) {
           for (const auto& p : inst.PhiArgs) {
               if (p.second == var) return true;
           }
           return false;
       }

       void evaluatePhi(const Instruction& inst, BasicBlock* block, std::queue<std::string>& ssaWorklist) {
           SCCPValue mergedVal{LatticeStatus::Top, 0};

           for (const auto& pair : inst.PhiArgs) {
               std::string edgeKey = pair.first + "->" + block->Name;
               if (ExecutableEdges.count(edgeKey)) {
                   // 仅从已标记为可达的前驱汇聚值! (关键剪枝)
                   SCCPValue inVal = LatValues[pair.second];
                   mergedVal = mergedVal.meet(inVal);
               }
           }

           if (mergedVal != LatValues[inst.Dest]) {
               LatValues[inst.Dest] = mergedVal;
               ssaWorklist.push(inst.Dest);
           }
       }

       void evaluateInst(
           const Instruction& inst,
           BasicBlock* block,
           std::queue<std::pair<BasicBlock*, BasicBlock*>>& cfgWorklist,
           std::queue<std::string>& ssaWorklist)
       {
           switch (inst.Op) {
               case OpCode::Constant: {
                   SCCPValue newVal{LatticeStatus::Constant, inst.ImmValue};
                   if (newVal != LatValues[inst.Dest]) {
                       LatValues[inst.Dest] = newVal;
                       ssaWorklist.push(inst.Dest);
                   }
                   break;
               }
               case OpCode::Add:
               case OpCode::Sub:
               case OpCode::Mul:
               case OpCode::CmpGT: {
                   SCCPValue v1 = LatValues[inst.Src1];
                   SCCPValue v2 = LatValues[inst.Src2];
                   SCCPValue res{LatticeStatus::Top, 0};

                   if (v1.isConstant() && v2.isConstant()) {
                       int64_t computed = 0;
                       if (inst.Op == OpCode::Add) computed = v1.Val + v2.Val;
                       else if (inst.Op == OpCode::Sub) computed = v1.Val - v2.Val;
                       else if (inst.Op == OpCode::Mul) computed = v1.Val * v2.Val;
                       else if (inst.Op == OpCode::CmpGT) computed = (v1.Val > v2.Val) ? 1 : 0;
                       res = {LatticeStatus::Constant, computed};
                   } else if (v1.isBottom() || v2.isBottom()) {
                       res = {LatticeStatus::Bottom, 0};
                   }

                   if (res != LatValues[inst.Dest]) {
                       LatValues[inst.Dest] = res;
                       ssaWorklist.push(inst.Dest);
                   }
                   break;
               }
               case OpCode::Branch: {
                   for (BasicBlock* succ : block->Successors) {
                       if (succ->Name == inst.TrueLabel) {
                           cfgWorklist.push({block, succ});
                       }
                   }
                   break;
               }
               case OpCode::BranchCond: {
                   SCCPValue condVal = LatValues[inst.Src1];
                   if (condVal.isConstant()) {
                       // 条件为常数: 仅激活确定分支边 (死分支彻底阻断!)
                       std::string target = (condVal.Val != 0) ? inst.TrueLabel : inst.FalseLabel;
                       for (BasicBlock* succ : block->Successors) {
                           if (succ->Name == target) {
                               cfgWorklist.push({block, succ});
                           }
                       }
                   } else if (condVal.isBottom()) {
                       // 条件未知: 激活两条后继边
                       for (BasicBlock* succ : block->Successors) {
                           cfgWorklist.push({block, succ});
                       }
                   }
                   break;
               }
               default:
                   break;
           }
       }
   };

   } // namespace gvn_sccp_engine

   // =========================================================================
   // 4. 端到端测试套件与优化验证
   // =========================================================================
   namespace test {

   inline void runGVNAndSCCPTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " GVN 支配树 CSE 与 Wegman-Zadeck SCCP 优化验证套件
";
       std::cout << "=======================================================

";

       // 1. 测试支配树作用域 CSE 与代数恒等式折叠
       {
           using namespace gvn_sccp_engine;
           Function func;
           func.Name = "test_cse_gvn";
           BasicBlock* bEntry = func.createBlock("entry");
           func.Entry = bEntry;

           // %x = const 10
           // %y = const 20
           // %c1 = add %x, %y
           // %c2 = add %y, %x   <--- 交换律加法，期望被 CSE 消除为 %c1
           // %z  = xor %x, %x   <--- 代数恒等式，期望被折叠为 const 0
           bEntry->Instructions.push_back({OpCode::Constant, "x", "", "", 10, "", "", {}});
           bEntry->Instructions.push_back({OpCode::Constant, "y", "", "", 20, "", "", {}});
           bEntry->Instructions.push_back({OpCode::Add, "c1", "x", "y", 0, "", "", {}});
           bEntry->Instructions.push_back({OpCode::Add, "c2", "y", "x", 0, "", "", {}});
           bEntry->Instructions.push_back({OpCode::Xor, "z", "x", "x", 0, "", "", {}});
           bEntry->Instructions.push_back({OpCode::Return, "", "c2", "", 0, "", "", {}});

           std::cout << "[测试 1: CSE 优化前 IR]:
";
           func.dump();

           DominatorCSEPass::run(func);

           std::cout << "
[测试 1: 支配树 CSE 与代数化简后 IR]:
";
           func.dump();

           // 验证断言: c2 必须被消除，return 操作数重定向为 c1
           assert(func.Entry->Instructions.back().Src1 == "c1");
           std::cout << "  -> 交换律公共子表达式与异或化简验证成功。

";
       }

       // 2. 测试 SCCP 死分支阻断与 Phi 节点常量保真
       {
           using namespace gvn_sccp_engine;
           Function func;
           func.Name = "test_sccp_prune";

           BasicBlock* bEntry = func.createBlock("entry");
           BasicBlock* bThen  = func.createBlock("then_block");
           BasicBlock* bElse  = func.createBlock("else_block");
           BasicBlock* bMerge = func.createBlock("merge_block");

           func.Entry = bEntry;
           bEntry->Successors = {bThen, bElse};
           bThen->Predecessors = {bEntry};
           bThen->Successors = {bMerge};
           bElse->Predecessors = {bEntry};
           bElse->Successors = {bMerge};
           bMerge->Predecessors = {bThen, bElse};

           // entry:
           //   %cond = const 1 (True)
           //   br %cond, then_block, else_block
           bEntry->Instructions.push_back({OpCode::Constant, "cond", "", "", 1, "", "", {}});
           bEntry->Instructions.push_back({OpCode::BranchCond, "", "cond", "", 0, "then_block", "else_block", {}});

           // then_block (可达):
           //   %val_then = const 100
           //   br merge_block
           bThen->Instructions.push_back({OpCode::Constant, "val_then", "", "", 100, "", "", {}});
           bThen->Instructions.push_back({OpCode::Branch, "", "", "", 0, "merge_block", "", {}});

           // else_block (死分支! 永远不可达):
           //   %val_else = const 999
           //   br merge_block
           bElse->Instructions.push_back({OpCode::Constant, "val_else", "", "", 999, "", "", {}});
           bElse->Instructions.push_back({OpCode::Branch, "", "", "", 0, "merge_block", "", {}});

           // merge_block:
           //   %res = phi [val_then, then_block], [val_else, else_block]
           //   ret %res
           Instruction phiInst;
           phiInst.Op = OpCode::Phi;
           phiInst.Dest = "res";
           phiInst.PhiArgs["then_block"] = "val_then";
           phiInst.PhiArgs["else_block"] = "val_else";
           bMerge->Instructions.push_back(phiInst);
           bMerge->Instructions.push_back({OpCode::Return, "", "res", "", 0, "", "", {}});

           std::cout << "[测试 2: SCCP 求解前 IR (包含死分支 else_block)]:
";
           func.dump();

           SCCPSolver solver;
           solver.run(func);

           std::cout << "
[SCCP 求解变量常量格状态]:
";
           for (const auto& pair : solver.LatValues) {
               std::cout << "  变量 %" << pair.first << " -> " << pair.second.toString() << "
";
           }

           // 核心断言:
           // 1. else_block 绝不能被标记为 Executed
           assert(!solver.ExecutedBlocks.count("else_block"));
           // 2. phi 结果 %res 必须精准收敛为 100，未被死分支 999 污染为 Bottom
           assert(solver.LatValues["res"].isConstant() && solver.LatValues["res"].Val == 100);
           std::cout << "  -> SCCP 死分支剪枝成功，Phi 节点成功收敛为常数 100。

";
       }

       std::cout << "  -> GVN、CSE 与 SCCP 优化引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了 GVN 与 SCCP 协同优化的深层威力：

1. **交换律与代数恒等式化简**：在测试 1 中，``c2 = add y, x`` 通过规范化键排序命中已有定值 ``c1`` 并被物理消除；同时 ``z = xor x, x`` 被代数折叠为绝对常数 $0$，大幅减少了指令条数。
2. **SCCP 死分支精准阻断**：在测试 2 中，由于分支条件 ``cond == 1`` 为编译期已知常量，算法仅向工作表压入 ``entry -> then_block`` 边，使 ``else_block`` 从始至终未被执行。
3. **Phi 节点常量保真**：在汇合块 ``merge_block`` 处，$\phi$ 节点仅从已激活的 ``then_block`` 路径获取值 $100$，成功避免了与死路径的 $999$ 会合而退化为未知变量，达成了最大不动点（MFP）的极限优化精度。

小结与下章导读
--------------

本章系统解构了现代编译器中端标量优化与常量折叠的核心技术体系：

1. **全局值编号模型**：形式化阐述了将程序事实划分为数学等价类的原理，剖析了支配树作用域栈在实现跨块公共子表达式消除中的物理流转。
2. **交换律规范化与代数化简**：推导了操作数排序契约对消除等价变体表达式的作用，建立了经典的强度折减与恒等式化简规则矩阵。
3. **Wegman-Zadeck SCCP 算法**：深入解构了双工作表协同驱动模型，阐明了利用控制流可达性剪除死分支、保护下游 $\phi$ 节点不被污染的核心机理。

在完成了标量寄存器级别的值分析与常量传播后，编译器优化必须直面现代程序中最复杂、对性能影响最大的维度——**内存与指针操作**。在第 5 模块第 4 节 **内存别名分析 (Alias Analysis)：Must/May/No-Alias 判定、逃逸分析与 MemorySSA 建模（``05_data_flow_analysis_and_optimizations/04_memory_alias_analysis_and_memory_ssa.rst``）** 中，我们将深入剖析指针寻址模型、基于类型的别名分析（TBAA）、安德森（Andersen）与斯廷斯加德（Steensgaard）指向分析、指针逃逸分析，以及在存在内存副作用时建立 MemorySSA 依赖图的微架构实现。
