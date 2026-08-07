第039章：Type Traits
===================

核心知识点
----------

* Type traits 把类型问题转成编译期布尔值、类型别名或模板条件，服务重载选择、偏特化、``static_assert``、``if constexpr`` 和 concepts。
* 分类 traits 回答“这个类型是什么”，如 ``is_integral``、``is_pointer``、``is_reference``、``is_same``；关系和属性 traits 用于更具体的类型判断。
* 转换 traits 回答“把类型整理成什么形状”，如 ``remove_reference``、``remove_cv``、``decay``、``add_pointer``。
* 泛型接口应先规范化类型形状，再进行分类或关系判断；否则转发引用、cv、数组和函数类型会把调用形式混入接口语义。
* ``std::decay_t<T>`` 模拟常见按值传参后的类型调整：去引用、去顶层 cv、数组退化为指针、函数退化为函数指针。
* ``std::enable_if`` 把布尔 trait 接到模板声明上，条件为假时使候选在替换阶段失效，是传统 SFINAE 的常见入口。
* ``std::void_t`` 把一组合法类型映射为 ``void``，适合构建检测 idiom，判断成员类型或表达式是否存在。
* ``is_same``、``is_constructible``、``is_convertible`` 的约束强度不同：完全同型、可构造、可隐式转换分别表达不同接口承诺。
* Traits 只证明类型层条件，不证明运行时对象状态、容量、地址有效性或生命周期。
* 版本边界：``type_traits`` 自 C++11 进入标准库，``_t`` 别名常见于 C++14，``_v`` 与 ``void_t`` 常见于 C++17，C++20 concepts 改善了接口约束表达。

关键路径
--------

1. 从模板实参 ``T``、``C`` 等原始类型开始，先判断是否需要去引用、去 cv 或 decay。
2. 对规范化后的类型执行分类、关系、构造性或转换性查询。
3. 把查询结果接入 ``static_assert``、``if constexpr``、``enable_if``、偏特化或 concepts。
4. 若需要检测成员或表达式，使用 ``decltype``、``declval`` 与 ``void_t`` 构建未求值语境下的合法性检查。
5. 最终再把可行候选送入普通重载决议；traits 本身不替代重载排序。

概念辨析
--------

* **分类 traits 与转换 traits**：前者返回类型性质，后者生成新的类型形状。
* **remove_reference 与 decay**：前者只去引用；后者还处理顶层 cv、数组和函数退化。
* **is_same 与 is_constructible**：完全相同是最窄关系；可构造允许通过构造函数建立目标对象。
* **is_constructible 与 is_convertible**：可构造包含显式构造路径；可转换关注隐式转换可行性。
* **void_t 检测与运行时验证**：``void_t`` 只检查表达式能否形成，不执行表达式，也不验证对象当前状态。

本章结论
--------

Type traits 的稳定用法是“规范化类型 → 查询类型事实 → 接入模板机制”。设计约束时先确定真正需要的是同型、可构造、可转换还是表达式存在，再选对应 trait；不要让引用形态和调用方式意外决定接口语义。