第131章：MMIO 与寄存器级硬件控制
================================

本章必须记住
------------

#. MMIO 把设备寄存器窗口放入 CPU 可访问地址空间，但访问对象仍是硬件协议，不是普通 RAM。
#. 寄存器偏移来自设备协议；寄存器基地址来自 Device Tree、ACPI、platform resource、PCI BAR 或其它总线资源。
#. ``struct resource`` 只描述地址范围和类型，不是可直接解引用的内核指针。
#. 驱动应先申请资源所有权，再建立映射，防止多个驱动同时控制同一窗口。
#. ``ioremap()`` 把设备物理地址范围转换成内核可使用的 ``void __iomem *`` token。
#. ``__iomem`` 表示 I/O 地址空间语义，应交给 ``readb/readw/readl/readq``、``write*`` 或对应封装。
#. 直接把 ``__iomem`` 强转为普通指针并解引用，会绕过架构相关的字节序、访问宽度和顺序规则。
#. ``readl()/writel()`` 常用于 little-endian 32 位寄存器；big-endian 设备应使用相应 BE accessor 或驱动封装。
#. 访问宽度属于硬件 ABI；不能用 32 位访问器读一个只允许 8 位访问的寄存器。
#. 64 位寄存器在部分架构上不是单次原子访问，可能要求高低半部的规定顺序和专用 helper。
#. MMIO 读取可能具有副作用，例如 clear-on-read、弹出 FIFO、锁存状态或推进设备状态机。
#. MMIO 写入可能启动 DMA、清中断、复位设备、更新 doorbell 或切换电源状态。
#. 因此驱动不能为了“确认数值”随意重复读取，也不能把所有寄存器都做 read-modify-write。
#. W1C、W1S、write-only、self-clearing 和 reserved bits 必须按手册处理。
#. 对 W1C 状态寄存器做普通 read-modify-write，可能错误清除并发到达的新事件。
#. Reserved bits 应按文档保持规定值，不能把读取值全部原样写回。
#. ``readl_relaxed()/writel_relaxed()`` 只减少部分顺序保证；使用前必须证明与普通内存、DMA 和跨 CPU 状态无依赖。
#. 编译器屏障、CPU memory barrier、DMA barrier 和 MMIO accessor 解决不同层级的重排问题。
#. ``wmb()/rmb()/mb()`` 主要约束普通内存观察顺序，不能单独证明 posted MMIO write 已到达设备。
#. 许多总线允许 posted write：CPU 发出写事务后可继续执行，设备可能尚未真正收到写入。
#. 当后续动作依赖写入已到设备时，常需从同一设备执行安全 read-back，或使用总线规定的 flush 方法。
#. Read-back 的作用可能是冲刷 posted write，返回值本身不一定具有业务意义。
#. 若设备正在 reset，普通 MMIO read 可能失败；某些 PCI 路径会选用可安全失败的配置空间读取作 flush。
#. Doorbell 前的关键顺序通常是：先写普通内存中的描述符，再用 DMA/内存屏障发布，最后写 MMIO doorbell。
#. ``writel()`` 不能替代所有描述符发布屏障；真实要求取决于 coherent memory、设备手册和架构规则。
#. 设备中断 mask 寄存器写入后，驱动若准备释放 IRQ 或断电，通常需要确认写入已生效。
#. 停止 DMA engine 通常是：禁止新工作 → 写 stop → read-back/轮询 idle → 确认不再访问内存。
#. MMIO 映射成功不证明设备已上电、时钟已开启、reset 已释放或 BAR 已 enable。
#. 访问掉电设备的寄存器可能返回固定值、总线错误或导致系统异常，依平台而定。
#. Runtime PM 路径必须先恢复设备可访问状态，再读写寄存器；不能只因 ``struct device`` 存活就访问 MMIO。
#. Platform 驱动常用 ``devm_platform_ioremap_resource()`` 或 ``devm_ioremap_resource()`` 完成资源申请与映射。
#. PCI 驱动常先 enable device、request region，再用 ``pci_iomap*()`` 建立 BAR 映射。
#. Managed mapping 只自动处理映射和资源释放，不会自动停止 DMA、屏蔽中断或撤销上层入口。
#. ``devm_*`` 的释放时点位于设备资源回收阶段；若硬件仍在运行，自动 unmap 仍会造成 use-after-unmap。
#. 驱动私有对象中的 ``void __iomem *base`` 生命周期不能短于任何 IRQ、timer、work、NAPI 或异步请求的访问。
#. 多线程访问同一寄存器状态时，锁保护软件协议；锁本身不保证设备完成或冲刷 posted write。
#. 同一个寄存器被 IRQ 和进程上下文访问时，应明确锁类型、不可睡眠约束和设备侧原子语义。
#. MMIO 读写顺序也可能受设备内部队列影响；CPU 顺序正确不代表设备处理已完成。
#. Polling 状态位必须设置超时，不能无限循环等待硬件。
#. ``readl_poll_timeout*()`` 一类 helper 可表达轮询、间隔和超时，具体可用接口随上下文而异。
#. 原子上下文不能使用会睡眠的轮询 helper；进程上下文应避免无意义 busy loop。
#. Poll 超时后应保存关键寄存器和软件状态，再进入 reset、错误上报或设备离线流程。
#. MMIO 地址不是 DMA 地址；``ioremap`` 结果不能写入设备描述符作为内存 buffer 地址。
#. CPU 访问设备 BAR 的地址空间与设备访问系统 RAM 的 DMA 地址空间必须分开。
#. ``memcpy_toio()/memcpy_fromio()`` 用于 I/O 窗口的数据搬运；普通 ``memcpy`` 不保留 I/O 语义。
#. 端口 I/O 与 MMIO 是不同访问模型；x86 ``inb/outb`` 等接口不能和 ``readb/writeb`` 混用。
#. Mmap 给用户态的设备寄存器窗口会扩大安全与 ABI 风险，需严格限制范围、缓存属性和权限。
#. 用户态映射不能让进程访问未授权寄存器、相邻设备窗口或内核私有控制位。
#. 寄存器 dump 也可能触发 read side effect，调试接口应维护可安全读取清单。
#. 设备移除时应先撤销用户入口，再停止新硬件请求，然后屏蔽 IRQ、停止 DMA、等待异步路径，最后 unmap。
#. ``iounmap`` 只撤销 CPU 映射，不会通知硬件停止访问，也不会释放 PCI/平台资源所有权。
#. Resource release、iounmap、clock disable、reset assert 和 power off 的顺序应按硬件依赖逆序排列。
#. 诊断全 0/全 1 读值时，应检查设备电源、reset、BAR/resource、映射属性、链路和热拔插状态。
#. 诊断写入无效时，应检查寄存器权限、设备状态、posted write、clock、unlock sequence 和字节序。
#. 诊断随机状态时，应检查副作用读取、W1C 错用、并发 RMW、屏障和 teardown 竞态。
#. 精确 accessor、relaxed 语义、ioremap 属性和架构屏障属于版本与架构敏感实现。
#. 稳定源码阅读顺序是：资源来源 → 资源所有权 → ioremap → 寄存器协议 → accessor → 顺序 → PM/reset → teardown。

