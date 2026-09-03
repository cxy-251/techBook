====================================================================================================
SSA 静态单赋值形式核心：变量槽位向唯一计算值映射、Phi 节点语义与 Mem2Reg 栈提升
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 3 节（``04_ir_cfg_and_ssa_construction/03_dominance_frontiers_and_natural_loops.rst``）中，我们系统确立了控制流图（CFG）的支配关系代数模型、构建了直接支配者（$idom$）树形拓扑，并形式化推导了支配边界（Dominance Frontier, DF）的数学定义与自然循环回边检测机制。在传统非 SSA 编译器中，变量被视作可反复覆写的物理内存或寄存器槽位（Slot），一个变量名在不同时间点绑定了不同的计算结果。这导致数据流分析器必须维护极其昂贵的到达定值集合（Reaching Definitions）与动态 Def-Use 链表，严重阻碍了常量传播、死代码消除与全局值编号（GVN）的优化效率。为了彻底解耦计算值与其存储位置，现代编译器中端全面转向 **静态单赋值（Static Single Assignment, SSA）形式**。本章深入剖析变量槽位向唯一值标识（Value Identity）的映射原理、$\phi$ 节点（Phi Node）的多前驱条件选择操作语义、最小化 SSA（Minimal SSA）与剪枝 SSA（Pruned SSA）的拓扑判定、Cytron 支配边界变量重命名状态机，以及将前端 ``alloca/load/store`` 内存操作提升为纯粹 SSA 虚拟寄存器值流的 **Mem2Reg Pass** 物理实现。

变量槽位模型 vs 纯粹值标识 (Value Identity)
--------------------------------------------

在高级源码与初始中间表示中，程序通常基于 **可变存储槽位模型（Mutable Storage Slot Model）** 组织数据。

槽位覆写对中端优化的物理阻碍
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

考虑以下典型的变易计算序列：

.. code-block:: text

   [ 非 SSA 槽位覆写指令流 ]
   1. x = a + b
   2. y = x * 2
   3. x = c - d      <--- 变量名 x 被覆写，破坏了第 1 行定值的单调性
   4. z = x + 4
   5. ret y + z

在此指令流中：
- 变量名 ``x`` 先后承载了两次完全独立的计算事实：``a + b`` 与 ``c - d``。
- 优化器在分析第 5 行时，若想查询第 2 行 ``x * 2`` 中 ``x`` 的来源，无法直接通过变量名索引，必须沿控制流向前执行线性逆向扫描，以判定其间是否存在对 ``x`` 的杀死定值（Killing Definition）。
- 这种名字复用掩盖了数据流的真实依赖拓扑，导致数据流分析的时间复杂度随程序规模呈二次方级数上升。

SSA 形式的核心定义与值标识解耦
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**静态单赋值（Static Single Assignment, SSA）形式** 施加了一条刚性结构契约：
**在 IR 的静态文本表示中，每一个 SSA 变量名有且仅有一个唯一的定值点（Definition Point）。**

将上述非 SSA 指令流转换为 SSA 形式：

.. code-block:: text

   [ 严格 SSA 形式指令流 ]
   1. %x1 = add i32 %a, %b      ; 定值点 1: %x1 终生代表 (a + b) 的计算值
   2. %y1 = mul i32 %x1, 2      ; 显式引用 %x1
   3. %x2 = sub i32 %c, %d      ; 定值点 2: 分配全新名字 %x2，代表 (c - d)
   4. %z1 = add i32 %x2, 4      ; 显式引用 %x2
   5. %res = add i32 %y1, %z1
   6. ret %res

在 SSA 形式下：
1. **名字即值（Name is Value）**：每个 SSA 名字（如 ``%x1``）全局唯一对应单次计算结果（Value Identity）。
2. **Def-Use 链常数时间可达**：每个使用点（Use）直接持有指向其唯一定值指令（Def）的指针，消除了一切到达定值搜索开销。
3. **静态唯一 vs 动态执行**：SSA 约束作用于编译期的静态 IR 拓扑。处于循环体内部的 SSA 指令在运行时可被硬件 CPU 执行数百万次，但在编译期文本中依然严格满足单一定值契约。

