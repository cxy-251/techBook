第014章：ISP, Camera Sensor, Lens, and Imaging Hardware
=======================================================

核心知识点
----------

* 手机相机的主硬件链是 ``Lens → Sensor → Camera Interface → ISP → Memory Buffer → Preview / Capture / Video``。App 调用相机 API 时，真正执行的是这条硬件与系统服务组合路径。
* Lens 决定光学输入，Sensor 把光转换成 RAW 采样，ISP 把 RAW 处理成可显示、可编码、可分析的图像。上层算法不能完全补偿镜头、sensor 和读出方式的物理限制。
* Sensor 的关键能力包括像素阵列、读出速度、曝光范围、增益、HDR mode、rolling/global shutter 特征、PDAF 等。应用看到的是 HAL 与 framework 已经裁剪过的能力表。
* ISP pipeline 通常包含 black level、坏点处理、lens shading、demosaic、noise reduction、color correction、HDR、sharpening、tone mapping 等阶段；目标是把物理采样变成稳定视觉结果。
* 3A 是闭环控制：AE 调曝光与增益，AF 调镜头位置，AWB 调色温与通道增益；当前帧统计会反馈到后续帧的 sensor、lens 和 ISP 参数。
* Preview 与 still capture 共享前半段硬件，但目标不同。Preview 优先连续低延迟，Still Capture 优先高分辨率与画质，可能使用更重的多帧、HDR、NPU/GPU 后处理。
* Camera request 描述期望采集参数和输出 stream，capture result 返回实际 metadata 与状态。能力必须先由 hardware/HAL 声明，App 才能稳定请求。
* Buffer 是相机系统的关键交换对象。ISP 输出 frame 后，会进入 preview surface、still capture、video encoder、ML consumer 等不同路径；多消费者会增加带宽和同步压力。
* 相机能力受 stream combination、ISP throughput、memory bandwidth、temperature、设备并发和系统服务仲裁共同约束。Sensor 规格高不代表所有模式可以同时开启。
* 厂商影像差异来自镜头、Sensor、OIS、ISP、NPU、算法、色彩与调参的整体系统，而不是单个“像素数量”或某一种算法。

关键路径
--------

连续预览：

::

   lens focuses light
   → sensor exposes and reads RAW frame
   → CSI / camera interface
   → ISP processing
   → camera buffer
   → preview surface
   → graphics compositor
   → display

3A 闭环：

::

   current frame
   → ISP statistics
   → AE / AF / AWB algorithms
   → update exposure / gain / lens / color parameters
   → next sensor frame
   → repeat until stable

拍照请求：

::

   app capture request
   → framework / camera service
   → HAL validates stream and controls
   → sensor + ISP capture
   → result metadata + output buffers
   → encode / save / return to app

概念辨析
--------

* **Lens 与 Sensor**：Lens 决定进入 sensor 的光学图像，Sensor 决定采样；两者的问题不能简单靠 ISP 完全修复。
* **ISP 与 NPU**：ISP 擅长固定实时图像处理，NPU 更适合学习型模型；现代影像 pipeline 常同时使用两者。
* **Preview 与 Capture**：两者可能来自同一 sensor，却使用不同分辨率、处理强度、buffer 和 latency 目标。
* **Hardware capability 与 Camera API**：硬件存在某模式不等于 framework 一定开放；HAL 能力声明与 stream combination 才是 App 的可用边界。
* **分辨率与画质**：更高像素只改变采样上限，镜头、噪声、动态范围、ISP、算法和曝光条件共同决定最终画质。

本章结论
--------

相机是一条从光学到 buffer 的实时闭环系统。理解预览卡顿、对焦失败、画质差异或能力缺失时，应沿 Lens、Sensor、3A、ISP、stream/buffer、HAL 与 Camera Service 逐段定位，而不是只看相机 API 参数或传感器规格。