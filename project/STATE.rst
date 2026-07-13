项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-061``。最新三章：

#. ``LK-BOOT-059``：Linux 怎样建立 IRQ descriptor 并把外部中断入口写入 IDT？
#. ``LK-BOOT-060``：Linux 怎样建立 tick、timer wheel、hrtimer 与 softirq？
#. ``LK-BOOT-061``：Linux 怎样建立 timekeeping，并把 x86 定时器初始化延后？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 6.12.95
   Linux source tag  = gregkh/linux v6.12.95
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

当前控制流位置
--------------

第五十九至六十一章已经完成：

::

   early_irq_init()
   → initialize default IRQ affinity
   → allocate boot IRQ descriptors
   → insert sparse IRQ descriptors into Maple Tree
   → create x86 VECTOR IRQ domain and vector matrix
   → init_IRQ()
   → map legacy ISA vectors to CPU0 irq_desc objects
   → initialize CPU0 IRQ stack
   → initialize legacy PIC/ISA IRQ chip and flow handlers
   → install APIC system and external IRQ gates into IDT
   → map IDT into CPU entry area and mark it read-only
   → tick_init()
   → initialize tick broadcast and NO_HZ management
   → rcu_init_nohz()
   → finalize optional RCU no-CB masks and callback offload layout
   → timers_init()
   → initialize per-possible-CPU timer wheel bases
   → register TIMER_SOFTIRQ
   → srcu_init()
   → enable normal SRCU delayed-work queueing
   → hrtimers_init()
   → initialize CPU0 hrtimer bases and HRTIMER_SOFTIRQ
   → softirq_init()
   → initialize per-CPU tasklet queues and tasklet softirq actions
   → vdso_setup_data_pages()
   → allocate final VDSO/VVAR backing pages
   → timekeeping_init()
   → read x86 persistent wall clock
   → establish realtime/monotonic/raw bases
   → install jiffies as initial clocksource
   → update fast timekeeper and VDSO time data
   → time_init()
   → set late_time_init = x86_late_time_init

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``time_init()`` 已返回，``random_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task`` / ``swapper/0`` / PID 0；
* scheduler：runqueue、scheduling class 与 CPU0 idle task 已建立；
* scheduler tick：尚未启动；
* interrupts：关闭，``early_boot_irqs_disabled = true``，CPU0 IF 位仍为 0；
* IRQ descriptors：启动所需 descriptor 已建立，默认处于 disabled/masked；
* x86 IRQ：VECTOR domain、vector matrix、legacy vector mapping 与 IDT external gates 已建立；
* IDT：已映射到 CPU entry area 并设为只读；
* device irqaction：绝大多数设备尚未注册 handler；
* AP：尚未收到 INIT/SIPI；
* buddy/slab/vmalloc：可用；
* timer wheel：所有 possible CPU 的 base 已建立；
* hrtimer：CPU0 base 和 softirq handler 已建立；
* softirq：TIMER、HRTIMER、TASKLET 与 HI action 已登记，``ksoftirqd`` 尚未创建；
* tick framework：broadcast/NO_HZ 管理已建立，CPU0 最终 clock-event device 尚未完成；
* timekeeping：realtime/monotonic/raw 基础已建立，初始 clocksource 为 jiffies；
* VDSO/VVAR：正式 backing pages 和 time data 已准备；
* x86 hardware time：``late_time_init`` 已登记，HPET/PIT/TSC 与最终 interrupt mode 尚未执行；
* workqueue：可创建和排队，worker kthread 尚未运行；
* RCU/SRCU：核心结构与 SRCU 正常 queueing 基础已建立，相关 kthread 尚未运行；
* 正式 console：尚未初始化；
* initramfs：尚未解包；
* PID 1 / PID 2：尚未创建。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():random_init()`` 开始，继续 ``kfence_init()``、``boot_init_stack_canary()``、``perf_event_init()``、``profile_init()`` 与 ``call_function_init()``，随后核对 ``early_boot_irqs_disabled = false`` 和 ``local_irq_enable()``。保持状态边界清晰：IDT gate 与 IRQ descriptor 已存在，timer/softirq/timekeeper 软件结构已建立，只有执行 ``local_irq_enable()`` 后 CPU0 才开始接受普通 maskable external IRQ。x86 HPET/PIT/TSC 的实际 late 初始化仍在更后的 ``acpi_early_init()`` 之后。
