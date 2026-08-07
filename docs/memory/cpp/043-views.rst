第043章：Views
==============

核心知识点
----------

* view 是轻量的 range 变换对象，通常保存底层 range、callable 和少量状态；它自身一般不复制整份数据。
* view pipeline 采用 lazy execution：构造管线时保存规则，真正遍历时才执行 filter、transform、take、drop 等操作。
* ``filter_view`` 在推进 iterator、寻找下一个满足条件的元素时调用 predicate；命中率直接影响遍历成本。
* ``transform_view`` 通常在解引用时调用映射函数；同一位置被多次解引用时，转换可能重复执行。
* ``take_view`` 增加计数终止条件；``drop_view`` 改变起点；``iota_view`` 直接生成值序列而不是包装已有容器。
* view 会传播或削弱底层 iterator 能力。过滤后的第 N 个可见元素无法常数时间定位，因此即使底层是 vector，也不能把 filter_view 当随机访问序列理解。
* 部分 view 会缓存 ``begin`` 或其他位置状态；底层 range 修改导致 iterator 失效后，view 内缓存同样需要重新审查。
* callable 是 view 对象状态的一部分。lambda 的值捕获、引用捕获、大对象捕获都会影响复制成本和生命周期。
* view 自身轻量不代表底层数据安全；non-owning view 的有效性最终取决于底层 range 是否仍然存活且未发生破坏性修改。
* 无界生成 range 必须由 ``take``、sentinel 或外部消费逻辑提供终止条件，否则完整遍历无法结束。

关键路径
--------

1. 先找到 pipeline 最底层的 range，确认数据由谁拥有。
2. 沿管线向外检查每个 adaptor 保存的 predicate、transform、计数或其他状态。
3. 判断具体操作在 ``begin``、``operator++`` 还是 ``operator*`` 时发生。
4. 检查 adaptor 是否降低 iterator 能力，后续算法是否仍满足对应 concept。
5. 检查是否存在 begin/位置缓存，以及底层容器修改是否会让缓存或 iterator 失效。
6. 检查 callable 捕获对象的所有权、复制成本与生命周期。
7. 最后确认 pipeline 被消费一次还是多次，以及重复遍历是否符合底层 range 与副作用语义。

概念辨析
--------

* **view 与 owning container**：view 主要表达观察或变换关系；container 负责元素存储、容量和生命周期。
* **lazy 与 eager**：view adaptor 多数延迟执行；``ranges::sort``、``ranges::copy`` 等 algorithm 通常立即遍历。
* **filter 与 transform**：filter 改变哪些元素可见；transform 改变元素被观察成什么值。
* **take 与 drop**：take 限制终点；drop 推进起点。
* **iota_view 与普通 view**：iota 是 range factory，自己生成序列；filter/transform 等通常包装已有 range。
* **轻量对象与安全生命周期**：view 对象复制便宜，不代表它指向的底层对象会自动延寿。

本章结论
--------

分析 view 应按“底层 range → adaptor 状态 → 求值时机 → iterator 能力 → 缓存 → 生命周期 → 消费方式”展开。View 的核心价值是零或低额外存储的组合式延迟计算，它的主要风险也集中在延迟执行、悬垂引用和底层修改后的失效传播。