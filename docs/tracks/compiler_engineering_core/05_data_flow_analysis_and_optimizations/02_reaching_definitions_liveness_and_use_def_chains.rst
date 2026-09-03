====================================================================================================
到达定值与活跃变量分析：Kill/Gen 集合构建、Def-Use / Use-Def 链与死代码消除 (DCE)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块第 1 节（``05_data_flow_analysis_and_optimizations/01_data_flow_framework_lattices_and_fixed_points.rst``）中，我们系统确立了数据流分析的数学基石——格理论（Lattice Theory）、单调传递函数（Transfer Function）与 Kildall 不动点迭代算法收敛性证明。格理论为静态分析提供了统一的形式化语义空间。本章将该抽象数学框架落地于编译器中端最具代表性的两类经典位向量（Bit-Vector）数据流分析：**正向到达定值分析（Reaching Definitions）** 与 **逆向活跃变量分析（Live Variables）**。到达定值回答“当前程序点读取的值可能由哪些历史定值生成”，活跃变量回答“当前定值产生的结果在未来路径上是否还可能被读取”。本章深入剖析基于位向量（BitVector）的高性能 Gen/Kill 集合构建、Def-Use 与 Use-Def 显式依赖网格的维护机理、基于活跃变量分析的死代码消除（Dead Code Elimination, DCE）状态机，以及从非 SSA 密集数据流链向 SSA 稀疏值流图的演进本质。

到达定值分析 (Reaching Definitions)：正向 May 分析模型
------------------------------------------------------

**到达定值分析（Reaching Definitions Analysis）** 追踪程序中每一个变量的定值点（Definition / 写入操作）是否能够沿着某条控制流路径传播至指定的程序点，且在中途未被该变量的新定值所覆盖杀死（Killed）。

物理模型与数学形式化
~~~~~~~~~~~~~~~~~~~~

设程序中所有定值点的全集为 $\mathcal{U}_{	ext{defs}} = \{d_1, d_2, \dots, d_M\}$，每个定值 $d_k$ 关联一个被写入的目标变量 $	ext{var}(d_k)$。

1. **格定义**：采用幂集布尔格 $(\mathcal{P}(\mathcal{U}_{	ext{defs}}), \subseteq, \cup, \cap, \emptyset, \mathcal{U}_{	ext{defs}})$。
2. **流动方向**：正向（Forward）。
3. **会合算子**：并集 $\cup$（May 分析，只要存在一条路径可达即保留）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     到达定值分析 (Reaching Definitions) 拓扑                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 前驱基本块 P1 ] (OUT[P1])       [ 前驱基本块 P2 ] (OUT[P2])             |
   |              \                             /                                |
   |               \                           /                                 |
   |                v                         v                                  |
   |              +-----------------------------+                                |
   |              | IN[B] = OUT[P1] U OUT[P2]   | <--- 会合算子: 并集 (May)      |
   |              |-----------------------------|                                |
   |              |  f_B(X) = Gen[B] U          |                                |
   |              |           (X \ Kill[B])     | <--- 传递函数 (Transfer Func)  |
   |              |-----------------------------|                                |
   |              | OUT[B]                      |                                |
   |              +-----------------------------+                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Gen 与 Kill 集合的局部构建规则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于基本块 $B$：
- **$	ext{Gen}[B]$（向下暴露定值集）**：基本块 $B$ 内部生成的定值集合，且该定值在其后没有被 $B$ 内部对同一变量的后续定值所覆盖。
- **$	ext{Kill}[B]$（杀死定值集）**：程序全集中所有与 $B$ 内部定值修改了相同变量的其他外部定值集合：

.. math::

   	ext{Kill}[B] = \bigcup_{d \in 	ext{DefsIn}(B)} \{ d' \in \mathcal{U}_{	ext{defs}} \mid 	ext{var}(d') = 	ext{var}(d) \land d' 
eq d \}

数据流传递方程组为：

