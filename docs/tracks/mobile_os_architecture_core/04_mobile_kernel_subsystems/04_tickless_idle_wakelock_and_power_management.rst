========================================================================
Chapter 21: Tickless Idle、WakeLock 与系统休眠唤醒状态机
========================================================================

.. note:: 前置背景与认知承接
   在前一章中，我们解构了移动硬件中断拓扑（ARM GIC）、上半部执行禁区、Threaded IRQ 实时调度以及 DMA/SMMU 零拷贝总线直通体系。然而，智能手机与桌面 PC 最显著的物理分界在于**严苛的电池能量预算（Battery Energy Budget）**。一台配备 4500mAh（约 17.1Wh）锂电池的手机，必须在全天候网络连接与传感器监听的前提下实现超过 24 小时的续航。这意味着系统在熄屏待机时的整机平均电流必须被死死压制在 **10mA 以内（静态待机功耗 < 40mW）**。为了达成这一物理极限，移动内核建立了一套极其精密的分层电源管理架构：从 CPU 毫秒级微观空闲的 **Tickless Idle (NO_HZ)** 与 **C-State 能级跃迁**，到设备级的 **Runtime PM**，再到整机宏观冻结的 **System Suspend**、**WakeLock / Wakeup Source** 仲裁与硬件唤醒状态机。本章将深入内核源码与硬件底层，全面剖析移动操作系统的低功耗运转与休眠唤醒全景机制。

------------------------------------------------------------------------
21.1 移动内核时间基准与 Tickless Idle (NO_HZ) 机制
------------------------------------------------------------------------

在传统的通用操作系统中，内核依赖周期性时钟中断（Periodic Timer Tick，通常为 100Hz、250Hz 或 1000Hz）驱动进程调度时间片轮转、更新系统时间以及触发软件定时器。对于移动设备而言，固定频率的时钟中断是一场**功耗灾难**：即使系统中所有应用程序均处于空闲阻塞状态，硬件定时器依然会每隔 1 毫秒（1000Hz）向 CPU 发送一次中断信号，强制将 CPU 从低功耗休眠状态唤醒并执行中断处理例程，导致 CPU 核心根本无法沉入深层节能能级。

为了消除这种无意义的周期性能耗浪费，现代移动内核全面启用了 **Tickless Idle（动态时钟中断，内核配置宏 `CONFIG_NO_HZ_IDLE` 与 `CONFIG_NO_HZ_FULL`）** 机制。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            传统周期性 Tick vs 移动内核 Tickless Idle (NO_HZ) 对比       |
   +-------------------------------------------------------------------------+

   [ 1. 传统周期性时钟 (Periodic Tick: 1000Hz) ]
   CPU 状态: | 活跃 | 休眠 | 活跃 | 休眠 | 活跃 | 休眠 | 活跃 | 休眠 | ...
   时钟中断:    ^      ^      ^      ^      ^      ^      ^      ^
                | 1ms  | 1ms  | 1ms  | 1ms  | 1ms  | 1ms  | 1ms  |
   物理后果: CPU 被强制每毫秒唤醒一次，无法进入高延迟、高节电的深层 C-State!

   [ 2. 移动内核动态时钟 (Tickless Idle / NO_HZ) ]
   任务队列: [ 无就绪进程 ] -------------------> [ 下一个定时器: 850ms 后到期 ]
   CPU 状态: | 活跃 |              深度休眠 (Deep Sleep / 850ms)           | 唤醒 |
   时钟中断:    ^                                                           ^
                | 关停周期 Tick，动态编程硬件定时器为 850ms                 |
   物理后果: CPU 持续处于断电/时钟门控状态，静态功耗由 150mW 骤降至 < 2mW!

Tickless Idle 动态评估与停跳决策算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当某个 CPU 核心运行队列（Runqueue）中的最后一个就绪进程进入睡眠或阻塞状态时，调度器会选择运行特殊的 `idle` 线程（PID 0，即 `swapper` 进程）。在执行空闲循环之前，内核 `tick_nohz_idle_enter()` 函数启动动态评估：

