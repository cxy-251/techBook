第190章：Technical Evaluation of Android OEM Systems
====================================================

核心知识点
----------

* OEM 系统应按“平台工程产品”评估：AOSP 基础之上叠加硬件实现、系统服务、策略、算法、生态和更新维护，最终表现为稳定性、流畅度、续航、影像、隐私和生命周期。
* 七个核心维度是：后台策略、权限治理、影像系统、图形与流畅度、电源与温控、更新维护、生态服务。每个维度都必须对应可重复场景和责任链。
* 后台策略不能只看“杀不杀进程”，应同时测试 IM 通知、地图导航、音乐、健康记录、IoT、WorkManager/JobScheduler/FGS、Push 和用户白名单是否形成一致规则。
* 权限策略重点是透明度、可控性和可恢复性：用户能否知道谁访问敏感资源、能否按合理粒度授权/撤销，以及 OEM 附加策略是否过度干预标准 Android 能力。
* 影像评估需要同时观察默认相机与第三方 API。默认相机质量高而第三方能力弱，常说明 vendor algorithm / HAL extension 暴露不充分，而不是纯硬件不足。
* 图形与流畅度应看 frame pacing、触控响应、SurfaceFlinger/HWC 合成、刷新率切换、内存压力和热状态，平均帧率不能代替稳定帧时间。
* 电源与温控是持续负载下的资源分配问题。应观察游戏、录像、上传、导航、充电和低电量场景中的频率、帧率、温度、后台能力与用户体验降级顺序。
* 更新维护应同时看安全补丁、大版本、Mainline、kernel/driver/firmware、OTA 回滚和支持年限；版本承诺只有被持续交付才构成平台能力。
* 厂商账号、Push、云、商店、支付和多设备协同属于生态服务维度；它们既能增强系统体验，也可能增加区域差异和迁移成本。
* 技术评价必须从可观察行为回推 Framework、System Service、OEM Service、HAL、Kernel/Driver，而不是用品牌印象替代证据。

关键路径
--------

统一评估路径：

``Scenario → App Observable Result → Framework API → System Service → OEM Policy/Service → HAL/Kernel/Driver → Hardware/Cloud``

后台测试：

``Screen Off / Doze / Weak Network → Push or Scheduled Work → OEM Policy → Execution Time → Notification / Data Continuity``

流畅度测试：

``Input → Main Thread / Render → Surface / Composition → Display → Frame Time + Touch-to-Display Latency``

持续性能测试：

``Long Workload → CPU/GPU/ISP/Modem Load → Thermal & Power Policy → Frequency/Frame/Quality Degradation → User Result``

更新测试：

``Patch Commitment → Release Cadence → OTA Quality → Driver/Firmware Maintenance → Long-Term Device State``

概念辨析
--------

* **功能多 vs 平台质量高**：功能数量只说明产品表面；平台质量取决于策略一致性、故障恢复、兼容性和长期维护。
* **平均性能 vs 稳定性能**：峰值和平均值不能代表长时间帧稳定、温控降级和电池状态下的体验。
* **默认 App 体验 vs Third-Party Platform Capability**：默认应用可使用厂商私有接口；第三方 API 的稳定能力更能反映平台开放质量。
* **严格后台策略 vs 好续航**：过度限制能降低后台耗电，也会损害消息、导航、健康和 IoT 可靠性；优秀策略需要区分任务价值和用户意图。
* **隐私保护 vs 额外阻断**：更多弹窗和开关不自动等于更安全；关键是授权语义清晰、行为可审计、用户可恢复。
* **更新承诺 vs 更新能力**：承诺是计划；实际补丁频率、OTA 质量、driver/firmware 生命周期才是可验证能力。

本章结论
--------

评价 Android OEM 系统，应统一使用“场景—路径—证据—结果”方法。后台、权限、影像、图形、电源、更新和生态服务都要沿 ``App → Framework → System/OEM Service → HAL/Kernel → Hardware/Cloud`` 定位。真正成熟的 OEM 平台不是某一项跑分或功能突出，而是在不同设备状态和长期生命周期中保持规则清楚、能力稳定、降级可解释、用户可恢复。