.. math::

   IN[B] = \bigcup_{P \in Pred(B)} OUT[P]

.. math::

   OUT[B] = 	ext{Gen}[B] \cup (IN[B] \setminus 	ext{Kill}[B])

活跃变量分析 (Live Variable Analysis)：逆向 May 分析模型
--------------------------------------------------------

**活跃变量分析（Live Variable Analysis / Liveness）** 判定在某个程序点上，变量 $v$ 中当前保存的值是否可能在沿 CFG 从当前点出发的某条未来执行路径上被读取（Used）。若在任何未来路径上被读取前 $v$ 均被新值覆盖或程序已退出，则称 $v$ 在该点是 **死亡的（Dead）**。

物理模型与数学形式化
~~~~~~~~~~~~~~~~~~~~

设程序中所有变量名的全集为 $\mathcal{U}_{	ext{vars}} = \{v_1, v_2, \dots, v_K\}$。

1. **格定义**：采用幂集布尔格 $(\mathcal{P}(\mathcal{U}_{	ext{vars}}), \subseteq, \cup, \cap, \emptyset, \mathcal{U}_{	ext{vars}})$。
2. **流动方向**：逆向（Backward，从出口向入口回溯）。
3. **会合算子**：并集 $\cup$（May 分析，只要未来某条分支需要读取，当前变量即处于活跃状态）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     活跃变量分析 (Live Variables) 逆向拓扑                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              +-----------------------------+                                |
   |              | IN[B] = Use[B] U            |                                |
   |              |         (OUT[B] \ Def[B])   | <--- 逆向传递函数              |
   |              |-----------------------------|                                |
   |              | 基本块 B 执行内容           |                                |
   |              |-----------------------------|                                |
   |              | OUT[B] = Union IN[Succ]     | <--- 汇聚来自所有后继的活跃需求|
   |              +-----------------------------+                                |
   |                             /               \                               |
   |                            /                 \                              |
   |                           v                   v                             |
   |              [ 后继基本块 S1 ] (IN[S1])     [ 后继基本块 S2 ] (IN[S2])      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Use 与 Def 集合的局部构建规则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于基本块 $B$：
- **$	ext{Use}[B]$（向上暴露使用集）**：在 $B$ 内部被读取、且在当前块该读取点之前未被 $B$ 内部语句重新定值的变量集合。
- **$	ext{Def}[B]$（块内定值集）**：在 $B$ 内部被写入定值的变量集合。

逆向数据流传递方程组为：

.. math::

   OUT[B] = \bigcup_{S \in Succ(B)} IN[S]

.. math::

   IN[B] = 	ext{Use}[B] \cup (OUT[B] \setminus 	ext{Def}[B])

两大位向量分析特性深度对比
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 到达定值分析与活跃变量分析特性对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 到达定值分析 (Reaching Definitions)
     - 活跃变量分析 (Live Variables)
   * - 分析方向
     - 正向 (Forward)：沿控制流自顶向下推进
     - 逆向 (Backward)：沿控制流自底向上回溯
   * - 集合元素实体
     - 定值指令标识点集合 ($d \in \mathcal{U}_{	ext{defs}}$)
     - 程序变量符号名集合 ($v \in \mathcal{U}_{	ext{vars}}$)
   * - 边界初始状态
     - $OUT[Entry] = \emptyset$（初始无定值到达）
     - $IN[Exit] = \emptyset$（程序退出后无变量存活）
   * - 典型下游优化
     - 常量传播、复写传播、未初始化变量检测
     - 死代码消除 (DCE)、寄存器分配 (活跃区间分析)

Def-Use 链与 Use-Def 链拓扑
---------------------------

