第013章：类对象构造
==================

核心知识点
----------

``class`` 语句会创建类对象
   类定义不是静态容器声明。解释器会解析类头、准备 namespace、执行 class body、调用 metaclass 创建类对象，最后把结果绑定到外层名字。

类创建具有明确阶段
   主路径包括解析 MRO entries、确定合适的 metaclass、调用 ``__prepare__``、执行 class body、调用 metaclass、由 ``type.__new__`` 建立类型结构、完成类级回调、应用 decorators 和外层绑定。

Class body 是一次代码块执行
   类体中的赋值、``def``、descriptor 实例和 ``__slots__`` 声明先写入临时 class namespace。此时外层的类名尚未绑定到最终类对象。

类 namespace 不是方法的 enclosing scope
   类体后续语句可以读取前面写入的类名，但方法调用时普通名字仍按函数的 LEGB 路径解析。读取类属性应使用 ``self.attr``、``type(self).attr``、明确类名或 ``__class__``。

``__prepare__`` 决定类体写入容器
   Metaclass 可以返回自定义 mapping，记录声明顺序、拒绝重复名称、收集 DSL 字段或执行写入检查。它运行在最终类对象出现之前，不能依赖已经创建好的 owner class。

Metaclass 选择必须兼容所有基类
   显式 metaclass 与各基类的 metaclass 会形成候选集合，解释器选取其中可兼容的最派生类型。不存在共同候选时，类定义在执行 class body 之前或创建阶段失败。

Metaclass 调用仍遵守对象调用协议
   类体完成后，解释器近似执行 ``Meta(name, bases, namespace, **keywords)``。Metaclass 的 ``__call__`` 通常继续调用其 ``__new__`` 和 ``__init__``，最终返回类对象。

``type.__new__`` 建立真正的类型结构
   它把类名、bases 和 namespace 转换成拥有 ``__mro__``、``__dict__``、实例布局、slot 和 descriptor 状态的类对象。类 ``__dict__`` 对外暴露为 mapping proxy，属性修改仍通过类型对象的设置路径完成。

``__set_name__`` 在类创建时通知 descriptor
   ``type.__new__`` 扫描原始 class namespace，把最终 owner 和属性名传给定义了 ``__set_name__`` 的对象。类创建后动态添加 descriptor 不会自动补调该回调。

``__init_subclass__`` 在父类侧处理新子类
   新类对象创建后，其直接父类链可以通过 ``__init_subclass__`` 接收类头额外关键字、做校验、登记或默认属性设置。它适合影响子类定义，不负责创建普通实例。

``__slots__`` 改变实例布局
   ``__slots__`` 会让 ``type.__new__`` 为指定名称建立 slot descriptor，并可能省略普通实例 ``__dict__`` 与 ``__weakref__``。它不是简单的字段白名单，而是类型级内存布局声明。

``__classcell__`` 连接方法与最终类对象
   方法体使用零参数 ``super()`` 或 ``__class__`` 时，编译器会要求 class namespace 保留 ``__classcell__``。自定义 metaclass 必须把它传给 ``type.__new__``，否则最终绑定无法完成。

Class decorators 处理已经创建的类对象
   Decorator 在类对象及相关创建回调完成后按逆序调用，其返回值成为外层类名最终绑定的对象。Decorator 可以替换类对象，不能改变已经执行过的 class body。

关键路径
--------

完整类创建路径：

::

   解析 class 头部与 bases
   → 处理 __mro_entries__
   → 选择兼容 metaclass
   → metaclass.__prepare__(name, bases, **keywords)
   → 执行 class body 并填充 namespace
   → metaclass(name, bases, namespace, **keywords)
   → metaclass.__new__ / type.__new__ 创建类对象
   → 调用 namespace 中 descriptor 的 __set_name__
   → 调用父类 __init_subclass__
   → metaclass.__init__ 完成类对象初始化
   → 依次应用 class decorators
   → 把结果绑定到外层类名

``__class__`` cell 路径：

::

   编译器发现零参数 super() 或 __class__
   → 在 class namespace 放入 __classcell__
   → metaclass 保留并传递该 cell
   → type.__new__ 创建最终类对象
   → 把类对象写入 cell
   → 方法 closure 通过 cell 取得实际 owner class

概念辨析
--------

* **Class body 与类对象**：class body 是创建期间执行的代码块；类对象是执行结果经过 metaclass 构造后的运行时对象。
* **Class namespace 与方法作用域**：前者收集类属性；后者执行时不会把类字典自动加入 LEGB。
* **``__prepare__`` 与 ``__new__``**：前者准备类体写入容器；后者接收已填充 namespace 并创建类对象。
* **Metaclass ``__new__`` 与类 ``__new__``**：前者创建类对象；后者在该类被调用时创建普通实例。
* **``__set_name__`` 与 ``__init_subclass__``**：前者通知类字典中的单个声明对象；后者让父类处理整个新子类。
* **``__slots__`` 与实例字段限制**：它首先改变实例布局和存储机制，是否允许其它属性取决于继承链是否仍提供 ``__dict__``。
* **Class decorator 与 metaclass**：decorator 接收已经创建的类对象；metaclass 参与类对象本身的生成过程。

本章结论
--------

定位类定义行为时，应按“类头解析 → namespace 准备 → class body 执行 → metaclass 构造 → 类级回调 → decorator → 外层绑定”逐段检查，并明确每个 hook 能看到的对象状态；只有分清类体、类对象和普通实例的创建阶段，才能正确使用 metaclass、descriptor、``__slots__`` 与 ``__init_subclass__``。
