第五十九章：Linux怎样建立IRQ描述符与x86中断入口？
===============================================

第五十八章结束时，工作队列、RCU和追踪事件已经取得早期对象，CPU0仍以IF位为0的状态执行
``start_kernel()``。接下来的两次调用分别进入通用IRQ层和x86架构层：

.. code-block:: c

   early_irq_init();
   init_IRQ();

本章追踪到 ``init_IRQ()`` 返回，下一章从 ``tick_init()`` 开始。这里会建立逻辑IRQ、x86向量
以及CPU入口之间的联系；但是 ``local_irq_enable()`` 仍在更后面，因此入口可用不等于CPU0已经
接受普通可屏蔽中断。

逻辑IRQ、x86向量与CPU入口承担不同职责
------------------------------------

设备或中断控制器提供硬件中断源；通用IRQ层用逻辑IRQ编号查找 ``struct irq_desc``；x86再为
可投递的中断选择8位向量。CPU收到向量后，FRED事件入口或IDT门把执行引入架构汇编入口，后者
再根据当前CPU的 ``vector_irq`` 找回描述符。

因此， ``irq_desc`` 保存中断的软件状态和处理动作， ``vector_irq`` 保存逐CPU的反向映射，
FRED或IDT负责进入内核。创建其中一个对象不会自动完成另外两个对象，也不会替设备驱动登记
``irqaction``。

``early_irq_init()`` 先确定默认亲和掩码
-------------------------------------

在SMP构建中， ``init_irq_default_affinity()`` 检查启动参数阶段建立的
``irq_default_affinity``。如果掩码尚不可用，它用 ``GFP_NOWAIT`` 尝试申请；如果最终掩码为空，
则把 ``cpu_possible_mask`` 中的所有CPU加入掩码。 ``irqaffinity=`` 参数的解析还会强制加入启动CPU，避免错误
参数把CPU0排除。非SMP构建中的该函数为空。

这里的亲和掩码表示尚未被驱动或用户另行限制时允许选择的CPU，不表示这些CPU已经在线。当前
``cpu_online_mask`` 仍只有CPU0， ``cpu_possible_mask`` 中的其他CPU尚未执行。

x86 ``arch_probe_nr_irqs()`` 依据当前 ``gsi_top``、传统IRQ数量、 ``nr_cpu_ids`` 以及
``CONFIG_PCI_MSI`` 调整 ``total_nr_irqs``，并通过 ``legacy_pic->probe()`` 给出启动阶段要预先
准备的传统IRQ数量。正文没有固定构建配置和CPU数量，所以不写死描述符总数。

稀疏IRQ构建把描述符存入Maple Tree
--------------------------------

启用 ``CONFIG_SPARSE_IRQ`` 时， ``sparse_irqs`` 是带外部互斥锁、范围分配和RCU读取标志的
``struct maple_tree``。 ``early_irq_init()`` 对每个预分配编号调用 ``alloc_desc()``，
再通过 ``mas_store_gfp()`` 把返回的指针写入该树。第五十六章创建的Maple Tree节点缓存由此
开始服务于核心子系统，但这棵树保存的是离散逻辑IRQ编号，不是进程虚拟地址范围。

``alloc_desc()`` 为每个编号申请描述符、逐CPU统计对象以及构建配置要求的亲和掩码，并初始化
自旋锁、请求互斥锁、等待队列、重发状态、引用和RCU字段。 ``desc_set_defaults()`` 设置：

.. code-block:: c

   desc->irq_data.irq  = irq;
   desc->irq_data.chip = &no_irq_chip;
   desc->handle_irq    = handle_bad_irq;
   desc->depth         = 1;

同时， ``IRQD_IRQ_DISABLED`` 与 ``IRQD_IRQ_MASKED`` 均被置位。正常返回的描述符因此只有安全
的占位状态：它还没有真实 ``irq_chip``、设备处理动作或可投递状态。

