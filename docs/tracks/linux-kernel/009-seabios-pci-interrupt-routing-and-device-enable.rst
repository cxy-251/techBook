第九章：SeaBIOS 怎样建立 q35 PCI INTx 路由并打开设备地址解码？
===========================================================

上一章结束时，SeaBIOS 已经为 PCI endpoint 写入 BAR 地址，也为 PCI bridge 写入 I/O、MEM 和 PREFMEM
转发窗口。控制流仍在：

::

   qemu_platform_setup()
   → pci_setup()
   → pci_bios_map_devices() 返回

下一条调用是：

.. code-block:: c

   pci_bios_init_devices();

此时配置空间中虽然已经保存了设备地址，设备还没有被统一打开。PCI function 是否响应 I/O port 或 MMIO 访问，
取决于 ``PCI_COMMAND``；传统 INTx 中断最终进入哪条 IRQ，也需要设备的 interrupt pin、q35 的 pin swizzle、
ICH9 PIRQ 路由和 8259A 触发方式共同一致。

本章沿下面的真实控制流前进：

::

   pci_bios_init_devices()
   → 逐个调用 pci_bios_init_device()
   → 读取 PCI_INTERRUPT_PIN
   → 计算并写入 PCI_INTERRUPT_LINE
   → 按 vendor/device/class 执行设备专用初始化
   → 配置 ICH9 LPC、IDE、SMBus 等条件路径
   → 打开 PCI_COMMAND_IO / MEMORY / SERR
   → 为 bridge 打开 SERR forwarding
   → 释放临时 PCI 资源规划结构
   → pci_enable_default_vga()
   → pci_setup() 返回

本章结束时，PCI设备已经拥有地址，传统INTx路由寄存器与可写的地址解码位也已配置。但IRQ10/11仍被第006章
留下的slave PIC mask遮蔽，主控制流IF也仍为0；“路由已建立”不等于设备中断已经能送达BSP。ATA、AHCI、NVMe、
USB、virtio等SeaBIOS驱动仍未开始扫描设备后面的介质， ``BootList`` 中仍没有具体磁盘，GRUB也没有被读取。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

pci_bios_init_devices 逐个处理已发现的 function
---------------------------------------------

``pci_bios_init_devices()`` 本身很短：

.. code-block:: c

   static void
   pci_bios_init_devices(void)
   {
       struct pci_device *pci;
       foreachpci(pci) {
           pci_bios_init_device(pci);
       }
   }

``foreachpci`` 遍历第七章建立的全局 ``PCIDevices`` 链表。这里不会重新扫描总线，也不会重新判断 function 是否
存在；每个 ``struct pci_device`` 已经保存了 BDF、vendor/device ID、class、header type 和 parent bridge。

每个 function 进入：

.. code-block:: c

   static void
   pci_bios_init_device(struct pci_device *pci)
   {
       u16 bdf = pci->bdf;
       int pin = pci_config_readb(bdf, PCI_INTERRUPT_PIN);
       if (pin != 0)
           pci_config_writeb(bdf, PCI_INTERRUPT_LINE,
                             pci_slot_get_irq(pci, pin));

       pci_init_device(pci_device_tbl, pci, NULL);

       pci_config_maskw(bdf, PCI_COMMAND, 0,
                        PCI_COMMAND_IO |
                        PCI_COMMAND_MEMORY |
                        PCI_COMMAND_SERR);

       if (pci->header_type & PCI_HEADER_TYPE_BRIDGE)
           pci_config_maskw(bdf, PCI_BRIDGE_CONTROL, 0,
                            PCI_BRIDGE_CTL_SERR);
   }

顺序是：

#. 处理传统 INTx 路由；
#. 执行当前设备的专用寄存器配置；
#. 打开统一的 I/O、MMIO 和 SERR 能力；
#. 如果是 bridge，再打开下游 SERR 转发。

这个顺序使设备在地址解码被打开前，已经拥有与平台一致的中断和专用寄存器状态。

PCI_INTERRUPT_PIN 与 PCI_INTERRUPT_LINE 不是同一个概念
----------------------------------------------------

普通 PCI function 配置头中有两个相邻字段：

::

   offset 0x3c  PCI_INTERRUPT_LINE
   offset 0x3d  PCI_INTERRUPT_PIN

``PCI_INTERRUPT_PIN`` 描述设备使用哪个传统 INTx pin：

::

   0  不使用传统 INTx
   1  INTA#
   2  INTB#
   3  INTC#
   4  INTD#

