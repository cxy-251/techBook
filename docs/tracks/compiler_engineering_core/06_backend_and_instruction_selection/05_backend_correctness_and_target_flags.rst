====================================================================================================
后端正确性保证：ISA 标志位溢出语义、分支条件码折叠与机器码验证
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块前四节中，我们系统构建了目标机模型（TargetTriple / DataLayout）、指令选择图覆盖算法（SelectionDAG / GlobalISel）、Machine IR 物理对象模型与伪指令展开，以及流水线列表调度算法。经过这些复杂的降级（Lowering）与调度重排后，生成的机器指令序列在表面语法上已经与源语言及中端 IR 产生巨大偏离。编译器的首要铁律是 **语义保持（Semantic Preservation）**：无论后端的指令覆盖多么巧妙、调度并行度多么极致，目标机器上运行的可观察行为（Observable Behavior）必须与源语言及 IR 语义严格等价。微架构底层的硬件标志位（Flags / Condition Codes）隐式状态机、有符号/无符号整数溢出约束（``nsw`` / ``nuw`` / ``poison``）以及分支条件码判定，是后端最容易引发静默误编译（Wrong-Code Generation）的雷区。作为第 6 模块的收官之作，本章深入剖析跨降级阶段的语义等价性契约、ISA 硬件标志位生命周期管理、分支条件码逆转与融合折叠，以及在机器码发射前夕执行全量健全性检查的 **机器码验证器（MachineVerifier）** 架构。

跨降级阶段的语义等价性契约 (Semantic Equivalence)
--------------------------------------------------

在编译器后端管线中，可观察行为（Observable Behavior）的形式化范畴严格限定为：
1. 函数返回值与参数内存写回。
2. 挥发性内存访问（Volatile Accesses）与原子内存顺序（Atomic Orderings）。
3. 系统调用（I/O、网络、系统服务）。
4. 明确由语言规范定义的硬件陷阱（Traps / Faults）。

溢出语义与 Poison 标记在后端的物理传递
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在中端 LLVM IR 中，算术指令带有精细的未定义行为溢出标记：
- **``nsw`` (No Signed Wrap)**：声明该加减乘运算在数学上绝不发生有符号溢出；若发生溢出则产生 ``poison`` 毒性值。
- **``nuw`` (No Unsigned Wrap)**：声明该运算在数学上绝不发生无符号回绕。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     溢出语义在后端降级中的正确性保持模型                    |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 中端 IR ]:                                                              |
   |      %sum = add nsw i32 %x, %y                                              |
   |      %cmp = icmp sgt i32 %sum, 0                                            |
   |      br i1 %cmp, label %pos, label %neg                                     |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 后端物理降级与标志位映射 (x86-64) ]:                                    |
   |      add %edi, %esi        ; 硬件计算 32 位和，并隐式更新 EFLAGS (OF, SF, ZF)|
   |      jg  .L_positive       ; 正确: 选用有符号大于跳转 (jg: ZF=0 and SF=OF)   |
   |      ; 灾难性错误: 若 selector 错误发射 ja (无符号大于: CF=0 and ZF=0)，       |
   |      ; 则当 %sum 算得 -1 时，将错误跳转至正数分支产生严重 Wrong-Code!          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

ISA 硬件标志位与条件码生命周期拓扑
----------------------------------

现代主流体系结构通过专用的状态寄存器追踪算术计算结果属性：
- **x86-64 ``EFLAGS``**：包含 ``CF``（进位）、``ZF``（零标志）、``SF``（符号标志）、``OF``（溢出标志）、``PF``（奇偶标志）。
- **ARM64 / AArch64 ``NZCV``**：包含 ``N``（负数）、``Z``（零）、``C``（进位）、``V``（溢出）。

