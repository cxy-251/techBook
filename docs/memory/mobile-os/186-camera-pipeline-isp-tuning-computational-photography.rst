第186章：Camera Pipeline, ISP Tuning, Computational Photography
===============================================================

核心知识点
----------

* OEM 影像差异来自完整 Camera Pipeline，而不是单个 sensor：默认相机、CameraService、Camera HAL、driver/firmware、sensor/lens、ISP、NPU/GPU、算法库和温控共同决定结果。
* HAL3 的稳定模型是“Request → Result Metadata + Buffers”。App 表达 stream 和 capture intent，HAL 把标准控制映射到厂商硬件时序，并回报实际曝光、3A 状态和输出 buffer。
* Camera HAL 是公开 Framework 与 vendor 实现的边界；driver 负责设备控制、DMA、中断和电源，ISP firmware/tuning 负责 RAW 处理、降噪、色彩、tone mapping、sharpening 等。
* 3A 是 AE、AF、AWB 的闭环控制。曝光、对焦和白平衡状态是否稳定，直接影响快门时机、连拍一致性和后续多帧融合质量。
* 计算摄影把多帧采集、运动估计、配准、HDR、降噪、人像分割、夜景和防抖放到 ISP/NPU/GPU/CPU 协同路径中，通常需要更多延迟、内存带宽和热预算。
* 默认相机可使用 vendor tag、私有算法和系统权限；第三方 Camera2/CameraX 只能依赖公开 capability、标准 metadata 和被 OEM 暴露的扩展能力。
* CTS/ITS/HAL compatibility 约束接口正确性和最低能力，不规定 OEM 必须采用相同影像风格或向第三方暴露全部私有算法。

关键路径
--------

标准拍摄：

``Camera App → Camera2/CameraX → CameraService → Camera HAL → Driver/Firmware → Sensor/Lens → ISP → Output Buffer + Result Metadata``

夜景/计算摄影：

``Capture Intent → 3A Converge/Lock → Multi-Frame Capture → Motion Alignment → HDR/NR/Fusion → Tone/Color/Sharpen → Encode``

第三方能力判断：

``CameraCharacteristics → Stream Configuration / Standard Controls / Extensions → Runtime Session → Capture Result``

故障定位：

``Permission/Session → HAL Capability → 3A/Metadata → Buffer/ISP → Algorithm → Thermal/Power``

概念辨析
--------

* **Sensor hardware vs Image quality**：sensor 只是输入源；最终观感由 optics、ISP tuning、3A 和计算摄影共同决定。
* **HAL vs ISP algorithm**：HAL 定义 Framework 与 vendor 的接口；ISP/算法是 HAL 后面的具体成像实现。
* **Standard metadata vs Vendor tag**：前者属于通用 Android 能力语义；后者承载厂商扩展，第三方可用性取决于暴露策略。
* **Preview vs Final photo**：Preview 优先低延迟和连续性；最终成片可以等待多帧融合和更重算法，因此画面风格可能不同。
* **Compatibility vs Quality**：通过兼容性测试证明接口满足平台要求，不代表不同设备拥有相同算法质量和第三方体验。

本章结论
--------

OEM Camera 应按 ``App → Framework/CameraService → HAL → Driver/ISP/Sensor → Algorithm`` 分层阅读。影像差异若只在默认相机出现，优先检查私有算法和能力暴露；若所有 App 都异常，再向 HAL、driver、ISP、sensor 与 thermal 下沉。硬件规格决定上限，HAL 和算法决定能力如何被系统与第三方真正使用。