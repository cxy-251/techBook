第122章：Camera Sensor, Lens, ISP, Buffer, Exposure, Focus, Image Pipeline
=========================================================================

核心知识点
----------

* Sensor 把光转换成 Raw 数据；Raw 仍包含 Bayer pattern、噪声、黑电平、坏点和镜头相关误差，不等于最终 JPEG / HEIF。
* Sensor 的关键约束包括 pixel array、bit depth、exposure time、gain、rolling shutter 与 readout time；它们共同决定动态范围、噪声、运动模糊和最大帧率。
* Lens 系统决定视角、进光、对焦和光学稳定。Focus motor、OIS、固定/可变光圈都属于真实机械和光学约束。
* ISP 把 Raw 变成可显示或可编码图像，典型阶段包括 demosaic、denoise、lens correction、HDR、color correction、tone mapping、sharpening。
* 3A 是 AE、AF、AWB 的闭环控制。它基于连续帧统计与硬件状态，持续调整曝光、焦点和白平衡。
* Camera buffer/stream 是硬件管线与 Framework 的数据合同。buffer 数量、格式、分辨率、fence 和 consumer 速度决定吞吐与 backpressure。
* Preview、photo、video 可以共享 sensor/ISP，但通常使用不同 stream、分辨率、帧时长和处理质量目标。

关键路径
--------

基础成像：

``Light → Lens → Sensor Exposure / Readout → Raw Bayer → ISP → YUV / RGB / JPEG-like Output → Buffer Queue → Framework Consumer``

3A 控制闭环：

``Preview Statistics → AE / AF / AWB Decision → Exposure / Gain / Lens Position / White Balance → Next Frame → Metadata Feedback``

多输出 session：

``Capture Request → Sensor / ISP → Preview Stream + Photo Stream + Video Stream → Surface / Image Buffer / Encoder``

概念辨析
--------

* **Raw vs final image**：Raw 是近传感器数据；最终图像已经过 ISP、色彩和压缩处理。
* **Exposure time vs frame time**：曝光时间必须落在帧周期和 sensor readout 约束内；长曝光会压缩可用帧率。
* **OIS vs EIS**：OIS 通过镜片或 sensor 物理补偿；EIS 通过裁切、运动估计和数字变换补偿。
* **Sensor capability vs stream capability**：Sensor 能读出某模式，不代表系统允许任意多 stream 组合同时使用。
* **Buffering vs latency**：更多 buffer 提高抗抖动能力，也会增加排队和内存占用。

本章结论
--------

相机 API 的上限由光学、Sensor readout、ISP 预算和 buffer 管线共同决定。理解一帧的最小模型是 ``Lens → Sensor → ISP → Buffer → Framework``，理解连续相机行为还必须加入 ``3A feedback`` 和 stream backpressure。高分辨率、高帧率、HDR、RAW、夜景等能力本质上都是这几类硬件与带宽约束的组合结果。