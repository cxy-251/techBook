第127章：Device-Level Imaging Differences
==========================================

核心知识点
----------

* 设备级影像差异首先来自硬件：sensor size、pixel pitch、lens、aperture、OIS、focus system、readout speed 和多摄组合决定原始采集条件。
* 像素数量不能单独代表画质；低光信噪比、动态范围、运动模糊和读出速度通常更受物理尺寸与 sensor 模式影响。
* ISP 与算法调校决定降噪、锐化、白平衡、肤色、HDR、tone mapping 和多帧融合风格，因此相同硬件也能产生明显不同结果。
* Android OEM 可以在 Camera HAL、vendor tag、算法库、CameraX Extensions 和默认相机私有路径中加入差异化能力。
* 默认相机与第三方 App 不一定进入完全相同的算法路径。第三方能力上限取决于平台公开的 stream、metadata、RAW、depth、HDR、extension 和 vendor-facing 接口。
* Apple 的软硬件统一让 device、ISP、Framework 和默认相机策略更集中，但私有算法细节仍不能从公开 API 直接推出。
* HDR、Night Mode、Portrait、Video Stabilization 的差异通常是 sensor、ISP、多帧算法、运动估计、NPU/GPU 与热预算共同结果。
* 对比不同设备时，应按 ``Hardware → ISP/Algorithm → HAL/API Exposure → App Path → Policy`` 分层，而不是按品牌或照片观感直接归因。

关键路径
--------

设备差异形成：

``Scene → Lens / Sensor → ISP + 3A → Multi-frame / ML Algorithms → HAL / Framework Exposure → Default Camera or Third-party App → Final Image``

Android OEM：

``Camera2 Standard Metadata → Camera HAL / Vendor Tags / Extensions → OEM ISP + Algorithms → Public or Private Camera Path``

第三方画质判断：

``Same Device → Compare Default Camera vs Third-party Stream → Check Resolution / HDR / Stabilization / Extension / Metadata → Locate API Boundary``

概念辨析
--------

* **Megapixels vs image quality**：像素数只描述采样网格；画质还受光学、噪声、动态范围和算法决定。
* **Hardware difference vs tuning difference**：硬件决定可获得的信号；调校决定如何解释和处理信号。
* **Standard API vs OEM private path**：标准 API 追求兼容；厂商私有路径可以使用更多未公开参数和算法。
* **Default camera quality vs platform capability**：默认相机结果不能直接代表第三方 App 可获得的公开能力。
* **Photo pipeline vs video pipeline**：照片允许更重的多帧处理；视频更受实时性、编码和温控限制。

本章结论
--------

设备影像差异不是单点原因，而是 ``硬件输入质量 × ISP/算法 × 平台暴露边界 × App 使用路径`` 的结果。比较手机画质或排查第三方相机质量下降时，必须先固定输入硬件，再比较处理链和 API 能力，最后分析默认相机是否使用了第三方无法访问的私有路径。