未启用 ``CONFIG_SPARSE_IRQ`` 时，内核改为遍历静态 ``irq_desc[NR_IRQS]``，对每个元素执行
``init_desc()``。这一分支不使用 ``sparse_irqs``。章节结论只要求相应构建分支中的描述符完成
初始化，不把Maple Tree写成所有构建的共同事实。

``arch_early_irq_init()`` 创建x86向量域
-------------------------------------

通用描述符处理完成后， ``early_irq_init()`` 把控制权交给
``arch_early_irq_init()``。x86实现先为名称 ``VECTOR`` 创建固件节点和
``x86_vector_domain``，再把它设为默认IRQ域；随后申请 ``vector_searchmask``，并创建只在
``FIRST_EXTERNAL_VECTOR`` 到 ``FIRST_SYSTEM_VECTOR`` 之间搜索的 ``vector_matrix``。必需对象
缺失由 ``BUG_ON()`` 处理，正常路径不会带着空向量域继续。

低编号向量留给CPU异常，高编号向量留给架构系统事件，普通设备中断只能使用中间范围。向量矩阵
此时只是分配和保留账本，大部分IOAPIC、MSI与MSI-X中断仍未申请具体向量。

函数最后执行 ``arch_early_ioapic_init()``。在启用IOAPIC的实现中，它为已经枚举到的每个
IOAPIC尝试分配保存路由寄存器的内存；分配失败只打印错误并使该IOAPIC不能完成挂起、恢复状态
保存，不阻止本次函数返回0。这一步同样没有编程设备路由。

``init_IRQ()`` 先连接CPU0的传统向量和IRQ栈
----------------------------------------

``init_IRQ()`` 先把每个传统IRQ的 ``irq_to_desc(i)`` 写入CPU0的
``vector_irq[ISA_IRQ_VECTOR(i)]``。这只是为以后从传统向量反查描述符，不能让中断越过当前
关闭的IF位。

随后， ``irq_init_percpu_irqstack(0)`` 为CPU0取得硬中断栈顶。启用相应虚拟映射方案时，它
建立带保护页的IRQ栈映射；不能使用该方案时，它采用逐CPU后备存储。若映射失败，
``init_IRQ()`` 的 ``BUG_ON()`` 终止正常路径。其他可能CPU要在各自启动时单独完成这一步。

``native_init_IRQ()`` 建立传统控制器基础
--------------------------------------

默认的 ``x86_init.irqs.intr_init`` 指向 ``native_init_IRQ()``，其第一步调用
``x86_init.irqs.pre_vector_init``；默认实现是 ``init_ISA_irqs()``。该函数执行
``init_bsp_APIC()``，初始化当前选择的 ``legacy_pic``，再把每个传统IRQ的芯片设为
``legacy_pic->chip``、流处理函数设为 ``handle_level_irq``，并加上 ``IRQ_LEVEL`` 状态。

这会把相应描述符从 ``no_irq_chip`` 占位状态推进到传统中断控制器的初始状态。固定平台为QEMU
q35，但最终CPU、构建配置和完整设备参数未固定；后续 ``late_time_init()`` 仍要选择并建立最终
中断模式，当前不能把传统PIC初始化写成IOAPIC路由已经完成。

FRED与IDT是互斥的入口完成分支
----------------------------

``native_init_IRQ()`` 接着根据构建和CPU特性选择入口形式。若构建包含
``CONFIG_X86_FRED``，它先调用 ``fred_complete_exception_setup()``：低于
``FIRST_EXTERNAL_VECTOR`` 的向量被标记为系统向量，已有FRED系统向量处理函数得到保留，未登记
的系统向量槽改指向FRED意外中断处理函数。

只有当前CPU没有 ``X86_FEATURE_FRED`` 时，源码才调用
``idt_setup_apic_and_irq_gates()``。该函数先把 ``apic_idts`` 中的系统入口写入IDT；再为普通
外部向量写入按 ``IDT_ALIGN`` 间隔排列的汇编入口；启用Local APIC时，还为未分配的高位系统
向量安装意外中断入口。完成后，它把IDT页以只读属性映射到CPU入口区域，重新加载
``idt_descr``，把原表页设为只读，并将 ``idt_setup_done`` 置为真。

