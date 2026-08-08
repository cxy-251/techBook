第031章：Interrupt, DMA, Device Driver, Hardware Event
======================================================

核心知识点
----------

* Interrupt 是硬件把“状态已变化”送入 Kernel 的入口；中断本身通常只通知事件到达，完整业务语义由 Driver、Kernel 子系统和用户态服务继续构造。
* Hard IRQ 路径应尽量短，只确认事件、清除状态并安排后续工作；耗时处理通常移到 threaded IRQ、softirq、workqueue、NAPI 或设备子系统 worker。
* DMA 让设备直接与内存交换大块数据，适合 camera frame、audio PCM、network packet、storage block 和 graphics buffer；CPU 主要负责配置、同步和状态管理。
* DMA 路径必须区分 CPU virtual address、physical address 与 device/DMA address；IOMMU 可进一步限制设备能访问的物理页范围。
* Buffer ownership 是高速设备正确性的核心。必须明确当前 buffer 属于 device、driver、service 还是 consumer，并用 fence/completion/queue 状态决定何时允许下一方访问。
* Device Driver 管理寄存器、firmware 协议、buffer、ring/descriptor queue、中断与错误状态，把硬件控制面包装成 Kernel object 和受控用户态接口。
* Queue 深度是吞吐、延迟、功耗与内存占用之间的取舍。深队列提高流水线吞吐，但会增加交互延迟、取消成本和 buffer 占用。
* Touch、Camera、Audio、Network 的共同骨架都是“Hardware → Interrupt/DMA → Driver → Kernel subsystem → System Service → Framework → App”，只是数据量和实时性不同。
* App 看到黑帧、爆音、丢包或输入迟滞时，应依次检查 IRQ、completion、buffer queue、用户态 service 消费和最终回调，而不是直接把现象归因于 App。

关键路径
--------

触摸事件：

::

   touch controller samples input
   → IRQ
   → driver handler / threaded handler
   → input subsystem event
   → system input service
   → target window
   → App callback

相机帧：

::

   sensor / ISP
   → DMA writes frame buffer
   → completion interrupt
   → driver marks buffer ready
   → HAL / camera daemon
   → System Service
   → preview / capture consumer

概念辨析
--------

* **Interrupt 与数据传输**：Interrupt 主要报告状态变化；大量数据通常已经通过 DMA 或设备队列完成传输。
* **Hard IRQ 与 deferred work**：Hard IRQ 强调短和确定，延迟工作允许睡眠、复杂解析和用户态交接。
* **DMA 与 CPU copy**：DMA 减少 CPU 搬运，不代表不消耗内存带宽，也不消除 cache、IOMMU 和同步成本。
* **Driver 与 System Service**：Driver 控制寄存器、buffer 和硬件队列；System Service 负责权限、资源所有权、生命周期和用户可见语义。
* **设备完成与 App 完成**：硬件 completion 只表示底层阶段结束，上层仍可能等待服务、Framework、渲染或业务处理。

本章结论
--------

硬件事件进入 App 不是单一函数调用，而是多层状态交接。定位问题时应固定 ``Interrupt → Driver → DMA/Buffer → Kernel subsystem → System Service → Framework → App`` 这条骨架，并检查每个阶段的 completion、ownership、queue 和错误状态。