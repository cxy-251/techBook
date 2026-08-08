第039章：Android HAL and Vendor Boundary
========================================

核心知识点
----------

* Android HAL 是 Framework 与 vendor 硬件实现之间的标准能力契约。Framework 依赖接口语义，vendor implementation 负责把语义落到当前设备的 driver、firmware 和硬件。
* 相机、音频、传感器、蓝牙、图形等能力都遵循类似路径：``App → Framework / Service → HAL Interface → Vendor Implementation → Kernel Driver → Hardware``。
* Framework Layer 负责公开 API、权限、生命周期、资源仲裁和错误转换；Vendor Layer 负责设备适配、调参、算法、firmware glue 和设备状态；Kernel Driver 负责设备节点、DMA、interrupt、power 和低层同步。
* HAL 的价值不是消除硬件差异，而是把差异收束成可声明、可调用、可测试、可升级的接口合同。
* HIDL 和 AIDL 都是接口定义机制。Android 8 以后大量 HAL 使用 HIDL；新 HAL 已转向 stable AIDL，跨 ``system.img`` 与 ``vendor.img`` 的接口需要稳定性约束。
* Stable AIDL 通过版本、hash、frozen interface、VINTF stability 和兼容规则限制跨分区接口随意变化；新 client 调用旧 server 的新方法仍要正确处理版本缺失。
* VINTF 把“vendor 提供什么”和“framework 需要什么”变成 manifest 与 compatibility matrix，可用于启动、OTA 和兼容性验证。
* VTS/CTS 等测试体系验证 HAL contract 是否满足平台要求。接口存在不等于实现质量合格，能力声明还必须和真实硬件行为一致。
* Binderized HAL 把 HAL 运行在独立进程中，可以提高故障隔离和权限收束；早期 passthrough 形态则把 vendor implementation 更直接地加载到调用进程中。
* Vendor Boundary 的工程意义是让 framework、vendor image、kernel/vendor module 和设备硬件各自拥有清晰责任，使系统升级不必重新绑定所有设备内部细节。

关键路径
--------

Camera HAL：

::

   Camera2 API
   → CameraService
   → query HAL instance and metadata
   → HAL standard method
   → vendor camera implementation
   → kernel driver / ISP firmware / sensor
   → result metadata and buffer
   → CameraService callback

接口兼容：

::

   framework requirement
   → VINTF compatibility matrix
   ↔ device/vendor manifest
   → HAL version / hash / instance check
   → service registration
   → runtime call

故障定位：

::

   API failure
   → permission / resource arbitration
   → HAL instance availability
   → interface version compatibility
   → vendor process state
   → driver / firmware execution
   → hardware result

概念辨析
--------

* **HAL interface 与 vendor implementation**：前者是系统合同，后者是某个设备对合同的具体实现。
* **Framework error 与 HAL error**：权限、占用等常停在 framework/service；设备 error、timeout、metadata 错误更接近 vendor/driver。
* **HIDL 与 AIDL**：都是接口定义工具；AIDL 已成为新 HAL 的主方向，稳定性由 stable AIDL 与 VINTF 共同约束。
* **VINTF 与 VTS**：VINTF 描述兼容合同，VTS 负责验证实现是否满足合同。
* **API compatibility 与 implementation quality**：接口兼容只保证能对话，不保证画质、延迟、稳定性和功耗一定优秀。

本章结论
--------

Android HAL 的本质是跨 Framework/Vendor 的长期兼容合同。理解硬件能力问题时，应按 Framework 期望、HAL 声明、VINTF 兼容、vendor 实现、driver/firmware 行为逐层定位；只有这条边界稳定，Android 才能在多 SoC、多 OEM 设备上持续升级。