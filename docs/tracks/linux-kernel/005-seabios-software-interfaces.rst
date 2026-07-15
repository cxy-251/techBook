第五章：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？
======================================================

上一章结束时，SeaBIOS 已经建立了 IVT、BDA、EBDA 和额外的 16 位中断栈。控制流仍在：

::

   post.c:interface_init()

它接下来依次调用：

.. code-block:: c

   boot_init();
   bios32_init();
   pmm_init();
   pnp_init();
   kbd_init();
   mouse_init();

这些函数的名字容易让人产生一个错误印象：SeaBIOS 好像马上就要扫描磁盘、驱动键盘和识别鼠标。

实际情况更早。当前阶段主要是在建立 **软件契约**：

* 将来发现启动设备时，按什么规则排序；
* 32 位程序怎样找到 PCI BIOS 服务；
* Option ROM 在 POST 期间怎样申请临时或永久内存；
* 旧式软件怎样发现 PnP BIOS 入口；
* 键盘字符先放到哪里；
* 系统怎样声明存在指点设备。

真正的 PCI 枚举、PS/2 控制器初始化、磁盘控制器探测和设备驱动还没有开始。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

当前路径使用该提交的默认QEMU配置，其中 ``CONFIG_BOOT``、 ``CONFIG_BOOTORDER``、
``CONFIG_PCIBIOS``、 ``CONFIG_OPTIONROMS``、 ``CONFIG_PMM``、 ``CONFIG_PNPBIOS``、
``CONFIG_KEYBOARD`` 和 ``CONFIG_MOUSE`` 均为 ``y``。关闭对应配置时，相关入口会返回
或不被发布，不能沿用本章的结束状态。

本章结束在 ``interface_init()`` 返回。下一条控制流将是 ``maininit()`` 中的
``platform_hardware_setup()``。

boot_init 先建立启动规则，不是寻找启动设备
-----------------------------------------

``boot_init()`` 位于 ``src/boot.c``：

.. code-block:: c

   void
   boot_init(void)
   {
       if (!CONFIG_BOOT)
           return;

       if (CONFIG_QEMU) {
           /* 从 CMOS 读取默认启动类别顺序 */
       }

       BootRetryTime = romfile_loadint("etc/boot-fail-wait", 60*1000);
       loadBootOrder();
       loadBiosGeometry();
   }

这里没有访问 ATA、SATA、SCSI、NVMe、光驱或网卡。``BootList`` 此时仍然可以是空的。

``boot_init()`` 建立的是一套排序规则。稍后设备驱动真正发现磁盘、光驱或网络启动 ROM 时，才会调用：

.. code-block:: c

   boot_add_floppy(...);
   boot_add_hd(...);
   boot_add_cd(...);
   boot_add_bev(...);
   boot_add_bcv(...);

把具体设备加入 ``BootList``。

这个顺序很重要。SeaBIOS 必须先知道“怎样排序”，随后每个驱动才能在发现设备时立即计算优先级；不能等
所有设备都初始化完，再临时猜测哪一个应该排在前面。

QEMU CMOS 中的传统启动类别
-------------------------

在 QEMU 构建中，``boot_init()`` 读取两个 CMOS 字段，组合成传统启动顺序。每个四位值代表一种类别：

::

   1 = floppy
   2 = hard disk
   3 = CD-ROM
   4 = BEV

BEV 是 Boot Entry Vector，通常由可启动 Option ROM 提供，例如某些网络启动 ROM。

源码的四个静态初值是：

::

   floppy    101
   CD-ROM    102
   hard disk 103
   BEV       104

这些值不是当前QEMU分支读取CMOS后的最终默认值。进入 ``if (CONFIG_QEMU)`` 后，
``boot_init()`` 先把四类全部改成 ``DEFAULT_PRIO = 9999``，再只消费三个四位槽位：

::

   i = 101, 102, 103

每个非零槽位把对应类别改成当前 ``i``；没有出现在这三个槽位中的类别保持9999。
所以在当前QEMU路径中，BEV不能无条件继承静态初值104。数字仍然越小越靠前，但最终
类别顺序取决于这三个CMOS槽位。

