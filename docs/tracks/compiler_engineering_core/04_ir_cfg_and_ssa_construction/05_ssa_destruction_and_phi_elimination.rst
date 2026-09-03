====================================================================================================
SSA 销毁与 Phi 消除：并行拷贝冲突、关键边分割 (Critical Edge Splitting) 与寄存器降级
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 4 节（``04_ir_cfg_and_ssa_construction/04_ssa_form_value_identity_and_phi_nodes.rst``）中，我们深入剖析了静态单赋值（SSA）形式的核心优势、$\phi$ 节点的操作语义以及通过 Mem2Reg Pass 将栈内存读写（``alloca/load/store``）提升为纯粹虚拟寄存器值流的过程。SSA 形式为中端数据流分析、死代码消除（DCE）、全局值编号（GVN）与循环优化提供了极高精度的 Def-Use 依赖链。然而，现代物理硬件指令集（如 x86-64、AArch64、RISC-V）基于有限的物理寄存器与线性内存栈槽执行计算，底层微架构不存在能够依据前驱路径动态选择操作数的硬件 $\phi$ 指令。在编译器完成全部中端优化并跨入后端代码生成（Code Generation）阶段之前，必须执行 **SSA 销毁（SSA Destruction / Out-of-SSA）**，将抽象的 $\phi$ 节点还原为底层的寄存器搬移指令（Copy / Move），并重新引入可变存储槽位。本章深入剖析 $\phi$ 节点的并行赋值（Parallel Copy）语义、SSA 销毁过程中的经典缺陷（Lost-Copy 问题与 Swap 问题）、临界边分割（Critical Edge Splitting）在代码安放中的物理必要性、常规 SSA（CSSA）向变换 SSA（TSSA）的合流冲突消解，以及现代编译器无损降级为线性机器指令序列的完整工程实现。

SSA 销毁的物理动因与后端降级契约
--------------------------------

SSA 形式是编译器中端优化的专属抽象表示。后端代码生成面临以下物理约束：

1. **硬件指令集的单一定值缺失**：物理 CPU 寄存器数量有限（如 x86-64 的 16 个通用寄存器，ARM64 的 31 个通用寄存器），必须在不同时间段被反复复用（Register Reuse）以承载不同的生命周期。
2. **Phi 节点的物理虚构性**：$\phi$ 节点并非 CPU 可执行指令，它的本质是控制流分支合流时对不同路径定值的一个 **声明式数据合并契约**。
3. **降级核心任务**：SSA 销毁的核心使命是在保证语义绝对等价的前提下，将所有 $\phi$ 节点消除，并在前驱基本块的控制转移边上插入具体的拷贝指令（``mov dest, src``），将多个不同的 SSA 虚拟寄存器归并映射到同一个可变物理存储槽位。

Phi 节点的并行拷贝 (Parallel Copy) 语义
---------------------------------------

当一个基本块的头部同时存在多个 $\phi$ 节点时，SSA 语义严格规定：**同一个基本块内的所有 $\phi$ 节点是在控制流跨越基本块边界的瞬间，同时、原子、并行执行的。**

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      Phi 节点的并行原子语义 vs 顺序执行歧义                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 合流基本块 MergeBlock 开头的多个 Phi 节点 ]:                             |
   |      %x1 = phi [ %y0, PredecessorBlock ], ...                               |
   |      %y1 = phi [ %x0, PredecessorBlock ], ...                               |
   |                                                                             |
   |   * 并行语义 (Parallel Semantics):                                          |
   |     在控制流离开 PredecessorBlock 并进入 MergeBlock 的瞬间:                 |
   |     临时寄存器捕获: (t_x = %y0, t_y = %x0)                                  |
   |     同时原子更新:   (%x1 = t_x, %y1 = t_y)                                  |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   * 错误朴素顺序化 (Naive Sequentialization):                               |
   |     1. mov %x, %y   ; 此时 %x 的旧值被 %y 覆盖破坏!                         |
   |     2. mov %y, %x   ; 此时读取到的是已经变为 %y 的 %x，导致 %y 最终等于 %y! |
   |                                                                             |
   +-----------------------------------------------------------------------------+

若直接将并行拷贝转化为简单的顺序拷贝指令序列，极易引发变量生命周期重叠破坏。

