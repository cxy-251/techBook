第115章：Decode, Encode, Render, Mux, Demux
===========================================

核心知识点
----------

* Demux 负责从容器中读出 track、压缩 sample、时间戳、关键帧与格式描述；它不负责解码。
* Decode 把压缩视频或音频 sample 还原为 raw video frame 或 PCM；进入 raw frame 后，内存带宽、像素格式和 buffer 生命周期成为主要成本。
* Render 把 decoded frame 送入 Surface、Layer、Texture、Pixel Buffer 等显示边界，并按 presentation timestamp、VSync 和 playback clock 决定何时可见。
* Encode 把 raw frame / PCM 压回 H.264、HEVC、AV1、AAC 等码流，bitrate、profile、GOP、keyframe interval 和 rate control 会影响质量、文件大小与延迟。
* Mux 把已经编码完成的 audio / video sample 按 track 和时间戳写入 MP4、MOV、WebM 等容器；muxer 不负责压缩 raw frame。
* Transcode 需要 decode + 处理 + encode，成本最高；remux / rewrap 只改变容器组织，不改变压缩内容，通常更快且无重新编码损失。
* 移动端应尽量让视频帧通过 Surface / native buffer / pixel buffer 在 decoder、GPU、encoder、compositor 之间共享，减少 CPU 侧大块拷贝。
* seek、预览、导出、录制都可以用同一组阶段解释，差别只在从哪一段进入、在哪一段退出。

关键路径
--------

播放：

``Container → Demux → Encoded Sample → Decode → Raw Frame / PCM → Render / Audio Output``

带滤镜导出：

``Container → Demux → Decode → Raw Frame → GPU / Filter / Composite → Encode → Encoded Sample → Mux → Output File``

重封装：

``Container A → Demux → Encoded Sample → Mux → Container B``

概念辨析
--------

* **Demux vs decode**：demux 拆容器；decode 解压码流。
* **Render vs encode**：render 面向显示；encode 面向生成新的压缩码流。
* **Mux vs encode**：mux 组织已编码 sample；encode 生成 sample。
* **Transcode vs remux**：transcode 改变编码内容并重新压缩；remux 只换容器或 track 组织。
* **ByteBuffer path vs Surface path**：ByteBuffer 便于 CPU 直接读写；Surface path 更适合硬件 codec、GPU 和 compositor 之间的低拷贝传递。

本章结论
--------

判断媒体任务成本时，先问是否需要产生 raw frame。只要进入 ``Decode → Raw Frame → Encode``，就进入高带宽、高功耗路径；若压缩 sample 可直接复用，应优先停留在 ``Demux → Mux`` 层。