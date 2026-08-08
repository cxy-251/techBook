第050章：Apple Daemons, Framework Frontends, Service Backends
==============================================================

核心知识点
----------

* Apple 平台把开发者可见的 Framework Frontend 与真正持有资源和策略的 Service Backend 分离。
* App 应依赖公开 Framework、授权状态和错误语义，而不依赖私有 daemon 名称、端口或内部协议。
* ``launchd`` 是 Apple 服务管理模型的根：它负责系统服务注册、按需启动、崩溃后的重新拉起以及服务生命周期管理。
* XPC 提供进程间通信与隔离。连接可被 interruption / invalidation，客户端必须把远端服务视为可失败、可重启的独立组件。
* System daemon、user agent、XPC service、app extension、helper 的管理者、权限范围和生命周期不同。
* Entitlement、sandbox 和 TCC/隐私授权承担不同职责：entitlement 表示平台能力资格，sandbox 限制进程对象访问，TCC 类授权表达用户对敏感数据的许可。
* Framework Backend 会把后端拒绝、资源不可用、服务重启、云端状态变化等转换成稳定 API 结果。

关键路径
--------

通用 Apple 服务路径：

``App → Public Framework → XPC / system IPC → Service Backend / Daemon → XNU / Driver Framework → Resource``

以照片选择与读取为例：

#. 用户通过系统 UI 或公开 Framework 选择资源。
#. Framework 生成受授权范围约束的资源请求。
#. 后端服务检查调用者身份、照片授权、sandbox/entitlement 和资源状态。
#. 数据可能来自本地文件、缓存、数据库或云端同步状态。
#. Framework 将结果包装成公开对象、异步进度、取消或错误。
#. 后端服务崩溃或连接失效时，client 处理 interruption/invalidation，并按 API 契约重试或结束操作。

概念辨析
--------

``Framework Frontend`` 与 ``Service Backend``：前者是开发者稳定接口；后者是平台内部资源所有者和策略执行者。

``launchd`` 与 ``XPC``：launchd 负责服务生命周期和启动管理；XPC 负责进程间消息与连接抽象。

``System daemon`` 与 ``XPC service``：system daemon 通常承载平台共享能力；XPC service 常用于更小的隔离单元或应用/服务辅助进程。

``Entitlement`` 与 ``Privacy Authorization``：entitlement 是签名绑定的平台能力资格；隐私授权是用户是否允许当前 App 访问具体敏感数据或传感器。

本章结论
--------

Apple 的开发者稳定边界位于公开 Framework，而真实能力由受系统管理的 service/daemon 持有。分析 Apple 系统路径时，应依赖公开 API、entitlement、sandbox、授权状态和错误信号推断责任边界，不把私有服务实现当成稳定接口。