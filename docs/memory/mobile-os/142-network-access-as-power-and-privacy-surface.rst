第142章：Network Access as Power and Privacy Surface
=====================================================

核心知识点
----------

* 移动网络访问同时进入数据传输、后台调度和隐私暴露三条路径；一次很小的请求也可能触发 radio 唤醒、DNS、TLS、连接保持和元数据暴露。
* 网络功耗不能只看传输字节数。radio wakeup、tail time、keepalive、轮询、失败重试和弱信号重传通常更决定电量成本。
* 固定周期 polling 会在“没有变化”时持续制造唤醒；平台推送让多个 App 共享系统级通道，更适合后台消息和状态变化通知。
* 私有长连接适合通话、导航、实时协作等明确持续交互；普通后台同步应优先使用推送、批处理和系统任务调度。
* Background sync 应允许系统根据充电、Wi-Fi、未受限网络、设备空闲和用户最近使用状态进行批处理，减少全机唤醒次数。
* Doze/App Standby、Background App Refresh、系统托管传输等机制本质上都在把自由后台联网改成受预算控制的执行窗口。
* 网络元数据本身具有隐私含义：IP 地址、DNS 查询、目标域名、连接时间、网络类型和流量模式都能推断位置、行为或服务使用情况。
* Advertising ID、跨 App 标识、稳定设备指纹和网络 fingerprinting 会把普通联网升级为追踪问题；平台分发与隐私规则会限制此类行为。
* VPN、proxy、Private Relay 等机制可以改变 IP、DNS 和流量可见性，但也会引入额外转发、性能、兼容性和企业管理边界。
* 隐私保护不是“流量全部不可见”。不同方案只隐藏部分观察者能看到的信息，目标 IP、DNS、SNI/域名、账号身份和服务端日志需要分别分析。
* 网络访问设计应可批处理、可恢复、可解释、可撤销：任务能延迟，失败能重试，用户能理解数据用途，权限/追踪选择能被尊重。
* 排查耗电或隐私问题时，应把请求频率、唤醒次数、后台资格、连接保持、目标元数据和第三方 SDK 放到同一时间线上分析。

关键路径
--------

后台联网功耗：

::

   App background work
   → scheduler/push entry
   → lifecycle + power policy
   → DNS/TLS/connect
   → radio wakeup
   → transfer + tail time
   → retry/keepalive decision
   → return to low-power state

隐私暴露：

::

   App network request
   → identifiers + destination metadata
   → DNS / IP / timing / network-type observations
   → proxy/VPN/relay policy may transform visibility
   → remote service and intermediaries retain different evidence
   → platform privacy/distribution policy constrains tracking use

概念辨析
--------

* **Data volume 与 energy cost**：少量数据也可能因频繁唤醒和重试产生高能耗，大流量在一次批处理窗口中反而可能更高效。
* **Push 与 long connection**：push 复用系统共享通道，私有长连接由 App/服务自行维护，资源与后台资格不同。
* **Privacy content 与 metadata**：加密可以保护正文内容，但 IP、时序、流量大小和部分域名信息仍可能泄露行为线索。
* **VPN 与 anonymity**：VPN 改变本地网络看到的流量与出口 IP，但 VPN 提供方和目标服务仍拥有各自可观察信息。
* **Background sync 与 real-time requirement**：后台数据新鲜度通常允许批处理，真正实时能力需要明确用户价值和更强执行理由。

本章结论
--------

网络能力是 ``Connectivity + Power Budget + Privacy Surface`` 的交汇点。移动 App 应减少无意义唤醒、用系统推送替代轮询、把可延迟任务交给调度器，并把 IP/DNS/标识/追踪风险作为网络架构的一部分，而不是只关注 socket 是否成功。