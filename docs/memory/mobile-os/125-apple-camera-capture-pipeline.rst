第125章：Apple Camera Capture Pipeline
======================================

核心知识点
----------

* Apple 相机公开路径可按 ``App → AVFoundation → System Media Service / Daemon → Driver / ISP / Sensor → Sample / Photo Result`` 理解。
* ``AVCaptureSession`` 是会话图所有者；``AVCaptureDevice`` 表示设备；``AVCaptureInput`` 把设备接入会话；``AVCaptureOutput`` 表示结果端。
* App 配置的是公开 session graph，不直接控制 sensor。真正设备打开、buffer 分配和硬件调度由系统侧完成。
* ``beginConfiguration / commitConfiguration`` 是配置事务边界；配置合法性和运行期稳定性要分开判断。
* 连续视频帧通常以 ``CMSampleBuffer`` 携带时间与格式语义，以 ``CVPixelBuffer`` 携带像素数据；这些对象连接 AVFoundation、Core Media、Core Video、编码和图像处理路径。
* ``AVCapturePhotoOutput`` 面向高质量照片结果；``AVCaptureVideoDataOutput`` 面向 App 可读帧；``AVCaptureMovieFileOutput`` 或 ``AVAssetWriter`` 可承担录像路径。
* Route/device format、focus、exposure、system pressure、interruption 和 runtime error 都可能改变已经建立的 capture session。
* Apple 的 ISP、daemon、驱动和多帧算法大量属于私有实现；工程分析应以公开对象、回调、错误和可观察状态为证据边界。

关键路径
--------

会话建立：

``Authorization → Select AVCaptureDevice → AVCaptureDeviceInput → AVCaptureSession + Outputs → commitConfiguration → startRunning``

视频帧：

``Sensor / ISP → System Media Service → AVCaptureVideoDataOutput → CMSampleBuffer → CVPixelBuffer → App / Encoder / Renderer``

拍照：

``AVCapturePhotoOutput.capturePhoto → System Capture Pipeline → Photo Processing → Delegate Result + Metadata → Save``

概念辨析
--------

* **AVCaptureSession vs AVCaptureDevice**：session 管图；device 表示某个摄像设备。
* **Preview layer vs photo output**：preview 服务取景显示；photo output 服务高质量成片，两条输出目标不同。
* **CMSampleBuffer vs CVPixelBuffer**：前者包含时间/格式/附件语义；后者主要承载像素内存。
* **Configuration error vs runtime interruption**：前者是图不合法；后者是已运行会话因资源、系统状态或媒体服务变化被打断。
* **Public API vs private pipeline**：可以确认公开对象和行为，不能把私有 daemon / ISP 细节当作稳定接口。

本章结论
--------

Apple 相机应按 session graph 和 sample flow 阅读：``AVFoundation 表达意图 → 系统服务持有设备 → 底层产生 frame → Core Media / Core Video 返回时间化 buffer``。定位问题时先检查权限与会话图，再看 interruption / pressure / runtime error，再看 sample、timestamp 和下游编码或显示。