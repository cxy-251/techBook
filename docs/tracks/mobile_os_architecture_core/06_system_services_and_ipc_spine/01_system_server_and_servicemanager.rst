========================================================================
Chapter 28: SystemServer 架构与核心系统服务治理
========================================================================

.. note:: 前置背景与认知承接
   在前五部分（Part 1 ~ Part 5）中，我们系统剖析了移动操作系统的底层硬件拓扑、安全引导链、内核子系统以及硬件抽象层（HAL）模型。从 Project Treble 跨进程 Binderized HAL 到 Apple DriverKit 用户态扩展，现代移动系统确立了“硬件访问接口契约化、特权域最小化”的底层共识。然而，驱动与硬件抽象仅解决了“单个设备如何受控操作”的技术问题；在完整的智能终端上，成百上千个第三方应用程序并发申请屏幕、相机、定位、音频、电源与网络等有限物理资源，若无集中式权威仲裁者，系统必然陷入资源争用踩踏、功耗失控与隐私泄露的混乱深渊。

   本章开启 **Part 6: 系统服务与 IPC 通信中枢**。我们将视角向上推移至移动操作系统的心脏与控制中枢——Android **system_server** 及其统一名字发现中枢 **ServiceManager**。本章将解构 `system_server` 的进程孵化与三阶段服务装配流水线、`ServiceManager` 的句柄 0 寻址底座与授权验证、Framework Manager 与 Binder Service Backend 的分层桥接，并深入剖析四大核心系统服务（AMS/ATMS、PMS、WMS、PowerMS）的事实所有权模型与系统级 Watchdog 死锁防御自愈机制。

------------------------------------------------------------------------
28.1 system_server 进程孵化与初始化拓扑
------------------------------------------------------------------------

从 Zygote 到特权系统宿主进程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Android 启动全链路（Chapter 16）中，系统加电后由内核拉起用户空间第一个进程 `init`，`init` 依照 `init.rc` 脚本启动 64 位应用孵化中枢 `zygote`。Zygote 完成基础 Java/ART 运行时预加载与类库热身之后，首要任务就是派生出整个操作系统的业务托管容器——`system_server`。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  system_server 孵化与执行特权降级时序                   |
   +-------------------------------------------------------------------------+

   [ init 进程 (PID 1, root) ]
        |
        v 解析 init.rc 启动
   [ app_process64 (ZygoteInit, PID ~500, root) ]
        |
        | 1. 预加载 ~7000 个核心类与系统资源
        | 2. 准备套接字 /dev/socket/zygote
        | 3. 调用 Zygote.forkSystemServer()
        v
   [ system_server 进程 (fork 诞生, 继承 COW 页表) ]
        |
        +---> [ ZygoteInit.nativeZygoteInit() ]
        |          |
        |          v 调用 AppRuntime::onZygoteInit()
        |     [ ProcessState::self()->startThreadPool() ] (启动底层 Binder 线程池)
        |
        +---> [ Linux 内核凭据降级与沙箱隔离 ]
        |     - UID: 从 root(0) 降为 system(1000)
        |     - GID: system(1000) + 附加组 (graphics, input, audio, etc.)
        |     - Capabilities: 保留 CAP_SYS_PTRACE, CAP_KILL, CAP_SYS_RESOURCE 等特权位
        |     - SELinux: 跃迁至 u:r:system_server:s0 独立受限安全上下文
        |
        v
   [ com.android.server.SystemServer.main() ] ---> 开启 Java 服务三阶段装配流水线

`Zygote.forkSystemServer()` 在内核层执行 `fork()` 系统调用，利用写时复制（COW, Copy-On-Write）技术使 `system_server` 零延迟共享 Zygote 预加载的数千个核心系统类、Framework 框架代码及只读常量池，极大收缩内存物理驻留。

一旦分裂成功，`system_server` 立即切断与 Zygote 的控制套接字，通过 POSIX 系统调用放弃 `root (0)` 绝对特权，将有效用户 ID（EUID）降级为 `system (1000)`，同时配置严密的 Linux 附加用户组（`graphics` 访问显存节点、`audio` 访问音频节点、`net_raw` 监听套接字）。在 SELinux 层面，进程上下文由初始域跃迁至强制隔离的 `u:r:system_server:s0` 域，禁止加载任意未签名模块并严格限制原始设备节点访问。随后，C++ 原生层调用 `ProcessState::self()->startThreadPool()` 开启专用工作线程监听 `/dev/binder`，正式接入系统进程间通信总线。

