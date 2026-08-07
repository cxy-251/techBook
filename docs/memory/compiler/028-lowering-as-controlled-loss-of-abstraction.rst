第028章：Lowering as Controlled Loss of Abstraction
====================================================

核心知识点
----------

* Lowering 是把高层表示逐步转换为更基础表示的过程，本质是受控地减少抽象，同时增加更明确的执行约束。
* ``for``、``if``、数组访问、闭包、异常、泛型和对象等高层结构，会逐步拆成 basic block、branch、SSA value、address calculation、load/store 和 runtime call。
* Lowering 可以改变表示形状，必须保持程序可观察语义：求值顺序、控制路径、数据依赖、内存效果、异常行为和语言规定的类型语义都属于可能的不变量。
* 每次 lowering 都会丢失一部分源码形态，因此必须在丢失前完成依赖该信息的分析，或通过 metadata 保留后续仍需要的证据。
* 大型编译器通常采用 progressive lowering，让每一阶段只处理一组明确约束，而不是一次从 AST 直接落到机器码。
* Lowering 完成后，新 IR 必须满足目标层结构规则；verification 是检查转换是否至少生成合法内部表示的重要手段。

关键路径
--------

``AST -> High-Level IR -> Structured IR -> CFG/SSA IR -> Low-Level IR -> Machine IR``。

以循环为例，源码中的初始化、条件、循环体和步进先保留为结构化循环，随后拆为 header/body/latch/exit 等 block；数组下标进一步变成地址计算与 load，局部可变变量则可转换成 SSA value 与 ``phi``/block argument。

分析 lowering 时固定三步：先列出源抽象表达的语义；再确认目标层用哪些操作、边和值承载这些语义；最后检查转换后是否保持关键不变量并通过 verifier。

概念辨析
--------

* **Lowering vs optimization**：lowering 的目标是改变抽象层级；optimization 的目标是在同等语义下改善性能或代码质量。
* **信息丢失 vs 语义丢失**：源码形态可以消失；影响可观察行为的语义不能被错误删除。
* **High-level operation vs primitive operations**：一个高层节点通常会扩展成多个更窄、约束更明确的低层操作。
* **Debug mapping**：源码节点与低层指令往往不是一一对应，需要 source location/debug metadata 维持调试关联。

本章结论
--------

Lowering 是编译器把程序员友好抽象转成机器可承担约束的核心机制。正确的 lowering 允许表示越来越低层，同时让必须保持的语义始终能在目标层找到明确证据。