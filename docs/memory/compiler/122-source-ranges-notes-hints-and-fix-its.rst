第122章：Source Ranges, Notes, Hints, and Fix-Its
=================================================

核心知识点
----------

* Source location 回答“先看哪里”，source range 回答“哪段源码参与了当前判断”；二者是诊断证据的坐标系统。
* Primary location 应落在最关键 token 或插入点，primary range 应覆盖最小有意义结构，related range 再补充声明、候选、宏展开或模板上下文。
* Caret 是 primary location 的视觉渲染，highlight 是 source range 的视觉渲染；IDE 中的波浪线本质上是同一组结构化 range。
* Range 过小会丢上下文，过大会制造噪声。稳定做法是“窄 primary + 必要 related spans”。
* 宏、生成代码、模板和 include 会让 token 同时拥有 spelling location 与 expansion/use location；主诊断应优先指向用户真正能修改的位置。
* Note 用于保存主诊断之外的重要推理事实，例如 previous declaration、候选函数、模板实例化栈、宏展开来源、类型推导来源。
* Note 不应重复主错误，而应回答“为什么编译器会这样判断”。
* Hint 是修复方向；fix-it 是可结构化应用的局部编辑。Fix-it 通常应表达明确的 insert、delete 或 replace，而不是开放式建议。
* 自动 fix-it 的前提是高置信度和局部语义安全。编译器只能猜测用户意图时，应提供 help，而不是直接生成首选自动修改。
* Fix-it 必须绑定精确 source range，并考虑 token boundary、宏展开、编码和多编辑冲突；错误的自动修复比没有修复更危险。
* 诊断生成逻辑与渲染逻辑应分离：前端/语义阶段保存 span、note、edit，终端、IDE、CI 再决定如何显示。
* 好诊断的目标不是堆更多文字，而是保留“错误事实 → 相关证据 → 可行动修改”的最短推理路径。

关键路径
--------

源码证据构造：

::

   compiler failure
   → choose primary source location
   → choose minimal primary range
   → attach related source spans
   → attach notes explaining relationships
   → derive safe local edit if provable
   → render caret/highlight or IDE ranges

Fix-it 决策：

::

   candidate repair
   → exact editable source range?
   → unique/high-confidence intent?
   → local semantic safety?
   → no macro/generated-code ambiguity?
   → emit insert/delete/replace
   → otherwise emit help only

概念辨析
--------

* **Location 与 range**：location 是点，range 是参与判断的一段源码。
* **Primary span 与 related span**：前者聚焦当前失败，后者补充跨位置证据。
* **Caret/highlight 与 structured span**：前者是显示形式，后者才是编译器与工具共享的数据。
* **Hint 与 fix-it**：hint 可以只是建议，fix-it 必须能转换为明确、安全的文本编辑。
* **Spelling location 与 expansion location**：宏或生成代码中的 token 可能来自定义位置，也可能在用户调用位置触发错误。

本章结论
--------

诊断证据的稳定模型是 ``Primary Range + Related Spans + Reasoning Notes + Safe Edit``。高质量诊断不是只说“错了什么”，而是把编译器的内部推理重新锚定到可修改源码，并在证据足够强时把修复压缩成精确 edit。
