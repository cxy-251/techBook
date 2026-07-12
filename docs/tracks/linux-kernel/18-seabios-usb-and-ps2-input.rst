第十八章：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？
========================================================

上一章已经确认，当前固定 QEMU q35 默认路径中：

::

   ThreadControl = 1
   threads_during_optionroms() = false

VGA Option ROM 和文字控制台建立以后，``maininit()`` 进入：

.. code-block:: c

   if (!threads_during_optionroms()) {
       device_hardware_setup();
       wait_threads();
   }

``device_hardware_setup()`` 的调用顺序是：

.. code-block:: c

   void device_hardware_setup(void)
   {
       usb_setup();
       ps2port_setup();
       block_setup();
       lpt_setup();
       serial_setup();
       cbfs_payload_setup();
   }

这一章先追踪前两个入口，停在 ``block_setup()`` 即将开始的位置。

需要先说明一个执行细节：这里虽然称为“同步设备初始化路径”，也不表示每个函数返回时，它启动的所有任务都已经完成。SeaBIOS 的 ``run_thread()`` 会创建协作式线程，线程遇到 ``yield()``、``msleep()`` 或等待硬件时把执行机会交回主线程。

所以实际形态更接近：

::

   main thread 调用 usb_setup()
   → USB controller thread 开始运行并在等待时 yield
   → main thread 继续 ps2port_setup()
   → PS/2 keyboard thread 开始运行并在等待时 yield
   → main thread 即将进入 block_setup()
   → 所有设备线程随后交错推进
   → device_hardware_setup() 返回后 wait_threads() 统一收尾

“同步路径”指这些任务不会跨过 VGA Option ROM 阶段并行运行；它们在当前设备初始化阶段内部仍然可以协作并发。

q35 默认创建怎样的 USB 控制器
-------------------------

固定 QEMU ``pc_q35_init()`` 在 USB 启用时调用：

.. code-block:: c

   ehci_create_ich9_with_companions(pcms->pcibus, 0x1d);

它在 PCI slot ``0x1d`` 创建：

::

   00:1d.7  ICH9 EHCI controller
   00:1d.0  ICH9 UHCI companion 1
   00:1d.1  ICH9 UHCI companion 2
   00:1d.2  ICH9 UHCI companion 3

具体 BDF 仍会受总线拓扑和机器配置影响，上面是没有额外 bridge 改写默认根总线布局时的典型结果。

这组控制器不是四套互不相关的 USB 端口。EHCI 负责 USB 2.0 high-speed 事务，三个 UHCI companion 负责同一组物理端口上的 low-speed/full-speed 设备。

QEMU 把每个 UHCI function 连接到 EHCI child bus 的不同端口区间：

::

   UHCI 1 → firstport 0
   UHCI 2 → firstport 2
   UHCI 3 → firstport 4

因此一组六个逻辑 root ports 由一个 EHCI 与三个 UHCI function 协同管理。

usb_setup 为什么按 XHCI、EHCI、UHCI、OHCI 排序
-----------------------------------------

SeaBIOS 执行：

.. code-block:: c

   xhci_setup();
   ehci_setup();
   uhci_setup();
   ohci_setup();

当前默认 q35 重点是 EHCI + UHCI；XHCI 和 OHCI 扫描通常找不到匹配 function，除非虚拟机另外添加对应控制器。

EHCI 必须早于 UHCI 的原因不是“新协议优先”。真正原因是 companion routing。

EHCI 先检查端口速度：

* high-speed 设备由 EHCI 自己接管；
* low-speed 设备通过 ``PORT_OWNER`` 交给 companion；
* reset 后未进入 high-speed 的 full-speed 设备也交给 companion。

UHCI 如果过早扫描，可能在 EHCI 尚未完成端口所有权判定时看到不稳定状态。因此 SeaBIOS 使用：

::

   PendingEHCI
   ehci_wait_controllers()

让 UHCI controller thread 在枚举端口前等待所有 EHCI 初始化完成。

EHCI 怎样从一个 PCI function 变成可用控制器
---------------------------------------

``ehci_setup()`` 扫描已经建立的 ``PCIDevices``，匹配 USB EHCI class/prog-if，然后对每个 function 调用 ``ehci_controller_setup()``。

第一步是取得 PCI BAR0：

.. code-block:: c

   caps = pci_enable_membar(pci, PCI_BASE_ADDRESS_0);

