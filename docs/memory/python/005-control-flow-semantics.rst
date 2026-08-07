第005章：控制流语义
==================

核心知识点
----------

控制流由运行时对象状态驱动
   ``if`` 和 ``while`` 依赖 truth value，``for`` 依赖 iterator 状态，``match`` 依赖 subject、pattern 与 guard，异常路径依赖异常对象和 handler，``with`` 退出依赖 context manager 协议。

``if`` 与 ``while`` 的判断次数不同
   ``if`` 按源码顺序求条件并选择第一个真值分支；``while`` 在每轮入口重新求条件。条件表达式中的属性访问、调用和副作用只在实际到达该条件时发生。

``for`` 由 iterator 推进
   ``for`` 先求值 iterable 并创建 iterator，之后反复取得下一个对象并绑定 target。循环体内重新绑定 iterable 的名字，不会替换已经创建的 iterator。

``continue`` 与 ``break`` 改变局部执行位置
   ``continue`` 转到最近一层循环的下一轮入口；``break`` 离开最近一层循环，并跳过该循环的 ``else``。二者不改变 iterator 协议本身。

loop ``else`` 表示自然结束
   ``for`` 的自然结束来自 iterator 耗尽，``while`` 的自然结束来自条件变假。命中当前循环的 ``break`` 时 ``else`` 不执行；``return`` 和异常则直接离开更外层控制区域。

结构匹配按 case 顺序选择
   ``match`` 只求值一次 subject，然后顺序尝试 pattern。裸名字通常是 capture pattern，会建立局部绑定；``_`` 是 wildcard；需要稳定值比较时应使用 literal 或 qualified value pattern。

guard 在 pattern 成功后求值
   ``case pattern if guard`` 先完成结构匹配和捕获，再求 guard。guard 为假时继续尝试后续 case，guard 抛出异常时直接进入异常路径。

清理逻辑覆盖多种退出方式
   ``finally`` 和 context manager 退出协议会在正常结束、``return``、循环跳转或异常传播等离开路径上运行。清理代码自身产生的新控制流可能替换原有返回或异常。

关键路径
--------

迭代与 loop ``else``：

::

   求值 iterable
   → 创建 iterator
   → 取得下一个对象并绑定循环 target
   → 执行 body
   → continue 返回取值点或 break 进入循环出口
   → iterator 耗尽时形成自然结束
   → 仅自然结束执行 loop else

匹配、异常与清理：

::

   求值 match subject
   → 按顺序尝试 pattern
   → pattern 成功后求 guard
   → 执行选中 case 或抛出异常
   → 异常沿 frame 查找 handler
   → 离开控制区域前执行 finally 或 context manager 退出逻辑
   → 返回正常路径、抑制异常或继续传播

概念辨析
--------

* **iterable 与 iterator**：iterable 能产生 iterator；iterator 保存当前推进状态，并用 ``StopIteration`` 表示耗尽。
* **``break`` 与自然耗尽**：``break`` 是主动提前退出；自然耗尽是 iterator 或条件自己报告结束，只有后者触发 loop ``else``。
* **pattern 与 guard**：pattern 检查结构并捕获值；guard 在匹配成功后执行额外布尔约束。
* **capture pattern 与 value pattern**：裸名字通常建立新绑定；literal 或带限定路径的名字用于与既有值比较。
* **handler 与 cleanup**：``except`` 决定是否处理异常；``finally`` 和 ``__exit__`` 负责离开路径上的收束，并可能影响最终传播结果。

本章结论
--------

追踪 Python 控制流时，应先确认当前 suite 的驱动对象，再判断跳转目标和自然结束条件，随后检查 pattern、guard、异常 handler 与清理边界；loop ``else``、``finally`` 和 ``with`` 的行为都取决于代码以何种方式离开当前控制区域。
