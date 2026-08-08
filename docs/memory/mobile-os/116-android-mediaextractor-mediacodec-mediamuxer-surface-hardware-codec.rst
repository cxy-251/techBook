第116章：Android MediaExtractor, MediaCodec, MediaMuxer, Surface, Hardware Codec
=============================================================================

核心知识点
----------

* Android 低层媒体主链是 ``MediaExtractor → MediaCodec → Surface / ByteBuffer → MediaMuxer``；AudioTrack、Camera、SurfaceFlinger 等会在不同任务中接入这条主链。
* MediaExtractor 负责 data source、track format、sample data、sample time 与 sample flags；输出仍是压缩 sample。
* MediaCodec 是统一 encoder / decoder 状态机。Decoder 把压缩 sample 变成 raw frame / PCM，encoder 把 raw frame / PCM 变成压缩 sample。
* MediaCodec 的关键状态是 configure、start、input/output buffer 流转、format change、EOS、stop、release。状态错误与 buffer 所有权错误是常见故障源。
* 视频优先使用 Surface 作为 decoder output 或 encoder input，可把 GraphicBuffer / native buffer 直接交给 GPU、SurfaceFlinger 或硬件 codec，减少 CPU 拷贝。
* MediaMuxer 只接受已经编码好的 sample，并要求先添加 track、start，再按正确 presentation timestamp 写 sample，最后 stop / release 完成容器。
* Hardware codec 能力受 MIME、profile、level、resolution、frame rate、bit depth、color format、secure playback 和 vendor 实现限制；同一代码在不同设备上可能走不同组件。
* Codec2 / OMX 等属于 MediaCodec 后端实现边界。App 应依赖公开 API、codec capability 与实际输出 format，而不是绑定私有组件细节。
* Camera 可把帧送入 encoder input Surface，decoder 可把帧送入 SurfaceFlinger，音频 decoder 可把 PCM 送入 AudioTrack；因此 MediaCodec 是媒体、图形、相机和音频之间的重要交汇点。

关键路径
--------

Android 播放：

``Data Source → MediaExtractor → Encoded Sample → MediaCodec Decoder → Surface / Audio PCM → SurfaceFlinger / AudioTrack``

Android 转码：

``MediaExtractor → Decoder → Surface / Raw Buffer → GPU / Processing → Encoder → Encoded Sample → MediaMuxer``

Android 录像：

``Camera Surface / Audio PCM → MediaCodec Encoder → Encoded Sample → MediaMuxer → File``

概念辨析
--------

* **MediaExtractor vs MediaCodec**：Extractor 解析容器并读 sample；Codec 处理压缩语法。
* **MediaCodec vs MediaMuxer**：Codec 负责编解码；Muxer 负责容器写入。
* **Surface output vs ByteBuffer output**：Surface 更适合显示和零拷贝图形链；ByteBuffer 更适合 CPU 可见处理。
* **Codec capability vs codec name**：组件名称只是实现标识，真正决定可用性的还是 format capability 与运行时配置。
* **EOS vs stop**：EOS 表示数据流结束；stop 是关闭 codec 执行状态，两者语义不同。

本章结论
--------

Android 媒体问题应按数据所有权排查：``Extractor 是否给出正确 sample → Codec 是否正确消费/产生 buffer → Surface / Buffer 是否被及时释放 → Muxer 是否收到单调时间戳``。设备差异主要集中在 codec capability、图形 buffer 约束和 vendor 后端。