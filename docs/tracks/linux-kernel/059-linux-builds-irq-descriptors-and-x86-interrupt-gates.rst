第五十九章：Linux 怎样建立 IRQ descriptor 并把外部中断入口写入 IDT？
======================================================================

第五十八章结束时，RCU、trace event 与 context tracking 已经具备基础状态，但 Linux 还没有建立通用 IRQ descriptor，也没有把普通外部中断入口完整安装到 x86 IDT。

``start_kernel()`` 接下来执行：

.. code-block:: c

   early_irq_init();
   init_IRQ();

本章追踪到 ``init_IRQ()`` 返回，停在 ``tick_init()`` 之前。

这一段要完成两类不同工作：

* 通用 IRQ 层建立 Linux 逻辑中断号对应的 ``struct irq_desc``；
* x86 架构层建立 IRQ domain、向量分配器，并把 APIC 与普通外部中断入口写入 IDT。

这仍然不等于 CPU 已经开始接收外部中断。``local_irq_enable()`` 还在更后面。

IRQ、向量和 IDT entry 不是同一个对象
------------------------------------

在 x86 上，一次设备中断至少涉及三套编号或对象：

.. code-block:: text

   hardware interrupt source
       → Linux logical IRQ number
       → x86 interrupt vector
       → IDT gate / assembly entry

其中：

* hardware interrupt source 可能来自 8259A PIC、IOAPIC、Local APIC、MSI 或 MSI-X；
* Linux logical IRQ 是内核通用 IRQ 子系统使用的编号；
* x86 vector 是 CPU 接收中断时放入 IDT 索引的 8 位向量；
* IDT gate 保存真正进入汇编入口代码的位置和门属性。

``irq_desc`` 管理的是 Linux IRQ 的软件状态。``vector_irq`` 负责从某个 CPU 的 vector 找回 ``irq_desc``。IDT entry 只负责把 CPU 引到正确的低级入口。

``early_irq_init()`` 先建立默认 affinity
---------------------------------------

第一条调用位于 ``kernel/irq/irqdesc.c``：

.. code-block:: c

   int __init early_irq_init(void)
   {
       init_irq_default_affinity();
       initcnt = arch_probe_nr_irqs();
       ...
   }

默认 affinity 描述一个 IRQ 在没有被驱动或用户重新限制前可以投递到哪些 CPU。

当前只有 CPU0 online，但 possible CPU 集合已经建立。IRQ 子系统必须从一开始就使用正式 cpumask，而不能把当前单 CPU 状态误认为整台机器永远只有一个 CPU。

``arch_probe_nr_irqs()`` 允许架构调整可支持的 IRQ 数量，并返回启动阶段需要预先分配的 IRQ descriptor 数量。

Sparse IRQ 为什么使用 Maple Tree
-------------------------------

在启用 ``CONFIG_SPARSE_IRQ`` 时，内核不会静态创建完整的 ``irq_desc[NR_IRQS]`` 大数组，而是只为实际需要的 IRQ 分配对象。

Linux 6.12.95 使用：

.. code-block:: c

   static struct maple_tree sparse_irqs =
       MTREE_INIT_EXT(sparse_irqs, ...);

把逻辑 IRQ number 映射到动态分配的 ``struct irq_desc``。

第五十六章建立的 Maple Tree 节点 cache 因而已经开始被后续核心子系统使用。这里不是保存虚拟地址范围，而是把离散 IRQ number 作为 Maple Tree index。

对每个预分配 IRQ，``early_irq_init()`` 执行：

.. code-block:: c

   desc = alloc_desc(i, node, 0, NULL, NULL);
   irq_insert_desc(i, desc);

``alloc_desc()`` 会分配 descriptor 本体、per-CPU 统计对象和 affinity mask，然后把它插入 ``sparse_irqs``。

新建的 ``irq_desc`` 默认不能处理真实中断
--------------------------------------

``desc_set_defaults()`` 为新 descriptor 设置保守状态：

.. code-block:: text

   irq_data.irq       = logical IRQ number
   irq_data.chip      = no_irq_chip
   handle_irq         = handle_bad_irq
   IRQD_IRQ_DISABLED  = set
   IRQD_IRQ_MASKED    = set
   depth              = 1

同时初始化：

