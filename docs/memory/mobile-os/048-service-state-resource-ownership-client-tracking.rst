第048章：Service State, Resource Ownership, Client Tracking
===========================================================

核心知识点
----------

* Service State 是系统服务跨多次请求保存的控制数据，包括资源占用、客户端列表、策略结果、缓存、底层设备状态和待投递事件。
* 系统服务通常不是无状态 RPC；camera session、audio focus、location listener、window token、network request 都需要服务端长期记录。
* Client Registration 会把一次调用变成持续关系，服务必须保存 identity、subscription、callback、session/token 和清理规则。
* Resource Ownership 需要明确 owner 身份、资源范围、生命周期和优先级，否则 client 崩溃后容易留下“资源仍被占用”的脏状态。
* Binder death / XPC invalidation 等连接失效机制，让服务能够在客户端进程消失后自动清理 callback、session 和资源。
* Session、Token、Handle 是一次能力访问的上下文引用，不等于底层资源本身；它们把调用者、权限和服务状态绑定起来。
* 服务重启时要区分可重建状态与不可恢复状态。注册表、缓存和 provider 状态可能重建，旧 session 和 in-flight request 往往需要失效并由 client 重连。
* 状态更新应支持失败回滚，避免“服务状态已登记、底层资源却打开失败”形成不一致。

关键路径
--------

Client 生命周期：

``Register → Create client record → Bind identity/token → Start resource → Callback → Unregister / Death → Cleanup``

服务状态更新建议遵循：

#. 记录调用意图与 client identity。
#. 完成权限和策略检查。
#. 创建临时 session/client record。
#. 请求 HAL/daemon/driver 建立资源。
#. 成功后提交 active state；失败则回滚记录。
#. 异步事件先经过 client record 和当前策略过滤，再投递 callback。
#. client 死亡、权限撤销或服务重启时，统一关闭 session 并回收底层资源。

概念辨析
--------

``App object`` 与 ``Service state``：App 本地对象销毁不代表服务端状态已经释放；真正资源是否可用要看服务 owner/session 是否结束。

``Callback`` 与 ``Client record``：callback 只是投递端点；client record 还包含身份、权限、订阅、资源和清理信息。

``Token`` 与 ``Resource``：token 是访问上下文和引用，真实资源仍由系统服务、HAL 或 kernel 持有。

``Service restart`` 与 ``Session resume``：服务进程重新启动不意味着旧 session 自动恢复；多数硬件会话需要 client 重新建立。

本章结论
--------

系统服务的可靠性取决于状态、所有权和客户端生命周期能否闭合。遇到资源泄漏、重复回调、死连接或重启后状态错乱时，应先检查 client record、owner、token 和 death cleanup，再进入底层设备路径。