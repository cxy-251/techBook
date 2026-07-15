第十二章：SeaBIOS怎样扫描CPU并在存在AP时用INIT/SIPI启动它们？
=========================================================

上一章停在 ``msr_feature_control_setup()`` 返回后。BSP仍是SeaBIOS MainThread的唯一
执行者； ``smp_msr`` 最多保存32项已经对BSP执行过的MSR写入，但只有日志未截断时，
它才是完整的AP模板。下一条调用是：

::

   qemu_platform_setup()
   → smp_setup()

当前固定配置没有规定 ``-smp``，所以present vCPU数不能唯一确定。固定QEMU源码把通用
machine class的 ``default_cpus`` 缺省为1，并用它初始化 ``smp.cpus`` 与
``smp.max_cpus``；没有额外命令行时，q35实例只有BSP，显式 ``-smp`` 则可创建AP。
这并不让 ``smp_setup()`` 消失：有local APIC时，
SeaBIOS仍安装临时跳板、配置BSP local APIC并广播INIT/SIPI，只是没有AP接收。

本章把QEMU缺省单CPU出口与显式 ``-smp`` 产生的多CPU出口
分开。不能先把“代码支持AP”写成“本次必有AP”，再让后续Linux章节假定CPU0是唯一
online CPU。

present CPU数与etc/max-cpus不是一个量
--------------------------------------

``smp_setup()`` 先读取：

.. code-block:: c

   MaxCountCPUs = romfile_loadint("etc/max-cpus", 0);
   u16 smp_count = qemu_get_present_cpus_count();
   if (MaxCountCPUs < smp_count)
       MaxCountCPUs = smp_count;

``qemu_get_present_cpus_count()`` 从 ``FW_CFG_NB_CPUS`` 取得16位在场CPU数；RTC存在
时还读取 ``CMOS_BIOS_SMP_COUNT + 1``，取两者较大值。fresh QEMU机器至少包含BSP；
无 ``-smp`` override时该结果为1，显式多CPU配置时则是对应present count。

``etc/max-cpus`` 对应 ``FW_CFG_MAX_CPUS``。固定QEMU源码明确说明，x86为了兼容旧
SeaBIOS接口，这个名字实际传递的是 ``apic_id_limit``：所有可能CPU的APIC ID都小于
它。它可以因为 ``maxcpus``、拓扑空洞或热插拔范围而大于当前present CPU数。因此：

``smp_count``
   QEMU/CMOS宣告本次应报到的在场CPU数量。

``CountCPUs``
   SeaBIOS在本轮实际完成登记的CPU计数。

``MaxCountCPUs``
   至少不小于present count的APIC-ID描述上界；后续表构造用它选择xAPIC/x2APIC与
   legacy table边界。

把 ``MaxCountCPUs`` 直接翻译为“最大CPU数量”会在稀疏APIC ID拓扑中产生错误表意。

没有local APIC时只登记BSP并返回
--------------------------------

``smp_scan()`` 读取CPUID leaf 1。如果版本字段不满足测试，或EDX没有 ``CPUID_APIC``，
它执行：

.. code-block:: c

   CountCPUs = 1;
   return;

这个出口不写 ``0x10000``，不配置LINT，不发送IPI，也不调用 ``yield()``。固定q35的
正常x86-64 CPU提供local APIC，所以下面的APIC路径适用；“是否有AP”仍由present count
决定。

0x10000只在本轮扫描期间保存远跳转
---------------------------------

APIC路径先令 ``CountCPUs=1`` 把BSP计入，再保存物理地址 ``0x10000`` 的原8字节。
SeaBIOS用 ``BUILD_AP_BOOT_ADDR=0x10000`` 构造一条16位far jump：

::

   ljmpw $SEG_BIOS, $(entry_smp - BUILD_BIOS_ADDR)

机器码写入 ``0x10000``。SIPI的8位vector按 ``vector << 12`` 形成起始物理地址，
所以SeaBIOS稍后发送 ``0x10``，接收者从 ``0x10000`` 取这条跳转并进入BIOS映射中的
``entry_smp``。该低端页不是永久AP固件区；扫描正常完成后原8字节会恢复。

BSP启用local APIC并只改变LINT接线
---------------------------------

SeaBIOS以 ``BUILD_APIC_ADDR`` 定位BSP local APIC，先在SVR中保留原值并设置bit 8，
打开software enable。随后写：

::

   LINT0 = 0x8700   ExtINT, level-triggered
   LINT1 = 0x8400   NMI,    level-triggered

