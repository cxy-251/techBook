第009章：Mobile SoC Component Map
==================================

核心知识点
----------

* SoC 是手机硬件能力的集中承载体。CPU、GPU、NPU、ISP、modem、memory controller、security engine、I/O controller 和低功耗单元共同组成移动平台的硬件执行面。
* CPU 主要承担通用控制、线程执行、系统服务和异常处理；GPU 负责图形与大规模并行计算；NPU 负责适合专用加速器的模型推理；ISP 负责相机 RAW 到可用图像的固定流水线；modem 负责蜂窝基带与无线链路。
* 专用单元并不直接等于 App 能力。硬件能力必须经过 firmware、driver、HAL/daemon、system service 和 framework API 包装，才变成可授权、可仲裁、可返回错误的系统能力。
* DRAM、memory controller、片上互连和 IOMMU 是多个硬件单元的共享数据路径。很多移动性能问题不是算力不足，而是 buffer 搬运、同步或共享带宽成为瓶颈。
* Camera、graphics、AI、video、network 等高吞吐任务会同时争用内存带宽、功耗预算和 thermal envelope；峰值硬件规格不能代表多模块并发时的持续能力。
* sensor、storage 和无线芯片通常通过 I/O controller、DMA、中断和 firmware 协议接入 SoC。CPU 多数时候负责配置与调度，而不是亲自搬运全部数据。
* Security engine、TEE/secure processor、secure element 等安全单元用于保存密钥、执行受保护运算或建立可信边界；App 通常只能通过系统安全服务使用其能力。
* Sensor hub、always-on processor 等低功耗单元可以在主 CPU 深度休眠时持续采样、聚合事件或产生唤醒条件，降低常驻感知的能耗。
* SoC 读法必须同时追踪 control flow 与 data flow：谁发起请求、谁拥有设备、buffer 在哪里、谁生产、谁消费、谁发出完成信号。

关键路径
--------

一次拍照并上传：

::

   app camera request
   → framework / camera service
   → HAL / driver configures sensor and ISP
   → sensor → ISP → DRAM buffer
   → NPU/GPU optional processing
   → display preview / storage write
   → security engine protects data
   → Wi-Fi or modem uploads result

硬件能力进入系统：

::

   physical hardware block
   → firmware / device description
   → kernel driver
   → HAL / daemon
   → system service
   → framework capability
   → app-visible API and errors

性能定位：

::

   user-visible delay
   → identify active hardware blocks
   → inspect shared buffer / memory path
   → inspect queue and synchronization
   → inspect power / thermal state
   → locate compute, bandwidth, or policy bottleneck

概念辨析
--------

* **SoC 与 CPU**：CPU 只是 SoC 中的通用计算单元，手机的图形、影像、AI、通信和安全大量依赖专用硬件。
* **硬件支持与系统开放**：芯片具备某项能力，不代表第三方 App 一定能访问；系统仍会受权限、HAL 能力表、生命周期和平台策略约束。
* **算力瓶颈与数据瓶颈**：计算单元空闲并不代表路径没有瓶颈，DRAM 带宽、buffer copy、fence 或互连拥塞都可能限制吞吐。
* **Control flow 与 data flow**：CPU/服务层通常控制请求和状态，像素、tensor、视频帧等大数据则多由 DMA 和专用单元直接流转。
* **专用硬件与固定功能**：NPU、ISP、DSP 能效高，但适用任务边界更窄；不支持的工作仍需要 CPU/GPU 或软件 fallback。

本章结论
--------

Mobile SoC 应被理解为一组共享内存、功耗和热预算的异构执行单元，而不是一颗“更快的 CPU”。分析移动系统行为时，要先把 App 能力映射到 CPU、GPU、NPU、ISP、modem、安全单元和 I/O 路径，再沿 firmware、driver、service 与 buffer 流定位真正的执行责任和瓶颈。