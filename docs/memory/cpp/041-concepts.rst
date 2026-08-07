第041章：Concepts
================

核心知识点
----------

* C++20 concepts 把模板要求提升到接口层，让“这个模板接受什么类型、需要什么操作”直接出现在声明中，而不是等函数体实例化失败后再暴露。
* Concept 是命名后的约束集合；constraint 是实际参与候选可行性和重载排序的编译期条件。
* ``requires clause`` 把约束附着在模板或函数声明上；``requires expression`` 用来检查表达式、类型和附加条件是否成立。
* requires expression 可包含简单要求、类型要求、复合要求和嵌套要求；它们分别检查表达式存在、类型存在、返回类型/``noexcept`` 以及额外布尔条件。
* 约束在函数体实例化前参与候选过滤，不满足约束的模板不会进入可行候选集合，因此诊断更靠近接口条件。
* 约束还参与重载偏序。更强的标准 concept，如 ``random_access_range`` 相对于 ``input_range``，可以使更专门的重载获胜。
* 编译器通过约束归一化和原子约束判断 subsumption；它不是任意布尔定理证明器，因此应优先复用同一标准 concept 或共享自定义 concept。
* ``std::same_as`` 表达精确同型；``std::integral`` 表达整数类型族；二者约束强度和接口含义不同。
* ``std::ranges`` concepts 把 ``begin/end``、iterator 能力和 range 语义组合成标准算法输入契约，例如 ``input_range``、``random_access_range``。
* Concepts 改善接口约束表达，但不替代对象生命周期、异常安全、复杂度和业务不变量检查。

关键路径
--------

1. 从模板真正会执行的操作出发，先写清输入对象必须满足的能力。
2. 优先选择已有标准 concept；标准 concept 不足时再用 requires expression 补充成员、返回类型或常量条件。
3. 将约束通过模板参数形式或 ``requires clause`` 附着到声明上。
4. 调用时先完成模板实参替换，再检查关联约束；失败候选被淘汰，成功候选进入普通重载决议。
5. 多个约束重载同时可行时，根据约束强弱和普通重载规则选择最佳候选。
6. 被选中后才实例化函数体，因此接口约束只保证声明中明确写出的条件。

概念辨析
--------

* **requires clause 与 requires expression**：前者把约束挂到声明上；后者生成“某组要求是否成立”的约束表达式。
* **concept 与 constraint**：concept 是可复用的命名约束；constraint 是某个声明最终关联的实际条件。
* **same_as 与 convertible_to**：前者要求精确同型，后者允许转换语义，接口边界明显更宽。
* **integral 与 same_as<int>**：``integral`` 接受整个整数类型族；``same_as<int>`` 只接受精确 ``int``。
* **concepts 与 SFINAE**：SFINAE 通过替换失败间接删除候选；concepts 直接声明条件，并提供约束诊断与偏序关系。
* **range concept 与容器类型**：算法约束的是 range/iterator 能力，不是某个具体 ``vector``、``list`` 类型名称。

本章结论
--------

Concepts 的稳定模型是“操作需求 → 命名约束 → 候选过滤与偏序”。设计泛型接口时应从算法真正使用的操作出发，优先复用标准 concepts，再补充最小自定义要求；约束要表达能力边界，而不是把具体实现类型写死。