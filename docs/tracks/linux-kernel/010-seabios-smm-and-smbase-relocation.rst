第十章：SeaBIOS怎样判定SMM可用并在可用时迁移SMBASE？
=====================================================

上一章停在 ``pci_setup()`` 返回后。BSP仍在SeaBIOS POST的32位保护模式中执行，
分页关闭、A20开启、IF=0，NMI继续由CMOS index bit 7屏蔽；PIC只放行master IRQ2与
slave IRQ13。 ``PCIDevices`` 已经包含Q35 MCH和ICH9 LPC，下一段同步调用是：

::

   qemu_platform_setup()
   → smm_device_setup()
   → smm_setup()

SeaBIOS默认QEMU构建启用 ``CONFIG_USE_SMM`` 和 ``CONFIG_CALL32_SMM``，但这还不能
推出CPU一定会进入SMM。当前固定条件没有规定QEMU加速器，也没有把machine属性
``smm`` 固定为 ``on``。QEMU把它初始化成 ``auto``：TCG与qtest提供SMM；KVM只有
``KVM_CAP_X86_SMM`` 可用时提供SMM；其他不支持SMM的执行后端在auto模式下关闭它。

这条能力判断会同时传给Q35 host bridge的 ``smm-ranges`` 和ICH9 LPC的
``smm-enabled``。ICH9复位时，如果SMM不可用，QEMU预先设置
``SMI_EN.APMC_EN``，源码注释明确说这是把SMM标成“已经初始化”，阻止固件再运行
SMM。因而本章必须保留两个出口：能力可用时执行一次SMBASE迁移；能力不可用时
SeaBIOS看到标记后跳过。把前一条写成无条件历史，会让后面所有状态从这里开始漂移。

smm_device_setup只把PCI身份交给SMM代码
-----------------------------------------

``smm_device_setup()`` 先受 ``CONFIG_USE_SMM`` 约束，再从已有
``PCIDevices`` 链表查找支持的平台组合。它先尝试i440fx/PIIX4；固定q35机器匹配：

.. code-block:: c

   isapci = pci_find_device(PCI_VENDOR_ID_INTEL,
                            PCI_DEVICE_ID_INTEL_ICH9_LPC);
   pmpci = pci_find_device(PCI_VENDOR_ID_INTEL,
                           PCI_DEVICE_ID_INTEL_Q35_MCH);

两者同时存在时，只保存：

.. code-block:: c

   SMMISADeviceBDF = isapci->bdf;
   SMMPMDeviceBDF  = pmpci->bdf;

这里的 ``SMMISADeviceBDF`` 指向ICH9 LPC， ``SMMPMDeviceBDF`` 指向Q35 MCH。
没有SMRAM写入，没有SMI，也没有CPU模式切换；执行者始终是BSP上的MainThread。

``smm_setup()`` 再检查构建开关和BDF，读取LPC的device ID，并为固定ICH9设备调用：

::

   ich9_lpc_apmc_smm_setup(SMMISADeviceBDF, SMMPMDeviceBDF)

如果设备查找失败，函数直接返回；固定q35创建了这两个function，所以fresh boot中的
分歧发生在下一次 ``SMI_EN`` 读取。

APMC_EN把成功路径与跳过路径分开
--------------------------------

ICH9 PM I/O空间的 ``SMI_EN`` 已由上一章配置好的 ``acpi_pm_base`` 定位。SeaBIOS
先读取该寄存器：

.. code-block:: c

   value = inl(acpi_pm_base + ICH9_PMIO_SMI_EN);
   if (value & ICH9_PMIO_SMI_EN_APMC_EN)
       return;

在本书的fresh QEMU实例中，这个测试有明确的两种含义：

* QEMU判定SMM不可用时，ICH9复位代码已经置位 ``APMC_EN``；SeaBIOS立即返回，
  不打开SMRAM、不安装入口、不触发SMI；
* QEMU判定SMM可用时，ICH9复位值没有该位，SeaBIOS继续完成下面的安装流程。

