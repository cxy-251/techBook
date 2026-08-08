第172章：Apple Deep Path Camera Request
=======================================

核心知识点
----------

* Apple Camera Path 的稳定主线是 ``App → AVFoundation → Privacy / TCC → System Media Service → Driver / ISP / Sensor → Core Media / Preview / Capture / Save``。
* App 通过 ``AVCaptureSession`` 描述 capture graph，通过 ``AVCaptureDeviceInput`` 选择设备输入，通过 ``AVCapturePhotoOutput``、``AVCaptureVideoDataOutput`` 等声明输出形态。
* App 提交的是公开配置和资源意图，不直接控制 sensor、ISP、DMA 或 driver；系统服务持有真实设备所有权、并发仲裁和硬件状态。
* Camera 权限需要 usage description 与 TCC authorization；运行时还可能受前后台状态、设备占用、系统相机、热状态和隐私策略影响。
* AVFoundation 把底层帧流转成稳定对象；``CMSampleBuffer`` 表达带时间语义的媒体样本，``CVPixelBuffer`` 表达可在视频、GPU 和编码路径间传递的像素 buffer。
* Preview、photo capture、video capture 和 sample-buffer processing 对延迟、画质、buffer、编码和存储要求不同，不能把所有相机输出视为同一数据路径。
* Apple 私有 media daemon、ISP firmware、sensor protocol 和驱动队列不是 public API 契约；分析时应以 authorization、session notification、runtime error、output callback 等公开证据为主。

关键路径
--------

* 初始化路径：``request camera access → choose AVCaptureDevice → create input/output → configure AVCaptureSession → startRunning``。
* 拍照路径：``capture settings → AVFoundation → media service arbitration → ISP / sensor exposure → processed result / metadata → photo callback``。
* 实时视频路径：``sensor / ISP → system media path → CMSampleBuffer / CVPixelBuffer → delegate queue → App processing / encode / preview``。
* 保存路径与采集路径分离：拿到 photo/video result 后，还可能继续经过 file write、Photos authorization、metadata 和 media library service。
* 失败时按顺序检查：TCC authorization → session graph → interruption/runtime error → device availability/occupation → output callback → encoding/save。
* “预览正常但拍照失败”应优先看 photo output 与 capture result；“有 frame 但 UI 慢”应继续进入 App processing 和 graphics pipeline，而非回到 camera permission。

概念辨析
--------

* ``AVCaptureSession`` 是 capture graph 和会话控制对象；``AVCaptureDevice`` 是公开设备能力入口；二者都不是底层 driver handle。
* ``CMSampleBuffer`` 负责媒体样本、时间和格式；``CVPixelBuffer`` 负责像素内存，两者经常关联但语义不同。
* ``Preview`` 追求低延迟显示；``Photo`` 可能触发更复杂 ISP/计算摄影；``Video`` 还要满足持续帧率和音画同步。
* ``TCC authorization`` 表示用户允许访问 camera；``resource arbitration`` 仍可因为设备被占用或系统状态拒绝 session。
* ``Public API 可见失败`` 可以定位责任边界；``私有 ISP/daemon 实现`` 只能作为受限推断，不应写成稳定接口。

本章结论
--------

Apple 相机是典型的系统代理硬件能力。App 负责声明 session graph、输出类型和处理逻辑，系统负责隐私检查、设备仲裁、硬件执行和 buffer 调度。排查相机问题时应先完成公开链路闭环，再把无法由授权、session、callback、save 解释的部分收束到 media service、driver、ISP 和 hardware 边界。