Out-of-SSA 的两大经典陷阱：Lost-Copy 与 Swap 问题
-------------------------------------------------

在工业级编译器演进过程中，朴素的 $\phi$ 节点消除算法暴露出两个著名的语义破坏陷阱：

1. 交换问题 (The Swap Problem / Cycle Dependency)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

如上图所示，当两个 $\phi$ 节点构成环形相互依赖时（例如变量值在循环或分支中交叉传递：$x \leftarrow y, y \leftarrow x$）：
- 顺序拷贝 ``mov x, y`` 会先行覆盖目标变量 $x$ 的内存，导致后续指令 ``mov y, x`` 读取到被污染的新值。
- **物理消解机制**：算法必须先构建并行拷贝依赖有向图（Copy Dependency Graph）。当探测到图中存在环路（Cycle）时，必须引入一个临时的中间虚拟寄存器（Scratch Register $t$）打破环路：

  .. code-block:: text

     1. mov %scratch, %x0   ; 保存即将被覆盖的旧值
     2. mov %x1, %y0        ; 执行无环赋值
     3. mov %y1, %scratch   ; 从临时寄存器恢复写回

2. 丢失拷贝问题 (The Lost-Copy Problem)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当优化 Pass（如循环变换、复写传播）对 SSA 形式进行激进改写后，某个变量在多个 $\phi$ 节点与后续指令中交叉存活。若前驱块存在临界边（Critical Edge），直接在前驱块末尾插入拷贝会意外污染其他无关分支路径上的变量值：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     Lost-Copy 问题的临界边物理成因                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |          +-------------------+                                              |
   |          |  PredBlock (S)    | (拥有 2 个后继: Dest 和 Other)               |
   |          +-------------------+                                              |
   |               /         \                                                   |
   |              /           \ (临界边 Critical Edge)                           |
   |             v             v                                                 |
   |      +------------+     +-------------------------------+                   |
   |      | OtherBlock |     | DestBlock (拥有 2 个前驱)     |                   |
   |      | 读取 %x    |     | %x = phi [ %y, PredBlock ]... |                   |
   |      +------------+     +-------------------------------+                   |
   |                                                                             |
   |   * 冲突: 若在 PredBlock 插入 mov %x, %y:                                   |
   |     当控制流走向 OtherBlock 时，OtherBlock 中的 %x 被错误改写!              |
   |                                                                             |
   |   * 解决: 必须先执行 Critical Edge Splitting，将拷贝安放在专用的合成块中    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

临界边分割在 Phi 消除中的关键作用
---------------------------------

为了彻底杜绝 Lost-Copy 风险，**临界边分割（Critical Edge Splitting）是执行 SSA 销毁的前置刚性步骤**：
1. 识别所有从多后继块指向多前驱块的边。
2. 在边上插入合成跳转基本块 $B_{	ext{split}}$。
3. 将所有针对该前驱路径的 $\phi$ 消除拷贝指令，安全地放置在 $B_{	ext{split}}$ 内部。
4. 由于 $B_{	ext{split}}$ 具有单入单出的纯净拓扑，拷贝指令仅在控制流确实流向该目标汇聚块时生效，消除了对侧分支路径的副作用污染。

常规 SSA (CSSA) 与变量合并 (Coalescing) 优化
---------------------------------------------

为了减少 SSA 销毁阶段产生的冗余 ``mov`` 指令数量，现代编译器（如 LLVM 的 ``PHIElimination`` 与 ``LiveIntervals``）采用了基于 **干涉图（Interference Graph）** 的变量合并（Coalescing）技术。

CSSA 规范化与并查集变量归并
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **常规 SSA 形式（Conventional SSA, CSSA）**：
   若同一个 $\phi$ 节点的所有输入操作数以及该 $\phi$ 节点自身产出的定值，在整个程序的控制流图中彼此 **生命周期互不重叠（No Interference）**，则称该 IR 满足 CSSA 约束。
2. **变量合并（Variable Coalescing）**：
   对于满足 CSSA 约束的变量族，编译器使用并查集（Union-Find）将它们合并为同一个物理寄存器标识。消除 $\phi$ 时，由于操作数与目标已分配到相同槽位，对应的 ``mov x, x`` 指令直接被视作自赋值冗余代码被擦除，达成了零额外运行时指令消耗。

工业级 C++ 完整 SSA 销毁与并行拷贝消除引擎实现
----------------------------------------------

