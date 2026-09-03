====================================================================================================
LLVM 基础设施与 PassManager：模块化管线、PreservedAnalyses 缓存与 opt/FileCheck 实战
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 8 模块第 5 节（``08_linking_runtime_vms_and_jit/05_jit_compilation_tiered_execution_and_deoptimization``）中，我们深入剖析了运行时分层 JIT 编译流水线、基于内联缓存（IC）的推测特化、Guard 守卫以及去优化（Deopt）与栈上替换（OSR）的物理机制。随着编译系统由专用运行时向通用大型工业级基础设施拓展，编译器必须面对由数以千计的分析与转换阶段构成的复杂优化管线。
   现代工业级编译器基础设施（以 LLVM 为代表）将中端优化建立在精细解耦的对象模型与模块化调度系统之上。本章系统解构 LLVM New Pass Manager（NPM）的物理拓扑，剖析 ``Module -> CGSCC -> Function -> Loop`` 四级 IR 粒度适配机制、基于 CRTP 静态多态与值语义的 Pass 调度架构、层次化 AnalysisManager 的事实缓存与 ``PreservedAnalyses`` 状态机，并深入解析动态 Pass 插件注入、``opt`` 驱动流水线及基于 FileCheck 的编译器自动化回归测试工程。

LLVM IR 内存对象图与 IR 粒度分层拓扑
------------------------------------

LLVM 中端优化器操作的核心实体是由 C++ 对象构成的双向引用内存图。优化管线的输入与输出呈现为以模块（Module）为顶层容器、以指令（Instruction）和 SSA 值为叶子节点的层级拓扑。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       LLVM IR 四级粒度层次化内存拓扑                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ Module (顶层编译单元 / 容器) ]                                          |
   |     - TargetTriple (目标架构三元组) / DataLayout (内存排布规则)             |
   |     - GlobalVariable 列表 (全局符号与常量池)                                |
   |     - NamedMDNode 列表 (模块级元数据)                                       |
   |     - Function 列表                                                         |
   |          |                                                                  |
   |          v                                                                  |
   |   [ CGSCC (调用图强连通分量 Call Graph Strongly Connected Component) ]      |
   |     - 互递归或环形调用函数子集 {Func_A, Func_B}                             |
   |     - 底层支撑跨函数内联决策与过程间属性推导 (IP-Analysis)                  |
   |          |                                                                  |
   |          v                                                                  |
   |   [ Function (函数控制流容器) ]                                             |
   |     - Argument 列表 (函数形参 SSA 值)                                       |
   |     - AttributeSet (调用约定、内存效应属性)                                 |
   |     - BasicBlock 列表 (双向链表组织的控制流基本块)                          |
   |          |                                                                  |
   |          v                                                                  |
   |   [ Loop (循环拓扑单元 / 由 LoopInfo 识别) ]                                |
   |     - Loop Header / Latch / Exiting / Exit 基本块子集                       |
   |     - 循环嵌套深度 (Loop Nest Level) 与归纳变量描述                         |
   |          |                                                                  |
   |          v                                                                  |
   |   [ BasicBlock (单入口单出口指令序列) ]                                     |
   |     - Instruction 侵入式双向链表 (ilist<Instruction>)                       |
   |     - TerminatorInst (唯一结尾跳转/返回指令，维护 CFG 前驱后继边)           |
   |          |                                                                  |
   |          v                                                                  |
   |   [ Instruction & Use-Def 拓扑 ]                                            |
   |     - Value 基类 (具备 Use 链表，支持 O(1) 遍历所有使用者)                  |
   |     - User 基类 (具备 Operand 数组，支持 O(1) 访问所有操作数)               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Pass 粒度选择原则与作用域边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译器优化动作被封装为独立的 Pass 单元。选择合适的 IR 粒度直接决定了 Pass 所需分析事实的开销以及改写造成的缓存失效扩散半径：

.. list-table:: LLVM New Pass Manager 四级 IR 粒度物理特性与调度边界
   :widths: 14 18 26 22 20
   :header-rows: 1
   :class: tight-table

   * - IR 粒度
     - 核心输入类型
     - 典型分析事实
     - 典型改写动作
     - 缓存失效扩散范围
   * - **ModulePass**
     - ``Module &M``
     - 全局符号可见性、死全局变量、模块级元数据
     - 跨模块函数内联、死函数剔除、全局变量压缩
     - 全局所有层级分析缓存
   * - **CGSCCPass**
     - ``LazyCallGraph::SCC &C``
     - 调用图环路特征、自递归边界、参数别名逃逸
     - 局部相互内联、函数参数属性特化、去虚拟化
     - SCC 内部及调用相关分析
   * - **FunctionPass**
     - ``Function &F``
     - 支配树（DomTree）、活跃变量、别名集、循环森林
     - 指令化简（InstCombine）、死代码消除（DCE）、SROA
     - 仅当前函数级分析缓存
   * - **LoopPass**
     - ``Loop &L``
     - 循环迭代次数（TripCount）、标量演进（SCEV）、循环不变量
     - 循环旋转（Rotate）、循环展开（Unroll）、LICM 外提
     - 仅当前循环及内层循环分析

