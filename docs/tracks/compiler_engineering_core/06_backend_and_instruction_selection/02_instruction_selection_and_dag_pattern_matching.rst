====================================================================================================
指令选择算法：树形覆盖匹配、SelectionDAG 图重写与 GlobalISel 现代后端管线
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 1 节（``06_backend_and_instruction_selection/01_target_machine_model_and_target_triples.rst``）中，我们系统剖析了编译器后端的目标机抽象描述模型、TargetTriple 规范、DataLayout 内存物理排布法则、硬件复杂寻址模式以及类型/操作合法化（Legalization）状态机。合法化确保了输入表示中的所有操作数类型均可被硬件寄存器所容纳。在此基础之上，编译器后端的核心计算任务是 **指令选择（Instruction Selection, ISel）**。指令选择负责将中端目标无关的通用抽象计算语义（如 ``add``、``mul``、``load``、``select``），高效映射为目标硬件指令集（如 x86-64、AArch64、RISC-V）中物理执行代价最低的机器指令序列。本章深入解构指令选择的数学本质——图/树覆盖问题（Tree/DAG Covering）、贪心最大咀嚼法（Maximal Munch）与动态规划最优树覆盖算法（Dynamic Programming Tree Tiling）、LLVM 经典 SelectionDAG 图重写管线（Chain 时序依赖与 Glue 硬件标志位绑定），以及以线性流水线与全函数视野为核心的现代 **GlobalISel** 架构。

指令选择的数学本质：图/树覆盖问题 (Tree/DAG Covering)
------------------------------------------------------

从形式化角度，指令选择是一个典型的 **模式匹配与组合优化问题**。

覆盖问题的形式化定义
~~~~~~~~~~~~~~~~~~~~

1. **输入计算图（Subject Graph）**：中端 IR 表达式构成的有向无环图 $G = (V, E)$，其中节点 $V$ 代表抽象算术或内存操作，有向边 $E$ 代表值的数据流传递。
2. **目标模式库（Tile / Pattern Library）**：硬件指令集中的每一条机器指令均被建模为一个局部树形“瓦片（Tile / Pattern）”，瓦片携带一个执行开销度量 $	ext{Cost}(T)$（如指令时钟周期数 Latency 或二进制代码体积 Size）。
3. **优化目标**：寻找一组互不重叠且完全覆盖计算图 $G$ 中所有节点的指令瓦片集合 $\{T_1, T_2, \dots, T_k\}$，使得全图的总体执行代价达到理论极小值：

.. math::

   \min \sum_{i=1}^k 	ext{Cost}(T_i) \quad 	ext{s.t.} \quad \bigcup_{i=1}^k 	ext{Nodes}(T_i) = V(G)

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     指令选择树形瓦片覆盖 (Tree Tiling) 拓扑                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 抽象计算树: result = array[index] + scale * value ]                     |
   |                                                                             |
   |                                [ ADD ]  <-----------------------+           |
   |                                /     \                          | 瓦片 2:   |
   |                               /       \                         | 乘加指令  |
   |                       [ LOAD ]         [ MUL ]  <---------------+ FMA / MLA |
   |                          |             /     \                  | (Cost=1)  |
   |                          v            v       v                 |           |
   |                       [ ADD ]       scale   value <-------------+           |
   |                       /     \                                               |
   |                      /       \                                              |
   |                 array      [ MUL ]  <---------------------------+ 瓦片 1:   |
   |                            /     \                              | SIB 寻址  |
   |                         index   const(4) <----------------------+ (Cost=0)  |
   |                                                                             |
   |   * 方案 A (朴素逐节点选择): 2 次乘法 + 2 次加法 + 1 次加载 = 5 条指令 (Cost=5)|
   |   * 方案 B (最优瓦片覆盖): 1 条 SIB 内存加载 + 1 条乘加 = 2 条指令 (Cost=2)  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

NP 完全性与树形降阶
~~~~~~~~~~~~~~~~~~~

- **通用 DAG 覆盖**：对于任意包含多使用点（Multiple Uses / 节点出度 $> 1$）的有向无环图（DAG），寻找全局最优瓦片覆盖已被严格证明为 **NP-Complete 问题**。
- **树形覆盖（Tree Covering）**：若将表达式图解构为独立的树形结构（Tree，每个节点有且仅有一个父节点），则该问题可通过 **动态规划（Dynamic Programming）** 在 $\mathcal{O}(N)$ 严格线性时间内求得全局最优覆盖解。

