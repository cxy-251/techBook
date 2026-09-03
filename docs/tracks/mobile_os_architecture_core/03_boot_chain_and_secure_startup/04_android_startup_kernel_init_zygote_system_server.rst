========================================================================
Chapter 16: Android 启动全链路：Linux 内核、init.rc、Zygote 与 system_server
========================================================================

.. note:: 前置背景与认知承接
   前一章解构了 GPT 存储分区拓扑、A/B 双槽位无缝 OTA 状态机、Virtual A/B 写时复制（CoW Snapshot）与硬件 eFuse/RPMB 防版本回滚保护。当引导加载程序（Bootloader）通过安全验签并正确解压加载 `boot` 分区中的 Linux 内核与 RAMDisk 后，操作系统正式迈过了硬件与固件阶段，进入内核执行与用户空间初始化的核心主干。本章将系统剖析 Android 启动的全链路流转微架构：从 Linux 内核 `start_kernel()` 汇编入口与 1 号进程 `init` 的诞生、`init.rc` 脚本语法与分阶段触发器状态机（First Stage / Second Stage Init）、`ueventd` 设备节点动态挂载与 SELinux 策略加载，到 `Zygote` 进程孵化器预加载（Preload ART & Resources）与 `system_server` 核心系统服务树的构建。

------------------------------------------------------------------------
16.1 Linux 内核引导与 PID 1 init 进程的诞生
------------------------------------------------------------------------

当 Bootloader 将控制权移交给 Linux 内核后，CPU 处于特权级最高的一级异常级别（ARM64 Exception Level 1 - EL1）。内核执行流程从汇编入口（`arch/arm64/kernel/head.S`）迅速跳转至通用 C 语言初始化主入口 `start_kernel()`（`init/main.c`）。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Linux 内核核心子系统初始化拓扑                    |
   +-------------------------------------------------------------------------+

   [ Bootloader 移交控制权 (CPU: EL1 内核态) ]
        |
        v
   [ start_kernel() - init/main.c ]
        |
        +---> setup_arch(&command_line): 解析扁平设备树 (FDT), 初始化物理内存节点与 CPU 拓扑
        +---> mm_init(): 建立伙伴系统 (Buddy System) 与 Slab 内存分配器
        +---> sched_init(): 初始化 CFS / EAS 能效感知调度器核心数据结构与运行队列
        +---> trap_init() / init_IRQ(): 配置异常向量表, 初始化 ARM GIC 中断控制器
        +---> time_init(): 校准硬件定时器, 初始化 Generic Timer
        |
        v
   [ rest_init() - 派生核心线程 ]
        |
        +---> 创建 2 号内核线程: kthreadd (PID 2 - 所有内核线程的祖先)
        |
        +---> 创建 1 号用户态进程: kernel_init (PID 1)
        |
        v
   [ PID 0 进程蜕化为 cpu_idle() 闲置循环线程 ]

从内核态到用户态的特权级降级
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 `kernel_init()` 线程执行末尾，内核需要启动用户空间的第一个进程：

1. **挂载根文件系统 (RAMDisk)**：内核解压随 `boot.img` 载入内存的初始 RAMDisk；
2. **寻找可执行文件**：内核依次尝试检索 `/init`，即 Android 的根初始化程序；
3. **特权级降级 (EL1 $	o$ EL0)**：
   内核调用 `run_init_process("/init")`，底层通过执行 `eret`（Exception Return）异常返回指令，**将 CPU 执行级别从 EL1（内核态）强行降级至 EL0（用户空间）**。自此，PID 为 1 的 `init` 进程正式成为 Android 用户空间所有进程的绝对祖先！

------------------------------------------------------------------------
16.2 init 进程执行状态机：Two-Stage Init 与 SELinux 注入
------------------------------------------------------------------------