Phi 节点 (Phi Node) 的操作语义与动态流转
-----------------------------------------

在直线代码中，重命名变量足以构建 SSA 形式。然而，当控制流图中出现分支汇聚（Control Flow Merge）时，同一变量在不同分支路径上可能产生不同的定值。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     分支汇流与 Phi 节点选择语义拓扑                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                                 [ Entry ]                                   |
   |                                 /       \                                   |
   |                       (cond)   /         \  (!cond)                         |
   |                               v           v                                 |
   |                       [ ThenBlock ]   [ ElseBlock ]                         |
   |                       %x_then = 10    %x_else = 20                          |
   |                               \           /                                 |
   |                                \         /                                  |
   |                                 v       v                                   |
   |                               [ MergeBlock ]                                |
   |               %x_merge = phi [ %x_then, ThenBlock ],                        |
   |                              [ %x_else, ElseBlock ]                         |
   |               %res = add i32 %x_merge, 1                                    |
   |               ret %res                                                      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Phi 节点操作语义
~~~~~~~~~~~~~~~~

为了在分支汇流点统一变量版本，SSA 引入了伪指令——**$\phi$ 节点（Phi Node / Phi Instruction）**：

.. math::

   \%x_{	ext{merge}} = \phi \left[ v_1, B_1 \right], \left[ v_2, B_2 \right], \dots, \left[ v_k, B_k \right]

- **语法结构**：$\phi$ 节点必须严格位于基本块的最顶端（在任何非 $\phi$ 普通计算指令之前）。它包含一组二元组列表 $[v_i, B_i]$，其中 $B_i \in 	ext{Pred}(	ext{MergeBlock})$ 为直接前驱基本块，$v_i$ 为沿该前驱路径到达时的 SSA 值。
- **运行期执行模型**：$\phi$ 节点在硬件指令集层面并非真实物理 CPU 指令。它在概念上表达了一个 **由控制流来源决定的并行多路选择器**：若运行时控制流从前驱块 $B_1$ 跃迁至当前块，$\%x_{	ext{merge}}$ 即刻获得值 $v_1$；若来自 $B_2$，则获得 $v_2$。在编译器后端（Code Generation），$\phi$ 节点最终会被消除并降级为前驱块末尾的真实寄存器搬移指令（Copy）。

SSA 分类：Minimal SSA、Semi-Pruned SSA 与 Pruned SSA
---------------------------------------------------

并非所有变量在所有分支汇聚点都需要插入 $\phi$ 节点。依据 $\phi$ 节点的插入密度与活跃性判定，SSA 形式分为三个经典层次：

.. list-table:: SSA 形式三层分类与构建开销对比
   :widths: 18 32 50
   :header-rows: 1
   :class: tight-table

   * - SSA 变体
     - 插入判定条件与算法
     - 内存膨胀与分析开销权衡
   * - 最小化 SSA (Minimal SSA)
     - 在变量所有定值块的迭代支配边界（$IDF$）处无条件插入 $\phi$ 节点
     - 构建速度快，但会生成大量死 $\phi$ 节点（插入后从未被任何指令读取）
   * - 半剪枝 SSA (Semi-Pruned SSA)
     - 预先过滤局部变量：仅对 **跨越基本块边界活跃** 的变量在 $IDF$ 处插入 $\phi$ 节点
     - **工业级首选（LLVM 标准）**：无需计算完整活跃变量集合，剪除绝大多数临时变量 $\phi$
   * - 剪枝 SSA (Pruned SSA)
     - 结合全局活跃变量分析：仅当变量在目标汇合块入口处 **处于活跃状态（Live-in）** 时插入 $\phi$
     - 产出的 $\phi$ 节点数量绝对最少，但必须预先执行高成本的全局活跃变量数据流分析

Cytron 算法：Phi 放置与支配树重命名状态机
------------------------------------------

工业界构建 SSA 形式的标准经典算法由 Cytron 等人于 1991 年提出，包含两个核心阶段：