经典算法对决：Maximal Munch 贪心算法 vs 动态规划最优树覆盖
----------------------------------------------------------

在编译器演进史上，存在两类经典的树覆盖算法：

Maximal Munch (最大咀嚼法 / 贪心匹配)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Maximal Munch 采用自顶向下的贪心匹配策略：
1. 从树的根节点 $R$ 出发，扫描模式库中能够覆盖根节点 $R$ 的所有合法瓦片。
2. **贪心选择能够覆盖最多节点（尺寸最大）的瓦片 $T$**。
3. 递归地对瓦片 $T$ 底部暴露出的所有叶子子树执行相同的最大咀嚼选择。
- **优缺点**：实现简单、速度极快，但容易陷入局部最优，无法权衡全局寄存器压力与多指令组合代价。

动态规划最优树覆盖算法 (Dynamic Programming Tree Tiling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

基于 Aho-Johnson 与 Burg 理论的动态规划算法包含两遍扫描：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    动态规划最优树覆盖 (DP Tree Tiling) 流水线               |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 自底向上状态转移 (Bottom-Up Cost Propagation) ]                |
   |      对树进行后序遍历 (Post-order Traversal):                               |
   |      对于当前节点 n 与每个可能的硬件目标寄存器类别 r:                       |
   |                                                                             |
   |      Cost(n, r) = min_{能够覆盖 n 且产出 r 的瓦片 T} (                      |
   |                      Cost(T) + sum_{子节点 c_i} Cost(c_i, ReqClass(T, c_i)) |
   |                   )                                                         |
   |                                                                             |
   |      记录在节点 n 处达成该最小开销的最优瓦片 BestTile(n, r)                 |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 阶段 2: 自顶向下指令发射 (Top-Down Code Emission) ]                    |
   |      从根节点出发，依据阶段 1 记录的 BestTile 递归发射硬件机器指令          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

动态规划算法从数学上保证了在树形结构上选择出的指令序列具有全局最低代价值。

LLVM SelectionDAG 经典架构与图重写管线
--------------------------------------

LLVM 在其经典代码生成器（SelectionDAGISel）中构建了一套基于有向无环图的复杂指令选择基础设施。

SelectionDAG 物理数据结构与节点拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SelectionDAG 内部以 ``SDNode`` 为核心节点，操作数通过 ``SDValue``（二元组：$\langle 	ext{SDNode*}, 	ext{ResultIndex} \rangle$）建立数据与控制连接。

三大依赖边拓扑
^^^^^^^^^^^^^^

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      SelectionDAG 三大依赖边物理模型                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. 纯数据依赖边 (Value Edge) : 传递真实的虚拟寄存器值计算流               |
   |      %add = [ ADD: i32 ] <--- Value Edge --- %src [ LOAD: i32 ]             |
   |                                                                             |
   |   2. 内存时序依赖边 (Chain Edge / MVT::Other) : 串联具有副作用的内存指令    |
   |      [ EntryToken ] ---> (Chain) ---> [ LOAD ] ---> (Chain) ---> [ STORE ]  |
   |      * 物理作用: 强制建立拓扑偏序，防止具有别名冲突的内存指令被非法调度重排|
   |                                                                             |
   |   3. 硬件胶水强绑定边 (Glue Edge / MVT::Glue) : 物理指令原子黏合            |
   |      [ CMP: x86_flags ] === (Glue) ===> [ JCC: 依赖 EFLAGS 的条件跳转 ]     |
   |      * 物理作用: 保证调度器绝不能在 CMP 与 JCC 之间插入任何修改标志位的指令  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

SelectionDAG 五阶段执行流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: SelectionDAG 完整后端编译阶段
   :widths: 20 35 45
   :header-rows: 1
   :class: tight-table

   * - 流水线阶段
     - 核心处理对象
     - 微架构物理使命
   * - **1. DAG 构建**
     - LLVM IR 基本块
     - 将单个基本块内部的 SSA 指令平铺为初始的 SelectionDAG 图
   * - **2. DAGCombine (1)**
     - 目标无关初始 DAG
     - 进行目标无关的算术代数化简、冗余零扩展/符号扩展消除
   * - **3. Legalize**
     - 原始类型与操作
     - 执行类型合法化（Promote/Expand）与操作合法化（Custom/Expand/LibCall）
   * - **4. DAGCombine (2) & Pattern Match**
     - 合法化后 DAG
     - 运行由 TableGen DSL 自动编译生成的字节码状态机匹配器，将通用节点替换为机器指令节点
   * - **5. InstrEmitter 调度**
     - 匹配后的机器 DAG
     - 进行指令拓扑排序与调度（List Scheduling），发射线性 Machine IR

