第十二章：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？
==================================================

上一章结束时，BSP 已经完成自己的 MTRR 与 ``IA32_FEATURE_CONTROL`` 设置，并把每一条需要其他 CPU 重放的
MSR 写入保存到 ``smp_msr`` 数组。

控制流仍在：

::

   qemu_platform_setup()

下一条调用是：

.. code-block:: c

   smp_setup();

本章将第一次让 BSP 之外的 Application Processor，简称 AP，开始执行指令。

这里需要区分两个称呼：

``BSP``
   Bootstrap Processor。复位后负责执行固件主流程的 CPU。

``AP``
   Application Processor。系统中的其他 CPU，开机时先等待 BSP 通过 local APIC 启动。

本章沿下面的真实控制流前进：

::

   smp_setup()
   → 读取 etc/max-cpus
   → 读取当前实际存在的 CPU 数
   → smp_scan()
   → 检查 local APIC 能力
   → 在 0x10000 写入 AP 启动跳板
   → 开启 BSP local APIC
   → 配置 LINT0 / LINT1
   → BSP 暂时占有共享栈锁
   → 广播 INIT
   → 广播 SIPI，vector = 0x10
   → AP 从物理地址 0x10000 开始取指
   → AP 远跳转到 entry_smp
   → AP 进入 32 位保护模式
   → AP 竞争共享栈锁
   → handle_smp()
   → 记录 APIC ID
   → 重放 MTRR 与 feature-control MSR
   → CountCPUs++
   → AP 释放锁并 HLT
   → BSP 等到全部当前 CPU 报到
   → 恢复 0x10000 原始内容
   → smp_setup() 返回

本章固定使用：

::

   SeaBIOS repository: coreboot/seabios
   SeaBIOS commit:     c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

实际存在的 CPU 数与最大可支持 CPU 数不是一回事
-----------------------------------------------

``smp_setup()`` 首先读取：

.. code-block:: c

   MaxCountCPUs = romfile_loadint("etc/max-cpus", 0);
   u16 smp_count = qemu_get_present_cpus_count();

   if (MaxCountCPUs < smp_count)
       MaxCountCPUs = smp_count;

这里有三个容易混淆的数量。

``smp_count``
   当前虚拟机已经存在、这次开机应当被唤醒的 CPU 数量。

``CountCPUs``
   SeaBIOS 实际已经看到并完成报到的 CPU 数量。进入扫描前只计 BSP，所以从 1 开始。

``MaxCountCPUs``
   固件表需要描述的最大 CPU/APIC ID 范围，可能包含以后通过热插拔出现的 CPU。QEMU 的兼容接口
   ``etc/max-cpus`` 历史上更接近 APIC ID limit，不应简单理解为“当前在线 CPU 数”。

因此一个虚拟机可能当前只有 4 个 CPU，固件表却为更多潜在 CPU 位置保留描述空间。

SeaBIOS 怎样得到当前存在的 CPU 数
--------------------------------

``qemu_get_present_cpus_count()`` 优先从 fw_cfg 的：

::

   QEMU_CFG_NB_CPUS

读取 16 位数量。

如果 RTC/CMOS 存在，它还读取：

::

   CMOS_BIOS_SMP_COUNT + 1

然后取两者中的较大值。

``+1`` 的原因是旧 CMOS 字段保存的通常是“除 BSP 之外的 CPU 数”或 ``count - 1`` 形式。fw_cfg 是当前主路径，
CMOS 兼容值用于旧平台和旧接口。

这一数量只是 BSP 接下来等待的目标值。真正是否有 AP 执行到 ``handle_smp()``，还需要下面的 INIT/SIPI 启动过程确认。

没有 local APIC 时退化成单 CPU
-----------------------------

``smp_scan()`` 读取 ``CPUID.01H``，检查 APIC feature bit。

如果处理器没有 local APIC，SeaBIOS 直接：

.. code-block:: c

   CountCPUs = 1;
   return;

后面的 INIT/SIPI 全部不会发生。

固定 q35 x86-64 虚拟 CPU 主线提供 local APIC，所以继续执行多处理器扫描。

为什么 AP 需要一个低端内存启动地址
--------------------------------

x86 AP 接收 Startup IPI，简称 SIPI，之后不会直接跳到任意 32 位 C 函数。SIPI 携带一个 8 位 vector，CPU 将它解释为：

::

   physical start address = vector << 12

也就是以 4 KiB 为单位选择 1 MiB 以下的启动页。

SeaBIOS 固定：

::

   BUILD_AP_BOOT_ADDR = 0x10000

所以 SIPI vector 是：

.. code-block:: c

   sipi_vector = BUILD_AP_BOOT_ADDR >> 12;
               = 0x10000 >> 12;
               = 0x10;

