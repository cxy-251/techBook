第036章：Device Driver Role in Mobile Systems
===============================================

核心知识点
----------

* Driver 是真实硬件进入操作系统资源模型的第一层软件：它理解寄存器、firmware 协议、中断、DMA、buffer、queue 和 power state，再把这些细节包装成 kernel 可管理对象。
* 移动设备的稳定路径通常是 ``App → Framework → System Service → HAL / Daemon → Driver → Hardware``。App 表达能力意图，driver 才真正处理设备控制。
* Driver 的输入有两类：上层提交的控制请求，以及硬件产生的 interrupt、DMA completion、error status、thermal/wakeup event；输出则是硬件命令、kernel event、buffer 完成和错误状态。
* Driver 最核心的五类对象是 register、interrupt、DMA、buffer、queue。Register 决定模式，queue 描述请求，buffer 承载数据，DMA 搬运数据，interrupt 把完成或错误带回系统。
* Kernel driver 能直接参与 MMIO、IRQ、DMA、IOMMU、runtime PM 和 kernel subsystem，路径短但故障影响面大；user-space driver 隔离更好，但需要更严格的 IPC、buffer 和权限合同。
* 移动平台常采用混合模型：kernel driver 保留中断、DMA、电源和底层设备访问；HAL、vendor daemon 或 Driver Extension 负责协议、能力枚举、厂商算法和错误恢复。
* Character、block、network 等设备模型只是底层资源形态；上层通常不会把这些原始设备接口直接暴露给第三方 App。
* Driver 必须服从 kernel resource management：probe/remove、锁、引用计数、地址映射、IOMMU、runtime suspend/resume 和 system suspend 都属于它的生命周期边界。
* Driver fault 的影响范围高于普通 App fault。越界写、错误 DMA、锁死、错误寄存器顺序可能导致设备失联、数据损坏、kernel panic 或权限边界失守。
* Android 主要表现为 Linux kernel/vendor driver + HAL；Apple 公开架构中 IOKit/DriverKit 承担类似设备对象和受控驱动边界，具体 iOS 驱动实现多数属于私有系统。

关键路径
--------

相机预览：

::

   App requests preview
   → Camera framework / service
   → HAL or vendor daemon
   → driver configures power, registers and queues
   → hardware DMA writes frame buffer
   → completion interrupt
   → driver returns buffer / status
   → service callback
   → App sees frame or error

Driver 请求闭环：

::

   probe device
   → runtime resume
   → configure registers
   → map buffer
   → enqueue request
   → start DMA / hardware work
   → interrupt or completion
   → return ownership
   → reuse or recover

故障定位：

::

   capability request fails
   → check service policy
   → check HAL state
   → check driver probe / power
   → check queue and DMA mapping
   → check interrupt / completion
   → check reset and recovery

概念辨析
--------

* **Driver 与 HAL**：Driver 处理 kernel/hardware 资源，HAL 处理 framework 与 vendor 实现之间的能力契约。
* **Register control 与 capability API**：前者是设备级控制细节，后者是 App 可理解的平台语义。
* **Kernel driver 与 user-space driver**：前者权限高、路径短；后者隔离强、可恢复性好，但依赖稳定的代理接口。
* **Buffer existence 与 DMA accessibility**：CPU 能访问 buffer 不代表设备一定能访问，仍要经过 DMA/IOMMU mapping 和同步规则。
* **Driver error 与 App error**：App 参数错误通常应被服务或接口收束；driver 错误可能扩大到整个设备或 kernel。

本章结论
--------

Driver 的本质是把设备寄存器、firmware、IRQ、DMA、buffer、queue 与 power state 转换成操作系统可管理的资源。分析移动硬件能力时，应先沿服务和 HAL 找到真实 driver 边界，再用 probe、power、queue、DMA、interrupt、ownership 和 recovery 检查请求是否闭环。