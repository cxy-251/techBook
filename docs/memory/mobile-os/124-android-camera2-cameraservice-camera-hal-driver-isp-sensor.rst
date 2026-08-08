第124章：Android Camera2, CameraService, Camera HAL, Driver, ISP, Sensor
=======================================================================

核心知识点
----------

* Android 相机主路径是 ``App → Camera2 → Binder → CameraService → Camera Provider / Device / Session HAL → Driver / ISP / Sensor``。
* Camera2 使用 request-result 模型：``CaptureRequest`` 描述控制参数和 target Surface，``CaptureResult`` 返回实际帧状态与 metadata。
* ``openCamera`` 解决设备连接与所有权；``createCaptureSession`` 解决 stream 组合；``setRepeatingRequest`` 解决持续预览；单次 capture 可插入 repeating 流。
* CameraService 是系统仲裁中心，负责 caller identity、permission/AppOps、client 生命周期、设备占用、错误隔离和 HAL 连接。
* HAL 对象模型可按 provider → device → session 理解：provider 枚举设备，device 暴露静态能力，session 固定 stream 组合并处理 request。
* HAL 把 Framework request 转成 vendor pipeline 可执行的 sensor、ISP、buffer 与 metadata 操作；底层实现可因 OEM、HAL 接口版本和 SoC 不同而变化。
* Surface 是 Camera 与 Graphics / Media 的交接点；ImageReader、preview Surface、MediaCodec input Surface 会形成不同 consumer 路径。
* 权限、AppOps、SELinux、foreground state 和 privacy policy 都可能在相机访问路径中形成检查点。

关键路径
--------

打开与配置：

``CameraManager.openCamera → Binder → CameraService → Permission / Ownership Check → Camera Provider → Camera Device Session``

预览：

``CameraCaptureSession.setRepeatingRequest → CameraService → HAL processCaptureRequest → Sensor / ISP → Output Buffer → Preview Surface``

结果返回：

``Sensor Timestamp + 3A / Lens / Exposure Metadata → HAL Result → CameraService → Camera2 Callback → App``

概念辨析
--------

* **Camera2 vs CameraService**：Camera2 是 App-facing Framework；CameraService 持有全局设备和 client 状态。
* **CaptureRequest vs CaptureResult**：request 是期望；result 是本帧实际执行状态。
* **Provider vs Device vs Session**：provider 发现设备；device 表示 camera id；session 承载已配置 stream 和请求队列。
* **Open success vs preview success**：设备打开成功不代表 stream、HAL、buffer 和 Surface 已能稳定出帧。
* **Logical camera vs physical camera**：App 可看到一个逻辑 camera id，其背后可以由多颗物理 sensor 协同实现。

本章结论
--------

Android Camera2 的稳定阅读模型是 ``API request → Binder → CameraService 仲裁 → HAL session → Driver / ISP / Sensor → Buffer + Metadata``。排查时先确认设备所有权，再确认 session/stream 配置，再确认 request-result 是否推进，最后进入 HAL、driver 和硬件；不要从黑屏现象直接跳到 Sensor。