这个单一bit本身没有携带原因。一般情况下它也可能表示先前代码已经初始化过SMM；
SeaBIOS在这里不重新验证SMBASE或handler。当前fresh boot之所以能解释分支，是因为
QEMU复位路径和初始化顺序都已固定。

成功路径先借用两个地址布局
--------------------------

继续执行时，SeaBIOS使用两个SMBASE常量：

::

   BUILD_SMM_INIT_ADDR = 0x00030000
   BUILD_SMM_ADDR      = 0x000a0000

x86从 ``SMBASE + 0x8000`` 取得SMI第一条指令，所以默认入口是 ``0x38000``，迁移后
入口是 ``0xa8000``。 ``struct smm_layout`` 从各自SMBASE起组织为：

::

   +0x0000  backup1（0x200 bytes）
   +0x0200  backup2（0x200 bytes）
   +0x0400  A20 backup，随后是stack
   +0x8000  8-byte codeentry
   +0xfe00  CPU save-state（0x200 bytes）

``backup1``、 ``backup2`` 与A20字段服务于默认开启的 ``CALL32_SMM`` trampoline；
这不是普通SeaBIOS线程栈。 ``entry_smi`` 把ESP设为 ``0xa8000``，栈向低地址增长，
因此即使第一次SMI从默认 ``0x38000`` 进入，C handler也使用目标SMRAM布局里的栈。

为了让普通POST代码能够写目标区，SeaBIOS先把Q35 ``SMRAM`` 寄存器写成 ``0x4a``：

::

   C_BASE=2 | G_SMRAME | D_OPEN

QEMU据此让A0000—BFFFF窗口在普通地址空间可访问。 ``smm_save_and_copy()`` 随后把
默认布局中将被CPU覆盖的 ``cpu`` save-state原字节和 ``codeentry`` 原8字节复制到
目标布局，再只把默认 ``0x38000`` 的8字节替换成 ``SMI_INSN``：

::

   movw %cs, %ax
   ljmpw $SEG_BIOS, $entry_smi

第一条指令保留当前SMM segment，远跳则复用BIOS映射中的入口代码。默认区不需要
长期保存一份完整handler。

SeaBIOS写两个SMI_EN位，但固定QEMU只以APMC_EN触发
--------------------------------------------------

入口准备好后，SeaBIOS把此前读到的 ``SMI_EN`` 加上：

::

   ICH9_PMIO_SMI_EN_APMC_EN
   ICH9_PMIO_SMI_EN_GLB_SMI_EN

然后在ICH9 ``GEN_PMCON_1`` 中设置 ``SMI_LOCK``。这三个动作不能被概括成“整个SMM
配置已经锁死”。在固定QEMU实现中：

* APM command回调只检查 ``APMC_EN``，没有再次以 ``GLB_SMI_EN`` 为门；
* ``SMI_LOCK`` 使锁位自身不可再清除，并从 ``SMI_EN`` 写掩码中去掉bit 0，锁住的是
  ``GLB_SMI_EN``；
* ``APMC_EN`` 和 ``SMI_EN`` 的其他位没有因此全部变成只读；
* Q35 MCH的SMRAM窗口锁 ``D_LCK`` 是另一套寄存器语义，本路径尚未设置它。

SeaBIOS确实同时写入APMC与global enable；这里只是不能把硬件手册的泛化模型覆盖到
固定QEMU回调的实际判断上。

写0xb2让当前BSP进入第一次SMI
---------------------------

``smm_relocate_and_restore()`` 先把状态端口 ``0xb3`` 写成1，再把command端口
``0xb2`` 写成0：

.. code-block:: c

   outb(0x01, PORT_SMI_STATUS);
   outb(0x00, PORT_SMI_CMD);