三阶段服务装配流水线 (Three-Phase Bootstrapping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

进入 Java 层入口 `com.android.server.SystemServer.run()` 后，主线程并不杂乱地并行实例化服务，而是严格按照**拓扑依赖图**执行三阶段串行装配，确保基础物理依赖就绪后，上层业务服务方可接入：

.. list-table:: system_server 三阶段服务启动流水线与核心依赖
   :widths: 18 32 50
   :header-rows: 1
   :class: tight-table

   * - 启动阶段
     - 启动方法与核心服务集合
     - 阶段核心职责与关键拓扑依赖约束
   * - **阶段 1：引导服务**
       (Bootstrap Services)
     - `startBootstrapServices()`:
       
       - `Installer`
       - `ActivityTaskManagerService` (ATMS)
       - `ActivityManagerService` (AMS)
       - `PowerManagerService` (PowerMS)
       - `DisplayManagerService` (DMS)
       - `PackageManagerService` (PMS)
       - `SensorPrivacyService`
     - **不可或缺的底层基座**。
       
       - `Installer` 必须最先建立，以便通过守护进程 `installd` 操作底层 `/data` 目录；
       - `ATMS/AMS` 建立进程调度与组件管理骨架；
       - `PowerMS` 与 `DMS` 提供屏幕与供电支持；
       - `PMS` 解析全量 APK Manifest，读取系统签名与权限，为后续服务提供组件查询字典。
   * - **阶段 2：核心服务**
       (Core Services)
     - `startCoreServices()`:
       
       - `BatteryService`
       - `UsageStatsService`
       - `WebViewUpdateService`
       - `BinderCallsStatsService`
       - `DropBoxManagerService`
     - **系统运行态基础事实维护**。
       
       - 监听底层电池物理电量、温度与快充状态；
       - 追踪各 App 前后台时间窗，为温控降频与内存淘汰（LMKD）提供数据事实依据；
       - 初始化 WebView 运行核，管理系统崩溃日记收集。
   * - **阶段 3：其他服务**
       (Other Services)
     - `startOtherServices()`:
       
       - `WindowManagerService` (WMS)
       - `InputManagerService` (IMS)
       - `NetworkManagementService`
       - `ConnectivityService`
       - `NotificationManagerService`
       - `AudioService`、`LocationManagerService` 等 80+ 服务
     - **高层能力代理、外设中介与 UI 展示**。
       
       - `WMS` 建立窗口层级并连接 `SurfaceFlinger`；
       - `IMS` 连接内核 `EventHub` 与触控驱动；
       - 网络协议栈、定位框架、通知中心全面拉起；
       - 最终触发 `AMS.systemReady()`，启动系统桌面（Launcher）与锁屏（SystemUI）。

装配流水线中的生命周期回调步进 (Phase Milestones)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

服务被 `SystemServiceManager.startService()` 实例化后，由其内部的单例容器 `SystemServiceManager` 统一管控其生命周期。随着系统环境逐步就绪，管理器向所有派生自 `SystemService` 的对象广播状态阶梯事件：

1. `onBootPhase(PHASE_WAIT_FOR_DEFAULT_DISPLAY)`：基础显示通道就绪，WMS 可开始挂载默认屏幕树；
2. `onBootPhase(PHASE_LOCK_SETTINGS_READY)`：用户凭据与加密数据库（FBE 凭据加密区 CE）已可访问；
3. `onBootPhase(PHASE_SYSTEM_SERVICES_READY)`：所有已注册系统服务核心端口就绪，允许服务之间发起内部交叉调用；
4. `onBootPhase(PHASE_BOOT_COMPLETED)`：系统桌面启动并稳定运行，解锁广播发送，系统全面向第三方 App 开放处理能力。

这种分阶段事件驱动模型解耦了数十个系统服务之间的循环依赖（Circular Dependencies），避免了早期 Android 系统中因服务初始化竞争引发的空指针崩溃。

------------------------------------------------------------------------
28.2 ServiceManager 权威命名注册表与 Binder 寻址底座
------------------------------------------------------------------------

句柄 0 (Handle 0) 的硬件物理映射与总线接入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在基于 Binder 的 IPC 体系中，通信双方并不知晓对方进程的物理内存指针或内存布局，必须依靠 32 位整型 **Binder Handle（句柄）** 进行虚拟定位。然而，系统冷启动时，调用方进程如何获取目标服务的第一个 Handle？这引出了经典的“元名字服务寻址悖论”。

Android 在 Linux 内核 `binder.c` 驱动中硬性设定了核心寻址基准：**Handle 0 永远永久保留并强制映射为系统注册表守护进程——ServiceManager**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     ServiceManager 核心注册与查询闭环                   |
   +-------------------------------------------------------------------------+

   [ 普通客户端进程 / App ]            [ system_server / 核心服务进程 ]
             |                                        |
             |                                        | 1. addService("activity", amsBinder)
             |                                        v
   +=========================================================================+
   | Linux 内核 Binder 驱动空间 (/dev/binder)                                |
   |                                                                         |
   | - 截获目标 Handle = 0 的事务请求                                        |
   | - 自动重定向至内部全局静态变量: binder_context_mgr_node                 |
   +=========================================================================+
             |                                        |
             |                                        | 2. 生成本地代理节点，注册表落盘
             v                                        v
   +-------------------------------------------------------------------------+
   | 用户态 ServiceManager 守护进程 (/system/bin/servicemanager)             |
   |                                                                         |
   | 核心数据结构:                                                           |
   | std::map<std::string, Service> mNameToService;                          |
   |                                                                         |
   | [ 安全校验 ]                                                            |
   | - 查询 SELinux service_contexts 规则:                                   |
   |   allow system_server activity_service:service_manager add;             |
   | - 阻断非特权进程冒名伪造核心服务                                        |
   +-------------------------------------------------------------------------+
             |
             | 3. getService("activity")
             | 4. 内核在调用方进程的 Handle 空间分配新 Handle X，指向同一目标节点
             v
   [ 客户端拿到 Handle X，封装为 IActivityManager.Stub.Proxy 发起业务调用 ]

当任何 C++ 原生进程执行 `defaultServiceManager()` 时，其内部封装的远程代理对象 `BpServiceManager` 直接将其内部目标句柄硬编码为 `0`：

.. code-block:: cpp

   // frameworks/native/libs/binder/IServiceManager.cpp 核心逻辑
   sp<IServiceManager> defaultServiceManager() {
       std::call_once(gSmOnce, []() {
           // 创建目标 Handle 为 0 的 BpBinder，直连 ServiceManager
           sp<IBinder> binder = ProcessState::self()->getContextObject(nullptr);
           gDefaultServiceManager = interface_cast<IServiceManager>(binder);
       });
       return gDefaultServiceManager;
   }

任何向 Handle 0 发出的 Binder 事务，内核驱动无条件寻址至 `binder_context_mgr_node`。`servicemanager` 二进制守护程序在系统启动时通过 `ioctl(BINDER_SET_CONTEXT_MGR_EXT)` 确立自身地位；整机中有且仅有一个进程可成功获得此特权。

服务注册、查询语义与懒加载机制 (addService / getService / waitForService)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`ServiceManager` 向上暴露的核心接口遵循最精简的状态机模型：

.. code-block:: java

   // AIDL 接口语义抽象
   interface IServiceManager {
       void addService(String name, IBinder service, boolean allowIsolated, int dumpPriority);
       IBinder getService(String name);
       IBinder checkService(String name);
       IBinder waitForService(String name); // 现代 Android 关键引入
   }

1. **`addService`（服务注册）**：
   - 目标服务在装配阶段将其真实 Binder 实体对象提交给 `ServiceManager`；
   - 参数 `allowIsolated` 决定是否向隔离沙箱进程（Isolated Process，如 Chrome 渲染沙箱沙箱进程）开放；
   - 参数 `dumpPriority` 标定该服务在执行系统诊断转储（`dumpsys`）时的排队优先级（CRITICAL, HIGH, NORMAL）。
2. **`getService` 与 `checkService` 的语义分水岭**：
   - `checkService` 执行非阻塞探测查询。若服务未启动或注册表无记录，立即返回 `null`，不阻塞调用方线程；
   - 传统 `getService` 在服务端未注册时会执行有限时间的同步轮询重试。
3. **`waitForService` 与 Lazy Service（按需懒加载）**：
   - 在 Android 11+ 与车机/低内存设备上，为缩短冷启动时间并节约内存，大量非核心守护服务（如特定外设 HAL、生物认证扩展）被重构为 **Lazy Service**；
   - 客户端调用 `waitForService` 时，若服务未拉起，`ServiceManager` 会联合 `init` 动态孵化目标进程，完成实时拉起与接口绑定后再返回结果，调用方在此期间挂起等待。

SELinux service_contexts 强类型准入网关
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`ServiceManager` 绝非单纯的字符串键值哈希表，而是 Android 系统控制面的第一道 SELinux 防火墙。系统内所有允许注册的服务名称与类型必须在 `/system/etc/selinux/service_contexts` 中静态显式声明：

.. code-block:: text

   # 核心系统服务安全上下文静态映射
   activity                        u:object_r:activity_service:s0
   package                         u:object_r:package_service:s0
   window                          u:object_r:window_service:s0
   power                           u:object_r:power_service:s0
   camera                          u:object_r:cameraserver_service:s0
   SurfaceFlinger                  u:object_r:surfaceflinger_service:s0

每当收到注册（`addService`）或查询（`getService`）事务时，`servicemanager` 自动从内核获取调用方的安全凭据（SID / UID / PID），并调用内核 SELinux 策略执行点：

- **注册校验**：检查调用者域（如 `system_server`）是否具备目标服务的发布权限（`allow system_server activity_service:service_manager add;`）。任何未经授权的第三方进程若试图伪造注册 `activity` 服务，将在注册时刻被直接拦截并记录 AVC 审计违规；
- **查找校验**：检查调用者域（如 `untrusted_app`）是否被允许查找该服务（`allow untrusted_app window_service:service_manager find;`）。受限沙箱进程无法获取敏感管理服务的 Binder 代理。

------------------------------------------------------------------------
28.3 核心系统服务职责网格与事实所有权
------------------------------------------------------------------------

四大支柱服务的状态持有模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 `system_server` 内部运行着多达 100+ 个系统服务，其中最核心的四个被称为 Android 运行时的四大支柱服务。它们各自独占特定维度的**系统唯一事实所有权（State Ownership）**：

.. list-table:: system_server 四大支柱服务职责与系统事实拓扑
   :widths: 20 28 28 24
   :header-rows: 1
   :class: tight-table

   * - 核心系统服务
     - 独占事实所有权 (Owned States)
     - 核心管理边界与关键方法
     - 客户端 Framework 代理
   * - **ActivityManagerService**
       (AMS / ATMS)
     - 进程生命周期、进程 OOM 优先级阶梯评分 (`oom_score_adj`)、任务栈拓扑、前台交互焦点、广播队列
     - - `startActivity()`
       - `killProcess()`
       - `setProcessStates()`
       - `registerReceiver()`
     - `ActivityManager` / `ActivityTaskManager`
   * - **PackageManagerService**
       (PMS)
     - APK 元数据注册表、系统权限定义与动态授权表、组件导出表、系统签名校验、ABI/So 路径解析
     - - `getInstalledPackages()`
       - `checkPermission()`
       - `resolveIntent()`
       - `installPackage()`
     - `PackageManager`
   * - **WindowManagerService**
       (WMS)
     - 全局窗口 Token 树、Z-Order 堆叠顺序、屏幕物理旋转与显示切割区、输入事件焦点窗口判定
     - - `addWindow()`
       - `relayoutWindow()`
       - `setFocusedApp()`
       - `createSurfaceControl()`
     - `WindowManager`
   * - **PowerManagerService**
       (PowerMS)
     - 屏幕亮灭状态、硬件 WakeLock 计数器、系统休眠（Suspend）锁定、芯片温控降频等级联动
     - - `acquireWakeLock()`
       - `goToSleep()`
       - `wakeUp()`
       - `userActivity()`
     - `PowerManager`

Java 集中控制面 vs Native 分布式数据面
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

一个经典的架构疑问是：**为什么 Android 不把所有的系统服务全部塞入 `system_server`？**

答案在于**控制面（Control Plane）**与**数据面（Data Plane）**在时延、吞吐与崩溃容忍度上的根本差异：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               控制面与数据面的双轨架构隔离拓扑                          |
   +-------------------------------------------------------------------------+

   [ 控制面集中化: system_server (Java 运行时) ]
   +-------------------------------------------------------------------------+
   | - 职责: 策略判定 (谁能做)、生命周期流转、全局状态仲裁、权限审计         |
   | - 特点: 业务逻辑极度复杂，依赖类库庞大，容忍毫秒级调度延迟             |
   | - 承载: AMS, PMS, WMS, PowerMS, AudioService, NotificationManager      |
   +-------------------------------------------------------------------------+
           |                                                 |
           | 1. 下发合成图层元数据 (Layer/Z-Order)           | 2. 传递物理硬件配置 (SampleRate)
           v                                                 v
   [ 数据面解耦化: 独立 Native 守护进程 (C++ 原生运行时) ]
   +----------------------------------+  +----------------------------------+
   | SurfaceFlinger 进程              |  | AudioFlinger (audioserver) 进程  |
   | - 纯 C++ 实现，零 GC 抖动风险    |  | - 独占实时音频线程 (SCHED_FIFO)  |
   | - 专精每秒 120 帧物理屏幕合成    |  | - 专精毫秒级双声道混音与输出     |
   | - 直接操作 GPU/DPU 显存 DMA 描述符|  | - 直接对齐 ALSA 硬件环形缓冲区   |
   +----------------------------------+  +----------------------------------+

1. **GC 停顿与实时性冲突**：`system_server` 是一个巨大的 Java 虚拟机进程，持有海量对象。高频的物理帧合成（如 120Hz 刷新率下每 8.3ms 一帧）或音频流采样（每 5ms 一批 PCM 数据）若在 `system_server` 内执行，ART 虚拟机的并发垃圾回收（CC-GC）带来的微小停顿都会直接引发肉眼可见的掉帧（Jank）或音频爆音；
2. **内存与指针操作开销**：多媒体帧缓冲（GraphicBuffer / DMA-BUF）动辄数十兆字节，Native 进程能够直接通过 C++ 指针解引用与系统调用完成无锁零拷贝传递，完全规避了 JNI 数组拷贝与内存对齐惩罚；
3. **故障爆炸半径控制**：音频解码库或相机驱动扩展极易因厂商私有代码缺陷产生段错误（SIGSEGV）。将易崩模块放入独立守护进程（`audioserver`, `cameraserver`），即使进程崩溃也仅导致播放中断并可被系统自动重启，绝不会连带击垮 `system_server` 导致整机重启。

------------------------------------------------------------------------
28.4 Framework Manager 桥接模式与客户端存根
------------------------------------------------------------------------

SystemServiceRegistry 与单例客户端缓存
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于应用程序开发者而言，获取系统能力通常始于一行极为简单的公开 SDK API：

.. code-block:: java

   LocationManager lm = (LocationManager) context.getSystemService(Context.LOCATION_SERVICE);
   lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, listener);