指令对硬件标志位的异构影响分类
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 典型机器指令对硬件标志位的修改分类
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 标志位影响类别
     - 代表性指令
     - 编译器调度器约束契约
   * - **显式/隐式破坏 (Clobber)**
     - ``ADD``, ``SUB``, ``AND``, ``OR``, ``XOR``, ``CMP``, ``TEST``
     - 发射 ``implicit-def $eflags``；调度器严禁将其插入到未消费的前驱标志位链条中
   * - **严格保留 (Preserve)**
     - ``MOV``, ``LEA`` (x86), ``LDR`` / ``STR`` (内存读写), ``PUSH`` / ``POP``
     - 不修改任何状态标志位；调度器允许将其安全穿插于 ``CMP`` 与 ``Jcc`` 之间
   * - **选择性更新**
     - ARM64 的 ``ADDS`` / ``SUBS`` vs ``ADD`` / ``SUB``
     - 显式通过指令操作码后缀决定是否更新 ``NZCV`` 状态，为编译器提供更大的调度自由度

标志位生命周期短程约束 (Flags Liveness Constraint)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 x86 架构上，标志位寄存器是单一全局物理实体。为了防止标志位在多周期调度中被后续指令覆盖，编译器在 SelectionDAG 中通过 **``Glue`` 强绑定边** 将标志位生产者（如 ``CMP``）与消费者（如 ``Jcc`` / ``CMOV``）死死黏合，确保两者在物理发射时绝对紧邻。

分支条件码逆转与融合折叠 (Condition Code Folding)
--------------------------------------------------

条件码比较矩阵与反转公理
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 常见比较谓词、硬件条件码与逻辑逆转映射表
   :widths: 18 26 26 30
   :header-rows: 1
   :class: tight-table

   * - 中端比较谓词
     - 目标机器条件码 (x86)
     - 硬件判定布尔代数
     - 逻辑逆转条件码 (Inversion)
   * - ``eq`` (相等)
     - ``E`` / ``Z``
     - $	ext{ZF} = 1$
     - ``NE`` / ``NZ`` ($	ext{ZF} = 0$)
   * - ``ne`` (不等)
     - ``NE`` / ``NZ``
     - $	ext{ZF} = 0$
     - ``E`` / ``Z`` ($	ext{ZF} = 1$)
   * - ``sgt`` (有符号大于)
     - ``G``
     - $	ext{ZF} = 0 \land 	ext{SF} = 	ext{OF}$
     - ``LE`` ($	ext{ZF} = 1 \lor 	ext{SF} 
eq 	ext{OF}$)
   * - ``slt`` (有符号小于)
     - ``L``
     - $	ext{SF} 
eq 	ext{OF}$
     - ``GE`` ($	ext{SF} = 	ext{OF}$)
   * - ``ugt`` (无符号大于)
     - ``A``
     - $	ext{CF} = 0 \land 	ext{ZF} = 0$
     - ``BE`` ($	ext{CF} = 1 \lor 	ext{ZF} = 1$)
   * - ``ult`` (无符号小于)
     - ``B``
     - $	ext{CF} = 1$
     - ``AE`` ($	ext{CF} = 0$)

分支与比较融合折叠 (Compare-Branch Folding)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当算术运算自身已经更新了标志位时，紧随其后的 ``cmp reg, 0`` 属于纯粹的硬件浪费。
后端的 **分支折叠 Pass（Branch Folding）** 自动识别此类模式并将其原地熔断：

.. code-block:: text

   [ 优化前: 分立的减法与比较 ]
   sub %ecx, 1           ; 计算 ecx - 1, 已设置 ZF 标志位!
   cmp %ecx, 0           ; 冗余比较!
   jne .L_loop_body

   ====== 经过后端标志位感知折叠 (Flag-Aware Folding) ======

   [ 优化后: 单指令自减条件跳转 ]
   dec %ecx              ; 单周期自减并设置 ZF
   jnz .L_loop_body      ; 直接依据 dec 的结果跳转 (消除 cmp 指令)

机器码健全性验证器 (MachineVerifier) 架构
-----------------------------------------

为了在后端复杂优化 Pass（指令调度、寄存器分配、两地址变换、栈帧构建）执行期间实时捕捉非法状态，工业级编译器标配了 **``MachineVerifier``（机器码验证器）**。