命令0不是QEMU特殊处理的ACPI enable/disable值。ICH9回调看到 ``APMC_EN`` 后，默认
没有协商broadcast feature，于是对 ``current_cpu`` 注入SMI；此刻current CPU就是
BSP。SMI不经过8259A，不消费PIC vector，也不依赖IF=1。CPU把普通执行现场写进默认
``0x3fe00`` save-state，从 ``0x38000`` 执行刚安装的跳板。

``entry_smi`` 沿 ``transition32_nmi_off`` 装入SeaBIOS GDT/IDT，清除CR0中的PG、CD、
NW并设置PE，进入32位flat代码。该入口名中的 ``nmi_off`` 表示调用者已经处在NMI关闭
条件；它从这个label开始，不会再次写CMOS。随后：

.. code-block:: asm

   movl $BUILD_SMM_ADDR + 0x8000, %esp
   calll handle_smi
   rsm

传入 ``handle_smi(cs)`` 的CS来自默认跳板保存的AX，所以 ``MAKE_FLATPTR(cs, 0)``
得到当前SMBASE布局。

handle_smi通过save-state迁移SMBASE
---------------------------------

第一次进入满足 ``smm == 0x30000``。SeaBIOS读取save-state revision的低位格式，
只接受：

::

   SMM_REV_I32 = 0x00020000
   SMM_REV_I64 = 0x00020064

I64表示64位save-state布局，不表示POST主控制流已经进入long mode。两个支持分支都把
对应布局中的 ``smm_base`` 写成 ``0xa0000``，然后清零 ``0xb3``，向普通环境公布迁移
已经执行。

默认 ``CONFIG_CALL32_SMM=y`` 时，handler还把当前CPU save-state分别复制到目标布局
的 ``backup1`` 和 ``backup2``，并设置全局 ``HaveSmmCall32=1``。这些副本给未来
``CALL32SMM_CMDID`` 往返使用；本次迁移不在这里执行任意设备驱动。

revision若既不是I32也不是I64， ``handle_smi`` 只调用 ``warn_internalerror()`` 后
返回，没有清零 ``0xb3``。汇编仍执行 ``RSM``，但普通环境随后永久停在：

.. code-block:: c

   while (inb(PORT_SMI_STATUS) != 0x00)
       ;

这里没有timeout，也没有恢复窗口的失败回滚。本章后续“成功出口”明确以revision受支持
为条件。

RSM返回后恢复默认RAM并关闭当前窗口
---------------------------------

成功handler返回到 ``entry_smi`` 后执行 ``RSM``。CPU从save-state恢复进入SMI前的
寄存器、CR0和指令位置，并采用已更新的SMBASE；BSP继续执行原来的
``smm_relocate_and_restore()``，IF与NMI屏蔽状态也回到进入前的值。

轮询看到 ``0xb3=0`` 后，SeaBIOS从目标区的备份恢复默认 ``0x30000`` 布局中被借用的
save-state与 ``0x38000`` 原8字节；再把 ``SMI_INSN`` 写到目标 ``0xa8000``，执行
``wbinvd()``。从此下一次SMI使用SMBASE ``0xa0000``，而默认低端RAM不再承担入口。

最后Q35 ``SMRAM`` 寄存器写成 ``0x0a``： ``G_SMRAME`` 保持、 ``D_OPEN`` 清除，
当前普通地址空间不再直接看到目标SMRAM窗口。这个值不含 ``D_LCK``，所以准确状态是
“窗口已经关闭”，不是“Q35窗口寄存器永久锁定”。本章也不能由当前关闭状态推导出
未来ring 0代码绝无可能重新编程host bridge。

随后 ``ich9_lpc_apmc_smm_setup()``、 ``smm_setup()`` 依次返回。没有调度、没有新
SeaBIOS线程；成功路径中只有BSP发生一次同步SMI/RSM往返。

本章结束状态
------------