这行代码背后隐藏着精妙的**代理桥接模式（Proxy-Bridge Pattern）**：

.. code-block:: text

   [ App 进程空间 ]
   +-------------------------------------------------------------------------+
   | 业务代码: context.getSystemService(LOCATION_SERVICE)                     |
   |      |                                                                  |
   |      v 查询静态注册表                                                   |
   | SystemServiceRegistry (维护客户端 Manager 单例缓存)                     |
   |      |                                                                  |
   |      | 首次获取: 触发 CachedServiceFetcher.createService()              |
   |      v                                                                  |
   | ServiceManager.getServiceOrThrow("location")                            |
   |      |                                                                  |
   |      v 返回底层通用 Binder 代理句柄: IBinder (BpBinder)                 |
   | ILocationManager.Stub.asInterface(binder)                               |
   |      |                                                                  |
   |      v 包装为强类型 AIDL 代理: ILocationManager.Stub.Proxy              |
   | 实例化包装对象: new LocationManager(context, proxy)                     |
   +-------------------------------------------------------------------------+
          |
          | 调用 requestLocationUpdates()
          | 内部调用 proxy.registerLocationListener(..., mListenerTransport)
          v
   [ 发起底层 Binder 跨进程事务 (ioctl BINDER_WRITE_READ) ]

