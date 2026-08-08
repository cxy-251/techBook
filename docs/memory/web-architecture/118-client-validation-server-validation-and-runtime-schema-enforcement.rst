Client Validation, Server Validation, and Runtime Schema Enforcement
====================================================================

核心知识点
----------

* 校验分三层：client validation 提供快速反馈，server validation 建立可信判断，runtime schema 把未知输入转换成后续代码可以依赖的 checked data。
* 浏览器中的 ``required``、``type``、长度、pattern 和即时提示服务 UX；用户可以绕过 DOM、JavaScript 和 TypeScript，因此这些规则不能保护数据库或权限边界。
* 服务端必须重新检查 body、params、headers、cookies、session、CSRF、rate limit、tenant、权限和业务规则；所有来自外部 runtime 的输入都应视为不可信。
* runtime schema 应靠近边界入口，把 ``unknown`` 解析为稳定数据形状；TypeScript 静态类型不能证明网络中的真实 payload。
* schema 适合类型、长度、枚举、格式、结构与基础转换；唯一性、库存、余额、资源归属和并发版本属于业务/持久化约束。
* 数据库约束是最终一致性防线之一：客户端和服务端预检查都可能在并发窗口后失效，唯一索引、外键和事务必须能够拒绝最终冲突。
* 错误结果应区分 field error、business error、auth/permission error、conflict 和 infrastructure error，让 UI 能恢复到正确位置。

关键路径
--------

``User Input`` → browser constraint / client feedback → submit request → server 把输入视为 ``unknown`` → runtime schema 解析 → request context 校验（session / CSRF / rate / tenant）→ business rules → database constraints / transaction → structured result → UI 将字段错误放回控件、业务错误放回流程、系统错误提供重试或故障反馈。

稳定顺序应尽量让廉价且确定的检查靠前：shape → request context → business rule → transaction。这样可以避免在输入已经确定无效时触发数据库、邮件、支付或其他副作用。

概念辨析
--------

* **client validation vs trust**：客户端校验减少无效提交，不建立安全边界。
* **TypeScript type vs runtime schema**：前者约束开发期代码，后者检查真实运行时数据。
* **schema validation vs domain validation**：schema 判断数据能否解释；domain validation 判断该数据在当前业务上下文是否允许。
* **pre-check vs database constraint**：预检查改善错误体验；数据库约束处理最终并发事实。
* **field error vs business error**：字段错误通常能由用户修改单个输入修复；业务错误可能需要刷新资源、重新认证、等待或改变流程。

本章结论
--------

可靠校验不是把同一套规则复制三遍，而是按运行位置分工：浏览器负责即时反馈，schema 负责收束未知输入，服务器与数据库负责最终信任和业务事实。任何真正影响持久化状态的规则，都必须在可信边界内再次成立。