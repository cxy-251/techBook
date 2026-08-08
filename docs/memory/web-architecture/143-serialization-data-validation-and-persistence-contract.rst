第143章：Serialization, Data Validation, and Persistence Contract
==================================================================

核心知识点
----------

* Persistence contract 定义 runtime value 如何变成长期可存储、可查询、可迁移、可再次输出的数据；input shape、domain shape、storage shape 和 output shape 可以不同。
* Date、decimal、money、enum、JSON、binary、nullable、id、timezone、Unicode/encoding 等值进入存储前必须有稳定表示，不能依赖语言或框架的默认序列化行为。
* 金额应明确 currency 与精度；时间应明确时区/UTC 与业务语义；``undefined``、``null``、缺字段应有不同含义时必须显式映射。
* Validation 必须匹配边界。Browser validation 提供即时反馈；API validation 保护 request shape；domain validation 判断业务规则；database constraint 保护最终完整性。
* 第三方 callback、Webhook 和上传 metadata 还需要验证来源、签名、timestamp、event id、幂等性与本地业务关联。
* Database constraint 是最后数据完整性防线。Unique、foreign key、not null、check、range 等不变量不应只依赖前端或单个 service 的校验。
* TypeScript/schema library 能减少开发期错误，但不能替代数据库约束、历史数据兼容和 runtime input validation。
* Serialization bug 会成为 long-lived data bug。时区偏差、浮点误差、enum 改名、JSON 丢字段、错误 nullable、字符编码等一旦写入库，会污染后续 API、缓存、报表和迁移。
* 持久化映射应显式完成 ``Input → Domain → Row/Document``，读取时再 ``Row/Document → Domain/View``；不要把 request object 或 ORM row 直接当全局模型。
* Persistence contract 必须与 API contract、cache contract 和 migration strategy 兼容；字段类型“对得上”不代表语义一致。
* 写入后仍需确认数据库生成值、default、trigger、version、timestamp 与派生字段，再据此更新 cache/UI，而不是盲信提交前对象。

关键路径
--------

写入转换：

::

   browser/raw input
   → request schema validation
   → normalized command
   → domain validation + business meaning
   → explicit serialization/mapping
   → database row/document
   → constraints + generated/default values
   → read committed result
   → API/cache/UI projection

数据完整性防线：

::

   client feedback
   → API shape validation
   → domain invariant validation
   → transaction
   → database constraints
   → post-write verification

概念辨析
--------

* **Serialization 与 Validation**：serialization 决定如何表示值，validation 决定该值是否允许跨越当前边界。
* **Input Shape 与 Storage Shape**：表单/JSON 适合传输和交互，数据库结构适合持久化和查询，不应强制相同。
* **Application Validation 与 Database Constraint**：前者改善错误体验和业务判断，后者保护所有写入路径的最终完整性。
* **Null 与 Missing**：``null`` 可表示明确无值，missing 可表示未提供；若语义不同必须保留区别。
* **Type Correct 与 Semantically Correct**：字符串、数字类型正确，仍可能代表错误时区、错误货币或错误业务状态。

本章结论
--------

稳定持久化应按 ``Meaning → Validation → Representation → Constraint → Read-Back → Projection`` 设计。数据一旦进入长期存储就会被未来代码持续消费，因此序列化和验证不是边缘实现细节，而是数据库、API、缓存和迁移共同依赖的长期契约。
