========================================================================
《移动操作系统底层架构与软硬件边界全景深度剖析》全书架构与执行路线图
========================================================================

:书名: 移动操作系统底层架构与软硬件边界全景深度剖析 (Mobile OS Architecture Core)
:定位: 深入 Android (AOSP) 与 Apple (iOS/Darwin/XNU) 核心底层，涵盖 SoC 硬件拓扑、安全引导链、Linux/XNU 内核子系统、HAL/Treble 驱动边界、系统服务网格与 IPC 通信中枢工程专著
:标准规范: 遵循 Sphinx / reStructuredText 工业级排版规范与底层硬件事实/源码拓扑推导
:当前完成度: 42 / 42 节 (100.0%) - 全书全量完工!

------------------------------------------------------------------------
模块总览与推进状态表
------------------------------------------------------------------------

.. list-table:: 专著 8 大核心模块推进全景
   :widths: 10 35 15 15 25
   :header-rows: 1
   :class: tight-table

   * - 模块编号
     - 模块全称 (Directory / Module)
     - 规划章节数
     - 已完成章节
     - 当前推进状态
   * - **Part 1**
     - 移动 OS 架构模型与系统边界 (01_mobile_os_architecture_model)
     - 6
     - 6
     - **全量完工 [x]**
   * - **Part 2**
     - 智能手机硬件平台与 SoC 拓扑 (02_mobile_hardware_and_soc_topology)
     - 6
     - 6
     - **全量完工 [x]**
   * - **Part 3**
     - 引导链路与安全启动 (03_boot_chain_and_secure_startup)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 4**
     - 移动内核底层机制 (04_mobile_kernel_subsystems)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 5**
     - 驱动模型、HAL 与厂商边界 (05_driver_model_and_hardware_abstraction)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 6**
     - 系统服务与 IPC 通信中枢 (06_system_services_and_ipc_spine)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 7**
     - 应用运行时与生命周期策略 (07_runtime_layer_and_process_lifecycle)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 8**
     - 移动安全沙箱、存储与数据保护 (08_mobile_security_storage_and_user_data)
     - 5
     - 5
     - **全量完工 [x]**
   * - **全书总计**
     - **8 大模块 (Part 1 ~ Part 8)**
     - **42 节**
     - **42 节**
     - **全书 42/42 节全量完工 (100.0%) [x]**

------------------------------------------------------------------------
详细章节清单与完成状态
------------------------------------------------------------------------

