第130章：Core Mobile Sensors
=============================

核心知识点
----------

* 核心移动传感器负责把设备运动、环境变化和接近状态转换成可调度的数据流；系统再把这些数据组合成屏幕方向、自动亮度、步数、姿态、楼层变化等能力。
* Accelerometer 测量三轴加速度，通常包含重力分量。它适合判断设备朝向、摇动、步态、冲击和自由落体，但不能直接把读数积分成稳定位置。
* Gravity 与 linear acceleration 是对 accelerometer 数据进一步处理后的不同语义：前者保留重力方向，后者尽量去除重力分量。
* Gyroscope 测量三轴角速度，适合低延迟追踪快速旋转；积分会累积 bias 和 drift，因此长期姿态必须借助其它参考修正。
* Magnetometer 测量地磁场，为航向和绝对方向提供参考；硬铁/软铁效应、扬声器、金属环境和车辆都会制造明显干扰。
* Proximity sensor 服务通话贴耳灭屏、口袋防误触等近距离判断。它提供的是阈值型接近事实，具体灭屏策略属于电话、显示和窗口系统。
* Ambient light sensor 驱动自动亮度、显示功耗和部分 HDR/环境适配策略。系统通常会平滑读数，避免光线抖动造成屏幕亮度频繁跳变。
* Barometer 测量气压，能反映相对高度变化，但天气变化会改变基线；楼层、爬升和定位融合必须结合时间序列及其它数据源。
* 屏幕方向、device motion、step detector、activity recognition 等属于物理传感器向虚拟能力的转换结果。
* 单一 sensor 的可观测事实很有限。运动状态通常需要时间窗口、多个轴、多个传感器、历史状态以及设备姿态共同判断。
* Android 通过 SensorManager 暴露物理与软件合成 sensor；Apple 主要通过 Core Motion 将 accelerometer、gyro、magnetometer、device motion、pedometer、altimeter 等组织成高层接口。
* 排查传感器失准时，应依次检查硬件存在性、单位/坐标系、校准状态、采样频率、融合状态、系统策略和 App 解释，而不是直接归因于某一个 API。

关键路径
--------

运动姿态路径：

::

   accelerometer + gyroscope + magnetometer
   → calibration
   → coordinate normalization
   → filtering / fusion
   → gravity + attitude + heading
   → framework motion object
   → orientation / AR / game / activity logic

环境策略路径：

::

   proximity / ambient light / barometer
   → sensor service
   → debouncing / smoothing / calibration
   → display / telephony / location / activity policy
   → user-visible behavior

概念辨析
--------

* **Accelerometer 与 gyroscope**：前者感知线性加速度和重力，后者感知角速度；两者互补，不可互相替代。
* **Magnetic heading 与 gyroscope heading**：磁力计提供长期绝对方向参考，陀螺仪提供短时相对旋转连续性。
* **Proximity event 与 screen-off policy**：接近事件是输入事实，是否熄屏由系统电话/显示策略决定。
* **Barometric altitude 与 absolute altitude**：气压更适合相对高度变化，绝对高度仍需基线、GNSS 或地图上下文。
* **Physical measurement 与 context event**：物理 sensor 输出测量值，步数、活动、姿态等是算法解释后的系统能力。

本章结论
--------

手机核心传感器应按“物理量 → 校准 → 时间序列 → 融合 → 系统策略”理解。单个芯片只提供局部事实，真正影响 UI、定位、运动、通话和功耗的，是系统把多传感器数据转换成稳定上下文后的结果。