如果CPU实际启用FRED，该IDT函数不会执行，外部中断通过FRED入口处理。由于最终CPU模型和构建
配置没有固定，本章保留两条路径，不再把“完整外部IDT门已经写入”当作无条件事实。

系统向量和传统向量进入分配账本
----------------------------

无论采用FRED还是IDT， ``native_init_IRQ()`` 都执行
``lapic_assign_system_vectors()``。它先把 ``system_vectors`` 中已有的向量标成系统占用；传统
IRQ多于一个时单独保留PIC级联向量；随后把向量矩阵的启动CPU状态置为在线，并把其余预分配的
传统向量记为已分配。这样，后续的动态IOAPIC或MSI分配不会占用这些入口。

若既没有ACPI枚举的IOAPIC，也没有设备树IOAPIC，并且存在传统IRQ，
``native_init_IRQ()`` 还尝试用 ``request_irq()`` 为IRQ2登记 ``no_action`` 级联动作。q35的
正常ACPI IOAPIC路径会跳过这个条件分支；正文仍按源码条件记录，避免把未固定输入推断为实际
登记结果。

本章结束状态
------------

``init_IRQ()`` 返回后，选定构建方式下的通用IRQ描述符已经初始化，x86
``x86_vector_domain``、向量搜索掩码和向量矩阵已经建立。CPU0具有传统向量反向映射和硬中断
栈；传统IRQ描述符已连接初始芯片与流处理函数。CPU入口采用FRED完成表或采用已完成并只读映射
的IDT，取决于构建和CPU特性。CPU0的IF位仍为0，应用处理器、普通设备驱动以及调度时钟均未
开始。

关键边界
--------

* ``irq_desc``、x86向量和FRED或IDT入口是三类对象，不能合并成一个“中断已经工作”的状态。
* ``CONFIG_SPARSE_IRQ`` 决定描述符使用Maple Tree还是静态数组。
* 新描述符初始处于禁用、屏蔽状态，并以 ``no_irq_chip`` 和 ``handle_bad_irq`` 占位。
* ``arch_early_ioapic_init()`` 保存IOAPIC寄存器空间，不会完成IOAPIC路由编程。
* ``X86_FEATURE_FRED`` 决定是否跳过 ``idt_setup_apic_and_irq_gates()``。
* 传统PIC基础和向量保留不等于q35的最终IOAPIC模式已经选定。
* 本章没有执行 ``local_irq_enable()``，所以不存在由普通外部中断引起的异步控制流。

下一入口
--------

``start_kernel()`` 的下一条语句是：

.. code-block:: c

   tick_init();

第60章将建立时钟滴答管理掩码、定时器队列、SRCU正常排队路径、高精度定时器以及小任务软中断
入口，但仍不会在本章打开IF位。

资料
----

* `Linux 7.2-rc1 init/main.c：通用IRQ与架构IRQ调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1076-L1083>`_
* `Linux 7.2-rc1 kernel/irq/irqdesc.c：描述符初始化与稀疏IRQ分支 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/irq/irqdesc.c#L120-L195>`_
* `Linux 7.2-rc1 kernel/irq/irqdesc.c：early_irq_init实现 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/irq/irqdesc.c#L552-L618>`_
* `Linux 7.2-rc1 arch/x86/kernel/apic/vector.c：IRQ数量、向量域与矩阵 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/vector.c#L717-L820>`_
* `Linux 7.2-rc1 arch/x86/kernel/irqinit.c：CPU0传统向量、IRQ栈与入口分支 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/irqinit.c#L54-L113>`_
* `Linux 7.2-rc1 arch/x86/kernel/idt.c：APIC和普通中断门 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/idt.c#L278-L325>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_fred.c：FRED入口完成步骤 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_fred.c#L125-L167>`_
* `Linux 7.2-rc1 arch/x86/kernel/apic/io_apic.c：早期IOAPIC保存区 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/io_apic.c#L218-L248>`_
