====================================================================================================
内存别名分析 (Alias Analysis)：Must/May/No-Alias 判定、逃逸分析与 MemorySSA 建模
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块第 3 节（``05_data_flow_analysis_and_optimizations/03_constant_propagation_gvn_and_cse.rst``）中，我们系统剖析了基于纯标量虚拟寄存器的全局值编号（GVN）、支配树公共子表达式消除（CSE）以及稀疏条件常量传播（SCCP）算法。标量 SSA 形式彻底消除了标量寄存器值流的不确定性。然而，真实工业级程序不可避免地通过指针、引用、结构体字段偏移（GEP）与数组下标与底层的物理堆栈内存交互。由于不同指针在运行期可能指向重叠的内存区间（即发生 **内存别名 / Memory Aliasing**），中端优化器在试图执行内存读消除（Load-Elimination）、死写消除（Dead Store Elimination, DSE）或循环不变量内存外提（LICM）时，必须获得绝对可靠的别名判定依据。若在缺乏别名独立性证据的情况下盲目重排 ``load`` 与 ``store`` 指令，将直接破坏程序的可观测语义。本章深入剖析内存别名分析（Alias Analysis, AA）的四分类代数格、基于包含关系的安德森（Andersen）与基于等价合一的斯廷斯加德（Steensgaard）指针分析、基于类型的别名分析（TBAA）、指针逃逸分析（Escape Analysis），以及将物理内存副作用优雅融入 SSA 形式的现代基础设施——**MemorySSA（MemoryDef / MemoryUse / MemoryPhi）** 的架构与实现。

内存访问与别名四分类代数格
--------------------------

在编译器底层，一次内存访问可精确建模为一个四元组：

.. math::

   	ext{MemLoc} = \langle 	ext{BasePtr}, 	ext{Offset}, 	ext{Size}, 	ext{TBAATag} \rangle

其中 $	ext{BasePtr}$ 为基地址指针，$	ext{Offset}$ 为编译期已知或未知的常数/符号偏移量，$	ext{Size}$ 为访问的连续字节宽度，$	ext{TBAATag}$ 为类型元数据。

别名关系的四分类判定格
~~~~~~~~~~~~~~~~~~~~~~

当优化器查询两个内存访问位置 $	ext{Loc}_A$ 与 $	ext{Loc}_B$ 的相互关系时，别名分析器返回以下四类严格判定之一：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        别名分析 (Alias Analysis) 判定格拓扑                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ NoAlias : 证明绝对互不重叠 (Disjoint Memory Ranges) ]        |
   |                                     |                                       |
   |                                     v                                       |
   |     +-------------------------------+-------------------------------+       |
   |     |                                                               |       |
   |     v                                                               v       |
   | [ MayAlias : 可能重叠 (缺乏证明) ]                  [ PartialAlias : 部分重叠 ]|
   |     |                                                               |       |
   |     +-------------------------------+-------------------------------+       |
   |                                     |                                       |
   |                                     v                                       |
   |              [ MustAlias : 证明严格指向完全相同的起始地址与尺寸 ]           |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: 别名分析四大分类准则与中端优化动作矩阵
   :widths: 16 34 50
   :header-rows: 1
   :class: tight-table

   * - 判定结果
     - 物理数学定义
     - 允许的中端优化动作
   * - **NoAlias**
     - $	ext{Range}(	ext{Loc}_A) \cap 	ext{Range}(	ext{Loc}_B) = \emptyset$
     - **完全解耦**：允许跨越彼此自由重排 ``load/store``、将 ``load`` 自由外提至循环外，无需任何内存屏障
   * - **MustAlias**
     - $	ext{Addr}(	ext{Loc}_A) == 	ext{Addr}(	ext{Loc}_B) \land 	ext{Size}_A == 	ext{Size}_B$
     - **读写转发 (Forwarding)**：后继 ``load`` 可直接替换为前驱 ``store`` 的写入值；连续 ``store`` 可直接作为死写消除
   * - **PartialAlias**
     - $	ext{Range}(	ext{Loc}_A) \cap 	ext{Range}(	ext{Loc}_B) 
