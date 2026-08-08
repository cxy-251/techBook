第049章：Android system_server, Native Services, Service Manager
=================================================================

核心知识点
----------

* ``system_server`` 是 Android Java System Service 的核心宿主，集中承载 Activity、Package、Window、Power 等全局控制面服务。
* Native Service 更靠近图形、音频、相机、媒体和传感器等低延迟、高吞吐或硬件强相关路径。
* ``ServiceManager`` 负责 Binder 服务注册与发现：服务端按名字注册 Binder object，客户端按名字取得远端 handle。
* Framework Manager 是 App 侧稳定入口；Binder Service Backend 才执行调用者身份读取、权限检查、状态更新和下游调用。
* Android 服务路径应区分控制面与数据面：``system_server`` 偏策略与全局状态，SurfaceFlinger、AudioFlinger、CameraService 等 native service 更靠近 buffer 和硬件时序。
* 服务可达不等于调用获准。拿到 Binder handle 后仍需经过 permission、AppOps、SELinux、前后台状态和资源仲裁。
* ``system_server`` 的故障影响范围大；native service 独立进程能把部分硬件和媒体故障限制在较小边界内。

关键路径
--------

典型 Android 调用：

``App → Framework Manager → ServiceManager / Binder Proxy → Binder Service → Native Service / HAL → Kernel Driver``

相机预览可拆成：

#. Activity / Window / Power 等服务确定页面、窗口和前台状态。
#. CameraManager 取得相机 Binder 服务引用并发起调用。
#. CameraService 检查调用者、权限、camera owner 和 session 状态。
#. CameraService 调用 Camera HAL/vendor service。
#. Driver 管理设备节点、DMA、interrupt、buffer 和电源状态。
#. 预览 buffer 经 SurfaceFlinger / display pipeline 合成到屏幕。
#. 任一服务死亡时，Binder death/error 传回 client，旧 session 需要关闭或重建。

概念辨析
--------

``system_server`` 与 ``ServiceManager``：前者承载大量服务实现，后者只是 Binder 服务注册/查询基础设施。

``Java System Service`` 与 ``Native Service``：前者通常偏系统策略和 framework 状态；后者通常偏媒体、图形、设备数据流，但不是绝对按语言划分。

``Framework Manager`` 与 ``Binder Backend``：manager 是 SDK 门面，backend 是跨进程后的权威实现。

``Service discovery`` 与 ``Authorization``：查到服务只证明服务可达，不证明调用有权限或资源可用。

本章结论
--------

Android 系统能力由 ``system_server``、native services、Binder 和 HAL 共同组织。定位问题时先确定 API 对应哪个 manager 和 Binder service，再判断控制面还是数据面，最后沿 HAL 和 kernel 路径追踪。