共同状态：

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：普通出口为32位保护模式，分页关闭、A20开启、IF=0；
* NMI/PIC：CMOS仍屏蔽NMI；PIC mask仍只放行IRQ2与IRQ13；
* Q35 MCH与ICH9 LPC BDF：已由 ``smm_device_setup()`` 记录；
* PCI资源与 ``PCIDevices``：保持第009章结果；
* MTRR、FEATURE_CONTROL与SMP扫描：尚未由后续调用处理；
* SeaBIOS线程：仍只有MainThread；
* GRUB/Linux：均未装入。

若QEMU SMM能力可用且save-state revision受支持：

* BSP完成一次SMI/RSM；
* SMBASE：从 ``0x30000`` 迁移到 ``0xa0000``；
* permanent SMI entry： ``0xa8000`` 的 ``SMI_INSN``；
* 默认 ``0x30000`` save-state和 ``0x38000`` 原内容：已恢复；
* ``HaveSmmCall32=1``；
* ``SMI_EN.APMC_EN=1``、 ``GLB_SMI_EN=1``；后者被ICH9 ``SMI_LOCK`` 锁定；
* Q35 SMRAM：普通窗口当前关闭，但 ``D_LCK`` 未设置。

若QEMU SMM能力不可用：

* ICH9复位预置 ``SMI_EN.APMC_EN=1``；
* SeaBIOS在第一次测试处返回，没有触发SMI；
* 本章没有迁移SMBASE、没有安装 ``0xa8000`` 入口，也没有置
  ``HaveSmmCall32``；
* Q35没有启用SMM ranges。

若能力可用但save-state revision不受支持，BSP停在状态端口轮询，没有本章返回出口。

关键边界
--------

#. SeaBIOS的构建开关不等于QEMU执行后端一定提供SMM；固定条件必须保留能力分支。
#. fresh boot中 ``APMC_EN`` 既是成功路径要设置的source enable，也是QEMU关闭SMM时
   预置给SeaBIOS的跳过标记。
#. SMI由ICH9 APM回调注入当前BSP，不经过PIC，也不要求普通IF已打开。
#. 第一次入口是 ``0x38000``；handler通过修改CPU save-state里的 ``smm_base`` 让
   ``RSM`` 接受 ``0xa0000``。
#. ``HaveSmmCall32`` 只在成功revision分支设置。
#. 不支持的revision会让BSP永久轮询；代码没有timeout或事务回滚。
#. ICH9 ``SMI_LOCK`` 只锁住它自身和 ``GLB_SMI_EN`` 写位，不锁整个 ``SMI_EN``。
#. SeaBIOS用 ``0x0a`` 关闭Q35 SMRAM窗口，但没有设置MCH ``D_LCK``。
#. SMM成功或跳过都不启动设备驱动、不创建AP，也不改变MainThread调度状态。

下一入口
--------

``smm_setup()`` 正常返回后的下一条调用在两种正常分支中相同：

::

   qemu_platform_setup()
   → mtrr_setup()

下一章从BSP读取CPUID ``MTRR``/``MSR`` 能力和 ``MSR_MTRRcap`` 开始；SMM成功与否
不会改变这条调用顺序。

资料
----

* `SeaBIOS固定提交：SMM发现、迁移与q35设置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smm.c#L70-L278>`_
* `SeaBIOS固定提交：SMI汇编入口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S#L190-L200>`_
* `SeaBIOS固定提交：SMM地址常量 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_
* `SeaBIOS固定提交：默认SMM构建选项 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L347-L360>`_
* `QEMU固定提交：SMM auto能力判定 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/x86.c#L166-L188>`_
* `QEMU固定提交：q35传递SMM能力 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L215-L246>`_
* `QEMU固定提交：ICH9复位时的SMM跳过标记 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/ich9.c#L251-L266>`_
* `QEMU固定提交：APM command触发当前CPU SMI <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/isa/lpc_ich9.c#L463-L486>`_
* `QEMU固定提交：SMI_LOCK写掩码 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/isa/lpc_ich9.c#L532-L553>`_
* `QEMU固定提交：Q35 SMRAM窗口与D_LCK <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/pci-host/q35.c#L351-L388>`_
