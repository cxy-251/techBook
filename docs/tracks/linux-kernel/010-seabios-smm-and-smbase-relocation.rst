第十章：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？
====================================================

上一章结束时，SeaBIOS 已经完成 PCI 地址分配、INTx 路由和 q35/ICH9 设备解码。控制流回到：

::

   qemu_platform_setup()

接下来两条调用是：

.. code-block:: c

   smm_device_setup();
   smm_setup();

这一段第一次让 CPU 进入 System Management Mode，简称 SMM。SMM 不是 Linux 内核态，也不是普通的 x86
保护模式特权级。CPU 收到 System Management Interrupt，简称 SMI，之后会暂时离开当前执行环境，把寄存器状态
保存到一块专用内存，转去执行固件准备的 SMI handler。handler 最终执行 ``RSM``，CPU 才恢复被打断的环境。

本章沿下面的真实控制流前进：

::

   qemu_platform_setup()
   → smm_device_setup()
   → 从 PCIDevices 找到 q35 MCH 与 ICH9 LPC
   → 保存两者的 BDF
   → smm_setup()
   → ich9_lpc_apmc_smm_setup()
   → 临时打开 SMRAM 窗口
   → 在默认 SMM 入口安装跳板
   → 允许写 0xb2 产生 SMI
   → 触发第一次 SMI
   → CPU 在默认 SMBASE 下进入 SMM
   → handle_smi() 把 SMBASE 改到 0xa0000
   → RSM 返回正常执行
   → 在新 SMBASE 安装正式入口
   → 关闭普通软件对 SMRAM 的访问

本章结束在 ``smm_setup()`` 返回。此时 SMM 已经可以工作，普通 PCI 驱动和磁盘介质探测仍然没有开始。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

SMM 与普通中断不是同一套机制
----------------------------

前面已经见过两片 8259A、IRQ 和 IVT。普通硬件中断大致是：

::

   外设发出 IRQ
   → PIC 选择中断向量
   → CPU 查询 IVT 或 IDT
   → 跳到普通中断处理入口

SMI 不走这条路径。它具有独立的 CPU 进入机制：

::

   平台产生 SMI
   → CPU 保存当前机器状态到 SMM save-state area
   → CPU 进入 SMM
   → 从 SMBASE + 0x8000 取第一条 SMI handler 指令
   → handler 执行 RSM
   → CPU 恢复进入 SMM 前的状态

这里没有查询当前操作系统的 IDT，也不要求 Linux 提前安装中断门。SMI 对操作系统来说通常表现为一段无法直接解释的
停顿：CPU 暂停原来的代码，执行固件 handler，随后从原位置继续。

SMM 的特权来源也不只是 CPL 0。进入 SMM 后，CPU 使用专用的保存状态和地址环境；SMRAM 在完成配置后通常不会映射给
普通软件。即使以后 Linux 已经进入 ring 0，它也不会因为处于内核态就自然获得 SMRAM 的普通读写权限。

SeaBIOS 当前建立 SMM 的直接用途包括自己的 32 位调用跳板和传统平台管理接口。这里不把 SMM 泛化成所有物理主板的完整
管理固件实现；当前只追踪 QEMU q35 与这份 SeaBIOS 源码实际执行的路径。

smm_device_setup 只寻找设备，不会立即进入 SMM
----------------------------------------------

``smm_device_setup()`` 首先检查构建配置：

.. code-block:: c

   if (!CONFIG_USE_SMM)
       return;

启用 SMM 时，它从前面已经建立的 ``PCIDevices`` 链表寻找平台组合。源码支持两条主要路径：

::

   i440fx / PIIX4
   q35 / ICH9

当前固定平台是 q35，所以真正匹配的是：

.. code-block:: c

   isapci = pci_find_device(PCI_VENDOR_ID_INTEL,
                            PCI_DEVICE_ID_INTEL_ICH9_LPC);
   pmpci  = pci_find_device(PCI_VENDOR_ID_INTEL,
                            PCI_DEVICE_ID_INTEL_Q35_MCH);