这里处理的是类别级别的旧式启动顺序，例如“先光驱，再硬盘”。它还不能区分两块具体硬盘之间谁先谁后。

bootorder 文件把设备路径变成优先级
--------------------------------

SeaBIOS 随后执行：

.. code-block:: c

   loadBootOrder();

它通过 ``romfile_loadfile("bootorder", NULL)`` 读取一份按行排列的设备路径。QEMU 可以通过 ``fw_cfg``
把这份文件交给 SeaBIOS。

路径看起来类似：

::

   /pci@i0cf8/ide@1,1/drive@0/disk@0
   /pci@i0cf8/scsi@5/channel@0/disk@1,0
   /pci@i0cf8/ethernet@5

SeaBIOS 把第一行赋予优先级 1，第二行赋予优先级 2，依次递增。稍后某个驱动发现设备时，会根据 PCI
BDF、控制器通道、target、LUN、USB 端口等信息构造同样的路径，再调用 ``find_prio()`` 匹配。

因此启动顺序不是靠“第一个扫描到的磁盘就是第一启动盘”。硬件发现顺序和启动优先级是两件不同的事：

::

   设备探测顺序
       决定什么时候发现设备

   bootorder 优先级
       决定设备最终排在启动列表的什么位置

``boot_init()`` 还读取：

``etc/boot-fail-wait``
   所有启动尝试失败后等待多久。缺省值是 60 秒。

``bios-geometry``
   为需要传统 CHS 几何信息的磁盘提供 cylinder、head、sector 参数。

到这里，SeaBIOS 已经知道怎样组织未来的启动候选项，仍然没有一块具体磁盘被加入 ``BootList``。

bios32_init 建立 32 位服务目录
----------------------------

传统 BIOS 最著名的接口是 ``INT xx`` 软件中断，它们主要面向 16 位实模式程序。80386 以后，启动软件和
操作系统早期代码可能已经运行在 32 位保护模式中。它们需要一种不退回普通 16 位中断调用，就能发现
32 位 BIOS 服务入口的方法。

``bios32_init()`` 为此填写 BIOS32 Service Directory：

.. code-block:: c

   struct bios32_s BIOS32HEADER __aligned(16) VARFSEG = {
       .signature = 0x5f32335f,  /* _32_ */
       .length = sizeof(BIOS32HEADER) / 16,
   };

   void
   bios32_init(void)
   {
       BIOS32HEADER.entry = (u32)entry_bios32;
       BIOS32HEADER.checksum -= checksum(&BIOS32HEADER,
                                         sizeof(BIOS32HEADER));
   }

``0x5f32335f`` 按内存中的 ASCII 字节表示为：

::

   _32_

这个结构按 16 字节对齐，包含：

* 签名；
* 32 位入口地址；
* 版本；
* 以 16 字节为单位的长度；
* 校验和。

SeaBIOS 调整 ``checksum`` 字段，使整个结构的逐字节和为零。发现者不能只看到 ``_32_`` 就相信它；还要
检查长度和校验和，避免把普通数据误认成服务目录。

BIOS32 入口当前只公开 PCI BIOS
-----------------------------

``entry_bios32`` 位于 ``src/romlayout.S``。调用者把希望查找的服务签名放在 ``EAX``。SeaBIOS 当前检查：

.. code-block:: asm

   cmpl $0x49435024, %eax   // $PCI
   jne unknown

``0x49435024`` 的字节形式是：

::

   $PCI

匹配成功后，SeaBIOS 返回：

::

   EBX = BUILD_BIOS_ADDR
   ECX = BUILD_BIOS_SIZE
   EDX = entry_pcibios32
   AL  = 0

也就是告诉调用者：PCI BIOS 32 位服务位于哪一段 BIOS 地址区域，真正入口相对于基址在哪里。

未知服务则返回：

::

   AL = 0x80

这个“32 位”仍然是 IA-32 保护模式接口，不是 x86-64 long mode，也不是 Linux 内核已经启动。它只是让
32 位启动软件可以调用固件提供的 PCI 配置查询能力。

