第051章：Typing and Runtime Boundary
====================================

核心知识点
----------

* Python type hints 主要描述“工具期望的对象关系”，CPython runtime 仍按普通对象、属性查找、调用和异常规则执行，不会自动强制 annotation。
* ``TypeVar`` 表达多个标注位置之间的类型一致性；它服务静态推导，不会在对象字段写入时自动校验值。
* ``Generic`` 让类或函数表达参数化类型关系；``Box[int]`` 这类表达式在 runtime 可形成泛型别名/参数化对象，但实例仍按普通类逻辑运行。
* ``Protocol`` 表达结构化能力：静态检查器关注对象是否拥有兼容成员，runtime 真正发生的是属性查找和方法调用。
* ``@runtime_checkable`` 只提供有限的 ``isinstance`` / ``issubclass`` 能力，核心检查是成员存在性，不等于完整验证方法签名、返回类型和业务语义。
* ``TypedDict`` 表达 dict 的键集合和键值类型；runtime 创建的实例仍是普通 ``dict``，键和值不会因为声明自动校验。
* ``Required``、``NotRequired``、``total=False`` 会留下可自省声明元数据，但元数据读取与真实数据验证是两个阶段。
* ``cast(T, obj)`` 只改变静态类型检查器对对象的视角，runtime 返回原对象本身，不转换、不复制、不验证。
* ``Any`` 会弱化静态检查传播；``object`` 则表示“未知对象”，使用前仍需通过 ``isinstance``、协议或显式解析缩窄。
* ``typing.get_type_hints()`` 用于解析 annotation，可能需要 globals/locals，并可能求值 forward reference；annotation 的存储和求值策略受 Python 版本影响。
* 参数化内置类型如 ``list[int]``、``dict[str, int]`` 在 runtime 可用于 annotation/introspection，但 ``isinstance(value, list[int])`` 不是通用 runtime 深层校验方案。
* runtime 数据边界必须显式验证：网络 payload、配置、JSON、插件数据应从 ``object`` / ``dict[str, object]`` 进入 parser，再返回可信 domain object 或 TypedDict。
* 静态类型错误的失败时间在检查阶段；runtime 类型错误只会在真实操作需要某种能力时出现，例如下标、运算、属性访问或调用。
* 类型系统适合表达契约和提高提交前反馈，runtime validator 负责处理不可信输入和真实数据安全，两层不能互相替代。

关键路径
--------

静态类型路径：

::

   source + annotations + stubs
       ↓
   type checker / IDE / linter
       ↓
   infer TypeVar / Generic / Protocol relations
       ↓
   report mismatch before execution
       ↓
   runtime code remains unchanged

真实运行路径：

::

   Python object arrives
       ↓
   name binding / attribute lookup / call / subscription
       ↓
   operation supported?
       ├─ yes → continue
       └─ no  → runtime exception

不可信数据进入可信域：

::

   external object
       ↓
   explicit parser / validator
       ↓
   check container kind
       ↓
   check required keys / members
       ↓
   check or convert values
       ↓
   construct trusted dict/domain object
       ↓
   return annotated result

概念辨析
--------

* **annotation 与 runtime constraint**：annotation 是声明信息；runtime constraint 需要显式代码、descriptor、dataclass/pydantic 类工具或其它校验机制。
* **``TypedDict`` 与 class instance**：前者描述字典结构，实例仍是 ``dict``；普通 class 实例有独立类型和属性存储。
* **``Protocol`` 与继承**：Protocol 支持 structural typing，不要求实现类显式继承协议。
* **runtime-checkable Protocol 与完整接口验证**：前者主要确认名字存在，不保证方法真正可调用或签名完全兼容。
* **``cast`` 与转换**：``cast`` 不做数据转换；真正转换需要 ``int(x)``、parser、constructor 等运行时代码。
* **``Any`` 与 ``object``**：``Any`` 基本关闭该值上的静态约束；``object`` 保留“必须先缩窄才能安全使用”的检查。
* **泛型参数与实例内容**：``Box[int]`` 的类型参数是类型系统信息，不会阻止 runtime 放入字符串等对象。
* **静态可信与外部可信**：通过 type checker 的代码仍可能接收到不符合 annotation 的网络、文件或反序列化数据。

本章结论
--------

Typing and runtime boundary 可以压缩为“类型标注描述期望关系，runtime 只执行真实对象协议；外部数据要靠显式验证进入可信域”。阅读泛型、Protocol、TypedDict 和 cast 时，先判断它是静态工具规则、runtime 可自省元数据，还是实际会执行的校验代码。只要把这三层分开，就不会把 type hint 误当成运行时安全机制。