1. **检查 CPU 就绪队列**：确认当前 CPU 上的 `rq->nr_running == 0`，确保不存在等待调度的就绪任务；
2. **扫描高精度定时器红黑树（hrtimer rbtree）**：检索当前 CPU 本地定时器基准中最早到期的定时器事件（Next Expiry Event），计算出距离当前时间的最长可休眠时间差 $\Delta T_{	ext{sleep}}$；
3. **停跳（Stop Tick）并动态重设硬件比较器**：
   - 停止内核周期性 `sched_tick` 中断；
   - 将计算得到的下一次超时绝对时间戳直接写入 ARM64 核心本地通用定时器的物理寄存器 **`CNTV_CVAL_EL0`（Virtual Timer CompareValue Register）** 或 **`CNTV_TVAL_EL0`（TimerValue Register）**；
4. **移交控制权至 CPUIdle 子系统**：通知 CPUIdle 框架，当前核心可以安全休眠 $\Delta T_{	ext{sleep}}$ 毫秒，且在此期间不会有任何周期性中断强行打扰。

------------------------------------------------------------------------
21.2 CPUIdle 子系统与 C-State 能级跃迁状态机
------------------------------------------------------------------------

当 CPU 确定进入空闲状态后，究竟应该以何种方式“休眠”？在现代移动 SoC（如高通 Oryon/Kryo、联发科 Cortex-X4/A720/A520）中，硬件为 CPU 核心提供了多个阶梯式的低功耗状态，在体系结构中被称为 **C-State（Idle States: C0 ~ Cn）**。

.. list-table:: 移动 SoC CPU C-State 能级特性与开销矩阵
   :widths: 10 15 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 能级
     - 状态名称
     - 硬件电路操作与断电范围
     - 唤醒延迟 (Exit Latency)
     - 典型节能效果 (Power Savings)
   * - **C0**
     - Active Running
     - 满负荷工作，时钟使能，全电压供电
     - 0 $\mu	ext{s}$ (当前状态)
     - 0% (基准功耗: 200mW ~ 2500mW)
   * - **C1**
     - Clock Gating (WFI)
     - 仅切断核心内部执行单元时钟，保持电压与 L1 缓存
     - 1 ~ 2 $\mu	ext{s}$
     - 节约 ~30% 动态功耗
   * - **C2**
     - Retention / Low-V
     - 核心逻辑降压至维持电压，关闭时钟树，保留寄存器
     - 20 ~ 50 $\mu	ext{s}$
     - 节约 ~70% 功耗
   * - **C3**
     - Core Power Collapse
     - 核心逻辑**彻底断电**，L1/L2 缓存刷入 L3，寄存器状态下推至 DRAM
     - 200 ~ 500 $\mu	ext{s}$
     - 节约 > 95% 功耗 (接近 0mW 静态漏电)
   * - **C4**
     - Cluster Power Down
     - 整个 CPU 丛集（Cluster）断电，关闭共享 L3 缓存与 Snoop Filter
     - 1000 ~ 3000 $\mu	ext{s}$
     - 丛集完全下电

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                CPUIdle 能级跃迁的“收支平衡点” (Break-even Time)         |
   +-------------------------------------------------------------------------+

   功耗 (Power)
      ^
      |    +------------------------+ (C0 运行态基准功耗: P_run)
      |    |
      |----+........................+ (进入深层 C3 状态的硬件瞬时能耗脉冲)
      |    | \ 状态保存与缓存刷写能耗
      |    |  \
      |    |   +--------------------+ (C3 深度休眠静态功耗: P_c3 接近 0)
      |    |   |                    |
      |    |   |   净收益节能区域   | / 唤醒上电与现场恢复能耗
      |    |   |                    |/
      +----+---+--------------------+------------------------> 时间 (Time)
           0   t_enter              t_exit
               |<---- Target Residency (目标驻留时间) ---->|

CPUIdle 决策模型：Menu Governor 与 TEO Governor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

深层 C-State（如 C3 核心断电）虽然功耗极低，但存在极大的**进入开销（Entry Latency & Energy）**与**退出开销（Exit Latency & Energy）**。如果一个核心仅空闲了 50 微秒，却被送入需要 300 微秒唤醒的 C3 状态，不仅不会省电，反而会因为频繁刷写缓存和核心复位而导致电量倒贴，并引发系统严重卡顿。

为了精准决策，Linux 内核开发了专门的 CPUIdle 调速器：
1. **Menu Governor**：
   - 传统复杂调速器，综合分析历史平均空闲时间（Rolling Average）、系统负载（I/O 等待比例）以及 CPUFreq 频点，利用启发式算法预测当前休眠时长；