``entry_pcibios32`` 最终进入 ``handle_pcibios()``。后者可以完成：

* 检查 PCI BIOS 是否存在；
* 按 vendor/device ID 查找设备；
* 按 class code 查找设备；
* 读取 PCI 配置字节、字和双字；
* 写入 PCI 配置字节、字和双字；
* 取得 PCI IRQ routing 信息。

当前阶段只是把入口公布出去。 ``MaxPCIBus`` 尚未由后续PCI探测形成最终值，
``PirAddr`` 也尚未指向之后生成的IRQ routing table；此刻调用查找或IRQ routing服务
不能被解释成已经拥有完整PCI结果。PCI设备枚举从第七章才开始。

PMM 让 Option ROM 在 POST 期间申请内存
------------------------------------

显卡、网卡、存储控制器等扩展设备可能带有 Option ROM。固件执行这些 ROM 时，ROM 代码有时需要临时
缓冲区，也可能要留下启动后仍然有效的数据。

Option ROM 不能随便挑一段物理内存写入。它不知道 SeaBIOS 已经在哪些区域放置了 EBDA、固件表、临时代码
和其他 ROM。SeaBIOS 因此提供 POST Memory Manager，也就是 PMM。

PMM 头的签名是：

::

   $PMM

源码定义：

.. code-block:: c

   struct pmmheader PMMHEADER __aligned(16) VARFSEG = {
       .signature = PMM_SIGNATURE,
       .version = 0x01,
       .length = sizeof(PMMHEADER),
   };

``pmm_init()`` 填入 16 位入口并计算校验和：

.. code-block:: c

   PMMHEADER.entry = FUNC16(entry_pmm);
   PMMHEADER.checksum -= checksum(&PMMHEADER, sizeof(PMMHEADER));

Option ROM 可以通过入口请求三类操作：

::

   0x00  allocate
   0x01  find by handle
   0x02  deallocate

PMM 分配长度以 16 字节 paragraph 为单位。``length * 16`` 才是实际字节数。

标志位还决定：

* 从低端内存还是高端内存分配；
* 是否允许低端和高端二选一；
* 是否按分配大小提高对齐；
* 申请的是 POST 临时内存还是永久内存。

临时请求使用：

::

   ZoneTmpLow
   ZoneTmpHigh

永久请求使用：

::

   ZoneLow
   ZoneHigh

如果永久高端请求太大，``ZoneHigh`` 放不下，SeaBIOS 可以从更大的 ``ZoneTmpHigh`` 分配，再把这段范围加入
``E820_RESERVED``。这样内存虽然来自原本的临时高端 RAM，bootloader 和操作系统也不会把它覆盖。

PMM 不是操作系统运行期间长期开放的通用内存分配器。在准备启动时，SeaBIOS 的 ``pmm_prepboot()`` 会清除
``$PMM`` 签名和入口。它的生命周期只覆盖固件 POST 与 Option ROM 初始化阶段。

PnP BIOS 头公布实模式和保护模式入口
---------------------------------

``pnp_init()`` 建立另一份可扫描结构，签名是：

::

   $PnP

头部记录：

* PnP BIOS 版本 ``1.0``；
* 结构长度和校验和；
* 实模式入口 ``entry_pnp_real``；
* 保护模式入口 ``entry_pnp_prot``；
* 实模式代码段和数据段；
* 保护模式代码基址和数据基址。

初始化代码为：

.. code-block:: c

   PNPHEADER.real_ip = (u32)entry_pnp_real - BUILD_BIOS_ADDR;
   PNPHEADER.prot_ip = (u32)entry_pnp_prot - BUILD_BIOS_ADDR;
   PNPHEADER.checksum -= checksum(&PNPHEADER, sizeof(PNPHEADER));

SeaBIOS 当前 PnP BIOS 实现很小。``handle_pnp()`` 主要支持函数 ``0x60``，用于 BBS 版本与安装检查；其他
大多数调用返回 ``FUNCTION_NOT_SUPPORTED``。

