第163章：Android Deep Path Camera Request
=========================================

核心知识点
----------

* Camera2 拍照主链是 ``App Camera2 → Framework → Binder → CameraService → Camera HAL Session → Driver / ISP / Sensor → Buffer / Metadata → Callback``。
* App 提交的是“请求描述”而不是直接硬件操作：``CaptureRequest`` 描述控制参数和输出 target，``Surface`` 描述数据去向，``CameraCaptureSession`` 描述已配置的 stream 组合。
* ``CameraManager`` 负责枚举/打开设备，``CameraDevice`` 表示已打开 camera，``CameraCaptureSession`` 承载 repeating preview 与 still capture 等 request。
* Session 配置先于 capture。输出尺寸、格式、动态范围、高帧率、RAW/JPEG/preview 等组合必须在设备支持范围内，否则请求不会进入真正采集阶段。
* preview 常用 repeating request，still capture 是一次性 request；二者可以在同一 session 中按硬件管线能力调度。
* Binder 控制面携带 caller UID/PID、package/attribution、callback、Surface/handle 等信息；图像数据不直接塞进 Binder，而是走共享 graphics buffer 与 fence。
* ``CameraService`` 是相机设备和 client 的系统所有者，负责权限、AppOps、前后台/隐私状态、资源占用、client priority、设备断开和错误恢复。
* Camera HAL 把平台 request 转成具体 sensor、ISP、3A、stream 和 buffer 管线。设备厂商的多帧算法、vendor tag 和硬件能力从这里开始出现差异。
* Driver / ISP / Sensor 层负责 sensor 时序、中断、DMA、buffer 填充、曝光/读出和图像处理硬件执行。
* Metadata result 与 image buffer 是两条相关但不同的返回路径；应用应使用 frame number、timestamp 或 request identity 对齐结果。
* Camera 安全检查不是单点：Manifest/runtime permission、AppOps、camera privacy toggle、caller identity、SELinux、设备节点访问都可能成为门禁。
* 排查应区分四类失败：设备打不开、session 配置失败、request 提交/执行失败、metadata 已返回但 image buffer 未到达。

关键路径
--------

::

   App selects camera id
   → openCamera()
   → Binder to CameraService
   → permission / AppOps / resource arbitration
   → CameraDevice opened
   → configure output Surfaces
   → create CameraCaptureSession
   → setRepeatingRequest(preview)
   → capture(still request)
   → Camera HAL processCaptureRequest
   → driver / ISP / sensor
   → capture result metadata + image buffer
   → CameraService / Framework callback
   → App

概念辨析
--------

* **CameraDevice 与 CameraCaptureSession**：Device 表示已打开硬件端点，Session 表示已配置好的 stream 集合和 request 执行环境。
* **CaptureRequest 与 CaptureResult**：Request 是 App 期望的控制参数，Result 是系统/硬件实际执行后的 metadata。
* **Surface 与 Image Buffer**：Surface 是 producer/consumer 的输出端点，真正图像数据在其背后的共享 buffer 中流动。
* **CameraService 与 Camera HAL**：CameraService 管平台身份、资源和 client；HAL 执行厂商硬件管线。
* **权限成功与相机成功**：权限通过后仍可能因 camera 被占用、stream 组合非法、HAL error、driver 超时或 sensor 故障失败。

本章结论
--------

Camera2 深路径应同时追 ``Request`` 与 ``Buffer``：Request 沿 Framework/Binder/Service/HAL 下沉，Buffer/Metadata 沿硬件/HAL/Service/Callback 返回。定位失败时先判断请求停在哪一层，再判断结果在哪个边界没有回来。