必背路径
--------

Platform MMIO Probe：

::

   Firmware 描述 reg 资源
   → platform core 形成 struct resource
   → probe 申请资源所有权
   → devm_platform_ioremap_resource
   → 得到 void __iomem *base
   → 打开 clock / regulator
   → 释放 reset
   → readl/writel 初始化寄存器
   → 注册 IRQ 和上层功能

描述符发布与 Doorbell：

::

   CPU 填写 descriptor 地址、长度和控制位
   → DMA/内存屏障保证描述符先可见
   → 更新 producer/valid
   → writel doorbell
   → 必要时 read-back 冲刷 posted write
   → 设备开始读取 descriptor

停止设备：

::

   阻止新请求
   → mask 设备中断
   → read-back 确认 mask 到达
   → 写 stop / disable DMA
   → 轮询 idle 并设置超时
   → synchronize_irq / 停止异步路径
   → 释放 buffer 和 IRQ
   → unmap MMIO
   → 释放 resource / power off

诊断寄存器访问异常：

::

   确认设备对象和资源范围
   → 确认设备已上电、clock 和 reset 状态
   → 检查 mapping 与访问宽度
   → 检查字节序和寄存器副作用
   → 检查 W1C/RMW/保留位
   → 检查 barrier 与 posted write flush
   → 对齐 IRQ、DMA、PM 和热拔插时间线

必须区分
--------

资源地址与 MMIO 指针
   Resource 描述物理窗口；ioremap 后才得到供 I/O accessor 使用的 ``__iomem`` token。

MMIO Barrier 与 Posted Write Flush
   屏障约束访问顺序；read-back 或总线 flush 才用于确认写事务到达设备。

普通内存与设备寄存器
   RAM 保存数据；寄存器读写可能具有副作用并推动硬件状态机。

CPU MMIO 地址与设备 DMA 地址
   CPU 用 MMIO 映射控制设备；设备用 DMA address 访问系统内存。

Managed Resource 与硬件停止
   Devres 可自动释放映射；驱动仍须主动停止 IRQ、DMA 和异步访问。

一句话结论
----------

MMIO 表面是地址读写，实质是带副作用、访问宽度、顺序和完成规则的硬件协议；资源、映射、访问器和 teardown 必须按同一设备生命周期闭合。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 27，IRQ, DMA, MMIO, IOMMU, Cache Coherency, and Hardware Resources；
* AIBook 章节：Chapter 131，MMIO and Register-Level Hardware Control；
* 源文件：``docs/LinuxK/Part_27_IRQ_DMA_MMIO_IOMMU_Cache_Coherency_and_Hardware_Resources/Chapter_131_MMIO_and_Register_Level_Hardware_Control.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_27_IRQ_DMA_MMIO_IOMMU_Cache_Coherency_and_Hardware_Resources/Chapter_131_MMIO_and_Register_Level_Hardware_Control.md>`_。