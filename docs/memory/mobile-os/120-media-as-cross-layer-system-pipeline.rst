第120章：Media as Cross-Layer System Pipeline
=============================================

核心知识点
----------

* Media pipeline 是移动 OS 最典型的跨层系统：App、Framework、系统服务、codec、图形、音频、相机、文件、安全和硬件会在同一任务中协作。
* 播放方向是 ``File / Network → Demux → Decode → Video Display + Audio Output``；录制方向是 ``Camera / Screen / Microphone → Encode → Mux → Storage / Media Library``。
* Hardware codec 降低 CPU 压力，但仍消耗 DRAM 带宽、显示、音频、网络与热预算；分辨率、帧率、bit depth、HDR、DRM 和并发任务都会影响可用性。
* 视频通过 Surface / Layer / Pixel Buffer 与图形系统连接，关键对象是 buffer ownership、fence、color space、HDR metadata、composition 与 display timing。
* 音频通过 PCM、AudioTrack / AVAudioSession 等与音频系统连接，播放时钟、buffer、路由变化和蓝牙延迟会直接影响音视频同步。
* Camera capture 把媒体系统与 sensor、ISP、HAL / daemon、权限和隐私连接起来；preview、recording、encoder surface 和 metadata 共用一套 buffer / stream 模型。
* File / storage 边界决定容器 finalize、原子保存、媒体库索引、共享、备份和删除语义；写出字节只是保存流程的一部分。
* DRM、camera / microphone permission、sandbox、screen recording policy、protected buffer 共同构成媒体安全边界。
* 后台、低电量、温控、网络切换、蓝牙路由等系统状态会改变媒体链中的 codec、buffer、刷新、音频路由和预加载策略。
* 分析媒体问题时，应先确定当前数据方向和资源所有者，再沿具体子管线定位，而不是把“播放器”或“录像器”视为一个封闭模块。

关键路径
--------

播放跨层链：

``App Player → Framework / Media Service → Demux / DRM → Hardware Codec → Video Surface + Audio PCM → Graphics + Audio System → Display + Route``

录制跨层链：

``App Capture Intent → Camera / Microphone / Screen Service → Raw Buffers → Hardware Encoder → Muxer → File System → Media Library``

媒体系统统一检查链：

``Intent → Permission / Lifecycle / Power Policy → Format / Codec Capability → Buffer / Clock → Output / Storage → User-visible Result``

概念辨析
--------

* **Media framework vs codec**：framework 组织资源、状态和工作流；codec 只负责压缩数据与 raw data 的转换。
* **Video pipeline vs graphics pipeline**：视频 pipeline 产生按时间排序的帧；graphics pipeline 决定这些帧如何合成并显示。
* **Audio sync vs video render**：音频提供连续时钟和路由延迟；视频根据该时间轴安排帧显示。
* **Media permission vs DRM**：permission 判断 App 是否可访问设备或用户数据；DRM 判断受保护内容能否解密和输出。
* **Hardware acceleration vs free performance**：硬件 codec 更高效，但仍受内存带宽、热、功耗和并发资源限制。

本章结论
--------

媒体系统应作为跨层资源协作模型阅读：``数据从哪里来 → 谁拥有 buffer → 谁决定时间 → 谁执行 codec → 谁控制显示/声音 → 谁保存结果 → 哪些策略可以阻断路径``。掌握这条模型后，黑屏有声、音画漂移、HDR 异常、录制掉帧和保存失败都能落回明确系统边界。