在 App 进程生命周期内，`SystemServiceRegistry` 会缓存 `LocationManager` 的实例。`LocationManager` 本身只是一个轻量级的 Java SDK 外壳（Wrapper），它负责校验应用层参数有效性、管理 App 内部的回调分发器（如将 AIDL 回调接口转接至 App 的主线程 `Handler`），其底层真正持有的则是通往 `system_server` 的强类型 IPC 句柄——`ILocationManager.Stub.Proxy`。

AIDL 穿透分发与 JNI 边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

跨进程事务从 App 到系统服务的底层执行流严格遵循经典的 AIDL 桩-代理分发结构：

.. list-table:: 跨进程系统调用端到端穿透栈追踪
   :widths: 15 25 60
   :header-rows: 1
   :class: tight-table

   * - 执行阶段
     - 核心执行类与方法
     - 底层物理行为与内存状态变化
   * - **App 端发起**
     - `LocationManager.java`
     - 校验传入入参，从当前上下文提取包名 `context.getPackageName()`
   * - **Proxy 打包**
     - `ILocationManager.Stub.Proxy`
     - 分配 `Parcel` 对象，将方法编号（`TRANSACTION_requestLocationUpdates`）、接口描述符和业务参数序列化为二进制流
   * - **驱动陷入**
     - `BpBinder.transact()`
     - 通过 JNI 陷入 `android_util_Binder.cpp`，调用 `ioctl(binder_fd, BINDER_WRITE_READ)` 触发 CPU 异常向量陷入内核态
   * - **内核调度**
     - Linux 内核 `binder.c`
     - 挂起 App 线程，单次拷贝 Parcel 数据到 `system_server` 接收缓冲区，唤醒 `system_server` 处于休眠的 Binder 工作线程
   * - **服务端解包**
     - `ILocationManager.Stub.onTransact()`
     - `system_server` 工作线程被唤醒，读取方法编号，反序列化 Parcel 参数为 Java 原生数据对象
   * - **业务与权限执行**
     - `LocationManagerService.java`
     - 调用 `Binder.getCallingUid()` 获得真实调用者身份，执行权限审计，驱动底层 GNSS 硬件开始定位

