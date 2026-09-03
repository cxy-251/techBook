========================================================================
Chapter 25: 传感器 HAL 与 Sensor Hub 通信：IIO 子系统与低功耗监听
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 24）中，我们系统剖析了厂商接口契约（VINTF）与通用系统镜像（GSI）的解耦升级机制。VINTF 确保了框架与硬件在静态接口契约上的兼容性。然而，在移动设备中，物理硬件的实时数据采集对功耗与时延有着极端严苛的要求。智能手机内部集成了加速度计、陀螺仪、地磁计、光感、距离感应、气压计等数十种传感器，这些传感器不仅需要在用户交互时提供高达数百赫兹的高吞吐数据，更需要在整机处于锁屏休眠（Suspend）状态下以微安（$\mu	ext{A}$）级电流持续监听抬腕、计步和手势唤醒。本章将深入解构移动传感器子系统的垂直数据链路：从底层的物理采样与 Sensor Hub 协处理器微架构，到 Linux 内核工业 I/O（IIO）子系统，再到 Android Sensors AIDL HAL 中的 Fast Message Queue（FMQ）无锁零拷贝队列与 Direct Channel 硬件直达机制。

------------------------------------------------------------------------
25.1 移动传感器微架构与物理采样全景
------------------------------------------------------------------------

传感器硬件拓扑与总线连接
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

移动设备上的传感器在物理形态上多属于 **MEMS（微机电系统 / Micro-Electro-Mechanical Systems）** 芯片，通过板级总线与处理芯片物理相连：

- **I2C（Inter-Integrated Circuit）**：工作频率通常为 400 kHz（Fast-mode）或 1 MHz（Fast-mode Plus），采用两线制（SDA/SCL），主要用于低频环境传感器（如环境光、距离、气压计）；
- **SPI（Serial Peripheral Interface）**：工作频率可达 10 MHz ~ 20 MHz，采用四线制（CS, SCLK, MOSI, MISO），全双工高吞吐，主要用于高频运动传感器（如 6 轴/9 轴 IMU 惯性测量单元）；
- **I3C（Improved Inter-Integrated Circuit）**：新一代移动传感器总线标准，两线制下提供高达 12.5 MHz 数据率，支持带内中断（In-Band Interrupt - IBI）与动态寻址，消除了专用外部中断引脚（GPIO IRQ）的布线开销。

.. list-table:: 移动设备核心传感器物理特性与采样要求
   :widths: 18 15 20 22 25
   :header-rows: 1
   :class: tight-table

   * - 传感器类型
     - 物理总线
     - 典型采样率范围
     - 数据量化精度
     - 核心应用场景与功耗敏感度
   * - **加速度计 (Accelerometer)**
     - SPI / I3C
     - 50 Hz ~ 400 Hz
     - 16-bit 3轴 ($	ext{m/s}^2$)
     - 屏幕旋转、UI 物理效果、计步常驻 (极度敏感)
   * - **陀螺仪 (Gyroscope)**
     - SPI / I3C
     - 100 Hz ~ 800 Hz
     - 16/24-bit 3轴 ($	ext{rad/s}$)
     - 游戏视角控制、相机 OIS 光学防抖、AR 姿态追踪
   * - **磁力计 (Magnetometer)**
     - I2C / SPI
     - 10 Hz ~ 100 Hz
     - 16-bit 3轴 ($\mu	ext{T}$)
     - 电子罗盘、地图朝向校准 (易受电磁干扰)
   * - **环境光与距离感应 (ALS/PS)**
     - I2C
     - 5 Hz ~ 20 Hz
     - 16-bit 标量 (Lux / cm)
     - 自动亮度调节、通话防误触贴耳灭屏
   * - **气压计 (Barometer)**
     - I2C / SPI
     - 1 Hz ~ 25 Hz
     - 24-bit 标量 (hPa)
     - 室内楼层高度判定、辅助 GPS 垂直定位

传感器融合 (Sensor Fusion) 数学模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

单个物理传感器具有不可消除的物理缺陷：
- 加速度计受震动噪声干扰大，且无法区分重力加速度与动态线性加速度；
- 陀螺仪短时精度极高，但积分计算角度时存在物理漂移（Drift）；
- 磁力计对周围硬铁与软铁电磁环境极度敏感。

为了向上层提供高精度的虚拟复合传感器（如 ``TYPE_ROTATION_VECTOR``、``TYPE_LINEAR_ACCELERATION``、``TYPE_GRAVITY``），系统必须在底层运行 **传感器融合（Sensor Fusion）算法**（通常基于扩展卡尔曼滤波 EKF 或互补滤波算法）：

