========================================================================
Chapter 31: 硬件能力仲裁与多租户并发访问控制：独占抢占、共享聚合、会话管理与死亡清理
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 30）中，我们深入 Android Binder 的中枢控制面，系统解构了 `BINDER_WRITE_READ` 双向状态机、线程池动态扩容（`BR_SPAWN_LOOPER`）、异步单向事务流控、基于 EAS 的优先级继承以及调用链嵌套重入死锁防御。Binder IPC 为操作系统构建了高吞吐、低延迟且防篡改的跨进程通信骨干。

   然而，通信管道仅仅解决了数据与控制指令的传递问题。现代智能手机面临着远比桌面端严苛的物理资源约束：电池电量预算极其受限、被动散热热包络极窄，且相机、麦克风、GNSS、各种运动传感器与显示合成器均涉及强隐私与实时并发冲突。当多个应用（例如前台短视频录制、后台音乐播放、地图导航、健身步数统计以及突发来电）同时争夺有限的硬件外设时，操作系统如何防止资源争用、状态污染与硬件过载？

   本章我们将深入移动操作系统的核心治理中枢，系统剖析系统服务如何扮演“物理硬件中介代理人”。我们将建立独占资源与共享资源的分类拓扑，剖析 CameraService 与 AudioService 的抢占状态机与焦点仲裁，解构 SensorService 与 LocationManagerService 的多租户请求合并与批处理（Batching），揭秘基于 `IBinder::linkToDeath` 的内核级死亡清理闭环，并推导服务崩溃与客户端异常时的系统一致性恢复机制。

------------------------------------------------------------------------
31.1 移动硬件能力的多租户治理全貌：独占资源 vs 共享资源分类模型
------------------------------------------------------------------------

多租户并发与物理硬件中介化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在经典桌面操作系统中，硬件外设（如扬声器、USB 设备）通常允许多个进程以相对宽松的并发模型访问，甚至允许普通进程直接打开特定字符设备节点。但在移动操作系统中，这种开放模型会导致严重的工程灾难：
1. **能耗与热失控**：多个应用并发唤醒 GPS 射频芯片或并发启动相机传感器，会导致整机静态功耗飙升至数瓦特，瞬间击穿电池续航并触发 Thermal 降频保护；
2. **状态竞争与硬件冲突**：CMOS 传感器与图像信号处理器（ISP）在物理层面上只能配置一套曝光、增益与对焦流水线，无法同时服务两组截然不同的拍摄参数；
3. **隐私越界与后台窃听**：若缺乏全局中介，后台恶意应用便可在用户无感知的情况下持续监听麦克风或捕获摄像头帧。

因此，移动操作系统确立了**硬件能力完全中介化（Complete Hardware Mediation）**法则：**用户空间应用被彻底剥离直接访问底层驱动节点（如 `/dev/video*`, `/dev/snd/*`）的权限；所有硬件能力均封装在系统服务中枢之后**。系统服务充当全局唯一的资源仲裁者与所有权事实源（Single Source of Truth）。

硬件资源分类：独占型 vs 共享型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据物理特性、驱动流水线设计以及用户感知模型，移动系统的硬件能力严格划分为两大阵营：

.. list-table:: 移动系统硬件资源分类与仲裁特征矩阵
   :widths: 14 16 22 22 26
   :header-rows: 1
   :class: tight-table

   * - 资源大类
     - 典型物理外设
     - 物理/驱动约束特征
     - 系统服务治理模型
     - 冲突处理裁决机制
   * - **独占型资源**
       (Exclusive)
     - 相机传感器 (CMOS/ISP)、麦克风录音链路、通话音频路由、硬件视频编码器
     - 硬件时钟、寄存器配置与数据流强绑定单一会话；切换上下文开销达数百毫秒；隐私敏感度极高。
     - **持有者模型 (Session Owner)**：单一时间窗口内仅允许唯一合法的 Client 掌握控制权。
     - **优先级抢占 (Preemption)**：高优先级任务强行剥离低优先级任务控制权，触发错误回调或静默断流。
   * - **共享型资源**
       (Shared)
     - 卫星定位 (GNSS)、运动传感器 (IMU)、网络射频 (Wi-Fi/Cellular)、显示合成器 (DPU/HWC)
     - 硬件可生成连续采样广播流，或具备多通道数据分发能力；单次驱动配置可满足多方需求。
     - **订阅者模型 (Multi-Subscriber)**：维护动态 Listener 注册表与请求参数集合。
     - **频次整形与合并 (Coalescing & Batching)**：提取最高采样率、最大容忍时延，利用硬件 FIFO 合并批处理。