AP 接收 SIPI 后从：

::

   0x10 << 12 = 0x10000

开始执行。

0x10000 原本不是永久保留的 AP 固件区
-----------------------------------

SeaBIOS 在写跳板前先保存原来的 8 字节：

.. code-block:: c

   u64 old = *(u64 *)BUILD_AP_BOOT_ADDR;

随后构造一条 16 位 far jump：

.. code-block:: asm

   ljmpw $SEG_BIOS, $(entry_smp - BUILD_BIOS_ADDR)

机器码的首字节是 ``0xea``，后面依次是 16 位 offset 和 16 位 segment。SeaBIOS 把这条指令直接写到物理地址
``0x10000``。

因此 AP 的第一小段路径是：

::

   SIPI vector 0x10
   → 物理地址 0x10000
   → 16 位 far jump
   → SeaBIOS F-segment 中的 entry_smp

这块低端 RAM 只被临时借用。所有 AP 报到后，BSP 会把保存的原始 8 字节写回去。

BSP 先开启自己的 local APIC
--------------------------

local APIC 的 MMIO 基址固定为：

::

   0xfee00000

SeaBIOS 操作三个寄存器：

::

   SVR   = 0xfee000f0
   LINT0 = 0xfee00350
   LINT1 = 0xfee00360
   ICR low = 0xfee00300

它先读取 Spurious Interrupt Vector Register，简称 SVR，并设置 bit 8：

.. code-block:: c

   val = readl(APIC_SVR);
   writel(APIC_SVR, val | 0x0100);

bit 8 是 local APIC software enable。没有这一位，后面的 IPI 发送路径不能按预期工作。

LINT0 接收传统 8259A 的 ExtINT
-----------------------------

SeaBIOS 写入：

.. code-block:: c

   writel(APIC_LINT0, 0x8700);

其中 delivery mode 是 ``ExtINT``，trigger mode 是 level。

这使 BSP 的 local APIC LINT0 能接收传统 PIC 输出。前面章节已经配置两片 8259A；这里把传统中断系统与 local APIC
输入端接上。

LINT1 被配置成 NMI
-----------------

SeaBIOS 写入：

.. code-block:: c

   writel(APIC_LINT1, 0x8400);

delivery mode 是 ``NMI``，并采用 level-triggered 配置。

这不表示此刻已经发生 NMI，只是规定 local APIC 的 LINT1 输入以后按不可屏蔽中断处理。

BSP 为什么先把共享栈锁设为占用
-----------------------------

SeaBIOS 定义：

.. code-block:: c

   u32 SMPLock;
   u32 SMPStack;

在发出 IPI 前：

.. code-block:: c

   SMPLock = 1;

值 1 表示锁已被 BSP 占有。这样 AP 即使很快到达 ``entry_smp``，也不能立刻使用 BSP 当前的栈。

SeaBIOS 没有为每个 AP 分配独立固件栈，而是让 AP 一个接一个借用 BSP 暂时交出的栈。锁保证同一时刻只有一个 AP
进入 C 处理函数。

第一条 IPI 是 INIT
-----------------

BSP 向 local APIC ICR low 写：

.. code-block:: c

   writel(APIC_ICR_LOW, 0x000C4500);

这个值包含：

* delivery mode = INIT；
* level = assert；
* destination shorthand = all excluding self。

“all excluding self”表示向除 BSP 自己之外的所有 local APIC 目标广播。

INIT IPI 让 AP 进入架构规定的初始化/等待启动状态。它不是让 AP 执行 SeaBIOS C 代码，真正提供启动地址的是下一条 SIPI。

第二条 IPI 是 SIPI
-----------------

BSP 随后写入：

.. code-block:: c

   writel(APIC_ICR_LOW, 0x000C4600 | 0x10);

其中：

* delivery mode = Startup；
* destination shorthand = all excluding self；
* vector = ``0x10``。

因此所有目标 AP 从物理地址 ``0x10000`` 开始执行前面安装的 far jump。

这里没有为每个 AP 单独发送不同入口。所有 AP 运行同一段启动代码，再通过各自 local APIC ID 区分身份。

AP 从 SIPI 入口开始时处于什么状态
--------------------------------

SIPI 启动入口属于传统 x86 AP startup 环境。AP 不会继承 BSP 当前的 32 位 C 调用栈，也不会从
``qemu_platform_setup()`` 的下一行继续。

它从 ``0x10000`` 的 16 位跳板进入 ``entry_smp``：

.. code-block:: asm

   entry_smp:
       cli
       cld
       movl $2f + BUILD_BIOS_ADDR, %edx
       jmp transition32_nmi_off

``CLI`` 关闭可屏蔽中断，``CLD`` 清除方向标志。随后复用早期章节讲过的保护模式转换代码：

