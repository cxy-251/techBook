第034章：Structured Control Flow vs Unstructured Jumps
======================================================

核心知识点
----------

* 结构化控制流用 ``if``、``while``、``for``、``switch`` 等嵌套语法帮助人理解程序；中端最终把它们 lowering 成 block、branch、merge、exit 和 backedge。
* ``break``、``continue`` 和 early return 都会新增非顺序 CFG 边，但它们的目标仍受当前结构约束。
* ``break`` 指向循环或选择结构出口；``continue`` 指向语言规定的下一轮入口，``for`` 中通常先经过 increment/latch。
* Early return 直接切断当前函数路径；存在析构、``defer``、``finally`` 或 cleanup 语义时，返回边必须先经过必要清理区域。
* ``goto`` 可以跨越普通嵌套边界，把远距离 block 直接连接起来，因此会增加支配、循环、数据流和可维护性分析成本。
* 某些目标具有结构化控制流约束，例如 WebAssembly；编译器可能需要把一般 CFG 重新组织成可验证的嵌套控制结构。

关键路径
--------

* 从 AST 中识别结构化控制节点，并为条件、body、merge、latch 和 exit 创建明确 block。
* 将 ``if`` 转成条件分支和 merge，将循环转成 header、body、latch、backedge 与 exit edge。
* 将 ``break`` 接到当前循环出口，将 ``continue`` 接到正确的 latch 或 header，将 early return 接到返回或 cleanup 路径。
* 遇到 ``goto`` 时按目标 label 直接建立边，再重新检查 predecessor、dominance、loop membership 和数据流合并点。
* Lowering 后通过 CFG verifier 或结构检查确认每个 block 有合法 terminator，所有目标存在，退出和回边语义与源码一致。
* 如果目标要求结构化控制流，再根据支配关系、回边、合流点和 region 规则进行 relooping 或等价重构。

概念辨析
--------

* Structured syntax 与 CFG 不同：前者保存人类友好的嵌套关系，后者保存编译器需要的实际控制转移图。
* ``break`` 与 ``return`` 不同：``break`` 离开当前局部结构，``return`` 离开整个函数。
* ``continue`` 与直接跳 header 不总等价：``for`` 循环可能要求先执行 increment/latch。
* ``goto`` 与结构化跳转不同：``goto`` 的目标由 label 决定，可以跨过普通结构边界。
* Reducible CFG 与结构化源码并非同义词，但规整的单入口循环和分支通常更容易映射到结构化控制表示。

本章结论
--------

结构化语法服务源码理解，CFG 服务编译器分析和代码生成。Lowering 的核心任务是把每种控制结构转换成准确的 block 与 edge，同时保持退出、继续、清理和循环语义；跳转越不受结构限制，后续分析与重构成本越高。
