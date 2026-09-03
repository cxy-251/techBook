===========================================
Part 6: 系统服务与 IPC 通信中枢
===========================================

本模块解构移动操作系统的能力代理与通信中枢，深入剖析 system_server 服务宿主、Android Binder 驱动内核机制、Apple Mach Port/XPC 消息通信、核心硬件仲裁与服务看门狗故障隔离。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_system_server_and_servicemanager
   02_binder_driver_mmap_and_refcounts
   03_binder_protocol_and_thread_pool
   04_hardware_arbitration_and_multi_tenant
   05_apple_launchd_and_xpc