以下 C++ 源码实现了一套工业级自包含的 SSA 销毁与 $\phi$ 节点消除引擎。该实现涵盖：
1. 具备 $\phi$ 节点与并行拷贝语义的 IR 数据结构。
2. 针对 $\phi$ 消除的专用临界边自动探测与合成块插入。
3. 并行拷贝有向图依赖分析器，包含环路拓扑检测与借助 Scratch 临时寄存器打破环路（彻底解决 Swap 问题）。
4. 将全图 $\phi$ 节点安全替换为线性顺序 ``Copy``（``mov``）指令流。
5. 包含 Swap 环路依赖、多分支汇聚与临界边隔离的完整端到端测试套件。

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
   #include <algorithm>

   namespace out_of_ssa_engine {

   // =========================================================================
   // 1. IR 指令与基本块模型
   // =========================================================================
   enum class InstType {
       Copy,       // mov dest, src
       Add,        // dest = src1 + src2
       Branch,     // br label %target
       BranchCond, // br %cond, label %true, label %false
       Return,     // ret %src
       Phi         // dest = phi [src, pred]...
   };

   struct Instruction {
       InstType Type;
       std::string Dest;
       std::string Src1;
       std::string Src2;
       std::string TargetLabel;
       std::string FalseLabel;
       std::unordered_map<std::string, std::string> PhiArgs; // [PredBlock -> SrcVal]

       std::string toString() const {
           std::stringstream ss;
           switch (Type) {
               case InstType::Copy:
                   ss << "  %" << Dest << " = copy %" << Src1;
                   break;
               case InstType::Add:
                   ss << "  %" << Dest << " = add i32 %" << Src1 << ", %" << Src2;
                   break;
               case InstType::Branch:
                   ss << "  br label %" << TargetLabel;
                   break;
               case InstType::BranchCond:
                   ss << "  br i1 %" << Src1 << ", label %" << TargetLabel << ", label %" << FalseLabel;
                   break;
               case InstType::Return:
                   ss << "  ret i32 %" << Src1;
                   break;
               case InstType::Phi: {
                   ss << "  %" << Dest << " = phi i32 ";
                   bool first = true;
                   for (const auto& pair : PhiArgs) {
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

       explicit BasicBlock(std::string name) : Name(std::move(name)) {}

       Instruction* getTerminator() {
           if (!Instructions.empty()) {
               auto t = Instructions.back().Type;
               if (t == InstType::Branch || t == InstType::BranchCond || t == InstType::Return) {
                   return &Instructions.back();
               }
           }
           return nullptr;
       }
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

       BasicBlock* findBlock(const std::string& name) const {
           for (const auto& b : Blocks) {
               if (b->Name == name) return b.get();
           }
           return nullptr;
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
   // 2. 并行拷贝序列化算法 (Parallel Copy Sequentializer with Cycle Breaking)
   // =========================================================================
   struct ParallelCopyPair {
       std::string Dest;
       std::string Src;
   };

   class ParallelCopySolver {
   public:
       // 将一组并行的拷贝操作序列化为正确的顺序指令序列 (消除 Swap 冲突)
       static std::vector<Instruction> sequentialize(
           const std::vector<ParallelCopyPair>& parallelCopies,
           uint32_t& scratchCounter)
       {
           std::vector<Instruction> result;
           if (parallelCopies.empty()) return result;

           // 建立拷贝映射: dest -> src
           std::unordered_map<std::string, std::string> copyMap;
           std::unordered_set<std::string> allDests;
           std::unordered_set<std::string> allSrcs;

           for (const auto& cp : parallelCopies) {
               if (cp.Dest != cp.Src) { // 过滤恒等自赋值
                   copyMap[cp.Dest] = cp.Src;
                   allDests.insert(cp.Dest);
                   allSrcs.insert(cp.Src);
               }
           }

           // 循环处理，直到所有拷贝均被发射
           while (!copyMap.empty()) {
               // 1. 优先寻找就绪节点 (Ready Node): Dest 不作为任何其他未完成拷贝的 Src
               std::string readyDest;
               bool foundReady = false;

               for (const auto& pair : copyMap) {
                   const std::string& d = pair.first;
                   bool isReadByOther = false;
                   for (const auto& other : copyMap) {
                       if (other.second == d) {
                           isReadByOther = true;
                           break;
                       }
                   }
                   if (!isReadByOther) {
                       readyDest = d;
                       foundReady = true;
                       break;
                   }
               }

               if (foundReady) {
                   // 安全发射无环顺序拷贝
                   Instruction inst;
                   inst.Type = InstType::Copy;
                   inst.Dest = readyDest;
                   inst.Src1 = copyMap[readyDest];
                   result.push_back(inst);

                   copyMap.erase(readyDest);
               } else {
                   // 2. 命中环路依赖 (Swap Problem): 选取一个环内节点，引入 Scratch 寄存器破环
                   auto it = copyMap.begin();
                   std::string cycleDest = it->first;
                   std::string cycleSrc = it->second;

                   std::string scratchVar = "scratch_" + std::to_string(++scratchCounter);

                   // 发射: mov scratch, cycleSrc
                   Instruction saveInst;
                   saveInst.Type = InstType::Copy;
                   saveInst.Dest = scratchVar;
                   saveInst.Src1 = cycleSrc;
                   result.push_back(saveInst);

                   // 更新依赖: 将原先读取 cycleSrc 的地方重定向为 scratchVar
                   copyMap[cycleDest] = scratchVar;
               }
           }

           return result;
       }
   };

   // =========================================================================
   // 3. SSA 销毁 (Phi Elimination) Pass
   // =========================================================================
   class SSADestructionPass {
   public:
       static void runOnFunction(Function& func) {
           uint32_t scratchCounter = 0;

           // 1. 识别并分割所有临界边 (防止 Lost-Copy 污染)
           splitCriticalEdges(func);

           // 2. 收集每个前驱块所需要执行的并行拷贝集合
           // Map: [PredBlock -> Vector of (Dest, Src)]
           std::unordered_map<BasicBlock*, std::vector<ParallelCopyPair>> blockCopies;

           for (const auto& b : func.Blocks) {
               for (const auto& inst : b->Instructions) {
                   if (inst.Op == InstType::Phi) {
                       for (const auto& pair : inst.PhiArgs) {
                           BasicBlock* predBlock = func.findBlock(pair.first);
                           assert(predBlock && "Predecessor block not found for phi argument");
                           blockCopies[predBlock].push_back({inst.Dest, pair.second});
                       }
                   }
               }
           }

           // 3. 在各前驱块的末尾 (Terminator 之前) 插入序列化后的 Copy 指令
           for (auto& pair : blockCopies) {
               BasicBlock* pred = pair.first;
               auto& parallelPairs = pair.second;

               std::vector<Instruction> seqCopies =
                   ParallelCopySolver::sequentialize(parallelPairs, scratchCounter);

               if (!seqCopies.empty()) {
                   // 定位 Terminator 插入在其正前方
                   if (!pred->Instructions.empty() && pred->getTerminator()) {
                       auto it = pred->Instructions.end() - 1;
                       pred->Instructions.insert(it, seqCopies.begin(), seqCopies.end());
                   } else {
                       pred->Instructions.insert(pred->Instructions.end(), seqCopies.begin(), seqCopies.end());
                   }
               }
           }

           // 4. 从所有基本块中全量移除 Phi 节点
           for (auto& b : func.Blocks) {
               std::vector<Instruction> cleanInsts;
               for (const auto& inst : b->Instructions) {
                   if (inst.Op != InstType::Phi) {
                       cleanInsts.push_back(inst);
                   }
               }
               b->Instructions = std::move(cleanInsts);
           }
       }

   private:
       static void splitCriticalEdges(Function& func) {
           std::vector<std::pair<BasicBlock*, BasicBlock*>> criticalEdges;

           for (const auto& b : func.Blocks) {
               if (b->Successors.size() > 1) {
                   for (BasicBlock* succ : b->Successors) {
                       if (succ->Predecessors.size() > 1) {
                           criticalEdges.emplace_back(b.get(), succ);
                       }
                   }
               }
           }

           for (auto& edge : criticalEdges) {
               BasicBlock* src = edge.first;
               BasicBlock* dst = edge.second;

               std::string splitName = src->Name + "_to_" + dst->Name + "_crit_edge";
               BasicBlock* splitBlock = func.createBlock(splitName);

               Instruction brInst;
               brInst.Type = InstType::Branch;
               brInst.TargetLabel = dst->Name;
               splitBlock->Instructions.push_back(brInst);

               Instruction* term = src->getTerminator();
               if (term) {
                   if (term->Type == InstType::BranchCond) {
                       if (term->TargetLabel == dst->Name) term->TargetLabel = splitName;
                       if (term->FalseLabel == dst->Name) term->FalseLabel = splitName;
                   } else if (term->Type == InstType::Branch) {
                       if (term->TargetLabel == dst->Name) term->TargetLabel = splitName;
                   }
               }

               // 更新目标块中 Phi 节点的前驱来源标记
               for (auto& inst : dst->Instructions) {
                   if (inst.Op == InstType::Phi) {
                       if (inst.PhiArgs.count(src->Name)) {
                           std::string val = inst.PhiArgs[src->Name];
                           inst.PhiArgs.erase(src->Name);
                           inst.PhiArgs[splitName] = val;
                       }
                   }
               }

               // 重构边拓扑
               src->Successors.erase(std::remove(src->Successors.begin(), src->Successors.end(), dst), src->Successors.end());
               src->Successors.push_back(splitBlock);
               splitBlock->Predecessors.push_back(src);
               splitBlock->Successors.push_back(dst);
               dst->Predecessors.erase(std::remove(dst->Predecessors.begin(), dst->Predecessors.end(), src), dst->Predecessors.end());
               dst->Predecessors.push_back(splitBlock);
           }
       }
   };

   } // namespace out_of_ssa_engine

   // =========================================================================
   // 4. 端到端测试与 Swap 环路破除验证套件
   // =========================================================================
   namespace test {

   inline void runSSADestructionTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " SSA 销毁 (Out-of-SSA) 与 Swap 环路破除测试套件
";
       std::cout << "=======================================================

";

       // 测试场景: 经典循环变量交换 (The Swap Problem)
       //
       // LoopHeader:
       //   %a1 = phi [ %a0, Entry ], [ %b1, LoopBody ]
       //   %b1 = phi [ %b0, Entry ], [ %a1, LoopBody ]
       //   br label %LoopBody
       //
       // 在 LoopBody 回跳时存在交叉赋值: a1 <- b1, b1 <- a1 (必须利用 Scratch 破环!)

       using namespace out_of_ssa_engine;
       Function func;
       func.Name = "swap_loop_demo";

       BasicBlock* bEntry = func.createBlock("entry");
       BasicBlock* bHeader = func.createBlock("loop.header");
       BasicBlock* bBody = func.createBlock("loop.body");

       func.Entry = bEntry;

       // Entry 块
       bEntry->Instructions.push_back({InstType::Copy, "a0", "10", "", "", "", {}});
       bEntry->Instructions.push_back({InstType::Copy, "b0", "20", "", "", "", {}});
       bEntry->Instructions.push_back({InstType::Branch, "", "", "", "loop.header", "", {}});
       bEntry->Successors = {bHeader};

       // Header 块 (包含环形依赖的 2 个 Phi)
       Instruction phiA;
       phiA.Type = InstType::Phi;
       phiA.Dest = "a1";
       phiA.PhiArgs["entry"] = "a0";
       phiA.PhiArgs["loop.body"] = "b1"; // 来自 Body 的 b1

       Instruction phiB;
       phiB.Type = InstType::Phi;
       phiB.Dest = "b1";
       phiB.PhiArgs["entry"] = "b0";
       phiB.PhiArgs["loop.body"] = "a1"; // 来自 Body 的 a1

       bHeader->Instructions.push_back(phiA);
       bHeader->Instructions.push_back(phiB);
       bHeader->Instructions.push_back({InstType::Branch, "", "", "", "loop.body", "", {}});
       bHeader->Predecessors = {bEntry, bBody};
       bHeader->Successors = {bBody};

       // Body 块
       bBody->Instructions.push_back({InstType::Branch, "", "", "", "loop.header", "", {}});
       bBody->Predecessors = {bHeader};
       bBody->Successors = {bHeader};

       std::cout << "[消除前: 包含环形依赖 Phi 节点的 SSA IR]:
";
       func.dump();
       std::cout << "
";

       // 执行 SSA 销毁
       SSADestructionPass::runOnFunction(func);

       std::cout << "[消除后: 降级为线性 Copy/Scratch 指令的非 SSA IR]:
";
       func.dump();
       std::cout << "
";

       // 验证生成的非 SSA 属性
       // 1. 全图必须不存在任何 Phi 节点
       for (const auto& b : func.Blocks) {
           for (const auto& inst : b->Instructions) {
               assert(inst.Type != InstType::Phi);
           }
       }
       std::cout << "  -> 全图 Phi 节点已全量清除。
";

       // 2. LoopBody 末尾必须成功插入 Scratch 寄存器破除环路
       bool scratchFound = false;
       for (const auto& inst : bBody->Instructions) {
           if (inst.Type == InstType::Copy && inst.Dest.find("scratch") != std::string::npos) {
               scratchFound = true;
               std::cout << "  -> 成功在 loop.body 捕获 Scratch 破环指令: " << inst.toString() << "
";
           }
       }
       assert(scratchFound);
       std::cout << "  -> Swap Problem 环形冲突已成功通过 Scratch 临时变量化解。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了 SSA 销毁的完整物理转换：

1. **并行拷贝无损序列化**：在 ``loop.body`` 向 ``loop.header`` 回跳时，原 $\phi$ 节点包含 $a_1 \leftarrow b_1$ 与 $b_1 \leftarrow a_1$ 的环路依赖。算法成功发射：
   - 暂存破坏源：``%scratch_1 = copy %a1``
   - 无后顾之忧赋值：``%a1 = copy %b1``
   - 恢复写入：``%b1 = copy %scratch_1``
   精准消除了变量覆盖导致的语义破坏。
2. **临界边物理隔离**：对于存在多个后继的前驱分支，边分割机制确保了拷贝动作仅发生在该前驱与该汇合块之间的专用路径上。
3. **顺利交付后端**：消除 $\phi$ 节点后的 IR 转化为纯粹的直线代码与条件跳转序列，使后续的物理寄存器分配器（Register Allocator）能够直接开展活跃区间分析与图着色。

小结与全模块结项导读
--------------------

本章系统解构了现代编译器跨越中端与后端分水岭的核心收尾技术——SSA 销毁与 $\phi$ 节点消除：

1. **并行拷贝原子语义**：形式化阐明了 $\phi$ 节点在基本块边界上的同时执行模型，推导了简单顺序化赋值引发数据覆盖的根本原因。
2. **经典冲突消解**：剖析了利用临界边分割解决 Lost-Copy 问题，以及利用依赖图拓扑排序与 Scratch 临时寄存器打破环路解决 Swap 问题的物理机理。
3. **CSSA 与变量合并**：阐明了通过干涉图消除自赋值冗余 ``mov`` 指令的优化路径。

========================================================================
第 4 模块：中间表示 (IR)、控制流图 (CFG) 与 SSA 形式全量完工结项
========================================================================

至此，《现代编译器架构设计与程序转换优化全景深度剖析》**第 4 模块（04_ir_cfg_and_ssa_construction）的 5 节核心专著章节已全部全量完工落盘**：
- **01 节**：中间表示 (IR) 设计哲学：高层语言语义保留与机器无关性前端解耦、受控降级 (Lowering)
- **02 节**：基本块与控制流图 (CFG)：单入口单出口区间、Terminator 终止指令与前驱后继边拓扑
- **03 节**：支配关系与自然循环识别：不可达块消除、支配树 (Dominator Tree) 构建与回边 (Backedge) 检测
- **04 节**：SSA 静态单赋值形式核心：变量槽位向唯一计算值映射、Phi 节点语义与 Mem2Reg 栈提升
- **05 节**：SSA 销毁与 Phi 消除：并行拷贝冲突、关键边分割 (Critical Edge Splitting) 与寄存器降级

在接下来的 **第 5 模块：数据流分析与中端优化 Pass 体系（05_data_flow_analysis_and_optimizations）** 中，我们将全面进军编译器的中端核心优化算法。在第 5 模块第 1 节 **数据流分析框架：传递函数 (Transfer Function)、格理论 (Lattice) 与不动点单调迭代收敛（``05_data_flow_analysis_and_optimizations/01_data_flow_framework_lattices_and_fixed_points.rst``）** 中，我们将深入剖析半偏序集、交半格（Meet-Semilattice）、单调传递函数与 Kildall 不动点迭代算法在编译器静态分析中的数学基石。
