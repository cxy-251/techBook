第114章：Container, Codec, Frame, Timestamp, Synchronization
============================================================

核心知识点
----------

* Media container 负责组织轨道、样本、索引、时间表和元数据；codec 负责解释或生成压缩码流，两者是不同边界。
* Elementary stream 是单一媒体类型的编码流。Demux 从 MP4、MOV、WebM 等容器中拆出视频、音频、字幕等 track，再把压缩 sample 交给 codec。
* 媒体数据应按阶段理解：file / track 属于容器层，sample / packet 属于 demux 输出，NAL unit / codec frame 属于编码语法层，raw frame / PCM 属于解码输出层。
* PTS 决定何时展示，DTS 决定何时解码，duration 表示持续时间，timebase 负责把整数时间戳换算成真实时间。
* B-frame 等重排序场景会使 DTS 与 PTS 不同，因此“解码顺序”和“显示顺序”不能混为一谈。
* 音视频同步需要把不同 track 的时间戳归一到共同时间轴，再由 playback clock 驱动音频输出和视频帧调度。
* rotation、color space、HDR、封面、地理位置等 metadata 不改变压缩主数据，但会显著影响方向、显示质量、媒体库呈现和隐私。
* 移动系统优先使用硬件 codec 以降低 CPU、功耗和发热，但 profile、level、bit depth、分辨率、DRM 与设备能力共同决定硬件路径是否成立。

关键路径
--------

播放主链：

``Container → Track / Sample Table → Demux → Encoded Sample → Decoder → Raw Video Frame / PCM → Clocked Render / Audio Output``

时间关系：

``Track Timebase → PTS / DTS / Duration → Common Media Timeline → Playback Clock → Audio Output + Video Presentation``

数据层级：

``File → Track → Sample / Packet → Codec Syntax Unit → Raw Frame / PCM → Surface / Audio Buffer``

概念辨析
--------

* **Container vs codec**：container 决定媒体怎样封装；codec 决定音视频怎样压缩与解压。
* **Sample / packet vs raw frame**：sample / packet 通常仍是压缩数据；raw frame 是 decoder 输出，可直接显示或继续处理。
* **PTS vs DTS**：PTS 面向展示顺序；DTS 面向解码输入顺序。
* **Frame vs NAL unit**：frame 是媒体时间上的图像或音频单位；NAL unit 是 H.264 / HEVC 等 codec 内部语法单元，一个 access unit 可包含多个 NAL unit。
* **Metadata vs media payload**：metadata 描述媒体如何解释和呈现；payload 承载主要音视频数据。

本章结论
--------

读取媒体系统时先固定三层：``Container 组织数据 → Codec 转换数据 → Timestamp / Clock 调度数据``。文件可解析、codec 可运行、时间线正确三者缺一不可；方向、HDR、色彩和同步异常通常都可沿这三层与 metadata 边界回溯。