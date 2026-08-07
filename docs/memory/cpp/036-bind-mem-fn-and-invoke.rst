第036章：Bind Mem Fn and Invoke
===============================

核心知识点
----------

* ``std::bind`` 把一个可调用对象和部分参数保存成新的函数对象；普通绑定参数默认按衰变后的值保存，引用语义需要 ``std::ref`` / ``std::cref`` 显式表达。
* ``std::placeholders::_1``、``_2`` 等描述未来调用实参的位置映射。占位符只负责参数槽位映射，不负责对象所有权与移动策略。
* ``std::mem_fn`` 把成员函数指针或成员数据指针包装成普通可调用对象；真正的接收者在调用时作为第一个实参提供。
* ``std::invoke`` 是统一 callable 调用入口，可处理普通函数、函数对象、lambda、成员函数指针和成员数据指针。
* 成员指针调用必须同时提供成员指针与接收者；接收者可来自对象、对象指针、``reference_wrapper`` 或可解引用句柄，具体可调用性仍受成员函数的 cv/ref 限定约束。
* ``std::is_invocable``、``std::invoke_result``、``std::is_nothrow_invocable`` 把“能否调用、返回什么、是否 noexcept”转成编译期 trait；C++20 可进一步用 ``std::invocable`` 等 concept 表达约束。
* ``std::bind`` 会把调用配置对象化，但 placeholder 映射较难阅读；现代业务适配通常优先 lambda，把捕获、参数和逻辑放在同一个局部结构中。
* ``std::mem_fn`` 与 ``std::invoke`` 不等于 ``std::function``：前两者通常保留具体类型，``std::function`` 才执行运行时类型擦除。
* 版本边界：``bind``、``placeholders``、``mem_fn`` 属于 C++11；``invoke`` 与 invocable trait 属于 C++17；concept 约束进入 C++20；``invoke_r`` 进入 C++23。

关键路径
--------

1. 先判断调用逻辑是否需要被保存成对象；局部业务适配优先 lambda，需要参数绑定对象时再考虑 ``bind``。
2. 阅读 ``bind`` 时先写出目标函数形参顺序，再逐槽位还原普通值、``reference_wrapper`` 和 ``_N`` 的来源，最后得到一次真实调用。
3. 遇到成员函数指针或成员数据指针时，把第一个调用实参识别为接收者，再检查其对象类别、生命周期和成员限定。
4. 泛型代码需要统一处理不同 callable 时，使用 ``std::invoke(f, args...)`` 作为调用入口，而不是为普通函数与成员指针分别写分支。
5. 在模板接口中先用 ``is_invocable`` / concept 验证调用表达式，再用 ``invoke_result`` 和 ``is_nothrow_invocable`` 传播返回类型与异常属性。
6. 需要统一运行时存储不同 callable 时，再进入 ``std::function`` 或其他 type-erased wrapper；仅统一调用语法时不需要类型擦除。

概念辨析
--------

* **bind 与 lambda**：二者都能保存状态并适配参数；lambda 的捕获和参数流更直观，``bind`` 更偏向传统参数绑定与重排。
* **placeholder 与参数所有权**：``_N`` 只表示未来第 N 个实参的位置，引用、复制、移动语义仍由目标形参和绑定对象决定。
* **mem_fn 与成员指针**：成员指针本身需要 ``.*`` / ``->*`` 语义；``mem_fn`` 将其包装成普通函数对象调用表面。
* **invoke 与普通调用**：对普通 callable，``invoke`` 等价于常规调用；它的价值在于把成员函数指针和成员数据指针纳入同一规则。
* **invoke 与 function**：``invoke`` 统一“怎么调用”，``std::function`` 统一“怎么以同一种运行时类型保存和调用”。
* **is_invocable 与 invoke_result**：前者回答调用是否合法，后者给出合法调用的结果类型；``is_nothrow_invocable`` 再补充异常属性。
* **对象生命周期与包装器生命周期**：``mem_fn`` 保存的是成员指针，``bind`` 或 lambda 可能保存值或引用；包装器存活不代表外部引用对象仍然存活。

本章结论
--------

C++ callable 工具可以按“局部适配、参数绑定、成员指针包装、统一调用、运行时类型擦除”分层理解。业务代码优先用 lambda，成员指针进入普通调用表面时用 ``mem_fn``，泛型库统一执行 callable 时用 ``invoke``，模板约束用 invocable trait/concept；只有确实需要异构 callable 的统一运行时存储时才进入 ``std::function``。