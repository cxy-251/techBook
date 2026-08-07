第017章：Wireless Hardware Wi-Fi, Bluetooth, NFC, GPS, Cellular Modem
======================================================================

核心知识点
----------

* Wi-Fi、Bluetooth、NFC、GNSS 和 cellular modem 都由系统服务统一代理。App 使用的是网络、附近设备、支付、定位和蜂窝能力，而不是直接控制 radio、baseband 或 secure element。
* Wi-Fi/Bluetooth combo chip 经 driver、firmware 和协议栈接入系统；两者可能共享天线、频段、电源域与共存策略，因此一个无线链路的负载会影响另一个链路。
* Wi-Fi 扫描和 Bluetooth 扫描会暴露附近环境信息，所以系统通常将扫描频率、前后台状态和权限纳入控制面。API 调用成功不代表无线芯片已经完成新的 scan。
* NFC controller 负责近场通信，支付路径还要经过 Wallet、用户认证和 secure element/安全组件。近场链路建立与支付凭证有效是两个不同阶段。
* Location 不是单纯 GNSS。系统会融合 GNSS、Wi-Fi、cellular、Bluetooth beacon、IMU、气压等信息，再根据权限、精度和功耗策略向 App 返回位置。
* Cellular modem/baseband 负责蜂窝接入、信令、数据链路和部分语音能力；SIM/eSIM、carrier policy、APN、IMS、漫游和网络制式共同影响最终连接。
* 无线系统是强身份与隐私边界：位置、附近设备、支付凭证、运营商身份和网络状态都属于受控资源，不能按普通外设读法忽略权限与审计。
* Radio operation 具有显著功耗成本。弱信号、频繁扫描、重传、漫游和后台保活都会增加 modem/Wi-Fi 活跃时间并消耗电池与热预算。
* 飞行模式、低数据模式、省电、后台限制、权限撤销和企业策略会改变相同 API 的执行结果。无线能力必须按“当前系统状态”判断。
* 无线失败要区分 API/权限、系统服务、协议栈、driver/firmware、射频环境和远端网络六个层级，不能把“连不上”视为单一错误。

关键路径
--------

Wi-Fi / Bluetooth：

::

   app request
   → framework API
   → permission / background policy
   → system service
   → protocol stack / HAL
   → kernel driver
   → wireless firmware
   → radio / antenna
   → scan, connection, or error event

定位：

::

   app location request
   → permission and accuracy policy
   → location service / fusion
   → GNSS + Wi-Fi + cellular + sensors
   → fused position and uncertainty
   → app callback

蜂窝数据：

::

   app network request
   → network framework
   → connectivity / telephony service
   → modem stack + carrier policy
   → baseband firmware / radio
   → cell network
   → packets or failure reason

概念辨析
--------

* **GNSS 与 Location**：GNSS 是定位数据源之一，Location 是系统融合和策略处理后的能力。
* **Wi-Fi scan 与联网**：扫描附近 AP、关联某个 AP、获得 IP、访问互联网是不同阶段。
* **Bluetooth discovery 与 connection**：发现附近设备不等于已经建立 profile/数据连接，两者权限和状态机也可能不同。
* **NFC 通信与支付**：NFC 只建立近场通道，支付还需要凭证、用户认证、Wallet 与支付网络规则。
* **Modem 与 App network API**：App 使用 socket/HTTP 等接口，modem 只负责底层蜂窝链路；中间还有 network stack、carrier policy 和系统连接管理。

本章结论
--------

无线硬件是由协议栈、系统策略和物理射频共同决定结果的能力系统。分析定位慢、蓝牙断开、NFC 支付失败或蜂窝弱网时，应沿 Framework、permission、service、stack、driver/firmware、radio 与远端网络逐层检查，并把功耗、后台和身份隐私约束视为主路径的一部分。