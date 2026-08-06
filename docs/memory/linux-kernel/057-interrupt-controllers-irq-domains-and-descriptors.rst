第057章：中断控制器、IRQ Domain 与 IRQ 描述符
============================================

核心知识点
----------

中断控制器负责硬件路由
   Interrupt controller 接收设备事件，维护屏蔽、优先级和 pending 状态，选择目标 CPU，并把事件送入架构中断入口。APIC、GIC、GPIO 控制器和 MSI/MSI-X 都属于这条硬件路径的不同层级。

一个事件可以经过多级控制器
   GPIO pin 可能先进入 GPIO 控制器，再级联到 GIC 或 APIC，最后到达 CPU。Linux 必须保存每一层控制器之间的映射和操作关系。

``hwirq`` 是控制器局部编号
   相同数值可以在不同控制器中重复出现。只有把 ``hwirq`` 与所属 ``irq_domain`` 放在一起，才能确定它表示哪一个硬件中断源。

``irq_domain`` 负责编号翻译
   固件提供 interrupt specifier，domain 的 translate/xlate 逻辑把它解释为 ``hwirq`` 和触发类型，再映射成 Linux 管理的 IRQ 编号。

Linux IRQ 对应 ``irq_desc``
   ``irq_desc`` 是 generic IRQ 层的核心对象，保存锁、状态、统计、flow handler、action 链以及控制器相关数据。Linux IRQ 编号本质上是描述符空间中的索引身份。

``irq_data`` 表示某一控制器层
   它连接 Linux IRQ、``hwirq``、``irq_domain``、chip data 和 ``irq_chip``。分层 domain 中，一个逻辑 IRQ 可以沿父子关系拥有多层 ``irq_data``。

``irq_chip`` 封装控制器操作
   mask、unmask、ack、eoi、set_type 和 set_affinity 等硬件动作由控制器驱动实现。设备驱动不直接承担通用控制器流控。

Flow handler 组织触发协议
   ``handle_level_irq()``、``handle_edge_irq()`` 和 ``handle_fasteoi_irq()`` 等路径负责组织 level、edge、EOI 等通用顺序，再调用具体设备 action。

设备 handler 处理业务状态
   驱动通过 ``request_irq()`` 或 ``request_threaded_irq()`` 注册 ``irqaction``。共享 IRQ 中，每个 handler 都必须确认事件是否属于本设备，不属于时返回 ``IRQ_NONE``。

控制器确认与设备清除不是一回事
   ACK 或 EOI 多属于控制器协议；设备寄存器中的 pending 条件仍需驱动按硬件规则清除。任何一层顺序错误都可能造成重复触发或丢事件。

IRQ 生命周期必须与设备一致
   注册、启用、屏蔽、同步和释放都属于同一个 IRQ 对象生命周期。设备拆除前必须先停止新事件，再等待正在运行的 handler 和线程退出。

关键路径
--------

从设备事件到驱动 handler：

::

   设备产生中断条件
   → 本地控制器记录 hwirq
   → 必要时级联到父控制器
   → 父控制器把向量投递到目标 CPU
   → 架构入口进入 generic IRQ 层
   → irq_domain 将 hwirq 映射为 Linux IRQ
   → 找到 irq_desc
   → flow handler 调用 irq_chip 完成通用流控
   → 遍历 irqaction 并调用驱动 handler
   → 驱动确认设备并安排后续处理

建立 IRQ 映射：

::

   固件提供 interrupt specifier
   → irq_domain 解析 hwirq 与触发类型
   → 分配或查找 Linux IRQ 描述符
   → 绑定 irq_data、irq_chip 与 chip data
   → 设置 edge、level 或 fasteoi flow handler
   → 设备驱动取得 Linux IRQ
   → request_irq 注册 action

安全释放 IRQ：

::

   设备进入 stopping 状态
   → 阻止设备继续产生事件
   → mask 或 disable IRQ
   → synchronize_irq 等待正在执行的 handler
   → 停止 IRQ thread 与延迟工作
   → free_irq 或 devres 释放 action
   → 最后释放设备对象和控制器资源

概念辨析
--------

``hwirq`` 与 Linux IRQ
   ``hwirq`` 属于某个控制器的局部编号；Linux IRQ 属于内核描述符空间。

``irq_desc`` 与 ``irq_chip``
   ``irq_desc`` 保存一个 Linux IRQ 的运行状态；``irq_chip`` 封装控制器硬件操作。

Flow handler 与设备 handler
   Flow handler 处理通用触发和控制器协议；设备 handler 处理设备自己的 pending 状态与业务数据。

ACK、EOI 与设备状态清除
   ACK/EOI 通常面向控制器；设备 pending 位通常还要由驱动访问设备寄存器清除。

Linux IRQ 与 CPU 向量
   Linux IRQ 是内核对象编号；CPU 向量是架构入口编号，二者通过控制器和架构代码连接。

本章结论
--------

Linux 通过 ``irq_domain`` 把控制器局部 ``hwirq`` 转换为 Linux IRQ，再由 ``irq_desc``、flow handler、``irq_chip`` 与驱动 action 共同完成统一的中断管理。