适配器（Adaptor）机制与嵌套管线构建
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当高层管线调度低层 Pass 时，PassManager 必须依赖**适配器（Pass Adaptor）**进行上下文转换。例如，``ModuleToFunctionPassAdaptor`` 遍历当前 Module 中的每一个定义函数，依次对每个函数独立运行内嵌的 ``FunctionPassManager``：

.. code-block:: text

   [ ModulePassManager ]
           |
           +--> [ GlobalOptPass (ModulePass) ]
           |
           +--> [ ModuleToFunctionPassAdaptor ]
                     |
                     v
             [ FunctionPassManager ]  (针对 Module 内每个 Function 循环执行)
                     |
                     +--> [ SROAPass (FunctionPass) ]
                     +--> [ InstCombinePass (FunctionPass) ]
                     +--> [ FunctionToLoopPassAdaptor ]
                               |
                               v
                       [ LoopPassManager ]  (针对 Function 内每个 Loop 循环执行)
                               |
                               +--> [ LICMPass (LoopPass) ]
                               +--> [ LoopRotatePass (LoopPass) ]

适配器模式将 Pass 严格约束在所声明的 IR 作用域内，杜绝了低层 Pass 越权访问外层未受保护结构的隐患。

New Pass Manager 架构与静态多态设计
-----------------------------------

LLVM 早期采用的 Legacy Pass Manager 依赖 C++ 虚函数继承体系（``class FunctionPass : public Pass``），存在全局静态单例状态管理混乱、虚函数调用开销以及 Analysis 与 Transform 强耦合等设计缺陷。New Pass Manager（NPM）重构为**基于 CRTP（Curiously Recurring Template Pattern，奇异递归模板模式）的静态多态与概念驱动模型（Concept/Model Idiom）**。

PassInfoMixin 骨架与接口契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 NPM 中，Pass 表现为常规结构体，通过继承 ``llvm::PassInfoMixin<DerivedT>`` 获得名字查询与类型反射能力，并实现统一的 ``run()`` 成员函数：

.. code-block:: cpp

   #include "llvm/IR/PassManager.h"
   #include "llvm/IR/Function.h"
   #include "llvm/IR/Instructions.h"

   namespace my_compiler {

   class ArithmeticIdentitySimplifyPass : public llvm::PassInfoMixin<ArithmeticIdentitySimplifyPass> {
   public:
       // 统一的执行接口：接收当前 IR 单元与对应的 AnalysisManager
       llvm::PreservedAnalyses run(llvm::Function &F, llvm::FunctionAnalysisManager &FAM) {
           bool Modified = false;
           // 遍历 BasicBlock 与 Instruction 执行优化
           for (auto &BB : F) {
               for (auto InstIt = BB.begin(), InstEnd = BB.end(); InstIt != InstEnd; ) {
                   llvm::Instruction &I = *InstIt++;
                   // 匹配 add X, 0 并进行常数消除
                   if (I.getOpcode() == llvm::Instruction::Add) {
                       if (auto *ConstOp = llvm::dyn_cast<llvm::ConstantInt>(I.getOperand(1))) {
                           if (ConstOp->isZero()) {
                               I.replaceAllUsesWith(I.getOperand(0));
                               I.eraseFromParent();
                               Modified = true;
                           }
                       }
                   }
               }
           }
           
           if (!Modified) {
               return llvm::PreservedAnalyses::all();
           }
           
           // 仅修改了指令，保持控制流图 CFG 拓扑完整
           llvm::PreservedAnalyses PA;
           PA.preserveSet<llvm::CFGAnalyses>();
           return PA;
       }
   };

   } // namespace my_compiler

PassBuilder 与默认优化流水线组装
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``llvm::PassBuilder`` 是构建与配置完整优化管线的核心工厂。它负责注册各层级的 AnalysisManager、绑定跨层代理，并根据预设的优化等级（如 ``-O1``, ``-O2``, ``-O3``, ``-Os``, ``-Oz``）或文本流水线描述构造嵌套管线：