LINT0把传统8259A输出接入local APIC；它没有解除第009章留下的PIC mask，也没有把BSP
的IF改成1。LINT1只是规定未来输入的delivery mode，本章没有生成NMI。CMOS index
bit 7的NMI屏蔽状态也没有在这里改写。

INIT与一个SIPI发给all-excluding-self
----------------------------------

BSP把 ``SMPLock`` 写成1，先阻止潜在AP使用当前栈；经过compiler barrier后，依次向
ICR low写：

::

   0x000c4500          INIT,    all excluding self
   0x000c4600 | 0x10   Startup, all excluding self, vector 0x10

代码发送一个INIT和一个SIPI，没有为每个AP逐一寻址，也没有在两次写入之间轮询delivery
status。缺省单CPU实例中目标集合为空：写寄存器仍发生，但没有第二个CPU从0x10000
执行。显式配置多个present vCPU时，所有AP收到相同vector并竞争同一个入口。

SeaBIOS在发出IPI后才调用 ``apic_id_init()`` 登记BSP。这个顺序让IPI继续通过xAPIC
MMIO发送；若 ``MaxCountCPUs >= 256`` 且CPUID提供x2APIC，BSP随后才设置
``IA32_APIC_BASE.EXTD`` 并从x2APIC ID MSR读取自身ID。

``MaxCountCPUs < 256`` 时，ID来自 ``CPUID.1:EBX[31:24]``，并在256-bit
``FoundAPICIDs`` 中置位。需要更大ID范围但CPUID没有x2APIC时，函数返回 ``-1``；
扫描计数仍可继续，但后续不能把该无效ID假装成legacy 8-bit记录。

缺省单CPU路径不会执行entry_smp
--------------------------------

BSP再次读取present count作为 ``expected_cpus_count``。无 ``-smp`` override时：

::

   expected_cpus_count = 1
   CountCPUs            = 1

所以等待循环一次也不进入。 ``SMPStack`` 没有发布给其他CPU， ``handle_smp()`` 没有
调用， ``smp_write_msrs()`` 也没有重放。代码仍调用一次 ``yield()``；第009章以来没有
创建其他SeaBIOS线程，因此MainThread没有可切换的peer，控制权仍回到自己。

随后BSP把保存的8字节写回 ``0x10000``。这个出口中local APIC已经配置、扫描完成，
但不存在“AP已停在HLT”的对象。若固定运行命令含显式 ``-smp``，则走下面的多CPU
出口，不能用早期Linux只有CPU0 online反推固件阶段没有present AP；Linux会在自己的
``smp_init()`` 之前保持AP offline。

多CPU时AP先进入32位模式，再串行借用BSP栈
-------------------------------------------

只有 ``expected_cpus_count > 1`` 且AP实际响应SIPI时，AP执行：

::

   0x10000 far jump
   → entry_smp
   → transition32_nmi_off

``entry_smp`` 先 ``cli``、 ``cld``，再从 ``transition32_nmi_off`` label装入SeaBIOS
IDT/GDT、设置CR0.PE、进入32位flat segments。该label不会再次操作CMOS NMI位，也
不会给AP复制BSP调用栈。

32位入口用 ``lock btsl $0, SMPLock`` 竞争bit 0。锁仍为1时AP自旋；得到0并原子置1的
AP从 ``SMPStack`` 载入ESP，然后调用 ``handle_smp()``。所有AP共享这一栈，因而同一
时刻只能有一个进入C代码。

BSP的等待循环负责交出栈：

::

   SMPStack = BSP.ESP
   SMPLock  = 0
   → BSP用lock bts反复尝试重新取得锁

一次释放不保证某个AP一定先于BSP抢到；BSP可能立刻重取。只要计数尚未相等，循环就
再次发布栈并释放锁。AP成功取得锁后，BSP在它使用共享栈期间无法重取；AP释放后，
BSP或另一个AP继续竞争。

handle_smp登记ID、重放已记录MSR并计数
------------------------------------

取得栈的AP依次执行：

::

   apic_id_init()
   → smp_write_msrs()
   → CountCPUs++

APIC ID走与BSP相同的xAPIC/x2APIC条件。 ``smp_write_msrs()`` 只遍历
``smp_msr_count``，按数组顺序执行 ``wrmsr``。若第011章日志完整，AP得到相同的MTRR
序列与条件FEATURE_CONTROL；若日志因32项上限截断，AP只得到前缀，不能宣称与BSP
一致。

``CountCPUs++`` 本身不是原子指令，但它位于 ``SMPLock`` 串行区内，同一时刻只有一
个AP修改。handler返回后汇编把 ``SMPLock=0``，然后在IF=0下永久执行：

::

   hlt
   jmp hlt