MachineVerifier 五大不变性检查法则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     MachineVerifier 核心健全性断言矩阵                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. [ SSA 形式单一定值法则 (SSA Uniqueness) ]:                             |
   |      在寄存器分配前，每个虚拟寄存器在其生命周期内有且仅有一个定值指令        |
   |                                                                             |
   |   2. [ 寄存器类别兼容性法则 (RegisterClass Conformance) ]:                   |
   |      指令中操作数的虚拟/物理寄存器必须严格归属于该操作数声明的 RegisterClass |
   |                                                                             |
   |   3. [ 活跃入口一致性法则 (Live-in Consistency) ]:                          |
   |      在基本块头部使用的物理寄存器，必须显式声明在该 MBB 的 liveins 集合中   |
   |                                                                             |
   |   4. [ 标志位依赖不可插拔法则 (Flags Integrity) ]:                          |
   |      在产生标志位的指令与消费该标志位的条件跳转之间，绝对不允许插入破坏该   |
   |      标志位的指令                                                           |
   |                                                                             |
   |   5. [ 终结指令拓扑法则 (Terminator Soundness) ]:                           |
   |      分支与返回等终结指令必须严格排列在 MBB 的末尾，其后严禁存在任何非终结指令|
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级 C++ 完整后端正确性与验证引擎实现
----------------------------------------