.. code-block:: cpp

   #include "llvm/Passes/PassBuilder.h"

   void executeOptimizationPipeline(llvm::Module &M) {
       // 1. 实例化四级 AnalysisManager
       llvm::LoopAnalysisManager LAM;
       llvm::FunctionAnalysisManager FAM;
       llvm::CGSCCAnalysisManager CGAM;
       llvm::ModuleAnalysisManager MAM;

       // 2. 实例化 PassBuilder 并注册标准分析
       llvm::PassBuilder PB;
       PB.registerModuleAnalyses(MAM);
       PB.registerCGSCCAnalyses(CGAM);
       PB.registerFunctionAnalyses(FAM);
       PB.registerLoopAnalyses(LAM);

       // 3. 建立跨层分析代理 (Proxy)，打通层级失效传播链路
       PB.crossRegisterProxies(LAM, FAM, CGAM, MAM);

       // 4. 构建模块级 -O2 默认优化管线
       llvm::ModulePassManager MPM = PB.buildPerModuleDefaultPipeline(llvm::OptimizationLevel::O2);

       // 5. 驱动管线执行
       MPM.run(M, MAM);
   }

AnalysisManager 缓存拓扑与跨层代理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AnalysisManager 充当分析结果的集中缓存中心。当 Transform Pass 需要依赖特定分析时，通过 ``FAM.getResult<DominatorTreeAnalysis>(F)`` 检索结果。若缓存命中且有效，直接返回已有对象的常数时间引用；若未命中或已失效，则自动触发计算并置入缓存。

为了支持外层 Pass（如 ModulePass）查询内层分析（如 Function 级 DominatorTree），LLVM 引入了**分析代理（Analysis Proxy）**机制：
- ``OuterAnalysisManagerProxy``：允许内层 Pass 向上查询外层分析。
- ``InnerAnalysisManagerProxy``：允许外层 Pass 深度遍历内层分析缓存，并在外层发生破坏性修改时，定向清空指定子单元的失效缓存。

PreservedAnalyses 契约与分析失效状态机
--------------------------------------

编译器优化的运行效率高度依赖分析事实的复用。如果每个 Pass 执行完毕后都将全局分析清空重算，整个编译期的算法复杂度将迅速劣化为二次方或三次方级数。**PreservedAnalyses 是 Transform Pass 向 AnalysisManager 递交的事实有效性声明契约**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  PreservedAnalyses 契约解析与失效流转状态机                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ Transform Pass 执行完毕 ]                                               |
   |              |                                                              |
   |              v                                                              |
   |   [ 生成 PreservedAnalyses 声明 ]                                           |
   |              |                                                              |
   |              +---> (情况 A: 未执行任何修改) -------------------------------+|
   |              |     - 返回 PreservedAnalyses::all()                         ||
   |              |     - 行为: 保留该 IR 单元的所有缓存事实                    ||
   |              |                                                             ||
   |              +---> (情况 B: 仅修改指令操作数/代数化简，CFG 保持原状) ------+||
   |              |     - 返回 PA.preserveSet<CFGAnalyses>()                    |||
   |              |     - 行为: 保留 DominatorTree / LoopInfo 等控制流分析;     |||
   |              |             强制使 AliasAnalysis / MemorySSA 等值依赖失效   |||
   |              |                                                             |||
   |              +---> (情况 C: 重构控制流图 / 增删基本块 / 劈开关键边) -------+||||
   |              |     - 方案 1: 保守返回 PreservedAnalyses::none()             ||||
   |              |     - 方案 2: 使用 DomTreeUpdater 增量更新并声明:           ||||
   |              |               PA.preserve<DominatorTreeAnalysis>()          ||||
   |              |                                                             ||||
   |              v                                                             vvvv
   |   [ AnalysisManager 接收声明并执行过滤 (Invalidation) ]                     |
   |     - 遍历当前 IR 单元已缓存的所有 AnalysisResult                           |
   |     - 判定该 Result 是否处于 Preserved 集合中                               |
   |     - 对未被保留的 Result 执行析构与内存释放                                |
   |     - 后续 Pass 再次请求该分析时按需重新触发计算                            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

