第十六章：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并条件初始化 TPM？
=======================================================================

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
   先查 TPM2/TCPA event-log 表；固定QEMU默认没有TPM设备，因而本章正常路径在这里
   返回。只有显式加入TPM的条件分支才继续启动硬件并开始measured boot记录。

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

KVM 可以最先确定 TSC 频率
-------------------------

较早的 ``kvm_detect()`` 可从KVM CPUID ``base+0x10`` 取得invtsc频率；随后
``kvmclock_init()`` 也可从带stable bit的paravirtualized clock反推TSC频率。两条路径
都会调用：

.. code-block:: c

   tsctimer_setfreq(khz, "invtsc" or "kvmclock");

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
   TimerKHz  = 3580 kHz（由3,579,545 Hz向上取整）

PM timer 是递增计数器，底层频率为 3,579,545 Hz。当前实现按 24 位有效值读取：

.. code-block:: c

   inl(TimerPort) & 0x00ffffff

24 位计数器会周期性回绕。``timer_adjust_bits()`` 用 ``TimerLast`` 保存扩展高位：当新低位小于上次值时，加上 ``0x01000000``，把多次读取拼成单调递增的 32 位时间轴。

timer_setup 在固定 q35 路径为什么直接返回
--------------------------------------

到当前 ``timer_setup()`` 时，函数先检查：

.. code-block:: c

   if (TimerPort != PORT_PIT_COUNTER0)
       return;

因此在固定q35主线中只有两种实际结果：

* 稳定 KVM TSC 已选中时，不再校准；
* 否则ICH9 LPC初始化已经选中ACPI PM timer，仍不再校准。

q35的LPC function是当前固定机器不可缺少的南桥功能；默认开启的
``CONFIG_PMTIMER`` 又使 ``pmtimer_setup(acpi_pm_base + 0x08)`` 能够接管初始哨兵。
所以到这里 ``TimerPort`` 不会仍是 ``0x40``， ``timer_setup()`` 的CPUID检查与
``tsctimer_setup()`` 都不在当前执行轨迹上。

PIT channel 2 校准属于哪条排除分支
--------------------------------

若换成没有提前提供TSC频率、也没有建立PM timer的平台或构建配置，且CPU报告TSC，
SeaBIOS才会读取I/O port ``0x61`` 的原状态，关闭speaker输出但打开timer 2 gate：

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

若这条排除分支中的CPU连TSC也不支持， ``TimerPort`` 才会保持 ``0x40``，内部timer
回退为读取PIT channel 0。两者解释了通用实现，却不能列入本章固定q35的当前状态。

内部 timer 的选择优先级
----------------------

固定q35控制流应整理为：

::

   KVM提供可用invtsc频率或稳定kvmclock
      TimerPort = 0

   否则q35 ICH9 LPC建立ACPI PM timer
      TimerPort = PMBASE + 8

选择仍由“谁先把 ``TimerPort`` 从初始哨兵改掉”实现，而不是集中式switch。用PIT
channel 2校准TSC及PIT channel 0 fallback只是其他平台/配置的后备分支。

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

``rtc_updating()`` 如果看到UIP已经清零就立即返回；如果UIP为一，则最多等待约15 ms，
期间调用 ``yield()``。但这里有一个必须保留的错误边界： ``clock_setup()`` 没有检查
它的返回值。即使等待超时，代码仍会继续分别读取秒、分、时并初始化BDA；只有后续
``INT 1Ah`` 的部分读服务会把 ``rtc_updating()`` 失败报告给调用者。因此“先等待”不
等于“只有拿到一致快照才继续”。

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

第六章已经建立PIC映射：master IRQ0对应 ``INT 08h``。现在 ``enable_hwirq`` 先解除
IRQ0屏蔽，再把中断向量指向SeaBIOS handler。主线程的32位执行环境仍保持IF=0；这里
建立的是“向量+PIC放行”状态，不表示调用返回前已经执行过一次IRQ0。SeaBIOS以后在
``yield()``、 ``check_irqs()`` 或16位调用边界短暂允许中断时，pending tick才可进入
handler。

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

``rtc_setup()`` 把PIE保持为关闭；安装 ``INT 70h`` 和放行IRQ8也不会自动产生1024 Hz
中断。 ``rtc_use()`` 用引用计数 ``RTCusers`` 管理PIE bit：第一个使用者出现时开启，
最后一个使用者离开时关闭。

典型使用者包括：

* INT 15h AH=86 微秒等待；
* INT 15h AH=83 interval callback；
* 仅在 ``ThreadControl==2`` 时，option ROM执行期间的SeaBIOS线程抢占检查。

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

tpm_setup 在固定默认路径停在哪里
--------------------------------

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