.. math::

   \mathbf{q}_{t} = \mathbf{q}_{t-1} \otimes \Delta \mathbf{q}(\boldsymbol{\omega}_t \Delta t) \quad \xrightarrow{	ext{Kalman Correction}} \quad \hat{\mathbf{q}}_t = f(\mathbf{q}_t, \mathbf{a}_t, \mathbf{m}_t)

通过陀螺仪高频角速度 $\boldsymbol{\omega}_t$ 进行姿态四元数 $\mathbf{q}$ 航位推算，并利用加速度计低频重力向量 $\mathbf{a}_t$ 与地磁向量 $\mathbf{m}_t$ 作为观测方程对漂移进行实时闭环校正，最终解算出绝对世界坐标系下的设备三维朝向。

------------------------------------------------------------------------
25.2 独立 Sensor Hub (CHRE) 低功耗协处理器架构
------------------------------------------------------------------------

主 AP 直接采样的能耗悖论
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若由应用处理器（Application Processor - AP / 即主 SoC 上的 CPU 大小核）直接通过内核 I2C/SPI 驱动以 200 Hz 轮询或中断方式读取 IMU 数据：
- 主 CPU 将被锁死在活跃或浅休眠状态，无法进入低功耗深度休眠模式（C-States / System Suspend）；
- 整机基线电流将从待机状态的 **3 mA ~ 5 mA 暴增至 150 mA ~ 300 mA**，一块 4000 mAh 电池在息屏待机状态下将在 15 小时内耗尽。

Sensor Hub 物理拓扑与硬件卸载
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代移动 SoC 引入了物理独立的 **Sensor Hub（低功耗传感器中枢协处理器）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             现代移动 SoC Sensor Hub 硬件拓扑与数据流                    |
   +-------------------------------------------------------------------------+

   [ 外部物理传感器芯片 ]
   +--------------------+  +--------------------+  +--------------------+
   | IMU (Acc + Gyro)   |  | 光感 + 距离 (ALS)  |  | 磁力计 / 气压计   |
   +--------------------+  +--------------------+  +--------------------+
             | SPI                   | I2C                   | I2C/I3C
             +-----------------------+-----------------------+
                                     |
                                     v
   +-------------------------------------------------------------------------+
   | Sensor Hub 独立芯片 / 片上独立供电域 (DSP / Cortex-M33 / SLPI)          |
   | (独立运行实时操作系统 RTOS: FreeRTOS / Zephyr / CHRE)                   |
   |                                                                         |
   | +---------------------------------------------------------------------+ |
   | | 片上硬件微控制器 (Microcontroller Core, < 5mW 全速功耗)             | |
   | +---------------------------------------------------------------------+ |
   | | 硬件私有内存 (SRAM: 512KB ~ 2MB)                                    | |
   | | - 运行 Sensor Fusion 姿态融合算法                                   | |
   | | - 运行手势识别 (Gesture / Activity Recognition)                     | |
   | | - 运行抬腕亮屏 (Significant Motion / Tilt-to-Wake Nanoapps)         | |
   | +---------------------------------------------------------------------+ |
   | | 硬件事件环形缓冲区 (Hardware Sensor Event FIFO: 8KB ~ 64KB)         | |
   | +---------------------------------------------------------------------+ |
   +-------------------------------------------------------------------------+
                      |                                     |
                      | 共享内存 (Shared RAM / DMA)         | 外部唤醒引脚 (Wakeup GPIO IRQ)
                      v                                     v
   +=========================================================================+
   | 主应用处理器 (Application Processor - AP / Linux Kernel)                |
   | (主 CPU 核心在此期间可保持深度挂起 Suspend, 功耗接近 0)                 |
   +=========================================================================+

- **独立硬件核**：通常采用专用 DSP（如高通 Hexagon SLPI / Sensor Low-Power Island）或超低功耗 ARM Cortex-M 核心，配备独立的片上 SRAM，整机运行功耗仅为 **1 mW ~ 5 mW**；
- **总线物理隔离**：传感器物理引脚直接接入 Sensor Hub 的 I2C/SPI 控制器，物理上绕开主 AP 总线；
- **全天候后台监听（Always-On Sensing）**：在手机黑屏休眠期间，主 AP 完全断电挂起，Sensor Hub 独立运行计步、抬腕检测与语音关键词监听（Voice Wakeup）。