这里消费了第八、九章完成的 BAR 分配和 memory-space decode。返回值是 EHCI capability registers 的 MMIO 基址。

接下来 SeaBIOS：

* 分配 controller bookkeeping；
* 从 ``HCSPARAMS`` 读取 root port 数；
* 根据 ``CAPLENGTH`` 计算 operational register 基址；
* 条件清零 64 位地址高半部分；
* 开启 PCI bus master；
* 增加 ``PendingEHCI``；
* 用 ``run_thread(configure_ehci, cntl)`` 启动配置线程。

开启 bus master 很关键。EHCI schedule、queue head 和 transfer descriptor 都在客户机 RAM 中，控制器必须能主动 DMA 读取这些结构并写回完成状态。

EHCI reset 期间主线程为什么还能继续
--------------------------------

``configure_ehci()`` 向 ``USBCMD`` 写入 ``HCRESET``，然后等待硬件自动清除该 bit。

等待循环不是永久忙等：

.. code-block:: c

   while (USBCMD & HCRESET) {
       if (timeout)
           ...
       yield();
   }

因此 EHCI 正在复位时，SeaBIOS 可以切换到其他 controller thread 或返回主线程继续建立后续任务。这是固件协作式线程第一次真正用于缩短设备探测等待时间。

EHCI 为什么需要 periodic 和 asynchronous 两张 schedule
---------------------------------------------------

复位后 SeaBIOS 分配：

``frame list``
   周期调度表，用于 interrupt transfer 等定期事务。

``interrupt queue head``
   周期调度链的入口。

``asynchronous queue head``
   control transfer 与 bulk transfer 使用的循环异步队列入口。

SeaBIOS 把这些物理地址写入：

::

   PERIODICLISTBASE
   ASYNCLISTADDR

随后打开：

::

   CMD_PSE   periodic schedule enable
   CMD_ASE   asynchronous schedule enable
   CMD_RUN   controller run

最后设置 ``CONFIGFLAG=1``，声明 EHCI 已经接管支持 high-speed 的端口路由。

这时控制器才从“PCI function 已枚举”变成“可以执行 USB transaction schedule 的 DMA engine”。

端口枚举不是读取一次状态寄存器
---------------------------

``check_ehci_ports()`` 先给 root ports 上电，等待约 20 ms，再构造一个临时 root hub 对象并调用：

.. code-block:: c

   usb_enumerate(&hub);

``usb_enumerate()`` 对每个端口分别创建线程：

::

   port 0 thread
   port 1 thread
   ...

每个 ``usb_hub_port_setup()`` 执行：

::

   detect connection
   → 等待 connect debounce / timeout
   → 锁住 controller resetlock
   → reset port 并判断速度
   → 使用默认地址 0 建立 control pipe
   → SET_ADDRESS
   → 切换到新 device address
   → 解锁 resetlock
   → 读取 descriptors
   → 选择受支持 class driver

同一 controller 上的 SET_ADDRESS 阶段需要串行化，因为所有刚复位、尚未编号的设备都响应 USB default address 0。如果两个端口同时在 address 0 上发送命令，主机无法可靠区分目标。

所以 SeaBIOS 允许多个端口并行等待连接和 reset，却用 ``resetlock`` 保护最敏感的地址分配阶段。

为什么先只读取 device descriptor 的 8 字节
-------------------------------------

设备刚复位时，host 还不知道 endpoint 0 的真实 ``wMaxPacketSize``。

SeaBIOS 先按速度选择保守初值：

::

   low/full speed  → 8 bytes
   high speed      → 64 bytes
   SuperSpeed      → 512 bytes

完成 SET_ADDRESS 后，再读取 device descriptor 前 8 字节，从 ``bMaxPacketSize0`` 得到真实值，并重新配置 default control pipe。

这是一种 USB 枚举中的“先用规范保证的最低知识通信，再从设备自描述信息升级通信参数”的过程。

配置描述符为什么要读两次
---------------------

``get_device_config()`` 先只读取固定长度的 configuration descriptor header，取得：

::

   wTotalLength

然后按该长度分配缓冲区，第二次读取整段配置树。

完整配置包含：

* configuration descriptor；
* 一个或多个 interface descriptor；
* endpoint descriptor；
* class-specific descriptor。

第一次就猜一个固定大缓冲区既浪费低端固件内存，也可能截断更大的 descriptor tree。

