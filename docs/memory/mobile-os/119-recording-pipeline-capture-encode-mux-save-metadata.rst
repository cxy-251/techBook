第119章：Recording Pipeline Capture, Encode, Mux, Save, Metadata
===============================================================

核心知识点
----------

* Recording pipeline 把 camera / screen / microphone 等实时采集源转换为可播放、可保存、可索引的媒体文件。
* 录制主链包含采集、预处理、编码、mux、文件 finalize、媒体库登记六个阶段；每段都有独立失败边界。
* Camera 输出图像 buffer，screen capture 输出显示帧，microphone 输出 PCM；三者权限、时间戳来源、格式和资源所有权不同。
* Video encoder 接收 Surface / pixel buffer，audio encoder 接收 PCM。实时录制更适合硬件 Surface / buffer 路径，减少 CPU 拷贝。
* Encoder backpressure 表示下游处理速度跟不上输入速度。视频可通过降帧、降低质量或调整 bitrate 缓解；音频连续性通常更难容忍丢样。
* 音视频必须绑定到可比较的时间基准。录像中常以连续音频时钟或统一 monotonic 时间线维持同步，并对 camera frame drop、audio drift 做补偿。
* Muxer 需要在 track format 已确定后写入 sample，并保持每条 track 的时间戳有效；停止录制时必须正确 finalize 容器，否则文件可能损坏或时长异常。
* rotation、location、HDR、color、creation time 等 metadata 需要在容器或媒体库层正确保存，错误 metadata 会产生方向、色彩、隐私或索引问题。
* “文件写成功”不等于“用户可见”。Android MediaStore、Apple Photos 等还需要合法授权和资产登记，才能进入系统媒体库。

关键路径
--------

录像：

``Camera / Screen + Microphone → Capture Session → Raw Frame / PCM → Video + Audio Encoder → Encoded Samples → Muxer → File Finalize → Media Library``

带 GPU 处理的视频录制：

``Camera Frame → GPU Filter / Composite → Encoder Input Surface → Video Encoder → Muxer``

保存闭环：

``Temporary / App File → Finalize Container → Commit to MediaStore / Photos → Media Index / Asset → User Visible``

概念辨析
--------

* **Capture vs encode**：capture 产生原始图像或 PCM；encode 把原始数据压缩成码流。
* **Encoder backpressure vs storage slow**：backpressure 可发生在 codec 队列；storage slow 发生在 mux/file 写入，两者都可能最终造成丢帧。
* **Mux complete vs file visible**：容器完整只说明文件可播放；媒体库登记决定系统相册是否能看到。
* **Video timestamp vs audio timestamp**：来源可能不同，必须转换到共同时间基准后才能同步。
* **Metadata vs encoded sample**：metadata 描述方向、颜色、位置等语义；encoded sample 承载压缩媒体内容。

本章结论
--------

录制问题应按 ``采集是否有数据 → encoder 是否持续消费 → sample 时间戳是否稳定 → mux 是否完整 finalize → 媒体库是否成功登记`` 排查。用户看到的一个“录像文件”，实际上是实时硬件链、媒体时间线、文件系统与权限系统共同产物。