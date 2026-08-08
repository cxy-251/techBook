第043章：Hardware Abstraction, Platform Update, Device Fragmentation
====================================================================

核心知识点
----------

* Hardware Abstraction 的长期价值是把具体 sensor、ISP、codec、modem、driver、firmware 差异压到稳定合同下，让 framework 和 App 可以独立演进。
* 移动平台升级能力取决于多层合同是否稳定：public framework API、system service expectation、HAL interface、driver/KMI、firmware protocol 和设备能力声明都可能成为升级边界。
* Android 通过 Project Treble、system/vendor 分离、VINTF、stable HAL、GSI、CTS/VTS 和 GKI/KMI 降低 framework 更新与设备适配之间的耦合。
* VINTF manifest 表达设备/vendor 提供的接口，compatibility matrix 表达 framework 要求；两者匹配是 OTA 和系统升级的重要兼容条件。
* GSI 用通用 AOSP system image 检查 vendor interface 的可替换性。它主要验证基础 framework/vendor 边界，不代表所有 OEM 私有体验功能都天然可迁移。
* Android fragmentation 的技术来源包括 SoC 支持周期、driver、firmware、HAL 能力、OEM policy、carrier 配置、地区 SKU 和更新节奏，而不是单纯“品牌多”。
* Apple 通过更集中的 SoC、硬件型号、driver、firmware、framework、签名和系统发布体系减少组合数量，形成更受控的设备矩阵。
* Apple 设备仍存在硬件能力差异和生命周期边界；同一系统版本下，某些功能仍可能要求特定芯片、ISP、NPU、memory 或 sensor 能力。
* Driver ABI/KMI 解决 kernel 与 module 的兼容，HAL interface 解决 system service 与 vendor implementation 的兼容，framework expectation 则决定 App 可见行为；三者不能混为一个“API 兼容”。
* 抽象边界越稳定，安全补丁和 framework 更新越能独立前进；越多跨层私有依赖，越容易让一次系统更新退化成整机 BSP 重新适配。
* 平台生命周期是技术合同和产品策略的共同结果。硬件仍能运行，不代表 vendor、firmware、安全补丁和发布体系仍有持续维护资源。

关键路径
--------

长期相机兼容：

::

   App Camera API
   → framework contract
   → CameraService expectation
   → stable HAL capability
   → vendor implementation
   → driver / firmware
   → sensor / ISP

Android 更新：

::

   new system image
   → framework compatibility requirements
   ↔ VINTF device/vendor declarations
   → HAL contract verified
   → kernel/vendor module compatibility checked
   → OTA boots and capability tests pass

生命周期成本：

::

   SoC support
   + driver / firmware maintenance
   + HAL compatibility
   + OEM / carrier policy
   + test and security patch cost
   → actual upgrade lifetime

概念辨析
--------

* **Hardware abstraction 与 hardware uniformity**：抽象层统一合同，不会让不同硬件的能力、质量和性能自动相同。
* **Treble 与 GKI**：Treble 主要解决 framework/vendor 接口分离；GKI/KMI 进一步处理通用 kernel 与 vendor module 边界。
* **VINTF compatibility 与 feature completeness**：VINTF 匹配说明基础接口可协作，不代表 OEM 所有私有特性完整存在。
* **Driver ABI 与 HAL API**：Driver ABI/KMI 面向 kernel/module；HAL API 面向 system/vendor 服务，两者处于不同层。
* **Fragmentation 与 openness**：碎片化是供应链、接口、配置和更新周期的组合结果，开放生态只是其中背景条件。

本章结论
--------

移动平台能否长期升级，取决于硬件差异是否被稳定合同隔离。Android 用 Treble、VINTF、HAL 和 GKI 把多厂商生态拆成可验证边界，Apple 用受控硬件矩阵和统一发布减少组合空间。分析设备生命周期时，应重点看接口稳定性、vendor/firmware 维护和测试成本，而不是只看芯片性能。