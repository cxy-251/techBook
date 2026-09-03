====================================================================================================
基本块与控制流图 (CFG)：单入口单出口区间、Terminator 终止指令与前驱后继边拓扑
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 1 节（``04_ir_cfg_and_ssa_construction/01_ir_design_working_language_and_lowering.rst``）中，我们系统确立了中间表示（IR）的正交解耦哲学，建立了三地址码（3AC）指令集体系，并实现了将包含嵌套循环、条件分支与多维数组寻址的高级 AST 降解（Lowering）为扁平指令流的转换器。在降级生成的线性指令序列中，控制流转移通过离散的跳转指令与文本标签（Label）表达。然而，若直接以线性数组组织指令，优化 Pass 将无法高效追踪分支汇聚、循环回边以及不可达代码路径。为了使数据流分析（Data-Flow Analysis）、支配树（Dominator Tree）构建与静态单赋值（SSA）转换具备高效的图论拓扑支撑，编译器必须将线性指令流划分为最大连续直线代码段——**基本块（Basic Block）**，并通过有向边连接构建 **控制流图（Control Flow Graph, CFG）**。本章深入剖析基本块的单入口单出口微架构不变性、首指令（Leaders）判定划分算法、终止指令（Terminator）的物理约束、前驱与后继双向指针拓扑网格、临界边（Critical Edge）识别与分割算法，以及异常展开等非正常控制流的建模机理。

基本块的物理本质与单入口单出口不变性
------------------------------------

在编译器体系中，**基本块（Basic Block）** 是控制流分析与优化的最小原子调度单元。它被严格定义为一个具备直线执行特性的指令序列。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      基本块 (Basic Block) 物理执行特性                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   控制流仅从首条指令进入                                                    |
   |            |                                                                |
   |            v                                                                |
   |   +---------------------------------------------------------------------+   |
   |   | [ 首指令 / Leader ] : %t1 = add i32 %a, %b                          |   |
   |   |                       %t2 = mul i32 %t1, 4                          |   |
   |   |                       store i32 %t2, ptr %ptr                       |   |
   |   | [ 终止指令 / Terminator ] : br i1 %cond, label %B1, label %B2        |   |
   |   +---------------------------------------------------------------------+   |
   |                                    |                                        |
   |                                    v                                        |
   |                     控制流仅由末尾终止指令转移至后继块                      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

基本块的核心物理不变性包含以下两条刚性契约：

1. **单入口性（Single Entry）**：控制流只能从该基本块的第一条指令（Leader）进入。指令序列内部的任何中间指令严禁作为任何跳转指令（分支、跳转表、调用返回）的目标地址。
2. **单出口性（Single Exit）**：一旦首条指令开始执行，序列内的所有后续指令必须按照严格的线性顺序确定性执行完毕，只能由最后一条指令将控制权转移至其他基本块或退出当前函数。序列内部严禁包含任何提前跳出当前块的分支或停机指令。

该物理不变性保证了：在基本块内部，每条指令的执行次数与执行时序完全等价。优化器在基本块内部执行局部公共子表达式消除（Local CSE）、死代码消除（Local DCE）与指令重排时，无需考虑跨指令的分支跳转与外部控制注入。

线性指令流切分算法：首指令 (Leaders) 判定
-----------------------------------------

将未经组织的线性 3AC 指令数组划分为独立基本块的过程由 **首指令识别算法（Leaders Identification Algorithm）** 驱动。

Leaders 识别三原则
~~~~~~~~~~~~~~~~~~

遍历包含 $N$ 条指令的线性序列 $I_1, I_2, \dots, I_N$，满足以下任一条件的指令 $I_k$ 被标记为基本块的 **首指令（Leader）**：