死亡通知 (DeathRecipient) 与客户端脱机生命周期清理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

移动平台上的 App 极易因内存不足被 LMKD 杀死、因异常崩溃被系统终止或由用户在多任务视图滑卡清理。如果应用向 `system_server` 注册了长期监听回调（如传感器监听、位置监听、音频焦点），而在崩溃时未能主动注销，系统服务内持有的远端回调指针将变成僵尸节点，进而导致**系统服务内存泄漏**并向死进程分发事件导致系统报错。

为了根治此问题，系统服务在接纳客户端注册时，必须建立 **DeathRecipient（死亡观察者）** 机制：

.. code-block:: java

   // LocationManagerService 服务端注册监听核心实现范式
   public void registerLocationListener(ILocationListener listener, ...) {
       // 1. 获取客户端传来的 Binder 远程实体
       IBinder binder = listener.asBinder();
       
       // 2. 构建与调用者生命周期绑定的凭据包裹
       LocationClientRecord record = new LocationClientRecord(binder, ...);
       
       // 3. 向底层 Binder 注册死亡回调
       binder.linkToDeath(new IBinder.DeathRecipient() {
           @Override
           public void binderDied() {
               Slog.w(TAG, "检测到客户端进程意外死亡: " + record.packageName);
               synchronized (mLock) {
                   // 4. 从全局监听列表移除，彻底排空残留对象
                   removeLocationUpdatesLocked(record);
                   // 5. 若已无活跃客户端，下发硬件休眠指令降低整机功耗
                   updateGpsPowerStateLocked();
               }
           }
       }, 0);
   }