名字中的 ``isapci`` 和 ``pmpci`` 是 SeaBIOS 沿用下来的内部变量名。当前 q35 路径对应的实际设备是：

``ICH9 LPC``
   位于南桥一侧，提供传统 LPC、ACPI PM、SMI 控制等平台功能。

``Q35 MCH``
   Memory Controller Hub，也是 PCI 根复合体的 host bridge。它控制本章需要使用的 SMRAM 映射寄存器。

找到两者后，SeaBIOS只保存 BDF：

.. code-block:: c

   SMMISADeviceBDF = isapci->bdf;
   SMMPMDeviceBDF  = pmpci->bdf;

这一步没有：

* 打开 SMRAM；
* 产生 SMI；
* 修改 SMBASE；
* 执行 SMI handler。

它只是把第七章发现的 PCI 身份信息转换成后续 SMM 代码可以直接使用的设备坐标。

smm_setup 根据设备 ID 选择 q35 路径
--------------------------------

下一条调用是：

.. code-block:: c

   smm_setup();

函数先检查：

.. code-block:: c

   if (!CONFIG_USE_SMM || SMMISADeviceBDF < 0)
       return;

如果平台设备没有匹配成功，SeaBIOS不会猜测寄存器位置，也不会强行触发 SMI。

设备存在时，``smm_setup()`` 读取先前保存 BDF 的 ``PCI_DEVICE_ID``。PIIX4 使用
``piix4_apmc_smm_setup()``；当前 ICH9 LPC 使用：

.. code-block:: c

   ich9_lpc_apmc_smm_setup(SMMISADeviceBDF,
                           SMMPMDeviceBDF);

两个实参分别是 ICH9 LPC 和 q35 MCH 的 BDF。后面的写寄存器操作因此都落到前面真实发现的虚拟 PCI function，不依赖
硬编码“它一定在某个槽位”的假设。

APMC 端口为什么能触发 SMI
------------------------

SeaBIOS 和 QEMU 约定两个传统 I/O port：

::

   0x00b2  PORT_SMI_CMD
   0x00b3  PORT_SMI_STATUS

``0xb2`` 常称为 APMC command port。SeaBIOS 会配置 ICH9，使对这个端口的写操作成为一种 SMI source。
``0xb3`` 在当前初始化流程中作为 SeaBIOS 与 SMI handler 之间的简易握手状态端口。

进入 setup 时，SeaBIOS 先读取 ICH9 PM I/O 空间中的 ``SMI_EN``：

.. code-block:: c

   value = inl(acpi_pm_base + ICH9_PMIO_SMI_EN);

如果 ``APMC_EN`` 已经打开，函数直接返回：

.. code-block:: c

   if (value & ICH9_PMIO_SMI_EN_APMC_EN)
       return;

这避免重复安装 SMM 环境。SMM 的入口地址、保存状态和 SMRAM 锁定都不是适合反复覆盖的普通临时配置。

SMRAM 为什么位于 0xa0000
----------------------

SeaBIOS 固定了两个地址：

::

   BUILD_SMM_INIT_ADDR = 0x30000
   BUILD_SMM_ADDR      = 0xa0000

``0x30000`` 是初次进入 SMM 时使用的默认 SMBASE。x86 SMI 入口位于：

::

   SMBASE + 0x8000

所以第一次 SMI 的入口地址是：

::

   0x30000 + 0x8000 = 0x38000

SeaBIOS 最终希望把 SMBASE 迁移到：

::

   0x000a0000

之后正式入口位于：

::

   0x000a0000 + 0x8000 = 0x000a8000

``0xa0000`` 在普通 PC 内存布局中还是传统 VGA window 的起点。这里需要区分两种访问视图：

``普通执行环境``
   ``0xa0000`` 通常属于 VGA/legacy 映射区域。

``SMM 环境``
   芯片组把同一地址范围切换成 SMRAM，CPU 在 SMM 中看到的是保存状态、栈和 SMI handler 数据。

