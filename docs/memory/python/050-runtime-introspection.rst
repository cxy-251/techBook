第050章：Runtime Introspection
==============================

核心知识点
----------

* runtime introspection 的对象是已经存在的 module、class、instance、function、method、frame、traceback、code object 等 live object。
* ``inspect`` 没有绕开 Python 对象模型；它把对象类型、signature、成员、源码位置和 frame 等可观察入口封装成标准 API。
* ``obj.__dict__`` 观察实例或模块自身存储，``type(obj).__dict__`` 与 MRO 观察类型层声明，二者和真正 ``getattr()`` 结果不是同一个问题。
* ``getattr()``、``hasattr()``、``inspect.getmembers()`` 可能触发 descriptor、``__getattribute__``、``__getattr__``，因此内省本身可能执行用户代码。
* ``inspect.getattr_static()`` / ``getmembers_static()`` 尽量绕开动态属性求值，适合文档、schema、插件扫描和低副作用检查，但可能返回 descriptor 本体。
* ``inspect.signature()`` 把 callable 的参数名、参数种类、默认值、annotation 和返回 annotation 转成 ``Signature`` 对象。
* ``Signature.bind()`` / ``bind_partial()`` 按真实调用规则把 args/kwargs 映射到参数，是调用前契约检查，不会执行函数体。
* decorator 会改变外部可见 callable；``__wrapped__`` 决定 ``inspect.signature()`` 等工具能否继续追踪被包装对象。
* frame 保存当前执行状态，包括 code、globals、locals、caller relation、当前行和 tracing 状态；它是动态现场，不是函数的静态定义。
* ``frame.f_back`` 表达调用者关系，``frame.f_code`` 指向当前 code object，``f_locals`` / ``f_globals`` 暴露当前命名空间视图。
* 持有 frame 会同时持有 locals、globals 以及调用链上的对象，可能形成引用环并延长大量对象生命周期；短期观察后应尽快释放引用。
* source inspection 依赖 ``__file__``、loader、linecache、code object 元数据等；动态生成、REPL、冻结模块、C builtin 并不保证能恢复源码文本。
* ``sys.settrace()`` 产生 call/line/return/exception 等细粒度事件，适合 debugger、coverage；``sys.setprofile()`` 更偏 call/return 与 C call 事件，适合 profiler。
* trace/profile hook 运行在真实执行路径上，会带来明显开销，并可能改变时序、递归和异常观察结果。
* 内省结果属于 runtime 事实，静态分析结果属于源码/类型工具事实；动态属性、猴子补丁、运行时注册表等会让两者出现差异。

关键路径
--------

对象成员检查：

::

   runtime object
       ↓
   inspect type(obj) / instance storage
       ↓
   inspect type.__dict__ + MRO
       ↓
   identify descriptor or declared member
       ↓
   choose static lookup or dynamic getattr
       ↓
   observe descriptor / getattr side effects
       ↓
   interpret resulting object

signature 路径：

::

   callable object
       ↓
   inspect.signature()
       ↓
   follow __wrapped__? / read callable metadata
       ↓
   Signature(parameters, return_annotation)
       ↓
   bind(args, kwargs)
       ↓
   BoundArguments or TypeError

frame 观察路径：

::

   running function
       ↓
   current frame
       ↓
   f_code / f_locals / f_globals / f_back
       ↓
   read diagnostic information
       ↓
   release frame reference
       ↓
   normal object lifetime resumes

概念辨析
--------

* **静态成员与动态属性值**：类字典中的 descriptor 是结构；``getattr(instance, name)`` 得到的是协议执行后的运行时结果。
* **function 与 frame**：function 是可重复调用对象；frame 是某一次调用的动态执行状态。
* **code object 与 source code**：code object 保存已编译执行描述；源码文本需要额外文件/loader/linecache 支持。
* **signature 与类型检查**：signature 描述调用形状并能绑定参数，不会验证业务值是否满足 annotation。
* **``dir()`` 与 ``__dict__``**：``dir()`` 是可发现名字集合；``__dict__`` 是某个对象层级真实存储的映射。
* **``hasattr`` 与声明检查**：``hasattr`` 会执行属性访问；要确认类是否声明成员，应优先检查静态结构。
* **trace 与 profile**：trace 更细粒度并常含 line events；profile 事件更粗，主要服务调用统计。
* **内省与无副作用**：内省不是天然只读；动态属性、descriptor、hook 和 frame 持有都可能影响程序行为或生命周期。

本章结论
--------

Runtime introspection 可以压缩为“从 live object 出发，选择观察入口，再判断该入口会不会执行协议或持有执行现场”。排查框架和调试工具时，应先区分实例存储、类型结构、动态属性、signature 与 frame，再确认 source/hook 的实现边界。只要把“观察什么对象”和“观察是否会改变执行”分开，``inspect``、signature、frame、trace 与动态属性就能落到同一套运行时模型中。