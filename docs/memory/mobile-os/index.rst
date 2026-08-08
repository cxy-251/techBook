Mobile OS 必背课本
==================

本目录与 AIBook 的 ``docs/MobileOS`` 一一对应。AIBook 保留完整讲解、平台资料、案例和系统路径，这里只保留稳定、必须掌握、可以直接复习的移动操作系统架构模型。

Part 1：Mobile OS Architecture Model
------------------------------------

* `第001章：Mobile OS and Desktop OS Shared Foundations, Different Constraints <001-mobile-os-and-desktop-os-shared-foundations-different-constraints.rst>`_；
* `第002章：The Core System Chain Hardware, Kernel, Driver, Service, Framework, App <002-the-core-system-chain-hardware-kernel-driver-service-framework-app.rst>`_；
* `第003章：Hardware Capability Mediation and System Control <003-hardware-capability-mediation-and-system-control.rst>`_；
* `第004章：Mobile Platform Constraint Model <004-mobile-platform-constraint-model.rst>`_；
* `第005章：Hardware Boundary, System Boundary, Runtime Boundary, App Boundary <005-hardware-boundary-system-boundary-runtime-boundary-app-boundary.rst>`_；
* `第006章：Kernel, Operating System, and Mobile Platform <006-kernel-operating-system-and-mobile-platform.rst>`_；
* `第007章：Android Above Linux and Apple Above XNU <007-android-above-linux-and-apple-above-xnu.rst>`_；
* `第008章：Capability Path as the Reading Model <008-capability-path-as-the-reading-model.rst>`_。

Part 2：Smartphone Hardware Platform
------------------------------------

* `第009章：Mobile SoC Component Map <009-mobile-soc-component-map.rst>`_；
* `第010章：SoC Integration and Mobile Hardware Topology <010-soc-integration-and-mobile-hardware-topology.rst>`_；
* `第011章：CPU Core Topology and Scheduling Pressure <011-cpu-core-topology-and-scheduling-pressure.rst>`_；
* `第012章：GPU, Display Engine, Hardware Composer, and Frame Output <012-gpu-display-engine-hardware-composer-and-frame-output.rst>`_；
* `第013章：NPU and Specialized Compute Units <013-npu-and-specialized-compute-units.rst>`_；
* `第014章：ISP, Camera Sensor, Lens, and Imaging Hardware <014-isp-camera-sensor-lens-and-imaging-hardware.rst>`_；
* `第015章：Memory, Flash Storage, and Mobile IO Characteristics <015-memory-flash-storage-and-mobile-io-characteristics.rst>`_；
* `第016章：Peripheral Devices Display, Touch, Audio, Camera, and Haptics <016-peripheral-devices-display-touch-audio-camera-and-haptics.rst>`_；
* `第017章：Wireless Hardware Wi-Fi, Bluetooth, NFC, GPS, Cellular Modem <017-wireless-hardware-wifi-bluetooth-nfc-gps-cellular-modem.rst>`_；
* `第018章：Battery, Charging, Thermal Sensors, and Power Hardware <018-battery-charging-thermal-sensors-and-power-hardware.rst>`_。

Part 3：Boot Chain and System Startup
------------------------------------

* `第019章：Power-On Sequence and Boot Entry <019-power-on-sequence-and-boot-entry.rst>`_；
* `第020章：Boot ROM, Bootloader, Firmware, Kernel Image, Verified Boot <020-boot-rom-bootloader-firmware-kernel-image-verified-boot.rst>`_；
* `第021章：Secure Boot and Trust Chain <021-secure-boot-and-trust-chain.rst>`_；
* `第022章：Signature Verification and System Integrity <022-signature-verification-and-system-integrity.rst>`_；
* `第023章：System Partitions, Recovery, OTA Update, Rollback Protection <023-system-partitions-recovery-ota-update-rollback-protection.rst>`_；
* `第024章：Android Startup Path Bootloader, Kernel, init, Zygote, system_server <024-android-startup-path-bootloader-kernel-init-zygote-system-server.rst>`_；
* `第025章：Apple Startup Path Secure Boot, XNU, launchd, System Services <025-apple-startup-path-secure-boot-xnu-launchd-system-services.rst>`_；
* `第026章：Startup Security and Platform Trust Establishment <026-startup-security-and-platform-trust-establishment.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时优先沿 ``App → Framework → IPC → System Service / Daemon → HAL / Driver → Kernel → Hardware`` 定位能力所有者，再把 permission、lifecycle、power、thermal、privacy、sandbox 和 distribution policy 放回对应边界。