第131章：Location Stack GPS, Wi-Fi, Cellular, Bluetooth, Permission, Power
============================================================================

核心知识点
----------

* 移动定位不是“GPS API”，而是 ``GNSS + Wi-Fi + Cellular + Bluetooth + Motion Sensors + Cache + Policy`` 的多源融合系统能力。
* App 请求的是位置语义；系统服务决定当前使用哪些 provider、是否复用缓存、是否启动高功耗无线电，以及结果能以多高精度和多高频率返回。
* 一个位置结果至少要同时看坐标、timestamp 和 accuracy。新但粗略的位置、旧但精确的位置，适用场景完全不同。
* GNSS 提供全球坐标系下的绝对位置，室外开阔环境效果最好；城市峡谷、室内、多路径反射和冷启动会显著降低可用性和首次定位速度。
* Wi-Fi 与 cellular 更适合快速提供环境约束和粗略位置；Wi-Fi 扫描结果本身具备位置推断能力，因此平台会把扫描权限和节流纳入隐私策略。
* Bluetooth/beacon 主要提供近距离存在性与区域上下文，惯性传感器提供短时运动连续性；它们通常作为融合输入，而不是独立全球定位来源。
* Foreground、background、precise/approximate、one-shot 与 continuous update 是不同能力级别。授权成立不代表系统必须以最高频率持续定位。
* 后台定位是高敏感、高功耗能力，平台会通过后台权限、foreground service/background mode、频率限制、提示和系统状态指示收束它。
* 高精度持续定位会激活 GNSS、扫描和 CPU 处理，电量成本明显；geofence、significant-change、batching、低频更新等机制用于把业务意图转换成更低功耗系统事件。
* Android 需要同时理解 Location API、权限、系统 provider/fused provider、位置总开关和后台策略；Apple 通过 Core Location 暴露 authorization、accuracy、background update 与区域监控等表面。
* “定位不准”必须拆成信号、缓存时效、精度授权、provider 可用性、后台限制和电源策略几个独立问题。

关键路径
--------

前台高精度定位：

::

   App request
   → Framework location API
   → caller identity + permission + precise/approximate state
   → location system service
   → cache freshness check
   → fused provider selects GNSS / Wi-Fi / cellular / Bluetooth / motion
   → hardware observations
   → fusion
   → Location(timestamp, accuracy, coordinates, optional speed/bearing)
   → App callback

低功耗后台路径：

::

   App moves to background
   → background authorization/policy check
   → continuous high-rate request is reduced or rejected
   → geofence / significant-change / batched low-rate strategy
   → system owns monitoring
   → qualifying event wakes or notifies App

概念辨析
--------

* **GPS 与 GNSS**：GPS 是 GNSS 星座之一，手机“GPS 定位”通常实际使用多星座与辅助信息。
* **Provider 与 fused location**：provider 是数据来源或系统定位角色，fused location 会组合多个来源形成最终估计。
* **Accuracy 与 freshness**：accuracy 描述空间误差估计，freshness 由 timestamp 描述；二者必须同时判断。
* **Permission 与 availability**：有权限只说明 App 有请求资格，provider、信号、电源和系统开关仍可能让结果不可用或降级。
* **Continuous location 与 geofence**：前者持续交付位置流，后者把区域事件交给系统长期监控，功耗和后台语义不同。

本章结论
--------

定位栈的稳定模型是 ``App Intent → Authorization/Policy → Multi-Source Observation → Fusion → Time/Accuracy-Bounded Result``。移动 OS 的核心价值在于替 App 管理信号来源、缓存、精度、后台和功耗；业务应描述“需要什么位置能力”，而不是试图永久占用某一种无线硬件。