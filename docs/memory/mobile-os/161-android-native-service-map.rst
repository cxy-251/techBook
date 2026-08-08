第161章：Android Native Service Map
===================================

核心知识点
----------

* Native Service 位于 Framework/System Service 与 HAL/Kernel 之间，常用 C++ 实现，负责图形、音频、媒体、相机、传感器等低延迟能力的会话、队列、buffer 和客户端状态。
* 典型路径是 ``App → Framework → Binder → Native Service → HAL → Driver → Hardware``；部分能力会先经过 ``system_server`` 中的 Java service，再进入 native service。
* Native Service 常把控制面和数据面分离：控制消息走 Binder/AIDL，数据走共享内存、fd、FMQ、BufferQueue、GraphicBuffer、fence 或 DMA buffer。
* ``SurfaceFlinger`` 是系统图形合成器，维护 Layer、Transaction、Buffer、fence 与显示时间线，并与 Hardware Composer 协同完成最终 composition/present。
* 图形问题先区分 producer 是否按时产出 buffer、SurfaceFlinger 是否按时 latch/compose、HWC 是否能使用 device composition、display 是否按时 present。
* ``AudioFlinger`` 偏音频数据面，管理 playback/record track、mixer thread、record thread、effect 和 HAL stream；AudioPolicy 体系更偏路由与用途策略。
* 低延迟音频依赖小 buffer、稳定周期、线程调度和硬件参数匹配；不能只靠提高线程优先级解决格式转换、HAL 或蓝牙链路延迟。
* ``MediaCodecService`` 等媒体服务承接 codec allocation、client lifecycle、buffer 和硬件/软件编解码边界。Android 7.0 之后媒体职责进一步拆进多个受隔离进程以缩小攻击面。
* ``CameraService`` 是相机系统资源所有者，管理 client、device/session、权限与 AppOps、并发占用、stream 配置和 HAL 请求。
* ``SensorService`` 接收 Sensors HAL 事件，管理 client connection、sampling rate、batching、wake-up sensor 和事件分发。
* Native Service 的通用责任是：维护全局硬件会话状态、保护资源所有权、管理高吞吐数据通道、处理 client 死亡，并把 HAL/device 错误转成上层状态。
* HAL 与 Native Service 要分开：Native Service 属于 Android system side，负责平台资源和策略；HAL 属于 system/vendor 边界，负责把标准接口映射到厂商硬件实现。

关键路径
--------

::

   App Framework API
   → Binder control request
   → system_server service or native service
   → client/session/resource state
   → HAL interface
   → vendor implementation
   → kernel driver / hardware
   → shared buffer / event / callback
   → native service
   → App

典型能力映射：

::

   Graphics → SurfaceFlinger → HWC → display
   Audio    → AudioFlinger / AudioPolicy → Audio HAL → codec
   Media    → MediaCodecService → codec HAL / component → hardware codec
   Camera   → CameraService → Camera HAL → ISP / sensor
   Sensor   → SensorService → Sensors HAL → sensor hub / sensor

概念辨析
--------

* **Java System Service 与 Native Service**：前者通常偏 Framework 策略与全局业务状态，后者更接近低延迟资源、buffer 与 HAL。
* **SurfaceFlinger 与 App Renderer**：App 负责生成自身 surface buffer，SurfaceFlinger 负责全局 layer 合成。
* **AudioFlinger 与 AudioPolicy**：AudioFlinger 偏数据处理，AudioPolicy 偏路由、用途和设备选择策略。
* **CameraService 与 Camera HAL**：CameraService 管理客户端和平台资源；HAL 实现具体设备管线。
* **Binder 与 Buffer**：Binder 适合控制和句柄，持续的大规模媒体/图形数据通常走专用共享 buffer 通道。

本章结论
--------

Android Native Service Map 的价值是先确定“谁拥有这项低层资源”。图形看 SurfaceFlinger，音频看 AudioFlinger/Policy，媒体看 codec service，相机看 CameraService，传感器看 SensorService；随后再向 HAL、driver 和 hardware 追踪。