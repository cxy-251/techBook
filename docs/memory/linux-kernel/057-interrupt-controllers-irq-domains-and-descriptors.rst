第057章：中断控制器、IRQ Domain 与 IRQ 描述符
============================================

本章必须记住
------------

#. Interrupt controller 负责接收设备事件、维护屏蔽和优先级状态、选择目标 CPU，并把事件路由到 CPU 中断入口。
#. APIC、GIC、GPIO interrupt controller 和 MSI/MSI-X 路径处在不同硬件层级，但都要被 Linux generic IRQ 层统一管理。
#. 一个中断路径可能经过多级控制器，例如 GPIO 控制器先识别 pin，再通过父级 GIC 或 APIC 把事件送到 CPU。
#. 每个控制器都有自己的本地硬件中断号 ``hwirq``；设备驱动通常使用 Linux 全局管理的 IRQ 编号。
#. ``hwirq`` 只有放在所属 ``irq_domain`` 中才有完整意义，不同控制器可以重复使用相同数值。
#. ``irq_domain`` 负责把 controller-local ``hwirq`` 映射到 Linux IRQ 编号，并支持反向查找。
#. 设备树、ACPI 或平台代码提供 interrupt specifier，domain 的 translate/xlate 逻辑把它解释为 hwirq 和触发类型。
#. Linear domain 适合紧凑连续 hwirq 空间，tree/radix 类映射适合稀疏空间，hierarchical domain 表达多级控制器路径。
#. Hierarchical irq domain 会把子控制器、父控制器和 CPU 投递路径串成多层 ``irq_data`` 关系。
#. Linux IRQ 编号对应一个 ``irq_desc``，它是 generic IRQ 层管理该中断的核心描述对象。
#. ``irq_desc`` 保存中断状态、锁、统计、flow handler、action 链以及控制器相关数据。
#. ``irq_data`` 描述当前层 IRQ 编号、hwirq、domain、chip data 和 ``irq_chip`` 等控制器视图。
#. ``irq_chip`` 是控制器操作表，封装 mask、unmask、ack、eoi、set_type、set_affinity 等硬件动作。
#. 设备驱动不应直接实现通用控制器流控；它通过 ``request_irq()`` 或 ``request_threaded_irq()`` 注册业务 handler。
#. 驱动注册的 handler 被挂到 ``irqaction`` 或 action 链上；共享 IRQ 可以包含多个 action。
#. Shared IRQ handler 必须检查设备状态，事件不属于本设备时返回 ``IRQ_NONE``。
#. ``IRQ_HANDLED`` 表示当前 handler 确认并处理了事件，``IRQ_WAKE_THREAD`` 表示还要唤醒对应 IRQ 线程。
#. Flow handler 负责组织触发语义和通用处理顺序，例如 level、edge、fasteoi 和 chained flow。
#. ``handle_level_irq()``、``handle_edge_irq()``、``handle_fasteoi_irq()`` 等名称表示不同触发与确认协议。
#. 电平触发中断若设备 pending 条件未清除，handler 返回后会迅速再次触发，形成中断风暴。
#. 边沿触发中断若确认或排队处理不正确，可能丢失后续边沿或重复处理状态。
#. EOI、ACK 和设备寄存器清除属于不同层次；具体顺序由 flow handler、irq_chip 和设备协议共同决定。
#. Generic IRQ 层把设备驱动 API、flow handler 和控制器操作分开，使同一驱动不依赖具体 APIC 或 GIC 实现。
#. ``generic_handle_domain_irq(domain, hwirq)`` 一类入口先通过 domain 找 Linux IRQ，再进入描述符和 flow handler 路径。
#. ``/proc/interrupts`` 展示 Linux IRQ 编号、每 CPU 累计计数、控制器或触发信息及设备名称。
#. ``/proc/interrupts`` 能证明事件进入了 Linux IRQ 路径，不能单独还原 hwirq、domain 和控制器拓扑。
#. IRQ affinity 决定控制器允许把某个 Linux IRQ 投递到哪些 CPU，具体能力受硬件和 irq_chip 支持限制。
#. 注册、启用、禁用、同步和释放 IRQ 都属于描述符生命周期；设备拆除前必须阻止新事件并等待旧 handler 退出。

必背路径
--------

从硬件事件到驱动 handler：

::

   设备产生中断条件
   → 本地 interrupt controller 记录 hwirq
   → 必要时级联到父控制器
   → 父控制器把向量投递到目标 CPU
   → 架构入口进入 generic IRQ 层
   → irq_domain 将 hwirq 映射为 Linux IRQ
   → 找到 irq_desc
   → flow handler 调用 irq_chip 完成通用流控
   → 遍历 irqaction 并调用驱动 handler
   → 确认设备状态并安排后续工作

建立 IRQ 映射：

::

   固件描述 interrupt specifier
   → irq_domain translate 得到 hwirq 与触发类型
   → 分配或查找 Linux IRQ 描述符
   → 绑定 irq_data、irq_chip 和 chip data
   → 设置 edge、level 或 fasteoi flow handler
   → 设备驱动获得 Linux IRQ
   → request_irq 注册 action

读取一个 IRQ 对象：

::

   从 /proc/interrupts 找 Linux IRQ 和设备名
   → 找驱动 request_irq 注册点
   → 找 irq_desc 与 flow handler
   → 找 irq_chip 操作
   → 找所属 irq_domain 和 hwirq
   → 继续向父 domain 和控制器驱动追踪

安全释放 IRQ：

::

   设备进入 stopping 状态
   → 禁止设备继续产生中断
   → mask 或 disable IRQ
   → 同步正在执行的 handler
   → 停止 threaded IRQ 和延迟工作
   → free_irq 或 devm 释放
   → 最后释放设备对象和控制器资源

必须区分
--------

hwirq 与 Linux IRQ
   hwirq 是某个控制器局部编号；Linux IRQ 是内核描述符空间中的管理编号。

``irq_desc`` 与 ``irq_chip``
   ``irq_desc`` 描述一个 Linux IRQ 的运行状态；``irq_chip`` 封装控制器硬件操作。

Flow handler 与设备 handler
   Flow handler 处理通用 edge/level/EOI 协议；设备 handler 处理设备业务状态。

ACK、EOI 与设备状态清除
   ACK/EOI 多属于控制器协议；设备 pending 位通常还要由驱动访问设备寄存器清除。

IRQ 编号与 CPU 向量
   Linux IRQ 是内核对象编号；CPU 向量是架构入口编号，二者可能通过控制器和架构代码映射。

一句话结论
----------

Linux 用 ``irq_domain`` 把控制器局部 hwirq 映射成 Linux IRQ，再由 ``irq_desc``、flow handler、``irq_chip`` 和驱动 action 把硬件事件变成统一可管理的处理路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 12，Interrupts, Exceptions, Softirq, Tasklet, and Workqueue；
* AIBook 章节：Chapter 57，Interrupt Controllers, IRQ Domains, and IRQ Descriptors；
* 源文件：``docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_057_Interrupt_Controllers_IRQ_Domains_and_IRQ_Descriptors.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_057_Interrupt_Controllers_IRQ_Domains_and_IRQ_Descriptors.md>`_。