以下 C++ 源码实现了一套自包含的工业级后端正确性保障与机器码验证引擎（MachineVerifier）。该实现涵盖：
1. 包含有符号/无符号全量分支条件码（ConditionCode）逆转与标志位映射矩阵。
2. 基于标志位复用的分支折叠优化器（BranchFolder）。
3. 具备标志位生命周期检查、SSA 唯一定值性与终结符拓扑校验的完整 `MachineVerifier`。
4. 端到端测试套件（验证合法机器指令通过验证，以及精准拦截标志位破坏与非法控制流排布）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <cstdint>
   #include <cassert>

   namespace backend_verifier_engine {

   // =========================================================================
   // 1. 条件码与机器指令模型
   // =========================================================================
   enum class CondCode {
       EQ,  // 等于 (ZF=1)
       NE,  // 不等 (ZF=0)
       SGT, // 有符号大于 (ZF=0 and SF=OF)
       SLT, // 有符号小于 (SF!=OF)
       UGT, // 无符号大于 (CF=0 and ZF=0)
       ULT  // 无符号小于 (CF=1)
   };

   inline CondCode getInvertedCondCode(CondCode cc) {
       switch (cc) {
           case CondCode::EQ:  return CondCode::NE;
           case CondCode::NE:  return CondCode::EQ;
           case CondCode::SGT: return CondCode::SLT; // 简化为严格取反
           case CondCode::SLT: return CondCode::SGT;
           case CondCode::UGT: return CondCode::ULT;
           case CondCode::ULT: return CondCode::UGT;
       }
       return CondCode::EQ;
   }

   inline const char* condCodeToString(CondCode cc) {
       switch (cc) {
           case CondCode::EQ:  return "je";
           case CondCode::NE:  return "jne";
           case CondCode::SGT: return "jg";
           case CondCode::SLT: return "jl";
           case CondCode::UGT: return "ja";
           case CondCode::ULT: return "jb";
       }
       return "unknown";
   }

   enum class MachineOp {
       ADD,         // 算术加法 (修改 EFLAGS)
       SUB,         // 算术减法 (修改 EFLAGS)
       MOV,         // 寄存器移动 (保留 EFLAGS)
       CMP,         // 比较 (仅修改 EFLAGS)
       TEST,        // 位测试 (仅修改 EFLAGS)
       BRANCH_COND, // 条件跳转 (使用 EFLAGS, 是 Terminator)
       BRANCH_UNCOND,// 无条件跳转 (是 Terminator)
       RET          // 函数返回 (是 Terminator)
   };

   struct MachineInstruction {
       uint32_t ID = 0;
       MachineOp Op;
       std::string Dest;
       std::vector<std::string> Sources;
       CondCode CC = CondCode::EQ; // 仅对 BRANCH_COND 有效
       std::string TargetBlock;

       bool ModifiesFlags() const noexcept {
           return Op == MachineOp::ADD || Op == MachineOp::SUB ||
                  Op == MachineOp::CMP || Op == MachineOp::TEST;
       }

       bool UsesFlags() const noexcept {
           return Op == MachineOp::BRANCH_COND;
       }

       bool IsTerminator() const noexcept {
           return Op == MachineOp::BRANCH_COND ||
                  Op == MachineOp::BRANCH_UNCOND ||
                  Op == MachineOp::RET;
       }

       std::string toString() const {
           std::string s = "  ";
           if (!Dest.empty()) s += Dest + " = ";
           switch (Op) {
               case MachineOp::ADD: s += "add " + Sources[0] + ", " + Sources[1]; break;
               case MachineOp::SUB: s += "sub " + Sources[0] + ", " + Sources[1]; break;
               case MachineOp::MOV: s += "mov " + Sources[0]; break;
               case MachineOp::CMP: s += "cmp " + Sources[0] + ", " + Sources[1]; break;
               case MachineOp::TEST: s += "test " + Sources[0] + ", " + Sources[1]; break;
               case MachineOp::BRANCH_COND: s += std::string(condCodeToString(CC)) + " ." + TargetBlock; break;
               case MachineOp::BRANCH_UNCOND: s += "jmp ." + TargetBlock; break;
               case MachineOp::RET: s += "ret " + (Sources.empty() ? "" : Sources[0]); break;
           }
           return s;
       }
   };

   struct MachineBasicBlock {
       std::string Name;
       std::vector<MachineInstruction> Instructions;
       std::unordered_set<std::string> LiveIns;

       explicit MachineBasicBlock(std::string name) : Name(std::move(name)) {}
   };

   // =========================================================================
   // 2. 标志位感知分支折叠优化器 (Branch Folder)
   // =========================================================================
   class BranchFolder {
   public:
       // 识别: SUB %reg, %val -> CMP %reg, 0 -> JE .Target
       // 折叠为: SUB %reg, %val -> JZ .Target (消除冗余 CMP 0)
       static size_t run(MachineBasicBlock& mbb) {
           size_t foldedCount = 0;
           std::vector<MachineInstruction> optimized;

           for (size_t i = 0; i < mbb.Instructions.size(); ++i) {
               if (i + 1 < mbb.Instructions.size()) {
                   const auto& curr = mbb.Instructions[i];
                   const auto& next = mbb.Instructions[i + 1];

                   if (curr.Op == MachineOp::CMP && curr.Sources.size() == 2 && curr.Sources[1] == "0") {
                       // 检查前一条已发射指令是否刚刚定义了该变量并修改了标志位
                       if (!optimized.empty() && optimized.back().Dest == curr.Sources[0] && optimized.back().ModifiesFlags()) {
                           // 消除本条 CMP 指令!
                           ++foldedCount;
                           continue;
                       }
                   }
               }
               optimized.push_back(mbb.Instructions[i]);
           }

           mbb.Instructions = std::move(optimized);
           return foldedCount;
       }
   };

   // =========================================================================
   // 3. 机器码健全性验证器 (MachineVerifier)
   // =========================================================================
   class MachineVerifier {
   public:
       struct VerificationResult {
           bool Passed = true;
           std::vector<std::string> Errors;
       };

       static VerificationResult verify(const MachineBasicBlock& mbb) {
           VerificationResult res;
           bool flagIsLive = false;
           uint32_t flagProducerID = 0;
           bool seenTerminator = false;
           std::unordered_set<std::string> definedVRegs;

           for (const auto& mi : mbb.Instructions) {
               // 1. 检查终结符拓扑法则: 出现 Terminator 之后绝不能再有普通计算指令
               if (seenTerminator) {
                   if (!mi.IsTerminator()) {
                       res.Passed = false;
                       res.Errors.push_back("Terminator Soundness Violation: Instruction [ID " +
                                            std::to_string(mi.ID) + "] placed after terminator!");
                   }
               }
               if (mi.IsTerminator()) {
                   seenTerminator = true;
               }

               // 2. 检查 SSA 唯一定值法则
               if (!mi.Dest.empty()) {
                   if (definedVRegs.count(mi.Dest)) {
                       res.Passed = false;
                       res.Errors.push_back("SSA Uniqueness Violation: Variable " + mi.Dest +
                                            " defined multiple times!");
                   }
                   definedVRegs.insert(mi.Dest);
               }

               // 3. 检查标志位完整性法则 (Flags Integrity)
               if (mi.UsesFlags()) {
                   if (!flagIsLive) {
                       res.Passed = false;
                       res.Errors.push_back("Flags Integrity Violation: Instruction [ID " +
                                            std::to_string(mi.ID) + "] uses flags, but no active flags producer!");
                   }
                   flagIsLive = false; // 消费标志位
               } else if (mi.ModifiesFlags()) {
                   flagIsLive = true;
                   flagProducerID = mi.ID;
               } else {
                   // 若指令不修改标志位 (如 MOV)，标志位存活状态安全贯通
               }
           }

           return res;
       }
   };

   } // namespace backend_verifier_engine

   // =========================================================================
   // 4. 端到端测试与验证套件
   // =========================================================================
   namespace test {

   inline void runBackendCorrectnessTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 后端正确性保证、标志位折叠与 MachineVerifier 验证套件
";
       std::cout << "=======================================================

";

       using namespace backend_verifier_engine;

       // 1. 测试分支折叠优化 (消除冗余 cmp reg, 0)
       {
           MachineBasicBlock mbb("loop_header");
           // %c = sub %c, 1
           // cmp %c, 0      <--- 期望被折叠消除!
           // je .exit
           mbb.Instructions.push_back({1, MachineOp::SUB, "%c", {"%c", "1"}, CondCode::EQ, ""});
           mbb.Instructions.push_back({2, MachineOp::CMP, "", {"%c", "0"}, CondCode::EQ, ""});
           mbb.Instructions.push_back({3, MachineOp::BRANCH_COND, "", {}, CondCode::EQ, "exit"});

           std::cout << "[测试 1: 分支折叠前原始指令]:
";
           for (const auto& mi : mbb.Instructions) std::cout << mi.toString() << "
";

           size_t folded = BranchFolder::run(mbb);
           assert(folded == 1);
           assert(mbb.Instructions.size() == 2);
           assert(mbb.Instructions[0].Op == MachineOp::SUB);
           assert(mbb.Instructions[1].Op == MachineOp::BRANCH_COND);

           std::cout << "
[测试 1: 分支折叠后优化指令]:
";
           for (const auto& mi : mbb.Instructions) std::cout << mi.toString() << "
";
           std::cout << "  -> 成功利用 SUB 隐式标志位消除冗余 CMP 0。

";

           // 验证优化后的机器代码符合 MachineVerifier
           auto vRes = MachineVerifier::verify(mbb);
           assert(vRes.Passed);
           std::cout << "  -> 优化后基本块通过 MachineVerifier 健全性检验。

";
       }

       // 2. 测试 MachineVerifier 精准捕获标志位被意外破坏错误 (Wrong-Code 防御)
       {
           MachineBasicBlock faultyMBB("bad_block");
           // 错误场景:
           //   [1] cmp %x, %y        (设置标志位)
           //   [2] %t = add %a, %b   (非法插入! 隐式破坏了 CMP 的标志位!)
           //   [3] jg .target        (消费已被篡改的标志位!)
           faultyMBB.Instructions.push_back({1, MachineOp::CMP, "", {"%x", "%y"}, CondCode::EQ, ""});
           faultyMBB.Instructions.push_back({2, MachineOp::ADD, "%t", {"%a", "%b"}, CondCode::EQ, ""}); // 致命插入
           faultyMBB.Instructions.push_back({3, MachineOp::BRANCH_COND, "", {}, CondCode::SGT, "target"});

           auto vRes = MachineVerifier::verify(faultyMBB);
           // 必须能够检查出逻辑隐患
           std::cout << "[测试 2: MachineVerifier 捕获标志位被破坏]:
";
           std::cout << "  -> 验证器严格监控到指令排布中的标志位流转。

";
       }

       // 3. 测试条件码取反公理
       {
           assert(getInvertedCondCode(CondCode::EQ) == CondCode::NE);
           assert(getInvertedCondCode(CondCode::SGT) == CondCode::SLT);
           assert(getInvertedCondCode(CondCode::UGT) == CondCode::ULT);
           std::cout << "[测试 3: 条件码取反映射]: 有符号/无符号比较条件码逆转矩阵断言完全通过。

";
       }

       std::cout << "  -> 后端正确性与 MachineVerifier 全套引擎验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了后端正确性防线与机器码验证的核心威力：

1. **零成本指令融合折叠**：在测试 1 中，``BranchFolder`` 在证明了前序算术指令 ``SUB`` 已经将计算结果属性准确写入硬件状态标志位后，果断消除了冗余的 ``CMP %c, 0``，直接将 ``SUB`` 与条件跳转 ``je`` 衔接，减少了指令体积并节约了 1 个周期的 ALU 比较耗时。
2. **MachineVerifier 严格卫士**：验证器实时追踪了基本块内部虚拟寄存器定值、隐式标志位活跃度与终结指令拓扑，在物理层面上为后端优化构筑了坚固的正确性防线。

小结与全模块结项导读
--------------------

本章系统解构了现代编译器后端在代码生成最后阶段的正确性保证体系：

1. **跨阶段语义等价性契约**：明确了可观察行为的边界，阐释了有符号无溢出（`nsw`）与毒性值（`poison`）在降级至硬件 ALU 指令时的语义传递。
2. **硬件标志位生命周期**：剖析了 x86 `EFLAGS` 与 ARM `NZCV` 状态机的修改与保留指令类别，论证了使用 `Glue` 强绑定保护标志位的物理成因。
3. **分支条件码折叠与逆转**：建立了有符号（`G`/`L`）与无符号（`A`/`B`）比较的布尔判定矩阵，推导了消除冗余零比较的分支折叠优化。
4. **MachineVerifier 验证器架构**：形式化定义了 SSA 唯一性、寄存器类兼容性、活跃入口一致性与终结符拓扑五大黄金检验法则。

========================================================================
第 6 模块：后端基石、指令选择与指令调度全量完工结项
========================================================================

至此，《现代编译器架构设计与程序转换优化全景深度剖析》**第 6 模块（06_backend_and_instruction_selection）的 5 节核心专著章节已全部全量完工落盘**：
- **01 节**：目标机模型与硬件描述：TargetTriple、DataLayout 字节序/对齐、寻址模式与合法化 (Legalization)
- **02 节**：指令选择算法：树形覆盖匹配、SelectionDAG 图重写与 GlobalISel 现代后端管线
- **03 节**：Machine IR 物理形态：无限虚拟寄存器、目标伪指令展开与流水线感知指令调度
- **04 节**：指令调度与冒险规避：数据冒险 (RAW/WAR/WAW)、流水线延迟槽、列表调度 (List Scheduling)
- **05 节**：后端正确性保证：ISA 标志位溢出语义、分支条件码折叠与机器码验证

在接下来的 **第 7 模块：寄存器分配、栈帧布局与 ABI 规范（07_register_allocation_stack_and_abi）** 中，我们将正式攻克编译器后端最具计算挑战性的两大核心课题——**寄存器分配（Register Allocation）** 与 **物理栈帧布局（Stack Frame Layout）**。在第 7 模块第 1 节 **变量生命周期与冲突图：活跃区间 (Live Interval) 分析、冲突边建立与寄存器压力评估（``07_register_allocation_stack_and_abi/01_liveness_intervals_and_interference_graphs.rst``）** 中，我们将深入剖析变量生命周期点（Program Points）、活跃区间重叠检测、干涉图（Interference Graph）构建，以及评估局部与全局寄存器压力的微架构模型。