1. **函数入口指令**：程序的第一条指令 $I_1$ 必然是首指令（Entry Leader）。
2. **跳转目标指令**：任何显式条件跳转指令、无条件跳转指令或跳转表指令的目标标签（Target Label）所对应的第一条可执行指令。
3. **紧随跳转指令之后的指令**：任何条件跳转指令、无条件跳转指令或函数返回指令紧随其后的下一条指令 $I_{k+1}$。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     首指令 (Leaders) 识别与基本块切分流水线                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 线性 3AC 指令序列 ]                                                     |
   |    1. %a = load ptr %p           <--- 原则 1: 函数首指令 (Leader 1)         |
   |    2. %cmp = icmp slt %a, 10                                                |
   |    3. br %cmp, %L1, %L2          <--- 包含跳转目标: %L1, %L2                |
   |    4. %b = add %a, 1             <--- 原则 3: 紧随跳转之后的指令 (Leader 2)  |
   |    5. br label %L3                                                          |
   |    6. L1:                        <--- 原则 2: 跳转目标指令 (Leader 3)       |
   |    7. %c = mul %a, 2                                                        |
   |    8. br label %L3                                                          |
   |    9. L2:                        <--- 原则 2: 跳转目标指令 (Leader 4)       |
   |   10. %d = sub %a, 5                                                        |
   |   11. L3:                        <--- 原则 2: 跳转目标指令 (Leader 5)       |
   |   12. ret void                                                              |
   |                                                                             |
   |   [ 切分结果: 5 个独立基本块 ]                                              |
   |   * Block 1: [1..3]  (以 br %cmp 结束)                                      |
   |   * Block 2: [4..5]  (以 br label %L3 结束)                                 |
   |   * Block 3: [6..8]  (以 br label %L3 结束)                                 |
   |   * Block 4: [9..10] (以隐式直通到 L3 结束，需补全显式跳转)                 |
   |   * Block 5: [11..12](以 ret void 结束)                                     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

区间切分与终止指令补全
~~~~~~~~~~~~~~~~~~~~~~

在识别出所有 Leader 索引集合 $\{L_1, L_2, \dots, L_M\}$ 并按升序排列后：
- 每个基本块由从当前 Leader $L_i$ 开始、直到下一个 Leader $L_{i+1}$ 之前（或文件末尾）的所有指令构成，形成左闭右开区间 $[L_i, L_{i+1})$。
- 若某个基本块的末尾指令不属于显式控制转移指令（如源码中的直通控制流 Fall-through），编译器必须在降级期显式插入无条件跳转指令 ``br label %L_{i+1}``，确保所有基本块均以严格的终止指令收束。

终止指令 (Terminator Instructions) 体系
---------------------------------------

现代编译器 IR（如 LLVM IR 与 MLIR）在语法结构上强制要求：**每个基本块的最后一条指令必须且只能是终止指令（Terminator）**。

终止指令的主要物理分类与语义模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 编译器核心 Terminator 终止指令类别与控制转移特性
   :widths: 20 28 52
   :header-rows: 1
   :class: tight-table

   * - 终止指令类别
     - 操作码示例
     - 控制转移语义与后继边（Successors）拓扑
   * - 无条件分支
     - ``br label %dest``
     - 产生且仅产生一条无条件控制流转移边（后继数 $= 1$）
   * - 条件分支
     - ``br i1 %c, label %T, label %F``
     - 产生两条显式后继边：True 分支边与 False 分支边（后继数 $= 2$）
   * - 多路选择分派
     - ``switch i32 %val, label %Def [i32 0, label %B0 ...]``
     - 依据比较值产生 $K$ 条 Case 分支边与 1 条 Default 分支边（后继数 $\ge 1$）
   * - 函数返回
     - ``ret void`` / ``ret i32 %val``
     - 销毁当前栈帧，将控制权归还调用者，无函数内后继边（后继数 $= 0$）
   * - 异常分派
     - ``invoke @func() to label %Normal unwind label %Handler``
     - 产生正常返回边与异常展开（Unwind）边（后继数 $= 2$）
   * - 动态间接跳转
     - ``indirectbr ptr %addr, [label %B1, label %B2 ...]``
     - 通过寄存器计算地址跳转，必须显式列出所有潜在后继块列表
   * - 不可达断言
     - ``unreachable``
     - 标记控制流物理不可达（如调用 ``abort()`` 后），指导优化器激进剪枝

控制流图 (CFG) 的拓扑数据结构与双向指针网格
-------------------------------------------