仲裁核心状态表 (Arbitration State Table)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

系统服务内部维护的不是静态的配置，而是一张动态流转的**全局资源状态表**。该状态表由四个核心维度构成：

$$	ext{ResourceState} = \langle 	ext{ClientIdentity}, 	ext{ResourceDescriptor}, 	ext{PolicyContext}, 	ext{LeaseLifetime} \rangle$$

1. **ClientIdentity（调用者身份）**：包含调用方 UID、PID、PackageName 以及 AttributionTag（用于归因虚拟分身或前台服务）；
2. **ResourceDescriptor（资源描述符）**：具体的物理硬件 ID（如 Camera ID `0`、Audio Stream Type、Sensor Type）；
3. **PolicyContext（策略上下文）**：调用方当前所处的进程状态（Process State，由 ActivityManagerService 计算的 `oom_score_adj`）、权限快照（AppOps 状态）、前台可见性与屏幕亮灭状态；
4. **LeaseLifetime（租约生命周期）**：本次分配关联的会话凭证（Session Token）、回调接口（`IInterface` 代理）以及内核级死亡监听器（DeathRecipient）。

------------------------------------------------------------------------
31.2 独占型硬件能力仲裁：CameraService 抢占状态机与 Audio 焦点治理
------------------------------------------------------------------------

CameraService 架构与硬件独占冲突
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以移动平台最复杂的独占外设——相机子系统为例。物理 CMOS 传感器通过 MIPI CSI-2 差分接口连接至 SoC 内部的 ISP。ISP 硬件包含复杂的硬件统计引擎（3A 算法：AE/AF/AWB）与图像处理管线。

当 App 调用 `CameraManager.openCamera()` 时，调用请求通过 Binder 跨进程进入系统原生守护进程 `CameraService`。`CameraService` 在内存中为每一个物理相机维护一个 `CameraDeviceStatus` 与活跃客户端映射表 `mActiveClientMap`。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              CameraService 独占所有权与多租户抢占仲裁拓扑               |
   +-------------------------------------------------------------------------+

   [ 客户端 A (后台进程: oom_score_adj = 800) ]
        |
        | 1. openCamera("0") -> 成功获取 Owner 租约
        v
   +=========================================================================+
   | CameraService (Native 守护进程)                                         |
   |                                                                         |
   | 资源状态表: Camera "0" -> Owner: Client A (Cost: 100, Priority: Low)     |
   |                                                                         |
   | 2. 客户端 B (前台 Top-App: oom_score_adj = 0) 发起 openCamera("0")      |
   |    仲裁判定: Client B 优先级高于 Client A                               |
   +=========================================================================+
        |                                                 |
        | 3. 强制驱逐 Client A                            | 4. 移交硬件控制权
        v                                                 v
   [ 触发 Client A 的 onError 回调 ]             [ 配置 Client B 的硬件 Session ]
     状态码: ERROR_CAMERA_DISCONNECTED             打开 HAL3 /dev/video 节点
     释放底层 GraphicBuffer 队列                   重置 ISP 3A 流水线

抢占仲裁算法与状态机流转
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`CameraService` 的抢占裁决算法并非简单的“先来后到”，而是严格依赖 Android 框架层的进程可见性打分：