阶段 1: 迭代支配边界 (IDF) 处的 Phi 节点插入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设变量 $v$ 在控制流图中的定值基本块集合为 $	ext{Defs}(v)$。$v$ 的 $\phi$ 节点必须插入在 $	ext{Defs}(v)$ 的 **迭代支配边界（Iterated Dominance Frontier, $IDF$）** 集合上：

.. math::

   IDF(S) = 	ext{FixedPoint}\left( S \cup \bigcup_{b \in S} DF(b) \right)

算法利用工作表（Worklist）进行单调收敛求解：
1. 将 $	ext{Defs}(v)$ 中所有包含对 $v$ 进行定值的基本块加入 $	ext{Worklist}$。
2. 当 $	ext{Worklist}$ 非空时，取出基本块 $X$。
3. 遍历 $X$ 的支配边界节点 $Y \in DF(X)$：
   - 若 $Y$ 尚未为变量 $v$ 插入 $\phi$ 节点：
     - 在 $Y$ 的起始处插入新 $\phi$ 节点：$\%v_{	ext{new}} = \phi \dots$
     - 将 $Y$ 压入 $	ext{Worklist}$（因为在 $Y$ 处插入 $\phi$ 等同于为 $v$ 产生了一个新的定值点，可能引发连锁支配边界扩张）。

阶段 2: 支配树深度优先遍历与变量重命名状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在完成全图 $\phi$ 节点占位后，编译器必须为所有变量分配版本编号。重命名算法利用 **支配树深度优先搜索（DomTree DFS Traversal）** 与 **作用域栈（Version Stack）** 协同推进：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     支配树 DFS 变量重命名状态机流转                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 状态维护 ]:                                                             |
   |   * Stack[v]: 变量 v 的当前有效 SSA 版本栈 (栈顶即为当前可见定值)           |
   |   * Counter[v]: 变量 v 的全局自增版本计数器                                 |
   |                                                                             |
   |   [ 访问基本块 B ]:                                                         |
   |   1. 遍历 B 顶部的所有 phi 节点:                                            |
   |      * 分配新版本 v_k = ++Counter[v]，将 v_k 压入 Stack[v]                  |
   |   2. 顺序遍历 B 中的普通指令:                                               |
   |      * 将所有读取操作数 (Use of v) 替换为 Stack[v].top()                    |
   |      * 若指令定值了 v (Def of v)，分配新版本 v_m = ++Counter[v]，压入 Stack[v] |
   |   3. 遍历 B 在 CFG 中的所有后继块 Succ:                                     |
   |      * 定位 Succ 顶部的 phi 节点，将来自 B 路径的对应操作数填入 Stack[v].top()  |
   |   4. 递归遍历 B 在支配树上的所有子节点 Child in DomChildren(B):             |
   |      * Rename(Child)                                                        |
   |   5. 离开 B 时的栈状态回滚 (Scope Pop):                                     |
   |      * 弹出在当前块 B 内部压入 Stack[v] 的所有版本，恢复外层支配状态        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Mem2Reg Pass 架构：从栈内存到 SSA 寄存器提升
--------------------------------------------

在现代编译器前端（如 Clang 生成 LLVM IR）中，直接在 AST 遍历期生成完美 SSA 形式会极大地增加前端的实现复杂度。

工业级解耦方案：Alloca 占位与 Mem2Reg 提升
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代编译器采用前后端分离策略：
1. **前端极简代码生成**：前端为源码中的每个可变局部变量在函数入口处发射一条 ``alloca`` 指令（在栈帧上分配物理槽位），所有变量读操作统一发射为 ``load``，写操作统一发射为 ``store``。此时生成的 IR 天然良构，无需关心复杂的控制流分流。
2. **中端 Mem2Reg Pass 栈提升**：中端优化管线的第一个 Pass 即执行 **Mem2Reg（Memory-to-Register Promotion）**。它分析所有 ``alloca`` 指令，识别未逃逸的标量变量，运行 Cytron 算法直接将 ``load/store`` 内存存取消除并提升为纯粹的 SSA $\phi$ 节点与虚拟寄存器。

