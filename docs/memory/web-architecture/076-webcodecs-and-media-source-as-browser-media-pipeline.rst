WebCodecs and Media Source as Browser Media Pipeline
====================================================

核心知识点
----------

* 浏览器媒体不是单一 API，而是一条 ``network → container/demux → decode → buffer → clock → render/audio output`` 的持续管线。
* 普通 ``<video>`` / ``<audio>`` 把大部分下载、解复用、解码、同步和播放控制交给浏览器；高级 API 用于接管其中部分责任。
* Media Source Extensions（MSE）允许 JavaScript 向 ``SourceBuffer`` 追加媒体分片，常用于 DASH/HLS 类自适应流媒体、分段缓存和自定义缓冲策略。
* WebCodecs 更直接暴露 ``VideoDecoder``、``VideoEncoder``、``AudioDecoder``、``AudioEncoder``、``VideoFrame`` 等低层对象，适合编辑、实时处理、远程桌面、云游戏和自定义媒体管线。
* 媒体数据必须携带时间语义。timestamp、duration、decode order、presentation order、音画时钟和播放速率决定帧何时可见。
* 解码器/编码器存在内部队列；生产速度高于消费速度时必须做背压、丢帧、降采样或暂停输入，否则延迟和内存会持续增长。
* 硬件编解码能力依赖 codec、profile、level、分辨率、色彩格式、平台驱动和浏览器实现；“支持 H.264/AV1”不能替代具体 capability 检测。
* 媒体故障可能跨越网络、CORS、manifest/container、codec、MSE append、DRM、autoplay、设备输出和渲染边界，不能只从播放器 UI 判断原因。
* 当应用接管低层媒体管线后，也接管了更多资源释放、帧关闭、队列控制、同步、错误恢复与降级责任。

关键路径
--------

浏览器默认播放：

``URL → Network/Cache → Container/Demux → Decoder → Media Buffer → Media Clock → Video Render + Audio Output``

MSE：

``Application Fetch/ABR → media segments → SourceBuffer.appendBuffer → Browser Demux/Decode → Media Element Clock → Output``

WebCodecs：

``EncodedChunk → Decoder Queue → VideoFrame/AudioData → Application Processing → Canvas/WebGPU/MediaStream/Encoder → Output``

分析时依次检查：输入字节是否正确 → container/codec 是否兼容 → 队列和 timestamp 是否合理 → 是否发生 backlog/丢帧 → 输出路径是否被策略或设备阻断。

概念辨析
--------

* **MSE ≠ 解码器 API**：MSE 主要让应用喂入媒体分片，解复用和解码仍由浏览器媒体栈承担。
* **WebCodecs ≠ 完整播放器**：它提供编解码原语，容器解析、网络、同步、渲染和 UI 仍由应用组合。
* **硬件加速可用 ≠ 所有设备性能一致**：实际支持受 codec/profile/分辨率/功耗和驱动影响。
* **数据已下载 ≠ 帧可播放**：还要经过解复用、解码、时间排序、缓冲和渲染。
* **队列变长 ≠ 吞吐更高**：持续 backlog 通常意味着系统延迟正在扩大。

本章结论
--------

高级 Web 媒体架构的核心不是“调用哪个播放器 API”，而是明确每一段管线的所有者。MSE 把媒体分片输入交给应用，WebCodecs 把编解码控制进一步下放；随之必须显式处理时间、背压、设备能力、资源生命周期和跨层错误恢复。