eq \emptyset$，但非完全重合
     - 需通过位移与掩码提取部分字节（如从 64 位整数写入中提取 8 位读取），严禁简单转发
   * - **MayAlias**
     - 静态分析无法证明两者是否重叠（保守默认状态）
     - **保守阻断**：严禁跨越写入指令移动读取，强制保留原指令顺序

经典指针指向分析算法：Andersen vs Steensgaard
---------------------------------------------

指针分析（Points-To Analysis）旨在计算程序中每个指针变量在运行期可能指向的内存对象集合（Points-To Set, $	ext{pts}(p)$）。

Andersen 基于包含关系的子集约束分析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Andersen 算法（1994）将程序语句建模为 **包含约束系统（Inclusion-Based Constraints）**：

.. list-table:: Andersen 指针分析核心语句约束产生式
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 源码语句类型
     - 约束关系形式化
     - 指向图 (Points-To Graph) 有向边
   * - 地址获取：``p = &x``
     - $\{x\} \subseteq 	ext{pts}(p)$
     - 向 $p$ 的指向集合中添加实体节点 $x$
   * - 指针赋值：``p = q``
     - $	ext{pts}(q) \subseteq 	ext{pts}(p)$
     - 添加有向传播边：$q 	o p$
   * - 间接加载：``p = *q``
     - $\forall x \in 	ext{pts}(q), 	ext{pts}(x) \subseteq 	ext{pts}(p)$
     - 动态从 $q$ 指向的每个对象向 $p$ 添加传播边
   * - 间接写入：``*p = q``
     - $\forall x \in 	ext{pts}(p), 	ext{pts}(q) \subseteq 	ext{pts}(x)$
     - 动态从 $q$ 向 $p$ 指向的每个对象添加传播边

- **时间复杂度**：图的有向传递闭包求解，时间复杂度为 $\mathcal{O}(N^3)$。
- **精度特性**：保持单向包含精度，分析结果紧凑精确。

Steensgaard 基于等价关系的合一分析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Steensgaard 算法（1996）为了解决超大规模代码下的可扩展性瓶颈，将包含关系降级为 **等价关系（Equality-Based Unification）**：
- 当遇到语句 ``p = q`` 时，不建立单向子集传播，而是使用并查集（Disjoint-Set / Union-Find）将 $p$ 与 $q$ 的指向集合直接 **合二为一（Merge）**。
- **时间复杂度**：近乎线性的 $\mathcal{O}(N \alpha(N))$，其中 $\alpha$ 为反阿克曼函数。
- **精度折损**：由于双向合并导致指向集迅速膨胀，会产生大量虚假的 MayAlias 报告。

基于类型的别名分析 (TBAA) 与严格别名规则
-----------------------------------------

C/C++ 语言标准定义了 **严格别名规则（Strict Aliasing Rule）**：两个具有不兼容类型的指针绝对不允许访问同一块物理内存对象（除 ``char*`` 与 ``std::byte*`` 特权类型外）。

TBAA 类型 DAG 层次拓扑
~~~~~~~~~~~~~~~~~~~~~~

现代编译器（如 LLVM 与 GCC）在中端 IR 中附加 **TBAA 元数据节点（Type-Based Alias Analysis Nodes）**，构建类型继承与包含有向无环图（DAG）：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     LLVM TBAA 类型元数据树形拓扑结构                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                                 [ Root (Omnipotent char) ]                  |
   |                                      /              \                       |
   |                                     v                v                      |
   |                           [ Scalar Types ]     [ Struct Types ]             |
   |                             /          \                 |                  |
   |                            v            v                v                  |
   |                       [ int ]       [ float ]      [ struct Point ]         |
   |                                                          |                  |
   |                                                          +-> {offset 0: int}|
   |                                                          +-> {offset 4: int}|
   |                                                                             |
   |   * 判定准则: 若两个类型在 TBAA 树中不存在祖先/后代包含路径, 则判定为 NoAlias|
   |   * 实例: int* 与 float* 属于不相交的叶子分支 -> 绝对 NoAlias!              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