2. **TEO Governor (Timer Events Oriented)**：
   - 专门针对现代移动设备与高频动态负载设计；
   - 以高精度定时器（hrtimer）的确定性到期时间为硬基准，直接统计历史“短时早醒（Non-timer Wakeups）”事件的概率分布；
   - 判定准则：只有当预测的空闲时长严格大于目标 C-State 的 **`Target Residency`（目标驻留时间）**，且允许的最大唤醒延迟满足实时性约束时，调速器才会批准 CPU 跃迁至该深层 C-State。

PSCI 固件交互与 ARM Trusted Firmware (ATF)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ARM64 移动架构中，内核（EL1 特权级）并不直接操作 PMU 硬件寄存器切断 CPU 核心供电，而是遵循 ARM 官方规范 **PSCI（Power State Coordination Interface）**：
- Linux CPUIdle 驱动填充 PSCI 状态参数，执行 `smc`（Secure Monitor Call）或 `hvc` 指令，触发异常陷入安全世界 **EL3（ARM Trusted Firmware / ATF）**；
- ATF 固件执行底层硬件特定序列：保存 CPU 核心通用寄存器与系统控制寄存器、冲刷 L1/L2 缓存、通知芯片级供电管理单元（PMIC）切断当前核心的供电轨（Power Rail），最终执行 `WFI` 指令等待硬件中断唤醒。

------------------------------------------------------------------------
21.3 Android WakeLock 演进与内核 Wakeup Source 机制
------------------------------------------------------------------------

在移动操作系统的休眠哲学中，存在一条核心铁律：**当屏幕关闭且无前台交互时，系统应尽可能进入整机挂起（System Suspend）状态；但若后台存在关键业务（如通话中、音乐播放、正在写入闪存的 OTA 升级），系统必须阻止整机进入深度睡眠。**

这一机制在 Android 诞生之初催生了著名的 **WakeLock（唤醒锁）** 机制。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Android WakeLock 到内核 Wakeup Source 的架构演进         |
   +-------------------------------------------------------------------------+

   [ 早期 Android 方案 (Out-of-tree / sysfs 接口) ]
   应用/服务 ---> 向 /sys/power/wake_lock 写入锁字符串 ---> 内核阻止全局 suspend
   缺陷: 缺乏内核级锁引用计数与垃圾回收，用户态崩溃极易导致永久持锁、电量耗尽!

   [ 现代 Linux 主线与 Android 融合方案 (Wakeup Sources 机制) ]
   +-------------------------------------------------------------------------+
   | 用户空间 (Android Framework / Apps)                                     |
   |   * 应用层: PowerManager.newWakeLock(PARTIAL_WAKE_LOCK, "MyAudioLock")  |
   |   * 服务层: PowerManagerService (PMS) 集中鉴权、记账与超时管理          |
   |   * 守护进程: system_suspend (C++ native daemon, /vendor/bin/hw/...)     |
   +-------------------------------------------------------------------------+
        |
        | (通过 AIDL /dev/wakeup_sources / IPC 交互)
        v
   +-------------------------------------------------------------------------+
   | 内核空间 (Linux Kernel: drivers/base/power/wakeup.c)                    |
   |   * 核心数据结构: struct wakeup_source                                  |
   |   * 加锁 API: __pm_stay_awake(ws)    --> 活跃持锁计数 active_count++    |
   |   * 解锁 API: __pm_relax(ws)         --> 活跃持锁计数 active_count--    |
   |   * 全局状态仲裁: wakeup_sources_stats / pm_stay_awake 阻塞挂起线程     |
   +-------------------------------------------------------------------------+

内核 `struct wakeup_source` 核心结构体剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Linux 内核通过统一的 `wakeup_source` 对象管理所有的软件唤醒阻止请求与硬件唤醒事件：

.. code-block:: c

   struct wakeup_source {
       const char      *name;              /* 唤醒源名称 (如 "PowerManagerService.WakeLocks") */
       struct list_head entry;             /* 全局唤醒源链表节点 */
       spinlock_t      lock;               /* 保护内部状态的自旋锁 */
       struct timer_list timer;            /* 超时自动解锁定时器 (Auto-relax timer) */
       unsigned long   timer_expires;      /* 定时器超时时间戳 */
       ktime_t         total_time;         /* 该唤醒源历史累计持锁总时长 (功耗分析依据) */
       ktime_t         max_time;           /* 单次最长持锁时间 */
       ktime_t         last_time;          /* 最近一次加锁时间戳 */
       unsigned long   event_count;        /* 唤醒事件触发总次数 */
       unsigned long   active_count;       /* 当前正在持锁的实体引用计数 */
       bool            active:1;           /* 当前唤醒源是否处于持锁激活状态 */
       bool            autosleep_enabled:1;/* 是否支持系统自动休眠 */
   };

