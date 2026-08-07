第042章：Ranges
===============

核心知识点
----------

* C++20 Ranges 把传统 ``[first, last)`` iterator pair 提升为可直接传入算法的 range 对象；算法内部通过 ``std::ranges::begin/end`` 获取边界。
* range 只表示“可形成区间”，具体算法还会继续要求 iterator 能力、sentinel 兼容性、元素操作与 callable 约束。
* iterator 与 sentinel 可以是不同类型；iterator 负责访问和推进，sentinel 只负责描述终止条件。
* ``std::ranges::begin/end`` 是 customization point object，可统一支持数组、成员 ``begin/end`` 与用户定义 range。
* ranges algorithm 通常同时提供 iterator/sentinel 重载和整个 range 重载；调用整个 range 能减少边界配错的风险。
* ranges algorithm 通常立即执行；view adaptor 通常只构造延迟对象，真正过滤、映射等操作发生在迭代时。
* projection 在 comparator/predicate 之前先提取字段或键，常通过 ``std::invoke`` 调用；成员指针可直接作为 projection。
* ``borrowed_range`` / ``borrowed_iterator_t`` 处理返回 iterator 与临时 range 生命周期之间的关系；非 borrowed 临时 range 的 iterator 结果可能被替换为 ``dangling``。
* Ranges 没有取消旧 STL algorithm；二者长期并存，旧接口偏 iterator pair，新接口强调受约束 range 与 projection。

关键路径
--------

1. 判断对象能否通过 ``std::ranges::begin/end`` 形成 range。
2. 再检查算法需要的 iterator concept，例如 input、forward、bidirectional、random access。
3. 检查 sentinel 是否满足对应 ``sentinel_for`` 关系。
4. 检查 comparator、predicate、projection 与元素引用类型是否满足算法 concept。
5. range 重载进入后，本质仍会转成 begin/end，再进入算法主循环。
6. 若调用返回 iterator，确认输入是否为临时 range，以及返回类型是否受 borrowed range 规则限制。
7. 若后续接 view pipeline，再单独检查 lazy execution 与底层对象生命周期。

概念辨析
--------

* **range 与 container**：container 通常拥有元素；range 只要求可取得遍历边界，可以是容器、视图、数组或生成序列。
* **iterator 与 sentinel**：iterator 表示当前位置并能访问元素；sentinel 只表达结束条件，不要求与 iterator 同型。
* **ranges algorithm 与 view**：algorithm 通常立即消费区间；view 保存规则并延迟到遍历时执行。
* **projection 与 comparator**：projection 决定“看元素的哪个值”，comparator 决定这些值之间的顺序关系。
* **common_range 与一般 range**：common range 的 iterator 与 sentinel 同型；一般 range 允许二者分离。
* **borrowed range 与 owning range**：borrowed 讨论临时 range 销毁后 iterator 是否仍有意义，不等同于 range 自己是否拥有元素。

本章结论
--------

Ranges 的稳定分析顺序是“range 边界 → iterator/sentinel 能力 → 算法 concept → projection/callable → 返回值生命周期 → 是否延迟执行”。接口虽然更短，真正的约束比传统 iterator pair 更显式，也更依赖对生命周期与能力模型的准确判断。