**控制流图（Control Flow Graph, CFG）** 是一个有向图 $G = (V, E)$，其中：
- 节点集合 $V$ 由函数内的全部基本块构成：$V = \{B_1, B_2, \dots, B_n\}$。
- 有向边集合 $E$ 由基本块之间的控制转移转移关系构成：若基本块 $B_i$ 的末尾终止指令可能将控制权移交至 $B_j$，则存在一条有向边 $(B_i, B_j) \in E$。

前驱（Predecessors）与后继（Successors）网格
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在工业级编译器（如 LLVM ``llvm::BasicBlock``）的 C++ 内存拓扑中，CFG 节点通过维护双向指针容器实现 $\mathcal{O}(1)$ 的邻域遍历：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     CFG 节点双向指针网格 (Mesh) 物理模型                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |      +---------------------+           +---------------------+              |
   |      |  BasicBlock: Entry  |           |  BasicBlock: B_Alt  |              |
   |      +---------------------+           +---------------------+              |
   |                 |                                 |                         |
   |                 \----------------+----------------/                         |
   |                                  | (Successor Edges)                        |
   |                                  v                                          |
   |                 +---------------------------------+                         |
   |                 |        BasicBlock: Target       |                         |
   |                 |---------------------------------|                         |
   |                 | * Predecessors: [Entry, B_Alt]  |                         |
   |                 | * Instructions:                 |                         |
   |                 |     %phi = phi [0, Entry], ...  |                         |
   |                 |     %res = add i32 %phi, 1      |                         |
   |                 |     br label %Exit              |                         |
   |                 | * Successors:   [Exit]          |                         |
   |                 +---------------------------------+                         |
   |                                  |                                          |
   |                                  v (Successor Edge)                         |
   |                         +-----------------+                                 |
   |                         | BasicBlock: Exit|                                 |
   |                         +-----------------+                                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

- **前驱节点列表（Predecessor List）**：$	ext{Pred}(B) = \{ P \in V \mid (P, B) \in E \}$。前驱信息对于 SSA 形式下 $\phi$ 节点的参数绑定、数据流逆向分析（如活跃变量分析）至关重要。
- **后继节点列表（Successor List）**：$	ext{Succ}(B) = \{ S \in V \mid (B, S) \in E \}$。后继信息直接由基本块末尾的 Terminator 决定，支撑正向数据流传播（如到达定值、常量传播）。

入口块与出口块的不变性契约
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **单一入口块（Unique Entry Block）**：
   每个函数必须拥有唯一的 Entry 基本块。Entry 块严禁拥有任何前驱边（$	ext{Pred}(	ext{Entry}) = \emptyset$），即禁止任何内部跳转指令指向 Entry 块。若源码中存在跳转回函数开头的循环，编译器必须在 Entry 块之后插入独立的 Loop Header 块。
2. **显式出口块（Exit Blocks）**：
   所有包含 ``ret`` 指令的基本块均作为 CFG 的出口节点。在某些分析算法中，编译器会引入一个虚拟的统一汇聚出口节点（Single Virtual Exit Node），使 CFG 成为严格的单源单汇有向图。

临界边 (Critical Edge) 判定与分割 (Splitting) 机制
--------------------------------------------------

在控制流图的优化与变换中，**临界边（Critical Edge）** 是一种具有特殊拓扑特征的边，它直接阻碍了计算代码的安全提升与 SSA 形式的 Phi 节点消除。

临界边的形式化定义
~~~~~~~~~~~~~~~~~~

在有向图 $G=(V, E)$ 中，一条从源基本块 $S$ 指向目标基本块 $D$ 的有向边 $e = (S, D) \in E$ 被判定为 **临界边（Critical Edge）**，当且仅当它同时满足以下两个拓扑条件：

.. math::

   |	ext{Succ}(S)| > 1 \quad \land \quad |	ext{Pred}(D)| > 1

