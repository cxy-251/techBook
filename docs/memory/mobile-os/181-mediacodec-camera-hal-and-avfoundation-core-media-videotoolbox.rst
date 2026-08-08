第181章：MediaCodec Camera HAL and AVFoundation Core Media VideoToolbox
======================================================================

核心知识点
----------

* 移动媒体系统的稳定分析对象不是单个 API，而是 ``capture / demux → buffer → codec → timestamp / sync → render / mux → output`` 的跨层 pipeline。
* Android 的媒体路径常由 ``MediaExtractor / MediaCodec / MediaMuxer / Surface`` 组合完成；codec 具体实现可能来自厂商硬件组件或平台软件组件，能力需在运行时查询。
* ``MediaCodec`` 是低层 codec session；分辨率、帧率、profile / level、color format、secure mode、HDR、低延迟等条件共同决定能否使用目标硬件路径。
* Android 相机路径由 Camera2 / CameraService / Camera HAL 串起 request / result、stream configuration、Surface / buffer 与 vendor ISP；HAL 是系统与厂商影像实现的主要边界。
* Apple 以 AVFoundation 提供相机、播放、录制和导出等高层能力；Core Media 提供 ``CMTime``、``CMSampleBuffer``、format description 等时间与样本模型；VideoToolbox 提供硬件编解码访问入口。
* ``AVCaptureSession`` 负责 capture graph；系统服务负责隐私授权、设备占用和硬件调度；App 接收到的是 sample buffer、photo result、encoded output 或错误状态。
* Android 的设备能力和厂商 pipeline 差异更显式，第三方 App 需要主动处理 codec / camera capability fragmentation；Apple 的硬件、ISP、framework 更集中，公开能力表面更统一，但私有硬件路径可见性更低。
* 视频质量、延迟、功耗和兼容性往往由 buffer 拷贝、硬件 codec、时间戳、format negotiation、相机算法和热策略共同决定。

关键路径
--------

::

   Android recording:
   Camera2 → CameraService → Camera HAL / ISP
       → Surface / Buffer → MediaCodec Encoder
       → Encoded Sample → MediaMuxer → MP4

   Apple recording:
   AVCaptureSession → System Media Service / Camera Hardware
       → CMSampleBuffer / CVPixelBuffer
       → VideoToolbox / AVFoundation Encode
       → Timestamped Sample → Writer / File

   Playback:
   Container → Demux / Reader → Decoder → Surface / Pixel Buffer
       → Graphics Composition → Display

媒体故障优先检查能力发现、权限 / 资源仲裁、buffer 流、codec 配置、timestamp 和输出落盘，而不是直接归咎于“编解码器”。

概念辨析
--------

* ``MediaCodec`` 不等于具体硬件 codec；它是统一会话 API，实际组件可能是硬件或软件实现。
* ``Camera HAL`` 不等于 Camera2 API：Camera2 是 App framework 表面，HAL 是 system ↔ vendor 边界。
* ``AVFoundation`` 不等于 ``VideoToolbox``：前者提供高层媒体 / capture 模型，后者更接近 codec acceleration。
* ``CMSampleBuffer`` 是带时间与格式语义的媒体样本容器，不等于单纯像素 buffer。

本章结论
--------

Android 用公开 codec / camera API + HAL 适配多厂商硬件，能力差异需由运行时查询和降级策略吸收；Apple 用 AVFoundation + Core Media + VideoToolbox 把自有硬件能力包装成更统一的媒体表面。两边的核心都在 session、buffer、timestamp、硬件加速与资源仲裁的交接点。