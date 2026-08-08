第136章：Network Hardware, Modem, Wi-Fi Chip, Network Interface
================================================================

核心知识点
----------

* 手机网络链路应按 ``App → Network API → Connectivity Policy → Kernel Network Stack → Driver / Firmware → Radio Hardware`` 阅读；App 看到的是系统整理后的网络能力，不是裸网卡状态。
* Wi-Fi 芯片负责扫描、关联、MAC/PHY 收发与部分加密；蜂窝 modem 负责小区注册、无线协议、SIM/eSIM 鉴权与数据承载。两者在系统中都是 transport，但控制边界不同。
* Application Processor 运行 App、Framework、系统服务和常规 IP 栈；baseband/modem 通常是相对独立通信子系统，通过受控接口把注册、信号和数据承载状态交给 AP。
* Radio state、network interface、system network state 是不同层级：radio 表示硬件/firmware 状态，interface 是内核收发对象，system network state 还包含 IP、DNS、route、validation、VPN 与策略。
* 硬件存在不等于接口可用，接口存在也不等于互联网可用。系统只有在 driver 注册接口、完成地址与路由配置，并通过网络能力/验证判断后，才会把网络作为 App 可用路径发布。
* ``INTERNET`` 与 ``VALIDATED`` 应区分：前者表示网络被配置为可访问互联网，后者表示系统最近实际验证了通用互联网可达性。
* Wi-Fi 与蜂窝可以同时在线。默认网络由系统根据可用性、验证、成本、用户设置、VPN、信号和策略选择，不应简单理解为“Wi-Fi 永远优先”。
* 链路切换会影响 DNS、路由、socket、连接池和长连接。已有连接是否迁移、重建或失败取决于协议、Framework 和系统路径策略。
* Bluetooth/Wi-Fi combo 硬件可能共享射频与 firmware，Bluetooth 音频、BLE 扫描和 Wi-Fi 高吞吐之间需要 coexistence 调度；App 通常只看到吞吐、延迟或扫描结果变化。
* 网络硬件直接影响功耗：弱信号、频繁扫描、radio 重连、蜂窝高功率发射与多网络并发都会扩大电量成本。
* 排查“有信号但没网”时，应依次检查 radio、interface、IP/route/DNS、validation、默认网络与 App policy，而不是直接归因于服务器或硬件。

关键路径
--------

网络能力建立：

::

   radio hardware available
   → firmware / baseband ready
   → driver registers network interface
   → IP provisioning + route + DNS
   → system connectivity service receives network state
   → validation / cost / policy evaluation
   → default or eligible network selected
   → App receives capability/callback

Wi-Fi 到蜂窝切换：

::

   Wi-Fi signal/link degrades
   → system keeps cellular candidate ready
   → connectivity service re-evaluates networks
   → route/default network changes
   → DNS/socket/connection state adapts
   → App sees callback, reconnect or transient failure

概念辨析
--------

* **Radio state 与 Internet availability**：radio 已连接只说明无线链路成立，互联网仍依赖 IP、DNS、route 与 validation。
* **Network interface 与 default network**：interface 是内核对象，default network 是系统策略选择结果。
* **Wi-Fi signal 与 validated network**：信号强只说明无线质量，不保证门户页、DNS 或外网访问正常。
* **Cellular modem 与 kernel IP stack**：modem 负责蜂窝接入与无线协议，AP 内核仍负责 App 侧 socket、IP 路由和大部分通用网络语义。
* **Hardware capability 与 App-visible capability**：硬件支持某 transport，不代表当前 App 在当前策略下能使用它。

本章结论
--------

手机网络硬件应按 ``Radio → Firmware/Driver → Interface → IP/Route/DNS → Connectivity Policy → App`` 分层理解。真正决定 App 能否联网的不是信号图标，而是硬件链路、内核接口和系统网络策略共同形成的可用网络。