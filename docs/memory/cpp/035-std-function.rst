第035章：Std Function
=====================

核心知识点
----------

* ``std::function<R(Args...)>`` 固定调用签名，擦除具体 callable 类型，把函数指针、捕获 lambda、函数对象和 bind expression 统一成同一种拥有型运行时对象。
* type erasure 的核心是“固定外部接口 + 隐藏内部目标类型”；wrapper 内部仍必须保存目标对象、调用入口和生命周期管理入口。
* 调用路径可抽象为 ``wrapper → invoker → concrete callable``；调用方不再知道目标具体类型，因此会形成一次运行时间接调用边界。
* ``std::function`` 具有空状态；``operator bool`` 可检查是否保存目标，调用空对象会抛出 ``std::bad_function_call``。
* ``std::function`` 是 **copyable owning wrapper**。目标必须满足其复制模型，因此 move-only callable 不适合直接存入普通 ``std::function``。
* C++23 的 ``std::move_only_function`` 是标准 move-only owning wrapper，适合保存只能移动的 lambda、任务和独占资源所有者；它还支持 cv/ref/noexcept 限定进入调用签名。
* C++26 的 ``std::copyable_function`` 继续提供可复制 owning wrapper，同时补齐更完整的 cv/ref/noexcept 调用限定模型，可视为比传统 ``std::function`` 更精确的复制型调用包装器。
* C++26 的 ``std::function_ref`` 是 **non-owning callable view**：它不拥有目标，也不延长目标生命周期，适合短期同步调用边界，不能当长期 callback storage 使用。
* ``std::move_only_function`` 的空对象调用与 ``std::function`` 不同：空 ``std::move_only_function`` 的调用没有 ``bad_function_call`` 保障，使用前必须建立非空不变量或检查状态。
* 常见 owning wrapper 实现会提供 small object optimization，把满足条件的小目标内联存入 wrapper；目标过大时通常需要动态分配。
* SBO 的容量、对齐和一般启用条件属于实现细节，不能把“某个捕获一定不分配”当作跨标准库保证。
* 构造成本来自目标构造和可能分配；复制型 wrapper 还承担目标复制成本；调用成本来自间接派发和较弱的内联机会。
* owning wrapper 只管理 callable 对象本身，不自动延长 callable 内部引用、裸指针或 ``this`` 所指对象的生命周期；non-owning ``function_ref`` 的生命周期约束更强。
* 模板参数保留 callable 具体类型，适合即时调用和热路径；函数指针适合无状态调用；type-erased wrapper 适合 ABI/API 边界、异构回调槽位或运行时存储。
* 所有这些 callable wrapper 都不自动提供业务线程安全；目标状态、回调集合的替换和并发发布仍需要外层同步。

关键路径
--------

选择 callable 表达：

::

   need runtime type erasure ?
      ├─ no  → template / concrete callable / function pointer
      └─ yes
          → need wrapper to own callable ?
             ├─ no  → function_ref (C++26), lifetime must outlive call
             └─ yes
                 → callable must be copied ?
                    ├─ no  → move_only_function (C++23)
                    └─ yes
                        → std::function
                        → or copyable_function (C++26) when qualifiers matter

拥有型 wrapper：

::

   choose call signature
   → construct erased target
   → inline storage or allocation
   → copy/move according to wrapper contract
   → indirect invoke
   → destroy target

生命周期检查：

::

   wrapper stores callable
   → inspect captured references / this / pointers
   → owning wrapper owns closure object only
   → referenced external object still alive ?
      ├─ yes → invoke
      └─ no  → dangling access

   function_ref
   → target must already exist
   → view must not outlive target

概念辨析
--------

* **``std::function`` 与 ``std::move_only_function``**：前者要求复制型值语义；后者是 C++23 的 move-only owning wrapper，适合独占状态 callable。
* **``std::function`` 与 ``std::copyable_function``**：两者都拥有并复制目标；C++26 ``copyable_function`` 能在签名中更完整表达 cv/ref/noexcept 限定。
* **Owning wrapper 与 ``std::function_ref``**：owning wrapper 保存目标对象；``function_ref`` 只借用 callable，目标必须覆盖整个使用期。
* **``std::function`` 与模板 callable 参数**：前者统一运行时类型并牺牲部分优化信息，后者保留具体类型并产生模板实例化。
* **``std::function`` 与函数指针**：函数指针只表示无状态代码入口；type-erased owning wrapper 可以持有带状态目标。
* **SBO 与零开销**：SBO 只可能避免动态分配，仍存在类型擦除管理和间接调用边界。
* **wrapper 生命周期与目标引用生命周期**：wrapper 可继续存活并不意味着闭包内部引用仍然有效；``function_ref`` 更不会延长目标生命周期。
* **空状态语义**：空 ``std::function`` 调用抛 ``bad_function_call``；其它 wrapper 的空调用合同不能机械套用 ``std::function``。
* **标准存在与工具链可用**：C++23/26 标准已定义这些 wrapper，不代表所有当前编译器和标准库版本都完整实现；工程代码仍需检查 feature-test macro 与工具链支持。

本章结论
--------

2026 年不应再把“运行时 callable type erasure”只理解为 ``std::function``。正确选择顺序是 ``是否需要 type erasure → 是否拥有目标 → 是否需要复制 → 是否需要 cv/ref/noexcept 精确签名 → 生命周期与成本``：``std::function`` 负责经典可复制 owning 场景，``std::move_only_function`` 负责 move-only owning 场景，C++26 ``std::copyable_function`` 提供更精确的可复制包装，``std::function_ref`` 则负责非拥有短期调用视图。