CHRE (Context Hub Runtime Environment) 微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AOSP 提出了标准化的 **CHRE（Context Hub Runtime Environment）** 规范。CHRE 是运行在 Sensor Hub RTOS 之上的 C++ 跨平台事件驱动运行时，支持动态加载微型应用程序——**Nanoapps**：

.. list-table:: CHRE 核心组件与职责划分
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 运行时组件
     - 物理运行位置
     - 核心功能与机制
   * - **CHRE Core Framework**
     - Sensor Hub SRAM
     - 事件调度循环、传感器数据分发、定时器管理、内存安全池
   * - **Sensor Nanoapp**
     - Sensor Hub 动态加载
     - 订阅特定硬件采样率，执行滤波与特征工程计算
   * - **Gesture Nanoapp**
     - Sensor Hub 动态加载
     - 模式匹配抬起（Pick-up）、翻转（Flip）、摇一摇等物理手势
   * - **ContextHub HAL**
     - 主 AP (Vendor 空间)
     - 通过 IPC 驱动与 Sensor Hub 交互，管理 Nanoapp 签名下载与状态同步

硬件 FIFO 批量传输 (Batching) 机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了进一步降低主 AP 唤醒频率，Sensor Hub 配置了专用的硬件 FIFO 环形缓冲：
- 应用通过系统 API 请求传感器时，可指定 ``maxReportLatencyUs``（最大上报延迟）；
- Sensor Hub 以设定频率采集样本后，**先暂存于片上 FIFO 中，并不立即唤醒主 AP**；
- 只有当满足以下三个条件之一时，Sensor Hub 才会拉高 AP 唤醒中断引脚（Wakeup IRQ）并触发 DMA 批量传输：
  1. 累积时间达到应用指定的 ``maxReportLatencyUs`` 阈值；
  2. 片上硬件 FIFO 存满（FIFO Full）；
  3. 捕获到必须即时响应的唤醒事件（如抬腕亮屏或跌落检测）。

------------------------------------------------------------------------
25.3 Linux 工业 I/O (IIO) 子系统微架构
------------------------------------------------------------------------

Linux 驱动选型：为什么不是 Input 子系统？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

早期 Android 使用 Linux ``input`` 子系统（``/dev/input/eventX``）承载传感器。然而 ``input`` 子系统存在根本缺陷：
- 结构体 ``struct input_event`` 强制包含秒、微秒时间戳、type、code、value，每次事件开销达 24 字节（64位系统）；
- 仅原生支持标量整数，无法高效表达多通道同步采样（如 3 轴加速度同时采样并在硬件同一纳秒锁存）；
- 缺乏通道尺度缩放（Scale）、通道偏移（Offset）与硬件触发采样（Hardware Trigger）标准协议。

因此，Linux 内核引入了专为 ADC、DAC、陀螺仪、IMU 设计的 **IIO（Industrial I/O）子系统**。

IIO 核心数据结构与内核抽象
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Linux 内核中，每个传感器设备抽象为一个 ``struct iio_dev`` 实体：

.. code-block:: c

   #include <linux/iio/iio.h>
   #include <linux/iio/buffer.h>

   struct iio_dev {
       int                             id;
       const char                      *name;
       const struct iio_info           *info;          /* 读写控制回调 */
       const struct iio_chan_spec      *channels;      /* 通道描述符数组 */
       int                             num_channels;   /* 通道数量 */
       struct iio_buffer               *buffer;        /* 环形缓冲区指针 */
       struct iio_trigger              *trig;          /* 当前绑定的触发器 */
       struct device                   dev;
   };

``struct iio_chan_spec`` 通道描述符
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个物理测量维度定义为一个通道（Channel）：

.. code-block:: c

   static const struct iio_chan_spec mpu6050_channels[] = {
       {
           .type = IIO_ACCEL,
           .modified = 1,
           .channel2 = IIO_MOD_X,
           .info_mask_separate = BIT(IIO_CHAN_INFO_RAW),
           .info_mask_shared_by_type = BIT(IIO_CHAN_INFO_SCALE),
           .scan_index = 0,
           .scan_type = {
               .sign = 's',
               .realbits = 16,
               .storagebits = 16,
               .endianness = IIO_LE,
           },
       },
       /* Y 轴, Z 轴 与 陀螺仪通道 ... */
       IIO_CHAN_SOFT_TIMESTAMP(3), /* 硬件/内核时间戳通道 */
   };

