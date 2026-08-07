第029章：IR Verification and Structural Invariants
===================================================

核心知识点
----------

* IR 能被解析或打印，只说明文本/对象可构造；verifier 继续检查它是否满足后续 pass 可以信任的结构不变量。
* 常见 IR 不变量包括 CFG 完整性、basic block 合法 terminator、SSA 定义支配使用、``phi``/block argument 与前驱一致、类型一致性、符号存在性和 operation 专属约束。
* Dominance 保证普通 SSA value 在所有到达使用点的路径上都有合法定义；控制流合流处需要 ``phi`` 或 block argument 明确每条前驱边提供的值。
* Type consistency 要求 operation 的 operand/result 类型、函数签名、分支条件、返回值和内存操作满足当前 IR 的类型合同。
* Verifier 是编译器内部 contract checker，适合在 frontend、lowering 和 transform pass 后检查，帮助把错误定位到真正破坏 IR 的阶段。
* Verifier 证明的是结构合法性；程序语义等价、优化收益和业务正确性仍需要其它分析、测试或证明。

关键路径
--------

``Frontend/Pass -> IR -> Verifier -> next Pass``。

排查 invalid IR 时优先顺序是：先检查 CFG 和 block terminator；再检查 SSA definition/use、dominance 与合流值；然后检查类型、符号和 operation 专属规则。若错误由某个 pass 引入，应保留出错前后的 IR 和最短 pass pipeline。

典型错误包括：删除 block 后 ``phi`` 仍引用旧前驱；某值只在一个分支定义却在合流块普通使用；``i1`` 比较结果被送入 ``phi i32``；basic block 缺少 terminator；调用目标或函数签名不匹配。

概念辨析
--------

* **Parser validity vs verifier validity**：前者确认表示可被读入；后者确认内部图关系和不变量成立。
* **Dominance vs lexical order**：dominance 是 CFG 上所有路径的定义覆盖关系，不能仅靠文本先后判断。
* **Verifier error vs source error**：合法源程序产生 invalid IR，通常意味着 frontend/lowering/pass 的编译器 bug。
* **Structural validity vs semantic equivalence**：两个 IR 都能通过 verifier，仍可能因错误转换而语义不等价。

本章结论
--------

Verifier 把 IR 从“编译器内部数据”提升为有明确合同的可靠表示。任何转换都必须同时维护 CFG、SSA、类型和操作专属不变量；出现 verifier 错误时，应优先追踪最后一个修改这些关系的阶段。