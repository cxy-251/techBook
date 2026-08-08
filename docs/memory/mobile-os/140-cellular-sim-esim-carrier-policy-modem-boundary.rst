第140章：Cellular, SIM eSIM, Carrier Policy, Modem Boundary
=============================================================

核心知识点
----------

* 蜂窝网络是“订阅身份 + 运营商策略 + modem/baseband + 系统网络策略”共同形成的能力，不只是另一张网卡。
* Application Processor 运行 App、Framework、系统服务和常规网络栈；baseband/modem 负责无线注册、移动性、射频控制、SIM/eSIM 鉴权与蜂窝协议处理。
* Android 常见控制链是 ``Telephony Framework/Service → Radio HAL/RIL → Vendor Radio → Modem``；普通 App 不直接控制基带。
* SIM/eSIM profile 提供蜂窝订阅身份。profile 已安装不代表已成为 active/default data subscription，更不代表已经完成网络注册与数据承载。
* Subscription、slot/port、default data SIM、dual-SIM policy、roaming 与 carrier privileges 会共同决定哪一份身份可以使用数据服务。
* eSIM 的核心是 eUICC profile 下载、启用、切换与运营商授权；激活流程和实际网络注册是两个阶段。
* Carrier profile / CarrierConfig 会影响 APN、IMS、VoLTE/VoNR、Wi-Fi Calling、漫游、紧急呼叫、显示策略和部分数据行为。
* LTE、5G NR、Wi-Fi Calling 是不同接入/承载组合。5G 图标不等于业务一定更快；App 更应依赖系统发布的 validated、metered/expensive、constrained 等能力。
* 蜂窝数据与 Wi-Fi 的主要差异包括订阅身份、计费、漫游、移动性、radio state 与弱信号功耗；通用 IP/TLS/HTTP 仍在 AP 网络栈中处理。
* Baseband 应视为独立高价值安全边界。modem firmware、radio interface、更新与隔离决定无线攻击面不能和普通 App 进程混为一层。
* 弱信号会提高发射功率、重传、搜索和切换成本，使蜂窝网络同时成为功耗、定位与隐私输入。
* 排查蜂窝失败时，应先区分“无服务/注册失败”“数据承载失败”“系统网络未验证”“DNS/TLS/HTTP 失败”，再定位到对应层级。

关键路径
--------

蜂窝数据建立：

::

   SIM/eSIM profile active
   → subscription/default-data policy
   → carrier/APN/roaming checks
   → telephony service
   → radio HAL / modem control channel
   → modem registers on RAN/core network
   → data bearer established
   → kernel/network service exposes cellular Network
   → validation + cost policy
   → App traffic

蜂窝故障定位：

::

   App request fails
   → is cellular Network available/validated?
   → active subscription and data enabled?
   → roaming/carrier/APN policy?
   → modem registered and data bearer up?
   → DNS/TLS/HTTP stage?

概念辨析
--------

* **SIM/eSIM 与 subscription**：SIM/eSIM 是身份载体，subscription 是系统对当前运营商身份和服务状态的抽象。
* **eSIM installed 与 network active**：profile 安装成功只完成身份配置，后续仍需启用、注册和建立数据承载。
* **AP 与 baseband**：AP 处理 App 与通用网络协议，baseband 处理蜂窝无线协议和运营商接入。
* **RAT 与 Internet quality**：LTE/5G 说明无线接入技术，不直接等于吞吐、延迟或互联网服务质量。
* **Carrier policy 与 App policy**：运营商控制订阅/网络服务条件，App 只能在系统允许的网络能力上制定自己的下载或同步策略。

本章结论
--------

蜂窝网络应按 ``Subscription Identity → Carrier Policy → Telephony → Modem/RAN → System Network → App`` 阅读。只有把订阅、运营商、基带和通用 IP 网络栈分开，才能正确解释 eSIM、漫游、5G、Wi-Fi Calling、弱信号和数据失败。