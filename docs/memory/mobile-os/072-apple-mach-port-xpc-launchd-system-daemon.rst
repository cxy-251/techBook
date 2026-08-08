第072章：Apple Mach Port, XPC, launchd, System Daemon
====================================================

核心知识点
----------

* Apple 平台的系统能力通常从 public Framework 进入，随后通过 XPC 或更底层的 Mach IPC 到达系统 daemon。
* Mach port 是 XNU 中的受保护通信端点，访问依赖 port right。服务端通常持有 receive right，客户端持有 send right，send-once right 常用于一次性回复。
* 每个 task 都有自己的 port namespace；port name 只是本进程中的句柄，真正可传递的是由内核管理的 port right。
* Mach message 可以携带普通数据、port right、内存描述和安全凭据，因此既能传数据，也能传递访问能力。
* ``launchd`` 管理系统服务的注册、按需启动、崩溃恢复和生命周期。Mach service name 让客户端按名字获得通信入口，而无需知道 daemon 是否已经常驻。
* XPC 把 Mach IPC 包装成高层 connection、object、dictionary、handler、reply 和 proxy 模型。``NSXPCConnection`` 适合类型化 Objective-C / Swift 接口，C XPC API 更接近消息对象。
* Apple 平台的具体 iOS daemon 名称和私有协议不是稳定公共接口；架构分析应停在 public Framework、XPC / Mach、entitlement / sandbox 与公开错误边界。

关键路径
--------

通用 Apple 服务访问链：

``App → Public Framework → XPC connection / proxy → launchd service lookup / activation → Mach IPC → System Daemon → entitlement / privacy / resource check → lower system layer``

底层能力模型：

``client send right → Mach port queue → daemon receive right → reply port / send-once right``

服务进程可以在客户端建立逻辑连接时尚未运行；第一条消息到来后由 ``launchd`` 按需启动，daemon 崩溃后客户端通过 interruption / invalidation 感知连接变化。

概念辨析
--------

* **Mach port ≠ daemon process**：port 是内核通信对象，daemon 是持有 receive right 并解释消息的用户态进程。
* **Port name ≠ global address**：port name 只在当前 task namespace 中有意义。
* **XPC ≠ Mach replacement**：XPC 是更高层的 IPC 框架，底层仍建立在系统通信原语之上。
* **Connection created ≠ service ready**：按需启动模型下，逻辑连接存在时 daemon 可能还未完成初始化。
* **Public Framework ≠ private daemon API**：第三方应用应依赖公开 Framework 契约，不依赖私有 daemon 名称和内部协议。

本章结论
--------

Apple IPC 的稳定读法是：Framework 提供公开能力表面，XPC 提供高层连接模型，Mach port / right 提供内核级能力对象，``launchd`` 负责服务发现和生命周期，daemon 最终执行授权与资源管理。分析时应围绕这些边界，而不是依赖私有实现细节。