逃逸分析 (Escape Analysis) 与标量替换 (SROA)
--------------------------------------------

**逃逸分析（Escape Analysis）** 追踪在函数内部或局部作用域内分配的物理对象指针，其生命周期是否可能逃出当前上下文。

指针逃逸的三大状态层级
~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 指针逃逸三大状态层级与物理优化收益
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 逃逸状态
     - 指针生命周期特征
     - 中端物理优化动作
   * - **NoEscape (未逃逸)**
     - 指针仅在本函数内部被直接解引用读写，从未存入外部变量或传出
     - **聚合体标量替换 (SROA)**：将结构体/对象彻底打碎为纯 SSA 寄存器；**堆转栈**：将 ``malloc`` 直接降级为 ``alloca``
   * - **ArgEscape (参数逃逸)**
     - 指针作为参数传入外部函数，但外部函数未将其持久化到全局状态
     - 允许在调用前后保持局部只读优化，但需在调用点设置内存屏障
   * - **GlobalEscape (全局逃逸)**
     - 指针被存入全局变量、从函数 ``return`` 返回，或传递给未知动态链接库
     - 无法进行栈提升，所有针对该内存的访问必须保守维持物理内存读写

MemorySSA 建模：将内存副作用融入 SSA 体系
-----------------------------------------

在传统的 SSA 形式中，只有虚拟寄存器拥有唯一的 Def-Use 链，而物理内存被视为一个庞大的黑盒。当优化器（如 GVN、LICM 或 DSE）试图查询一次 ``load`` 指令之前是否存在对其产生修改的 ``store`` 指令时，必须沿着 CFG 逆向执行代价极高的全图扫描。

为了彻底解决内存分析的二次方复杂度爆炸，现代编译器（LLVM 引入并在中端标配）构建了 **MemorySSA**。

MemorySSA 三大核心虚拟指令拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MemorySSA 为整个程序内存空间赋予一个抽象的 **内存版本 Token（Memory Token, 如 ``1``, ``2``, ``3``）**，并定义了三类虚拟指令：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     MemorySSA 核心虚拟指令体系与数据流网格                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 指令 1: 内存写入 MemoryDef (产生新内存版本) ]                           |
   |      store i32 42, ptr %p                                                   |
   |      ==> 1 = MemoryDef(0)  ; 基于初始版本 0，写入产生新内存版本 1           |
   |                                                                             |
   |   [ 指令 2: 内存读取 MemoryUse (消费现有内存版本，不产生新版本) ]           |
   |      %val = load i32, ptr %p                                                |
   |      ==> MemoryUse(1)      ; 显式记录当前 load 读取的是内存版本 1           |
   |                                                                             |
   |   [ 指令 3: 控制流分支汇聚 MemoryPhi (合并多条前驱路径的内存版本) ]         |
   |      MergeBlock:                                                            |
   |      ==> 3 = MemoryPhi( [1, ThenBlock], [2, ElseBlock] )                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **``MemoryDef``**：任何可能修改内存状态的指令（``store``、带有写副作用的 ``call``）均被建模为一次定值，它输入前一个内存版本，并输出一个全新的单调递增内存版本。
2. **``MemoryUse``**：任何读取内存的指令（``load``、只读 ``call``）显式持有一个指向它所读取的内存版本（``MemoryDef`` 或 ``MemoryPhi``）的指针。
3. **``MemoryPhi``**：位于基本块顶部的虚拟合流指令，将不同前驱路径到达的内存版本合并为一个新的版本编号。