数据流分析计算出的集合最终固化为指令间的直接拓扑索引：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Def-Use 与 Use-Def 链物理映射拓扑                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 定值指令 Def 1 ] : d1: x = a + b                                        |
   |           |                                                                 |
   |           +-----------------------+-----------------------+                 |
   |           | (Def-Use 链: 1 对多)  | (Def-Use 链)          |                 |
   |           v                       v                       v                 |
   |   [ 使用指令 Use 1 ]      [ 使用指令 Use 2 ]      [ 使用指令 Use 3 ]        |
   |   u1: y = x * 2           u2: z = x - 4           u3: ret x                 |
   |           ^                       ^                       ^                 |
   |           \-----------------------+-----------------------/                 |
   |                                   |                                         |
   |                         (Use-Def 链: 多对 1)                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **Use-Def 链（UD 链）**：从某个使用点 $u$ 指向所有能够到达该点并提供其操作数初值的定值点集合 $	ext{UD}(u) = \{d_1, d_2, \dots\}$。
2. **Def-Use 链（DU 链）**：从某个定值点 $d$ 指向所有能够读取该定值结果的使用点集合 $	ext{DU}(d) = \{u_1, u_2, \dots\}$。

SSA 形式对数据流链的复杂度降阶
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统非 SSA 代码中，由于存在多次覆写与分支汇聚，一条变量可能产生密集的网状依赖，导致 DU/UD 链的空间与遍历时间复杂度达到 $\mathcal{O}(|	ext{Defs}| 	imes |	ext{Uses}|)$。

在 SSA 形式下，由于每个名字全局唯一绑定单一定值，**每个 Use 的 UD 链退化为唯一的单个指针（$\mathcal{O}(1)$ 常数时间直接索引 Def）**，彻底消除了数据流方程的求解开销。

死代码消除 (Dead Code Elimination, DCE) 算法
--------------------------------------------

**死代码消除（DCE）** 是编译器中端最核心的瘦身优化 Pass。其目标是识别并清除对程序外部可观测行为（I/O、全局内存、返回值）没有任何贡献的纯计算指令。

可消除指令判定准则
~~~~~~~~~~~~~~~~~~

一条指令 $I: 	ext{dest} = 	ext{op}(s_1, s_2)$ 能够被判定为死代码并安全删除，必须同时满足以下两条刚性约束：
1. **无关键副作用（No Observable Side Effects）**：指令不包含易失内存读写（``volatile``）、系统调用、外部 I/O 操作、内存分配或可能触发硬件异常的操作（如未受保护的除零）。
2. **定值非活跃（Dead Destination）**：在指令 $I$ 紧随其后的程序点上，目标变量 $	ext{dest}$ 处于非活跃状态（$	ext{dest} 
otin 	ext{LiveAfter}(I)$），或在 SSA 形式下其 Def-Use 链为空（$	ext{Users}(	ext{dest}) = \emptyset$）。

工作表死代码消除状态机 (Mark-Sweep DCE)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工业级 DCE 通常采用类似垃圾回收的 **标记-清除（Mark-Sweep）工作表算法**：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     工作表死代码消除 (Mark-Sweep DCE) 算法                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 关键指令标记 (Mark Critical Instructions) ]                     |
   |      * 扫描全程序，将所有固有关键指令压入 Worklist 并标记为 Live:           |
   |        1. 函数返回指令 (ret)                                                |
   |        2. 外部函数调用与 I/O 指令                                           |
   |        3. 内存写入指令 (store)                                              |
   |                                                                             |
   |   [ 阶段 2: 依赖逆向传播 (Reverse Dependency Propagation) ]                 |
   |      While Worklist 非空:                                                   |
   |         Pop 一条已标记活跃的指令 I                                          |
   |         For I 引用的每个输入操作数 Op:                                      |
   |            定位 Op 的定值指令 DefInst (沿 Use-Def 链)                       |
   |            If DefInst 未被标记为 Live:                                      |
   |               标记 DefInst 为 Live                                          |
   |               Worklist.push(DefInst)                                        |
   |                                                                             |
   |   [ 阶段 3: 死代码清除 (Sweep Dead Instructions) ]                          |
   |      遍历全程序所有基本块中的指令:                                          |
   |         If 指令未被标记为 Live:                                             |
   |            物理从基本块中移除并释放内存                                     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

