====================================================================
移动操作系统底层架构与软硬件边界全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书架构体系目录:
   :numbered:

   ROADMAP
   01_mobile_os_architecture_model/index
   02_mobile_hardware_and_soc_topology/index
   03_boot_chain_and_secure_startup/index
   04_mobile_kernel_subsystems/index
   05_driver_model_and_hardware_abstraction/index
   06_system_services_and_ipc_spine/index
   07_runtime_layer_and_process_lifecycle/index
   08_mobile_security_storage_and_user_data/index

专著简介与架构全景
==================

本专著是一部以现代移动操作系统（Android AOSP 与 Apple iOS/Darwin/XNU）为研究对象，系统解构移动平台软硬件交互边界、受控资源治理模型以及端到端能力流转机制的工业级技术著作。

移动操作系统并非桌面操作系统的简单微缩版，而是围绕“**电量预算（Battery Budget）、热包络（Thermal Envelope）、隐私数据隔离（Privacy Sandbox）与低延迟前台交互响应**”构建的一整套高约束自治系统。全书坚持“底层物理事实与操作系统源码实现优先”原则，自底向上穿透移动 SoC 芯片级异构拓扑、安全引导链、Linux/XNU 内核子系统、HAL 厂商驱动边界、系统服务中枢与 Binder/XPC 进程间通信通道，完整还原移动平台从硬件能力到用户可见体验的全部工程机理。

核心知识模块拓扑
----------------

.. list-table:: 移动操作系统架构与核心知识体系映射
   :widths: 10 25 35 30
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 系统关键技术与源码实现路径
     - 解决的核心工程问题
   * - 01
     - 移动 OS 架构模型与系统边界
     - 受控资源治理、前后台生命周期、跨层能力路径、Android Linux vs Apple XNU 映射
     - 建立移动操作系统受控能力流转的全局心智模型
   * - 02
     - 智能手机硬件平台与 SoC 拓扑
     - CPU 大小核拓扑、DVFS 调频、Display Engine/HWC 合成、ISP 图像链路、NPU 与电源硬件
     - 解构芯片级硬件能力源头与多模块物理资源争用
   * - 03
     - 引导链路与安全启动 (Boot Chain)
     - Boot ROM、硬件信任根 (Root of Trust)、AVB/dm-verity、A/B 分区 OTA 与 init/Zygote 启动链
     - 建立从上电第一周期到用户空间可用性的可信执行环境
   * - 04
     - 移动内核底层机制 (Mobile Kernel)
     - EAS 能效调度器、Low Memory Killer (LMKD)、WakeLock 电源管理、系统调用截获与 DAC/MAC
     - 解决移动场景下的帧率抖动 (Jank)、内存枯竭与异常功耗
   * - 05
     - 驱动模型、HAL 与厂商边界
     - HIDL/AIDL HAL 接口、Project Treble 架构、Camera/Audio/Gralloc HAL、Apple DriverKit
     - 隔离底层硬件私有驱动，实现系统镜像与厂商 BSP 的解耦升级
   * - 06
     - 系统服务与 IPC 通信中枢
     - system_server 架构、ServiceManager、Binder 驱动内核机制、Apple launchd/XPC 与硬件仲裁
     - 承载全局系统状态，实现多应用并发下的安全能力代理
   * - 07
     - 应用运行时与生命周期策略
     - ART 虚拟机 (DEX/JIT/AOT/GC)、Zygote 预加载、dyld 共享缓存、ARC 机制与进程五大状态机
     - 优化应用冷热启动速度，保障进程死亡后的可重入状态恢复
   * - 08
     - 移动安全沙箱、存储与数据保护
     - UID 沙箱隔离、SELinux 策略、KeyStore/Secure Enclave、分区存储 (Scoped Storage) 与 SAF
     - 构筑应用数据最小权限访问与持久化安全保护闭环

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