1. **优先级量化评级**：`CameraService` 通过内部接口向 `ActivityManagerService` 查询两个竞争客户端的当前综合优先级得分（基于进程状态 `PROCESS_STATE_TOP`、`PROCESS_STATE_FOREGROUND_SERVICE` 等）；
2. **同优先级拒绝**：若新申请者的优先级低于或等于当前活跃 Owner，`CameraService` 直接抛出 `CameraAccessException(CAMERA_IN_USE)`，拒绝新客户端的接入；
3. **高优先级抢占驱逐 (Eviction)**：若新申请者具备更高的可见性优先级（例如前台短视频 App 打开相机，而后台某个防盗监控服务正持有相机）：
   - **步骤 A：标记解绑**：`CameraService` 立即将旧客户端的 `CameraClient` 标记为 `DISCONNECTED` 状态，阻断其后续所有 `CaptureRequest` 的提交；
   - **步骤 B：异步断流通知**：通过旧客户端在连接时注册的 `ICameraDeviceCallbacks` 接口，向其发送 `onError(ERROR_CAMERA_DISCONNECTED)`；
   - **步骤 C：硬件资源归还**：`CameraService` 等待底层 Camera HAL 完成当前在途图元帧处理，随后调用 HAL 接口 `close()` 注销物理设备，断开所有绑定的 `Surface` 缓冲队列；
   - **步骤 D：重新绑定新 Owner**：底层硬件释放后，为新申请者重新调用 HAL `open()`，建立全新的 `CameraCaptureSession`。

音频焦点 (Audio Focus) 软仲裁与硬件路由切换
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

与相机在驱动层强制断开不同，音频播放属于典型的“物理共享（同一 DAC/功放可混音输出），但语义独占（用户无法同时听清音乐与导航播报）”的混合系统。

Android 的 `AudioService` 通过**音频焦点机制（Audio Focus）**协调并发播放冲突：

.. code-block:: java

   // 应用发起音频焦点申请
   AudioAttributes playbackAttributes = new AudioAttributes.Builder()
       .setUsage(AudioAttributes.USAGE_MEDIA)
       .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
       .build();

   AudioFocusRequest focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
       .setAudioAttributes(playbackAttributes)
       .setAcceptsDelayedFocusGain(true)
       .setOnAudioFocusChangeListener(focusChangeListener)
       .build();

   int result = audioManager.requestAudioFocus(focusRequest);

`AudioService` 内部维护一个 `Stack<FocusRequester> mFocusStack`。当新的焦点请求到达时，仲裁引擎执行如下状态迁移：

- **AUDIOFOCUS_GAIN（完全独占）**：用于长期媒体播放。此前持有焦点的所有客户端收到 `AUDIOFOCUS_LOSS` 回调，应当停止播放并释放音频解码资源；
- **AUDIOFOCUS_GAIN_TRANSIENT（瞬态独占）**：用于短促事件（如系统通知音）。原持有者收到 `AUDIOFOCUS_LOSS_TRANSIENT`，应当暂停播放，等待瞬态事件结束后恢复；
- **AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK（瞬态闪避）**：用于导航语音播报。原持有者收到 `AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK`。此时底层 `AudioFlinger` 或上层播放器会自动将背景音乐音量衰减至原始幅值的 20%（Duck 状态），待播报完毕后平滑淡出恢复。

在较新的移动平台（Android 12+）中，系统彻底抛弃了纯依赖应用“自律”处理焦点回调的设计，引入了**系统级强制淡出（System-Enforced Fading）**：若应用在收到焦点丢失信号后未在指定时间窗口内降低音量，`AudioFlinger` 混音引擎会直接在内核驱动上游对该音频轨应用数字衰减曲线，强制压制音频输出。

------------------------------------------------------------------------
31.3 共享型硬件能力聚合与频次整形：SensorService 与 LocationManagerService
------------------------------------------------------------------------

共享型外设面临的核心矛盾是：**每个租户的采样周期与延迟容忍度差异巨大，若分别独立驱动硬件，将引发严重的功耗雪崩**。

SensorService 的 Producer-Multi-Listener 拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以智能手机加速度计与陀螺仪为例。前台 3D 游戏要求以 $100	ext{ Hz}$（采样间隔 $10	ext{ ms}$）极低延迟刷新手势控制；后台计步健身应用仅需以 $1	ext{ Hz}$ 采样，且允许长达 $60	ext{ s}$ 的数据交付延迟。