相同数值地址不代表普通软件和 SMM 一定看到相同存储单元。q35 的 SMRAM 控制寄存器决定当前窗口是开放给普通访问，还是
只在 SMM 中可见。

为什么安装过程中必须临时打开 SMRAM
--------------------------------

最终状态下，普通软件不应直接修改 SMI handler。可是在安装 handler 时，SeaBIOS 当前仍处于普通 32 位保护模式，必须
先把代码和备份数据写入目标 SMRAM。

q35 路径执行：

.. code-block:: c

   pci_config_writeb(mch_bdf,
                     Q35_HOST_BRIDGE_SMRAM,
                     0x02 | 0x48);

源码把这一步描述为：

::

   enable the SMM memory window

窗口打开后，SeaBIOS 的普通执行代码才能通过 ``0xa0000`` 一带访问未来的 SMRAM 内容。

这里的“打开”只服务于安装过程，不表示最终允许 Linux 或 bootloader 随意访问 SMRAM。后面完成迁移后，SeaBIOS 会再次
修改同一寄存器，把普通访问关闭。

smm_layout 怎样组织两套入口和保存状态
----------------------------------

SeaBIOS 用 ``struct smm_layout`` 描述从 SMBASE 开始的一整块布局。关键部分可以简化为：

::

   SMBASE + 0x0000   backup1
   SMBASE + 0x0200   backup2
   SMBASE + 0x0400   A20 backup 与 SMM stack
   SMBASE + 0x8000   codeentry
   SMBASE + 0xfe00   CPU save-state area

``codeentry``
   CPU 响应 SMI 后开始取指的位置。

``cpu``
   CPU 自动保存进入 SMM 前寄存器状态的位置。具体字段布局取决于 32 位或 64 位 SMM save-state revision。

``backup1`` 与 ``backup2``
   SeaBIOS 在启用 ``CONFIG_CALL32_SMM`` 时保存两份 CPU 状态，用于在 SMM 中切换到指定 32 位执行上下文，再恢复原来的
   SMM 进入现场。

``stack``
   ``entry_smi`` 切换到 32 位模式后使用的专用栈空间。

这块布局不是 Linux 的 task stack，也不是 SeaBIOS 普通协作式线程栈。它只服务于 SMI 进入和 SMM 内部执行。

第一次 SMI 前先保存两处原始内存
----------------------------

SeaBIOS 调用：

.. code-block:: c

   smm_save_and_copy();

函数建立两个指针：

.. code-block:: c

   initsmm = (void *)0x30000;
   smm     = (void *)0xa0000;

接着把默认区域中稍后会被 CPU 保存状态覆盖的内容，复制到当前已经打开的 SMRAM：

.. code-block:: c

   memcpy(&smm->cpu, &initsmm->cpu, sizeof(smm->cpu));
   memcpy(&smm->codeentry, &initsmm->codeentry,
          sizeof(smm->codeentry));

然后只在默认 SMI 入口 ``0x38000`` 写入一段极短跳板：

.. code-block:: c

   initsmm->codeentry = SMI_INSN;

这段跳板对应：

.. code-block:: asm

   movw %cs, %ax
   ljmpw $SEG_BIOS, $entry_smi

第一条指令把当前 SMM 的 ``CS`` 保存到 ``AX``。第一次进入时，这个 segment 对应默认 SMBASE；后续迁移到 ``0xa0000``
以后，值也会随入口位置变化。第二条远跳转进入 SeaBIOS 位于 F-segment 的固定 ``entry_smi``。

为什么不把完整 handler 直接复制到 0x38000
--------------------------------------

SeaBIOS 的主要 16/32 位代码已经位于 BIOS 映射区。默认 SMM 入口只需要完成一个可靠的最小跳转：

::

   SMM 固定入口
   → 记录当前 SMM segment
   → 远跳入 SeaBIOS entry_smi

