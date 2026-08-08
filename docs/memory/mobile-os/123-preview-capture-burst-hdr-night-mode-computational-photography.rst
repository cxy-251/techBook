第123章：Preview, Capture, Burst, HDR, Night Mode, Computational Photography
=============================================================================

核心知识点
----------

* Preview 是持续帧流问题，目标是低延迟、稳定帧率和所见即所得；Still Capture 是结果生成问题，目标是高质量和完整 metadata。
* Preview 常使用 repeating request、较低分辨率和较浅 buffer；拍照可以切到高分辨率、不同 sensor mode 或更重的 ISP / 后处理路径。
* Burst 是短时间内连续提交多次 capture，并管理多组 buffer、timestamp、3A 状态与内存压力。
* HDR 的本质是合并不同曝光或不同增益的多帧，并完成 alignment、ghost suppression 和 tone mapping。
* Night Mode 用更长总采集窗口换取信噪比，通常需要多帧降噪、运动补偿、手持稳定判断和更长处理时间。
* Computational Photography 把 ISP、CPU、GPU、NPU/DSP、内存带宽与算法模型组合起来，输出能力由硬件与系统 API 共同封装。
* 预览质量、拍照质量、快门延迟、内存、功耗与温控不能同时无限提高，系统持续做多目标取舍。

关键路径
--------

Preview：

``Repeating Request → Sensor / 3A → ISP → Preview Buffer → Surface / Layer → Display → Metadata → Next Request``

Still Capture：

``Shutter → 3A State → High-quality Capture → ISP → Optional Multi-frame Compute → JPEG / HEIF / RAW → Metadata → Save``

HDR / Night：

``Multiple Frames → Exposure / Motion Alignment → Denoise / Merge → Tone Mapping / Detail Recovery → Final Image``

概念辨析
--------

* **Preview frame vs final photo**：预览帧服务交互；成片允许更高分辨率、更长处理和多帧算法。
* **Burst vs HDR**：burst 是连续采集调度；HDR 是利用多帧动态范围差异进行融合，二者可以结合。
* **Zero-shutter-lag vs instant processing**：ZSL 通过保留近期帧降低采集等待，不代表后处理瞬时完成。
* **Night Mode vs long exposure only**：夜景通常是多帧曝光、对齐、降噪和融合，不等于单帧长曝光。
* **ISP processing vs computational photography**：ISP 负责基础实时图像链；计算摄影常把多帧和通用/专用算力进一步加入处理。

本章结论
--------

相机体验来自两个并行循环：``Preview 持续实时输出`` 与 ``Capture 生成高质量结果``。Burst、HDR、Night Mode 和计算摄影都是在 capture 路径上增加时间、buffer 和计算预算来换画质。分析拍照慢、预览卡、HDR 失败或夜景降级时，应分别检查采集时序、buffer、算法负载、功耗和温控，而不是把所有问题归为 Camera API。