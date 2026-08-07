第009章：Exception Safety
=========================

核心知识点
----------

异常安全描述操作失败后对象还能保持什么状态。核心承诺分为 basic、strong 与 no-throw guarantee：basic 保证对象仍有效且无资源泄漏，但值可能改变；strong 保证操作要么成功，要么对目标对象无可观察影响；no-throw 保证操作不向外传播异常。

Strong guarantee 的典型实现是 commit/rollback：先在临时资源中完成所有可能失败的工作，只有全部成功后才执行一个极短、最好不抛异常的提交动作。失败时销毁临时对象、释放临时存储，旧状态保持不变。

RAII 是异常回滚的基础。临时 buffer、guard、锁和资源句柄都可以由局部对象持有；异常离开作用域时，其析构函数自动完成清理。Guard 通常记录“已经成功构造多少对象”，从而只销毁真正进入生命周期的前缀。

``noexcept`` 会参与 STL 实现选择。元素移动构造若 ``noexcept``，vector 扩容可以安全地迁移旧元素；若移动可能抛但拷贝可用，库常借助 ``std::move_if_noexcept`` 选择拷贝，以便失败后旧元素仍保持原值。

``std::move_if_noexcept`` 在移动不抛异常，或类型不可拷贝时返回右值入口；移动可能抛且可拷贝时返回 ``const T&``，让构造走拷贝路径。它将类型的异常属性直接转化为容器的迁移策略。

异常安全不仅看分配失败。元素构造、拷贝、移动、allocator、比较器、谓词和用户回调都可能抛异常，源码必须明确每个阶段已有多少状态发生变化，以及清理责任在哪里闭合。

关键路径
--------

Vector 扩容的 strong-guarantee 理想路径是：

``旧 vector 保持不动 → allocate 新存储 → guard 接管新存储 → 在新存储构造新元素/迁移旧元素 → 任一步失败则 guard 销毁已构造前缀并释放新存储 → 全部成功 → 销毁旧元素/释放旧存储 → 不抛异常地提交新 begin/end/capacity → guard release``。

Move/copy 选择路径是：

``检查 is_nothrow_move_constructible<T> → 若 true 则 move → 否则检查 copy 是否可用 → 可拷贝则 copy 以保护旧值 → 不可拷贝则只能尝试可能抛异常的 move``。

最后一种情况下，若移动一部分旧元素后抛异常，旧序列中部分对象可能已经进入 moved-from 状态，容器通常无法继续提供完整 strong guarantee。

RAII guard 的清理路径是：

``guard 保存 ptr/capacity/constructed_count → 每成功构造一个对象就 ++count → 异常传播 → guard 析构 → destroy [0,count) → deallocate 整块临时存储``。

提交点判断固定为：先找目标对象真正修改内部指针、size、root、link 等稳定状态的那一行，再检查提交之前的所有可能抛异常操作是否都由临时状态承接。

概念辨析
--------

Basic guarantee 不等于“失败后什么都可以乱”。它仍要求对象不变量成立、资源不泄漏、对象可以安全析构并继续执行合法操作。

Strong guarantee 不等于所有 STL 操作都必须保持原值。具体接口能否提供 strong guarantee 取决于元素类型、allocator 和操作本身的异常属性。

``noexcept`` 不等于函数绝对不会发生错误。它是“不允许异常逃出”的语言承诺；若异常仍逃出 ``noexcept`` 函数，程序会走终止路径。

``std::move`` 与 ``std::move_if_noexcept`` 不同。前者无条件改变表达式类别，后者根据移动是否安全与拷贝是否可用选择 move 或 copy 入口。

RAII 不等于 strong guarantee。RAII 主要保证资源责任能在异常时关闭；strong guarantee 还要求旧值保持，并依赖提交顺序与回滚设计。

异常安全等级是接口与实现共同的约束。源码中若声称 strong guarantee，却在所有可能失败工作完成前就破坏旧状态，就缺少支撑该承诺的提交边界。

本章结论
--------

分析 STL 异常安全时，先确定接口承诺，再画出对象状态变化，找出所有可能抛异常的步骤，随后定位 RAII guard、回滚路径与最终提交点，最后检查元素的 move/copy/noexcept 属性是否支持该承诺。异常安全本质上是对“部分执行状态”的严格管理。