常见 IR 改写动作与分析保留矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 典型编译器改写动作对各类分析事实的保留与失效矩阵
   :widths: 25 18 18 20 19
   :header-rows: 1
   :class: tight-table

   * - 改写动作
     - DominatorTree
     - LoopInfo
     - BasicAliasAnalysis
     - 推荐 Preservation 声明
   * - **只读分析 / 统计输出**
     - 保持有效
     - 保持有效
     - 保持有效
     - ``PreservedAnalyses::all()``
   * - **常量折叠 / 代数恒等化简**
     - 保持有效
     - 保持有效
     - 保持有效
     - ``PA.preserveSet<CFGAnalyses>()``
   * - **死指令消除（DCE）**
     - 保持有效
     - 保持有效
     - 保持有效
     - ``PA.preserveSet<CFGAnalyses>()``
   * - **分支折叠（条件跳转转无条件）**
     - 失效 (需更新)
     - 失效 (需更新)
     - 保持有效
     - ``PreservedAnalyses::none()``
   * - **循环旋转（LoopRotate）**
     - 失效 (需更新)
     - 保持有效 (维护后)
     - 保持有效
     - 显式声明已维护项
   * - **临界边分割（SplitCriticalEdge）**
     - 保持有效 (增量更新)
     - 保持有效 (增量更新)
     - 保持有效
     - 配合 ``DomTreeUpdater`` 保留

增量分析维护与 DomTreeUpdater
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于高频的基础控制流改写，完全丢弃 DominatorTree 会导致后续优化 Pass 触发昂贵的重新遍历。LLVM 提供了 ``llvm::DomTreeUpdater`` 机制，通过记录基本的边插入（``InsertEdge``）与边删除（``DeleteEdge``）操作，在改写局部执行细粒度的支配树拓扑缝合，从而安全保留支配分析结果：

.. code-block:: cpp

   #include "llvm/Analysis/DomTreeUpdater.h"

   void splitEdgeAndUpdateAnalyses(llvm::BasicBlock *FromBB, 
                                   llvm::BasicBlock *ToBB, 
                                   llvm::BasicBlock *NewBB, 
                                   llvm::DominatorTree &DT) {
       llvm::DomTreeUpdater DTU(DT, llvm::DomTreeUpdater::UpdateStrategy::Eager);
       
       // 记录边变化：删除旧边 (FromBB -> ToBB)，插入两条新边
       DTU.applyUpdates({{llvm::DominatorTree::Delete, FromBB, ToBB},
                         {{llvm::DominatorTree::Insert, FromBB, NewBB}},
                         {{llvm::DominatorTree::Insert, NewBB, ToBB}}});
   }

动态 Pass 插件体系与 opt 工具链实战
-----------------------------------

LLVM 提供了动态加载插件机制，允许开发者在无需重新编译整个 LLVM 工具链的前提下，将自定义 Pass 动态注入到核心优化管线中。

插件导出协议与宏规范
~~~~~~~~~~~~~~~~~~~~

Pass 插件必须导出遵循 C 链接规范的入口函数 ``llvmGetPassPluginInfo()``，向宿主加载器提供 API 版本与流水线解析回调：

.. code-block:: cpp

   #include "llvm/Passes/PassPlugin.h"
   #include "llvm/Passes/PassBuilder.h"

   extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo llvmGetPassPluginInfo() {
       return {
           LLVM_PLUGIN_API_VERSION,
           "ArithmeticSimplifyPlugin",
           LLVM_VERSION_STRING,
           [](llvm::PassBuilder &PB) {
               // 1. 注册文本管道解析回调：支持 -passes=arithmetic-simplify 命令行参数
               PB.registerPipelineParsingCallback(
                   [](llvm::StringRef Name, llvm::FunctionPassManager &FPM,
                      llvm::ArrayRef<llvm::PassBuilder::PipelineElement>) {
                       if (Name == "arithmetic-simplify") {
                           FPM.addPass(my_compiler::ArithmeticIdentitySimplifyPass());
                           return true;
                       }
                       return false;
                   });

               // 2. 注册标准流水线扩展点：在 Peephole 优化阶段自动注入
               PB.registerPeepholeEPCallback(
                   [](llvm::FunctionPassManager &FPM, llvm::OptimizationLevel Level) {
                       FPM.addPass(my_compiler::ArithmeticIdentitySimplifyPass());
                   });
           }
       };
   }

opt 工具链驱动与诊断指令集
~~~~~~~~~~~~~~~~~~~~~~~~~~

编译生成的动态链接库（``.so`` 或 ``.dylib``）通过 LLVM 优化器驱动程序 ``opt`` 加载执行：

