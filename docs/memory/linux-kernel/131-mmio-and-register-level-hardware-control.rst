第131章：MMIO 与寄存器级硬件控制
================================

核心知识点
----------

MMIO 是硬件协议入口
   设备寄存器被映射到 CPU 地址空间后，看起来像地址读写，实际仍受寄存器宽度、字节序、副作用、顺序和设备状态机约束。

资源描述与可访问映射分离
   Device Tree、ACPI、platform resource 或 PCI BAR 只给出地址范围。驱动先申请资源所有权，再经 ``ioremap`` 或总线 helper 得到 ``void __iomem *``。

``__iomem`` 不能当普通指针
   MMIO 必须使用 ``readb/readw/readl/readq``、``write*`` 或设备专用封装。普通解引用会绕过架构相关的访问宽度、字节序和顺序语义。

寄存器读写可能有副作用
   读取可能 clear-on-read、弹出 FIFO 或锁存状态；写入可能清中断、启动 DMA、更新 doorbell 或触发 reset，因此不能为调试随意重复访问。

寄存器位语义必须逐项遵守
   W1C、W1S、write-only、self-clearing 和 reserved bits 都不能用普通 read-modify-write 处理。特别是 W1C 寄存器，回写旧值可能清掉并发到达的新事件。

访问宽度和字节序属于硬件 ABI
   一个只允许 8 位访问的寄存器不能用 32 位 accessor；64 位寄存器在部分架构上还需要规定的高低半部顺序。

设备可访问状态先于寄存器访问
   MMIO 映射存在不表示设备已经上电、时钟已开启、reset 已释放或 PCI function 已 enable。Runtime PM 和错误恢复必须先恢复硬件可访问性。

普通屏障与 posted write 完成不同
   内存屏障约束访问顺序；总线 posted write 可能仍未到达设备。依赖写入已生效时，需要安全 read-back 或总线规定的 flush 方法。

描述符发布与 doorbell 是两层协议
   CPU 先写普通内存中的描述符，再用 DMA/内存屏障发布，最后写 MMIO doorbell。Doorbell read-back 不能替代描述符可见性屏障。

锁只保护软件并发
   锁可以串行化 CPU 对寄存器和软件状态的访问，不能证明设备已经执行命令，也不能冲刷 posted write。

轮询必须有超时
   状态寄存器轮询应使用适合当前上下文的 timeout helper。超时后保存软件状态和安全寄存器证据，再进入 reset、离线或错误上报。

MMIO 地址与 DMA 地址属于不同空间
   ``ioremap`` 结果供 CPU 控制设备；DMA API 返回的 ``dma_addr_t`` 供设备访问系统内存，二者不能互换。

Managed mapping 不负责停止硬件
   ``devm_ioremap_resource`` 等只简化资源归还。IRQ、DMA、work 和用户入口仍须在自动 unmap 前主动停止。

Teardown 先让硬件沉默
   移除时先阻止新请求、屏蔽中断、停止 DMA 并等待 idle，再同步所有异步路径，最后 unmap、释放资源和断电。

关键路径
--------

Platform MMIO 初始化：

::

   Firmware 描述 reg
   → platform core 形成 resource
   → 驱动申请资源所有权
   → ioremap 得到 __iomem token
   → 上电、开时钟、释放 reset
   → 使用 I/O accessor 初始化寄存器
   → 注册 IRQ 与上层接口

描述符发布：

::

   CPU 写 descriptor 字段
   → DMA/内存屏障
   → 发布 owner/valid 或 producer
   → 写 MMIO doorbell
   → 必要时 read-back 冲刷 posted write
   → 设备读取 descriptor

安全停止：

::

   阻止新提交
   → mask 设备中断并确认生效
   → 写 stop/disable DMA
   → 轮询 idle 且设置超时
   → synchronize IRQ/work/timer
   → 释放 DMA buffer 和 IRQ
   → unmap MMIO
   → 释放 resource、clock 和 power

概念辨析
--------

* Resource 与 MMIO pointer：前者描述物理窗口；后者是映射后供 accessor 使用的 I/O token。
* Memory barrier 与 posted-write flush：前者约束先后；后者确认写事务已经到达设备。
* 普通 RAM 与设备寄存器：RAM 保存数据；寄存器访问可能推动硬件状态机并产生副作用。
* MMIO address 与 DMA address：CPU 用前者控制设备；设备用后者访问系统内存。
* Devm release 与硬件 teardown：自动释放资源不等于自动停止 IRQ、DMA 和异步访问。

本章结论
--------

MMIO 不是普通内存访问，而是通过地址化寄存器执行硬件协议。正确性取决于资源所有权、专用 accessor、设备状态、顺序与完成规则以及 teardown 顺序同时成立。