SeaBIOS 只支持启动阶段真正需要的 USB class
-------------------------------------

当前 ``configure_usb_device()`` 只接受第一组 configuration 中的以下 interface：

``USB hub``
   继续向下枚举外接 hub 的子端口。

``USB mass storage``
   Bulk-Only Transport 或 UAS，用于 U 盘、USB 硬盘、USB 光驱等块设备。

``USB HID boot subclass``
   启动协议键盘或鼠标。

其他设备即使 USB 枚举完全合法，也不会因此获得 SeaBIOS 驱动。例如摄像头、音频设备和普通 vendor-specific device 会被忽略，因为它们不是 BIOS 启动和输入路径的必要组成部分。

识别到受支持 interface 后，SeaBIOS 发送 ``SET_CONFIGURATION``，随后才交给 class driver。

USB HID 为什么要求 boot protocol
-----------------------------

完整 HID 可以通过 HID report descriptor 描述几乎任意输入布局。解析完整 HID descriptor language 对小型固件来说复杂且收益有限。

USB HID boot subclass 定义了固定格式：

* boot keyboard report；
* boot mouse report。

SeaBIOS 向设备发送：

.. code-block:: c

   SET_PROTOCOL(boot protocol)

键盘还会发送 ``SET_IDLE``，使设备定期重复报告，从而支持固件阶段的按键重复。

随后 SeaBIOS 为 interrupt-IN endpoint 创建持久 pipe，并把它加入 ``keyboards`` 或 ``mice`` 链表。

USB 键盘为什么最终也走 process_key
--------------------------------

USB boot keyboard report 包含 modifier byte 和最多六个同时按下的 key usage。SeaBIOS 比较新旧 report，识别：

* 新按下的键；
* 已释放的键；
* modifier 变化；
* 按键重复。

接着使用 ``KeyToScanCode`` 和 ``ModifierToScanCode`` 表，把 USB HID usage 转成与 AT/PS2 类似的 scan-code sequence，再调用：

.. code-block:: c

   process_key(...);

PS/2 IRQ1 handler 也会把端口 ``0x60`` 读出的 scan code 交给同一个 ``process_key()``。

因此两种物理来源在固件内部汇合：

::

   USB keyboard report ─┐
                        ├→ process_key()
   PS/2 scan code ──────┘
                        → 更新 shift/lock 状态
                        → 生成 BIOS keycode
                        → enqueue 到 BDA keyboard ring
                        → INT 16h 读取

GRUB 将来通过 BIOS 键盘服务读取按键时，不需要知道按键最初来自 USB controller 还是 i8042。

USB mass storage 可能已经提前加入启动设备候选
---------------------------------------

USB class 分流发生在 ``block_setup()`` 之前。

Bulk-Only mass-storage driver 找到 bulk-IN 和 bulk-OUT endpoint，读取最大 LUN，然后为每个 LUN 建立 ``usbdrive_s``。它使用 SCSI command set 查询容量、设备类型和 block size，并调用：

.. code-block:: c

   scsi_drive_setup(&drive->drive, "USB MSC", prio);

因此如果虚拟机挂有 USB U 盘或 USB 光驱，启动设备候选可以在通用 ``block_setup()`` 调用前就出现。

这不表示默认 q35 一定挂载 USB 存储；默认创建的是 controller，具体 USB devices 由虚拟机配置决定。

UHCI 为什么必须等待 EHCI
---------------------

q35 的三个 UHCI function 各自使用 PCI I/O BAR4。SeaBIOS 为每个 controller：

* 开启 I/O decode 和 bus master；
* 清理 legacy PIRQ/SMI 状态；
* reset controller；
* 分配 1024-entry frame list、queue head 和 transfer descriptor；
* 设置 1 ms USB frame；
* 写入 frame-list base；
* 打开 Run/Stop、Configured Flag 和 64-byte packet mode。

真正扫描 root ports 前，``check_uhci_ports()`` 调用：

.. code-block:: c

   ehci_wait_controllers();

只有 ``PendingEHCI`` 归零后，UHCI 才检查自己的两个端口。此时 EHCI 已经把 low/full-speed 端口路由给 companion，避免同一物理设备被两个 host controller 同时尝试初始化。

没有设备时控制器会被主动停掉
--------------------------

SeaBIOS 对 EHCI/UHCI 的策略不是“只要发现 controller 就永远保持所有 schedule 和临时内存”。

如果 root-hub 扫描没有找到任何可支持设备：

