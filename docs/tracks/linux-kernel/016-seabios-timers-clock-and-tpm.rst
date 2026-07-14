第十六章：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？
====================================================================

上一章结束时，``qemu_platform_setup()`` 已经返回。控制流回到：

.. code-block:: c

   static void platform_hardware_setup(void)
   {
       ...
       qemu_platform_setup();
       coreboot_platform_setup();

       timer_setup();
       clock_setup();
       tpm_setup();
   }

当前固定路径是 QEMU q35 + SeaBIOS，``coreboot_platform_setup()`` 不会成为主线。接下来三个函数完成三件容易混在一起的工作：

``timer_setup()``
   选择 SeaBIOS 内部测量超时和延时所用的连续时间源。

``clock_setup()``
   配置传统 PIT/RTC，建立 BDA time-of-day counter、IRQ0/IRQ8 和 INT 1Ah 服务。

``tpm_setup()``
   条件探测 TPM、初始化 event log，并在 option ROM 扫描前开始 measured boot 记录。

“内部计时器”和“BIOS 系统时钟”不是一个东西
--------------------------------------

SeaBIOS 同时需要两种时间概念。

第一种是内部 deadline timer：

::

   设备复位后最多等待 100 ms
   命令完成前最多轮询 5 s
   延迟 10 us
   线程睡眠到某个时间点

这类用途要求频率足够高、读取方便，使用 ``timer_calc()``、``timer_check()``、``udelay()``、``msleep()`` 等接口。

第二种是传统 PC BIOS time-of-day clock：

::

   BDA timer_counter
   IRQ0 → INT 08h
   INT 1Ah 读取时间/日期
   INT 1Ch 用户 tick hook

它按约 18.2 Hz 增加，从午夜开始计数，面向 DOS、bootloader 和其他 legacy BIOS 调用者。

两者可能都依赖 PIT，也可能分别使用 TSC/PM timer 与 PIT。把它们都叫“系统时钟”会掩盖实际控制流。

内部 timer 的初始状态
--------------------

``src/hw/timer.c`` 定义：

.. code-block:: c

   u32 TimerKHz = ...;
   u16 TimerPort = PORT_PIT_COUNTER0;  // 0x40
   u8 ShiftTSC;

``TimerPort == 0x40`` 不是单纯表示“正在使用 PIT”，它也是“还没有选定更好的时间源”的初始哨兵。

运行到当前章节前，已有两个更早机会改变它。

KVM pvclock 可以最先确定 TSC 频率
-----------------------------

第七章经过的 ``kvmclock_init()`` 在 KVM 路径中可能从 paravirtualized clock 得到稳定 TSC 频率，然后调用：

.. code-block:: c

   tsctimer_setfreq(khz, "kvmclock");

它设置：

::

   TimerPort = 0
   TimerKHz  = 经过缩放的 TSC kHz
   ShiftTSC  = 为避免 32 位计算溢出选择的右移量

``TimerPort == 0`` 表示 ``timer_read()`` 直接读取 TSC：

.. code-block:: c

   rdtscll() >> ShiftTSC

如果 pvclock 明确给出稳定 TSC，这条路径避免再用 PIT 做校准。

ICH9 PM timer 是 q35 的第二选择
-----------------------------

第九章配置 ICH9 LPC 时已经调用：

.. code-block:: c

   pmtimer_setup(acpi_pm_base + 0x08);

``pmtimer_setup()`` 只在 ``TimerPort`` 仍等于 ``0x40`` 时生效。如果 KVM 稳定 TSC 已经被采用，它直接返回；否则把：

::

   TimerPort = PMBASE + 0x08
   TimerKHz  ≈ 3579.545 kHz

PM timer 是递增计数器，底层频率为 3,579,545 Hz。当前实现按 24 位有效值读取：

.. code-block:: c

   inl(TimerPort) & 0x00ffffff

24 位计数器会周期性回绕。``timer_adjust_bits()`` 用 ``TimerLast`` 保存扩展高位：当新低位小于上次值时，加上 ``0x01000000``，把多次读取拼成单调递增的 32 位时间轴。