- **``scan_type``**：精确描述数据在内存中的物理排布（有符号 ``'s'``、有效位 16 位、存储位 16 位、小端序 ``IIO_LE``）；
- **``info_mask_separate``**：通道私有属性（如 X 轴原始计数值 ``in_accel_x_raw``）；
- **``info_mask_shared_by_type``**：同类通道共享属性（如物理缩放因子 ``in_accel_scale``，将原始整型转换为 $	ext{m/s}^2$）。

IIO 触发器 (Trigger) 与连续缓冲区 (kfifo) 流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Linux 内核 IIO 子系统数据流拓扑                     |
   +-------------------------------------------------------------------------+

   [ 硬件层 (MEMS / Sensor Hub) ]
   +-------------------------------------------------------------------------+
   | 硬件产生数据就绪信号 (Data Ready Interrupt 引脚拉高)                    |
   +-------------------------------------------------------------------------+
                                      |
                                      v 触发中断下半部
   [ 内核 IIO 子系统 (Kernel Space) ]
   +-------------------------------------------------------------------------+
   | struct iio_trigger (触发器核心): iio_trigger_poll(trig)                 |
   |                                  |
   |                                  v 调用触发处理函数
   | iio_triggered_buffer_postenable(): 锁定活动通道掩码 (Scan Mask)         |
   |                                  |
   |                                  v SPI/I2C DMA 批量读取多轴物理寄存器
   | struct iio_buffer (kfifo 环形队列):                                     |
   | [ Scan 0: X, Y, Z, Timestamp ] -> [ Scan 1: X, Y, Z, Timestamp ] -> ... |
   +-------------------------------------------------------------------------+
                                      |
                                      | 字符设备驱动层 (VFS)
                                      v
   [ 用户态接口 (User Space: Sensor HAL) ]
   +-------------------------------------------------------------------------+
   | 1. 控制平面 (Sysfs): /sys/bus/iio/devices/iio:device0/                  |
   |    - echo 1 > buffer/enable              (启动流式采样)                 |
   |    - echo 200 > sampling_frequency       (设置采样频率)                 |
   |                                                                         |
   | 2. 数据平面 (Char Device): /dev/iio:device0                             |
   |    - read() / poll() / epoll()           (批量读取二进制结构体流)       |
   +-------------------------------------------------------------------------+

------------------------------------------------------------------------
25.4 现代 Android Sensors AIDL HAL 微架构与无锁队列
------------------------------------------------------------------------

Sensors HAL 接口演进与架构重构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sensors HAL 经历了从早期基于轮询的 C 语言函数指针，到现代强类型跨进程架构的演进：

.. list-table:: Android Sensors HAL 架构演进全景
   :widths: 20 20 30 30
   :header-rows: 1
   :class: tight-table

   * - 架构代际
     - 接口规范
     - 通信方式
     - 核心特征与瓶颈
   * - **Legacy HAL**
     - ``sensors.h`` (v1.0 ~ v1.4)
     - 同一进程 ``dlopen()`` 动态库
     - ``poll()`` 单线程阻塞循环，稳定性差，易被 Vendor 崩溃拖死
   * - **HIDL HAL**
     - ``android.hardware.sensors@2.0/2.1``
     - Binder 跨进程 + FMQ 共享内存队列
     - 引入 Fast Message Queue，支持动态传感器与传感器注入
   * - **Stable AIDL**
     - ``android.hardware.sensors-V2`` (Android 13+)
     - 统一 Stable AIDL 接口 + AIDL FMQ
     - 消除 ``hwservicemanager``，强类型接口契约，支持 Direct Report

Stable AIDL `ISensors.aidl` 核心契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 Sensors HAL 的核心 AIDL 接口定义如下：

.. code-block:: java

   package android.hardware.sensors;

   interface ISensors {
       // 1. 获取设备支持的所有物理与虚拟传感器元数据描述
       SensorInfo[] getSensorsList();

       // 2. 初始化 Fast Message Queue (FMQ) 事件通道与唤醒锁同步
       void initEventFlag(in EventFlag eventFlag);

       // 3. 激活 / 去激活指定传感器
       void activate(in int sensorHandle, in boolean enabled);

       // 4. 配置采样周期与批处理最大上报延迟
       void batch(in int sensorHandle, in long samplingPeriodNs, in long maxReportLatencyNs);

       // 5. 强制刷新当前底层 FIFO 中的所有暂存事件
       void flush(in int sensorHandle);

       // 6. 配置直接内存报告通道 (Direct Channel)
       int configDirectReport(in int sensorHandle, in int channelHandle, in int rateLevel);
   }

