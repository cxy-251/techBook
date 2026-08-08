第118章：Playback Pipeline Buffering, Seeking, Sync, DRM
========================================================

核心知识点
----------

* Playback pipeline 把 data source、demux、decoder、audio output、video surface、clock、DRM 和播放器状态机组织成连续输出。
* 播放状态通常包括 idle、preparing、buffering、ready、playing、paused、seeking、ended、failed；UI 只是这些底层状态的投影。
* Local file 的主要变量是文件权限、索引与 I/O；network stream 还要处理 HTTP、TLS、CDN、segment、网络切换与缓存。
* Buffering 不只有一层。network buffer、sample queue、decoder queue、audio sink buffer、video frame queue分别吸收不同阶段的速度抖动。
* Seek 不是修改一个时间值，而是重新建立随机访问状态：定位索引 / keyframe、flush decoder、清空旧队列、重建目标时间附近的 audio / video sample，再恢复 clock。
* 音视频同步通常选择稳定 playback clock 驱动。音频常作为主时钟，视频帧根据 PTS 与 clock 差值决定等待、显示或丢弃。
* DRM 把 license、key session、secure decoder、protected buffer、HDCP / 输出保护和屏幕捕获策略加入播放链；受保护内容可能不能进入普通 CPU 可读 buffer。
* HLS / DASH 的 ABR 根据 manifest、带宽估计、buffer health、设备能力和当前网络状态选择码率；高码率不是唯一目标，避免 stall 更重要。
* “转圈”只是统一表象，真实卡点可能在网络、demux、decoder、DRM、audio sink、video surface 或时钟恢复。

关键路径
--------

播放主链：

``Data Source → Buffer / Cache → Demux → DRM / Decrypt → Audio + Video Decoder → Audio Sink + Video Surface → Playback Clock → Output``

Seek：

``Seek Target → Find Index / Keyframe → Flush Old Queues → Refill Samples → Reconfigure / Resume Decoders → Re-anchor Clock → Render``

自适应流：

``Manifest → Segment Download → Throughput + Buffer Health → ABR Decision → Representation Switch → Continuous Decode``

概念辨析
--------

* **Buffering vs downloading**：下载到字节不等于已经有可解码、可播放的 sample。
* **Seek target vs keyframe**：用户目标时间可以是任意点；decoder 往往要从更早的关键帧开始恢复。
* **Playback clock vs timestamp**：timestamp 描述 sample 应在何时呈现；clock 描述当前播放进行到哪里。
* **DRM encryption vs secure output**：拿到解密 key 只是第一步，受保护内容还可能要求 secure decoder、protected buffer 和输出链保护。
* **Bitrate vs playback quality**：码率高不代表体验更好；持续播放还依赖 buffer、网络稳定性、codec 与热预算。

本章结论
--------

播放问题应沿 ``状态机 → 数据源 → sample → decoder → clock → output → DRM / network policy`` 逐层定位。Buffering、seek、同步和 DRM 都不是播放器 UI 行为，而是样本流在不同系统边界重新建立连续性的过程。