timer_setup 是最后的 TSC 校准机会
-------------------------------

到当前 ``timer_setup()`` 时，函数先检查：

.. code-block:: c

   if (TimerPort != PORT_PIT_COUNTER0)
       return;

因此：

* 稳定 KVM TSC 已选中时，不再校准；
* ICH9 PM timer 已选中时，不再校准；
* 只有两者都没有建立，才继续检查 CPUID 的 TSC bit。

如果 CPU 支持 TSC，``tsctimer_setup()`` 临时使用 PIT channel 2 做基准。

PIT channel 2 怎样校准 TSC
-------------------------

SeaBIOS 先读取 I/O port ``0x61`` 的原状态，关闭 speaker 输出但打开 timer 2 gate：

::

   speaker off
   timer2 gate on

随后把 PIT channel 2 设置为：

::

   binary
   mode 0
   LSB/MSB
   one-shot count = 0x0800

流程是：

::

   写入 0x0800
   → 读取起始 TSC
   → 轮询 port 0x61 的 timer2 output
   → 倒计时结束
   → 读取结束 TSC
   → 恢复 port 0x61

PIT 输入频率约为 1.193182 MHz，所以 2048 个 PIT ticks 大约持续 1.7 ms。SeaBIOS 用这段已知时间内的 TSC 差值估算 CPU TSC 频率。

估算值可能很大，后续 deadline 计算主要使用 32 位整数。代码因此不断右移频率并增加 ``ShiftTSC``，直到缩放值落入安全范围。读取时再把 TSC 同样右移，时间比例保持一致。

如果 CPU 连 TSC 都不支持，``TimerPort`` 保持 ``0x40``，内部 timer 最终回退为读取 PIT channel 0 当前计数值。

内部 timer 的选择优先级
----------------------

当前控制流可以整理为：

::

   1. 稳定 KVM pvclock 提供的 TSC 频率
      TimerPort = 0

   2. q35 ICH9 ACPI PM timer
      TimerPort = PMBASE + 8

   3. 用 PIT channel 2 校准的 TSC
      TimerPort = 0

   4. PIT channel 0 fallback
      TimerPort = 0x40

这里的优先级由“谁先把 ``TimerPort`` 从初始哨兵改掉”实现，不是由一个集中式 switch 表实现。

timer_calc 和 timer_check 怎样处理回绕
----------------------------------

``timer_calc(ms)`` 返回：

::

   current + TimerKHz × ms

``timer_check(end)`` 使用有符号差：

.. code-block:: c

   (s32)(timer_read() - end) > 0

只要 deadline 不跨越超过半个 32 位计数空间，这种写法即使计数器发生无符号回绕，也能正确判断当前时间是否已经越过终点。

``udelay()`` 和 ``mdelay()`` 忙等；``usleep()`` 和 ``msleep()`` 在等待期间调用 ``yield()``，让 SeaBIOS 其他协作线程继续运行。

clock_setup 开始建立传统 BIOS 时钟
-------------------------------

内部时间源确定后，``clock_setup()`` 首先执行：

.. code-block:: c

   pit_setup();

PIT channel 0 被设置为：

::

   binary
   mode 2 rate generator
   LSB/MSB
   divisor = 0x0000

PIT 规定写入零表示 divisor 65536，而不是除数为零。PIT 输入频率约 1.193182 MHz，因此：

::

   1,193,182 / 65,536 ≈ 18.2065 Hz

也就是每约 54.925 ms 产生一次 IRQ0。这是传统 PC BIOS 的 18.2 Hz tick 来源。

内部 timer 即使正在使用 TSC 或 PM timer，PIT channel 0 仍会被配置。原因是 IRQ0/BDA 时钟属于 BIOS 对外兼容接口，不等同于内部延时源。

RTC 初始化到 24 小时 BCD 模式
--------------------------

``rtc_setup()`` 操作 MC146818 兼容 RTC/CMOS：