为了支持动态分区挂载与尽早确立安全防线，现代 Android 将 `init` 进程严格划分为**两阶段启动架构（Two-Stage Init）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Android init 两阶段启动与安全初始化状态机              |
   +-------------------------------------------------------------------------+

   [ 内核启动 /init (First-Stage Init - 运行于 RAMDisk 极简环境) ]
        |
        v
   1. 挂载虚拟文件系统: mount("tmpfs", "/dev"), mount("sysfs", "/sys"), mount("proc", "/proc")
   2. 早期分区挂载 (Early Mount):
      * 驱动 dm-verity 与 dm-linear，从 super 分区挂载真正的 /system, /vendor 物理镜像
   3. 切换根目录 (pivot_root) 至挂载就绪的 /system
        |
        v [ 调用 execv("/system/bin/init", ["second_stage"]) 执行自跳转! ]
   +----+--------------------------------------------------------------------+
        |
        v
   [ Second-Stage Init (运行于完整 /system 环境) ]
        |
        +---> [ 关键安全截断: SELinux 策略编译与强制注入 ]
        |        * 读取 /system/etc/selinux/plat_sepolicy.cil 与 vendor 策略
        |        * 编译安全策略并写入内核 /sys/fs/selinux/load
        |        * 调用 selinux_enforcing_set(1) 开启严格 MAC 强制访问控制!
        |
        +---> [ 初始化属性服务 (Property Service) ]
        |        * 创建共享内存区域 (/dev/__properties__) 并通过 mmap 映射至全域
        |
        +---> [ 启动 epoll 事件主循环 ]
                 * 监听 SIGCHLD 信号 (回收僵尸进程)
                 * 监听 /dev/socket/property_service (属性写入请求)
                 * 解析并执行 init.rc 脚本拓扑!

------------------------------------------------------------------------
16.3 init.rc 脚本语言语法与分阶段触发器状态机
------------------------------------------------------------------------

Android 初始化系统的核心逻辑由 `init.rc` 及其引入的子模块（如 `/system/etc/init/*.rc`, `/vendor/etc/init/*.rc`）驱动。

init.rc 四大核心语法构件
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: init.rc 脚本核心语法结构
   :widths: 20 35 45
   :header-rows: 1
   :class: tight-table

   * - 语法构件
     - 语法形态与关键字
     - 物理微架构功能与语义
   * - **Actions (行为块)**
     - `on <trigger> [&& <trigger>]*`
     - 命名事件触发器。当满足指定状态时，顺序执行其内部包含的指令序列。
   * - **Commands (指令集)**
     - `mkdir`, `mount`, `chown`, `setprop`, `write`
     - 由 `init` 进程内部直接实现的原子操作（非通过 Shell 执行，性能高）。
   * - **Services (服务声明)**
     - `service <name> <path> <args>*`
     - 声明由 `init` 孵化并监控的守护进程。配置运行身份（`user`, `group`）与崩溃重启策略。
   * - **Imports (模块导入)**
     - `import /path/to/rc`
     - 实现多厂商与多模块解耦，运行时动态将子 `.rc` 文件插入解析语法树。

核心触发器分阶段执行流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`init` 进程依据严格的时间序依次推进触发器（Triggers）：

.. code-block:: text

   [ early-init ] ---> [ init ] ---> [ late-init ]
                                            |
        +-----------------------------------+-----------------------------------+
        v                                   v                                   v
   [ early-fs ] -> [ fs ] -> [ post-fs ] -> [ early-boot ] -> [ boot ] -> 启动各守护进程

- **`fs` 阶段**：挂载所有必须的物理与逻辑磁盘分区；
- **`post-fs` 阶段**：系统分区只读挂载就绪，启动基础核心守护进程（如 `ueventd`, `servicemanager`, `hwservicemanager`, `vold` 卷管理守护进程）；
- **`boot` 阶段**：启动运行时底座——核心守护进程 `zygote`！

------------------------------------------------------------------------
16.4 Zygote 进程孵化器的诞生与资源预加载 (Preload)
------------------------------------------------------------------------

传统 Linux 应用启动依赖 `fork() + execve()`。然而，在 Android 环境下，Java / Kotlin 应用依赖极其庞大的 Android Runtime（ART）虚拟机、核心类库（Framework Classes）以及庞大的系统资源包。若每个应用启动都完整加载一次 ART，应用冷启动时延将突破数秒，且物理内存开销不可承受。