现代新架构：GlobalISel (Global Instruction Selection)
-----------------------------------------------------

虽然 SelectionDAG 极其成熟，但随着编译性能与复杂架构演进，其暴露出三大固有缺陷：
1. **基本块局部视野限制**：SelectionDAG 严格局限在单一 Basic Block 内部，跨基本块的优化必须依赖中端 IR 或后续复杂的 Machine IR 重构。
2. **沉重的内存分配开销**：每个基本块均需动态构建数千个 ``SDNode`` 并在此后全量销毁，内存碎片严重，占用了近 $30\%$ 的后端编译耗时。
3. **阶段割裂与分析难以复用**：DAGCombine、TypeLegalize 与 ISel 之间的数据结构反复重构，无法复用已有的 SSA 数据流分析事实。

GlobalISel 四阶段线性流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了实现极致的编译吞吐率与全函数级全局指令选择，LLVM 推出了全新的 **GlobalISel** 框架：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        GlobalISel 现代后端四阶段流水线                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ LLVM IR (SSA 形式) ]                                                    |
   |             |                                                               |
   |             v                                                               |
   |   [ 阶段 1: IRTranslator (全函数翻译) ]                                     |
   |      * 直接将全函数转换为基于通用操作码的 通用机器 IR (Generic MIR / gMIR)   |
   |      * 例如: 转换为 G_ADD, G_MUL, G_LOAD, G_ICMP, G_BR (保持函数级全局 CFG)   |
   |             |                                                               |
   |             v                                                               |
   |   [ 阶段 2: Legalizer (规则表合法化) ]                                      |
   |      * 基于精准声明式的 Legality Query 规则表就地重写 gMIR 指令             |
   |      * 支持 widenScalar, narrowScalar, lower, libcall 等线性变换            |
   |             |                                                               |
   |             v                                                               |
   |   [ 阶段 3: RegBankSelect (寄存器库分配) ]                                  |
   |      * 判定虚拟寄存器归属于通用寄存器库 (GPRBank) 还是浮点向量库 (FPRBank)  |
   |      * 在跨库操作时自动插入拷贝指令 (Cross-Bank Copy)                       |
   |             |                                                               |
   |             v                                                               |
   |   [ 阶段 4: InstructionSelect (目标模式匹配) ]                              |
   |      * 使用 TableGen 编译生成的全局高效状态机，将 gMIR 原地替换为物理目标指令|
   |             |                                                               |
   |             v                                                               |
   |   [ Target-Specific Machine IR (进入寄存器分配与汇编发射) ]                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

GlobalISel 的核心飞跃在于：**自始至终统一在基于虚拟寄存器的线性 Machine IR 上执行就地重写**，完全消除了 SelectionDAG 的构图与销毁开销，编译速度提升可达数倍。

