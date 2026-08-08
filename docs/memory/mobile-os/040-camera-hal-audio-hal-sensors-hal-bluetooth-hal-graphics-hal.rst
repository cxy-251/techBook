第040章：Camera HAL, Audio HAL, Sensors HAL, Bluetooth HAL, Graphics HAL
=======================================================================

核心知识点
----------

* Camera、Audio、Sensors、Bluetooth、Graphics HAL 都位于 Android framework/system service 与 vendor hardware implementation 之间，但每类 HAL 的数据节奏和资源模型不同。
* Camera HAL 更接近 request/result frame pipeline：配置 stream，提交 capture request，返回 image buffer、metadata、timestamp、fence 和 error。
* Camera 的关键边界是 sensor/ISP 能力、stream configuration、buffer lifecycle、3A metadata 与 session state。打不开和画质差通常属于不同故障层级。
* Audio HAL 更接近持续 stream：route、format、sample rate、channel、buffer size、mixer、codec、DSP 和 latency 共同决定端到端体验。
* Audio route 由上层 policy 决定，HAL 负责把选定 route 落到 codec、DSP、driver 和实际输入输出设备。低延迟要求 App、framework、HAL、driver 与 hardware 全链路同时满足条件。
* Sensors HAL 把物理 sensor 和 sensor hub 数据包装成统一 sensor event；sensor list、sampling rate、batching、FIFO、wake-up 属性和 timestamp 是核心合同。
* Batching 能让低功耗 sensor hub 先缓存事件、减少主 CPU 唤醒；高采样率提升时间精度，也提高功耗和处理压力。
* Bluetooth HAL/stack 边界把 controller/HCI 与 framework service 分开；真实连接体验还受 profile、radio coexistence、permission、firmware 和 audio route 共同影响。
* Graphics HAL 主要围绕 buffer allocation、Hardware Composer、display config、overlay、fence 和 present。App 画出一帧不代表用户已经看到这一帧，仍需通过合成和 display pipeline。
* 不同 HAL 共享稳定模式：capability query → open/session → configure → submit/start → callback/result → flush/close → error recovery。
* HAL 负责实现硬件能力，不负责替代 framework 做全部权限和生命周期策略。用户可见问题必须先区分 service policy、HAL implementation、driver/firmware 和 hardware。

关键路径
--------

视频通话多 HAL：

::

   Camera API → CameraService → Camera HAL → sensor / ISP
   Audio API → AudioFlinger / Policy → Audio HAL → codec / DSP
   Sensor API → SensorService → Sensors HAL → sensor hub
   Bluetooth API → Bluetooth service / stack → controller / HCI
   Surface → SurfaceFlinger → Graphics HAL / HWC → display

Camera frame：

::

   configure streams
   → obtain buffers
   → submit capture request
   → sensor / ISP produces frame
   → return buffer + metadata + fence
   → preview / encoder / ImageReader consumes result

Display frame：

::

   App produces buffer
   → SurfaceFlinger gathers layers
   → HWC chooses overlay / composition
   → fence synchronization
   → present to display controller
   → panel scanout

概念辨析
--------

* **Camera request/result 与 Audio stream**：Camera 以帧和请求为核心；Audio 更强调持续 buffer 水位、时钟和 route。
* **Sensor sampling 与 batching**：Sampling 决定采样频率，batching 决定多久唤醒并批量交付。
* **Bluetooth link 与 Audio route**：蓝牙已连接不代表音频一定走蓝牙，还要看 profile 和系统 audio policy。
* **GPU rendering 与 display present**：GPU 完成绘制只是产生 buffer，真正显示还需要 compositor、HWC、fence 和 panel。
* **HAL capability 与 App permission**：HAL 能力存在只说明硬件可实现，App 仍需通过 framework 权限和策略。

本章结论
--------

各类 HAL 的共同作用是把设备差异收束为稳定合同，不同点在于数据节奏和资源模型。定位移动多媒体与外设问题时，应先识别属于 camera frame、audio stream、sensor event、Bluetooth link 还是 display present，再沿对应 service → HAL → driver → hardware 路径检查。