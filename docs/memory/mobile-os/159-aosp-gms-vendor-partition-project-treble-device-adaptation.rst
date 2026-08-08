第159章：AOSP, GMS, Vendor Partition, Project Treble, Device Adaptation
======================================================================

核心知识点
----------

* AOSP 是 Android 的开源平台基础，提供 Framework、system service、native service、ART、构建系统、HAL 接口规范、安全模型和兼容性基础。
* GMS 不属于 AOSP。Google Play services、FCM、Maps、Play Integrity、Google Sign-In 等能力属于 Google 授权生态，设备没有对应服务时，Android SDK 仍可能正常，但依赖 GMS 的功能会失败。
* 判断设备差异时先区分 ``Android 平台能力`` 与 ``Google 服务能力``。API level 满足并不代表 Google Play services 一定存在或版本满足。
* 现代 Android 通过分区划分更新与适配责任：``system`` 偏通用平台，``vendor`` 偏 SoC / HAL / vendor service，``odm`` 偏板级定制，``product`` 偏产品和区域配置。
* ``system_ext``、``vendor_dlkm``、``odm_dlkm`` 等分区进一步拆分平台扩展与可加载内核模块，目的仍是明确责任和升级边界。
* Project Treble 从 Android 8.0 起推动 Framework 与 Vendor 分离，使 system image 可以在不重写全部 vendor 实现的情况下升级。
* VINTF 用 manifest 与 compatibility matrix 描述 system/vendor 双方提供和需要的 HAL 接口、版本与兼容条件，并在启动、OTA 和兼容性测试中形成契约。
* 现代 HAL 更强调稳定接口和独立更新。AIDL / Stable AIDL 是主要方向，历史设备可能存在 HIDL。
* Device Adaptation 的真实链路是 ``SoC → BSP / Board → Firmware → Kernel Driver / Module → HAL / Vendor Service → VINTF → Android Framework``。
* 同一 AOSP 版本在不同手机上的相机、音频、显示、传感器、功耗和网络表现不同，通常来自硬件、vendor implementation、firmware、OEM policy 和产品配置，而不是 AOSP API 名称本身。
* Android-compatible device 还涉及 CDD、CTS、VTS 等兼容性约束；能启动 AOSP 并安装 APK，不等于已经达到完整 Android 生态兼容或 GMS 授权条件。
* OTA 问题要按分区和接口判断：system 升级失败、vendor HAL 不兼容、内核模块 KMI 不匹配、产品配置错误属于不同责任层。

关键路径
--------

::

   Third-party App
   → Android SDK API or Google service API
   → AOSP Framework / Google Play services
   → system service / native service
   → VINTF-stable HAL boundary
   → vendor / odm implementation
   → kernel module / firmware / hardware
   → compatibility and product policy

概念辨析
--------

* **AOSP 与 GMS**：AOSP 是开源 Android 平台基础；GMS 是 Google 授权应用和服务集合。
* **system 与 vendor**：system 承担通用 Android 平台，vendor 承担设备和 SoC 相关实现；Treble 重点就是稳定二者边界。
* **product 与 vendor**：product 更偏 SKU、区域、预装和产品功能；vendor 更偏硬件实现和 HAL。
* **Treble 与 VINTF**：Treble 是架构分离目标，VINTF 是描述和校验 system/vendor 接口契约的重要机制。
* **AOSP 可运行与 Android-compatible**：前者说明平台能构建运行，后者还要求满足兼容性定义和测试；GMS 授权又是另一层生态条件。

本章结论
--------

Android 设备差异应沿 ``AOSP / GMS → Partition → Treble / VINTF → HAL → Driver / Firmware → Hardware → OEM Policy`` 定位。先确认差异属于平台、Google 生态还是设备适配，再进入对应分区和接口边界。