.. code-block:: bash

   # 1. 动态加载插件并指定自定义 Pass 运行，将输出转换为人类可读的汇编 IR (-S)
   opt -load-pass-plugin=./libArithmeticSimplifyPlugin.dylib \
       -passes="function(arithmetic-simplify)" \
       -S input.ll -o output.ll

   # 2. 观察 PassManager 内部详细执行顺序、适配器调用及分析缓存命中状态
   opt -load-pass-plugin=./libArithmeticSimplifyPlugin.dylib \
       -passes="default<O2>" \
       -debug-pass-manager \
       -S input.ll -o /dev/null

   # 3. 在每个 Pass 执行完毕后强行插入 IR Verifier 校验，拦截破坏 SSA 契约的非法改写
   opt -load-pass-plugin=./libArithmeticSimplifyPlugin.dylib \
       -passes="function(arithmetic-simplify)" \
       -verify-each \
       -S input.ll -o output.ll

FileCheck 与 lit 自动化回归测试工程
-----------------------------------

编译器优化的正确性不能仅仅依赖返回值断言，而必须对**IR 结构在转换过程中的微观形态演变进行确定性模式匹配**。LLVM 构建了由 ``lit``（LLVM Integrated Tester）驱动器与 ``FileCheck`` 断言匹配器构成的黄金测试工程标准。

FileCheck 核心指令体系
~~~~~~~~~~~~~~~~~~~~~~

FileCheck 从标准输入读取编译器输出的文本流，并与测试源文件中的注释断言指令进行逐行或跨行匹配：

.. list-table:: FileCheck 核心指令集语法与匹配语义
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 指令语法
     - 匹配约束
     - 工业工程使用场景
   * - ``CHECK: <pattern>``
     - 自当前位置向下顺序查找首个匹配行
     - 匹配关键指令或计算结果是否存在
   * - ``CHECK-NEXT: <pat>``
     - 必须紧邻上一匹配行的下一有效行匹配
     - 断言严格的指令布局、基本块前缀与顺序执行
   * - ``CHECK-NOT: <pat>``
     - 在前后两个正向匹配锚点之间绝对禁止出现
     - 断言死代码已被彻底消除、无冗余指令残留
   * - ``CHECK-LABEL: <pat>``
     - 建立独立的函数或结构体作用域隔离锚点
     - 防止多函数测试用例之间变量捕获发生跨界串扰
   * - ``CHECK-SAME: <pat>``
     - 必须在当前匹配行的同一物理行内继续匹配
     - 验证单条指令携带的修饰符、对齐属性或元数据
   * - ``CHECK-COUNT-N: <pat>``
     - 严格连续匹配恰好 N 次
     - 验证循环完全展开后的指令发射数量

SSA 变量正则捕获与跨行约束实战
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以下展示一份标准的自包含 LLVM IR 回归测试文件（``test/Transforms/arith-simplify.ll``）：

.. code-block:: llvm

   ; RUN: opt -load-pass-plugin=%libdir/libArithmeticSimplifyPlugin%shlibext \
   ; RUN:     -passes="function(arithmetic-simplify)" -S %s | FileCheck %s

   ; -----------------------------------------------------------------------------
   ; 测试用例 1: 验证 add %x, 0 被正确化简为直接返回 %x (正向匹配与 SSA 捕获)
   ; -----------------------------------------------------------------------------
   ; CHECK-LABEL: define i32 @test_add_zero_elimination(i32 %x)
   ; CHECK-NEXT:  entry:
   ; CHECK-NOT:     add i32
   ; CHECK-NEXT:    ret i32 %x
   define i32 @test_add_zero_elimination(i32 %x) {
   entry:
     %sum = add i32 %x, 0
     ret i32 %sum
   }

   ; -----------------------------------------------------------------------------
   ; 测试用例 2: 验证多指令链条中的变量重绑定与指令清除
   ; -----------------------------------------------------------------------------
   ; CHECK-LABEL: define i32 @test_chained_add(i32 %a, i32 %b)
   ; CHECK-NEXT:  entry:
   ; CHECK-NEXT:    [[SUM_AB:%.*]] = add i32 %a, %b
   ; CHECK-NOT:     add i32 [[SUM_AB]], 0
   ; CHECK-NEXT:    ret i32 [[SUM_AB]]
   define i32 @test_chained_add(i32 %a, i32 %b) {
   entry:
     %t1 = add i32 %a, %b
     %t2 = add i32 %t1, 0
     ret i32 %t2
   }

   ; -----------------------------------------------------------------------------
   ; 负例测试用例 3: 验证非零常量加法绝对保持原状 (防止优化边界过度扩张)
   ; -----------------------------------------------------------------------------
   ; CHECK-LABEL: define i32 @test_add_nonzero_retained(i32 %x)
   ; CHECK-NEXT:  entry:
   ; CHECK-NEXT:    [[RES:%.*]] = add i32 %x, 5
   ; CHECK-NEXT:    ret i32 [[RES]]
   define i32 @test_add_nonzero_retained(i32 %x) {
   entry:
     %res = add i32 %x, 5
     ret i32 %res
   }

