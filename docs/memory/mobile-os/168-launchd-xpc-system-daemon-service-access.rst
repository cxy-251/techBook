第168章：launchd, XPC, System Daemon, Service Access
===================================================

核心知识点
----------

* ``launchd`` 是 Apple 用户态服务管理根节点，负责服务注册、按需激活、生命周期监督和崩溃后的恢复；“服务存在”与“服务进程当前正在运行”可以分离。
* Apple 后台服务可按作用域理解为 system daemon、user agent、XPC service：前者持有系统能力，agent 绑定用户会话，XPC service 常用于隔离 helper 工作。
* Framework frontend 提供公开 API，daemon backend 持有全局状态、资源和策略；二者通过 XPC / Mach service 等 IPC 边界连接。
* XPC connection 把消息、reply、错误和连接生命周期组织成稳定通信关系，服务可由本次连接请求触发启动。
* 系统服务需要知道“谁在请求”，因此 service access 常结合 audit token、code signing identity、entitlement、sandbox 与 TCC 状态判断。
* 连接生命周期至少要区分 created、active/resumed、interrupted 与 invalidated；服务重启不等于 App 一定要崩溃，客户端应按 API 语义处理重连和未完成请求。
* Daemon failure 应被视为服务边界故障：连接中断、请求失败、状态丢失和服务重启都需要 framework/client 具备恢复逻辑。

关键路径
--------

* 标准服务访问路径：``App → Public Framework → XPC connection → launchd service resolution / activation → daemon → policy / protected resource → reply → Framework callback``。
* daemon 接到请求后通常先做 caller identity 与权限检查，再处理资源；因此 API 参数合法不代表服务一定接受请求。
* 受控能力的检查路径可抽象为 ``Mach/XPC caller → audit token → code identity / entitlement → sandbox → TCC / policy → resource``。
* 服务崩溃时，客户端应把未完成请求视为未知或失败状态，等待 framework 给出的 interruption/invalidation/error，而不是假定事务已经完成。
* 调试服务访问问题时，先确认 public API 与 error，再确认授权/entitlement，再看连接是否中断，最后结合 Console、Instruments、sysdiagnose 等系统证据。

概念辨析
--------

* ``launchd`` 是服务管理者，不是所有系统能力的业务实现；真正状态通常由对应 daemon 持有。
* ``XPC service`` 是一种隔离的服务形态；``XPC`` 本身是通信与服务模型，二者不能等同。
* ``System daemon`` 与 ``App helper`` 都可使用 XPC，但权限范围、生命周期和资源所有权完全不同。
* ``Interruption`` 表示服务暂时不可达或重启等可恢复情形；``Invalidation`` 表示当前连接生命周期终结。
* ``Mach service name`` 是服务发现入口之一；它不是普通 App 可以任意连接的公共能力，仍受签名、sandbox 和 entitlement 限制。

本章结论
--------

Apple 服务模型的核心是把“能力长期存在”与“进程按需运行”分离，再用 XPC/Mach 通道把 App framework 与受控 daemon 连接起来。理解一次服务访问时，要同时追踪服务发现、调用者身份、权限策略、请求/回复和连接生命周期；只记某个 daemon 名称无法解释真实的权限、恢复和失败行为。