* raw spinlock；
* request mutex；
* threaded IRQ waitqueue；
* per-CPU interrupt counters；
* affinity 与 pending affinity mask；
* RCU、reference count 和 resend 状态。

所以 descriptor 建立只表示“内核已经有地方记录这个 IRQ”。它尚未绑定真实 ``irq_chip``，没有驱动的 ``irqaction``，默认处理器仍是 ``handle_bad_irq``，并且处于 disabled、masked 状态。

x86 ``arch_early_irq_init()`` 建立 vector IRQ domain
--------------------------------------------------

通用 descriptor 创建完成后，``early_irq_init()`` 调用：

.. code-block:: c

   arch_early_irq_init();

x86 路径位于 ``arch/x86/kernel/apic/vector.c``。它首先创建名为 ``VECTOR`` 的 IRQ domain：

.. code-block:: c

   x86_vector_domain = irq_domain_create_tree(...);
   irq_set_default_domain(x86_vector_domain);

IRQ domain 负责把 Linux logical IRQ 与架构硬件编号、x86 vector 和中断控制器层级联系起来。

随后建立 vector matrix：

.. code-block:: c

   vector_matrix = irq_alloc_matrix(
       NR_VECTORS,
       FIRST_EXTERNAL_VECTOR,
       FIRST_SYSTEM_VECTOR);

低向量保留给 CPU exceptions，较高的一段保留给 APIC system vectors。普通设备 IRQ 只能从中间允许的 external-vector 区间分配。

此时 vector matrix 只是分配器状态。大量设备 IRQ 尚未创建，MSI/MSI-X 也尚未配置。

``init_IRQ()`` 先建立 CPU0 的 legacy vector 映射
---------------------------------------------

下一条调用进入 ``arch/x86/kernel/irqinit.c:init_IRQ()``。

它先为 legacy IRQ 建立 CPU0 上的反向映射：

.. code-block:: c

   for (i = 0; i < nr_legacy_irqs(); i++)
       per_cpu(vector_irq, 0)[ISA_IRQ_VECTOR(i)] = irq_to_desc(i);

这表示 CPU0 若将来收到传统 ISA vector，可以通过当前 CPU 的 ``vector_irq`` 表找到对应 ``irq_desc``。

当前只是填表。IF 位仍为 0，CPU 不会因为普通 maskable external interrupt 跳入这些入口。

为什么还要准备专用 IRQ stack
--------------------------

``init_IRQ()`` 接着调用：

.. code-block:: c

   irq_init_percpu_irqstack(smp_processor_id());

x86-64 的中断入口需要为当前 CPU 准备 IRQ stack 状态，避免普通任务栈在嵌套中断或深调用链中被持续消耗。

现在只为 CPU0 执行。其他 CPU 的 per-CPU IRQ stack 会在 AP bring-up 时分别初始化。

``native_init_IRQ()`` 先初始化传统 ISA IRQ
----------------------------------------

默认 ``x86_init.irqs.intr_init`` 指向 ``native_init_IRQ()``，而它的 ``pre_vector_init`` 默认指向 ``init_ISA_irqs()``。

因此执行顺序是：

.. code-block:: text

   init_IRQ()
   → native_init_IRQ()
   → init_ISA_irqs()

``init_ISA_irqs()`` 会：

#. 初始化 boot CPU 的 Local APIC 基础；
#. 初始化 legacy PIC；
#. 为 legacy IRQ 绑定当前 legacy ``irq_chip``；
#. 将 flow handler 设为 ``handle_level_irq``；
#. 标记这些 IRQ 使用 level 语义。

这一步把最早预分配的 descriptor 从 ``no_irq_chip`` 推进到传统中断控制器可识别的状态。

QEMU q35 后面通常使用 IOAPIC 承担实际 legacy IRQ 路由。当前先建立兼容 PIC/ISA 基础，最终中断模式还要等 x86 late time initialization 重新选择和完成。

异常 IDT 与普通外部 IRQ gate 分阶段建立
-------------------------------------

Linux 在更早阶段已经建立过 early IDT，并在 ``trap_init()`` 附近完成 CPU exception handlers。

当前 ``idt_setup_apic_and_irq_gates()`` 处理的是：

* APIC system-vector gates；
* 普通 external interrupt vector gates；
* 未分配 system vector 的 spurious entry；
* 最终 IDT 的只读映射与重新加载。