当驱动或系统服务调用 `__pm_stay_awake(ws)` 时：
1. 内核将全局原子计数器 `combined_event_count` 中的高 16 位（处于 active 状态的唤醒源数量）原子加 1；
2. 系统挂起引擎在检查时，若发现 `combined_event_count` 中的活跃计数大于 0，将立即**中止挂起流程（Abort Suspend）**，确保关键任务不被打断。

------------------------------------------------------------------------
21.4 System Suspend 全系统挂起与休眠唤醒状态机
------------------------------------------------------------------------

当系统满足以下条件时：
1. 屏幕已关闭且处于非交互状态；
2. 系统内所有的 WakeLock / `wakeup_source` 均已完全释放（Active Count == 0）；
3. 后台没有正在运行的前台服务（Foreground Services）阻止休眠；

Android 系统休眠守护进程（`system_suspend`）将向内核节点 `/sys/power/state` 写入 `"mem"`，正式触发 **System Suspend（整机深度挂起）** 流程。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 移动操作系统 System Suspend 完整执行状态机              |
   +-------------------------------------------------------------------------+

   [ 触发休眠: 写入 /sys/power/state = "mem" ]
        |
        v
   [ 阶段 1: 冻结用户空间任务 (Freeze Tasks / PM_SUSPEND_PREPARE) ]
        | * 向所有非内核线程发送假信号 (fake_signal)，强制任务在调度边界进入 TASK_STOPPED
        | * 挂起所有 user space 进程，确保设备驱动休眠期间无任何用户态 I/O 并发
        v
   [ 阶段 2: 设备逐级挂起 (Device Suspend Pipeline) ]
        | * dpm_suspend(): 遍历设备树驱动链表，调用 dev->bus->pm->suspend()
        | * dpm_suspend_late(): 切断显示控制器 (DPU)、GPU、相机 ISP 供电
        | * dpm_suspend_noirq(): 关闭所有设备的中断处理例程 (HardIRQ Disabled)
        v
   [ 阶段 3: 停用非引导 CPU 核心 (Disable Non-Boot CPUs / CPU Hotplug) ]
        | * 将 Secondary Cores (Core 1 ~ Core 7) 上的任务全部迁移至 Core 0
        | * 调用 PSCI CPU_OFF 将从核心逐个完全断电 (Power Down)
        v
   [ 阶段 4: 中断控制器屏蔽与唤醒源使能 (GIC Wakeup Config) ]
        | * GIC 屏蔽所有常规外设中断，仅保留标记为 IRQF_NO_SUSPEND 的中断线
        | * 使能电源键 (PowerKey)、RTC 闹钟、Modem 寻呼、Touch 双击唤醒 GPIO
        v
   [ 阶段 5: 主核心进入系统级断电休眠 (System Power Collapse) ]
        | * Core 0 执行 syscore_suspend() 保存底层时钟与 GIC 寄存器上下文
        | * 调用 PSCI SYSTEM_SUSPEND 进入 ATF 固件
        | * PMIC 切断 SoC 主供电轨，仅保留 AON (Always-On) 供电域与 LPDDR 自身刷新
        |
   ~~~~~~~~~~~~~~~~~~~~~~~~ [ 整机深睡状态 (电流 < 5mA) ] ~~~~~~~~~~~~~~~~~~~~~~~~
        |
   [ 硬件唤醒事件触发: 如 5G Modem 收到来电寻呼 / 电源键按下 ]
        |
        v
   [ 阶段 6: 硬件唤醒与整机恢复 (System Resume Flow) ]
        | * AON 逻辑唤醒 PMIC，恢复 SoC 主供电轨与锁相环 (PLL) 时钟树
        | * Core 0 从 ATF 固件恢复执行现场，跳转回内核 syscore_resume()
        | * 启动 Secondary Cores (PSCI CPU_ON) 并恢复调度器运行
        | * 逆向执行 dpm_resume_noirq() -> dpm_resume_early() -> dpm_resume() 恢复设备
        | * 解冻用户空间任务 (Thaw Tasks)，通知 Android 亮屏或分发来电广播
        v
   [ 系统重回 Active 运行态 ]

