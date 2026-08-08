第184章：UI Skin, System Services, Policy, Power, Camera, App Store
=================================================================

核心知识点
----------

* OEM 差异分为两层：表层是 Launcher、SystemUI、Settings、主题和默认应用；深层是 system service policy、power/background policy、Camera HAL 和厂商生态服务。
* Runtime Resource Overlay（RRO）适合改变字符串、布尔配置、尺寸、颜色和部分布局等资源值；它本身不等于业务逻辑，行为变化要继续追踪资源读取方。
* System Service Policy 是 OEM 深度定制的关键位置。权限、通知、后台、网络、窗口、电源和相机请求最终都要结合 UID、AppOps、用户设置、设备状态与厂商配置做决策。
* 厂商省电通常在 Doze、App Standby、JobScheduler、Alarm、Foreground Service 等 Android 基础规则之上，再叠加自启动、冻结、白名单、清理和网络限制。
* OEM 影像体验来自默认相机、CameraService、Camera HAL、ISP tuning、算法库、sensor/lens 和温控预算的组合；第三方 App 通常只能使用公开 API 暴露的能力子集。
* OEM App Store、账号、云、Push、支付和多设备协同把 Android 基础系统扩展为厂商生态平台，并可能引入区域化分发、更新和 SDK 适配差异。

关键路径
--------

表层配置到实际行为：

``SystemUI / Settings → RRO / Device Config → System Service Policy → App Visible Behavior``

后台与电源：

``App Task → JobScheduler / Alarm / FGS → AOSP Power Policy → OEM Battery Policy → CPU / Network / Process Budget``

相机：

``Camera App / Third-Party App → Camera2 / CameraX → CameraService → Camera HAL → ISP / Driver / Sensor → Image Result``

生态服务：

``App → OEM Store / Account / Push SDK → OEM System Service → OEM Cloud → Distribution / Push / Sync Result``

概念辨析
--------

* **UI Skin vs 系统行为**：图标、主题、设置布局属于 UI；通知延迟、后台终止、相机能力差异属于执行策略或硬件路径。
* **RRO vs Framework 修改**：RRO 替换资源值；Framework 修改可以直接改变系统服务逻辑和调用规则。
* **AOSP 省电 vs OEM 省电**：前者是 Android 公共策略；后者是厂商在设备和产品目标下追加的限制与豁免。
* **默认相机能力 vs 第三方 Camera API**：默认相机可使用厂商私有算法和 vendor 扩展；第三方能力受公开 API、HAL capability 和权限边界限制。
* **应用商店 vs 系统能力**：商店负责分发和生态规则；后台、相机、权限等真实系统行为仍由 OS 服务和硬件路径执行。

本章结论
--------

评估 OEM 系统时，不能停在视觉皮肤。需要从用户现象继续追踪到 ``资源配置 → System Service Policy → Power/Background Policy → HAL/Vendor → OEM Cloud``。UI 决定用户如何触达能力，系统服务决定能力如何执行，HAL 决定硬件如何实现，厂商生态服务决定分发、账号、推送和跨设备体验。