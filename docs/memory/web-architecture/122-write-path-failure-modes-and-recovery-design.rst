Write Path Failure Modes and Recovery Design
============================================

核心知识点
----------

* 写入恢复设计的目标不是“显示错误”，而是同时保护用户意图、持久化事实和下一步可执行动作。
* Validation failure 应保留用户输入并把错误定位到字段、跨字段规则或业务状态；文本草稿、附件临时引用和目标上下文应有独立生命周期。
* Auth failure 要区分 401 身份失效与 403 授权不足；重新认证后必须重新检查目标资源和权限，不能直接重放旧请求假设。
* Conflict failure 表示请求基于的资源事实已经变化；稳定恢复依赖 base version、current version、用户修改集和可合并策略。
* Partial failure 出现在数据库、对象存储、支付、队列、邮件等多个系统边界不能原子提交时；需要事务、outbox、状态机、补偿动作或显式 intermediate state。
* Timeout / network failure 可能属于“结果未知”，客户端不能据此判定写入失败；应通过 idempotency key、operation id 或 status endpoint 查询最终状态。
* Offline/queued mutation 必须展示持久的 pending identity、重试条件与冲突规则，避免用户把“已排队”理解为“已提交成功”。
* Recovery 设计应记录 request/mutation id、资源版本、已完成副作用和错误类型，使客服、日志、trace 与 UI 能还原同一写入。

关键路径
--------

``User Intent`` → 保存可恢复草稿与 mutation identity → submit → schema / validation → auth / authorization → version / conflict check → transaction 与外部副作用 → 根据失败位置分类：字段修正、重新认证、冲突合并、补偿、状态查询或排队重试 → 返回结构化 recovery result → UI 保留仍有效输入 → 重新获取当前事实 → 用户确认或系统安全重试 → 最终收敛到明确成功/失败状态。

多系统写入中，要显式标记每一步是否已经提交。例如“附件已上传、ticket 未创建”“订单已创建、通知失败”“支付 provider 已成功、客户端超时”都应成为可观察状态，而不是被统一成 500。

概念辨析
--------

* **validation failure vs conflict**：前者表示输入不满足当前规则；后者表示输入所依赖的资源版本已经变化。
* **authentication vs authorization failure**：前者需要重新证明身份；后者说明身份已知但不允许当前动作。
* **failure vs unknown outcome**：明确失败表示系统确认 mutation 未成立；超时/断网可能只是调用方不知道最终结果。
* **rollback vs compensation**：rollback 撤销同一事务内未提交变化；compensation 用新的业务动作抵消已经跨系统提交的副作用。
* **queued vs committed**：进入离线队列或后台任务只表示后续会尝试执行，不等于 durable business state 已成立。

本章结论
--------

稳定写入系统必须让每类失败都有与其边界匹配的恢复路径：校验问题修输入，认证问题恢复身份，冲突问题重新对齐事实，部分失败执行补偿，不确定结果查询状态，离线任务保持明确排队身份。只返回统一错误码，会丢掉真正决定能否恢复的系统状态。