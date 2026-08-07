第053章：Serialization Boundary
===============================

核心知识点
----------

* serialization boundary 的核心问题是：对象离开当前进程后，哪些值、类型、共享关系和行为还能被恢复。
* ``json`` 表达跨语言值结构：object/array/string/number/boolean/null；它不自动保存 Python class、method、descriptor 或对象身份。
* Python rich object 进入 JSON 前通常需要显式投影成 schema，例如 ``datetime → ISO 字符串``、``Decimal → 十进制字符串``、``bytes → base64``。
* JSON 反序列化只恢复值结构；字段含义、版本、类型转换和业务验证由协议层负责。
* JSON 默认不保留共享引用：同一个 list 在两个位置出现，load 后通常得到内容相等但 identity 不同的两个对象。
* ``pickle`` 面向 Python object graph，能记录 memo，因此可以恢复共享引用和循环引用。
* pickle 对普通 class 常依赖“模块名 + 全局名字”定位类型；类移动、重命名或环境缺失会破坏恢复。
* pickle 可以执行对象重建逻辑，unpickle 不可信数据可能导致任意代码执行；只能用于可信边界。
* ``__getstate__``、``__setstate__``、``__reduce__`` 等协议可以控制 pickle 的状态与重建过程，也会增加兼容责任。
* ``marshal`` 服务 CPython 内部值和 ``.pyc`` / code object 等内部格式，不是稳定业务持久化协议。
* marshal 格式和 code object 强依赖解释器版本；跨版本持久化和不可信输入都不适合用它承担。
* ``struct`` 不是对象图序列化器，而是“显式二进制布局”工具：调用方必须指定字段顺序、字节序、宽度和对齐。
* ``struct.pack`` / ``unpack`` 适合网络协议、文件头、固定记录等稳定 binary schema；它不保存 Python 类型名或对象关系。
* serialization 会跨越 identity boundary：恢复对象通常是新对象；只有协议显式编码 alias/reference 时共享关系才可能恢复。
* 长期格式应显式记录 schema/version，避免把当前 Python class layout 当成永久协议。
* 选择方案时应按“信任边界 → 跨语言要求 → 是否需要对象图 → 版本寿命 → 性能/体积”排序，而不是只看编码速度。

关键路径
--------

JSON 路径：

::

   rich Python object
       ↓
   explicit schema projection
       ↓
   dict / list / str / number / bool / None
       ↓
   json.dumps
       ↓
   text boundary
       ↓
   json.loads
       ↓
   generic Python values
       ↓
   validate + reconstruct domain object

pickle 路径：

::

   Python object graph
       ↓
   pickle traversal + memo
       ↓
   type/global references + state
       ↓
   binary pickle stream
       ↓
   trusted unpickle only
       ↓
   import/find reconstruction targets
       ↓
   rebuild objects + alias/cycles

``struct`` 路径：

::

   explicit fields
       ↓
   choose format / byte order / widths
       ↓
   struct.pack
       ↓
   fixed binary bytes
       ↓
   struct.unpack
       ↓
   primitive tuple
       ↓
   business-level interpretation

概念辨析
--------

* **值序列化与对象图序列化**：JSON 保存值结构；pickle 能保存 Python 对象图和共享关系。
* **对象相等与对象身份**：反序列化后 ``==`` 可成立，``is`` 通常不成立；identity 必须由协议明确表达。
* **schema 与 class**：schema 是外部数据合同；class 是当前运行时实现对象，两者不应默认一一绑定。
* **pickle 与安全**：pickle 的风险来自加载阶段可能执行重建逻辑，不是简单“二进制格式不透明”。
* **marshal 与 pickle**：marshal 面向解释器内部有限值格式；pickle 面向一般 Python object graph。
* **struct 与 serializer**：struct 只按格式串布局原始字段，不知道 domain type、版本和引用关系。
* **编码兼容与业务兼容**：格式仍能解析，不代表字段语义、单位、默认值和类型迁移仍兼容。

本章结论
--------

Serialization boundary 可以压缩为“先决定跨边界要保留哪一层语义，再选择格式”。跨语言值结构用 JSON，可信 Python 对象图可用 pickle，解释器内部格式才考虑 marshal，固定二进制协议用 struct。设计时最先检查信任边界和版本寿命，然后确认 identity、共享引用、类型恢复和 schema 演进是否需要显式编码。