固定QEMU只在机器中存在唯一TPM interface时才把 ``tpm_get_version(tpm_find())`` 变成
有效版本，并据此生成TPM 1.2的TCPA表或TPM 2.0的TPM2表。当前固定条件没有
``-tpmdev`` 及对应TPM device；QEMU默认也不自动创建TPM。因此正常ACPI图里两张表都
不存在， ``tpm_tpm2_probe()`` 与 ``tpm_tcpa_probe()`` 都失败， ``tpm_setup()`` 立即
返回：不访问 ``0xfed40000``，不设置 ``TPM_working``，也不产生PCR extend或event-log
记录。

只有显式加入TPM的条件分支才由ACPI表取得log address/length，清零该区域并继续
``tpmhw_probe()``。这说明ACPI不只服务未来操作系统，SeaBIOS自己也依赖它取得TPM
event-log的内存布局；但不能把代码支持写成固定机器已经拥有TPM。

显式 TPM 条件分支的不同启动序列
-------------------------------

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

启动、自检、PCR bank或Spec ID等关键步骤失败时，SeaBIOS会把 ``TPM_working`` 清零，
停止后续measurement，而不是让整台虚拟机无法启动。物理存在断言失败本身不是这里
的致命条件；TPM 1.2路径仍会继续确定timeout并自检。

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

显式TPM分支启动成功后，SeaBIOS首先取得已经安装的SMBIOS structure blob，对它
计算SHA-1，并把measurement记录到PCR 1；SMBIOS缺席时这一步直接跳过。

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

执行完 ``timer_setup() → clock_setup() → tpm_setup()`` 后，
``platform_hardware_setup()`` 返回 ``maininit()``。本章停在下一次
``threads_during_optionroms()`` 尚未求值的位置。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``，调用点回到 ``maininit()``；
* CPU/mode：32位保护模式，分页关闭，A20开启，IF=0，CMOS NMI仍被每次RTC访问保持屏蔽；
* internal timer：若KVM先提供可用频率则 ``TimerPort=0`` 并读取缩放TSC，否则
  ``TimerPort=acpi_pm_base+8`` 并读取24位ICH9 PM timer；
* PIT channel 0：binary mode 2、divisor 65536，约18.2 Hz；
* BDA ``timer_counter``：已由一次RTC秒/分/时读取换算并对 ``TICKS_PER_DAY`` 取模；
* RTC UIP timeout：即使发生也未阻止上述读取，当前没有可据此宣称快照必然一致；
* IRQ0/INT 08h：IVT入口已安装，master PIC的IRQ0已解除屏蔽；
* IRQ8/INT 70h：IVT入口已安装，slave PIC的IRQ8已解除屏蔽； ``RTCusers=0``，PIE仍关闭；
* fixed default TPM：不存在TPM2/TCPA表， ``tpm_setup()`` 已返回，
  ``TPM_working=0``，没有event log、PCR extend或“Start Option ROM Scan”记录；
* 显式TPM条件分支：只有同时存在有效ACPI log表、TPM interface且startup成功时，才已
  测量条件存在的SMBIOS并向PCR 2加入option-ROM扫描动作；
* VGA Option ROM、USB/PS2、block driver与普通Option ROM：尚未进入本轮初始化；
* next entry： ``threads_during_optionroms()``。

关键边界
--------

#. 固定q35在当前入口前已经由KVM频率或ICH9 PM timer结束 ``TimerPort=0x40`` 哨兵；
   PIT校准TSC与PIT内部timer fallback不是本章当前轨迹。
#. internal deadline timer与PIT IRQ0/BDA 18.2 Hz时钟是两套用途不同的机制。
#. ``clock_setup()`` 忽略 ``rtc_updating()`` 的失败返回，不能保证初始化读取是原子RTC快照。
#. ``enable_hwirq`` 建立IVT并解除PIC屏蔽；MainThread保持IF=0，调用本身不等于handler已运行。
#. RTC IRQ8已可路由不等于periodic interrupt已开启；PIE由 ``RTCusers`` 的首尾引用控制。
#. 固定QEMU默认无TPM；TPM启动、PCR和event log只能保留为显式设备条件分支。
#. TPM测量记录实际执行链，但不在这里形成UEFI Secure Boot执行许可机制。

下一入口
--------

``maininit()`` 接下来求值：

.. code-block:: c

   if (threads_during_optionroms())
       device_hardware_setup();

固定QEMU没有发布 ``etc/threads``，所以 ``ThreadControl=1``、条件为false，提前的设备
初始化被跳过；下一章继续进入 ``vgarom_setup()``，而不是直接进入USB或block driver。

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
* `QEMU hw/i386/acpi-build.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-build.c>`_；
* `QEMU include/system/tpm.h <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/include/system/tpm.h>`_；
* `TCG PC Client Platform Firmware Profile Specification <https://trustedcomputinggroup.org/resource/pc-client-specific-platform-firmware-profile-specification/>`_；
* `ACPI Specification <https://uefi.org/specifications>`_。
