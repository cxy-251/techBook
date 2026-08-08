第129章：Sensor Hardware and Sensor Fusion
============================================

核心知识点
----------

* 移动传感器链的稳定模型是 ``Physical World → Sensor Chip → Driver / Sensor Hub → HAL → System Service → Framework → App``。控制请求向下传递，测量事件向上返回。
* Accelerometer、gyroscope、magnetometer、barometer、ambient light、proximity 等传感器提供不同物理量；系统能力通常来自多个物理传感器的组合，而不是某一个芯片的原始输出。
* Raw sensor data 接近硬件测量值，可能包含 bias、比例误差、温漂、噪声和坐标偏差；calibrated data 已经过偏置补偿、单位转换、坐标约定和精度标记。
* Sensor event 的 timestamp 应表达物理测量时刻，而不是 callback 到达 App 的时刻。批量上报只改变交付时间，不应改写事件时间线。
* Sampling rate 决定采样密度，batching 决定上报延迟，FIFO 决定低功耗阶段可以缓存多少事件；三者共同决定延迟、数据完整性和功耗。
* 多个客户端订阅同一 sensor 时，系统服务会合并采样需求和延迟要求；App 请求的频率只是需求，不代表它独占硬件配置。
* Wake-up sensor 可以在主处理器休眠时触发唤醒；non-wake-up sensor 更适合低功耗批处理。后台采样能力必须和系统睡眠策略一起理解。
* Sensor fusion 利用互补特性建立更稳定状态：gyroscope 提供短时旋转连续性，accelerometer 约束重力方向，magnetometer 提供航向参考，barometer 辅助高度变化。
* 高层 device motion、step count、activity、attitude 等结果属于虚拟/融合能力，不应被误认为单个物理 sensor 的直接读数。
* Android 常见链路是 ``SensorManager → SensorService → Sensors HAL → driver / sensor hub``；Apple 公开表面主要通过 Core Motion 暴露 raw motion、device motion、activity、pedometer 等抽象。
* 传感器既是系统功能输入，也是隐私和功耗负载。持续高频运动数据可以推断行为、位置和环境，因此采样频率、后台状态、授权与数据精度都是能力边界。

关键路径
--------

传感器数据链：

::

   App register/request
   → Framework API
   → system sensor service
   → merge client sampling/latency requirements
   → HAL / sensor hub / driver config
   → physical sensor sampling
   → calibration + timestamp
   → FIFO / batching
   → fusion / virtual sensor if needed
   → callback to App

低功耗路径：

::

   screen off / AP sleep
   → sensor hub continues sampling
   → hardware FIFO buffers events
   → wake-up condition or max latency reached
   → wake AP / flush batch
   → deliver events with original timestamps

概念辨析
--------

* **Physical sensor 与 virtual sensor**：前者测量真实物理量，后者由一个或多个物理 sensor 与算法合成高层状态。
* **Raw 与 calibrated data**：raw 更接近芯片输出，calibrated 已包含平台校准、单位和坐标语义。
* **Sampling rate 与 report latency**：前者决定多久测一次，后者决定多久向上层交付一次。
* **Event timestamp 与 callback time**：timestamp 表示测量发生时间，callback time 只是事件送达 App 的时间。
* **Sensor fusion 与简单滤波**：滤波主要抑制噪声或分离频段，fusion 需要综合多个传感器及状态模型形成更高层估计。

本章结论
--------

传感器系统的核心不是“App 读取一个硬件值”，而是 ``采样请求 → 系统合并 → 低功耗采集 → 校准/时间戳 → 融合 → 策略化交付``。判断任何 motion、step、attitude、light 或 proximity 现象时，都应同时检查物理来源、校准状态、采样策略、融合算法、后台功耗和权限边界。