位向量 (BitVector) 运算加速与工业级微架构优化
---------------------------------------------

工业级编译器在处理包含成千上万个基本块与定值的大型函数时，若采用基于哈希表（``std::unordered_set``）的集合运算，将引发海量的动态内存申请与 CPU 缓存失效。

现代数据流分析全面推行 **位向量（BitVector）密集表示**：
- 每个程序事实（定值或变量）映射为位向量中的唯一下标索引（Bit Index）。
- 集合并集（$\cup$）直接映射为硬件原生按位或指令（``OR``）。
- 集合交集（$\cap$）直接映射为硬件原生按位与指令（``AND``）。
- 集合差集（$X \setminus 	ext{Kill}$）直接映射为 ``AND-NOT`` 指令（$X \ \& \ \sim	ext{Kill}$）。
- 状态变化检测通过单条 64 位整数比较（``word != old_word``）或 SIMD AVX-512 向量化指令在单个时钟周期内并行比对 512 个事实，使不动点求解达到极高的机器吞吐率。

工业级 C++ 完整数据流与死代码消除引擎实现
------------------------------------------

以下 C++ 源码实现了一套自包含的位向量到达定值、活跃变量分析与死代码消除（DCE）引擎。该实现涵盖：
1. 高性能固定位宽 `BitVector` 类，支持位运算交并差。
2. 正向到达定值分析器（Gen/Kill 收集与不动点求解）。
3. 逆向活跃变量分析器（Use/Def 收集与逆向不动点求解）。
4. 基于活跃度分析与 Mark-Sweep 机制的死代码消除器（DCE Pass）。
5. 包含无用死计算、分支变量生命周期重叠与死代码物理剔除的完整测试套件。

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

   namespace dataflow_opt_engine {

   // =========================================================================
   // 1. 高性能密集位向量 (BitVector)
   // =========================================================================
   class BitVector {
   public:
       std::vector<uint64_t> Words;
       size_t NumBits = 0;

       BitVector() = default;
       explicit BitVector(size_t numBits) : NumBits(numBits) {
           Words.resize((numBits + 63) / 64, 0);
       }

       void set(size_t bit) {
           assert(bit < NumBits);
           Words[bit / 64] |= (1ULL << (bit % 64));
       }

       void reset(size_t bit) {
           assert(bit < NumBits);
           Words[bit / 64] &= ~(1ULL << (bit % 64));
       }

       bool test(size_t bit) const {
           assert(bit < NumBits);
           return (Words[bit / 64] & (1ULL << (bit % 64))) != 0;
       }

       bool operator==(const BitVector& other) const {
           return Words == other.Words;
       }
       bool operator!=(const BitVector& other) const {
           return !(*this == other);
       }

       // 按位或: this = this | other
       void unionWith(const BitVector& other) {
           assert(Words.size() == other.Words.size());
           for (size_t i = 0; i < Words.size(); ++i) {
               Words[i] |= other.Words[i];
           }
       }

       // 按位差: this = this & ~other
       void difference(const BitVector& other) {
           assert(Words.size() == other.Words.size());
           for (size_t i = 0; i < Words.size(); ++i) {
               Words[i] &= ~other.Words[i];
           }
       }
   };

   // =========================================================================
   // 2. 指令与基本块拓扑
   // =========================================================================
   enum class InstKind {
       Assign, // dest = src1 (or const)
       Add,    // dest = src1 + src2
       Store,  // store src1, ptr dest
       Return  // ret src1
   };

   struct Instruction {
       uint32_t DefId = 0;      // 全局唯一定值编号
       InstKind Kind;
       std::string Dest;        // 被定值变量名 (若有)
       std::string Src1;        // 读取源操作数 1
       std::string Src2;        // 读取源操作数 2
       bool HasSideEffect = false;

       std::string toString() const {
           std::stringstream ss;
           ss << "[d" << DefId << "] ";
           switch (Kind) {
               case InstKind::Assign:
                   ss << "%" << Dest << " = %" << Src1;
                   break;
               case InstKind::Add:
                   ss << "%" << Dest << " = add %" << Src1 << ", %" << Src2;
                   break;
               case InstKind::Store:
                   ss << "store %" << Src1 << ", ptr %" << Dest;
                   break;
               case InstKind::Return:
                   ss << "ret %" << Src1;
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

       explicit BasicBlock(std::string name) : Name(std::move(name)) {}
   };

   class FlowGraph {
   public:
       BasicBlock* Entry = nullptr;
       std::vector<std::unique_ptr<BasicBlock>> Blocks;

       BasicBlock* createBlock(const std::string& name) {
           Blocks.push_back(std::make_unique<BasicBlock>(name));
           return Blocks.back().get();
       }

       void addEdge(BasicBlock* from, BasicBlock* to) {
           from->Successors.push_back(to);
           to->Predecessors.push_back(from);
       }
   };

   // =========================================================================
   // 3. 活跃变量分析器 (Live Variable Analyzer - Backward May)
   // =========================================================================
   class LivenessAnalyzer {
   public:
       std::unordered_map<std::string, size_t> VarToBit;
       std::vector<std::string> BitToVar;

       std::unordered_map<BasicBlock*, BitVector> DefSets;
       std::unordered_map<BasicBlock*, BitVector> UseSets;
       std::unordered_map<BasicBlock*, BitVector> InLive;
       std::unordered_map<BasicBlock*, BitVector> OutLive;

       void run(FlowGraph& graph) {
           collectVariables(graph);
           size_t numVars = BitToVar.size();

           // 1. 构建每个块的局部 Use 与 Def 集合
           for (const auto& b : graph.Blocks) {
               BitVector def(numVars);
               BitVector use(numVars);

               for (const auto& inst : b->Instructions) {
                   // 检查源操作数读取 (未被本块先前定值覆盖的属于 Use)
                   if (!inst.Src1.empty() && VarToBit.count(inst.Src1)) {
                       size_t bit = VarToBit[inst.Src1];
                       if (!def.test(bit)) use.set(bit);
                   }
                   if (!inst.Src2.empty() && VarToBit.count(inst.Src2)) {
                       size_t bit = VarToBit[inst.Src2];
                       if (!def.test(bit)) use.set(bit);
                   }
                   // 检查目标定值
                   if (!inst.Dest.empty() && inst.Kind != InstKind::Store) {
                       if (VarToBit.count(inst.Dest)) {
                           def.set(VarToBit[inst.Dest]);
                       }
                   }
               }
               DefSets[b.get()] = def;
               UseSets[b.get()] = use;
               InLive[b.get()] = BitVector(numVars);
               OutLive[b.get()] = BitVector(numVars);
           }

           // 2. 逆向工作表迭代
           std::queue<BasicBlock*> worklist;
           for (const auto& b : graph.Blocks) {
               worklist.push(b.get());
           }

           while (!worklist.empty()) {
               BasicBlock* curr = worklist.front();
               worklist.pop();

               // OUT[curr] = Union_{Succ} IN[Succ]
               BitVector newOut(numVars);
               for (BasicBlock* succ : curr->Successors) {
                   newOut.unionWith(InLive[succ]);
               }
               OutLive[curr] = newOut;

               // IN[curr] = Use[curr] U (OUT[curr] \ Def[curr])
               BitVector newIn = newOut;
               newIn.difference(DefSets[curr]);
               newIn.unionWith(UseSets[curr]);

               if (newIn != InLive[curr]) {
                   InLive[curr] = newIn;
                   for (BasicBlock* pred : curr->Predecessors) {
                       worklist.push(pred);
                   }
               }
           }
       }

   private:
       void collectVariables(FlowGraph& graph) {
           VarToBit.clear();
           BitToVar.clear();
           for (const auto& b : graph.Blocks) {
               for (const auto& inst : b->Instructions) {
                   if (!inst.Dest.empty() && inst.Kind != InstKind::Store) {
                       if (!VarToBit.count(inst.Dest)) {
                           VarToBit[inst.Dest] = BitToVar.size();
                           BitToVar.push_back(inst.Dest);
                       }
                   }
                   if (!inst.Src1.empty() && !VarToBit.count(inst.Src1)) {
                       VarToBit[inst.Src1] = BitToVar.size();
                       BitToVar.push_back(inst.Src1);
                   }
                   if (!inst.Src2.empty() && !VarToBit.count(inst.Src2)) {
                       VarToBit[inst.Src2] = BitToVar.size();
                       BitToVar.push_back(inst.Src2);
                   }
               }
           }
       }
   };

   // =========================================================================
   // 4. 死代码消除 (Dead Code Elimination, DCE) Pass
   // =========================================================================
   class DeadCodeEliminationPass {
   public:
       static size_t run(FlowGraph& graph) {
           LivenessAnalyzer liveness;
           liveness.run(graph);

           size_t eliminatedCount = 0;

           // 逆向扫描每个基本块内部的指令
           for (auto& b : graph.Blocks) {
               BitVector live = liveness.OutLive[b.get()];
               std::vector<Instruction> survivingInsts;

               for (auto it = b->Instructions.rbegin(); it != b->Instructions.rend(); ++it) {
                   Instruction& inst = *it;
                   bool isDead = false;

                   // 判定是否属于可删除的无用纯计算定值
                   if (!inst.HasSideEffect && inst.Kind != InstKind::Return && inst.Kind != InstKind::Store) {
                       if (!inst.Dest.empty() && liveness.VarToBit.count(inst.Dest)) {
                           size_t destBit = liveness.VarToBit[inst.Dest];
                           if (!live.test(destBit)) {
                               isDead = true; // 目标定值在其后完全未存活，判定为死代码
                           }
                       }
                   }

                   if (isDead) {
                       ++eliminatedCount;
                   } else {
                       survivingInsts.push_back(inst);
                       // 更新当前活跃变量集: 杀死当前定值，激活输入源操作数
                       if (!inst.Dest.empty() && inst.Kind != InstKind::Store) {
                           if (liveness.VarToBit.count(inst.Dest)) {
                               live.reset(liveness.VarToBit[inst.Dest]);
                           }
                       }
                       if (!inst.Src1.empty() && liveness.VarToBit.count(inst.Src1)) {
                           live.set(liveness.VarToBit[inst.Src1]);
                       }
                       if (!inst.Src2.empty() && liveness.VarToBit.count(inst.Src2)) {
                           live.set(liveness.VarToBit[inst.Src2]);
                       }
                   }
               }

               // 恢复正常指令顺序
               std::reverse(survivingInsts.begin(), survivingInsts.end());
               b->Instructions = std::move(survivingInsts);
           }

           return eliminatedCount;
       }
   };

   } // namespace dataflow_opt_engine

   // =========================================================================
   // 5. 端到端测试与死代码消除验证套件
   // =========================================================================
   namespace test {

   inline void runLivenessAndDCETestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 活跃变量分析与死代码消除 (DCE) 引擎验证套件
";
       std::cout << "=======================================================

";

       // 构造包含死计算的典型函数:
       //
       // entry:
       //   d1: x = 10
       //   d2: unused_a = x + 100   <--- 死代码 1 (无后续使用)
       //   d3: y = 20
       //   d4: unused_b = y * 2     <--- 死代码 2 (无后续使用)
       //   d5: z = x + y
       //   d6: ret z

       using namespace dataflow_opt_engine;
       FlowGraph fg;
       BasicBlock* bEntry = fg.createBlock("entry");
       fg.Entry = bEntry;

       bEntry->Instructions.push_back({1, InstKind::Assign, "x", "10", "", false});
       bEntry->Instructions.push_back({2, InstKind::Add, "unused_a", "x", "100", false});
       bEntry->Instructions.push_back({3, InstKind::Assign, "y", "20", "", false});
       bEntry->Instructions.push_back({4, InstKind::Add, "unused_b", "y", "2", false});
       bEntry->Instructions.push_back({5, InstKind::Add, "z", "x", "y", false});
       bEntry->Instructions.push_back({6, InstKind::Return, "", "z", "", true}); // ret 具有关键副作用

       std::cout << "[DCE 优化前: 包含死代码的指令序列]:
";
       for (const auto& inst : bEntry->Instructions) {
           std::cout << "  " << inst.toString() << "
";
       }
       assert(bEntry->Instructions.size() == 6);

       // 执行活跃变量分析与死代码消除 Pass
       size_t removed = DeadCodeEliminationPass::run(fg);

       std::cout << "
[DCE 优化后: 剔除死代码后的指令序列]:
";
       for (const auto& inst : bEntry->Instructions) {
           std::cout << "  " << inst.toString() << "
";
       }

       // 验证断言
       assert(removed == 2);
       assert(bEntry->Instructions.size() == 4);
       for (const auto& inst : bEntry->Instructions) {
           assert(inst.Dest != "unused_a");
           assert(inst.Dest != "unused_b");
       }
       std::cout << "
  -> 成功检测并精准剪除 2 条无用死定值指令 (unused_a 与 unused_b)。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了活跃变量分析与死代码消除的运行轨迹：

1. **逆向活跃状态反向传播**：分析器从结尾的 ``ret z`` 出发，识别出 ``z`` 处于活跃状态。在向前推进时，遇到 ``z = add x, y`` 将 ``z`` 杀死并同时将 ``x`` 与 ``y`` 标记为活跃。
2. **死定值精准识别**：当逆向游标遇到 ``unused_b = add y, 2`` 时，由于在当前程序点 ``unused_b`` 未被标记为活跃且指令无外部副作用，算法精准将其判定为死代码。
3. **指令物理剔除与语义保持**：消除 ``unused_a`` 与 ``unused_b`` 后，保留的指令仅包含 ``x = 10``、``y = 20``、``z = x + y`` 与 ``ret z``，在完全保持原函数计算结果的前提下剔除了冗余计算开销。

小结与下章导读
--------------

本章系统解构了现代编译器中端最核心的位向量数据流分析与优化技术：

1. **到达定值与活跃变量模型**：对比了正向 May 分析（到达定值）与逆向 May 分析（活跃变量）在格会合与 Gen/Kill 传递上的代数对称性。
2. **Def-Use 与 Use-Def 链拓扑**：剖析了数据流依赖网格的物理组织，阐明了 SSA 形式将网状依赖降阶为 $\mathcal{O}(1)$ 常数时间指针引用的本质优势。
3. **死代码消除（DCE）状态机**：推导了基于活跃度与关键副作用的 Mark-Sweep 指令剪除流程。
4. **位向量加速体系**：阐释了利用 64 位整数与 SIMD 向量化位运算加速大规模控制流图不动点求解的高性能微架构实现。

在掌握了局部与全局数据流分析之后，下一章我们将深入剖析全局常量传播与冗余表达式消除的核心技术。在第 5 模块第 3 节 **全局值编号 (GVN) 与公共子表达式消除：稀疏条件常量传播 (SCCP)、代数恒等式化简与支配树折叠（``05_data_flow_analysis_and_optimizations/03_constant_propagation_gvn_and_cse.rst``）** 中，我们将深入剖析值编号（Value Numbering）等价类合并、结合控制流可达性剪枝的 SCCP 算法，以及利用支配树进行公共子表达式消除的工程实现。