* controller 被停止；
* 临时 frame list、queue head、pipe 被释放；
* 不保留无意义的轮询状态。

如果找到键盘、鼠标或存储，必要的 pipe 和 controller state 会搬到可跨 POST 保留的区域，供后续 16 位 BIOS 服务继续访问。

i8042 是否存在先由 ACPI 提示
-------------------------

``usb_setup()`` 返回到主线程后，``device_hardware_setup()`` 调用：

.. code-block:: c

   ps2port_setup();

它首先询问上一批章节建立的 DSDT 索引：

.. code-block:: c

   acpi_dsdt_present_eisaid(0x0303)

``PNP0303`` 是标准 PC keyboard controller/keyboard device ID。

返回值为明确不存在时，SeaBIOS 跳过 PS/2 初始化。这防止固件对没有 i8042 的平台盲目访问 ``0x60/0x64``。

如果 DSDT 表示存在，或解析结果无法确定，SeaBIOS 继续传统探测。当前 q35 PC 兼容路径通常提供 i8042。

PS/2 data port 与 status/command port
---------------------------------

传统 i8042 使用：

::

   0x60  data port
   0x64  status read / controller command write

状态寄存器关键 bit：

``OBF``
   Output Buffer Full。controller 有数据可供 CPU 从 ``0x60`` 读取。

``IBF``
   Input Buffer Full。controller 还没有消费 CPU 先前写入的数据，CPU 暂时不能继续写。

``AUXDATA``
   当前 output byte 来自 auxiliary/mouse port，而非 keyboard port。

SeaBIOS 的低层函数在每次 command 或 data write 前等待 ``IBF=0``，在读取返回字节前等待 ``OBF=1``，并使用内部 timer 设置超时。这样某个缺失或故障设备不会永久锁死 POST。

为什么先同时安装 IRQ1 和 IRQ12
---------------------------

``ps2port_setup()`` 执行：

.. code-block:: c

   enable_hwirq(1, FUNC16(entry_09));
   enable_hwirq(12, FUNC16(entry_74));

得到：

::

   keyboard IRQ1  → INT 09h
   mouse IRQ12    → INT 74h

这里安装 mouse IRQ path，并不代表鼠标已经开始 streaming。鼠标设备的 enable、sample rate 和 callback 通常要等 BIOS mouse service 调用者提出请求后再配置。

本章实际立即初始化的是 keyboard side。

PS/2 keyboard 初始化也运行在线程中
-------------------------------

``ps2port_setup()`` 最后执行：

.. code-block:: c

   run_thread(ps2_keyboard_setup, NULL);

键盘 reset 和 BAT 可能等待数百毫秒甚至数秒。放在线程里可以让 SATA、USB 或其他设备探测在等待 ACK/BAT 字节期间继续推进。

``ps2_keyboard_setup()`` 的顺序是：

::

   flush controller output buffer
   → disable keyboard port
   → disable auxiliary port
   → 再次 flush
   → controller self-test
   → keyboard interface test
   → keyboard reset / BAT
   → disable keyboard scanning
   → select scan-code set 2
   → configure controller translation + IRQ1
   → enable keyboard scanning

每一步失败都会终止 PS/2 keyboard 初始化，但不会终止整台机器启动；USB keyboard 仍可能提供输入。

controller self-test 与 keyboard BAT 不是同一测试
--------------------------------------------

SeaBIOS 首先发 i8042 controller self-test，期望返回：

::

   0x55

这测试的是 keyboard controller 本身。

随后测试 keyboard interface，期望：

::

   0x00

再向 keyboard device 发送 reset/BAT command。命令先应答：

::

   0xfa  ACK

随后设备自检成功通常返回：

::

   0xaa  BAT passed

把 ``0x55`` 与 ``0xaa`` 都笼统称作“键盘自检通过”会混淆 controller 和 device 两个层级。

为什么选择 scan-code set 2 又开启 translation
----------------------------------------

现代 AT keyboard 常用 scan-code set 2。SeaBIOS向设备设置 set 2，同时在 i8042 controller command byte 中打开 translation。

结果是：

::

   keyboard device 发送 set-2 code
   → i8042 translation logic
   → CPU 看到传统 set-1 风格 code
   → SeaBIOS process_key() 使用既有映射表

这种设计保持了传统 PC BIOS、DOS 软件和 ``INT 09h`` handler 对经典 scan code 的兼容。