pin 是设备侧的逻辑中断引脚身份。设备声明 INTA#，并不代表它一定进入 CPU 的 IRQ10；中间还可能经过
PCI-to-PCI bridge 的 pin swizzle、q35 root complex 的 PIRQ 映射和 ICH9 LPC 的 IRQ 路由。

``PCI_INTERRUPT_LINE`` 则保存固件最终选择的传统 IRQ 号。SeaBIOS 只有在 ``pin != 0`` 时才写这个字段：

.. code-block:: c

   line = pci_slot_get_irq(pci, pin);
   pci_config_writeb(bdf, PCI_INTERRUPT_LINE, line);

因此：

::

   PIN   回答“设备发出哪根 INTA-D 信号”
   LINE  回答“固件把这条信号路由到哪个传统 IRQ”

现代操作系统可以依据 ACPI、APIC 和 PCI routing 信息重新建立自己的中断路径。这里填写的是 BIOS/传统 PCI
环境需要的初始路由，不是 Linux 运行时最终的中断配置。

q35 怎样把 slot 与 pin 旋转成 IRQ10 或 IRQ11
-----------------------------------------

上一章识别 q35 MCH 时，``mch_mem_addr_setup()`` 已经把函数指针设为：

.. code-block:: c

   pci_slot_get_irq = mch_pci_slot_get_irq;

q35 路径使用的候选 IRQ 数组是：

.. code-block:: c

   const u8 pci_irqs[4] = {
       10, 10, 11, 11
   };

也就是四个逻辑位置最终落到：

::

   index 0 → IRQ10
   index 1 → IRQ10
   index 2 → IRQ11
   index 3 → IRQ11

``mch_pci_slot_get_irq()`` 会把设备的 pin、所在 slot 和经过的 parent bridge slot 共同计入：

.. code-block:: c

   static int
   mch_pci_slot_get_irq(struct pci_device *pci, int pin)
   {
       int pin_addend = 0;
       while (pci->parent != NULL) {
           pin_addend += pci_bdf_to_dev(pci->bdf);
           pci = pci->parent;
       }

       u8 slot = pci_bdf_to_dev(pci->bdf);
       if (slot <= 24)
           return pci_irqs[(pin - 1 + pin_addend + slot) & 3];

       return pci_irqs[(pin - 1 + pin_addend) & 3];
   }

``pin - 1`` 把 INTA-D 的编号 1-4 转成数组索引 0-3。``& 3`` 相当于对 4 取模，使结果始终落在四个
PIRQ 位置中。

bridge 会对下游设备的 INTA-D 做 pin swizzle。一个 endpoint 即使声明 INTA#，经过不同 slot 和 bridge 后，也可能
在根端表现成 INTB#、INTC# 或 INTD#。SeaBIOS 沿 ``parent`` 指针向上累积 slot，正是为了把这段拓扑旋转纳入计算。

因此多个 PCI function 可以共享 IRQ10 或 IRQ11。共享并不是异常；传统 PCI INTx 本来就是电平触发、可共享的
中断机制。中断处理程序收到 IRQ 后，还要读取设备状态寄存器，判断究竟是哪台设备在请求服务。

写 PCI_INTERRUPT_LINE 还不够
---------------------------

把 ``PCI_INTERRUPT_LINE`` 写成 10 或 11，只是把结果记录进设备配置空间。q35 芯片组内部还必须真正把 PIRQ
路由到同样的 8259A IRQ。

这个工作由 ICH9 LPC function 的专用初始化完成。

ICH9 LPC 是 PCI 与传统 PC 外设之间的桥
------------------------------------

SeaBIOS 的设备匹配表包含：

.. code-block:: c

   PCI_DEVICE(PCI_VENDOR_ID_INTEL,
              PCI_DEVICE_ID_INTEL_ICH9_LPC,
              mch_isa_bridge_setup),

q35 使用 ICH9 LPC bridge。LPC 是 Low Pin Count bus，用较少的物理信号承载传统 ISA 风格外设访问。对当前启动路径
来说，这个 PCI function 还承担：

* PIRQ 到传统 IRQ 的路由；
* ACPI PM I/O 基址；
* SCI 配置；
* RCBA 映射；
* PM timer 位置登记。

``pci_init_device()`` 按 vendor/device/class 遍历 ``pci_device_tbl``。匹配到 ICH9 LPC 的 vendor/device ID 后，
调用 ``mch_isa_bridge_setup()``；不匹配的表项不会执行。

