第121章：Camera as a Cross-Layer Mobile Subsystem
===============================================

核心知识点
----------

* Camera 是典型跨层子系统：``App → Framework → System Service / Daemon → HAL / Driver → Sensor / Lens / ISP → Buffer / Metadata``。
* 控制流和数据流方向相反。App 向下提交设备、stream、request 和策略意图；底层向上返回 frame、metadata、状态和错误。
* Lens 负责光学聚焦、焦距、OIS 与对焦机构；Sensor 负责曝光和读出；ISP 负责 demosaic、降噪、HDR、色彩和实时图像处理。
* Framework 暴露的是可请求能力，不是寄存器级硬件控制。真正设备所有权由系统服务持有。
* Preview、still capture、video recording、analysis 共享同一基础采集路径，但目标不同：预览重延迟，拍照重质量，录像重连续时间轴，分析重可读 buffer 与计算吞吐。
* Camera 同时受 permission、foreground state、resource ownership、buffer bandwidth、power、thermal 和 privacy policy 约束。
* Android 与 Apple API 形态不同，但共同角色稳定：framework frontend、系统仲裁层、驱动边界、硬件成像管线、buffer/metadata 返回。

关键路径
--------

打开与取景：

``User Action → Camera Framework → System Service / Daemon → Permission + Ownership Check → HAL / Driver → Sensor / Lens / ISP → Preview Buffer → Surface / Layer → Display``

拍照：

``Capture Request → 3A / Sensor Exposure → ISP / Multi-frame Processing → Photo Buffer + Metadata → Encode → Save``

录像：

``Repeating Camera Frames → Encoder Input → Video Codec → Muxer + Audio Track → File / Media Library``

概念辨析
--------

* **Camera device vs Camera subsystem**：device 是某个逻辑/物理相机；subsystem 还包含服务、HAL、ISP、图形、媒体和安全策略。
* **Control path vs data path**：控制路径下发 request；数据路径返回 buffer 和 metadata。
* **Preview vs capture**：preview 追求连续低延迟；capture 可以等待更重的 ISP、多帧和保存处理。
* **Framework capability vs hardware capability**：Framework 只暴露平台承诺的可用能力；硬件内部可能拥有更多私有能力。
* **Permission vs ownership**：permission 允许请求；ownership 决定当前 session 是否真正持有设备。

本章结论
--------

相机不能按“App 直接读 Sensor”理解。稳定模型是 ``App 表达意图 → 系统服务持有和仲裁设备 → HAL / Driver 执行硬件控制 → Sensor / ISP 产生 frame 与 metadata → 图形、媒体和存储子系统消费结果``。定位相机问题时先判断是控制流失败还是数据流失败，再沿责任边界下钻。