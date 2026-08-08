第134章：Android Capability Path Framework API, Service, HAL, Driver
=====================================================================

核心知识点
----------

* Android 设备能力的稳定阅读模型是 ``App → Framework Manager → Binder/System Service → Permission/AppOps/Policy → Native Stack/HAL → Driver/Firmware → Hardware``。
* Framework API 只是能力表面。真正的资源状态、并发仲裁、调用者身份和失败处理通常位于 system_server、native service 或独立 HAL service。
* Binder 把 App 请求带到系统服务，同时携带 UID、package、attribution、target SDK、foreground state 等身份上下文；系统服务据此执行策略。
* Permission、AppOps 与 SELinux 解决不同问题：manifest/runtime permission 表达调用资格，AppOps 表达可动态限制的操作状态，SELinux 约束进程对 binder service、device node、socket 和 vendor service 的系统级访问。
* HAL 把 Android 平台接口与 vendor 硬件实现分离；现代 Android 新 HAL 更偏向 AIDL/binderized 接口，具体实现和进程边界会随版本、OEM 与设备变化。
* Sensor 路径的典型链是 ``SensorManager → SensorService → Sensors HAL → sensor hub/driver``。它是持续事件流模型，重点在采样率、batching、FIFO、wake-up 与多客户端复用。
* Location 路径是多来源融合模型。系统服务还要结合精确/模糊授权、前后台状态、provider 可用性、缓存、电源与 GNSS/网络定位能力。
* Bluetooth 路径通常包含 Framework API、system Bluetooth service、native protocol stack、HAL/controller；Nearby Devices permission、扫描限制和连接状态共同决定 App 可见结果。
* NFC 路径通常包含 NfcAdapter/reader/HCE API、NFC service、HAL/vendor stack、controller；tag dispatch、reader mode、AID/HCE 路由属于服务层策略。
* Device capability 排查应先找“资源所有者”而不是先找 driver。若系统服务已经拒绝、降级或过滤请求，继续向内核追踪不会解释 App 行为。
* 同一能力可能跨 system_server、native daemon、vendor HAL 与 kernel 多个进程/边界；应用异常、服务拒绝、HAL 不支持和硬件故障必须分层归因。
* Android 能力封装的目标是让系统在设备差异、OTA、权限、安全、功耗和并发访问之间保持统一控制面。

关键路径
--------

通用能力请求：

::

   App intent
   → Framework manager/request object
   → Binder transaction with caller identity
   → system service
   → permission + AppOps + lifecycle/power/resource policy
   → native stack or HAL client
   → HAL service
   → driver / firmware / controller
   → hardware result/event
   → reverse path to callback/status/error

定位责任层：

::

   no result / degraded result
   → did Framework call reach service?
   → permission/AppOps/foreground policy?
   → resource owner state?
   → HAL capability/availability?
   → driver/firmware/hardware event?
   → return filtered/delayed by service policy?

概念辨析
--------

* **Framework Manager 与 System Service**：Manager 是 App 进程中的 API 表面，System Service 才通常持有全局状态与资源仲裁权。
* **Permission 与 AppOps**：permission 决定基本授权资格，AppOps 可结合用户/后台/隐私状态动态允许或限制具体操作。
* **HAL 与 driver**：HAL 统一 Android 上层契约，driver 直接处理内核设备、总线、中断和硬件接口。
* **System service 与 native stack**：服务负责策略、身份和资源状态，native stack 更偏协议、编解码或设备专用执行逻辑。
* **API success 与 capability success**：API 调用成功发出，只说明请求进入系统；资源仍可能在服务、HAL 或硬件层被拒绝、降级或失败。

本章结论
--------

Android 设备能力应沿 ``Framework → Binder Service → Policy → HAL → Driver → Hardware`` 阅读。真正理解 Sensor、Location、Bluetooth、NFC 等 API 的关键，不是记住类名，而是定位谁拥有资源、谁检查调用者、谁抽象硬件，以及结果在哪一层被过滤、延迟、拒绝或降级。