这样不需要在 ``0x38000`` 放置一份完整 C handler，也避免维护两套长代码副本。真正的模式切换和 C 调用仍复用 SeaBIOS
已有的汇编与 32 位代码。

ICH9 怎样允许写 0xb2 产生 SMI
---------------------------

安装默认入口后，SeaBIOS修改 ``ICH9_PMIO_SMI_EN``：

.. code-block:: c

   outl(value
        | ICH9_PMIO_SMI_EN_APMC_EN
        | ICH9_PMIO_SMI_EN_GLB_SMI_EN,
        acpi_pm_base + ICH9_PMIO_SMI_EN);

两个关键位是：

``APMC_EN``
   允许 APMC command port 成为 SMI source。

``GLB_SMI_EN``
   打开全局 SMI 生成。

只打开 APMC source 而没有全局开关，写 ``0xb2`` 仍不能形成完整 SMI。SeaBIOS 一次设置两者。

随后又读取 ICH9 LPC 的 ``GEN_PMCON_1``，设置：

::

   SMI_LOCK

这一位用于锁住 SMI 相关配置，避免后续普通软件重新改写关键使能状态。当前实现不是等到 Linux 启动后再锁，而是在 SMM
安装阶段立即完成。

SeaBIOS 怎样主动制造第一次 SMI
----------------------------

入口和触发条件准备好后，调用：

.. code-block:: c

   smm_relocate_and_restore();

第一步先写状态端口：

.. code-block:: c

   outb(0x01, 0x00b3);

然后写 command port：

.. code-block:: c

   outb(0x00, 0x00b2);

第二次写操作触发 SMI。此刻 BSP 正在执行 SeaBIOS 的普通 32 位 C 代码。SMI 到来后，CPU 不从下一条 C 指令继续，而是：

::

   把当前状态保存到 0x30000 + 0xfe00
   → 从 0x30000 + 0x8000 取指
   → 执行 mov CS, AX
   → 远跳到 SeaBIOS entry_smi

普通执行流程暂时被冻结，直到 SMI handler 执行 ``RSM``。

entry_smi 怎样从 SMM 入口进入 32 位 C
-----------------------------------

``src/romlayout.S`` 中的入口是：

.. code-block:: asm

   entry_smi:
       movl $1f + BUILD_BIOS_ADDR, %edx
       jmp transition32_nmi_off
       .code32
   1:
       movl $BUILD_SMM_ADDR + 0x8000, %esp
       calll _cfunc32flat_handle_smi - BUILD_BIOS_ADDR
       rsm

CPU刚进入 SMM 时并不直接处于 SeaBIOS 平时使用的 32 位 flat C 环境。``transition32_nmi_off`` 会装入 SeaBIOS 的 GDT，
设置 ``CR0.PE``，通过远跳转进入 32 位代码段。

进入 32 位代码后，栈顶设置为：

::

   BUILD_SMM_ADDR + 0x8000
   = 0xa0000 + 0x8000
   = 0xa8000

然后调用：

.. code-block:: c

   handle_smi(cs);

传入的 ``cs`` 来自跳板先前执行的 ``movw %cs, %ax``。因此 C 代码能判断本次 SMI 是从默认 SMBASE 进入，还是已经从迁移后的
SMBASE 进入。

handle_smi 怎样识别第一次进入
---------------------------

``handle_smi()`` 把传入 segment 转成 flat pointer：

.. code-block:: c

   struct smm_layout *smm = MAKE_FLATPTR(cs, 0);

第一次进入时：

::

   smm == (void *)BUILD_SMM_INIT_ADDR
       == 0x30000

函数因此进入 relocation 分支。

CPU save-state area 带有 SMM revision 字段。SeaBIOS 支持两种当前布局：

::

   SMM_REV_I32 = 0x00020000
   SMM_REV_I64 = 0x00020064

这里的 I64 表示 CPU 使用 64 位形式的 SMM save-state layout，不代表当前 SeaBIOS 正在 long mode 中执行。当前主线普通代码仍是
32 位保护模式；SeaBIOS只是需要根据 CPU 实际保存格式找到正确的 ``smm_base`` 字段。