::

   装载临时 IDT/GDT
   → 设置 CR0.PE
   → far jump 装载 32 位 code segment
   → 装载 32 位 data segments
   → 跳回 entry_smp 的 32 位部分

函数选择 ``transition32_nmi_off``，因为这条内部路径从已经受控的 AP 启动环境继续，不重复前面普通启动入口中的完整
NMI 处理序列。

所有 AP 竞争同一把锁
-------------------

进入 32 位部分后，AP 执行：

.. code-block:: asm

   lock btsl $0, SMPLock
   jc spin

``BTS`` 是 Bit Test and Set。它原子地读取 bit 0 的旧值，并把该位设为 1。

* 旧值为 0：当前 AP 成功取得锁；
* 旧值为 1：锁仍被 BSP 或另一个 AP 占有，当前 AP继续自旋。

``LOCK`` 前缀保证多个虚拟 CPU 同时访问这一个内存字时，只有一个能观察到未占用状态并成功设置。

取得锁后，AP 执行：

.. code-block:: asm

   movl SMPStack, %esp

``SMPStack`` 保存的是 BSP 主动交出的当前 ``ESP``。AP 因而暂时使用 BSP 的栈空间调用 ``handle_smp()``。

BSP 怎样把栈一次交给一个 AP
--------------------------

BSP 在等待循环中执行一段内联汇编：

.. code-block:: asm

   movl %esp, SMPStack
   movl $0, SMPLock

   acquire_again:
       lock btsl $0, SMPLock
       jc acquire_again

过程是：

#. BSP 把当前 ``ESP`` 写进 ``SMPStack``；
#. BSP 把锁清零，允许一个 AP 抢到；
#. 某个 AP 把锁从 0 改为 1并进入 ``handle_smp()``；
#. BSP尝试重新取得锁，在 AP 使用共享栈期间持续自旋；
#. AP 完成后把锁清零；
#. BSP重新取得锁，恢复对自己栈的独占；
#. 如果还有 AP 未报到，再重复一次。

所以 AP 并不是并行运行 SeaBIOS C 初始化。它们可以同时到达锁前，但会被串行放行，每次只让一个 AP 使用共享栈。

handle_smp 首先确认 APIC ID
--------------------------

``handle_smp()`` 调用：

.. code-block:: c

   int apic_id = apic_id_init();

在 ``MaxCountCPUs < 256`` 的传统 xAPIC 情况下，APIC ID 来自：

::

   CPUID.01H:EBX[31:24]

SeaBIOS 用 256 位 ``FoundAPICIDs`` bitmap 记录已经发现的 8 位 APIC ID。后面的 legacy MP table 等固件结构会使用这份信息。

如果 ``MaxCountCPUs >= 256``，8 位 xAPIC ID 不足以描述全部可能 CPU。处理器支持 x2APIC 时，SeaBIOS：

#. 设置 ``IA32_APIC_BASE`` 的 x2APIC enable bit；
#. 从 x2APIC MSR ``0x802`` 读取更宽的 local APIC ID。

如果需要超过 255 的范围，而 CPUID 又没有暴露 x2APIC，当前函数返回无效 ID。后面的旧式表也不会假装能够描述不存在的
8 位 ID 空间。

BSP 自己也要登记 APIC ID
-----------------------

广播 SIPI 后，BSP 本身调用一次 ``apic_id_init()``。

因为 IPI 使用“all excluding self”，BSP 不会经过 ``entry_smp``。如果不在主流程中单独调用，``FoundAPICIDs`` 将只有 AP，
缺少 BSP。

此外，当系统需要 x2APIC 模式时，BSP 也必须在发送传统 xAPIC MMIO IPI之后切换。源码特意把切换放在广播之后，让 xAPIC
和 x2APIC 配置共用同一套 AP 唤醒代码。

AP 重放上一章保存的 MSR 序列
---------------------------

AP 确认身份后执行：

.. code-block:: c

   smp_write_msrs();

它按保存顺序遍历 ``smp_msr``：

.. code-block:: c

   for (i = 0; i < smp_msr_count; i++)
       wrmsr(smp_msr[i].index,
             smp_msr[i].val);

因此每个 AP 得到与 BSP 相同的：

* fixed-range MTRR；
* variable-range MTRR；
* ``IA32_MTRR_DEF_TYPE``；
* 条件存在的 ``IA32_FEATURE_CONTROL``。

重放仍包含“先关闭 MTRR、写完整配置、再启用”的原始顺序，不只复制最终 ``DEF_TYPE``。

CountCPUs 为什么不需要原子自增
-----------------------------

``handle_smp()`` 最后执行：

.. code-block:: c

   CountCPUs++;