当 App 进程异常崩溃或被 SIGKILL 终结时，内核 Binder 驱动在清理该进程持有的 IPC 数据结构时，会自动识别所有与该进程相关的 `binder_ref` 引用，并向持有监听端的进程派发 `BR_DEAD_BINDER` 命令，在 `system_server` 的线程池中触发 `binderDied()` 回调，实现全自动的资源回收与硬件降功耗闭环。

------------------------------------------------------------------------
28.5 服务间死锁防范、Watchdog 监控与系统级恢复
------------------------------------------------------------------------

大一统进程模型 (Monolithic Process) 的脆弱性与跨服务死锁
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

将上百个核心系统服务打包在单一 `system_server` 进程中带来了高效的内存共享和极低的组件协同开销，但同时也引入了整机架构中最脆弱的软肋：**任何一个服务的彻底卡死，等同于整机操作系统的脑死亡**。

跨服务调用的隐式死锁是 `system_server` 最常见的系统性致命故障。当两个服务在不同线程上持有各自私有锁并发发起跨服务调用时，极易形成死锁环路：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                跨服务反向加锁引发的经典死锁循环 (AB-BA Deadlock)         |
   +-------------------------------------------------------------------------+

   [ 线程 1: 处理 App 启动事件 ]            [ 线程 2: 处理屏幕旋转事件 ]
   +-------------------------------+       +-------------------------------+
   | 运行在 ActivityManagerService |       | 运行在 WindowManagerService   |
   |                               |       |                               |
   | 1. 获取 AMS 全局实例锁:       |       | 1. 获取 WMS 全局锁:           |
   |    synchronized (mService)    |       |    synchronized (mGlobalLock) |
   |                               |       |                               |
   | 2. 跨模块调用 WMS 接口更新窗口|       | 2. 跨模块调用 AMS 接口通知布局|
   |    wms.setAppVisibility(...)  |       |    ams.updateConfiguration(...)
   |                               |       |                               |
   | 3. 阻塞等待获取 mGlobalLock ! |       | 3. 阻塞等待获取 mService 锁 ! |
   +-------------------------------+       +-------------------------------+
                   \                               /
                    \                             /
                     =====> [ 形成死锁闭环 ] <=====
                     双方线程永久挂起，阻塞传递至所有调用者！