移动 System Suspend 与桌面 S3/S4 的本质区别
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 移动平台 System Suspend 与 PC 桌面睡眠机制对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 对比维度
     - 移动系统 Suspend (Android / iOS)
     - 桌面系统 S3 (Sleep) / S4 (Hibernate)
   * - **待机目标**
     - **“假死真活”**：通信随时在线，毫秒级响应外部来电
     - **“彻底休眠”**：断开绝大多数外部网络，除非显式 WoL 唤醒
   * - **唤醒时间预算**
     - **极速响应**（从按键到屏幕全亮 $<100	ext{ms}$）
     - 较慢（S3 需 1~3 秒，S4 需 10~30 秒）
   * - **外设协处理器**
     - **Sensor Hub / Modem 独立运行**，主 AP 完全断电
     - 外设全部下电或进入 D3hot/cold 状态
   * - **休眠触发频率**
     - **碎片化高频进出**（用户一旦熄屏，几秒内立即 suspend）
     - 低频触发（通常由用户主动合盖或闲置 30 分钟触发）

------------------------------------------------------------------------
21.5 设备运行时电源管理 (Runtime PM) 与设备树供电拓扑
------------------------------------------------------------------------

整机 Suspend 属于粗粒度的系统级动作。在用户点亮屏幕使用手机的日常场景中，许多外设模块（如相机 ISP、GPS 芯片、UFS 存储控制器、NPU）大部分时间处于闲置状态。若让这些外设持续上电运行，将造成不可容忍的电池空耗。

Linux 内核提供了 **Runtime PM（运行时电源管理）** 框架，允许外设驱动在其空闲时**独立、动态地下电与休眠**，而无需等待整机 Suspend。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                设备运行时电源管理 (Runtime PM) 引用计数状态机           |
   +-------------------------------------------------------------------------+

   [ 应用打开相机 (Camera API) ]
        |
        v
   [ 驱动层调用: pm_runtime_get_sync(dev) ]
        | * dev->power.usage_count++ (原子引用计数从 0 变 1)
        | * 触发设备供电拓扑上电: 开启 PMIC LDO 供电轨 -> 开启总线时钟
        | * 执行驱动回调: dev->pm->runtime_resume() 初始化相机硬件
        v
   [ 设备处于 RPM_ACTIVE 状态 (正在采集图像帧) ]
        |
   [ 用户退至后台 / 相机关闭 ]
        |
        v
   [ 驱动层调用: pm_runtime_put_autosuspend(dev) ]
        | * dev->power.usage_count-- (引用计数归零)
        | * 启动自动休眠延迟定时器 (Autosuspend Delay: 如 50ms 防止频繁震荡)
        | * 定时器到期触发: dev->pm->runtime_suspend()
        | * 释放时钟资源，关闭 PMIC 供电轨，设备进入 RPM_SUSPENDED 状态
        v
   [ 设备完全断电，静态电流归零! ]

设备树中的 Regulator 与 Power Domain 依赖树
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在设备树（Device Tree）中，外设与片上电源域（Power Domains）和稳压器（Regulators）形成了严密的树状依赖关系：

.. code-block:: dts

   /* 移动 SoC 摄像头子系统设备树节点示例 */
   cam_sensor: camera-sensor@1a {
       compatible = "sony,imx766";
       reg = <0x1a>;
       
       /* 供电轨依赖: 模拟供电 (AVDD)、数字核心供电 (DVDD)、I/O 供电 (DOVDD) */
       avdd-supply = <&pm8350_l17a>;   /* PMIC LDO 17A: 2.8V */
       dvdd-supply = <&pm8350_l18a>;   /* PMIC LDO 18A: 1.1V */
       dovdd-supply = <&pm8350_l19a>;  /* PMIC LDO 19A: 1.8V */

       /* 时钟控制器依赖 */
       clocks = <&clock_controller CAM_MCLK0>;
       clock-names = "mclk";

       /* 挂载到 SoC 影像子系统电源域 */
       power-domains = <&qcom_camss_pd>;
   };