这条自增本身没有使用原子指令。它依然安全，因为所有 AP 都必须先取得 ``SMPLock``，同一时刻只有一个 AP 能进入
``handle_smp()``。锁已经把修改 ``CountCPUs`` 的临界区串行化。

AP 完成后不会返回普通主流程
-------------------------

``handle_smp()`` 返回汇编入口后：

.. code-block:: asm

   movl $0, SMPLock
   hlt

AP 先释放共享栈锁，让 BSP 或下一个 AP继续，然后执行 ``HLT``。

当前 AP 的 ``IF`` 仍为 0，因此普通可屏蔽中断不会让它开始运行 BIOS 主流程。它被停放在固件等待状态；以后 Linux 会用
自己的 AP startup 代码和 IPI 序列再次接管这些 CPU。

SeaBIOS 唤醒 AP 的目的不是让多个 CPU 一起执行 POST，而是：

* 确认当前实际存在多少 CPU；
* 记录 APIC ID；
* 把必要的每 CPU MSR 配置复制给它们；
* 再把它们停回等待状态。

BSP 等待的不是固定延时
---------------------

BSP 读取：

.. code-block:: c

   expected_cpus_count = qemu_get_present_cpus_count();

然后持续比较：

.. code-block:: c

   while (expected_cpus_count != CountCPUs)
       release_stack_and_reacquire();

它不会简单睡眠若干毫秒后猜测 AP 已经启动，而是等待实际报到数达到 QEMU/CMOS 宣布的当前 CPU 数。

如果某个 AP 永远没有执行到 ``CountCPUs++``，这段固件流程也无法正常继续。这体现了平台契约：QEMU 声明存在的 CPU
必须响应广播启动并运行跳板。

为什么等待结束后还调用 yield
---------------------------

当计数相等后，SeaBIOS 调用：

.. code-block:: c

   yield();

这给前面建立的 SeaBIOS 协作式任务机制一次运行机会。SMP 报到本身已经完成；``yield()`` 不是等待 AP 数量的核心条件，
核心条件是 ``CountCPUs`` 与 expected count 相等。

0x10000 的原始内容被恢复
-----------------------

所有当前 CPU 报到后：

.. code-block:: c

   *(u64 *)BUILD_AP_BOOT_ADDR = old;

临时 far jump 被撤销，物理 ``0x10000`` 恢复进入 SMP 扫描前的 8 字节。

因此 AP trampoline 不会永久占用这块低端 RAM，也不会作为 Linux 以后启动 AP 的入口。Linux 会建立自己的 trampoline。

第十二章结束时的机器状态
----------------------

控制权目前走过：

::

   qemu_platform_setup()
   → smp_setup()
   → 读取 etc/max-cpus
   → 读取当前 present CPU count
   → smp_scan()
   → 在 0x10000 安装 far-jump trampoline
   → 开启 BSP local APIC
   → LINT0 = ExtINT
   → LINT1 = NMI
   → 广播 INIT
   → 广播 SIPI vector 0x10
   → AP 从 0x10000 进入 entry_smp
   → AP 切换到 32 位保护模式
   → AP 串行借用 BSP 栈
   → handle_smp()
   → 记录 APIC ID
   → 重放 MTRR / feature-control MSR
   → CountCPUs++
   → AP HLT
   → BSP 等待全部 CPU 报到
   → 恢复 0x10000
   → smp_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前主流程 CPU：BSP；
* BSP 模式：32 位保护模式；
* 分页：关闭；
* 当前存在 CPU 数：已经由真实 AP 报到确认；
* APIC ID：已经发现；
* BSP 与 AP 的 MTRR：已经一致；
* BSP 与 AP 的条件 feature-control：已经一致；
* BSP local APIC：已经开启；
* AP：已经执行过 SeaBIOS 启动代码，当前停在 ``HLT``；
* ``0x10000`` SeaBIOS 临时 trampoline：已经移除；
* ``CountCPUs``：保存本次实际报到数量；
* ``MaxCountCPUs``：保存固件表需要覆盖的最大 CPU/APIC ID 范围；
* PIRQ table、MP table、SMBIOS：尚未建立；
* ACPI：尚未装载或生成；
* 存储与 USB 驱动：尚未开始介质探测；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``smp_setup()`` 返回后，``qemu_platform_setup()`` 继续创建固件表：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

下一章将解释 PCI IRQ Routing Table、Intel MP table 与 SMBIOS 分别向后续软件描述什么，以及为什么
``MaxCountCPUs > 255`` 时 SeaBIOS 跳过两种旧式表。

资料
----

* `SeaBIOS src/fw/smp.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smp.c>`_；
* `SeaBIOS src/romlayout.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S>`_；
* `SeaBIOS src/config.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_；
* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `Intel 64 and IA-32 Architectures Software Developer Manuals <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_。