为了杜绝此类隐式死锁，现代 AOSP 确立了严格的系统服务代码准则：
- **禁止持锁进行远程 IPC 调用**：在调用其他进程接口或可能耗时的跨模块方法前，必须提前释放本地锁；
- **固化全局锁继承顺序**：跨服务协同必须严格遵循从高层向底层的单向加锁顺序（如永远只允许 AMS 拿锁后调 WMS，禁止反向在持锁状态下调用 AMS）；
- **细粒度拆锁**：将原本庞大的全局单体对象锁拆解为状态局部锁，例如 Android 10+ 彻底将 `ActivityTaskManagerService` 与传统 `ActivityManagerService` 剥离并独立加锁。

Watchdog 60 秒心跳自检微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在系统发生不可逆死锁或关键线程被恶意阻塞时能够自动恢复，Android 设计了系统级看门狗守护线程——`com.android.server.Watchdog`。

Watchdog 独立运行在 `system_server` 进程内部的一个高优先级单例线程中，其检测逻辑包含两套并行的健康度探测通道：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Watchdog 双轨健康检测与心跳轮询                     |
   +-------------------------------------------------------------------------+

   [ Watchdog 单例检测线程 (每 30 秒周期性被调度执行) ]
        |
        +---> [ 检测通道 1: 关键线程消息循环探测 (Handler Checkers) ]
        |     向系统核心线程的消息队列投递标记性空 Runnable:
        |     - Main Thread (主 UI 线程)
        |     - UI Thread (系统交互线程)
        |     - IO Thread (磁盘文件写入线程)
        |     - Display Thread (显示刷新与合成线程)
        |     * 判定标准: 若某个线程的消息队列超过 60s 无法执行该任务，即判定卡死！
        |
        +---> [ 检测通道 2: 关键服务对象锁心跳探测 (Monitor Checkers) ]
              轮流尝试进入核心服务的同步代码块:
              - ams.monitor() { synchronized (ActivityManagerService.this) {} }
              - wms.monitor() { synchronized (WindowManagerService.this) {} }
              - pms.monitor() { synchronized (PackageManagerService.this) {} }
              * 判定标准: 若尝试获取某把锁的等待耗时累积超过 60s，即判定锁死锁！