修改保存状态就能迁移 SMBASE
-------------------------

32 位布局执行：

.. code-block:: c

   smm->cpu.i32.smm_base = BUILD_SMM_ADDR;

64 位布局执行：

.. code-block:: c

   smm->cpu.i64.smm_base = BUILD_SMM_ADDR;

写入值都是：

::

   BUILD_SMM_ADDR = 0xa0000

SeaBIOS没有直接写一个普通 MSR 来迁移 SMBASE，而是修改 CPU 已经生成的 SMM save-state area。稍后 ``RSM`` 恢复现场时，CPU
接受这份更新，从而让下一次 SMI 使用新的 SMBASE。

完成修改后，handler 写：

.. code-block:: c

   outb(0x00, PORT_SMI_STATUS);

也就是把 ``0xb3`` 从 1 改回 0。普通执行环境中的 ``smm_relocate_and_restore()`` 正在轮询这个端口：

.. code-block:: c

   while (inb(PORT_SMI_STATUS) != 0x00)
       ;

因此状态清零同时承担两层含义：

* SMI handler 已经真实执行；
* SMBASE save-state 字段已经修改完成。

RSM 怎样回到被打断的 SeaBIOS
-------------------------

``handle_smi()`` 返回汇编入口后，下一条指令是：

.. code-block:: asm

   rsm

``RSM`` 不是普通 ``ret``，也不是 ``iret``。它专门用于退出 SMM：

::

   从 SMM save-state area 恢复寄存器和执行状态
   → 应用修改后的 SMBASE
   → 离开 SMM
   → 回到触发 SMI 前被暂停的普通代码

所以 ``outb(0x00, 0xb2)`` 看起来像一个普通 I/O 指令，实际执行过程中间发生了一整次隐藏的 CPU 模式切换。等该指令返回后，
SeaBIOS 已经完成一次 SMM 往返。

为什么还要恢复 0x30000 的原始内容
------------------------------

第一次 SMI 会在默认区域写入：

* ``0x38000`` 的入口跳板；
* ``0x3fe00`` 附近的 CPU save-state。

这些地址属于普通低端 RAM，不应永久保留为 SMM 工作区。返回普通执行后，SeaBIOS把先前暂存在 ``0xa0000`` SMRAM 中的内容复制
回 ``0x30000`` 区域：

.. code-block:: c

   memcpy(&initsmm->cpu, &smm->cpu, sizeof(initsmm->cpu));
   memcpy(&initsmm->codeentry, &smm->codeentry,
          sizeof(initsmm->codeentry));

这里恢复的是第一次 SMI 为迁移而借用的默认区域。恢复完成后，普通低端 RAM 不再承担正式 SMI handler 的职责。

正式入口安装在 0xa8000
-------------------

接着 SeaBIOS 在迁移后的布局中写入同一个跳板：

.. code-block:: c

   smm->codeentry = SMI_INSN;

现在 ``smm`` 指向 ``0xa0000``，``codeentry`` 位于 offset ``0x8000``，所以写入位置是：

::

   0xa8000

下一次 SMI 将执行：

::

   CPU 使用 SMBASE 0xa0000
   → 从 0xa8000 取跳板
   → 进入 SeaBIOS entry_smi
   → 使用 0xa8000 附近的 SMM 专用布局和栈

SeaBIOS 最后执行：

.. code-block:: c

   wbinvd();

``WBINVD`` 会写回并失效 CPU cache，确保刚刚修改的 SMRAM 入口和相关数据不会只停留在旧缓存视图中。SMM 映射即将被关闭，
在改变可见性前刷新缓存可以避免处理器继续使用不一致内容。

关闭 SMRAM 后普通软件看不到 handler
--------------------------------

迁移结束后，q35 路径再次写 host bridge 的 SMRAM 控制寄存器：

.. code-block:: c

   pci_config_writeb(mch_bdf,
                     Q35_HOST_BRIDGE_SMRAM,
                     0x02 | 0x08);

