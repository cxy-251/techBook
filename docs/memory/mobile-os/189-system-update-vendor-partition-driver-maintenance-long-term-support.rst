第189章：System Update, Vendor Partition, Driver Maintenance, Long-Term Support
=============================================================================

核心知识点
----------

* Android 更新不是单一 OTA 文件问题，而是 Google 平台、安全补丁、SoC vendor、OEM 产品分支、运营商认证和设备安全链共同完成的交付流程。
* System/Vendor 分离的目标是让 Framework 与设备相关实现解耦：``system`` 更接近平台代码，``vendor`` 更接近 HAL、SoC 库、设备配置和硬件实现。
* Project Treble 用稳定 vendor interface 降低 Framework 升级对硬件实现的耦合；VINTF 用 manifest 和 compatibility matrix 明确“设备提供什么、Framework 需要什么”。
* HAL interface 是 System/Vendor 的能力契约。OTA 前后需要维持接口版本、服务声明和行为兼容，VTS/CTS 等测试用于验证这些边界。
* Driver、firmware、HAL 是长期支持成本最高的区域。SoC 停止维护、老 kernel、私有 firmware 和设备专有调校都会限制大版本升级和安全修复周期。
* GKI 和 stable KMI 将核心 kernel 与 vendor module 进一步解耦，目标是减少 kernel fragmentation 并让核心安全修复更易复用，但 vendor module 仍需持续维护。
* Mainline 把部分系统组件模块化为 APEX/APK，使修复可以脱离完整 OTA 更快分发；它无法替代所有 kernel、driver、firmware 和产品级 OTA。
* A/B OTA、Verified Boot 和 rollback protection 共同保证升级过程可验证、失败可恢复，并阻止回滚到低安全版本破坏信任链。
* 长期支持质量应看补丁频率、Android 大版本、Mainline、kernel/driver/firmware 维护、OTA 稳定性和真实设备生命周期，而不是只看一个版本号。

关键路径
--------

平台到设备：

``Google/AOSP/Security Fix → SoC Vendor + OEM Integration → Compatibility/Regression Test → Carrier/Regional Validation → OTA Rollout``

接口兼容：

``New Framework Requirements → Framework Compatibility Matrix ↔ Device Manifest / Vendor HAL → VINTF Check → Boot/OTA Decision``

OTA 安装：

``OTA Payload → update_engine → Inactive Slot / Dynamic Partitions → Reboot → AVB Verification → New Slot or Fallback``

长期维护：

``Kernel/GKI + Vendor Modules + HAL + Firmware + Product Services → Security Patch / Platform Upgrade → Revalidation``

概念辨析
--------

* **System update vs Vendor update**：前者偏 Framework/系统组件；后者涉及 HAL、driver、firmware 和设备实现，测试成本通常更高。
* **Treble vs Mainline**：Treble 解耦 Framework 与 Vendor；Mainline 模块化部分系统组件并允许独立更新。
* **GKI vs HAL**：GKI/KMI 管 kernel core 与 vendor modules；HAL 管 Framework/service 与 vendor hardware implementation。
* **Security patch level vs Android version**：补丁级别反映一组安全修复；Android 大版本还涉及 API、Framework 行为和兼容性变化。
* **A/B fallback vs Rollback protection**：A/B fallback 用于升级失败后的可启动恢复；rollback protection 防止退回不安全的软件版本。

本章结论
--------

Android 长期更新能力取决于多层接口是否可持续维护。Treble/VINTF、GKI/KMI、Mainline 和 A/B OTA 都是在缩短依赖链、提高可更新性；真正的设备寿命仍受 SoC、driver、firmware、HAL、OEM 测试和区域认证约束。评价 OEM 更新能力时，应沿 ``Platform → Vendor → Product → OTA → Boot Trust`` 全链观察。