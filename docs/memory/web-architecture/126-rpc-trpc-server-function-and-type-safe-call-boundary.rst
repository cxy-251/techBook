RPC, tRPC, Server Function, and Type-Safe Call Boundary
=======================================================

核心知识点
----------

* RPC 把远程交互表达成 procedure call，例如 ``createPost``、``submitOrder``；调用语法接近本地函数，真实路径仍跨 browser、network、server、database 与 cache boundary。
* type-safe RPC 的主要价值是减少 compile-time contract drift：procedure 名称、输入和输出可由服务端类型推导到客户端，接口改动能更早在编辑器或 CI 暴露。
* TypeScript 类型在运行时会被擦除。任何真实 request、旧 bundle、脚本、第三方客户端或恶意请求都必须经过 runtime schema validation。
* procedure 的可信顺序应是 ``deserialize → validate input → rebuild identity → authorize → domain/transaction → shape output → serialize result``；输入类型正确不代表调用者有权限。
* server function 把远程调用样板压缩到函数引用或表单 action 附近，但没有消除 HTTP、身份、CSRF、序列化、幂等、事务、缓存失效与错误恢复责任。
* RPC error 应是稳定的领域错误 contract，例如 validation、unauthorized、forbidden、conflict、transient；不能只把服务器 exception/stack 直接抛给浏览器。
* 类型安全通常依赖客户端和服务端共享版本或共享类型图；跨语言、第三方、长期独立部署场景仍需要显式 schema/version contract。

关键路径
--------

``User Intent → Typed Client Stub/Server Function Reference → Serialized Request → RPC Handler → Runtime Validation/Auth → Procedure → Database/Service → Typed Result/Error → Cache/UI``。

编译期检查只覆盖开发者写出的当前代码。运行时还要验证旧客户端和任意网络输入；写入成功后用 server-confirmed result 更新或失效 client query cache，不能把乐观预测永久当成事实。

对 server function 先还原真实部署边界：函数究竟运行在 Node、serverless、edge 还是框架 server runtime；随后检查 secret、database、cookie、cache 和 request lifecycle 是否符合该 runtime 能力。

概念辨析
--------

* **local function call vs RPC call**：前者共享进程与内存；后者存在序列化、网络、身份和失败不确定性。
* **type-safe vs runtime-safe**：静态类型减少当前源码误用；runtime schema 才能检查真实跨边界数据。
* **server function vs no API**：server function 只是框架隐藏 API boilerplate；公共输入、输出、安全和兼容责任仍存在。
* **RPC vs REST**：RPC 以动作/procedure 为中心；REST 以资源和 HTTP 语义为中心。可靠性取决于 contract 与边界设计，不取决于命名风格。

本章结论
--------

类型安全远程调用可以显著降低全栈项目的接口样板和编译期漂移，但不能把网络调用误认为本地函数。运行时校验、身份权限、事务、错误、幂等、缓存和版本边界仍必须显式成立。