AP不会落入BSP的POST主流程。以后操作系统若要使用它，需要自己的启动协议让它离开
这段固件停驻代码。

BSP等待精确相等，没有timeout
----------------------------

多CPU路径的退出条件是：

.. code-block:: c

   while (expected_cpus_count != CountCPUs)
       release_stack_and_reacquire();

这是精确不等比较，不是 ``CountCPUs < expected``。少一个AP、AP在MSR重放时异常、
或意外多计数都会让BSP永久循环；代码没有deadline、退化为较少CPU或失败回滚。正常
条件下，每个在场AP恰好递增一次，计数最终相等，BSP调用 ``yield()`` 并恢复
``0x10000`` 原字节。

恢复跳板只撤销SeaBIOS临时入口，不会唤醒或终止已经停驻的AP。多CPU正常出口中，AP
仍停在 ``entry_smp`` 的HLT循环；缺省单CPU出口中从未有AP进入。

本章结束状态
------------

共同状态：

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：BSP处于32位保护模式，分页关闭、A20开启、IF=0；
* ``MaxCountCPUs``：保存QEMU APIC-ID上界，并保证不小于present count；
* BSP local APIC：SVR software enable已置位；LINT0=ExtINT，LINT1=NMI；
* PIC/NMI：PIC mask与CMOS NMI mask未被本章解除；
* ``FoundAPICIDs``：正常APIC路径已登记BSP；
* ``0x10000``：临时8-byte far jump已经撤销，原内容恢复；
* PIRQ table、MP table、SMBIOS：尚未由后续调用构造；
* 设备驱动、GRUB与Linux：尚未进入。

未提供 ``-smp`` override、采用QEMU缺省CPU拓扑时：

* present count=1， ``CountCPUs=1``；
* INIT/SIPI广播没有AP接收者；
* 没有CPU执行 ``entry_smp``、 ``handle_smp`` 或 ``smp_write_msrs``；
* 不存在“SeaBIOS已经停驻的AP”；当前唯一CPU仍是BSP/CPU0。

显式配置多个present vCPU且全部正常报到时：

* ``CountCPUs=expected_cpus_count``；
* 每个AP已登记ID，并串行执行日志内的MSR前缀；
* 日志完整时BSP/AP得到相同序列，日志截断时不能保证相同最终MSR状态；
* 每个AP释放共享栈后停在IF=0的HLT循环；
* BSP仍是唯一继续执行SeaBIOS POST的CPU。

若present count与实际报到不一致，BSP没有本章返回出口。

关键边界
--------

#. QEMU未给 ``-smp`` 时缺省为1个vCPU；当前固定条件没有排除显式多CPU配置。
#. ``FW_CFG_NB_CPUS`` 是present count； ``etc/max-cpus`` 在x86上实际是APIC-ID上界。
#. 有local APIC时，即使present count为1，SeaBIOS仍临时写0x10000并广播INIT/SIPI。
#. INIT/SIPI目标是all-excluding-self；缺省单CPU广播没有接收者。
#. BSP在IPI发出后登记自身APIC ID，必要时才转入x2APIC。
#. 多CPU路径用一把内存锁串行共享BSP栈；AP不并行运行SeaBIOS C handler。
#. AP只重放32项数组里实际记录的MSR，继承第011章的截断风险。
#. AP递增计数后在IF=0的HLT循环停驻；缺省单CPU路径没有这种AP对象。
#. BSP等待精确计数相等且没有timeout，缺报到不会自动退化。
#. 恢复0x10000只撤销临时trampoline，不改变local APIC配置。

下一入口
--------

``smp_setup()`` 正常返回后， ``qemu_platform_setup()`` 进入固件表阶段：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

所以下一章的真实第一步是先比较 ``MaxCountCPUs <= 255``，再决定是否调用
``pirtable_setup()``；不能以“AP必已停驻”作为无条件开场状态。

资料
----

* `SeaBIOS固定提交：CPU数量、INIT/SIPI与等待循环 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smp.c#L52-L184>`_
* `SeaBIOS固定提交：AP入口、共享栈与HLT <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S#L202-L221>`_
* `SeaBIOS固定提交：present CPU读取 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L527-L540>`_
* `SeaBIOS固定提交：固件表调用顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L289-L299>`_
* `QEMU固定提交：默认CPU数量初始化 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/core/machine.c#L1216-L1275>`_
* `QEMU固定提交：FW_CFG_NB_CPUS与APIC-ID上界 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c#L119-L146>`_
* `QEMU固定提交：APIC-ID上界计算与present CPU创建 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/x86-common.c#L70-L115>`_
* `Intel 64 and IA-32 Architectures Software Developer Manuals <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_