双阶段超时熔断判定状态机：

1. **半程预警（30 秒未响应）**：Watchdog 发现某个 Checker 未能在前半周期完成心跳，不会立即采取破坏性措施，而是提前抓取当前异常线程的调用栈信息写入系统日志（Logcat），作为潜在卡顿分析的线索；
2. **全程判定（60 秒超时击穿）**：一旦超时时间达到 60 秒硬限制，Watchdog 确认当前控制面已经完全瘫痪且不可逆自愈，立即启动系统级熔断程序。

崩溃转储、自愈杀进程与系统级级联重启
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 Watchdog 判定 60 秒超时触发熔断后，其执行流程展示了移动操作系统在极端崩溃下的故障自愈与证据保留哲学：

.. code-block:: text

   [ 阶段 1: 冻结全场与抓取证据 (Evidence Preservation) ]
   1. Watchdog 向系统内所有核心进程发送 SIGQUIT (3) 信号:
      - system_server, Zygote, SurfaceFlinger, audioserver, 关键后台 App
   2. 各进程运行时响应信号，将全量 Java/Native 线程栈快照写入 /data/anr/traces.txt;
   3. 触发内核 sysrqDump 转储 CPU 寄存器与内核 D 状态挂起线程栈;
   4. 将 Watchdog 超时原因封装写入 DropBoxManager 数据库。
         |
         v
   [ 阶段 2: 实施自杀式熔断 (Suicide Eviction) ]
   Process.killProcess(Process.myPid()); // 强制杀死自身 system_server 进程！
         |
         v
   [ 阶段 3: 级联级自愈启动 (Cascade Recovery) ]
   1. system_server 退出触发内核向父进程发送 SIGCHLD 信号;
   2. 父进程 Zygote 检测到其最重要的子节点 system_server 异常夭折;
   3. 判定运行时环境已不可信，Zygote 立即调用 kill() 自行退出;
   4. PID 1 的 init 进程捕捉到 Zygote 死亡事件:
      - 重启 Zygote 进程;
      - 触发重新 forkSystemServer();
      - 重走三阶段装配流水线，拉起系统桌面。

这套熔断机制向用户呈现的外部表象是：手机屏幕瞬时黑屏或闪现 Boot Animation（开机动画），数秒后重新回到锁屏界面（俗称 **Soft Reboot / 软重启**）。系统通过牺牲瞬态内存会话，换取整机控制面脱离死锁死结并重新恢复可用。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了 Android 系统控制面中枢 `system_server` 与名字解析中枢 `ServiceManager` 的架构内幕：
- 解析了 `system_server` 由 Zygote 派生、执行权限降级以及按“引导服务 $	o$ 核心服务 $	o$ 其他服务”三阶段拓扑依赖启动的装配流水线；
- 剖析了 `ServiceManager` 依靠内核保留 Handle 0 确立名字寻址底座的机制，以及基于 SELinux `service_contexts` 实现的服务注册与查询强类型准入网关；
- 深入推导了 AMS/ATMS、PMS、WMS 与 PowerMS 的核心事实所有权模型，并阐明了 Java 控制面与 Native 实时数据面拆分的技术必然性；
- 解构了客户端 Framework Manager 与服务端 Binder Proxy 的桥接分层，以及利用 DeathRecipient 机制杜绝服务内存泄漏的实现规范；
- 揭示了单体服务进程的跨服务死锁风险，以及 Watchdog 依靠双轨 60 秒轮询探测、堆栈快照转储与全系统级联自愈重启的底层实现。

在本章中，我们多次提及跨进程调用必须穿越 `/dev/binder` 内核驱动。那么，Binder 是如何在操作系统内核中实现**仅需一次物理内存拷贝（`mmap`）**即可完成海量数据传输的？Binder 实体节点（`binder_node`）与远程引用（`binder_ref`）的生命周期又是如何跨越进程边界实现安全自动回收的？

在下一章——**Chapter 29: Binder IPC 驱动底层机制：单次内存拷贝 (mmap) 与引用计数** 中，我们将深入 Linux 内核源码 `binder.c` 的微观世界，逐行拆解跨进程虚拟内存映射与事务投递的物理本质。