IRQ1 到 INT 16h 之间还隔着哪些步骤
--------------------------------

键盘产生数据后：

::

   i8042 把 byte 放入 output buffer
   → 拉起 IRQ1
   → master PIC 映射到 INT 09h
   → entry_09
   → handle_09()
   → 检查 AUXDATA，确认是 keyboard byte
   → 从 0x60 读取 scan code
   → process_key()
   → 更新 BDA modifier/lock 状态
   → 生成 BIOS keycode
   → enqueue_key() 写入 BDA ring
   → PIC EOI

应用或 bootloader 随后调用：

::

   INT 16h AH=00 / 10  读取并移除按键
   INT 16h AH=01 / 11  检查但不移除按键

硬件 IRQ handler 和软件 BIOS service 是两个阶段：前者收集并转换输入，后者让调用者按统一接口取走结果。

当前阶段的任务可能尚未全部完成
---------------------------

执行到 ``ps2port_setup()`` 返回时：

* EHCI/UHCI controller threads 可能仍在枚举端口；
* USB hub 子端口线程可能仍在运行；
* USB mass-storage LUN 可能正在执行 SCSI inquiry；
* PS/2 keyboard thread 可能正在等待 BAT；
* USB keyboard 或 PS/2 keyboard 任一方都可能先完成。

主线程不会立刻在这里调用 ``wait_threads()``。它继续进入 ``block_setup()``，把 SATA、virtio、NVMe 等探测任务也加入同一个协作式执行集合，最后统一等待。

第十八章结束时的机器状态
----------------------

控制权目前走过：

::

   maininit()
   → default synchronous device_hardware_setup()
   → usb_setup()
   → xHCI conditional scan
   → EHCI controller setup
   → EHCI reset / schedules / port ownership
   → UHCI companion setup after EHCI routing
   → per-port USB threads
   → address 0 / SET_ADDRESS / descriptors
   → hub / MSC / UAS / HID boot class dispatch
   → ps2port_setup()
   → DSDT PNP0303 presence check
   → IRQ1 / INT09h and IRQ12 / INT74h
   → PS/2 keyboard thread
   → controller test / keyboard BAT / scan set 2 / translation
   → 即将调用 block_setup()

此刻：

* 当前主流程执行者：SeaBIOS ``device_hardware_setup()``；
* 主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* q35 EHCI/UHCI controllers：已发现并启动配置线程；
* USB ports：正在或已经完成枚举；
* USB HID：条件建立 boot keyboard/mouse pipe；
* USB mass storage：条件建立 SCSI-backed drive 并加入启动候选；
* i8042 IRQ1/IRQ12：已经接通；
* PS/2 keyboard：正在或已经完成 BAT、scan set 和 IRQ 配置；
* USB 与 PS/2 键盘：最终汇合到 ``process_key()``、BDA ring 和 ``INT 16h``；
* q35 内置 AHCI controller：PCI 层已存在，但 SeaBIOS AHCI driver 尚未开始本轮探测；
* 普通非 VGA Option ROM：尚未扫描；
* ``BootList``：可能已有 USB 条件设备，尚未形成最终集合；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``device_hardware_setup()`` 的下一条调用是：

.. code-block:: c

   block_setup();

下一章将固定启动磁盘走 q35 内置 ICH9 AHCI SATA 路径，逐步追踪 HBA reset、BAR5、command list/FIS、port link、IDENTIFY、LBA 容量、transfer mode、``boot_add_hd()`` 和 ``wait_threads()``。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/hw/usb.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/usb.c>`_；
* `SeaBIOS src/hw/usb-ehci.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/usb-ehci.c>`_；
* `SeaBIOS src/hw/usb-uhci.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/usb-uhci.c>`_；
* `SeaBIOS src/hw/usb-hid.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/usb-hid.c>`_；
* `SeaBIOS src/hw/usb-msc.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/usb-msc.c>`_；
* `SeaBIOS src/hw/ps2port.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ps2port.c>`_；
* `SeaBIOS src/kbd.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/kbd.c>`_；
* `SeaBIOS src/stacks.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c>`_；
* `QEMU hw/i386/pc_q35.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c>`_；
* `USB 2.0 Specification <https://www.usb.org/document-library/usb-20-specification>`_；
* `USB HID Specification <https://www.usb.org/hid>`_；
* `ACPI Specification <https://uefi.org/specifications>`_。