源码描述为：

::

   close the SMM memory window and enable normal SMM

这时 ``0xa0000`` 对普通执行环境恢复为传统平台映射视图；SMRAM 中的 handler、栈和保存状态只在 SMM 进入后使用。

因此“把 handler 放在 0xa8000”不能理解成 Linux 以后直接读物理地址 ``0xa8000`` 就能看到相同字节。地址译码受当前 CPU 模式
和 q35 SMRAM 状态共同控制。

SMM 安装完成不代表设备驱动已经运行
--------------------------------

``smm_setup()`` 返回时，SeaBIOS已经完成：

* 找到 q35 MCH 和 ICH9 LPC；
* 配置 APMC 写操作产生 SMI；
* 锁定 SMI 使能配置；
* 临时打开 SMRAM；
* 在默认 ``0x38000`` 安装迁移跳板；
* 主动触发第一次 SMI；
* 把 SMBASE 从 ``0x30000`` 改到 ``0xa0000``；
* 在 ``0xa8000`` 安装正式入口；
* 恢复默认低端 RAM 内容；
* 关闭普通环境对 SMRAM 的访问。

尚未完成：

* MTRR 内存类型配置；
* AP 启动和 CPU 数量确认；
* ACPI、SMBIOS、MP table；
* ATA、AHCI、NVMe、USB、virtio 和网络设备驱动；
* 磁盘扇区读取；
* 启动介质选择；
* GRUB 加载。

第十章结束时的机器状态
--------------------

控制权目前走过：

::

   qemu_platform_setup()
   → pci_setup() 返回
   → smm_device_setup()
   → 找到 ICH9 LPC 与 q35 MCH
   → smm_setup()
   → ich9_lpc_apmc_smm_setup()
   → 打开 SMRAM window
   → 在 0x38000 安装临时 SMI 跳板
   → 打开 APMC_EN 与 GLB_SMI_EN
   → 设置 SMI_LOCK
   → 写 0xb2 触发第一次 SMI
   → entry_smi
   → handle_smi()
   → 修改 save-state 中的 SMBASE = 0xa0000
   → RSM
   → 恢复 0x30000 默认区域
   → 在 0xa8000 安装正式入口
   → WBINVD
   → 关闭普通 SMRAM window
   → smm_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前 CPU：BSP；
* 普通执行模式：32 位保护模式；
* 分页：关闭；
* SMM：已经完成一次真实进入和退出；
* 默认 SMBASE ``0x30000``：只用于首次迁移，原始内容已经恢复；
* 正式 SMBASE：``0xa0000``；
* 正式 SMI entry：``0xa8000``；
* SMM save-state：位于正式 SMBASE 布局高端；
* SMRAM：普通执行环境窗口已经关闭；
* APMC port ``0xb2``：已经可产生 SMI；
* SMI enable：已经锁定；
* PCI 资源与地址解码：已经完成；
* MTRR：尚未配置；
* 其他 CPU：尚未由 SeaBIOS 启动；
* 固件表：尚未建立；
* 存储和 USB 驱动：尚未探测介质；
* ``BootList``：尚无具体启动设备；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``smm_setup()`` 返回后，``qemu_platform_setup()`` 的下一条调用是：

.. code-block:: c

   mtrr_setup();

下一段将处理 Memory Type Range Registers，明确哪些物理范围按 write-back、uncacheable 等内存类型访问；随后还会设置
``MSR_IA32_FEATURE_CONTROL`` 并进入 ``smp_setup()``，让 BSP 唤醒其他虚拟 CPU。

资料
----

* `SeaBIOS src/fw/smm.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smm.c>`_；
* `SeaBIOS src/romlayout.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S>`_；
* `SeaBIOS src/fw/paravirt.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.h>`_；
* `SeaBIOS src/fw/dev-q35.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/dev-q35.h>`_；
* `SeaBIOS src/config.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_；
* `Intel 64 and IA-32 Architectures Software Developer Manuals <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_。