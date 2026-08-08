第124章：Semantic Error Reporting
==================================

核心知识点
----------

* Semantic error 发生在源码结构已经成立之后，常见于 name resolution、type checking、member lookup、overload resolution、visibility 与 generic/template constraints。
* 高质量语义诊断必须能回溯到一个明确失败关系：哪个名字没绑定、哪个类型不兼容、哪个候选被拒绝、哪个约束没有满足。
* Undefined name 的主位置应落在使用点；拼写建议只应来自合理可见范围中的高置信候选。
* Type mismatch 应同时展示 expected 与 actual，并尽量连接到参数、返回值或声明位置，而不是只输出内部类型约束失败。
* Overload/candidate failure 需要先给总体结论，再列少量最相关候选及各自 rejection reason；候选过多时应排序、截断并保留展开入口。
* 候选比较最好使用统一维度，例如 arity、argument type、visibility、generic constraint、calling convention 等，让用户能直接判断应改哪类条件。
* Generic/template error 经常跨 definition、instantiation 与 call site。诊断需要保留“谁触发实例化 → 参数推导成什么 → 内部哪里失败”的路径。
* Macro、template 与 generic context 可能形成很长的上下文栈；默认展示应保留最能解释失败的关键帧，其余细节可折叠。
* Constraint diagnostics 的价值在于把 solver 内部状态翻译成人类关系，例如 ``T = User``、``User does not satisfy Ordered``，而不是泄漏实现术语。
* Precision 与 noise 必须平衡。展示所有候选、全部模板栈和完整内部类型可能 technically complete，却会淹没真正根因。
* Primary diagnostic 应围绕当前可修改源码，related notes 再展示 declaration、candidate、instantiation、macro expansion 等支持证据。
* 语义诊断的核心任务是把 compiler reasoning 翻译成 programmer reasoning，使用户能从失败关系直接推导修复方向。

关键路径
--------

语义诊断链：

::

   AST expression / declaration
   → name lookup
   → type/member/call resolution
   → candidate set + constraint state
   → identify exact failed relation
   → choose primary source range
   → rank relevant candidates/context
   → emit expected/actual or rejection reason
   → attach declaration/instantiation notes
   → offer safe next action if possible

泛型/模板上下文：

::

   user call site
   → infer/substitute type arguments
   → instantiate/check generic body or constraints
   → failure inside instantiated context
   → report trigger site
   → report inferred types
   → report inner failure + required constraint

概念辨析
--------

* **Syntax error 与 semantic error**：前者结构无法成立，后者结构成立但名字、类型或约束关系失败。
* **Name lookup failure 与 overload failure**：前者找不到目标声明，后者找到了候选但没有任何候选可接受当前使用方式。
* **Candidate set 与 selected declaration**：candidate set 是可能目标集合，只有解析成功后才形成唯一或明确的绑定结果。
* **Definition context 与 instantiation context**：泛型错误可能属于定义本身，也可能只在某次具体类型替换后出现。
* **Precision 与 verbosity**：精确表示证据准确，冗长只是信息量大；二者并不等价。

本章结论
--------

语义报错的稳定模型是 ``Failed Semantic Relation → Relevant Candidates/Constraints → Source-Linked Explanation``。优秀诊断不只是重复“类型不匹配”或“没有候选”，而是把名字解析、类型推导和约束求解的失败压缩成用户能直接比较、验证和修改的关系。