Part 1: 移动 OS 架构模型与系统边界 (01_mobile_os_architecture_model) [6/6 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 01. 移动与桌面系统共同基础与移动特定约束模型 (`01_shared_foundations_different_constraints.rst`)
- [x] 02. 核心系统全链路解构：硬件、内核、驱动、服务、框架到应用 (`02_core_system_chain_hardware_to_app.rst`)
- [x] 03. 硬件能力中介化与系统控制面：独占与共享设备仲裁 (`03_hardware_capability_mediation_and_system_control.rst`)
- [x] 04. 移动平台约束模型：电量预算、热包络与后台唤醒控制 (`04_mobile_platform_constraint_model.rst`)
- [x] 05. 四大系统边界拓扑图：硬件、厂商驱动、系统服务与应用沙箱 (`05_system_runtime_app_boundaries.rst`)
- [x] 06. 双平台架构映射：Android 基于 Linux 与 Apple 基于 Darwin/XNU (`06_android_above_linux_apple_above_xnu.rst`)

Part 2: 智能手机硬件平台与 SoC 拓扑 (02_mobile_hardware_and_soc_topology) [6/6 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 07. 移动 SoC 芯片级异构拓扑：片上互连、内存争用与供电域 (`01_mobile_soc_component_map.rst`)
- [x] 08. CPU 大小核异构拓扑与动态调频：EAS、DVFS 与前台加速 (`02_cpu_big_little_topology_and_dvfs.rst`)
- [x] 09. GPU 移动渲染与硬件合成输出：TBDR、BufferQueue 与 HWC (`03_gpu_display_engine_and_hwc.rst`)
- [x] 10. 相机传感器与 ISP 图像流水线：MIPI CSI、3A 闭环与 RAW 域处理 (`04_isp_camera_sensor_and_imaging_pipeline.rst`)
- [x] 11. NPU 边缘 AI 算力与异构计算：量化加速与底层硬件抽象 (`05_npu_edge_ai_and_heterogeneous_compute.rst`)
- [x] 12. 移动通信基带与射频前端：Modem-AP 接口协议与 IPC 通道 (`06_baseband_modem_and_rf_frontend.rst`)

Part 3: 引导链路与安全启动 (03_boot_chain_and_secure_startup) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 13. 系统加电与 Boot ROM 硬件信任根初始化 (`01_power_on_sequence_and_boot_rom.rst`)
- [x] 14. 校验启动链与 dm-verity 块设备完整性保护 (`02_verified_boot_and_dm_verity.rst`)
- [x] 15. 系统分区结构与 A/B 无缝 OTA 升级机制 (`03_system_partitions_ab_seamless_ota.rst`)
- [x] 16. Android 启动全链路：内核引导、init.rc、Zygote 与 system_server (`04_android_startup_kernel_init_zygote_system_server.rst`)
- [x] 17. Apple 启动全链路：Secure Boot、iBoot、XNU 内核与 SpringBoard (`05_apple_startup_iboot_xnu_launchd_springboard.rst`)

Part 4: 移动内核底层机制 (04_mobile_kernel_subsystems) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 18. 能效感知调度器 (EAS) 与前台响应：容量模型、WALT 与 UI 线程保障 (`01_eas_energy_aware_scheduler_and_responsiveness.rst`)
- [x] 19. 虚拟内存与物理内存治理：ZRAM 压缩、Ashmem 匿名共享、LMKD 与 iOS Jetsam 回收机制 (`02_virtual_memory_ashmem_and_low_memory_killer.rst`)
- [x] 20. 中断处理、下半部机制与移动驱动交互 (`03_interrupt_bottom_half_dma_and_drivers.rst`)
- [x] 21. Tickless Idle、WakeLock 与系统休眠唤醒状态机 (`04_tickless_idle_wakelock_and_power_management.rst`)
- [x] 22. 内核安全边界与攻击面收敛：DAC、MAC 与系统调用过滤 (`05_kernel_isolation_dac_mac_and_attack_surface.rst`)

Part 5: 驱动模型、HAL 与厂商边界 (05_driver_model_and_hardware_abstraction) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 23. HAL 架构演进：从旧式 dlopen 动态库到 Project Treble Binderized HAL 与 Stable AIDL (`01_hal_evolution_dlopen_to_aidl.rst`)
- [x] 24. 厂商接口契约 (VINTF) 与系统镜像 (GSI) 解耦架构 (`02_vintf_compatibility_matrix_and_gsi.rst`)
- [x] 25. 传感器 HAL 与 Sensor Hub 通信：IIO 子系统与低功耗监听 (`03_sensor_hal_and_iio_subsystem.rst`)
- [x] 26. 音频与多媒体 HAL 架构：AudioFlinger、ALSA 与低时延通路 (`04_audio_hal_and_subsystem.rst`)
- [x] 27. Apple 驱动框架演进：IOKit 面向对象模型与 DriverKit 用户态扩展 (DEXT) (`05_apple_driverkit_and_iokit.rst`)

Part 6: 系统服务与 IPC 通信中枢 (06_system_services_and_ipc_spine) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 28. SystemServer 架构与核心系统服务治理 (`01_system_server_and_servicemanager.rst`)
- [x] 29. Binder IPC 驱动底层机制：单次内存拷贝 (`mmap`) 与引用计数 (`02_binder_driver_mmap_and_refcounts.rst`)
- [x] 30. Binder 协议栈与线程池动态调度 (`03_binder_protocol_and_thread_pool.rst`)
- [x] 31. 硬件能力仲裁与多租户并发访问控制 (`04_hardware_arbitration_and_multi_tenant.rst`)
- [x] 32. Apple 服务治理中枢：launchd 守护进程网格与 XPC 异步通信机制 (`05_apple_launchd_and_xpc.rst`)

Part 7: 应用运行时与生命周期策略 (07_runtime_layer_and_process_lifecycle) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 33. Android 运行时 (ART) 微架构：DEX 格式、解释器、JIT 与 AOT (dex2oat) (`01_art_interpreter_jit_aot.rst`)
- [x] 34. ART 并发垃圾回收 (CC-GC) 与停顿时间控制 (`02_art_concurrent_copying_gc.rst`)
- [x] 35. Zygote 预加载与写时复制 (COW) 进程孵化加速 (`03_zygote_preload_and_fork_model.rst`)
- [x] 36. 应用前后台生命周期与进程优先级状态机 (`04_app_lifecycle_and_process_priority.rst`)
- [x] 37. Apple 原生运行时：Mach-O 格式、dyld 4 共享缓存与 ARC 内存模型 (`05_apple_dyld_and_arc.rst`)

Part 8: 移动安全沙箱、存储与数据保护 (08_mobile_security_storage_and_user_data) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 38. 应用沙箱底层机制：Linux UID 隔离与 SELinux 策略转换 (`01_uid_sandbox_and_selinux.rst`)
- [x] 39. 硬件密钥管理：Android KeyStore 与 Apple Secure Enclave (SEP) (`02_keystore_and_secure_enclave.rst`)
- [x] 40. 移动存储架构与文件系统：F2FS 闪存优化与文件级加密 (FBE) (`03_f2fs_and_file_based_encryption.rst`)
- [x] 41. 分区存储 (Scoped Storage) 与 SAF 框架访问控制 (`04_scoped_storage_and_saf.rst`)
- [x] 42. 功耗与后台执行治理：Doze 模式、App Standby 与 iOS BGTask (`05_power_management_doze_and_bgtask.rst`)
