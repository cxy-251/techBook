第012章：函数对象内部结构
========================

核心知识点
----------

``def`` 执行会创建 function object
   函数定义不是静态声明。模块、函数或类体执行到 ``def`` 时，会把已编译的 code object 与当前 globals、defaults、closure 和元数据组合成新的 function object，再把名字绑定到该对象。

Code object 与 function object 职责不同
   Code object 保存参数布局、局部变量名、常量、字节码、源码位置和闭包变量信息，描述“执行什么”；function object 保存运行环境、默认值、闭包、注解和调用入口，描述“在什么状态下执行”。

同一个 code object 可以生成多个函数对象
   嵌套 ``def`` 每执行一次都能创建新的 function object。多个闭包可以共享同一 ``__code__``，同时持有不同 ``__closure__``，因此执行逻辑相同而状态互相独立。

Function object 聚合调用所需状态
   常见属性包括 ``__globals__``、``__builtins__``、``__name__``、``__qualname__``、``__code__``、``__defaults__``、``__kwdefaults__``、``__closure__``、``__annotations__`` 和 ``__dict__``。CPython 内部还保存 vectorcall 等调用状态。

默认参数在函数创建时求值
   ``__defaults__`` 保存普通参数默认对象，``__kwdefaults__`` 保存关键字专用默认对象。它们保存对象引用并被后续调用复用，因此可变默认容器会跨调用共享修改结果。

注解与自定义元数据不自动约束调用
   ``__annotations__`` 服务类型工具、检查框架和文档系统，``__dict__`` 可保存框架附加状态。解释器通常不会仅因注解不匹配而拒绝调用；运行时校验来自主动读取注解的工具或框架。

Closure 由 cell object 保存外层绑定
   编译器把内层函数使用的外层名字记录为 free variables。创建内层 function object 时，对应绑定被装入 cell，并按 ``co_freevars`` 顺序组成 ``__closure__``。

``nonlocal`` 修改 cell 中的绑定
   Cell 保存的是绑定槽位，不是变量值的永久副本。对不可变对象执行 ``total += 1`` 会创建新对象并更新 cell；对可变对象调用原地方法则会修改 cell 当前指向的对象。

调用会创建一次执行状态
   调用 function object 时，运行时完成参数绑定、默认值补齐、closure 与 globals 接入，再为本次调用建立 frame 和局部状态。Function object 可以被重复调用，frame 是每次执行的独立状态载体。

Vectorcall 优化参数传递布局
   CPython 可用数组和关键字名元组直接传参，减少临时 tuple/dict 的构造。Vectorcall 改变内部传参成本，不改变参数绑定、异常和返回值语义。

函数作为类属性会生成 bound method
   Function object 是 non-data descriptor。通过实例读取时生成保存 ``__func__`` 与 ``__self__`` 的 method object；调用 method 时，实例自动成为原函数第一个实参。

Wrapper 会改变名字实际指向的函数对象
   装饰器返回 wrapper 后，原名字通常重新绑定到 wrapper。``functools.wraps`` 复制可见元数据并设置 ``__wrapped__``，但真实调用仍先进入 wrapper，再由其决定是否及如何调用原函数。

关键路径
--------

函数定义与调用：

::

   源码中的 def
   → 编译阶段生成 code object
   → 运行时执行 def
   → 组合 globals、defaults、closure 与元数据
   → 创建 function object
   → 名字绑定到 function object
   → 调用时执行参数绑定与默认值补齐
   → 创建 frame
   → 执行 code object
   → 返回对象或传播异常

闭包创建：

::

   编译器识别外层 cell variable 与内层 free variable
   → 外层调用建立 cell
   → 执行嵌套 def
   → 新 function object 保存 cell tuple
   → 外层 frame 结束后 cell 仍被闭包持有
   → 每次调用读取或更新 cell_contents

概念辨析
--------

* **function object 与 code object**：前者是可调用的运行时对象；后者是可被多个函数对象复用的编译结果。
* **function object 与 frame**：函数对象长期保存定义环境；frame 只代表一次具体调用的执行状态。
* **默认参数与局部变量**：默认对象在 ``def`` 执行时创建并保存；局部变量在每次调用的 frame 中建立。
* **closure 与对象复制**：closure 保存 cell 绑定，通常不复制被引用对象；多个 cell 也可以指向同一可变对象。
* **function 与 bound method**：类字典保存函数；实例读取生成绑定对象，调用时自动补入实例。
* **注解与运行时校验**：注解是元数据；除非框架主动解释，否则不会自动限制实参类型。
* **vectorcall 与调用语义**：vectorcall 是 CPython 的性能协议，不是另一套 Python 调用规则。
* **原函数与 wrapper**：装饰后公开名字可能指向 wrapper；``__wrapped__`` 只提供追踪入口，不跳过 wrapper 的实际执行。

本章结论
--------

分析函数行为时，应把编译产生的 code object、``def`` 创建的 function object、闭包持有的 cell、实例读取生成的 bound method 与调用创建的 frame 分开；默认值共享、闭包状态、装饰器和调用性能问题，都能沿这组对象关系得到准确解释。
