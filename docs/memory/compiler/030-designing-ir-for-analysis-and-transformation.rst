第030章：Designing IR for Analysis and Transformation
======================================================

核心知识点
----------

* IR 设计的核心目标是让后续分析和 transformation 能直接获得所需事实，而不是反复从源码形态中恢复语义。
* Operation granularity 决定一个 IR 节点承载多少语义：高层 operation 保留领域意图，低层 operation 暴露更基础的算术、控制和内存动作。
* 适合分析的 IR 应显式表达 control flow 与 data flow：block/edge 表示可达路径，SSA use-def 表示值依赖，合流点用 ``phi`` 或 block argument 表示路径相关值。
* 类型系统决定 operation 合法输入输出；memory model 和 side-effect semantics 决定 load/store/call 能否移动、合并或删除，是优化正确性的关键边界。
* IR 应为 verifier 提供可检查不变量，为 pass 提供稳定查询接口，为 lowering 提供可重写结构；设计目标应服务实际消费者。
* Textual IR、in-memory IR 和 serialized/binary IR 服务不同场景：文本适合调试与测试，内存对象适合高效分析和改写，序列化形态适合缓存与跨进程传输。

关键路径
--------

设计 IR 时按 ``消费者 -> 所需事实 -> operation/type/control/memory 表示 -> verifier -> transformation`` 推进。

以条件赋值为例，应让两个分支成为显式 CFG edge，让各分支结果成为独立 SSA value，在 merge 点建立 ``phi``/block argument，再把合流值交给 ``store`` 和 ``return``。这样可达性、常量传播、死代码删除和副作用分析都能直接在图上运行。

优化 pass 在改写前必须同时检查值依赖和副作用：没有使用者的纯计算通常可删除；没有使用者的 ``store``、I/O、volatile/atomic 操作或未知调用仍可能具有可观察效果。

概念辨析
--------

* **Operation granularity**：不是越低越好；最佳粒度取决于当前阶段需要保存和改写的事实。
* **Control flow vs data flow**：前者描述执行可能走向，后者描述值如何产生和传播；优化通常同时依赖两者。
* **Type semantics vs memory semantics**：类型回答操作数如何解释，内存/副作用回答操作能否跨越其它操作安全重排。
* **Text form vs in-memory form**：文本便于人读和 golden test；真正的 pass 通常操作带引用关系和缓存分析结果的内存结构。

本章结论
--------

好的 IR 是为分析和转换设计的语义接口。它应在合适粒度显式表达控制流、数据流、类型、内存和副作用，并提供可验证的不变量；某个事实越重要，越应在需要它的阶段成为一等表示，而不是依靠后续重新猜测。