它先写入 APIC 专用入口表，然后遍历可用 external vectors：

.. code-block:: c

   entry = irq_entries_start +
           IDT_ALIGN * (vector - FIRST_EXTERNAL_VECTOR);
   set_intr_gate(vector, entry);

每个 vector 指向一段按固定间隔排列的汇编 stub。stub 保存寄存器和 vector 信息，再进入统一 x86 IRQ dispatch 路径，通过 ``vector_irq`` 找到 logical IRQ descriptor。

为什么还要为未分配 vector 安装 spurious entry
--------------------------------------------

Local APIC 或异常硬件状态可能让 CPU 收到一个当前没有分配给设备的 vector。

若 IDT 中完全没有入口，CPU 会把一个可诊断的异常中断扩大成更严重的故障。Linux 因此为未分配的 system-vector 区间安装 spurious entries，使它能够记录并安全处理意外 vector。

IDT 被映射到 CPU entry area
-------------------------

完整 gate 写入后，内核执行：

.. code-block:: text

   map IDT into CPU entry area
   → reload IDTR
   → mark IDT page read-only
   → idt_setup_done = true

固定的 CPU entry area 地址减少 ``sidt`` 泄露内核随机地址的风险，也让入口路径使用稳定映射。将 IDT 页设为只读则限制普通内核写错误直接篡改中断入口。

system vectors 还要在 vector matrix 中保留
----------------------------------------

IDT gate 描述“某个 vector 到哪里执行”，vector matrix 描述“哪些 vector 可以分配给设备”。

``lapic_assign_system_vectors()`` 会把已经标记的 system vectors 在 matrix 中保留，并预占 legacy ISA vectors。

这可以避免后续 MSI 或 IOAPIC 动态分配误用：

* Local APIC timer vector；
* reschedule IPI；
* call-function IPI；
* error、spurious 等系统向量；
* 已保留的 ISA vector。

建立 gate 不代表有设备 handler
----------------------------

本章结束时已经形成：

.. code-block:: text

   external hardware vector
   → IDT assembly entry
   → per-CPU vector_irq lookup
   → struct irq_desc

仍然缺少大量后续工作：

* 设备驱动尚未调用 ``request_irq()``；
* 大部分 IOAPIC/MSI IRQ 尚未分配；
* Local APIC timer 尚未注册为 clock-event device；
* tick、timer、softirq 与 timekeeping 尚未建立完整连接；
* CPU IF 位仍关闭。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``init_IRQ()`` 已返回，``tick_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* IRQ descriptors：启动所需 descriptor 已分配并放入 sparse IRQ Maple Tree；
* x86 IRQ domain：``VECTOR`` domain 与 vector matrix 已建立；
* legacy IRQ：CPU0 vector 映射、PIC/ISA chip 和 level handler 基础已建立；
* IDT：exception、APIC system vector 与普通 external IRQ gates 已安装；
* IDT storage：已映射到 CPU entry area 并设为只读；
* device irqaction：绝大多数尚不存在；
* interrupts：IF 位仍关闭，``early_boot_irqs_disabled`` 仍为 true；
* scheduler tick：尚未启动；
* AP、initramfs、PID 1：均未开始。

下一条控制流是：

.. code-block:: c

   tick_init();

下一章进入 tick、RCU no-CB、timer wheel、SRCU、hrtimer 和 softirq 软件基础。中断入口已经存在，但 CPU0 仍不会接受普通外部 IRQ。

资料
----

* `Linux 6.12.95 init/main.c：early_irq_init、init_IRQ 与 tick_init 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/irq/irqdesc.c：IRQ descriptor 默认状态与 sparse IRQ Maple Tree <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/irq/irqdesc.c>`_
* `Linux 6.12.95 arch/x86/kernel/apic/vector.c：VECTOR domain 与 vector matrix <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/vector.c>`_
* `Linux 6.12.95 arch/x86/kernel/irqinit.c：legacy IRQ、init_IRQ 与 native_init_IRQ <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/irqinit.c>`_
* `Linux 6.12.95 arch/x86/kernel/idt.c：APIC、external IRQ gates 与只读 IDT <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/idt.c>`_
* `Linux generic IRQ 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/genericirq.rst>`_