C++ 工业级 PassManager 与 Analysis 缓存微内核实战
-------------------------------------------------

为了彻底阐明 LLVM New Pass Manager 的底层调度机制与事实失效流转，以下给出一套自包含、无外部依赖的 C++ 现代编译器 PassManager 与 Analysis 缓存微内核实现：
1. **轻量级 SSA IR 体系**：实现 ``Function``、``BasicBlock`` 与 ``Instruction`` 的所属拓扑与 Use-Def 绑定。
2. **DominatorTree 分析器**：实现基于控制流图（CFG）的支配树计算与缓存。
3. **PreservedAnalyses 与 Invalidation 状态机**：支持 ``all()``、``none()`` 及 ``preserveSet<CFGAnalyses>()``。
4. **FunctionPassManager 调度器**：按序调度执行 Pass 并执行失效通知。
5. **配套测试套件**：验证 Pass 执行前后支配分析缓存的命中、保留与按需重算逻辑。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <typeindex>
   #include <cassert>
   #include <algorithm>

   namespace mini_llvm {

   // =========================================================================
   // 1. 基础 IR 拓扑模型 (Instruction, BasicBlock, Function)
   // =========================================================================
   enum class Opcode {
       Add,
       Sub,
       Br,
       CondBr,
       Ret
   };

   struct BasicBlock;

   struct Instruction {
       Opcode Op;
       std::string ResultVar;
       std::vector<std::string> Operands;
       BasicBlock* ParentBB = nullptr;

       Instruction(Opcode op, std::string res, std::vector<std::string> ops)
           : Op(op), ResultVar(std::move(res)), Operands(std::move(ops)) {}
   };

   struct BasicBlock {
       std::string Name;
       std::vector<std::unique_ptr<Instruction>> Instructions;
       std::vector<BasicBlock*> Predecessors;
       std::vector<BasicBlock*> Successors;

       explicit BasicBlock(std::string name) : Name(std::move(name)) {}

       void addInstruction(std::unique_ptr<Instruction> inst) {
           inst->ParentBB = this;
           Instructions.push_back(std::move(inst));
       }
   };

   struct Function {
       std::string Name;
       std::vector<std::unique_ptr<BasicBlock>> BasicBlocks;

       explicit Function(std::string name) : Name(std::move(name)) {}

       BasicBlock* createBasicBlock(const std::string& name) {
           BasicBlocks.push_back(std::make_unique<BasicBlock>(name));
           return BasicBlocks.back().get();
       }
   };

   // =========================================================================
   // 2. 支配树分析结构 (DominatorTree)
   // =========================================================================
   class DominatorTree {
   public:
       std::unordered_map<std::string, std::string> IDom; // BB Name -> Immediate Dominator Name
       uint64_t ComputationEpoch = 0;

       void recalculate(const Function& F, uint64_t epoch) {
           IDom.clear();
           ComputationEpoch = epoch;
           if (F.BasicBlocks.empty()) return;

           // 简化模拟: 根节点支配自身，后继节点由前驱直接支配
           IDom[F.BasicBlocks[0]->Name] = F.BasicBlocks[0]->Name;
           for (size_t i = 1; i < F.BasicBlocks.size(); ++i) {
               IDom[F.BasicBlocks[i]->Name] = F.BasicBlocks[i - 1]->Name;
           }
       }

       bool dominates(const std::string& a, const std::string& b) const {
           std::string curr = b;
           while (true) {
               if (curr == a) return true;
               auto it = IDom.find(curr);
               if (it == IDom.end() || it->second == curr) break;
               curr = it->second;
           }
           return false;
       }
   };

   // =========================================================================
   // 3. PreservedAnalyses 契约与 AnalysisManager
   // =========================================================================
   struct CFGAnalysesTag {};

   class PreservedAnalyses {
   private:
       bool PreservedAll = false;
       std::unordered_set<std::type_index> PreservedIDs;
       bool PreservedCFGSet = false;

   public:
       static PreservedAnalyses all() {
           PreservedAnalyses PA;
           PA.PreservedAll = true;
           return PA;
       }

       static PreservedAnalyses none() {
           return PreservedAnalyses();
       }

       template <typename AnalysisT>
       void preserve() {
           PreservedIDs.insert(std::type_index(typeid(AnalysisT)));
       }

       template <typename AnalysisSetT>
       void preserveSet() {
           if (std::is_same<AnalysisSetT, CFGAnalysesTag>::value) {
               PreservedCFGSet = true;
           }
       }

       template <typename AnalysisT>
       bool isPreserved() const {
           if (PreservedAll) return true;
           if (std::is_same<AnalysisT, DominatorTree>::value && PreservedCFGSet) return true;
           return PreservedIDs.count(std::type_index(typeid(AnalysisT))) > 0;
       }
   };

   class FunctionAnalysisManager {
   private:
       std::unique_ptr<DominatorTree> CachedDomTree;
       uint64_t CurrentEpoch = 1;

   public:
       uint64_t CacheHits = 0;
       uint64_t Recomputations = 0;

       DominatorTree& getDominatorTree(const Function& F) {
           if (CachedDomTree) {
               CacheHits++;
               return *CachedDomTree;
           }
           Recomputations++;
           CachedDomTree = std::make_unique<DominatorTree>();
           CachedDomTree->recalculate(F, CurrentEpoch);
           return *CachedDomTree;
       }

       void invalidate(const Function& F, const PreservedAnalyses& PA) {
           CurrentEpoch++;
           if (!PA.isPreserved<DominatorTree>()) {
               CachedDomTree.reset(); // 丢弃失效分析缓存
           }
       }
   };

   // =========================================================================
   // 4. Pass 接口与调度器 (FunctionPassManager)
   // =========================================================================
   class FunctionPass {
   public:
       virtual ~FunctionPass() = default;
       virtual std::string getName() const = 0;
       virtual PreservedAnalyses run(Function& F, FunctionAnalysisManager& FAM) = 0;
   };

   class FunctionPassManager {
   private:
       std::vector<std::unique_ptr<FunctionPass>> Pipeline;

   public:
       void addPass(std::unique_ptr<FunctionPass> pass) {
           Pipeline.push_back(std::move(pass));
       }

       void run(Function& F, FunctionAnalysisManager& FAM) {
           for (auto& pass : Pipeline) {
               std::cout << "  >>> [Pass 调度器] 运行 Pass: " << pass->getName() 
                         << " 于函数: " << F.Name << std::endl;
               PreservedAnalyses PA = pass->run(F, FAM);
               FAM.invalidate(F, PA);
           }
       }
   };

   // =========================================================================
   // 5. 示例 Pass 实现
   // =========================================================================

   // Pass A: 指令化简 (保留 CFG)
   class AddZeroEliminationPass : public FunctionPass {
   public:
       std::string getName() const override { return "AddZeroEliminationPass"; }

       PreservedAnalyses run(Function& F, FunctionAnalysisManager& FAM) override {
           // 查询 DomTree (验证分析可正常调取)
           auto& DT = FAM.getDominatorTree(F);
           bool Changed = false;

           for (auto& BB : F.BasicBlocks) {
               auto it = BB->Instructions.begin();
               while (it != BB->Instructions.end()) {
                   if ((*it)->Op == Opcode::Add && (*it)->Operands.size() == 2) {
                       if ((*it)->Operands[1] == "0") {
                           std::cout << "      [优化动作] 消除零加法: " << (*it)->ResultVar 
                                     << " = " << (*it)->Operands[0] << " + 0" << std::endl;
                           it = BB->Instructions.erase(it);
                           Changed = true;
                           continue;
                       }
                   }
                   ++it;
               }
           }

           if (!Changed) {
               return PreservedAnalyses::all();
           }

           // 声明保留 CFG 相关分析 (包括 DominatorTree)
           PreservedAnalyses PA;
           PA.preserveSet<CFGAnalysesTag>();
           return PA;
       }
   };

   // Pass B: 结构性控制流改写 (完全破坏 CFG)
   class CFGDisruptivePass : public FunctionPass {
   public:
       std::string getName() const override { return "CFGDisruptivePass"; }

       PreservedAnalyses run(Function& F, FunctionAnalysisManager& FAM) override {
           std::cout << "      [优化动作] 插入新基本块，重构控制流图拓扑..." << std::endl;
           F.createBasicBlock("synthesized_bb");
           // 控制流已改变且未手动维护 DomTree，返回 none()
           return PreservedAnalyses::none();
       }
   };

   } // namespace mini_llvm

   // =========================================================================
   // 6. 端到端 Pass 调度与分析缓存验证套件
   // =========================================================================
   namespace test {

   inline void runLLVMPassManagerTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " LLVM PassManager 调度架构与 PreservedAnalyses 缓存验证
";
       std::cout << "=======================================================

";

       using namespace mini_llvm;

       // 1. 构建测试函数与基本块
       Function testFunc("@compute_kernel");
       auto* entryBB = testFunc.createBasicBlock("entry");
       auto* loopBB = testFunc.createBasicBlock("loop_body");

       // 添加包含零加法的指令
       entryBB->addInstruction(std::make_unique<Instruction>(
           Opcode::Add, "%x1", std::vector<std::string>{"%arg0", "0"}));
       entryBB->addInstruction(std::make_unique<Instruction>(
           Opcode::Add, "%x2", std::vector<std::string>{"%x1", "10"}));

       FunctionAnalysisManager FAM;

       // 2. 初次计算 DominatorTree 并检验缓存建立
       std::cout << "--- [阶段 1: 首次按需请求 DominatorTree 分析] ---
";
       auto& dt1 = FAM.getDominatorTree(testFunc);
       assert(dt1.dominates("entry", "loop_body"));
       assert(FAM.Recomputations == 1);
       assert(FAM.CacheHits == 0);
       std::cout << "  [分析缓存状态]: 重新计算次数 = " << FAM.Recomputations 
                 << ", 缓存命中次数 = " << FAM.CacheHits << "

";

       // 3. 构建并执行 Pass 管线
       std::cout << "--- [阶段 2: 运行保持 CFG 的指令化简 Pass] ---
";
       FunctionPassManager FPM;
       FPM.addPass(std::make_unique<AddZeroEliminationPass>());
       FPM.run(testFunc, FAM);

       // 4. 再次请求 DominatorTree，断言命中缓存 (未发生重算)
       auto& dt2 = FAM.getDominatorTree(testFunc);
       assert(FAM.Recomputations == 1);
       assert(FAM.CacheHits == 2); // Pass 内部查询 1 次 + 本次查询 1 次
       std::cout << "  [分析缓存验证]: 指令化简成功声明 preserveSet<CFGAnalyses>，DomTree 缓存成功复用!
";
       std::cout << "  [分析缓存状态]: 重新计算次数 = " << FAM.Recomputations 
                 << ", 缓存命中次数 = " << FAM.CacheHits << "

";

       // 5. 运行破坏 CFG 的 Pass
       std::cout << "--- [阶段 3: 运行破坏 CFG 的结构转换 Pass] ---
";
       FunctionPassManager DisruptiveFPM;
       DisruptiveFPM.addPass(std::make_unique<CFGDisruptivePass>());
       DisruptiveFPM.run(testFunc, FAM);

       // 6. 再次请求 DominatorTree，断言缓存已失效并触发重新计算
       std::cout << "--- [阶段 4: 校验失效后按需重算机制] ---
";
       auto& dt3 = FAM.getDominatorTree(testFunc);
       assert(FAM.Recomputations == 2);
       std::cout << "  [分析失效验证]: 控制流改写成功触发 Invalidation，DomTree 按需正确重算!
";
       std::cout << "  [最终缓存统计]: 重新计算总计 = " << FAM.Recomputations 
                 << ", 缓存命中总计 = " << FAM.CacheHits << "

";

       std::cout << "=======================================================
";
       std::cout << " LLVM PassManager 架构与分析缓存状态机测试全量通过!
";
       std::cout << "=======================================================
";
   }

   } // namespace test

