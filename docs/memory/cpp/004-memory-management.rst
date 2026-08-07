第004章：Memory Management
==========================

核心知识点
----------

C++ 内存管理要分成三层：分配接口取得和归还原始存储；构造/析构建立和结束对象生命周期；容器策略维护 size、capacity、异常安全和提交时机。STL 的正确性来自这三层始终不混淆。

``malloc/free`` 与 ``operator new/operator delete`` 主要处理动态存储。前者属于 C 风格接口，分配失败通常返回空指针；常规 throwing ``operator new`` 失败时抛 ``std::bad_alloc``。两者都不自动建立业务对象生命周期。

``new T(args...)`` 是组合表达式：选择分配函数取得存储，再构造 T；``delete p`` 先析构对象，再调用匹配的释放函数。数组形式 ``new[]/delete[]`` 还需要正确处理多个元素的构造、逆序析构与失败回滚。

STL 容器通常不使用 ``new T[n]`` 表示容量，因为那会一次性创建 n 个 T。vector 需要“capacity 个槽位，但只有 size 个活对象”，所以必须把原始存储分配与逐元素构造分离。

placement new / ``std::construct_at`` 在指定存储上建立对象；``std::destroy_at`` 结束对象生命周期。``reinterpret_cast<T*>`` 只改变指针解释，不会自动创建 T 对象。

allocator 把容器的存储来源抽象化；``allocator_traits`` 统一 allocate、deallocate、construct、destroy 以及传播规则。容器仍负责元素数量、结构状态、异常回滚和复杂度承诺。

关键路径
--------

手动创建动态对象的基本路径是：

``operator new(sizeof(T)) → construct_at → 活对象 → destroy_at → operator delete``。

``new T(args...)`` 将前两步组合，若构造抛异常，语言会调用匹配的 deallocation function 释放已取得存储；手动拆开分配与构造时，这个异常清理责任由调用方承担。

vector 扩容是本章最重要的内存路径：

``检查容量不足 → allocate 新原始存储 → 在新存储逐个 move/copy construct → 失败则销毁已构造新元素并 deallocate 新存储 → 全部成功后销毁旧元素 → deallocate 旧存储 → 更新 begin/end/cap``。

``clear`` 的路径是：

``逐个 destroy 已构造元素 → end = begin``。

它结束对象生命周期，但通常保留底层容量；容器析构或后续换存储时才真正 deallocate。

分配与释放必须匹配：``malloc ↔ free``、``operator new ↔ operator delete``、``new ↔ delete``、``new[] ↔ delete[]``、allocator 的 ``allocate ↔ deallocate``。混用会破坏分配器的内部约定。

概念辨析
--------

``分配内存`` 不等于 ``构造对象``。分配只产生原始存储；构造成功后，目标类型对象才真正存在。

``delete expression`` 不等于 ``operator delete``。前者是“析构 + 释放”的语言组合动作，后者主要是释放存储的函数。

``placement new`` 不分配新的堆内存。它使用调用方提供的地址，只承担在该地址建立对象生命周期的动作。

``capacity`` 不等于已构造对象数量。vector 的 ``[begin,end)`` 是活元素区，``[end,cap)`` 是未构造存储区。

``reserve`` 与 ``resize`` 不同。reserve 主要改变存储容量；resize 改变元素数量，需要构造或销毁对象。

allocator 不等于容器。allocator 决定存储取得策略，容器决定元素布局、生命周期、异常安全、iterator 规则和结构提交。

本章结论
--------

阅读 STL 内存源码时，先问“现在只有存储还是已经有对象”，再追踪 allocate、construct、destroy、deallocate 四个阶段，最后检查异常发生时已经成功构造了多少对象、哪些资源需要回滚、容器状态在什么时候正式提交。vector、deque、list 和 allocator 的差异都建立在这套分层之上。