PIRQA-PIRQH 被映射到 IRQ10 和 IRQ11
---------------------------------

``mch_isa_bridge_setup()`` 对四个索引循环：

.. code-block:: c

   for (i = 0; i < 4; i++) {
       irq = pci_irqs[i];

       pci_config_writeb(bdf, ICH9_LPC_PIRQA_ROUT + i, irq);
       pci_config_writeb(bdf, ICH9_LPC_PIRQE_ROUT + i, irq);
   }

结果是：

::

   PIRQA → IRQ10
   PIRQB → IRQ10
   PIRQC → IRQ11
   PIRQD → IRQ11

   PIRQE → IRQ10
   PIRQF → IRQ10
   PIRQG → IRQ11
   PIRQH → IRQ11

q35 root complex 与 bridge pin swizzle 决定某个设备落到哪条 PIRQ；ICH9 LPC routing register 再决定这条 PIRQ
进入哪个传统 IRQ。前面写入设备 ``PCI_INTERRUPT_LINE`` 的值和这里的芯片组路由必须一致。

为什么 IRQ10 和 IRQ11 要设置成电平触发
----------------------------------

SeaBIOS 同时构造两字节 ELCR 值：

.. code-block:: c

   elcr[irq >> 3] |= 1 << (irq & 7);

然后写入：

::

   ELCR1 port = 0x4d0
   ELCR2 port = 0x4d1

ELCR 是 Edge/Level Control Register，用来指定传统 IRQ 采用边沿触发还是电平触发。

IRQ10 和 IRQ11 位于第二个字节中。对应位被设为 1 后，两条线路采用 level-triggered。这样一条 IRQ 可以由多个
PCI function 共享：只要任一设备仍保持 INTx 有效，线路就继续维持请求状态。

这和传统 ISA 设备常用的 edge-triggered 不同。边沿触发只记录信号跳变，更适合不共享的旧式 IRQ；PCI INTx
需要电平语义，固件必须把 ELCR 配置一致。

但 ``mch_isa_bridge_setup()`` 没有改8259A的IMR。第006章结束时slave PIC只放行IRQ13，IRQ10和IRQ11仍被
mask；BSP主控制流的IF也仍为0。因此本章只建立设备pin、PIRQ、legacy IRQ与触发方式之间的一致映射，没有发生
设备中断处理、任务切换或线程调度。

PMBASE、SCI 和 RCBA 在同一个 LPC 初始化阶段建立
-------------------------------------------

PIRQ 完成后，``mch_isa_bridge_setup()`` 调用：

.. code-block:: c

   mch_isa_lpc_setup(bdf);

其中写入三组重要寄存器。

第一，设置 ACPI PM I/O 基址：

.. code-block:: c

   pci_config_writel(bdf, ICH9_LPC_PMBASE,
                     acpi_pm_base | ICH9_LPC_PMBASE_RTE);

``acpi_pm_base`` 是 SeaBIOS 当前选择的 ACPI power-management I/O 区域起点。最低使能位告诉 ICH9 让这段
I/O 地址开始响应。

第二，打开 ACPI 控制并选择 SCI IRQ9：

.. code-block:: c

   pci_config_writeb(bdf, ICH9_LPC_ACPI_CTRL,
                     ICH9_LPC_ACPI_CTRL_ACPI_EN);

SCI 是 System Control Interrupt。以后 ACPI 电源事件、定时器或其他平台事件可以通过 SCI 通知操作系统。当前只是
把芯片组基础路由建立起来，Linux 尚未加载 ACPI 表，也没有安装自己的 SCI handler。

第三，设置 RCBA：

.. code-block:: c

   pci_config_writel(bdf, ICH9_LPC_RCBA,
                     0xfed1c000 | 1);

RCBA 是 Root Complex Register Block Address。最低位 ``1`` 表示启用，物理地址是：

::

   0xfed1c000

SeaBIOS 随后把从该地址开始的 16 KiB 加入：

.. code-block:: c

   E820_RESERVED

这样 bootloader 和 Linux 的早期内存管理不会把这段设备寄存器窗口误当成普通 RAM。

最后保存 ACPI PM 控制寄存器位置，并尝试登记PM timer：

.. code-block:: c

   acpi_pm1a_cnt = acpi_pm_base + 0x04;
   pmtimer_setup(acpi_pm_base + 0x08);