所以“存在 ``$PnP`` 头”不等于 SeaBIOS 已经建立一套完整的现代即插即用设备管理系统。这里主要是在保持
传统固件接口兼容，并为后续 Option ROM 和启动流程提供必要的发现入口。

kbd_init 建立的是键盘队列，不是键盘驱动
--------------------------------------

第四章已经在 IVT 中把 ``INT 16h`` 指向 SeaBIOS 的键盘服务入口。现在 ``kbd_init()`` 初始化这项服务依赖
的 BDA 状态：

.. code-block:: c

   u16 x = offsetof(struct bios_data_area_s, kbd_buf);

   SET_BDA(kbd_flag1, KF1_101KBD);
   SET_BDA(kbd_buf_head, x);
   SET_BDA(kbd_buf_tail, x);
   SET_BDA(kbd_buf_start_offset, x);
   SET_BDA(kbd_buf_end_offset,
           x + FIELD_SIZEOF(struct bios_data_area_s, kbd_buf));

``kbd_buf`` 在 BDA 中从偏移 ``0x1e`` 开始，大小为 32 字节。SeaBIOS 每个键码使用 2 字节，因此内存中
存在 16 个物理槽位。环形队列必须始终空出一个槽位，用来区分 ``head == tail`` 表示“空”还是“满”，
所以实际最多保存 15 个键码。

刚初始化时：

::

   head = tail = 0x1e

表示队列为空。将来键盘中断处理程序收到按键后，会把扫描码和 ASCII 结果组成一个 16 位键码，写到
``tail`` 指向的位置，再向后移动两个字节。到达缓冲区末尾后，指针回绕到起点。

准备写入时，SeaBIOS 会先计算下一个 ``tail``。如果它将与 ``head`` 重合，就拒绝新键码，从而保留那个
用于区分满和空的空槽。

``INT 16h`` 的读取调用从 ``head`` 取出键码。读取后 ``head`` 前进；只检查状态时不移动 ``head``。

``kbd_init()`` 还设置 ``KF1_101KBD``，告诉兼容软件当前使用增强型 101 键键盘语义。

此时没有向 PS/2 端口发送命令，也没有发现 USB 键盘。后面的设备初始化会决定输入来自：

* PS/2 键盘；
* USB HID 键盘；
* QEMU 提供的相应虚拟设备。

无论底层设备是哪一种，最终按键都可以进入同一个 BDA 环形缓冲区，供 ``INT 16h`` 使用。这正是 BIOS
接口的作用：把不同硬件来源统一成旧式软件认识的调用方式。

mouse_init 目前只设置一个存在标志
--------------------------------

``mouse_init()`` 更短：

.. code-block:: c

   void
   mouse_init(void)
   {
       if (!CONFIG_MOUSE)
           return;
       set_equipment_flags(0x04, 0x04);
   }

它把 BDA ``equipment_list_flags`` 中的指点设备位设置为 1，表示 BIOS 提供鼠标支持。

这里没有复位鼠标、设置采样率，也没有启用 PS/2 辅助端口。真正的鼠标命令由后面的 ``INT 15h / AH=C2h``
服务和 PS/2 或 USB HID 后端完成。

鼠标服务需要保存调用者提供的事件处理函数地址。SeaBIOS 后续会把这个远指针以及鼠标状态放在 EBDA 中：

::

   far_call_pointer
   mouse_flag1
   mouse_flag2
   mouse_data[]

这也解释了为什么上一章必须先建立 EBDA，当前章才能宣布并维护鼠标 BIOS 接口。

interface_init 完成了什么
-----------------------

``interface_init()`` 到这里返回。SeaBIOS 已经完成两类不同的准备工作。

第一类是低端内存基础结构：

::

   IVT
   BDA
   EBDA
   ExtraStack

第二类是可被后续代码发现和使用的软件接口：

::

   boot priority policy
   BIOS32 Service Directory
   PCI BIOS 32-bit entry
   PMM entry
   PnP BIOS header
   INT 16h keyboard queue state
   INT 15h mouse support state

这些接口并不证明相关硬件已经初始化。当前更准确的状态是：