**Zygote（受精卵）** 通过“**进程分裂 + 写时复制（Copy-on-Write - CoW）**”完美破局：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Zygote 预加载与极速孵化模型                       |
   +-------------------------------------------------------------------------+

   [ init 进程解析 init.zygote64.rc ]
        |
        v
   [ 启动 /system/bin/app_process64 ]
        |
        v
   [ AndroidRuntime::start() - frameworks/base/core/jni/AndroidRuntime.cpp ]
        |  1. 调用 JNI_CreateJavaVM() 启动 ART 虚拟机实例
        |  2. 注册全套核心 JNI 本地系统接口
        v
   [ 进入 Java 世界: ZygoteInit.main() ]
        |
        +---> [ preloadClasses(): 预解析并加载 6000+ 个常用 Framework 类 ]
        |        * 预先完成字节码验证 (Verification) 与内存链接 (Linking)
        |
        +---> [ preloadResources(): 预加载公共系统 Drawables / Colors / Layouts ]
        |
        +---> [ preloadSharedLibraries(): 加载 libandroid_runtime.so 等共享 C++ 库 ]
        |
        +---> [ 执行一次全代垃圾回收 (gcAndFinalize) 冻结内存基底 ]
        |
        v
   [ 创建本地 IPC 监听套接字: /dev/socket/zygote ]
        |
        +---> [ 孵化系统核心大管家: forkSystemServer() -> 衍生 system_server 进程 ]
        |
        v
   [ ZygoteServer.runSelectLoop(): 进入死循环, 永久监听并极速响应应用启动请求 ]

写时复制 (Copy-on-Write) 的物理内存节省
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当应用通过 `AMS` 请求启动新进程时，Zygote 仅需调用一次底层的 `fork()` 系统调用。由于 Linux 的虚拟内存机制，新应用进程与 Zygote **100% 共享所有预加载的数百兆类库与资源物理内存页**！仅当应用尝试修改某特定变量时，MMU 硬件才会触发缺页中断并分配新的私有物理页，使每个 App 的基础内存开销压缩至极限。

------------------------------------------------------------------------
16.5 system_server 初始化与系统核心服务树的建立
------------------------------------------------------------------------

`system_server` 是 Android 最核心的 Java 特权系统进程，掌控着整机所有系统服务与硬件访问中介。

SystemServer 三阶段核心服务唤醒时序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 `SystemServer.java` 的 `run()` 方法中，核心系统服务按照强依赖关系分三批被依次唤醒并注册至 `ServiceManager`：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     system_server 三阶段服务构建拓扑                    |
   +-------------------------------------------------------------------------+

   [ Zygote.forkSystemServer() -> 诞生 system_server 进程 (UID: 1000 SYSTEM) ]
        |
        v
   [ SystemServer.run() ]
        |
        v
   [ 阶段 1: 启动引导服务 (startBootstrapServices) ]
        |  * ActivityTaskManagerService (ATMS): 管理 Activity 栈结构与生命周期
        |  * ActivityManagerService (AMS): 管理进程生命周期与四大组件调度
        |  * PowerManagerService: 电源状态机与唤醒锁 (WakeLock) 仲裁
        |  * DisplayManagerService: 屏幕物理参数与虚拟显示管理
        |  * PackageManagerService (PKMS): 解析 /system 与 /data 中的 APK 签名与元数据
        v
   [ 阶段 2: 启动核心服务 (startCoreServices) ]
        |  * BatteryService: 监听硬件电池温度与充电状态
        |  * UsageStatsService: 应用使用时长统计
        |  * GpuService: GPU 驱动与调试通道管理
        v
   [ 阶段 3: 启动其他服务 (startOtherServices) ]
        |  * WindowManagerService (WMS): 管理 Surface 窗口 z-order 与显示排版
        |  * InputManagerService (IMS): 监听触控硬件事件并向前台窗口分发
        |  * CameraServiceProxy, AudioService, NetworkManagementService, JobSchedulerService...
        v
   [ 所有服务就绪: ActivityManagerService.systemReady() ]
        |  * 向全域广播 Intent.ACTION_BOOT_COMPLETED
        |  * 启动首个前台应用: Launcher (桌面应用) 显示主屏幕！

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从硅片内核执行出发，完整推导了 Android 从 Linux 内核 `start_kernel()` 降级至用户态、`init` 两阶段执行状态机与 SELinux 强制注入、`init.rc` 事件驱动脚本解析、`Zygote` 依托 Copy-on-Write 实现的 Framework 极速预加载，以及 `system_server` 三阶段系统服务树的完整启动全貌。

至此，我们已经深入理解了 Android 开源生态的启动全流程。而在另一大移动阵营中，Apple 构建了一套完全不同的安全引导与进程守护体系——下一章我们将聚焦于 **Apple 启动全链路：Secure Boot → iBoot 阶段 → XNU 内核初始化 → launchd 守护树 → SpringBoard**，深入剖析 Darwin/XNU 内核、Mach 消息引导、`launchd` 属性列表（plist）守护架构以及 iOS 图形主桌面 SpringBoard 的启动哲学。
