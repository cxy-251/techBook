第041章：Vendor Partition, Device Tree, Firmware, Board Support
===============================================================

核心知识点
----------

* Android 的 vendor boundary 由 vendor partition、device tree / board config、firmware、BSP、HAL、vendor service 和 kernel/vendor module 共同组成。
* Vendor Partition 主要承载设备相关二进制、HAL service、vendor library、init 配置、设备 XML、调参、firmware、sepolicy 扩展和机型差异。
* Device Tree 描述 kernel 无法自动枚举的硬件事实，例如 bus address、GPIO、IRQ、clock、regulator、memory region 和 compatible；它直接影响 driver probe。
* Device Configuration 的范围比 device tree 更广，还包括 fstab、init rc、audio policy、thermal config、camera metadata、system property、display config 和 vendor SELinux policy。
* Firmware 运行在 modem、ISP、Wi-Fi/Bluetooth controller、touch controller、sensor hub、DSP、secure processor 等独立硬件单元中，driver/HAL 通过特定协议与其协作。
* Firmware 与 driver 必须在 command、shared-memory layout、event format、version 和 error semantics 上匹配，否则 system image 正常也可能出现设备能力失效。
* BSP 是让某个 SoC + board + peripheral 组合运行目标系统的完整适配集合，通常包含 kernel、driver、DT、firmware、HAL、vendor service、sepolicy、build config 和 tuning data。
* Vendor manifest 与 framework compatibility matrix 通过 VINTF 描述“设备提供什么”和“framework 要求什么”，是 system/vendor 分离后的兼容检查入口。
* OTA 能否独立更新 system，取决于 HAL/VINTF/KMI 等边界是否稳定；vendor image、firmware 和 kernel module 生命周期过短会直接缩短设备长期维护周期。
* Android 碎片化的重要技术来源不是单纯机型数量，而是 SoC support、driver、firmware、HAL、OEM policy、carrier config 与更新周期的组合差异。

关键路径
--------

OTA 后相机：

::

   Framework camera API
   → CameraService
   → VINTF resolves HAL instance
   → vendor camera HAL
   → kernel driver probe
   → device tree supplies GPIO / IRQ / clocks
   → firmware / tuning initializes ISP and sensor
   → preview result

启动期硬件描述：

::

   bootloader loads DTB / DTBO
   → kernel parses hardware description
   → driver matches compatible node
   → acquire regulator / clock / IRQ / memory
   → create device interface
   → HAL opens device

Vendor 兼容：

::

   framework compatibility matrix
   ↔ vendor / device manifest
   → HAL version and instance match
   → service starts
   → runtime capability available

概念辨析
--------

* **Vendor partition 与 BSP**：Vendor partition 是设备适配材料的运行时存放边界；BSP 是更完整的 SoC/board 支持集合。
* **Device Tree 与 vendor config**：DT 主要服务 kernel/device probe；vendor config 还服务 HAL、daemon 和 framework policy。
* **Firmware 与 driver**：Firmware 在设备内部处理协议和控制，driver 在主 OS 中负责加载、通信和资源管理。
* **System update 与 vendor update**：System 可以在稳定接口上独立前进，vendor/firmware 不兼容时仍会阻断真实硬件能力。
* **Hardware presence 与 capability availability**：硬件焊在主板上，不代表 driver probe、HAL、VINTF 和 firmware 全链路都已经可用。

本章结论
--------

Vendor boundary 是 Android 设备长期可维护性的核心。排查硬件问题时，应把 vendor image、device tree、firmware、BSP、VINTF 与 driver 放在同一条链上；系统升级能否持续，最终取决于这些设备专属材料能否通过稳定接口与 framework 解耦。