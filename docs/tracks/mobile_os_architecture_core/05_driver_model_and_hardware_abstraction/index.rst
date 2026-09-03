===========================================
Part 5: 驱动模型、HAL 与厂商边界
===========================================

本模块解构移动操作系统的硬件抽象机制与厂商软硬件分界线，剖析从传统 dlopen 动态库到 Project Treble 跨进程 Binderized HAL 与 Stable AIDL 的架构演进、VINTF 兼容性矩阵与 GSI 解耦契约、传感器 IIO 与音频 HAL 核心实装，以及 Apple IOKit 到 DriverKit 用户态驱动体系。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_hal_evolution_dlopen_to_aidl
   02_vintf_compatibility_matrix_and_gsi
   03_sensor_hal_and_iio_subsystem
   04_audio_hal_and_subsystem
   05_apple_driverkit_and_iokit
