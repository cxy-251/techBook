第015章：元类系统
================

核心知识点
----------

Metaclass 是类对象的类型
   普通实例由类创建，类对象由 metaclass 创建。对实例 ``obj``，``type(obj)`` 返回其类；对类对象 ``C``，``type(C)`` 返回创建和解释该类对象的 metaclass，默认通常是 ``type``。

实例关系与继承关系必须分开
   ``obj → C → Meta`` 描述对象的类型归属，``C → Base → object`` 描述类的继承和属性查找。Metaclass 负责类对象这一层，MRO 负责基类这一层。

``type`` 完成多数类对象的自举
   ``type(object) is type``、``type(type) is type`` 且 ``type`` 继承 ``object``。这组关系由解释器启动阶段建立，使后续用户类都能落入统一对象模型。

三参数 ``type`` 可以动态创建类
   ``type(name, bases, namespace)`` 接收类名、直接基类和类 namespace，返回新的类对象。Namespace 中的函数进入类字典后仍会通过 descriptor 形成实例方法。

自定义 metaclass 通常继承 ``type``
   ``__prepare__`` 准备 class body 的 mapping，``__new__`` 接收已填充 namespace 并创建类对象，``__init__`` 在类对象产生后补充初始化，``__call__`` 在类对象被调用时控制普通实例创建。

Metaclass 逻辑主要发生在类定义阶段
   注册、字段收集、命名检查和类型结构改写会在模块导入或 class statement 执行时发生。异常定位应回到类声明和 metaclass hook，而不是等到业务实例使用阶段。

Metaclass 选择遵循共同最派生规则
   显式 metaclass 与所有直接基类的 metaclass 构成候选集合。解释器必须找到一个同时是其它候选子类的类型；不存在时抛出 metaclass conflict ``TypeError``。

组合 metaclass 可以解决兼容冲突
   当两个基类分别使用 ``MetaA`` 与 ``MetaB`` 时，可定义同时继承二者的 ``MetaAB``，前提是它自身的 MRO 和行为也能兼容。修复不是忽略冲突，而是显式合并两套类创建规则。

动态建类必须选择正确的创建者
   直接调用自定义 metaclass ``Meta(name, bases, namespace)`` 会复用其注册和检查逻辑；改用默认 ``type`` 会绕过这些规则。``types.new_class`` 可包装 metaclass 选择、namespace 准备和类创建流程。

修改类属性会影响后续实例行为
   给类动态添加函数、descriptor 或 special method，会改变之后的属性查找和协议分发。CPython 需要使类型缓存、slot 和版本状态保持一致。

修改 ``__class__`` 或 ``__bases__`` 受布局约束
   这类操作会改变类型关系、实例布局假设、MRO 或 slot，只有兼容对象才能成功。失败通常抛出 ``TypeError``，工程上不应把它当作普通业务扩展机制。

类调用由 metaclass ``__call__`` 接管
   表达式 ``C(args)`` 实际先进入 ``type(C).__call__(C, args)``。默认 ``type.__call__`` 再调用 ``C.__new__`` 创建实例，并在结果适配时调用 ``C.__init__``。

Metaclass 应在必要时使用
   若需求只涉及子类登记、单个字段管理或类对象后处理，优先考虑 ``__init_subclass__``、descriptor 或 class decorator。Metaclass 适合确实需要改变整个类族创建规则的场景。

关键路径
--------

自定义类创建：

::

   解析 class 头与 bases
   → 收集显式 metaclass 和各基类 metaclass
   → 选出共同最派生 metaclass
   → Meta.__prepare__ 创建 namespace
   → 执行 class body
   → Meta.__call__(name, bases, namespace, keywords)
   → Meta.__new__ / type.__new__ 创建类对象
   → Meta.__init__ 初始化类对象
   → 外层名字绑定到类对象

普通实例创建：

::

   调用类对象 C(args)
   → type(C).__call__(C, args)
   → 默认路径调用 C.__new__(C, args)
   → 得到实例对象
   → 若实例属于 C 的类型体系，调用 C.__init__(instance, args)
   → 返回实例

Metaclass 冲突排查：

::

   列出每个直接基类
   → 计算 type(Base)
   → 加入显式 metaclass 候选
   → 检查候选之间的子类关系
   → 选共同最派生者
   → 无共同候选时定义兼容组合或重构类层级

概念辨析
--------

* **类与 metaclass**：类创建普通实例；metaclass 创建和管理类对象。
* **Metaclass 与基类**：metaclass 决定类对象如何产生；基类决定新类的继承内容和 MRO。
* **Metaclass ``__call__`` 与类 ``__call__``**：前者拦截 ``C()`` 的实例化过程；后者是实例自身被调用时的协议方法。
* **``type(name, bases, dict)`` 与 ``class`` 语句**：前者是动态创建核心接口；后者还负责类头解析、namespace 准备、class body 执行和 decorator 等完整流程。
* **Class decorator 与 metaclass**：decorator 接收已经创建的类对象；metaclass 参与该对象创建之前和创建期间的规则。
* **``__init_subclass__`` 与 metaclass**：前者让父类处理直接子类；后者可以控制整个类对象构造协议和实例化入口。
* **MRO 冲突与 metaclass 冲突**：MRO 冲突来自基类顺序约束；metaclass 冲突来自候选类创建者不兼容。
* **动态类属性修改与动态类型重构**：添加方法属于类 namespace 修改；替换 ``__bases__`` 或 ``__class__`` 会触及布局和类型关系，风险更高。

本章结论
--------

分析 metaclass 代码时，应先分清类定义阶段和实例创建阶段，列出所有候选 metaclass，再沿 ``__prepare__ → __new__ → __init__ → __call__`` 判断每个 hook 改变的对象；只有确实需要统一控制类对象构造规则时才引入 metaclass，其余需求应优先落到更局部的扩展点。
