第037章：Traits Design
======================

核心知识点
----------

* Traits 是泛型库的编译期“类型事实入口”：模板只拿到类型参数时，通过统一接口查询与类型绑定的关联信息。
* 常见 traits 既可以暴露类型，如 ``value_type``、``difference_type``、``pointer``，也可以暴露布尔属性、静态常量或静态操作。
* Traits 的信息来源主要有三类：类型自身的嵌套成员、标准库或用户特化、以及 traits 提供的默认推导路径。
* ``iterator_traits`` 把 iterator 的元素类型、距离类型和能力标签统一暴露给算法；原生指针依靠特化进入同一套算法模型。
* ``allocator_traits`` 把 allocator 的可选接口和默认行为整理为容器可依赖的统一表面，包括 pointer、rebind、construct、destroy 和传播属性。
* ``type_traits`` 把语言层面的类型分类、关系和转换结果变成模板可使用的编译期值或类型。
* Traits 只有进入分发点才改变程序形状。传统路径包括 tag dispatch、重载选择和 ``enable_if``，现代路径常使用 ``if constexpr`` 与 concepts。
* Traits 描述“这个类型是什么、具有什么事实”；policy 描述“这次调用希望采用什么策略”。事实与策略属于不同设计层。
* Traits 声明必须真实反映能力。错误的 iterator category、错误的平凡性判断或错误的 allocator 属性会让泛型实现选择不成立的路径。

关键路径
--------

1. 模板首先接收一个抽象类型参数，例如 ``It``、``Alloc`` 或 ``T``。
2. 通过对应 traits 提取与类型绑定的关联事实，而不是在算法中直接依赖某个具体实现类型。
3. 把提取结果用于局部类型声明、返回类型、tag dispatch、``if constexpr``、重载过滤或 concepts 约束。
4. 编译器根据这些事实实例化不同实现路径；运行时通常无需保存额外“类型描述对象”。
5. 阅读 STL 源码时先定位 traits 查询，再追踪该查询控制了哪个实现分支和最终对象语义。

概念辨析
--------

* **traits 与 policy**：traits 读取类型既有事实；policy 注入调用者主动选择的策略。
* **traits 与运行时反射**：traits 在模板实例化期产生类型或常量，不依赖运行时对象检查。
* **嵌套类型与 traits**：类 iterator 可以直接提供嵌套类型；traits 通过统一入口把类 iterator、原生指针和特化统一起来。
* **tag dispatch 与 if constexpr**：前者把标签类型交给重载决议，后者直接根据编译期布尔条件裁剪分支；两者都可由 traits 驱动。
* **traits 与 concepts**：traits 提供底层事实，concepts 把多个事实和表达式要求组织成接口约束。

本章结论
--------

Traits 的稳定模型是“类型参数 → 类型事实 → 编译期分发”。分析 STL 中的 traits 时，先确认事实来源，再看它被用于类型声明、候选过滤还是实现分支，并始终区分类型固有事实与调用策略。