小结与下章导读
--------------

本章系统解构了现代工业级编译器中端基础设施的基石——LLVM New Pass Manager（NPM）：
1. **层次化 IR 粒度模型**：剖析了 ``Module -> CGSCC -> Function -> Loop`` 四级单元的内存拓扑，阐明了适配器（Adaptor）在高低层管线嵌套调度中的作用域约束。
2. **基于 CRTP 的静态多态体系**：解构了 ``PassInfoMixin``、``PassBuilder`` 与四级 AnalysisManager 的依赖解耦机制。
3. **PreservedAnalyses 契约与失效状态机**：形式化分析了只读分析、局部代数化简与控制流破坏对分析事实有效性的边界，推导了 ``DomTreeUpdater`` 增量维护的性能优势。
4. **插件化工程与 FileCheck 测试体系**：深入解析了 ``opt`` 动态插件加载协议与基于 SSA 变量捕获的黄金回归测试工程标准。

随着异构计算（GPU、NPU、TPU、DSP）与领域特定计算（AI 张量图、量子计算、图形着色器）的爆发式发展，单一扁平、指令级抽象过低的传统 LLVM IR 在表达高维张量循环嵌套、多面体模型以及硬件特化语义时面临严重的语义降级间隙。在下一章中，我们将步入现代编译器领域的革新架构——**MLIR（Multi-Level Intermediate Representation）多层中间表示**，深入剖析其 Dialect 扩展哲学、Operation/Region/Block 统一图拓扑以及从高层张量到低层 LLVM IR 的渐进降级（Progressive Lowering）流水线。