当 `cam_sensor` 进入 Runtime Suspend 时，Runtime PM 核心会沿着设备拓扑向上溯源：如果整个相机子系统（CAMSS）的所有子传感器均已休眠，内核将自动下电顶层的 `qcom_camss_pd` 电源域，并切断对应的 PMIC LDO 供电轨，实现物理层面的彻底断电。

------------------------------------------------------------------------
21.6 Android 功耗治理策略与 Doze / App Standby 内核协同
------------------------------------------------------------------------

尽管内核提供了完善的 Tickless Idle、Runtime PM 与 System Suspend，但如果用户空间存在流氓软件频繁申请 WakeLock、启动无节制的后台常驻服务或设置高频 RTC 唤醒闹钟，内核将反复被从休眠中唤醒，导致待机电池雪崩式耗尽（俗称“电量杀手”）。

为此，Android Framework 构建了以 **Doze Mode（低电耗模式）** 与 **App Standby（应用待机分组）** 为核心的顶层功耗收缩策略，与内核层紧密协同。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Android Doze Mode 两阶段与维护窗口协同模型               |
   +-------------------------------------------------------------------------+

   [ 手机熄屏且静止放置 ]
        |
        v (熄屏数分钟)
   +-------------------------------------------------------------------------+
   | [ Light Doze (轻度低电耗模式) ]                                         |
   | * 阻断应用后台网络访问 (Network Policy Firewall)                        |
   | * 延后普通同步任务 (SyncManager) 与 JobScheduler 任务                    |
   +-------------------------------------------------------------------------+
        |
        v (持续未插电且运动传感器检测到绝对静止)
   +-------------------------------------------------------------------------+
   | [ Deep Doze (深度低电耗模式) ]                                          |
   | * 忽略所有非系统白名单应用的 WakeLock 持锁申请                          |
   | * 阻断标准 AlarmManager 闹钟 (仅允许 setAndAllowWhileIdle)              |
   | * 停止 Wi-Fi 扫描与基带高频探测                                         |
   | * 内核获得持续无锁环境，进入超长时间 System Suspend                     |
   +-------------------------------------------------------------------------+
        |                                       ^
        | (周期性递增开启维护窗口: 15m -> 30m -> 1h -> 2h...) |
        v                                       |
   +-------------------------------------------------------------------------+
   | [ Maintenance Window (周期性维护窗口: 持续 1~2 分钟) ]                  |
   | * 短暂恢复网络连接，允许所有堆积的后台 Job / Sync 集中批量并发执行      |
   | * 窗口关闭后，系统重新沉入更长时间的 Deep Doze                           |
   +-------------------------------------------------------------------------+

Doze 模式的系统服务控制闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **运动传感器静止判定（Significant Motion / AnyMotion Detector）**：
   - 依赖独立低功耗 Sensor Hub 协处理器监听加速度计数据；
   - 只有在手机被水平静置于桌面且一定时间内无物理位移时，系统方允许步入 Deep Doze；一旦用户拿起手机，Sensor Hub 触发硬件中断瞬间唤醒系统并退出 Doze；
2. **强制释放应用持锁通道**：
   - `DeviceIdleController`（Doze 控制中枢）通知 `PowerManagerService` 进入全局挂起模式；
   - 所有第三方未加白名单的应用进程即使调用 `wakeLock.acquire()`，在系统服务内部直接被标记为失效（Disabled），底层 `system_suspend` 守护进程不再向内核 `wakeup_source` 注入持锁请求，强行放行内核 System Suspend。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了移动操作系统电源管理从内核底层机制到上层治理策略的完整闭环：从消除不必要中断的 Tickless Idle 动态时钟，到基于目标驻留时间决策的 CPUIdle C-State 能级跃迁与 ARM ATF PSCI 固件交互；从 Android WakeLock 到 Linux 主线 `struct wakeup_source` 的演进，到 System Suspend 冻结进程、逐级断电外设、单核关断主供电轨的六阶段完整状态机；最后剖析了设备级 Runtime PM 供电依赖树与 Android Framework Doze 模式自上而下的功耗收敛体系。

在攻克了进程调度、内存治理、中断驱动与休眠电源等内核核心子系统后，下一章我们将深入 Part 4 的收官之作——**内核安全边界与攻击面收敛：DAC、MAC 与系统调用过滤**，全面剖析移动内核如何在底层构筑坚不可摧的特权隔离防线。
