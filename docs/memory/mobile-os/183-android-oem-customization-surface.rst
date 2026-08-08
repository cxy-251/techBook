第183章：Android OEM Customization Surface
==========================================

核心知识点
----------

* OEM 系统不是“换皮 AOSP”，而是 ``AOSP + GMS/区域服务 + Vendor Layer + OEM System Apps/Services`` 的完整发行平台。
* OEM 可定制面从上到下包括：Launcher/SystemUI/Settings、资源 overlay、Framework policy、system/native service、HAL、vendor/odm/product 分区、驱动/固件以及账号、云、推送、商店等生态服务。
* AOSP 负责共同的平台语义；GMS 提供 Google 生态能力；Vendor Layer 承载设备相关实现；OEM Services 负责产品差异化和生态绑定。
* UI 定制只改变入口、样式、文案和默认配置；真正改变后台、通知、权限、网络、相机等行为的通常是 system service policy、厂商 daemon 或 HAL/vendor 实现。
* Treble、VINTF、HAL 稳定接口、CDD、CTS、VTS 和 GMS 认证共同限定 OEM 的自由度：可差异化，但必须维持兼容边界。
* 分析 OEM 差异时应优先观察 App 可见行为，再沿公开 API 向 system service、policy、HAL/vendor 和生态服务回溯，避免把所有差异统称为“厂商魔改”。

关键路径
--------

典型 OEM 能力路径：

``App → Framework API → System Service → OEM Policy / Native Service → HAL / Vendor Interface → Driver / Firmware → Hardware``

用户配置路径：

``Settings / Security Center → OEM 配置或白名单 → System Service Policy → App 后台/通知/权限结果``

生态服务路径：

``App → GMS 或 OEM SDK → Google/OEM System Service → Cloud Service → Push / Account / Sync / Store Result``

相机类差异继续下沉：

``Camera2 / CameraX → CameraService → Camera HAL → Vendor ISP / Driver / Firmware → Sensor / Lens``

概念辨析
--------

* **UI Skin vs System Policy**：前者改变用户看到什么、入口在哪里；后者改变 App 请求是否被放行、延迟、降级或拒绝。
* **AOSP vs GMS**：AOSP 是开源平台基础；GMS 是 Google 授权的应用与服务集合，不属于 AOSP。
* **System App vs System Service**：Settings、安全中心等通常提供配置入口；真正执行资源仲裁和策略的是 system service、native daemon 或底层服务。
* **Overlay vs 代码逻辑**：RRO 主要替换资源和配置值；实际行为仍由读取这些资源的代码和服务决定。
* **HAL vs Driver**：HAL 是 Framework 与 vendor 实现之间的稳定能力接口；driver/firmware 负责具体硬件控制。
* **兼容性 vs 一致体验**：CDD/CTS/VTS 保证最低兼容与接口契约，不保证所有 OEM 在影像、后台、功耗和 UI 上完全一致。

本章结论
--------

Android OEM Customization 应理解为一套受兼容性约束的“再发行平台工程”。最稳定的分析方法是把任何厂商差异放回 ``App → Framework → Service/Policy → HAL/Vendor → Driver/Hardware`` 主链，再单独检查 GMS、OEM 云服务和系统应用入口；这样才能判断差异究竟来自视觉层、策略层、硬件实现层还是生态服务层。