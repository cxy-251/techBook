API Boundary as a Contract Between Independent Runtimes
========================================================

核心知识点
----------

* API boundary 存在于独立 runtime 之间；browser、edge、server、service 各自拥有独立内存、权限、生命周期和部署节奏，跨边界通信只能依赖可传输 representation。
* API contract 至少覆盖 request shape、response shape、error shape、auth requirement、side effect、serialization 与 compatibility guarantee；handler 参数列表或 TypeScript 类型本身不是完整 contract。
* 浏览器提交的是用户意图，服务器负责恢复身份、重新校验、授权、执行业务规则并产生 durable state；客户端不能把价格、权限、tenant、内部状态等自己提交的字段当成可信事实。
* 独立部署意味着新服务器必须面对旧 bundle、旧 Service Worker、旧 SDK 和旧调用假设；contract 稳定性是运行时兼容问题，不只是代码仓库内的类型问题。
* serialization 是暴露边界。Date、BigInt、Error、File、Stream、Map 等运行时对象必须转成稳定的跨运行时表示，并明确精度、时区、null/缺失、未知枚举和错误语义。
* error contract 必须支持恢复。HTTP status 提供粗粒度控制信号，稳定的 error code、field error、request id、retryability 与 conflict detail 决定客户端如何继续。

关键路径
--------

``User Intent → Browser State → Request Contract → Network/Edge → Server Validation/Auth → Domain/Database → Response Contract → Client Cache/UI``。

请求方向把 UI 状态压缩成服务端可验证的意图；响应方向把服务器事实裁剪成客户端可安全观察的 representation。任何内部对象、secret、数据库字段和异常对象在跨过 serialization boundary 前都必须被重新塑形。

版本演进时沿 ``Old Client → New Server`` 与 ``New Response → Old Client`` 两个方向检查。新增 optional 字段通常较安全；新增 required 输入、删除字段、改变字段语义、副作用或错误结构都可能成为 breaking change。

概念辨析
--------

* **API contract vs 类型定义**：类型定义约束某段代码；API contract 约束独立运行时之间真实可观察的协议行为。
* **representation vs domain object**：representation 是跨边界数据形状；domain/database object 可以包含更多内部状态，不能直接等同于公共响应。
* **HTTP success vs business success**：2xx 表示 HTTP 层成功处理；业务结果仍可能需要资源状态、版本、next action 等字段才能闭环。
* **compile-time compatibility vs runtime compatibility**：前者由类型检查发现；后者还受旧客户端、缓存、序列化、权限、数据和部署时间差影响。

本章结论
--------

API 的本质是独立 runtime 之间的长期契约。稳定接口必须同时定义可跨边界的输入、输出、错误、安全、序列化和演进规则，并把可信判断与 durable state 保留在服务器边界内。