默认QEMU构建中 ``CONFIG_PMTIMER=y``，但 ``pmtimer_setup()`` 只有当前timer source仍是PIT时才把 ``TimerPort``
切到这个I/O port；如果前面的KVM clock或其他TSC校准已经建立timer source，它会直接返回。因此调用必然发生，
“SeaBIOS此刻已经切换到PM timer”却不是无条件结论。 ``acpi_pm1a_cnt`` 的赋值不受这项选择影响。

IDE class 的 BAR 被改成传统兼容端口
-------------------------------

设备匹配表还包含一个按 class 匹配的通用 IDE 路径：

.. code-block:: c

   PCI_DEVICE_CLASS(PCI_ANY_ID,
                    PCI_ANY_ID,
                    PCI_CLASS_STORAGE_IDE,
                    storage_ide_setup),

只有当前配置中实际存在 class 为 IDE 的 function 时，这个函数才会运行。它把前四个 BAR 固定成传统 ATA 端口：

.. code-block:: c

   BAR0 = 0x01f0   // primary command block
   BAR1 = 0x03f4   // primary control block
   BAR2 = 0x0170   // secondary command block
   BAR3 = 0x0374   // secondary control block

这些是 PC/AT 兼容 IDE 端口。这样后面的 SeaBIOS ATA 驱动可以使用传统 primary/secondary channel 地址，而不必
只依赖上一章通用资源分配器给出的任意 I/O BAR。

这里仍然没有向磁盘发送 IDENTIFY 命令，也没有读取扇区。当前只是让 IDE controller 的寄存器出现在固件预期的
I/O 地址。

ICH9 SMBus 获得独立的 I/O 区域
----------------------------

设备表对 ICH9 SMBus function 调用：

.. code-block:: c

   ich9_smbus_setup();

它把 SMBus I/O 基址设为：

.. code-block:: c

   acpi_pm_base + 0x100

并在最低位标记这是 I/O BAR：

.. code-block:: c

   pci_config_writel(bdf, ICH9_SMB_SMB_BASE,
                     (acpi_pm_base + 0x100) |
                     PCI_BASE_ADDRESS_SPACE_IO);

随后设置：

.. code-block:: c

   ICH9_SMB_HOSTC_HST_EN

开启 SMBus host controller。

SMBus 与 I2C 接近，平台可以用它连接传感器、SPD EEPROM 和管理设备。QEMU 是否为当前虚拟机挂载具体 SMBus
从设备取决于机器配置。本阶段只打开 host controller；不能据此推断已经读取了真实内存条 SPD。

Intel VGA 的 OpRegion 与保留显存是条件路径
--------------------------------------

如果发现 Intel vendor 且 class 为 VGA 的 function，设备表还可能进入 ``intel_igd_setup()``。

它从 QEMU fw_cfg 查找：

::

   etc/igd-opregion
   etc/igd-bdsm-size

存在 IGD OpRegion 时，SeaBIOS 为其分配内存、复制内容，并把地址写入 Intel 图形设备配置寄存器。存在 BDSM 大小时，
SeaBIOS 为 stolen memory 分配区域并加入 ``E820_RESERVED``。

这是设备配置相关的条件路径。普通 q35 虚拟机可以使用不同 VGA 模型，并不一定存在 Intel IGD 数据，所以正文不能
把这两项写成所有 q35 启动必然发生的步骤。

PCI_COMMAND 决定设备是否响应已经分配的地址
--------------------------------------

专用初始化返回后，SeaBIOS 对每个 function 执行：

.. code-block:: c

   pci_config_maskw(bdf, PCI_COMMAND, 0,
                    PCI_COMMAND_IO |
                    PCI_COMMAND_MEMORY |
                    PCI_COMMAND_SERR);

三个 bit 的含义是：

``PCI_COMMAND_IO``
   允许设备响应落在其 I/O BAR 中的 port I/O 访问。

``PCI_COMMAND_MEMORY``
   允许设备响应落在其 memory BAR 中的 MMIO 访问。

``PCI_COMMAND_SERR``
   允许设备在严重 PCI 系统错误条件下发出 SERR#。

上一章把地址写进 BAR，只是告诉设备“你的窗口起点在哪里”。在对应 command bit 打开前，设备可以保持地址解码
关闭，不响应 CPU 对该窗口的访问。

对实现相应command bit且BAR有效的function，现在地址解码链才完整：

