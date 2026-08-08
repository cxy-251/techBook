第128章：Camera Hardware, Algorithm, Media, Privacy, UX Integration
===================================================================

核心知识点
----------

* Camera 是硬件、算法、图形、媒体、存储、安全、功耗和 UX 同时交汇的综合子系统。
* 一个 camera session 可以同时扇出 preview、recording、photo、analysis 等多条 stream；每条 stream 进入不同消费者和系统子管线。
* 算法管线不仅占用 ISP，还会使用 CPU、GPU、NPU/DSP、DRAM 带宽和多帧 buffer；画质提升会转化为持续算力和热预算。
* Camera 与 Graphics 的连接点是 preview Surface / Layer；用户看到的取景延迟由 sensor 帧率、buffer queue、composition 和 display refresh 共同决定。
* Camera 与 Media 的连接点是 encoder input；录像需要把视频帧、音频帧、timestamp、metadata 送入 codec 和 muxer，再完成容器 finalize。
* Camera 与 Storage / Media Library 的连接点是最终资产发布；文件写完不等于用户已能在相册看到，仍需完成容器收尾和媒体库登记。
* Camera 与 Security 的连接包括 permission、caller identity、session ownership、privacy indicator、foreground policy 与受保护内容边界。
* 长时间高分辨率录像会持续消耗 sensor、ISP、codec、DRAM、display 和 storage，系统可能因 power/thermal 降低帧率、分辨率、HDR、稳定或直接中断能力。
* UX 是系统状态的投影：取景器、对焦框、快门延迟、保存完成、隐私指示、发热和掉帧都能映射到具体责任层。

关键路径
--------

跨子系统录像：

``App → Camera Framework → System Camera Service → HAL / Sensor / ISP → Recording Stream → Video Encoder → Muxer + Audio → File → Media Library``

预览：

``Camera Preview Buffer → Surface / Layer → Window Compositor → Display → User-visible Viewfinder``

持续系统约束：

``Camera + ISP + Codec + Display + Storage Load → Power / Thermal Policy → Keep Quality / Reduce FPS / Reduce Resolution / Disable Feature / Stop Session``

安全与用户可见性：

``Permission + Active Session → System Policy → Privacy Indicator / App State → User-visible Trust Signal``

概念辨析
--------

* **Camera pipeline vs media pipeline**：camera 负责产生图像帧；media 负责编码、同步、mux 和保存。
* **Preview success vs recording success**：预览正常只证明显示流工作；编码、音频同步、mux 和文件发布仍可能失败。
* **File written vs media visible**：文件落盘后还可能等待 finalize、MediaStore/Photos 登记和索引发布。
* **Image quality vs system sustainability**：短时最高画质不等于长时间可持续；热状态会改变系统可用预算。
* **App camera UI vs system camera state**：UI 是产品状态，真实硬件占用和隐私状态由系统 session 与 policy 决定。

本章结论
--------

Camera 是移动 OS 跨层能力模型的缩影。完整判断链应是 ``硬件采集 → 算法处理 → Buffer 分流 → Graphics / Media / Storage → Permission / Privacy → Power / Thermal → UX``。任何相机现象都应先找到它落在哪条子管线，再检查该子管线的资源和策略边界，而不是把问题统一归到“相机模块”。