FMQ (Fast Message Queue) 零拷贝无锁队列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在高采样率场景（如 500 Hz 的 9 轴 IMU），每秒产生上千个 ``Event`` 结构体。若通过标准 Binder RPC 进行传输，每次调用都需要触发用户态-内核态上下文切换、数据序列化（Parceling）与内核物理内存拷贝，CPU 开销将突破 15%。

为了彻底解决这一性能瓶颈，Sensors HAL 引入了 **Fast Message Queue（FMQ）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               Sensors HAL Fast Message Queue (FMQ) 拓扑架构             |
   +-------------------------------------------------------------------------+

   [ Sensor HAL 守护进程 (Vendor Space) ]       [ SensorService (SystemServer) ]
   +------------------------------------+       +------------------------------+
   | HAL 事件写入线程 (Event Producer)  |       | 事件分发线程 (Event Consumer)|
   +------------------------------------+       +------------------------------+
                    |                                          |
                    | (用户态直接读写, 无任何系统调用与内核介入) |
                    v                                          v
   +===========================================================================+
   | 共享内存区域 (Shared Memory: POSIX shm / ashmem / dma-buf)                |
   |                                                                           |
   | +-----------------------------------------------------------------------+ |
   | | 队列元数据环形头 (Ring Buffer Metadata - 原子无锁索引计数器)          | |
   | | - mReadPtr (原子读指针)       - mWritePtr (原子写指针)                | |
   | +-----------------------------------------------------------------------+ |
   | | 预分配事件环形槽位数组 (Circular Event Buffer: Event[N])              | |
   | | [ Event 0 ] [ Event 1 ] [ Event 2 ] ... [ Event N-1 ] (每个 64 字节)  | |
   | +-----------------------------------------------------------------------+ |
   | | Futex 同步字 (EventFlag Word: 32-bit Bitmask)                         | |
   | +-----------------------------------------------------------------------+ |
   +===========================================================================+

FMQ 无锁环形缓冲核心算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **单生产者-单消费者（SPSC）内存可见性**：
   - HAL 生产端使用 ``std::atomic::load/store`` 配合 **获取-释放语义（Acquire-Release Memory Order）** 操作写指针（``mWritePtr``）；
   - SensorService 消费端以 Acquire 语义读取写指针，以 Release 语义更新读指针（``mReadPtr``），全程**无需互斥锁（Mutex-free）**；
2. **Futex 极速通知机制**：
   - 当队列由空变为非空时，生产端通过 Futex 系统调用唤醒消费端；当队列持续高速传输时，消费端在用户态自旋或轻量级 Futex 等待，完全旁路 Binder 驱动。

------------------------------------------------------------------------
25.5 唤醒传感器 vs 非唤醒传感器与 Direct Channel 直达
------------------------------------------------------------------------

Wake-up vs Non-wake-up 传感器电源语义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AOSP 严格规定了两类传感器的电源管理语义，这直接决定了休眠策略：

.. list-table:: 唤醒与非唤醒传感器行为对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - Non-wake-up 传感器 (非唤醒型)
     - Wake-up 传感器 (唤醒型)
   * - **AP 活跃时行为**
     - 正常产生并上报数据
     - 正常产生并上报数据
   * - **AP 挂起休眠时行为**
     - **绝不唤醒 AP**；数据暂存于 Sensor Hub FIFO，FIFO 满后**静默丢弃旧数据**（Overwrite）
     - 捕获到事件或 FIFO 满时，**立即拉高硬件中断唤醒 AP** 并递送数据
   * - **典型传感器代表**
     - ``TYPE_ACCELEROMETER``、``TYPE_GYROSCOPE``、``TYPE_LIGHT`` (常规连续采样)
     - ``TYPE_SIGNIFICANT_MOTION`` (重大动作)、``TYPE_WAKE_GESTURE``、``TYPE_STEP_DETECTOR``
   * - **系统功耗影响**
     - 零待机能耗开销
     - 若被频繁误触，将引发唤醒风暴（Wakeup Storm）

Direct Channel (直接内存通道) 硬件直达
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 VR / AR 头部追踪或低时延游戏控制器，即使经过 SensorService 分发仍会引入 5 ms ~ 10 ms 的进程调度抖动。