若为每个应用启动独立的内核读取线程，CPU 必须持续在微秒级区间内响应硬件中断，完全无法进入深度休眠（C-States）。

`SensorService` 建立了**合并降频与硬件 FIFO 批处理模型（Sensor Coalescing & Batching）**：

.. code-block:: text

   [ Client A (前台游戏: Period = 10ms, Latency = 0ms) ]
   [ Client B (后台计步: Period = 1000ms, Latency = 60000ms) ]
                  |                      |
                  +----------+-----------+
                             v
   +=========================================================================+
   | SensorService 仲裁中枢                                                  |
   |                                                                         |
   | 1. 计算物理采样率: min(10ms, 1000ms) = 10ms (100 Hz)                   |
   | 2. 计算最大批处理延迟: min(0ms, 60000ms) = 0ms (实时直通)              |
   |                                                                         |
   | 动态重构下发至 Sensor HAL 的参数:                                      |
   |   ioctl(fd, BATCH, sampling_period = 10ms, max_report_latency = 0ms)    |
   +=========================================================================+
                             |
                             v
   +=========================================================================+
   | 独立低功耗 Sensor Hub 协处理器 (Cortex-M) / 硬件 FIFO 缓冲区             |
   +=========================================================================+

Sensor HAL 批处理参数合并算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于同一个物理传感器，若存在 $N$ 个活跃订阅者，每个客户端 $i$ 请求的参数为：
- 采样周期：$T_i$（`sampling_period_ns`）
- 最大报告延迟：$L_i$（`max_report_latency_ns`）

`SensorService` 向底层驱动下发的最终硬件配置，遵循严格的极值收敛准则：

$$T_{	ext{hw}} = \min_{1 \le i \le N} \{ T_i \}$$
$$L_{	ext{hw}} = \min_{1 \le i \le N} \{ L_i \}$$

当高频客户端 A 存在时，硬件被迫以最高频率 $T_{	ext{hw}} = 10	ext{ ms}$、零延迟 $L_{	ext{hw}} = 0	ext{ ms}$ 运转；当客户端 A 注销其监听器后，`SensorService` 立即触发重算状态机，将硬件配置平滑切换为 $T_{	ext{hw}} = 1000	ext{ ms}$、$L_{	ext{hw}} = 60000	ext{ ms}$。此时主 CPU 完全进入 Suspend 深度休眠，数据完全积聚在外部独立 Sensor Hub 协处理器的硬件 FIFO 中，每隔 60 秒通过单次唤醒中断批量刷新，实现整机功耗下降 90% 以上。

LocationManagerService 的后台限速与缓存复用
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

定位服务（GNSS/GPS 与 Network Location Provider）的仲裁进一步融入了**基于生命周期状态的频次整形（Throttling）**。

在 `LocationManagerService` 中：
1. **统一 Provider 抽象**：将物理卫星硬件（GPS/GLONASS/BDS）、基站小区定位（Cell ID）与 Wi-Fi 扫描热点抽象为统一定位源；
2. **缓存位置直出**：客户端请求定位时，优先评估系统中最新缓存的定位结果（Last Known Location）与精度时间戳。若其生存时间（TTL）未过期，直接以零能耗返回缓存数据；
3. **后台频次硬性扼杀 (Background Location Throttling)**：
   Android 8.0（API level 26）后，非前台运行、未绑定前台服务且未处于豁免白名单的应用，无论其在 API 中声明的刷新间隔多短（如 $1	ext{ s}$），`LocationManagerService` 都会在服务中介层对其强行截断，限制为每小时仅交付数次低频位置更新，从架构层面彻底杜绝后台应用滥用 GNSS 导致的“电池发热枯竭”。

------------------------------------------------------------------------
31.4 会话抽象、Token 授权与客户端追踪 (Session, Token & Client Tracking)
------------------------------------------------------------------------

Session、Token 与 Handle 的微架构分工
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在无状态的跨进程 RPC 通道上维护长生命周期的硬件交互，系统服务层设计了精密的上下文标识体系：