::

   CPU 发出 I/O 或 MMIO 访问
   → host bridge 判断属于 PCI 窗口
   → PCI bridge 根据 base/limit 向下转发
   → endpoint 比较自己的 BAR
   → PCI_COMMAND 允许对应类型的地址解码
   → 访问到达设备寄存器

注意这里没有统一设置 ``PCI_COMMAND_MASTER``。bus mastering 允许设备主动成为 PCI bus master、发起 DMA。SeaBIOS
只会在具体驱动确实需要 DMA 时，通过 ``pci_enable_busmaster()`` 单独开启。因此“设备地址已经可访问”和“设备已经
可以主动 DMA”仍然是两个阶段。

bridge 还要允许下游 SERR 向上传递
-----------------------------

对于 PCI-to-PCI bridge，SeaBIOS额外设置：

.. code-block:: c

   PCI_BRIDGE_CTL_SERR

endpoint 发出的严重错误要经过一层或多层 bridge 才能到达根端。只打开 endpoint 的 ``PCI_COMMAND_SERR`` 不足以
保证错误穿过桥；每座 bridge 还需要允许 SERR forwarding。

普通设备中断 INTx 与 SERR 也不是同一条路径：

::

   INTx  用于正常设备服务请求
   SERR  用于 PCI 系统级严重错误报告

本章配置两者，但 Linux 以后会重新接管错误报告、中断控制器和设备驱动策略。

临时 PCI 资源规划结构在这里释放
----------------------------

所有设备完成初始化后，``pci_setup()`` 执行：

.. code-block:: c

   free(busses);

``busses`` 是上一章分配的临时资源规划数组，内部链表用于计算 BAR 和 bridge window 的大小、对齐与基址。

地址已经写入真实 PCI 配置空间后，这份临时计算结构不再需要。永久状态现在分别位于：

* 设备的 BAR；
* bridge 的 base/limit；
* ``PCI_INTERRUPT_LINE``；
* ICH9 LPC routing register；
* ``PCI_COMMAND``；
* SeaBIOS 的 ``PCIDevices`` 身份与拓扑链表。

释放的是规划过程，不是删除 PCI 设备，也不会清掉刚写入的配置寄存器。

pci_enable_default_vga 确保存在可达的主显示设备
-------------------------------------------

``pci_setup()`` 的最后一步是：

.. code-block:: c

   pci_enable_default_vga();

它先遍历所有设备并调用 ``is_pci_vga()``。一个 VGA function 被认为已经可用，需要同时满足：

#. class 是 ``PCI_CLASS_DISPLAY_VGA``；
#. ``PCI_COMMAND_IO`` 已开启；
#. ``PCI_COMMAND_MEMORY`` 已开启；
#. 从该设备到 root 的每座 bridge 都设置了 ``PCI_BRIDGE_CTL_VGA``。

如果已经找到满足条件的 VGA，SeaBIOS 直接采用，不再修改其他设备。

如果没有，则寻找第一个 VGA class function，打开它的 I/O 和 MMIO decode，并沿 ``parent`` 指针向根端逐层设置：

.. code-block:: c

   PCI_BRIDGE_CTL_VGA

这个 bridge bit 允许传统 VGA 地址穿过桥。VGA 兼容访问不仅包含普通 BAR，还涉及历史固定范围，例如 VGA I/O port
和 ``0xa0000`` 附近的 legacy display window；bridge 必须明确允许这类事务向下游传播。

如果根本没有VGA class function，函数记录 ``No VGA devices found`` 后返回；当前固定条件没有把具体VGA型号
写死。只有实际存在VGA时，这一阶段才选择并保证其legacy路径可达。VGA Option ROM的复制和执行属于后续
``vgarom_setup()``，不在当前 ``pci_setup()`` 内完成。

发现、分配、启用和驱动是四个不同阶段
----------------------------------

到这里可以把 PCI 启动过程区分为四层：

::

   第七章：发现
      总线上有哪些 function？拓扑怎样连接？

   第八章：分配
      每个 BAR 需要多大空间？地址放在哪里？

   第九章：启用
      中断怎样路由？设备是否响应 I/O/MMIO？

   后续章节：驱动
      怎样操作控制器？控制器后面有没有磁盘、USB 设备或网卡？

这些层次不能合并成一句“PCI 初始化完成”。当前结束时，配置空间和平台路由已经足以让 SeaBIOS 驱动访问控制器，
驱动尚未实际开始探测磁盘介质。

本章结束状态
------------

控制权目前走过：

