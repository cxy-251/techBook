===========================================
Part 3: 引导链路与安全启动 (Boot Chain)
===========================================

本模块系统解构智能手机从按下电源键上电、执行硬件级 Boot ROM、逐级验签引导、内核加载直至系统桌面呈现的完整启动全链路。深入剖析 Android Verified Boot (AVB)、dm-verity 哈希树校验、A/B 无缝 OTA 槽位切换、Android Zygote 预加载模型与 Apple Secure Boot / launchd 守护树拓扑。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_power_on_sequence_and_boot_rom
   02_verified_boot_and_dm_verity
   03_system_partitions_ab_seamless_ota
   04_android_startup_kernel_init_zygote_system_server
   05_apple_startup_iboot_xnu_launchd_springboard