- **Session（会话）**：表示一段跨越多次调用的连续硬件工作流水线，包含驱动层分配的物理缓冲区、流水线参数与内部状态机（如 `CameraCaptureSession`）；
- **Token（令牌）**：由服务端或客户端生成的 `IBinder` 物理实体（如 `Binder token = new Binder()`）。由于 Binder 实体在内核驱动中映射为不可伪造的 `binder_node` 内存指针，Token 充当了防篡改的**权限与归属权证明（Capability Token）**；
- **Handle（句柄）**：客户端持有用于发起操作的代理引用（如指向特定 Window 的 `AppWindowToken` 或文件描述符）。

RemoteCallbackList 微架构剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在服务端维护海量跨进程客户端监听器时，传统的 Java `ArrayList<IListener>` 会引发严重的并发死锁与内存泄漏：若某个客户端进程在注册后直接崩溃，服务端在遍历列表分发回调时将陷入 `DeadObjectException`，且无效的 `IBinder` 强引用会导致客户端进程在内核中无法被完全回收。

Android 框架层设计了工业级的核心并发容器——`RemoteCallbackList<E extends IInterface>`：

.. code-block:: java

   // frameworks/base/core/java/android/os/RemoteCallbackList.java
   public class RemoteCallbackList<E extends IInterface> {
       // 以底层 IBinder 为 Key 建立映射，避免重写 equals 带来的隐患
       ArrayMap<IBinder, Callback> mCallbacks = new ArrayMap<IBinder, Callback>();
       private Object[] mActiveBroadcast;
       private int mBroadcastCount = -1;
       private boolean mKilled = false;

       private final class Callback implements IBinder.DeathRecipient {
           final IBinder mBinder;
           final E mCallback;
           final Object mCookie;

           Callback(E callback, Object cookie) {
               mCallback = callback;
               mCookie = cookie;
               mBinder = callback.asBinder();
           }

           public void binderDied() {
               synchronized (mCallbacks) {
                   mCallbacks.remove(mBinder);
               }
               onCallbackDied(mCallback, mCookie);
           }
       }
       // ...
   }

`RemoteCallbackList` 的微架构精髓在于：
1. **生命线自动挂钩**：在调用 `register(E callback, Object cookie)` 时，自动提取底层 `IBinder`，创建内部 `Callback` 节点并就地执行 `mBinder.linkToDeath(this, 0)`。客户端一旦死亡，容器内部自动完成节点剔除并触发虚函数 `onCallbackDied`；
2. **快照广播隔离 (Snapshot Broadcasting)**：在通过 `beginBroadcast()` 遍历分发事件时，该容器将当前所有活动的回调指针浅拷贝至一维数组 `mActiveBroadcast` 中并释放内部互斥锁。系统服务在向各个客户端发起跨进程调用时处于**无锁状态**，彻底规避了因远端客户端阻塞导致的系统服务全局死锁；
3. **冻结进程策略 (Frozen Callee Policy)**：在现代 Android（API 36+）中，`RemoteCallbackList` 与内核 cgroup 进程冷冻器（Freezer）深度联动：当感知到目标客户端处于冻结状态时，可配置直接丢弃瞬态事件或仅排队保留最新快照，防止唤醒沉睡进程。

------------------------------------------------------------------------
31.5 死亡通知驱动的资源全链路闭环清理 (DeathRecipient & Cleanup Path)
------------------------------------------------------------------------

客户端非正常消亡与内核感知
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

移动应用运行在充满不确定性的沙箱环境中：应用进程可能因未捕获异常抛出 `SIGSEGV` 崩溃、可能因低内存被系统的 `lowmemorykiller`（LMKD）使用 `SIGKILL` 瞬间抹杀、也可能被用户在多任务卡片中强行划除（Force Stop）。

在上述所有场景中，应用完全来不及执行 Java 层的 `close()`、`release()` 或 `unregisterListener()`。如果操作系统服务不能自动感知客户端的消亡，硬件外设将被已被杀死的进程永久幽灵占用，导致后续任何应用都无法再次打开相机或录音，整机进入不可用状态。