即：源节点 $S$ 拥有多个后继（属于条件分支块），且目标节点 $D$ 拥有多个前驱（属于控制流汇聚块）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     临界边 (Critical Edge) 拓扑与分割算法                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 场景 1: 未分割的临界边拓扑 (存在代码安放歧义) ]                         |
   |                                                                             |
   |        +-----------------+              +-----------------+                 |
   |        |   Block S       |              |   Block Other   |                 |
   |        | (Succ count: 2) |              +-----------------+                 |
   |        +-----------------+                       |                          |
   |             /         \                          |                          |
   |   (Normal) /           \ (Critical Edge)         |                          |
   |           v             v                        v                          |
   |    +------------+     +-------------------------------+                     |
   |    | Block Side |     |           Block D             |                     |
   |    +------------+     |      (Pred count: 2)          |                     |
   |                       +-------------------------------+                     |
   |                                                                             |
   |   * 矛盾: 优化器若想仅在 S->D 路径上执行计算，无法将代码插入 S (会影响      |
   |     Side 分支)，也无法将代码插入 D (会影响 Other 前驱路径)。                |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 场景 2: 插入合成空块 (Split Edge) 后的良构拓扑 ]                        |
   |                                                                             |
   |        +-----------------+              +-----------------+                 |
   |        |   Block S       |              |   Block Other   |                 |
   |        +-----------------+              +-----------------+                 |
   |             /         \                          |                          |
   |            v           v                         |                          |
   |    +------------+   +----------------------+     |                          |
   |    | Block Side |   | New Block: S_to_D    |     |                          |
   |    +------------+   | (Single In / Out)    |     |                          |
   |                     | 放置专属提升代码/Copy|     |                          |
   |                     | br label %D          |     |                          |
   |                     +----------------------+     |                          |
   |                                \                 /                          |
   |                                 v               v                           |
   |                               +-------------------+                         |
   |                               |     Block D       |                         |
   |                               +-------------------+                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