.. code-block:: c

   rtc_write(CMOS_STATUS_A, 0x26);
   rtc_mask(CMOS_STATUS_B, ~RTC_B_DSE, RTC_B_24HR);
   rtc_read(CMOS_STATUS_C);
   rtc_read(CMOS_STATUS_D);

Status A ``0x26`` 选择 32.768 kHz 基准和约 976.5625 us 的 periodic interval，也就是 1024 Hz 周期基础。

Status B 打开 24 小时制，同时保留允许的 daylight-saving bit。这里没有设置 binary-mode bit，所以时间字段按 BCD 读取。

读取 Status C 会确认并清除挂起的 RTC interrupt flags；读取 Status D 取得有效状态。

为什么读取 RTC 前要等待 UIP 清零
----------------------------

RTC 每秒会把内部时间更新到可读寄存器。Status A 的 UIP，Update In Progress，表示复制正在进行。

如果在更新过程中分别读取 hour、minute 和 second，可能得到跨秒的不一致组合，例如：

::

   hour   = 12
   minute = 59
   second = 00

其中 minute 来自更新前，second 来自更新后。

``rtc_updating()`` 如果看到 UIP 已经清零就立即返回；如果 UIP 为一，则最多等待约 15 ms，期间调用 ``yield()``。超时说明 RTC 没有按预期完成更新。

RTC 时间怎样变成 BDA tick counter
-------------------------------

SeaBIOS 读取 BCD：

.. code-block:: c

   seconds
   minutes
   hours

转换为从午夜开始的毫秒数，再调用：

.. code-block:: c

   ticks_from_ms(...)

得到 18.2 Hz tick 数，最后写入：

::

   BDA physical 0x046c  timer_counter

``TICKS_PER_DAY`` 固定为：

::

   1,573,040

它约等于 24 小时中的 PIT tick 数。初始值还会对 ``TICKS_PER_DAY`` 取模，防止异常 RTC 时间产生越界日计数。

q35/QEMU 路径还直接从 ``CMOS_CENTURY`` 读取 century byte，后续 INT 1Ah 日期服务可以返回完整世纪。

IRQ0 怎样进入 INT 08h
-------------------

``clock_setup()`` 执行：

.. code-block:: c

   enable_hwirq(0, FUNC16(entry_08));

第六章已经建立 PIC 映射：master IRQ0 对应 ``INT 08h``。现在解除 IRQ0 屏蔽并把中断向量指向 SeaBIOS handler。

每次 PIT tick 的路径是：

::

   PIT channel 0
   → IRQ0
   → master 8259A
   → INT 08h entry
   → handle_08()
   → clock_update()

``clock_update()`` 将 BDA ``timer_counter`` 加一。达到 ``1,573,040`` 时：

::

   timer_counter = 0
   timer_rollover++

``timer_rollover`` 供 INT 1Ah AH=00 返回“自上次读取后是否跨过午夜”。

每个 18.2 Hz tick 还检查：

* floppy motor/recalibration 状态；
* USB HID event；
* PS/2 event；
* serial console event。

所以传统 timer interrupt 同时承担了若干固件后台事件推进功能。

INT 1Ch 是留给调用者的 tick hook
-----------------------------

SeaBIOS 更新自己的状态后，会软件调用：

.. code-block:: c

   INT 1Ch

这是传统 BIOS 允许 DOS 程序或其他低层软件挂接的用户 timer tick hook。随后 handler 才向 master PIC 发送 EOI。

顺序是：

::

   更新 BDA 和固件事件
   → 调用 INT 1Ch
   → PIC EOI
   → 从 IRQ 返回

如果用户 hook 执行过久，后续 IRQ0 会被延迟。

RTC IRQ8 与 1024 Hz wait service
-----------------------------

如果构建启用 ``CONFIG_RTC_TIMER``，``clock_setup()`` 还执行：

.. code-block:: c

   enable_hwirq(8, FUNC16(entry_70));

slave PIC IRQ8 映射到 ``INT 70h``。