Linux 内核 Binder 驱动的 DeathRecipient 机制构成了全系统的终极安全底座：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |          Binder 内核驱动感知进程消亡与 DeathRecipient 触发全链路         |
   +-------------------------------------------------------------------------+

   [ 客户端进程 (PID: 4396) 发生崩溃或被 LMKD 发送 SIGKILL ]
                                |
                                v
   [ Linux 内核执行 do_exit() 退出逻辑 ]
                                |
                                v 释放文件描述符表
   [ 调用 drivers/android/binder.c: binder_deferred_release() ]
                                |
                                v 遍历当前 proc 拥有的全部 binder_ref 引用
   +=========================================================================+
   | Linux 内核态检测:                                                       |
   | 发现该客户端 Binder 实体存在远端 death_recipient 监听!                 |
   |                                                                         |
   | 1. 构建 binder_work 结构体 (type = BINDER_WORK_DEAD_BINDER);           |
   | 2. 将工作项压入对应系统服务工作线程 (SystemServer/CameraService) todo 队列;|
   | 3. 唤醒系统服务休眠中的 Binder 线程池!                                  |
   +=========================================================================+
                                |
                                v
   [ 系统服务线程从 ioctl 读到 BR_DEAD_BINDER 返回码 ]
                                |
                                v
   [ IPCThreadState 反序列化通知, 执行注册的 deathRecipient->binderDied() ]

全链路幂等清理四步法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

系统服务收到 `binderDied()` 通知后，必须以严格的原子性与幂等性执行四步闭环收束，彻底还原物理硬件状态：

.. list-table:: 典型硬件能力在客户端消亡时的内核与服务清理闭环对比
   :widths: 15 22 28 35
   :header-rows: 1
   :class: tight-table

   * - 硬件能力
     - 服务端追踪实体
     - 死亡感知触发点
     - 全链路闭环收束动作
   * - **相机 (Camera)**
     - `CameraClient` 与 `CameraDeviceClient`
     - `CameraService::DeathRecipient::binderDied()`
     - 1. 将 Client 状态置为 `DISCONNECTED`；2. 强制终止底层 Camera HAL 的当前 CaptureRequest 流水线；3. 释放关联的 GraphicBuffer 队列句柄；4. 重置 ISP 供电域；5. 熄灭隐私指示灯（Green Dot）。
   * - **音频焦点与录音**
     - `FocusRequester` 与 `RecordClient`
     - `AudioService::DeathRecipient` / `AudioFlinger`
     - 1. 将该 Token 从 `mFocusStack` 移除；2. 调用 `AudioFlinger` 销毁音频输入 RecordTrack 并关闭 ADC；3. 重新计算剩余音频焦点，向被 Duck 或暂停的原活跃 App 发送 `AUDIOFOCUS_GAIN` 恢复播放。
   * - **传感器 (Sensor)**
     - `SensorEventConnection`
     - `SensorService::SensorEventConnection::binderDied()`
     - 1. 从 Sensor 活跃连接表移除该 Connection；2. 重新遍历剩余活跃订阅者，重新计算各传感器的最低采样周期与批处理延迟；3. 立即调用 Sensor HAL 重新下发 `batch` 与 `activate` 命令降频降电。
   * - **窗口与显示**
     - `WindowState` 与 `SurfaceControl`
     - `WindowManagerService::Session::binderDied()`
     - 1. WMS 销毁客户端的 Window Token；2. 触发 SurfaceFlinger 将该图层标记为销毁，释放由客户端持有的硬件图层（Overlay Plane）；3. 触发系统重新计算焦点窗口并向新前台派发按键与触控事件。

------------------------------------------------------------------------
31.6 超时保护、服务崩溃恢复与系统一致性重构
------------------------------------------------------------------------

跨进程调用超时与看门狗防御 (Timeout Watchdog)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

服务中介模型不仅要防范客户端死亡，还要防范客户端**活锁与恶意挂起**。

在双向交互模型中（如系统服务向客户端广播一个同步事件），若客户端的接收线程处于死锁或断点调试暂停状态，发起同步调用的系统服务工作线程将被永久挂起。若多次发生此类挂起，系统服务（如 `system_server`）的 16 个 Binder 工作线程将被全数耗尽，导致整机发生灾难性的全局 ANR 假死。