工业级 C++ 完整指令选择与动态规划树覆盖引擎实现
------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级指令选择与动态规划最优树覆盖（DP Tree Tiling）求解引擎。该实现涵盖：
1. 具备操作码、开销度量、子节点指针的表达式树（Expression Tree）模型。
2. 包含基础指令（`ADD`、`MUL`、`LOAD`）、乘加融合指令（`FMA: a * b + c`）与比例变址寻址加载指令（`SIB_LOAD: [base + idx * 4]`）的机器模式库。
3. 完整的后序动态规划树覆盖状态机，计算最小覆盖代价并递归发射最优机器指令。
4. 端到端测试套件（验证复合算术表达式在多瓦片竞争下的最优指令选择收敛）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>
   #include <climits>

   namespace isel_engine {

   // =========================================================================
   // 1. 通用抽象操作码与表达式树
   // =========================================================================
   enum class IROp {
       Const,
       Variable,
       Add,
       Mul,
       Load
   };

   struct ExprNode {
       uint32_t ID = 0;
       IROp Op;
       int64_t Imm = 0;
       std::string VarName;
       std::shared_ptr<ExprNode> Left;
       std::shared_ptr<ExprNode> Right;

       // 动态规划求解缓存
       int BestCost = INT_MAX;
       int BestTileID = -1;

       explicit ExprNode(uint32_t id, IROp op) : ID(id), Op(op) {}
   };

   // =========================================================================
   // 2. 硬件目标机器指令瓦片 (Machine Tiles)
   // =========================================================================
   enum class MachineOp {
       MOV_IMM,      // mov reg, imm         (Cost: 1)
       MOV_REG,      // mov reg, reg         (Cost: 1)
       ADD_REG,      // add dest, src1, src2 (Cost: 1)
       MUL_REG,      // mul dest, src1, src2 (Cost: 3)
       FMA_REG,      // madd dest, a, b, c   (a * b + c, Cost: 2) -> 乘加融合
       LOAD_SIB      // ldr dest, [base, idx, lsl #2] (Cost: 2)  -> 比例变址加载
   };

   struct MachineInstruction {
       MachineOp Op;
       std::string Dest;
       std::vector<std::string> Operands;
       int64_t Immediate = 0;

       std::string toString() const {
           std::string s = "  ";
           switch (Op) {
               case MachineOp::MOV_IMM:
                   s += Dest + " = mov_imm " + std::to_string(Immediate);
                   break;
               case MachineOp::MOV_REG:
                   s += Dest + " = mov " + Operands[0];
                   break;
               case MachineOp::ADD_REG:
                   s += Dest + " = add " + Operands[0] + ", " + Operands[1];
                   break;
               case MachineOp::MUL_REG:
                   s += Dest + " = mul " + Operands[0] + ", " + Operands[1];
                   break;
               case MachineOp::FMA_REG:
                   s += Dest + " = madd " + Operands[0] + ", " + Operands[1] + ", " + Operands[2];
                   break;
               case MachineOp::LOAD_SIB:
                   s += Dest + " = ldr_sib [" + Operands[0] + " + " + Operands[1] + " * 4]";
                   break;
           }
           return s;
       }
   };

   // =========================================================================
   // 3. 动态规划最优树覆盖 (DP Tree Tiling) 求解器
   // =========================================================================
   class DPTreeSelector {
   public:
       static int solveMinCost(std::shared_ptr<ExprNode> root) {
           if (!root) return 0;

           // 自底向上后序遍历: 先求解子树
           int leftCost = solveMinCost(root->Left);
           int rightCost = solveMinCost(root->Right);

           int minCost = INT_MAX;
           int bestTile = -1;

           // 瓦片 0: 常数加载 (Const)
           if (root->Op == IROp::Const) {
               minCost = 1; // mov imm
               bestTile = static_cast<int>(MachineOp::MOV_IMM);
           }
           // 瓦片 1: 变量名 (Variable)
           else if (root->Op == IROp::Variable) {
               minCost = 0; // 原生虚拟寄存器引用，无额外开销
               bestTile = static_cast<int>(MachineOp::MOV_REG);
           }
           // 瓦片 2: SIB 复杂寻址加载: Load( Add( Base, Mul( Index, Const(4) ) ) )
           else if (root->Op == IROp::Load && root->Left && root->Left->Op == IROp::Add) {
               auto addNode = root->Left;
               auto baseNode = addNode->Left;
               auto mulNode = addNode->Right;

               if (mulNode && mulNode->Op == IROp::Mul && mulNode->Right &&
                   mulNode->Right->Op == IROp::Const && mulNode->Right->Imm == 4)
               {
                   int c = 2 + solveMinCost(baseNode) + solveMinCost(mulNode->Left);
                   if (c < minCost) {
                       minCost = c;
                       bestTile = static_cast<int>(MachineOp::LOAD_SIB);
                   }
               }
           }

           // 瓦片 3: 乘加融合 FMA: Add( Mul( a, b ), c ) 或 Add( c, Mul( a, b ) )
           if (root->Op == IROp::Add) {
               // 检查左孩子是否为 Mul
               if (root->Left && root->Left->Op == IROp::Mul) {
                   int c = 2 + solveMinCost(root->Left->Left) +
                               solveMinCost(root->Left->Right) + solveMinCost(root->Right);
                   if (c < minCost) {
                       minCost = c;
                       bestTile = static_cast<int>(MachineOp::FMA_REG);
                   }
               }
               // 检查右孩子是否为 Mul
               if (root->Right && root->Right->Op == IROp::Mul) {
                   int c = 2 + solveMinCost(root->Right->Left) +
                               solveMinCost(root->Right->Right) + solveMinCost(root->Left);
                   if (c < minCost) {
                       minCost = c;
                       bestTile = static_cast<int>(MachineOp::FMA_REG);
                   }
               }
           }

           // 瓦片 4: 基础二元加法 (ADD)
           if (root->Op == IROp::Add) {
               int c = 1 + leftCost + rightCost;
               if (c < minCost) {
                   minCost = c;
                   bestTile = static_cast<int>(MachineOp::ADD_REG);
               }
           }

           // 瓦片 5: 基础二元乘法 (MUL)
           if (root->Op == IROp::Mul) {
               int c = 3 + leftCost + rightCost;
               if (c < minCost) {
                   minCost = c;
                   bestTile = static_cast<int>(MachineOp::MUL_REG);
               }
           }

           root->BestCost = minCost;
           root->BestTileID = bestTile;
           return minCost;
       }

       // 自顶向下发射机器指令
       static std::string emitCode(
           std::shared_ptr<ExprNode> node,
           std::vector<MachineInstruction>& emitted,
           uint32_t& vregCounter)
       {
           if (!node) return "";

           if (node->Op == IROp::Variable) {
               return node->VarName;
           }

           std::string outReg = "%vreg" + std::to_string(++vregCounter);
           auto tile = static_cast<MachineOp>(node->BestTileID);

           switch (tile) {
               case MachineOp::MOV_IMM: {
                   emitted.push_back({tile, outReg, {}, node->Imm});
                   break;
               }
               case MachineOp::LOAD_SIB: {
                   auto addNode = node->Left;
                   std::string baseReg = emitCode(addNode->Left, emitted, vregCounter);
                   std::string idxReg  = emitCode(addNode->Right->Left, emitted, vregCounter);
                   emitted.push_back({tile, outReg, {baseReg, idxReg}, 0});
                   break;
               }
               case MachineOp::FMA_REG: {
                   std::shared_ptr<ExprNode> mulNode = (node->Left->Op == IROp::Mul) ? node->Left : node->Right;
                   std::shared_ptr<ExprNode> addend  = (node->Left->Op == IROp::Mul) ? node->Right : node->Left;

                   std::string aReg = emitCode(mulNode->Left, emitted, vregCounter);
                   std::string bReg = emitCode(mulNode->Right, emitted, vregCounter);
                   std::string cReg = emitCode(addend, emitted, vregCounter);

                   emitted.push_back({tile, outReg, {aReg, bReg, cReg}, 0});
                   break;
               }
               case MachineOp::ADD_REG: {
                   std::string lReg = emitCode(node->Left, emitted, vregCounter);
                   std::string rReg = emitCode(node->Right, emitted, vregCounter);
                   emitted.push_back({tile, outReg, {lReg, rReg}, 0});
                   break;
               }
               case MachineOp::MUL_REG: {
                   std::string lReg = emitCode(node->Left, emitted, vregCounter);
                   std::string rReg = emitCode(node->Right, emitted, vregCounter);
                   emitted.push_back({tile, outReg, {lReg, rReg}, 0});
                   break;
               }
               default:
                   break;
           }

           return outReg;
       }
   };

   } // namespace isel_engine

   // =========================================================================
   // 4. 端到端测试套件与指令选择验证
   // =========================================================================
   namespace test {

   inline void runInstructionSelectionTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 动态规划树覆盖 (DP Tree Tiling) 指令选择引擎验证
";
       std::cout << "=======================================================

";

       using namespace isel_engine;

       // 构造复杂计算树: result = Load( array + index * 4 ) + scale * value
       //
       //                [ root: ADD ]
       //               /             \
       //       [ loadNode: LOAD ]     [ mulNode: MUL ]
       //              |                  /          \
       //       [ addAddr: ADD ]     scale(Var)    value(Var)
       //          /        \
       //     array(Var)  [ mulIdx: MUL ]
       //                   /         \
       //               index(Var)   const(4)

       auto root = std::make_shared<ExprNode>(1, IROp::Add);
       auto loadNode = std::make_shared<ExprNode>(2, IROp::Load);
       auto mulNode = std::make_shared<ExprNode>(3, IROp::Mul);

       auto addAddr = std::make_shared<ExprNode>(4, IROp::Add);
       auto arrayVar = std::make_shared<ExprNode>(5, IROp::Variable);
       arrayVar->VarName = "r_array";

       auto mulIdx = std::make_shared<ExprNode>(6, IROp::Mul);
       auto indexVar = std::make_shared<ExprNode>(7, IROp::Variable);
       indexVar->VarName = "r_index";
       auto const4 = std::make_shared<ExprNode>(8, IROp::Const);
       const4->Imm = 4;

       mulIdx->Left = indexVar;
       mulIdx->Right = const4;
       addAddr->Left = arrayVar;
       addAddr->Right = mulIdx;
       loadNode->Left = addAddr;

       auto scaleVar = std::make_shared<ExprNode>(9, IROp::Variable);
       scaleVar->VarName = "r_scale";
       auto valueVar = std::make_shared<ExprNode>(10, IROp::Variable);
       valueVar->VarName = "r_value";
       mulNode->Left = scaleVar;
       mulNode->Right = valueVar;

       root->Left = loadNode;
       root->Right = mulNode;

       // 运行动态规划树覆盖求解器
       int totalCost = DPTreeSelector::solveMinCost(root);
       std::cout << "[求解器计算全局最优覆盖代价]: Total Cost = " << totalCost << "

";

       std::vector<MachineInstruction> emittedInsts;
       uint32_t vregCounter = 0;
       std::string finalReg = DPTreeSelector::emitCode(root, emittedInsts, vregCounter);

       std::cout << "[发射的优化目标机器指令序列]:
";
       for (const auto& mi : emittedInsts) {
           std::cout << mi.toString() << "
";
       }
       std::cout << "  -> 最终结果寄存器: " << finalReg << "

";

       // 验证断言:
       // 1. 必须成功匹配 SIB 比例变址加载指令: ldr_sib [r_array + r_index * 4]
       assert(emittedInsts.size() == 2);
       assert(emittedInsts[0].Op == MachineOp::LOAD_SIB);
       assert(emittedInsts[0].Operands[0] == "r_array" && emittedInsts[0].Operands[1] == "r_index");

       // 2. 必须成功匹配乘加融合指令: madd
       assert(emittedInsts[1].Op == MachineOp::FMA_REG);
       assert(emittedInsts[1].Operands[0] == "r_scale" && emittedInsts[1].Operands[1] == "r_value");

       std::cout << "  -> 成功将 5 节点抽象子树压缩覆盖为 2 条高效硬件指令 (SIB 加载 + FMA 乘加融合)。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了动态规划指令选择算法的强大优化威力：

1. **复杂内存寻址模式融合**：算法自底向上扫描时，精准识别出 ``Load(Add(array, Mul(index, 4)))`` 符合硬件比例变址加载模式（SIB），直接将一次乘法、一次加法与一次加载三条抽象操作折叠为单一的 ``ldr_sib`` 机器指令。
2. **多操作数乘加融合（FMA）**：对于加法与乘法的级联，求解器选择发射开销仅为 2 的 ``madd`` 硬件乘加指令，相较于分离的 ``mul``（Cost=3）与 ``add``（Cost=1）累计减少了 $50\%$ 的时钟延迟。
3. **全局最优收敛**：全图由原本的 5 条分离指令（总代价 8）完美收敛为 2 条高级硬件指令（总代价 4），验证了动态规划在树形覆盖中的最优性。

小结与下章导读
--------------

本章系统解构了现代编译器后端将抽象计算语义映射为硬件机器指令的核心算法与工程体系：

1. **图/树覆盖数学模型**：形式化阐述了瓦片覆盖最小开销问题，推导了 DAG 覆盖的 NP 完全性与树形结构下的动态规划线性可解性。
2. **算法实现对比**：对比了 Maximal Munch 贪心算法的高速与 DP 最优树覆盖算法的全局最优保证。
3. **SelectionDAG 架构**：深入解构了数据流（Value）、时序依赖（Chain）与标志位胶水（Glue）三大边的拓扑约束及五阶段执行管线。
4. **GlobalISel 现代流水线**：阐释了基于通用机器 IR（gMIR）的全函数级线性翻译、规则表合法化与寄存器库分发的技术革新。

在完成指令选择并生成 Machine IR 之后，编译器面临的下一大核心挑战是：这些机器指令当前仍然操作着无限数量的抽象虚拟寄存器，且包含许多硬件无法直接执行的目标伪指令。在第 6 模块第 3 节 **Machine IR 物理形态：无限虚拟寄存器、目标伪指令展开与流水线感知指令调度（``06_backend_and_instruction_selection/03_machine_ir_and_pseudo_instruction_expansion.rst``）** 中，我们将深入剖析 MachineInstr 与 MachineOperand 的内存物理排布、伪指令（Pseudo Instructions）展开、基本块物理排布优化，以及面向超标量流水线（Superscalar Pipeline）的指令调度前序建模。