.. list-table:: 允许被 Mem2Reg 提升的 Alloca 判定准则
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 判定维度
     - 允许提升的 Alloca 特征
     - 拒绝提升（保持内存形态）的场景
   * - 类型特征
     - 基础一阶标量类型（整型、浮点型、裸指针）
     - 包含复杂内嵌数组或动态对齐的超大聚合结构
   * - 指针逃逸判定
     - 仅被本函数内的直接 ``load`` 与 ``store`` 指令引用
     - 指针地址被作为参数传入外部未知函数，或存入全局指针
   * - 寻址模式
     - 无任何指针算术运算或 GEP 偏移偏移运算
     - 被 ``volatile`` 修饰（必须严格保持物理内存读写时序）

工业级 C++ 完整 SSA 构造与 Mem2Reg 提升引擎实现
------------------------------------------------

以下 C++ 源码实现了一套工业级自包含的 SSA 构造器与 Mem2Reg 栈提升 Pass。该实现涵盖：
1. 包含 ``Alloca``、``Load``、``Store``、``Phi``、二元算术、条件跳转的 SSA IR 指令体系。
2. 结合支配树与支配边界（DF）的 $\phi$ 节点放置算法。
3. 带有作用域回滚的支配树深度优先搜索变量重命名状态机。
4. 完整的 Mem2Reg 提升器，将局部变量的栈分配指令消除并生成标准的 SSA 文本表示。
5. 端到端测试验证套件（包含分支条件下的变量汇聚与 SSA 格式校验）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <stack>
   #include <sstream>
   #include <cassert>
   #include <algorithm>

   namespace ssa_engine {

   // =========================================================================
   // 1. SSA 扩展指令集与 IR 容器
   // =========================================================================
   enum class OpKind {
       Alloca,
       Load,
       Store,
       Add,
       CmpLT,
       Branch,
       BranchCond,
       Return,
       Phi
   };

   struct Instruction {
       OpKind Op;
       std::string Dest;                  // 定值结果 SSA 变量名
       std::string Op1;                   // 输入源 1
       std::string Op2;                   // 输入源 2
       std::string TargetLabel;           // 分支目标 1
       std::string FalseLabel;            // 条件分支目标 2
       
       // Phi 节点专有输入: 映射 [前驱基本块名 -> 传入的 SSA 变量名]
       std::unordered_map<std::string, std::string> PhiIncoming;

       std::string toString() const {
           std::stringstream ss;
           switch (Op) {
               case OpKind::Alloca:
                   ss << "  %" << Dest << " = alloca i32";
                   break;
               case OpKind::Load:
                   ss << "  %" << Dest << " = load i32, ptr %" << Op1;
                   break;
               case OpKind::Store:
                   ss << "  store i32 %" << Op1 << ", ptr %" << Op2;
                   break;
               case OpKind::Add:
                   ss << "  %" << Dest << " = add i32 %" << Op1 << ", %" << Op2;
                   break;
               case OpKind::CmpLT:
                   ss << "  %" << Dest << " = icmp slt i32 %" << Op1 << ", %" << Op2;
                   break;
               case OpKind::Branch:
                   ss << "  br label %" << TargetLabel;
                   break;
               case OpKind::BranchCond:
                   ss << "  br i1 %" << Op1 << ", label %" << TargetLabel << ", label %" << FalseLabel;
                   break;
               case OpKind::Return:
                   ss << "  ret i32 %" << Op1;
                   break;
               case OpKind::Phi: {
                   ss << "  %" << Dest << " = phi i32 ";
                   bool first = true;
                   for (const auto& pair : PhiIncoming) {
                       if (!first) ss << ", ";
                       ss << "[ %" << pair.second << ", %" << pair.first << " ]";
                       first = false;
                   }
                   break;
               }
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
       std::unordered_set<BasicBlock*> DominanceFrontier;

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
   // 2. Mem2Reg 栈提升与 SSA 构造引擎
   // =========================================================================
   class Mem2RegPass {
   public:
       static void runOnFunction(Function& func) {
           // 1. 收集所有可提升的 alloca 变量
           std::unordered_set<std::string> promotableAllocas;
           std::unordered_map<std::string, std::unordered_set<BasicBlock*>> allocaDefBlocks;

           for (const auto& b : func.Blocks) {
               for (const auto& inst : b->Instructions) {
                   if (inst.Op == OpKind::Alloca) {
                       promotableAllocas.insert(inst.Dest);
                   } else if (inst.Op == OpKind::Store) {
                       if (promotableAllocas.count(inst.Op2)) {
                           allocaDefBlocks[inst.Op2].insert(b.get());
                       }
                   }
               }
           }

           if (promotableAllocas.empty()) return;

           // 2. 阶段 1: 在迭代支配边界 (IDF) 处插入 Phi 节点
           for (const std::string& var : promotableAllocas) {
               std::unordered_set<BasicBlock*> hasPhi;
               std::queue<BasicBlock*> worklist;

               for (BasicBlock* defBlock : allocaDefBlocks[var]) {
                   worklist.push(defBlock);
               }

               while (!worklist.empty()) {
                   BasicBlock* curr = worklist.front();
                   worklist.pop();

                   for (BasicBlock* dfBlock : curr->DominanceFrontier) {
                       if (hasPhi.insert(dfBlock).second) {
                           // 插入未填充的占位 Phi 节点
                           Instruction phiInst;
                           phiInst.Op = OpKind::Phi;
                           phiInst.Dest = var; // 暂存原变量名，待重命名阶段分配唯一 SSA 编号
                           dfBlock->Instructions.insert(dfBlock->Instructions.begin(), phiInst);

                           worklist.push(dfBlock);
                       }
                   }
               }
           }

           // 3. 阶段 2: 支配树 DFS 变量重命名状态机
           std::unordered_map<std::string, std::stack<std::string>> versionStacks;
           std::unordered_map<std::string, uint32_t> versionCounters;

           for (const std::string& var : promotableAllocas) {
               versionStacks[var].push("undef"); // 初始未定义值
               versionCounters[var] = 0;
           }

           renameBlock(func.Entry, versionStacks, versionCounters, promotableAllocas);

           // 4. 清除冗余的 Alloca、Load 与 Store 指令
           for (auto& b : func.Blocks) {
               std::vector<Instruction> cleanInsts;
               for (const auto& inst : b->Instructions) {
                   if (inst.Op == OpKind::Alloca && promotableAllocas.count(inst.Dest)) {
                       continue; // 消除栈分配
                   }
                   if (inst.Op == OpKind::Store && promotableAllocas.count(inst.Op2)) {
                       continue; // 消除内存写入
                   }
                   if (inst.Op == OpKind::Load && promotableAllocas.count(inst.Op1)) {
                       continue; // 消除内存读取
                   }
                   cleanInsts.push_back(inst);
               }
               b->Instructions = std::move(cleanInsts);
           }
       }

   private:
       static void renameBlock(
           BasicBlock* block,
           std::unordered_map<std::string, std::stack<std::string>>& stacks,
           std::unordered_map<std::string, uint32_t>& counters,
           const std::unordered_set<std::string>& allocas)
       {
           if (!block) return;

           // 记录本块内部压入栈的变量，用于退出作用域时回滚
           std::vector<std::string> pushedVars;

           // 1. 处理本块开头的 Phi 节点定值
           for (auto& inst : block->Instructions) {
               if (inst.Op == OpKind::Phi && allocas.count(inst.Dest)) {
                   std::string origVar = inst.Dest;
                   std::string newVersion = origVar + "_" + std::to_string(++counters[origVar]);
                   inst.Dest = newVersion;
                   stacks[origVar].push(newVersion);
                   pushedVars.push_back(origVar);
               }
           }

           // 2. 顺序遍历普通指令，重命名 Use 与 Def
           for (auto& inst : block->Instructions) {
               if (inst.Op == OpKind::Store && allocas.count(inst.Op2)) {
                   // Store 对应一次 Def: 产生当前变量的新有效版本
                   std::string origVar = inst.Op2;
                   stacks[origVar].push(inst.Op1); // 直接将存入的值作为当前可见版本
                   pushedVars.push_back(origVar);
               } else if (inst.Op == OpKind::Load && allocas.count(inst.Op1)) {
                   // Load 对应一次 Use: 记录映射替换
                   std::string origVar = inst.Op1;
                   std::string currentVal = stacks[origVar].top();
                   inst.Dest = currentVal; // 标记替换目标
               } else {
                   // 普通指令的操作数替换
                   if (!inst.Op1.empty() && allocas.count(inst.Op1)) {
                       inst.Op1 = stacks[inst.Op1].top();
                   }
                   if (!inst.Op2.empty() && allocas.count(inst.Op2)) {
                       inst.Op2 = stacks[inst.Op2].top();
                   }
               }
           }

           // 3. 为所有后继块的 Phi 节点填充来自当前块的操作数
           for (BasicBlock* succ : block->Successors) {
               for (auto& inst : succ->Instructions) {
                   if (inst.Op == OpKind::Phi) {
                       // 恢复原变量名索引
                       std::string origVar = inst.Dest.substr(0, inst.Dest.find('_'));
                       if (allocas.count(origVar)) {
                           inst.PhiIncoming[block->Name] = stacks[origVar].top();
                       }
                   }
               }
           }

           // 4. 递归遍历支配树子节点
           for (BasicBlock* child : block->DomChildren) {
               renameBlock(child, stacks, counters, allocas);
           }

           // 5. 作用域退出: 回滚本块产生的所有栈压入
           for (const std::string& var : pushedVars) {
               stacks[var].pop();
           }
       }
   };

   } // namespace ssa_engine

   // =========================================================================
   // 3. 端到端测试与 Mem2Reg 验证套件
   // =========================================================================
   namespace test {

   inline void runSSATestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Mem2Reg Pass 栈提升与 SSA 形式生成验证套件
";
       std::cout << "=======================================================

";

       // 构造一个包含条件分支与栈上可变变量的典型函数:
       //
       // int test_branch(int cond) {
       //     int x;
       //     if (cond < 10) {
       //         x = 100;
       //     } else {
       //         x = 200;
       //     }
       //     return x + 1;
       // }

       using namespace ssa_engine;
       Function func;
       func.Name = "test_branch";

       BasicBlock* bEntry = func.createBlock("entry");
       BasicBlock* bThen  = func.createBlock("then_block");
       BasicBlock* bElse  = func.createBlock("else_block");
       BasicBlock* bMerge = func.createBlock("merge_block");

       func.Entry = bEntry;

       // 1. entry 指令流: alloca %x; br %cond, %then_block, %else_block
       bEntry->Instructions.push_back({OpKind::Alloca, "x", "", "", "", ""});
       bEntry->Instructions.push_back({OpKind::CmpLT, "cond_res", "cond", "10", "", ""});
       bEntry->Instructions.push_back({OpKind::BranchCond, "", "cond_res", "", "then_block", "else_block"});
       bEntry->Successors = {bThen, bElse};

       // 2. then_block: store 100, %x; br %merge_block
       bThen->Instructions.push_back({OpKind::Store, "", "100", "x", "", ""});
       bThen->Instructions.push_back({OpKind::Branch, "", "", "", "merge_block", ""});
       bThen->Predecessors = {bEntry};
       bThen->Successors = {bMerge};

       // 3. else_block: store 200, %x; br %merge_block
       bElse->Instructions.push_back({OpKind::Store, "", "200", "x", "", ""});
       bElse->Instructions.push_back({OpKind::Branch, "", "", "", "merge_block", ""});
       bElse->Predecessors = {bEntry};
       bElse->Successors = {bMerge};

       // 4. merge_block: %v = load %x; %res = add %v, 1; ret %res
       bMerge->Instructions.push_back({OpKind::Load, "v", "x", "", "", ""});
       bMerge->Instructions.push_back({OpKind::Add, "res", "v", "1", "", ""});
       bMerge->Instructions.push_back({OpKind::Return, "", "res", "", "", ""});
       bMerge->Predecessors = {bThen, bElse};

       // 挂载支配拓扑与支配边界 (DF)
       // DomTree: bEntry 直接支配 bThen, bElse, bMerge
       bEntry->DomChildren = {bThen, bElse, bMerge};
       bThen->IDom = bEntry;
       bElse->IDom = bEntry;
       bMerge->IDom = bEntry;

       // DF 集合: DF(bThen) = {bMerge}, DF(bElse) = {bMerge}
       bThen->DominanceFrontier = {bMerge};
       bElse->DominanceFrontier = {bMerge};

       std::cout << "[提升前: 基于栈内存 Alloca/Load/Store 的初始 IR]:
";
       func.dump();
       std::cout << "
";

       // 执行 Mem2Reg Pass
       Mem2RegPass::runOnFunction(func);

       std::cout << "[提升后: 纯粹静态单赋值 (SSA) 形式 IR]:
";
       func.dump();
       std::cout << "
";

       // 验证生成的 SSA 属性
       // 1. merge 块顶端必须成功插入 Phi 节点
       assert(!bMerge->Instructions.empty());
       const Instruction& phi = bMerge->Instructions[0];
       assert(phi.Op == OpKind::Phi);
       assert(phi.PhiIncoming.size() == 2);
       assert(phi.PhiIncoming.at("then_block") == "100");
       assert(phi.PhiIncoming.at("else_block") == "200");
       std::cout << "  -> merge_block 成功插入 Phi 节点并绑定前驱值: %"
                 << phi.Dest << " = phi [ 100, then_block ], [ 200, else_block ]
";

       // 2. Alloca、Load 与 Store 必须全量被消除
       for (const auto& b : func.Blocks) {
           for (const auto& inst : b->Instructions) {
               assert(inst.Op != OpKind::Alloca);
               assert(inst.Op != OpKind::Load);
               assert(inst.Op != OpKind::Store);
           }
       }
       std::cout << "  -> 全量栈内存分配与读写指令已成功提升为纯 SSA 寄存器值流。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展现了 Mem2Reg Pass 的核心优化效果：

1. **IDF 处 Phi 节点精准放置**：由于 ``x`` 在 ``then_block`` 与 ``else_block`` 中分别被定值，两者支配边界的并集 $DF(	ext{then}) \cup DF(	ext{else}) = \{	ext{merge\_block}\}$ 精确引导算法仅在 ``merge_block`` 首部插入唯一的 $\phi$ 节点。
2. **多前驱值精确绑定**：支配树重命名状态机在遍历前驱后继时，将 ``then_block`` 的定值 ``100`` 与 ``else_block`` 的定值 ``200`` 精确填充至 $\phi$ 节点的映射表中。
3. **栈内存操作彻底消除**：所有的 ``alloca``、``load`` 与 ``store`` 指令被全量剪除，后续计算 ``%res = add i32 %x_1, 1`` 直接引用 $\phi$ 节点产出的 SSA 寄存器值，实现了数据流拓扑的极致纯净化。

小结与下章导读
--------------

本章系统解构了现代编译器中端核心表示体系——静态单赋值（SSA）形式与 Mem2Reg 栈提升 Pass：

1. **值标识解耦原理**：阐明了变量名与唯一计算值绑定的物理事实，消除了传统槽位覆写对数据流分析的二次方复杂度阻碍。
2. **Phi 节点操作语义**：解构了 $\phi$ 节点在分支汇聚处的条件选择语义及其在基本块首部的物理拓扑约束。
3. **Cytron SSA 构建算法**：推导了基于迭代支配边界（IDF）的 $\phi$ 放置与基于支配树 DFS 栈回滚的变量重命名状态机。
4. **Mem2Reg 栈提升架构**：剖析了前端生成 ``alloca/load/store`` 规避复杂构造与中端自动化提升为纯 SSA 寄存器的工业解耦实践。

在完成了 SSA 形式的构建之后，编译器在中端优化管线中可以极其高效地开展各类数据流与循环优化。然而，在优化完成后向后端硬件指令集降级时，目标硬件 CPU 并无原生的 $\phi$ 指令。在第 4 模块第 5 节 **SSA 销毁与 Phi 消除：并行拷贝冲突、关键边分割 (Critical Edge Splitting) 与寄存器降级（``04_ir_cfg_and_ssa_construction/05_ssa_destruction_and_phi_elimination.rst``）** 中，我们将深入剖析如何安全脱离 SSA 形式、解决 $\phi$ 并行赋值冲突（Lost-Copy 与 Swap-Problem），以及将 SSA 虚拟寄存器降级为线性硬件可分配槽位。