为了防御此类隐患，移动系统服务在向客户端回调时普遍采用以下隔离策略：
1. **全面推行单向异步传输（Oneway Calls）**：系统服务派发事件通知时，一律使用 `oneway void onStatusChanged(...)` 声明。系统服务将消息塞入驱动队列后立刻返回，绝不等待客户端任何应答；
2. **带超时的异步轮询 (Handler Timeout)**：对于必须等待客户端应答的关键状态（如广播接收器 `BroadcastReceiver` 的执行完毕通知 `finishReceiver()`），服务内部启动一个独立的高精度定时器（如前台 10 秒、后台 60 秒超时）。一旦超时触发，服务立即将该客户端标记为故障，强制剥离资源并向系统报告 ANR 崩溃，确保服务控制面永远不被不可信客户端拖垮。

系统服务进程崩溃（Service Crash）与客户端自愈模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

除应用崩溃外，系统底层的原生守护进程（如 `cameraserver`, `audioserver`, `surfaceflinger`）因底层硬件驱动异常或固件空指针也存在崩溃风险。当服务进程崩溃时，运行态中所有内存状态与 Binder 节点全部灰飞烟灭。

现代操作系统为此建立了**反向故障隔离与状态重建协议**：

1. **守护进程看门狗重启**：原生服务通过 Linux `init` 进程守护（配置在 `init.rc` 中为 `service cameraserver /system/bin/cameraserver ... onrestart restart ...`）。一旦进程终止，`init` 负责在毫秒级时间内重新孵化新进程，并向 `ServiceManager` 重新注册 Binder 句柄；
2. **客户端反向感知死亡**：应用端持有的远端服务代理在服务崩溃的瞬间，底层 Binder 引用失效。此时应用发起的任何 IPC 操作均会抛出 `DeadObjectException`；同时应用在初始化阶段向服务代理注册的 `DeathRecipient` 会被触发；
3. **分层状态重构 (State Reconstruction)**：
   - 应用端 SDK（如 `CameraManager`）感知到 `cameraserver` 死亡后，触发内部 `CameraDevice.StateCallback.onError(CAMERA_SERVER_DIED)`；
   - 客户端框架自动解绑不可用的本地失效句柄，并启动退避重连机制（Backoff Re-binding），重新向 `ServiceManager` 请求新的服务代理；
   - 新服务进程启动后，从底层重新探测硬件节点，并将系统全局状态重置至干净的初始基线，防止陈旧的脏状态污染新会话。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入移动操作系统服务治理中枢，系统解构了多租户硬件能力仲裁与并发控制体系：
- 建立了独占型资源（持有者模型）与共享型资源（订阅者模型）的物理分类特征与仲裁模型；
- 剖析了 `CameraService` 基于进程优先级打分的抢占驱逐状态机，以及 `AudioService` 音频焦点的强弱仲裁与系统强制淡出控制；
- 解密了 `SensorService` 基于极值准则的多租户采样周期与批处理延迟合并算法，以及 `LocationManagerService` 的后台限速与缓存复用机制；
- 剖析了 `RemoteCallbackList` 的微架构实现，揭示其如何通过快照遍历规避死锁，并通过 `IBinder` 令牌构建不可伪造的会话上下文；
- 深入推导了 Linux 内核 Binder 驱动在客户端进程消亡时派发 `BR_DEAD_BINDER` 的全链路，以及服务层针对相机、音频、传感器和窗口的幂等清理四部曲；
- 阐释了超时看门狗防御与服务进程崩溃后的反向自愈重连机制。

在攻克了系统服务中介与硬件仲裁治理之后，我们需要将视野进一步拓展至跨平台的另一核心阵营。在下一章——**Chapter 32: Apple 服务治理中枢：launchd 守护进程网格与 XPC 异步通信机制** 中，我们将深入 Darwin/XNU 的世界，系统解构 Apple 平台由 `launchd` 按需激活的系统守护进程网格、Mach Port 底层权标以及现代化 XPC 的双向异步类型安全通信体系。