RTC periodic interrupt 默认不是无条件一直开启。``rtc_use()`` 用引用计数 ``RTCusers`` 管理 PIE bit：第一个使用者出现时开启，最后一个使用者离开时关闭。

典型使用者包括：

* INT 15h AH=86 微秒等待；
* INT 15h AH=83 interval callback；
* option ROM 执行期间的 SeaBIOS 线程抢占检查。

每次 periodic IRQ 约代表：

::

   1,000,000 / 1024 ≈ 976.5625 us

``handle_70()`` 从 BDA ``user_wait_timeout`` 递减这段时间；完成后把调用者指定 flag byte 的 bit 7 置一。

RTC alarm interrupt 则调用 ``INT 4Ah``。最终向 slave/master PIC 完成 EOI。

INT 1Ah 暴露传统时间与日期服务
---------------------------

``handle_1a()`` 根据 AH 分派：

::

   AH=00 读取 BDA tick 与 midnight rollover
   AH=01 设置 BDA tick
   AH=02 读取 RTC 时间
   AH=03 设置 RTC 时间
   AH=04 读取 RTC 日期
   AH=05 设置 RTC 日期
   AH=06 设置 alarm
   AH=07 关闭 alarm
   AH=BB TCG BIOS extension

这套接口是 bootloader 进入操作系统前常见的 BIOS 服务。Linux 启动后会建立自己的 timekeeping、clocksource、clockevent 和 RTC 驱动，不再依赖 BIOS 每秒 18.2 次更新内核时间。

tpm_setup 首先需要 ACPI event log 描述
-----------------------------------

``tpm_setup()`` 是条件路径。``CONFIG_TCGBIOS`` 关闭时立即返回。

启用时，它先寻找：

.. code-block:: c

   TPM2 table

如果没有，再寻找：

.. code-block:: c

   TCPA table

两张表的共同目的之一是告诉固件：

::

   event log buffer address
   event log minimum length

SeaBIOS 把这块区域清零并初始化：

::

   log start
   log length
   next entry
   last entry
   entry count

没有对应 ACPI 表时，当前 TCG BIOS 流程不会继续。这说明 ACPI 不只服务未来操作系统，SeaBIOS 自己也依赖它取得 TPM log 内存布局。

TPM 1.2 与 TPM 2.0 使用不同启动序列
--------------------------------

``tpmhw_probe()`` 探测实际 TPM interface 和版本。

TPM 1.2 路径大致执行：

::

   TPM_Startup(ST_CLEAR)
   → assertion of physical presence
   → 读取 timeout 参数
   → SelfTestFull
   → 尝试 ResetEstablishmentBit

TPM 2.0 路径执行：

::

   设置 command timeout
   → TPM2_CC_Startup(SU_CLEAR)
   → TPM2_CC_SelfTest
   → 查询 active PCR banks
   → 在 event log 开头写 Spec ID Event03

Spec ID event 告诉 event log 读取者当前包含哪些 hash algorithm 和 digest size，例如 SHA-1、SHA-256、SHA-384 或 SHA-512。

任何关键命令失败时，SeaBIOS 会把 ``TPM_working`` 清零，停止后续 measurement，而不是让整台虚拟机无法启动。

PCR extend 与 event log 为什么必须同时存在
-------------------------------------

Measured boot 对同一事件做两件事。

第一件是扩展 PCR：

::

   new_PCR = HASH(old_PCR || event_digest)

它形成顺序敏感、难以逆转的累计值，但只看最终 PCR 无法知道中间测量了哪些对象。

第二件是向 event log 追加：

::

   PCR index
   event type
   digest
   event description/data

验证者重新按日志顺序计算 PCR，才能解释最终值。

所以 event log 不是 PCR 的替代品，PCR 也不是 event log 的压缩备份；两者共同构成可验证的 measured-boot 记录。

SeaBIOS 在 option ROM 扫描前测量什么
--------------------------------

TPM 启动成功后，SeaBIOS 首先取得已经安装的 SMBIOS structure blob，对它计算 SHA-1，并把 measurement 记录到 PCR 1。