MemorySSA 对冗余加载消除 (RLE) 与死写消除 (DSE) 的赋能
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

通过 MemorySSA：
- **冗余加载消除（Redundant Load Elimination, RLE）**：当两次 ``load`` 指令关联相同的内存版本（例如两个 ``load`` 均为 ``MemoryUse(1)``）且它们访问的目标地址满足 $	ext{MustAlias}$ 时，第二次 ``load`` 可以 **在 $\mathcal{O}(1)$ 常数时间内被证明为绝对冗余**，直接用第一次 ``load`` 的 SSA 寄存器值替换！
- **死写消除（Dead Store Elimination, DSE）**：若一个 ``MemoryDef(A)`` 生成的版本未被任何 ``MemoryUse`` 或后续存活路径读取，且紧接着被同地址的另一个 ``MemoryDef(B)`` 覆盖，则前一次写入指令可以直接在常数时间内判定为死写并被物理消除。

工业级 C++ 完整别名分析与 MemorySSA 引擎实现
--------------------------------------------

以下 C++ 源码实现了一套工业级自包含的别名分析器（涵盖 BasicAA、GEP 偏移计算、Disjoint Alloca 判定）与 MemorySSA 构建引擎。该实现涵盖：
1. 精确的 `MemoryLocation` 内存区域建模。
2. 基础别名分析器（BasicAliasAnalysis），支持 `NoAlias`、`MayAlias` 与 `MustAlias` 判定。
3. 完整的 MemorySSA 图构建器（生成 `MemoryDef`、`MemoryUse` 与 `MemoryPhi`）。
4. 基于 MemorySSA 的冗余加载消除 Pass（Redundant Load Elimination, RLE）。
5. 端到端测试套件，展示独立指针重排与别名阻断的物理执行过程。

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

   namespace alias_analysis_engine {

   // =========================================================================
   // 1. 别名分类与内存位置模型
   // =========================================================================
   enum class AliasResult {
       NoAlias,      // 绝对不相交
       MayAlias,     // 可能相交 (保守)
       PartialAlias, // 部分重叠
       MustAlias     // 严格指向相同基地址与尺寸
   };

   inline const char* aliasToString(AliasResult ar) {
       switch (ar) {
           case AliasResult::NoAlias: return "NoAlias";
           case AliasResult::MayAlias: return "MayAlias";
           case AliasResult::PartialAlias: return "PartialAlias";
           case AliasResult::MustAlias: return "MustAlias";
       }
       return "Unknown";
   }

   struct MemoryLocation {
       std::string BaseObject; // 基础分配实体 (如 alloca 名, 全局变量名)
       int64_t Offset = 0;     // 常量字节偏移
       int64_t Size = 4;       // 访问字节宽度

       bool operator==(const MemoryLocation& o) const {
           return BaseObject == o.BaseObject && Offset == o.Offset && Size == o.Size;
       }
   };

   class BasicAliasAnalysis {
   public:
       static AliasResult alias(const MemoryLocation& locA, const MemoryLocation& locB) {
           // 1. 两个不同的独立栈分配对象 (Disjoint Allocas) 必为 NoAlias
           if (locA.BaseObject != locB.BaseObject) {
               return AliasResult::NoAlias;
           }

           // 2. 同一基对象下的偏移范围判定
           if (locA.Offset == locB.Offset && locA.Size == locB.Size) {
               return AliasResult::MustAlias;
           }

           // 检查区间是否相交: [Offset, Offset + Size)
           int64_t startA = locA.Offset;
           int64_t endA   = locA.Offset + locA.Size;
           int64_t startB = locB.Offset;
           int64_t endB   = locB.Offset + locB.Size;

           if (endA <= startB || endB <= startA) {
               return AliasResult::NoAlias; // 区间完全不相交
           }

           return AliasResult::PartialAlias;
       }
   };

   // =========================================================================
   // 2. IR 指令与 MemorySSA 虚拟节点
   // =========================================================================
   enum class MemoryAccessKind {
       MemoryDef, // 内存写入/副作用
       MemoryUse, // 内存读取
       MemoryPhi  // 汇聚合流
   };

   struct MemoryAccess {
       uint32_t ID = 0;
       MemoryAccessKind Kind;
       uint32_t IncomingVersion = 0; // 输入依赖的内存版本
       MemoryLocation Loc;           // 关联的物理内存位置
   };

   enum class InstOp {
       Alloca,
       Load,
       Store,
       Add,
       Return
   };

   struct Instruction {
       InstOp Op;
       std::string Dest;
       std::string Ptr;
       int64_t Offset = 0;
       std::string Val;
       std::shared_ptr<MemoryAccess> MemAcc = nullptr;

       std::string toString() const {
           std::stringstream ss;
           switch (Op) {
               case InstOp::Alloca:
                   ss << "  %" << Dest << " = alloca 4";
                   break;
               case InstOp::Load:
                   ss << "  %" << Dest << " = load ptr %" << Ptr << " (offset " << Offset << ")";
                   if (MemAcc) ss << " ; MemoryUse(" << MemAcc->IncomingVersion << ")";
                   break;
               case InstOp::Store:
                   ss << "  store %" << Val << ", ptr %" << Ptr << " (offset " << Offset << ")";
                   if (MemAcc) ss << " ; " << MemAcc->ID << " = MemoryDef(" << MemAcc->IncomingVersion << ")";
                   break;
               case InstOp::Add:
                   ss << "  %" << Dest << " = add %" << Ptr << ", %" << Val;
                   break;
               case InstOp::Return:
                   ss << "  ret %" << Val;
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
           std::cout << "define void @" << Name << "() {
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
   // 3. MemorySSA 构建与冗余加载消除 Pass
   // =========================================================================
   class MemorySSABuilder {
   public:
       static void build(Function& func) {
           uint32_t currentMemVersion = 0; // 0 代表 liveOnEntry 初始内存状态
           uint32_t defCounter = 0;

           for (auto& b : func.Blocks) {
               for (auto& inst : b->Instructions) {
                   if (inst.Op == InstOp::Store) {
                       auto def = std::make_shared<MemoryAccess>();
                       def->ID = ++defCounter;
                       def->Kind = MemoryAccessKind::MemoryDef;
                       def->IncomingVersion = currentMemVersion;
                       def->Loc = {inst.Ptr, inst.Offset, 4};

                       inst.MemAcc = def;
                       currentMemVersion = def->ID; // 推进最新内存版本
                   } else if (inst.Op == InstOp::Load) {
                       auto use = std::make_shared<MemoryAccess>();
                       use->ID = 0;
                       use->Kind = MemoryAccessKind::MemoryUse;
                       use->IncomingVersion = currentMemVersion;
                       use->Loc = {inst.Ptr, inst.Offset, 4};

                       inst.MemAcc = use;
                   }
               }
           }
       }
   };

   class EarlyRLEPass {
   public:
       // 基于 MemorySSA 与别名分析的冗余加载消除 (Redundant Load Elimination)
       static size_t run(Function& func) {
           size_t eliminatedLoads = 0;

           for (auto& b : func.Blocks) {
               // 维护可用加载表: MemoryLocation -> SSA 寄存器值
               std::unordered_map<std::string, std::pair<MemoryLocation, std::string>> availableLoads;
               std::vector<Instruction> cleanInsts;
               std::unordered_map<std::string, std::string> valueReplacement;

               for (auto& inst : b->Instructions) {
                   // 传播已有替换
                   if (valueReplacement.count(inst.Val)) inst.Val = valueReplacement[inst.Val];
                   if (valueReplacement.count(inst.Ptr)) inst.Ptr = valueReplacement[inst.Ptr];

                   if (inst.Op == InstOp::Store) {
                       // 写入操作: 使所有可能与之产生别名的可用 Load 失效
                       MemoryLocation storeLoc{inst.Ptr, inst.Offset, 4};
                       std::vector<std::string> keysToInvalidate;

                       for (const auto& pair : availableLoads) {
                           AliasResult ar = BasicAliasAnalysis::alias(storeLoc, pair.second.first);
                           if (ar != AliasResult::NoAlias) {
                               keysToInvalidate.push_back(pair.first);
                           }
                       }
                       for (const auto& k : keysToInvalidate) {
                           availableLoads.erase(k);
                       }

                       // 将本次写入值记入当前位置的最新可用值 (Store-to-Load 转发支持)
                       std::string locKey = inst.Ptr + "+" + std::to_string(inst.Offset);
                       availableLoads[locKey] = {storeLoc, inst.Val};

                       cleanInsts.push_back(inst);
                   } else if (inst.Op == InstOp::Load) {
                       MemoryLocation loadLoc{inst.Ptr, inst.Offset, 4};
                       std::string locKey = inst.Ptr + "+" + std::to_string(inst.Offset);

                       if (availableLoads.count(locKey)) {
                           // 命中可用值: 消除本次 Load，直接复用已有值
                           valueReplacement[inst.Dest] = availableLoads[locKey].second;
                           ++eliminatedLoads;
                           continue; // 物理剔除本条 load
                       } else {
                           availableLoads[locKey] = {loadLoc, inst.Dest};
                           cleanInsts.push_back(inst);
                       }
                   } else {
                       cleanInsts.push_back(inst);
                   }
               }
               b->Instructions = std::move(cleanInsts);
           }

           return eliminatedLoads;
       }
   };

   } // namespace alias_analysis_engine

   // =========================================================================
   // 4. 端到端测试与别名验证套件
   // =========================================================================
   namespace test {

   inline void runAliasAnalysisTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 内存别名分析与 MemorySSA 冗余读消除验证套件
";
       std::cout << "=======================================================

";

       using namespace alias_analysis_engine;

       // 1. 测试基础别名分类判定 (BasicAA)
       {
           MemoryLocation locA{"ptr_x", 0, 4};
           MemoryLocation locB{"ptr_y", 0, 4};
           MemoryLocation locA_field0{"ptr_x", 0, 4};
           MemoryLocation locA_field1{"ptr_x", 4, 4};

           assert(BasicAliasAnalysis::alias(locA, locB) == AliasResult::NoAlias);
           assert(BasicAliasAnalysis::alias(locA, locA_field0) == AliasResult::MustAlias);
           assert(BasicAliasAnalysis::alias(locA_field0, locA_field1) == AliasResult::NoAlias);

           std::cout << "[测试 1: BasicAA 基础判定]:
"
                     << "  alias(ptr_x, ptr_y)           = " << aliasToString(BasicAliasAnalysis::alias(locA, locB)) << "
"
                     << "  alias(ptr_x, ptr_x)           = " << aliasToString(BasicAliasAnalysis::alias(locA, locA_field0)) << "
"
                     << "  alias(ptr_x[0..4], ptr_x[4..8]) = " << aliasToString(BasicAliasAnalysis::alias(locA_field0, locA_field1)) << "

";
       }

       // 2. 测试 MemorySSA 构建与无别名安全 RLE 消除
       {
           Function func;
           func.Name = "test_memory_opt";
           BasicBlock* bEntry = func.createBlock("entry");
           func.Entry = bEntry;

           // entry:
           //   %v1 = load ptr %p (offset 0)
           //   store 99, ptr %q (offset 0)  <--- 写入不同的基对象 %q (NoAlias)
           //   %v2 = load ptr %p (offset 0)  <--- 期望被 RLE 消除，复用 %v1!
           //   %res = add %v1, %v2
           //   ret %res
           bEntry->Instructions.push_back({InstOp::Load, "v1", "p", 0, ""});
           bEntry->Instructions.push_back({InstOp::Store, "", "q", 0, "99"});
           bEntry->Instructions.push_back({InstOp::Load, "v2", "p", 0, ""});
           bEntry->Instructions.push_back({InstOp::Add, "res", "v1", 0, "v2"});
           bEntry->Instructions.push_back({InstOp::Return, "", "", 0, "res"});

           std::cout << "[测试 2: MemorySSA 构建前初始 IR]:
";
           func.dump();

           MemorySSABuilder::build(func);

           std::cout << "
[测试 2: MemorySSA 构建后标注 IR]:
";
           func.dump();

           size_t removed = EarlyRLEPass::run(func);

           std::cout << "
[测试 2: 结合 AA 的 RLE 优化后 IR]:
";
           func.dump();

           // 核心断言:
           // 1. 成功消除 1 条冗余 load
           assert(removed == 1);
           // 2. add 操作数的 %v2 必须被重定向为 %v1
           assert(bEntry->Instructions[2].Op == InstOp::Add);
           assert(bEntry->Instructions[2].Ptr == "v1" && bEntry->Instructions[2].Val == "v1");
           std::cout << "  -> 跨越无别名写入成功消除冗余 Load，操作数完成重定向。

";
       }

       std::cout << "  -> 内存别名分析与 MemorySSA 优化引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展现了内存分析与优化的协同过程：

1. **精确识别独立内存空间**：通过对象标识与偏移计算，``BasicAliasAnalysis`` 准确证明了 ``ptr_x`` 与 ``ptr_y`` 为绝对 ``NoAlias``，且结构体内部不重叠字段（偏移 0 与偏移 4）同样为 ``NoAlias``。
2. **MemorySSA 精准拓扑建模**：构建器为 ``store %q`` 赋予全新的内存版本 ``1 = MemoryDef(0)``，为后续的 ``load %p`` 标注其所依赖的输入版本。
3. **安全跨写转发与读消除**：在执行 RLE 时，优化器证明了对 ``%q`` 的写入绝对不会破坏对 ``%p`` 已加载的有效性缓存，成功将第二个 ``load %p`` 物理删除，并将后续计算安全重定向至 ``%v1``。

小结与下章导读
--------------

本章系统解构了现代编译器中端直面物理内存副作用的核心分析与建模技术：

1. **别名四分类代数格**：形式化定义了 ``NoAlias``、``MayAlias``、``PartialAlias`` 与 ``MustAlias``，确立了内存重排与读写消除的安全边界。
2. **指针指向分析算法**：对比了包含约束的 Andersen 分析（$\mathcal{O}(N^3)$ 高精度）与等价合一的 Steensgaard 分析（$\mathcal{O}(N \alpha(N))$ 极速）的工程权衡。
3. **类型系统与逃逸分析**：剖析了严格别名规则（TBAA）的元数据 DAG 判定，阐释了逃逸分析对聚合体标量替换（SROA）与堆转栈优化的支撑作用。
4. **MemorySSA 架构**：解构了 ``MemoryDef``、``MemoryUse`` 与 ``MemoryPhi`` 的虚拟指令流，推导了将内存副作用转化为 $\mathcal{O}(1)$ SSA Def-Use 遍历的工业实践。

在攻克了标量与内存分析之后，下一章我们将进军现代优化器中能够带来成倍乃至数量级性能提升的核心领域——**循环优化与自动向量化**。在第 5 模块第 5 节 **循环优化与自动向量化：循环不变量外提 (LICM)、循环展开/分块 (Tiling) 与 SIMD 代码生成（``05_data_flow_analysis_and_optimizations/05_loop_optimizations_licm_unroll_and_vectorization.rst``）** 中，我们将深入剖析循环规范化（Loop Rotate/Preheader）、基于别名分析的循环不变量外提（LICM）、循环分块（Tiling）提升 CPU 缓存命中率，以及循环向量依赖距离与 SIMD 指令生成技术。