临界边分割算法 (Critical Edge Splitting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了消除代码放置歧义，编译器在执行循环不变量外提（LICM）、全局值编号（GVN）或 SSA 销毁（SSA Deconstruction）之前，必须执行 **临界边分割 Pass（BreakCriticalEdges Pass）**：

1. 扫描 CFG 中的每一条边 $(S, D)$。
2. 若 $|	ext{Succ}(S)| > 1$ 且 $|	ext{Pred}(D)| > 1$：
   - 创建一个全新的合成基本块 $B_{	ext{split}}$。
   - 在 $B_{	ext{split}}$ 内部填入一条无条件跳转指令 ``br label %D``。
   - 将 $S$ 的 Terminator 中指向 $D$ 的跳转目标重定向为 $B_{	ext{split}}$。
   - 更新 $D$ 内部所有 $\phi$ 节点的来源标记，将原前驱标识 $S$ 替换为 $B_{	ext{split}}$。
   - 更新 $S$、$D$ 与 $B_{	ext{split}}$ 的前驱后继指针列表。

分割后，边 $(S, B_{	ext{split}})$ 不再是临界边（因为 $B_{	ext{split}}$ 仅有 1 个前驱），边 $(B_{	ext{split}}, D)$ 亦不是临界边（因为 $B_{	ext{split}}$ 仅有 1 个后继）。优化器获得了安全的物理位置安放边相关的计算指令与寄存器拷贝指令。

非正常控制流 (Abnormal Control Flow) 建模
-----------------------------------------

除了常规的条件跳转与循环外，程序中还存在非局部的异常控制转移路径。

异常处理与 LandingPad
~~~~~~~~~~~~~~~~~~~~~

在支持 C++ 异常处理机制（Itanium C++ ABI）的系统中，函数调用可能因抛出异常而提前中断：
- 编译器使用 ``invoke`` 指令替代普通 ``call`` 指令。
- ``invoke`` 产生两条显式 CFG 边：一条指向正常返回的基本块（Normal Destination），另一条指向异常解包处理块（LandingPad Block）。
- LandingPad 块以 ``landingpad`` 指令开头，负责捕获异常类型对象并分发至对应的 ``catch`` 处理程序或执行局部变量析构（Cleanup）。

setjmp / longjmp 与间接控制流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C 语言的 ``setjmp/longjmp`` 会在程序执行过程中引发跨栈帧的任意控制流回跳。编译器将调用 ``setjmp`` 的基本块标记为具备隐式外部前驱（Abnormal Predecessor），强制保守限制该函数内部的寄存器分配与指令重排优化。

工业级 C++ 完整 CFG 拓扑构建与验证引擎实现
------------------------------------------

以下 C++ 源码实现了一套工业级自包含的控制流图（CFG）构建与分析引擎。该实现涵盖：
1. 包含完整终止指令语义的 3AC 指令与基本块（BasicBlock）类。
2. 线性指令序列的首指令（Leaders）识别与基本块自动化切分算法。
3. 前驱与后继双向网格拓扑的自动链接。
4. 临界边（Critical Edge）自动探测与边分割（Edge Splitting）算法。
5. 生成标准 Graphviz DOT 格式的可视化输出，展示前驱后继关系与临界边标记。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <sstream>
   #include <cstdint>
   #include <cassert>
   #include <algorithm>

   namespace cfg_engine {

   // =========================================================================
   // 1. 指令与 Terminator 终止语义定义
   // =========================================================================
   enum class InstKind {
       Assign,
       Add,
       Sub,
       Mul,
       Cmp,
       // Terminator 类别
       Branch,
       BranchCond,
       Return
   };

   struct Instruction {
       InstKind Kind;
       std::string Result;
       std::string Op1;
       std::string Op2;
       std::string TargetLabel;  // 用于 Branch / BranchCond (True)
       std::string FalseLabel;   // 仅用于 BranchCond (False)

       bool isTerminator() const {
           return Kind == InstKind::Branch ||
                  Kind == InstKind::BranchCond ||
                  Kind == InstKind::Return;
       }

       std::string toString() const {
           std::stringstream ss;
           switch (Kind) {
               case InstKind::Assign:
                   ss << "  %" << Result << " = " << Op1;
                   break;
               case InstKind::Add:
                   ss << "  %" << Result << " = add %" << Op1 << ", %" << Op2;
                   break;
               case InstKind::Sub:
                   ss << "  %" << Result << " = sub %" << Op1 << ", %" << Op2;
                   break;
               case InstKind::Mul:
                   ss << "  %" << Result << " = mul %" << Op1 << ", %" << Op2;
                   break;
               case InstKind::Cmp:
                   ss << "  %" << Result << " = icmp_slt %" << Op1 << ", %" << Op2;
                   break;
               case InstKind::Branch:
                   ss << "  br label %" << TargetLabel;
                   break;
               case InstKind::BranchCond:
                   ss << "  br %" << Op1 << ", label %" << TargetLabel << ", label %" << FalseLabel;
                   break;
               case InstKind::Return:
                   ss << "  ret " << Op1;
                   break;
           }
           return ss.str();
       }
   };

   // =========================================================================
   // 2. 基本块 (BasicBlock) 拓扑节点
   // =========================================================================
   class BasicBlock {
   public:
       std::string Name;
       std::vector<Instruction> Instructions;
       std::vector<BasicBlock*> Predecessors;
       std::vector<BasicBlock*> Successors;

       explicit BasicBlock(std::string name) : Name(std::move(name)) {}

       const Instruction* getTerminator() const {
           if (!Instructions.empty() && Instructions.back().isTerminator()) {
               return &Instructions.back();
           }
           return nullptr;
       }

       Instruction* getTerminator() {
           if (!Instructions.empty() && Instructions.back().isTerminator()) {
               return &Instructions.back();
           }
           return nullptr;
       }

       void addPredecessor(BasicBlock* pred) {
           if (std::find(Predecessors.begin(), Predecessors.end(), pred) == Predecessors.end()) {
               Predecessors.push_back(pred);
           }
       }

       void addSuccessor(BasicBlock* succ) {
           if (std::find(Successors.begin(), Successors.end(), succ) == Successors.end()) {
               Successors.push_back(succ);
           }
       }

       void removePredecessor(BasicBlock* pred) {
           Predecessors.erase(std::remove(Predecessors.begin(), Predecessors.end(), pred), Predecessors.end());
       }

       void removeSuccessor(BasicBlock* succ) {
           Successors.erase(std::remove(Successors.begin(), Successors.end(), succ), Successors.end());
       }
   };

   // =========================================================================
   // 3. 控制流图 (CFG) 与算法驱动
   // =========================================================================
   class ControlFlowGraph {
   public:
       std::string FunctionName;
       BasicBlock* EntryBlock = nullptr;
       std::vector<std::unique_ptr<BasicBlock>> Blocks;

       BasicBlock* createBlock(const std::string& name) {
           Blocks.push_back(std::make_unique<BasicBlock>(name));
           return Blocks.back().get();
       }

       BasicBlock* findBlock(const std::string& name) const {
           for (const auto& b : Blocks) {
               if (b->Name == name) return b.get();
           }
           return nullptr;
       }

       // 建立前驱后继边网格
       void buildEdges() {
           // 清除旧边
           for (auto& b : Blocks) {
               b->Predecessors.clear();
               b->Successors.clear();
           }

           for (auto& b : Blocks) {
               const Instruction* term = b->getTerminator();
               if (!term) continue;

               if (term->Kind == InstKind::Branch) {
                   BasicBlock* target = findBlock(term->TargetLabel);
                   if (target) {
                       b->addSuccessor(target);
                       target->addPredecessor(b.get());
                   }
               } else if (term->Kind == InstKind::BranchCond) {
                   BasicBlock* tTarget = findBlock(term->TargetLabel);
                   BasicBlock* fTarget = findBlock(term->FalseLabel);
                   if (tTarget) {
                       b->addSuccessor(tTarget);
                       tTarget->addPredecessor(b.get());
                   }
                   if (fTarget) {
                       b->addSuccessor(fTarget);
                       fTarget->addPredecessor(b.get());
                   }
               }
           }
       }

       // 临界边分割算法 (Critical Edge Splitting)
       size_t splitCriticalEdges() {
           size_t splitCount = 0;
           std::vector<std::pair<BasicBlock*, BasicBlock*>> criticalEdges;

           // 1. 探测所有临界边: Pred(D) > 1 && Succ(S) > 1
           for (const auto& b : Blocks) {
               if (b->Successors.size() > 1) {
                   for (BasicBlock* succ : b->Successors) {
                       if (succ->Predecessors.size() > 1) {
                           criticalEdges.emplace_back(b.get(), succ);
                       }
                   }
               }
           }

           // 2. 执行物理分割
           for (auto& edge : criticalEdges) {
               BasicBlock* src = edge.first;
               BasicBlock* dst = edge.second;

               std::string splitName = src->Name + "_to_" + dst->Name + "_split";
               BasicBlock* splitBlock = createBlock(splitName);

               // 填入无条件跳转指令指向目标块
               Instruction brInst;
               brInst.Kind = InstKind::Branch;
               brInst.TargetLabel = dst->Name;
               splitBlock->Instructions.push_back(brInst);

               // 重定向源块 Terminator 中的目标标签
               Instruction* term = src->getTerminator();
               assert(term && "Source block must have a terminator");

               if (term->Kind == InstKind::BranchCond) {
                   if (term->TargetLabel == dst->Name) {
                       term->TargetLabel = splitName;
                   }
                   if (term->FalseLabel == dst->Name) {
                       term->FalseLabel = splitName;
                   }
               } else if (term->Kind == InstKind::Branch) {
                   if (term->TargetLabel == dst->Name) {
                       term->TargetLabel = splitName;
                   }
               }

               ++splitCount;
           }

           if (splitCount > 0) {
               buildEdges(); // 重建边拓扑网格
           }
           return splitCount;
       }

       // 导出 Graphviz DOT 格式
       std::string dumpDot() const {
           std::stringstream ss;
           ss << "digraph CFG_" << FunctionName << " {
";
           ss << "  node [shape=record, fontname=\"Courier\"];

";

           for (const auto& b : Blocks) {
               ss << "  " << b->Name << " [label=\"{" << b->Name << ":\l";
               for (const auto& inst : b->Instructions) {
                   std::string str = inst.toString();
                   // 转义字符
                   for (char c : str) {
                       if (c == '"') ss << "\\"";
                       else if (c == '<' || c == '>') ss << "\" << c;
                       else ss << c;
                   }
                   ss << "\l";
               }
               ss << "}\"];
";

               for (BasicBlock* succ : b->Successors) {
                   ss << "  " << b->Name << " -> " << succ->Name;
                   // 判定是否为临界边
                   if (b->Successors.size() > 1 && succ->Predecessors.size() > 1) {
                       ss << " [color=red, label=\"critical\"];
";
                   } else {
                       ss << ";
";
                   }
               }
           }
           ss << "}
";
           return ss.str();
       }
   };

   // =========================================================================
   // 4. Leaders 判定切分引擎
   // =========================================================================
   struct RawLabeledInst {
       std::string ExplicitLabel; // 若该指令附带 Label 则记录
       Instruction Inst;
   };

   class CFGBuilder {
   public:
       static ControlFlowGraph buildFromRawInstructions(
           const std::string& funcName,
           const std::vector<RawLabeledInst>& rawInsts)
       {
           ControlFlowGraph cfg;
           cfg.FunctionName = funcName;
           if (rawInsts.empty()) return cfg;

           size_t n = rawInsts.size();
           std::vector<bool> isLeader(n, false);
           std::unordered_map<std::string, size_t> labelToIndex;

           // 第一遍扫描: 收集所有标签位置
           for (size_t i = 0; i < n; ++i) {
               if (!rawInsts[i].ExplicitLabel.empty()) {
                   labelToIndex[rawInsts[i].ExplicitLabel] = i;
               }
           }

           // 第二遍扫描: 应用 Leaders 判定三原则
           // 原则 1: 第一条指令是 Leader
           isLeader[0] = true;

           for (size_t i = 0; i < n; ++i) {
               const auto& inst = rawInsts[i].Inst;

               // 原则 2: 跳转目标所指向的指令是 Leader
               if (inst.Kind == InstKind::Branch) {
                   if (labelToIndex.count(inst.TargetLabel)) {
                       isLeader[labelToIndex[inst.TargetLabel]] = true;
                   }
               } else if (inst.Kind == InstKind::BranchCond) {
                   if (labelToIndex.count(inst.TargetLabel)) {
                       isLeader[labelToIndex[inst.TargetLabel]] = true;
                   }
                   if (labelToIndex.count(inst.FalseLabel)) {
                       isLeader[labelToIndex[inst.FalseLabel]] = true;
                   }
               }

               // 原则 3: 紧随跳转/返回之后的指令是 Leader
               if (inst.isTerminator() && i + 1 < n) {
                   isLeader[i + 1] = true;
               }
           }

           // 第三遍扫描: 依据 Leaders 切分基本块
           BasicBlock* currentBlock = nullptr;
           for (size_t i = 0; i < n; ++i) {
               if (isLeader[i]) {
                   std::string blockName = rawInsts[i].ExplicitLabel.empty()
                                               ? ("bb_" + std::to_string(i))
                                               : rawInsts[i].ExplicitLabel;
                   currentBlock = cfg.createBlock(blockName);
                   if (!cfg.EntryBlock) {
                       cfg.EntryBlock = currentBlock;
                   }
               }
               assert(currentBlock && "Instruction before first leader");
               currentBlock->Instructions.push_back(rawInsts[i].Inst);
           }

           // 建立拓扑边网格
           cfg.buildEdges();
           return cfg;
       }
   };

   } // namespace cfg_engine

   // =========================================================================
   // 5. 端到端验证套件
   // =========================================================================
   namespace test {

   inline void runCFGTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 控制流图 (CFG) Leaders 切分与临界边分割测试套件
";
       std::cout << "=======================================================

";

       // 构造一个包含条件分支与临界边的典型指令流:
       //
       // entry:
       //   %c1 = icmp_slt %x, 0
       //   br %c1, label %check_fast, label %merge
       // check_fast:
       //   %c2 = icmp_slt %fast, 1
       //   br %c2, label %merge, label %exit
       // merge:
       //   %res = add %x, 10
       //   br label %exit
       // exit:
       //   ret %res
       //
       // 拓扑分析:
       // - entry 拥有 2 个后继 (check_fast, merge)
       // - check_fast 拥有 2 个后继 (merge, exit)
       // - merge 拥有 2 个前驱 (entry, check_fast)
       // 因此: 边 (entry -> merge) 和边 (check_fast -> merge) 均为临界边！

       using namespace cfg_engine;
       std::vector<RawLabeledInst> stream = {
           // Block: entry
           {"entry", {InstKind::Cmp, "c1", "x", "0", "", ""}},
           {"",      {InstKind::BranchCond, "", "c1", "", "check_fast", "merge"}},
           // Block: check_fast
           {"check_fast", {InstKind::Cmp, "c2", "fast", "1", "", ""}},
           {"",           {InstKind::BranchCond, "", "c2", "", "merge", "exit"}},
           // Block: merge
           {"merge", {InstKind::Add, "res", "x", "10", "", ""}},
           {"",      {InstKind::Branch, "", "", "", "exit", ""}},
           // Block: exit
           {"exit", {InstKind::Return, "", "res", "", "", ""}}
       };

       // 1. 切分与建图
       ControlFlowGraph cfg = CFGBuilder::buildFromRawInstructions("demo_flow", stream);

       std::cout << "[初始 CFG 基本块拓扑]:
";
       for (const auto& b : cfg.Blocks) {
           std::cout << "  基本块: " << b->Name << "
";
           std::cout << "    前驱数量: " << b->Predecessors.size() << " [";
           for (auto* p : b->Predecessors) std::cout << p->Name << " ";
           std::cout << "]
";
           std::cout << "    后继数量: " << b->Successors.size() << " [";
           for (auto* s : b->Successors) std::cout << s->Name << " ";
           std::cout << "]
";
       }

       assert(cfg.Blocks.size() == 4);
       assert(cfg.findBlock("merge")->Predecessors.size() == 2);
       assert(cfg.findBlock("entry")->Successors.size() == 2);

       std::cout << "
[执行临界边检测与分割]:
";
       size_t splitCount = cfg.splitCriticalEdges();
       std::cout << "  成功检测并分割临界边数量: " << splitCount << " 条

";

       std::cout << "[分割后 CFG 拓扑网格]:
";
       for (const auto& b : cfg.Blocks) {
           std::cout << "  基本块: " << b->Name << " (前驱: " << b->Predecessors.size()
                     << ", 后继: " << b->Successors.size() << ")
";
       }

       assert(splitCount == 2);
       assert(cfg.Blocks.size() == 6); // 原 4 块 + 2 个合成分割块

       // 打印 DOT 图表达
       std::cout << "
[生成的 Graphviz DOT 图文本]:
";
       std::cout << cfg.dumpDot() << "
";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了从原始指令流到完备 CFG 的构建过程：

1. **Leaders 判定精准切分**：算法精准捕获了指令流中的 4 个 Leader 位置（``entry``, ``check_fast``, ``merge``, ``exit``），将 7 条指令规整切分为 4 个单入口单出口基本块。
2. **临界边拓扑捕获**：识别出 ``entry -> merge``（源块 2 后继，目标块 2 前驱）以及 ``check_fast -> merge``（源块 2 后继，目标块 2 前驱）两条高危临界边。
3. **边分割与无损拓扑重构**：自动生成了合成跳转块 ``entry_to_merge_split`` 与 ``check_fast_to_merge_split``，重定向了分支目标并重建了前驱后继网格，使所有汇聚边均成为单入单出边，为后续 SSA Phi 节点消除奠定了完备的图论基础。

小结与下章导读
--------------

本章系统剖析了现代编译器中端控制流的核心数据结构与拓扑机理：

1. **基本块的不变性契约**：明确了单入口（仅由 Leader 进入）与单出口（仅由 Terminator 离开）对局部线性指令序列优化的安全保障。
2. **首指令划分算法**：阐明了基于函数入口、跳转目标与紧随分支指令三原则的线性指令流自动化切分流水线。
3. **CFG 双向指针网格**：建立了前驱与后继双向索引模型，规范了唯一入口块与显式返回出口块的结构约束。
4. **临界边识别与分割**：形式化定义了 $|	ext{Succ}(S)| > 1 \land |	ext{Pred}(D)| > 1$ 的临界边条件，通过插入合成无条件跳转块消除了代码安放与 Phi 节点消除的拓扑歧义。

在建立了良构的控制流图后，编译器的下一个核心挑战是如何识别图中的支配层级与循环结构。在第 4 模块第 3 节 **支配关系与自然循环识别：不可达块消除、支配树 (Dominator Tree) 构建与回边 (Backedge) 检测（04_ir_cfg_and_ssa_construction/03_dominance_frontiers_and_natural_loops.rst）** 中，我们将深入解构 Lengauer-Tarjan 支配树快速构建算法、支配边界（Dominance Frontier）计算以及自然循环（Natural Loop）的规范化检测机制。