Android 引入了 **Direct Report Channel**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Sensor Direct Channel 硬件直达架构拓扑                   |
   +-------------------------------------------------------------------------+

   [ 客户端应用进程 (Game / AR Engine) ]
   +-------------------------------------------------------------------------+
   | 1. ASharedMemory_create() 或 AHardwareBuffer_allocate() 分配共享内存    |
   | 2. 通过 SensorManager.createDirectChannel() 将内存 FD 传递给系统        |
   | 3. 直接在私有内存环形槽位中无锁轮询读取最新数据 (零延迟)                |
   +-------------------------------------------------------------------------+
                                      ^
                                      | 硬件 DMA 零拷贝直写 (完全旁路 SensorService)
   +-------------------------------------------------------------------------+
   | Sensor Hub / IIO 驱动物理控制器                                         |
   | - 传感器每完成一次采样，DMA 引擎直接将数据写入该共享物理页框            |
   +-------------------------------------------------------------------------+

------------------------------------------------------------------------
25.6 传感器数据链路与延迟排查决策树
------------------------------------------------------------------------

传感器状态诊断工具链
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # 1. 查看当前系统中所有已注册传感器的详细状态、采样率与活跃订阅者
   adb shell dumpsys sensorservice

   # 2. 转储 Sensors HAL 运行状态与 FMQ 队列指标
   adb shell dumpsys android.hardware.sensors.ISensors/default

   # 3. 查看 Linux 内核 IIO 物理设备注册节点
   adb shell ls -la /sys/bus/iio/devices/

   # 4. 实时跟踪传感器事件分发与唤醒锁持有时间
   adb shell atrace --async_start -b 16384 sensors am pm

传感器子系统故障排查决策树
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   [ 现象: 屏幕无法自动旋转 / 计步器失效 / 息屏待机异常耗电 ]
                               |
                               v
            [ 执行 adb shell dumpsys sensorservice ]
                               |
               +---------------+---------------+
               |                               |
               v 传感器列表为空 / 崩溃         v 传感器存在但无数据上报
   +-------------------------------+   +-------------------------------+
   | 1. 检查 /vendor/etc/vintf     |   | 1. 检查各客户端请求的采样周期 |
   |    是否声明 android.hardware. |   |    与 maxReportLatencyNs;     |
   |    sensors 服务;              |   | 2. 检查应用是否持有非唤醒型   |
   | 2. 检查 Sensor HAL 守护进程   |   |    传感器导致休眠期数据被冲掉;|
   |    是否启动 (ps -A | grep -i  |   | 3. 读取底层内核节点:          |
   |    sensor);                   |   |    cat /sys/bus/iio/devices/  |
   | 3. 排查 SELinux 权限拒绝。    |   |    iio:device0/in_accel_x_raw |
   +-------------------------------+   +-------------------------------+
                                                       |
                                                       v
                                       +-------------------------------+
                                       | 内核节点是否有数值动态变化?   |
                                       +-------------------------------+
                                           |                       |
                                     No    |                   Yes |
                                           v                       v
                           +-----------------------+ +-----------------------+
                           | 1. 检查 I2C/SPI 总线  | | 1. 检查 Sensor Hub    |
                           |    供电轨与硬件挂死;  | |    CHRE 固件事件过滤; |
                           | 2. 检查 Sensor Hub 固 | | 2. 检查 FMQ 队列是否溢|
                           |    件是否崩溃死锁。   | |    出或读写指针死锁。 |
                           +-----------------------+ +-----------------------+

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统剖析了移动操作系统传感器子系统的端到端微架构：从多轴 MEMS 物理采样与传感器融合算法，到基于独立超低功耗 Sensor Hub（CHRE）的后台常驻监听与 FIFO 批处理机制；从 Linux 内核统一的 IIO 工业 I/O 驱动架构，到 Android Sensors AIDL HAL 基于 Fast Message Queue（FMQ）的无锁零拷贝传输，以及面向极致低延迟场景的 Direct Channel 硬件直通通道。

传感器子系统解决了移动终端对外界物理世界的感知与低功耗监听。而在多媒体交互领域，音频系统的低时延输入输出与多通路混音则是另一大高并发、高实时性的核心中枢。在下一章——**Chapter 26: 音频与多媒体 HAL 架构：AudioFlinger、ALSA 与低时延通路** 中，我们将深入解构 Android 音频服务器（AudioFlinger）、Linux ALSA 内核音频驱动、AudioTrack/AudioRecord 共享内存流转以及 FastMixer 与 AAudio/Oboe 超低时延音频处理流水线。
