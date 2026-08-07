第032章：引用计数
=================

核心知识点
----------

* CPython 的普通对象生命周期首先由引用计数驱动。对象头中的 ``ob_refcnt`` 记录 strong reference 对对象存活的持有责任。
* Python 名字、容器元素、实例属性、frame 局部变量、闭包 cell、traceback 和 C 扩展字段都可能形成 strong reference；判断生命周期时应先画对象图，再看单个名字。
* ``Py_INCREF()`` 表示取得一份新的 strong reference；``Py_DECREF()`` 表示释放自己已经拥有的一份 strong reference。最后一份 strong reference 被释放时，对象进入 ``tp_dealloc`` 等销毁路径。
* ``Py_NewRef()`` 可以直接取得新的 strong reference；``Py_XINCREF()``、``Py_XDECREF()`` 用于允许 ``NULL`` 的路径。
* ``Py_DECREF()`` 可能触发析构、weakref callback、``__del__`` 或其它 Python 代码，因此释放旧对象之前必须先把外部可见字段或容器更新到一致状态。
* ``Py_CLEAR(field)`` 的核心价值是先把字段清空，再释放旧引用；它常用于 GC 清理、析构和可能发生 re-entry 的对象字段。
* **new reference** 表示调用方接过释放责任；**borrowed reference** 表示调用方只临时观察对象，生命周期仍由原持有者保证；**steals reference** 表示所有权转交给被调用 API。
* borrowed reference 一旦跨过回调、容器修改、对象释放、线程切换或长期保存边界，就可能失效；需要继续使用时，应先通过 ``Py_NewRef()`` 等方式提升为 temporary strong reference。
* 引用计数解决的是“最后一份强引用消失”的对象；它无法单独回收仅由内部强引用互相支撑的循环对象组。
* 引用泄漏通常来自 long-lived root 仍然持有对象，或 C 层取得了 strong reference 却没有在所有成功、失败和异常路径上释放。
* traceback 会持有 frame，frame 又会持有 locals，因此长期保存异常对象可能间接延长大量业务对象的生命周期。
* 参与循环引用的 C 扩展类型需要通过 ``tp_traverse`` 暴露内部引用边，并通过 ``tp_clear`` 打断环，循环 GC 才能正确处理它们。
* ``sys.getrefcount()``、``Py_REFCNT()`` 适合调试，不适合做业务生命周期判断；immortal object 和 free-threaded build 会让计数读数更难等价为“真实引用条数”。

关键路径
--------

普通 strong reference 生命周期：

::

   object allocated
       ↓
   strong references created
       ↓
   INCREF / container store / local binding
       ↓
   object remains reachable
       ↓
   references released
       ↓
   DECREF
       ↓
   refcount > 0 ? ── yes ──→ keep alive
       ↓ no
   tp_dealloc / tp_free
       ↓
   memory returned to allocator

borrowed reference 安全路径：

::

   API returns borrowed reference
       ↓
   will code cross callback / mutation / release boundary ?
       ↓ yes
   Py_NewRef()
       ↓
   temporary strong reference
       ↓
   dangerous operation
       ↓
   Py_DECREF()

循环引用路径：

::

   object A strongly references B
       ↓
   object B strongly references A
       ↓
   external roots removed
       ↓
   each refcount still > 0
       ↓
   reference counting cannot free group
       ↓
   cyclic GC traversal and clear

概念辨析
--------

* **引用与所有权**：C 指针能指向对象，不代表当前代码拥有 strong reference；是否需要 ``DECREF`` 取决于 API 的所有权契约。
* **strong reference 与 borrowed reference**：strong reference 保证对象存活并带来释放责任；borrowed reference 的安全性依赖原持有者继续存在。
* **temporary strong reference 与长期持有**：temporary reference 只是让对象安全跨过危险边界，使用结束后立即释放；长期字段保存则属于对象状态的一部分。
* **reference leak 与 reference cycle**：leak 表示仍有不应存在的外部 strong reference；cycle 表示对象组只剩内部引用却无法靠 refcount 归零。
* **对象销毁与资源释放**：对象内存最终回收时机不应承担文件、锁、连接等外部资源的正确性；这类资源优先使用 ``with``、``close()`` 等显式协议。
* **``Py_DECREF`` 与简单减一**：它既改变计数，也可能直接进入复杂析构代码，因此必须把它视为一个可能 re-enter runtime 的边界动作。

本章结论
--------

CPython 引用计数的核心不是记住 ``ob_refcnt`` 的数字，而是维护 strong reference 的所有权协议。排查对象生命周期时，应先列出所有持有者，再标记每条引用的所有权，检查 new、borrowed、steals reference 的转移关系，并覆盖成功、失败、异常和回调路径。普通对象在最后一份 strong reference 消失时立即进入销毁；只剩内部环时则需要 cyclic GC 接管。