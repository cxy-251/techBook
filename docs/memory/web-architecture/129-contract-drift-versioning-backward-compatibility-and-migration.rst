Contract Drift, Versioning, Backward Compatibility, and Migration
=================================================================

核心知识点
----------

* contract drift 指实际服务行为、正式 schema、客户端代码、generated SDK、mock、测试、文档和缓存中的接口假设逐渐分叉；结构没变但字段语义改变，同样属于 drift。
* backward compatibility 保护独立部署的旧客户端。Web bundle、Service Worker、移动端、第三方集成和 CDN 都可能长期停留在旧版本，服务器不能假设所有消费者同时升级。
* additive change 通常比 breaking change 安全：新增 optional 字段、metadata 或 endpoint 更容易渐进发布；删除字段、改变类型、改变字段语义、收紧 required、改变错误或副作用都需要迁移计划。
* 新 enum 值也可能破坏旧客户端；稳定客户端必须有 unknown/fallback 分支，服务端发布新值前应确认关键消费方能容忍。
* versioning 可以放在 URL、header、media type、schema version 或 capability negotiation 中；版本机制只是隔离手段，不能代替兼容策略与退役治理。
* migration 的稳定模式是 ``introduce → dual support → migrate consumers → observe usage → deprecate → remove``，删除旧 contract 前必须有真实使用量证据。
* cache 也属于迁移对象。字段/语义变化时需要考虑 cache key、ETag、CDN、Service Worker 和持久客户端缓存，避免新代码读取旧 representation。
* contract telemetry 应能区分 client/version/operation/error，并让团队知道哪些旧字段、版本和调用路径仍被真实使用。

关键路径
--------

``Contract Change → Spec/Schema Diff → Server Dual Support → Old + New Clients → Cache Layers → Telemetry → Deprecation Window → Removal``。

每次变更同时检查两个方向：``old request → new server`` 是否仍被接受，``new response → old client`` 是否仍可解析和安全解释。

迁移字段时优先新旧并存并保持旧语义不变；新客户端切换到新字段后，通过 telemetry 确认旧字段使用归零，再移除旧路径。若语义无法兼容，则使用显式新版本或新 capability，而不是悄悄复用旧字段名。

概念辨析
--------

* **structural compatibility vs semantic compatibility**：JSON 仍能解析不代表业务含义仍兼容；语义漂移往往更危险。
* **versioning vs migration**：versioning 提供隔离边界；migration 负责让消费者真正迁移并最终退役旧版本。
* **deprecation vs removal**：deprecation 是承诺未来移除并给出替代路径；removal 必须基于迁移完成和使用量证据。
* **server deployment vs contract rollout**：服务端发布只是一个节点；客户端、SDK、缓存、mock 和文档仍可能处于旧状态。

本章结论
--------

API contract 是持续交付对象。长期稳定依赖兼容扩展、显式版本边界、双轨迁移、缓存治理和使用量观测；破坏性变更必须经过迁移窗口，而不能依赖“大家会一起升级”的假设。