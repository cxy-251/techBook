第182章：OEM Fragmentation and Platform Uniformity
==================================================

核心知识点
----------

* Android Fragmentation 的技术来源是多主体交付链：SoC、driver、firmware、HAL、vendor partition、OEM system service、GMS / 区域服务、运营商策略和系统版本都可能改变同一 API 的实际行为。
* CDD / CTS / VTS、稳定 HAL、VINTF、GKI 等机制约束 Android 的共同边界；它们降低碎片化失控风险，但不会消除硬件、算法、后台策略和更新节奏的差异。
* 相机最容易暴露底层差异：sensor、lens、ISP、Camera HAL、vendor tag、算法库、thermal policy 会共同影响画质、帧率、延迟和能力组合。
* 后台任务与通知最容易暴露系统策略差异：WorkManager / JobScheduler、Doze、App Standby、OEM 省电、自启动管理、GMS / OEM push 与通知设置可能叠加。
* Apple Platform Uniformity 来自较少硬件组合、统一 OS / framework、统一签名和隐私模型、统一主要分发渠道与更集中的系统更新。
* Apple 设备之间仍存在芯片、相机、屏幕刷新率、内存和硬件功能差异；“一致性”指公开 API 与系统策略更集中，不代表所有设备性能和能力相同。
* Android 的碎片化换来了更宽的硬件创新、价格区间、区域定制与 OEM 控制权；Apple 的统一性降低开发者测试矩阵和行为漂移，同时收缩厂商级定制空间。
* 工程上应把设备差异转换成 capability detection、版本与型号矩阵、真实设备测试、降级路径和可观测证据，而不是假设平台名即可代表具体行为。

关键路径
--------

::

   Android device behavior:
   Public API
       → OEM / Google / System Policy
       → HAL / Vendor Service
       → Driver / Firmware / Hardware
       → Device-specific Result

   Apple device behavior:
   Public Framework
       → Unified Platform Policy / Daemon
       → Apple-controlled Driver / Hardware
       → More uniform Result Surface

对“同一 App 两台手机表现不同”进行定位时，应依次核对 API level / OS version、feature / capability、permission / policy、vendor implementation、硬件与服务版本。

概念辨析
--------

* ``Fragmentation`` 不等于系统无标准：Android 有严格兼容层，只是允许更多硬件和厂商实现组合。
* ``Uniformity`` 不等于硬件相同：Apple 不同代设备仍有能力梯度，统一的是平台控制链和主要行为契约。
* ``Android version 相同`` 不等于设备栈相同：kernel、vendor、HAL、GMS、security patch、OEM service 都可能不同。
* ``OEM 定制`` 不只指 UI Skin；后台、电源、通知、权限、相机、网络和系统服务策略都可成为差异源。

本章结论
--------

Android 用兼容机制管理多厂商、多硬件和多区域组合，因此开发者必须把设备能力当作运行时事实；Apple 通过软硬件和平台政策集中控制获得更高行为一致性。Fragmentation 与 Uniformity 是两种平台工程取舍，核心差异在控制权、适配成本、更新链和创新空间。