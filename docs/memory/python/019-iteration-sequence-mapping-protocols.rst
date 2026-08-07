第019章：迭代、序列与映射协议
==============================

核心知识点
----------

迭代由 iterable 与 iterator 分工
   iterable 通过 ``__iter__`` 交出 iterator；iterator 通过 ``__next__`` 保存推进状态并逐个返回元素，耗尽时抛出 ``StopIteration``。容器通常每次返回新 iterator，一次性流对象可以让 ``__iter__`` 返回自身。

``for`` 只驱动 iterator
   循环先执行 ``iter(obj)``，再重复执行 ``next(iterator)``。元素返回后绑定到循环变量，``StopIteration`` 被转换为正常结束；循环体中的其它异常继续向外传播。

旧式序列可以作为迭代 fallback
   对象缺少 ``__iter__`` 时，运行时可能从 ``obj[0]`` 开始递增整数索引，直到 ``__getitem__`` 抛出 ``IndexError``。越界返回默认值会破坏终止条件，因此兼容路径仍依赖严格的异常契约。

sequence 通过位置表达有序元素
   ``__getitem__`` 接收整数或 ``slice``。Python 会原样传入负数索引和切片对象，具体解释由类型实现；整数越界通常使用 ``IndexError``，下标类型不合适通常使用 ``TypeError``。

``slice`` 是运行时对象
   ``obj[start:stop:step]`` 会构造 ``slice(start, stop, step)`` 交给 ``__getitem__``、``__setitem__`` 或 ``__delitem__``。类型需要自行决定是否支持步长、负边界以及返回新容器还是视图。

mapping 通过 key 定位 value
   ``obj[key]`` 对 mapping 表示键查找，key 通常必须 hashable，缺失时使用 ``KeyError``。mapping 的迭代惯例是遍历 key，``in`` 的惯例也是检查 key，而不是 value。

``__missing__`` 只属于特定映射路径
   dict 子类的 ``__getitem__`` 在 key 缺失时可调用 ``__missing__``。``get``、``setdefault``、成员测试等接口不必经过它，因此不能把所有缺失策略都寄托在 ``__missing__`` 上。

成员测试有明确 fallback 顺序
   ``item in obj`` 优先调用 ``__contains__``；缺少时尝试迭代；仍缺少时可能使用从索引 0 开始的旧式 sequence fallback。类型应明确 containment 检查的是元素、key 还是其它索引关系。

长度协议参与多个行为
   ``__len__`` 服务 ``len``，也可作为 ``bool(obj)`` 的 fallback，并被 ``reversed``、预分配和边界检查利用。返回值必须是非负整数，且应与对象对外暴露的元素集合保持一致。

可变容器必须维护内部索引一致性
   实现 ``__setitem__``、``__delitem__``、插入和批量更新时，若对象同时维护顺序存储、key 索引、缓存或反向索引，所有路径都必须原子地更新同一逻辑状态，否则不同协议会观察到冲突结果。

抽象基类只提供最低接口检查
   ``Iterable``、``Iterator``、``Sequence``、``Mapping`` 等 ``collections.abc`` 类型可以表达协议类别并提供部分 mixin，但方法存在不自动保证复杂度、异常、顺序和状态语义正确。

关键路径
--------

同步 ``for`` 路径：

::

   求值 iterable
   → iter(iterable)
   → 得到保存推进状态的 iterator
   → 循环调用 next(iterator)
   → 返回元素并绑定循环变量
   → StopIteration 表示自然耗尽
   → 退出循环

subscription 路径：

::

   求值 obj 和 key
   → 调用类型的 __getitem__
   → 根据 key 类型解释为整数、slice 或 mapping key
   → 返回元素、子序列或映射值
   → 以 IndexError、KeyError 或 TypeError 表达失败边界

概念辨析
--------

* **iterable 与 iterator**：前者能产生 iterator，后者保存当前位置并能被 ``next`` 推进。
* **容器与一次性流**：容器通常支持重复取得独立 iterator；流式 iterator 耗尽后不能自动重新开始。
* **``StopIteration`` 与 ``IndexError``**：前者结束 iterator 推进，后者在旧式 sequence fallback 中结束整数索引扫描。
* **负数索引与语言保证**：语法只传递负整数，是否解释为从尾部计数由具体 sequence 实现决定。
* **sequence 与 mapping 的 ``__getitem__``**：调用入口相同，key 语义、失败异常和遍历规则不同。
* **``__contains__`` 与迭代成员测试**：前者可提供直接索引查询，后者需要逐项比较，复杂度和副作用可能不同。
* **mapping key 与 attribute name**：``obj[key]`` 进入映射协议，``obj.name`` 进入属性查找系统，两套命名空间互不等价。
* **``__missing__`` 与通用默认值**：它只参与 dict 子类的下标缺失路径，不能替代 ``get`` 或业务层默认策略。
* **ABC 注册与真实契约**：通过 ``isinstance`` 检查不代表容器的返回值、异常和复杂度已经符合调用方预期。

本章结论
--------

设计或评审容器类型时，应先确定对象是可重复容器、一次性 iterator、sequence、mapping，还是多个表面的受控组合；随后逐项检查 iterator 状态、索引类型、切片语义、key 缺失、成员测试、长度和更新一致性。协议方法之间必须描述同一个逻辑对象，否则语法虽然都能运行，调用方仍会得到互相矛盾的容器行为。