::

   qemu_platform_setup()
   → pci_setup()
   → pci_bios_init_devices()
   → 为使用 INTx 的 function 写 PCI_INTERRUPT_LINE
   → ICH9 LPC 配置 PIRQA-H → IRQ10/IRQ11
   → 把 IRQ10/IRQ11 设置为 level-triggered
   → 建立 PMBASE、SCI IRQ9、RCBA 与 PM timer 地址
   → 条件配置 IDE legacy port、ICH9 SMBus、Intel IGD
   → 打开 PCI_COMMAND_IO / MEMORY / SERR
   → 为 bridge 打开 SERR forwarding
   → 释放临时 busses 资源规划数组
   → pci_enable_default_vga()
   → pci_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* A20：开启；NMI：仍由CMOS index bit 7屏蔽；
* 可屏蔽中断：主控制流IF仍为0；PIC仍只放行master IRQ2与slave IRQ13；
* SeaBIOS线程：仍只有 ``MainThread``，没有设备线程运行；
* q35 MMCONFIG：已经启用；
* PCI bus number、BAR 和 bridge window：已经配置；
* PCI INTx line：对 ``PCI_INTERRUPT_PIN != 0`` 的function已经计算并写入；
* ICH9 PIRQA-H：已经路由到 IRQ10/IRQ11；
* IRQ10/IRQ11：ELCR已设为电平触发，但仍被slave PIC mask；
* ICH9 LPC PMBASE、SCI 和 RCBA：已经配置；
* PM timer：setup调用已发生；是否取代PIT取决于此前是否已有timer source；
* PCI I/O、memory、SERR：SeaBIOS已对每个function请求置位其可写command bits；
* bridge SERR forwarding：SeaBIOS已请求置位；
* bus mastering：只会由后续具体驱动按需开启；
* 默认 VGA 路径：存在VGA时已选择并保证可达；不存在时已记录并返回；
* VGA Option ROM：尚未执行；
* SMM：尚未建立；
* ATA、AHCI、NVMe、USB、virtio 和网络驱动：尚未开始设备探测；
* 磁盘、光驱和网络启动项：尚未加入 ``BootList``；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

关键边界
--------

* ``PCI_INTERRUPT_PIN`` 是设备侧INTA-D身份， ``PCI_INTERRUPT_LINE`` 是固件写入的legacy IRQ号；
* q35 slot/pin swizzle、ICH9 PIRQ route和ELCR必须一致，但这些配置不会解除PIC mask或打开CPU IF；
* 本章没有处理任何设备中断；IRQ10/11仍不可经当前8259A状态送达BSP；
* 统一command写入包含I/O、memory和SERR，不包含bus master；没有对应窗口的bit也不会凭空产生设备资源；
* IDE legacy BAR、SMBus和Intel IGD设置都由实际匹配的function决定；固定AHCI控制器不进入IDE class分支；
* 临时 ``busses`` 被释放不影响配置空间中的BAR、bridge window、INTx或command状态；
* 默认VGA选择不执行Option ROM，控制器驱动和启动介质发现仍在后面。

下一入口
--------

``pci_setup()`` 返回后，``qemu_platform_setup()`` 的下一条调用是：

.. code-block:: c

   smm_device_setup();

下一章将进入System Management Mode相关准备：先由q35/ICH9状态判定QEMU执行后端
是否提供SMM；能力可用时安装SMI入口并让BSP完成第一次SMI/RSM，能力不可用时按
ICH9的预置标记跳过。

资料
----

* `SeaBIOS固定提交：q35 INTx swizzle、PIRQ与ELCR <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L106-L220>`_；
* `SeaBIOS固定提交：ICH9 SMBus和设备匹配表 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L275-L375>`_；
* `SeaBIOS固定提交：逐function INTx、command与bridge SERR <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L403-L431>`_；
* `SeaBIOS固定提交：默认VGA选择 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L433-L464>`_；
* `SeaBIOS固定提交：VGA legacy decode判定 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L206-L226>`_；
* `SeaBIOS固定提交：PM timer条件切换 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/timer.c#L137-L148>`_；
* `SeaBIOS固定提交：默认HARDWARE_IRQ与PMTIMER配置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L337-L367>`_；
* `SeaBIOS固定提交：bus mastering由驱动单独开启 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.c#L137-L144>`_；
* `QEMU固定提交：q35创建LPC、固定AHCI与条件SMBus/VGA <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L231-L325>`_；
* `SeaBIOS固定提交：pci_setup释放临时数组并返回 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L1239-L1247>`_。