随后加入动作：

.. code-block:: c

   tpm_add_action(2, "Start Option ROM Scan");

也就是在 PCR 2 中记录 option ROM 扫描阶段即将开始。

后续 ``vgarom_setup()``、``optionrom_setup()`` 和 boot path 会继续测量 ROM、IPL 或其他启动对象。当前章节只是建立 TPM 状态和测量日志起点。

Measured Boot 不等于 Secure Boot
------------------------------

当前流程主要是 measurement：

::

   计算 digest
   → extend PCR
   → 写 event log
   → 继续执行

它默认不会因为 option ROM 或 boot sector digest 不在允许列表中就拒绝执行。Secure Boot 强调执行前验证签名和策略阻止；Measured Boot 强调把实际执行链记录到 TPM，供本地或远程验证者事后判断。

两者可以组合，但不能因为出现 TPM/PCR 就把当前 SeaBIOS 路径描述成已经执行 UEFI Secure Boot。

platform_hardware_setup 到这里返回
--------------------------------

执行完：

.. code-block:: c

   timer_setup();
   clock_setup();
   tpm_setup();

``platform_hardware_setup()`` 返回 ``maininit()``。

第十六章结束时的机器状态
----------------------

控制权目前走过：

::

   platform_hardware_setup()
   → qemu_platform_setup() 返回
   → timer_setup()
   → 选择 KVM TSC / PM timer / calibrated TSC / PIT fallback
   → clock_setup()
   → PIT channel 0 mode 2, divisor 65536
   → RTC 初始化与 UIP 等待
   → RTC BCD time 转换为 BDA timer_counter
   → IRQ0 → INT 08h
   → 条件 IRQ8 → INT 70h
   → tpm_setup()
   → 条件 TPM2/TCPA event log
   → 条件 TPM startup/self-test/PCR bank 初始化
   → 测量 SMBIOS
   → 记录 Start Option ROM Scan
   → platform_hardware_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* SeaBIOS 内部 deadline timer：已经选定；
* PIT channel 0：已配置为约 18.2 Hz；
* BDA ``timer_counter``：已按 RTC 当前时间初始化；
* IRQ0 / INT 08h：已经启用；
* INT 1Ch：可作为用户 tick hook；
* RTC / INT 1Ah 时间日期服务：已经建立；
* 条件 RTC IRQ8 / INT 70h：已经建立；
* 条件 TPM：已启动并建立 event log；
* 条件 measured boot：已测量 SMBIOS 并标记 option ROM scan 起点；
* USB、PS/2、ATA/AHCI/NVMe 与普通 virtio-pci 驱动：尚未完成 ``device_hardware_setup()``；
* VGA Option ROM：尚未执行；
* 普通 option ROM：尚未扫描；
* ``BootList``：尚未形成最终启动设备集合；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``maininit()`` 接下来检查：

.. code-block:: c

   if (threads_during_optionroms())
       device_hardware_setup();

   vgarom_setup();

后续控制流会根据 ``ThreadControl`` 决定设备探测是与 option ROM 执行交错进行，还是在 VGA ROM 之后同步完成。下一章将先确认这个条件，然后进入 USB、PS/2 和 block driver 的实际设备发现阶段。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/hw/timer.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/timer.c>`_；
* `SeaBIOS src/clock.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/clock.c>`_；
* `SeaBIOS src/hw/rtc.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/rtc.c>`_；
* `SeaBIOS src/std/bda.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/bda.h>`_；
* `SeaBIOS src/stacks.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c>`_；
* `SeaBIOS src/tcgbios.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/tcgbios.c>`_；
* `SeaBIOS src/hw/tpm_drivers.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/tpm_drivers.c>`_；
* `TCG PC Client Platform Firmware Profile Specification <https://trustedcomputinggroup.org/resource/pc-client-specific-platform-firmware-profile-specification/>`_；
* `ACPI Specification <https://uefi.org/specifications>`_。