* SeaBIOS 已经准备好“怎样描述和调用”这些能力；
* 后面的硬件初始化将逐步提供真正的 PCI 设备、计时器、键盘控制器、鼠标、磁盘和其他资源；
* 每发现一个可启动设备，驱动会按照本章建立的规则把它加入 ``BootList``；
* Option ROM 运行时可以使用 PMM，而不会随意覆盖固件内存；
* 16 位和 32 位启动软件已经有固定入口寻找 BIOS 服务。

本章结束状态
------------

控制权目前走过：

::

   interface_init()
   → boot_init()
   → 读取 CMOS 启动类别顺序
   → 读取 bootorder / bios-geometry / boot-fail-wait
   → bios32_init()
   → 建立 _32_ 服务目录与 $PCI 入口
   → pmm_init()
   → 建立 $PMM 内存服务入口
   → pnp_init()
   → 建立 $PnP 实模式与保护模式入口
   → kbd_init()
   → 建立 BDA 键盘环形缓冲区
   → mouse_init()
   → 设置 BDA 指点设备标志
   → interface_init() 返回

此刻：

* 当前执行者：重定位后的 SeaBIOS ``maininit()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* 可屏蔽中断：关闭；NMI仍由CMOS index bit 7屏蔽；
* BIOS 软件服务发现结构：已经建立；
* 启动优先级规则：已经建立；
* QEMU类别优先级：只由三个CMOS槽位赋予101—103，未出现类别保持9999；
* 具体启动设备列表：仍为空，尚待设备驱动填充；
* PCI BIOS32入口：已经发布，但PCI枚举与PIR表尚未建立；
* 键盘 BDA 队列：已经初始化，尚无按键；
* 鼠标 BIOS 支持标志：已经设置；
* PCI、PIC、定时器、PS/2 和磁盘硬件初始化：尚未执行；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

关键边界
--------

#. ``boot_init()`` 建立排序输入，不探测任何磁盘、光驱或网卡； ``BootList`` 与
   bootorder规则是两个不同对象。
#. 101/102/103/104只是四个变量的静态初值；当前QEMU分支会先清成9999，再从三个
   CMOS槽位分配101—103。
#. ``_32_``、 ``$PMM`` 与 ``$PnP`` 结构的出现只发布调用契约，不证明其后依赖的
   PCI设备、PIR表、Option ROM或硬件控制器已经就绪。
#. PMM永久高端分配只有在实际请求且 ``ZoneHigh`` 失败后，才可能从
   ``ZoneTmpHigh`` 取得内存并添加E820保留项；本章没有发生PMM分配。
#. ``kbd_init()`` 只初始化BDA队列， ``mouse_init()`` 只设置equipment bit；PS/2与USB
   输入硬件均尚未初始化。

下一入口
--------

控制流回到 ``maininit()``，下一条真实调用是：

.. code-block:: c

   platform_hardware_setup();

``platform_hardware_setup()`` 将先执行 ``dma_setup()``；此时仍是BSP上的32位保护模式
POST上下文，分页关闭，具体设备线程尚不存在。

资料
----

* `SeaBIOS src/post.c：interface_init调用顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L101-L158>`_；
* `SeaBIOS src/boot.c：bootorder与QEMU CMOS优先级 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L241-L496>`_；
* `SeaBIOS src/pcibios.c：PCI BIOS服务与BIOS32头 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/pcibios.c#L27-L240>`_；
* `SeaBIOS src/romlayout.S：BIOS32与PCI 32位入口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S#L310-L355>`_；
* `SeaBIOS src/pmm.c：PMM分配与入口生命期 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/pmm.c#L19-L176>`_；
* `SeaBIOS src/pnpbios.c：PnP头与支持函数 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/pnpbios.c#L17-L88>`_；
* `SeaBIOS src/kbd.c：BDA键盘环形队列 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/kbd.c#L18-L105>`_；
* `SeaBIOS src/mouse.c：鼠标标志与EBDA状态 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/mouse.c#L16-L68>`_；
* `SeaBIOS src/Kconfig：软件接口默认配置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L390-L442>`_；
* `SeaBIOS Memory model <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Memory_Model.md>`_。
