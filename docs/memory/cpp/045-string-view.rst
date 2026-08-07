第045章：String View
===================

核心知识点
----------

* ``std::string_view`` 是 non-owning character range，核心状态可理解为字符起始地址与长度；它不拥有字符存储。
* ``string_view`` 适合只读字符串接口、解析切片、查找和比较，避免为了读取已有字符而构造新的 ``std::string``。
* ``std::string`` 表达所有权、分配和可修改存储；``string_view`` 只表达“观察哪一段字符”。
* ``string_view`` 可引用字符串字面量、``std::string``、字符数组以及显式 ``pointer + length`` 缓冲区。
* ``data()`` 只返回起点，``size()`` 才定义视图边界；视图覆盖的数据不保证在 ``data()+size()`` 处有 null terminator。
* ``substr``、``remove_prefix``、``remove_suffix`` 只调整视图边界，不移动、不复制底层字符。
* ``string_view`` 可以覆盖中间含 ``\0`` 的字符序列；长度语义独立于 C 字符串终止规则。
* 最大风险是生命周期：临时 ``std::string``、局部 string、重新分配后的 string/vector buffer 都可能让已有 view 悬垂。
* 保存 ``string_view`` 成员意味着对象依赖外部字符存储长期存在；无法保证外部存储时应复制为 ``std::string``。
* ``string_view::data()`` 不能无条件传给只接受 null-terminated ``const char*`` 的 C API；必要时构造拥有式 ``std::string`` 或使用带长度接口。

关键路径
--------

1. 先判断接口是否需要拥有或修改字符；需要所有权时使用 ``std::string``。
2. 只读且调用期间已有稳定字符存储时，可按值接收 ``std::string_view``。
3. 创建子串时优先保留 view，避免无意义字符复制。
4. 每个 view 都反向追踪到底层 owner：字面量、string、数组、网络缓冲区或其他存储。
5. 若 view 被返回、保存为成员、跨线程或延迟使用，重新验证 owner 是否覆盖完整使用期。
6. 若 owner 可能扩容、重分配、移动或销毁，相关 view 必须视为失效。
7. 与 C API 交互时同时检查 null terminator 和长度契约，不能只依据 ``data()``。

概念辨析
--------

* **string 与 string_view**：string 拥有字符并管理容量；string_view 只保存一段字符范围的位置和长度。
* **string_view 与 ``const char*``**：前者自带长度且不要求终止符；后者通常依赖额外长度或 ``\0`` 约定。
* **view copy 与 data copy**：复制 string_view 只复制视图状态，不复制字符。
* **substr 与 string::substr**：string_view 的 ``substr`` 产生新视图；string 的 ``substr`` 通常产生拥有式字符串结果。
* **non-owning 与 immutable**：string_view 不拥有数据，并不意味着底层存储永远不变；外部修改可能改变 view 看到的内容或直接使它失效。
* **静态字面量与临时 string**：字面量具有静态存储期，适合长期 view；临时 string 的字符存储会很快销毁，不能被长期引用。

本章结论
--------

``std::string_view`` 的判断核心是“谁拥有字符、视图会用多久、底层地址会不会变化、接口是否依赖终止符”。它非常适合短期只读参数和零拷贝解析，但长期保存、返回临时对象切片或跨 C 接口时必须把生命周期和 null-termination 当作一级约束。