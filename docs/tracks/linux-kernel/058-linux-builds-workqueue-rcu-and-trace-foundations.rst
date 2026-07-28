第五十八章：Linux怎样建立工作队列、RCU与追踪事件的早期基础？
=============================================================

第五十七章结束时，CPU0的 ``rq`` 已经把 ``init_task`` 登记为当前任务和空闲任务，
``scheduler_running`` 也已置为1；普通中断仍然关闭。 ``start_kernel()`` 随后依次执行：

.. code-block:: c

   radix_tree_init();
   housekeeping_init();
   workqueue_init_early();
   rcu_init();
   kvfree_rcu_init();
   trace_init();

   if (initcall_debug)
       initcall_debug_enable();

   context_tracking_init();

本章追踪到 ``context_tracking_init()`` 返回，下一章从 ``early_irq_init()`` 开始。这里建立的
对象将供中断、定时器和后续初始化函数使用，但当前执行者仍是CPU0上的 ``init_task``，
控制流没有离开 ``start_kernel()``。

``radix_tree_init()`` 建立共享的节点分配基础
-------------------------------------------

``radix_tree_init()`` 先用三个 ``BUILD_BUG_ON()`` 检查标记位、分配标志和
``XA_CHUNK_SIZE`` 是否能放入实现规定的字段，随后创建
``radix_tree_node_cachep``：

.. code-block:: c

   radix_tree_node_cachep =
       kmem_cache_create("radix_tree_node",
                         sizeof(struct radix_tree_node), 0,
                         SLAB_PANIC | SLAB_RECLAIM_ACCOUNT,
                         radix_tree_node_ctor);

构造函数会清零节点并初始化 ``private_list``。 ``SLAB_PANIC`` 表明这个专用缓存创建失败
时不会沿正常启动路径继续； ``SLAB_RECLAIM_ACCOUNT`` 则把其中可回收的内存计入相应统计。
第五十五章已完成SLUB的早期建立，因此本章可以创建该缓存。

基数树、XArray和IDR共用 ``struct radix_tree_node`` 这一节点形式。这里创建的只是节点
分配来源，没有向页缓存加入文件页，也没有为某个文件系统建立索引树。第五十六章建立的
``maple_node_cache`` 服务于Maple Tree；二者用途不同，不能因为Maple Tree已经存在就省略
本次初始化。

每个CPU还有静态的 ``radix_tree_preloads``。需要在不能睡眠的临界区扩展树时，调用者可先
在可分配内存的上下文中预留节点。 ``radix_tree_init()`` 用
``cpuhp_setup_state_nocalls()`` 登记 ``radix_tree_cpu_dead()``；CPU以后下线时，回调释放该CPU
尚未消耗的预留节点。登记失败只触发 ``WARN_ON()``，本章不会因此创建或下线任何应用处理器。

``housekeeping_init()`` 固化后台工作的CPU集合
--------------------------------------------

启动参数可以通过 ``isolcpus=``、 ``nohz_full=`` 等入口，把部分CPU排除在某些内核后台活动
之外。参数解析阶段使用 ``memblock`` 内存保存各类 ``housekeeping.cpumasks``，当前函数负责在普通
分配器可用后完成交接。

若 ``housekeeping.flags`` 为零， ``housekeeping_init()`` 立即返回，查询未被覆盖的类别时仍以
``cpu_possible_mask`` 为准。固定GRUB菜单给出的命令行没有上述参数；但最终构建配置、内建
命令行和可选 ``bootconfig`` 没有固定，因此正文保留 ``housekeeping.flags`` 非零的源码分支。

存在隔离设置时，函数先启用 ``housekeeping_overridden`` 静态分支；如果
``HK_FLAG_KERNEL_NOISE`` 已设置，还执行 ``sched_tick_offload_init()``。随后，它按已设置的
类别逐一用 ``kmalloc()`` 申请正式 ``cpumask``，复制原掩码，把RCU指针改指向新对象，再释放
原来的 ``memblock`` 对象。掩码为空会产生警告；正式掩码申请失败也会警告并提前结束，因而可能只
完成前面若干类别的交接。

把这一步放在 ``workqueue_init_early()`` 之前，使无绑定工作队列从创建之初就能读取正确的
``HK_TYPE_DOMAIN`` 掩码，而不必先覆盖全部CPU再修改。

``workqueue_init_early()`` 创建队列和工作池的描述对象
----------------------------------------------------

``workqueue_init_early()`` 是工作队列三阶段初始化的第一阶段。它首先申请
``wq_online_cpumask``、 ``wq_unbound_cpumask``、 ``wq_requested_unbound_cpumask`` 和
``wq_isolated_cpumask``。这些申请由 ``BUG_ON()`` 保护；正常返回意味着四个掩码均已取得。

``wq_online_cpumask`` 复制当前的 ``cpu_online_mask``，此时只包含CPU0；
``wq_unbound_cpumask`` 先复制 ``cpu_possible_mask``，再依次受 ``HK_TYPE_DOMAIN`` 和
``workqueue.unbound_cpus`` 启动参数限制。若一次限制会让结果变为空集，源码打印警告并忽略
该限制。 ``wq_isolated_cpumask`` 则记录 ``cpu_possible_mask`` 中不属于后台工作域的部分。

函数接着为 ``cpu_possible_mask`` 中的每个CPU初始化两类底半部工作池以及普通、高优先级CPU工作池。每个池都会
建立锁、工作链表、属性、CPU与NUMA节点关系，并取得池编号；底半部工作池还连接用于触发普通
或高优先级小任务软中断的 ``irq_work``。应用处理器尚未执行，但它们对应的池描述已经存在。

最后，函数创建 ``system_wq``、 ``system_highpri_wq``、 ``system_unbound_wq``、
``system_freezable_wq``、 ``system_bh_wq`` 等系统工作队列。任一必需对象缺失都会触发
``BUG_ON()``。正常返回后，后续代码可以创建工作队列，也可以排队、取消或整理工作项。

这些条件仍不足以执行普通工作项。源码把实际执行推迟到 ``workqueue_init()``；那时内核线程
已经能够创建和调度。当前既没有工作线程，也没有 ``kthreadd``，所以排入普通工作队列的工作
只能等待后续阶段。底半部工作队列还需要软中断执行条件，本章同样没有打开中断。

``rcu_init()`` 把启动CPU接入RCU核心
---------------------------------

``rcu_init()`` 的具体实现由构建配置决定。采用Tree RCU时，函数先运行早期自检并公布配置，
计算 ``rcu_node`` 层级，初始化全局 ``rcu_state`` 和各层节点。若 ``use_softirq`` 为真，
它把 ``RCU_SOFTIRQ`` 连接到 ``rcu_core_si()``；登记动作可以发生在
``softirq_init()`` 之前，因为 ``open_softirq()`` 只写入静态动作表。

随后，Tree RCU确认当前在线CPU不超过一个，并对CPU0依次执行
``rcutree_prepare_cpu()``、 ``rcutree_report_cpu_starting()`` 和
``rcutree_online_cpu()``。这一步把CPU0的 ``rcu_data``、叶节点归属和在线状态连接起来，
没有让 ``cpu_possible_mask`` 中的其他CPU开始执行。

Tree RCU还创建 ``rcu_gp_wq`` 与 ``sync_wq``。它们分别供Tree SRCU、加速宽限期和同步工作
使用；创建失败会产生警告。工作队列对象已经存在不代表其中的普通工作现在能够运行，实际执行
仍受上一节所述的工作线程边界约束。若构建选择Tiny RCU，则 ``rcu_init()`` 走另一套较小实现，
不能把Tree RCU的节点层级和工作队列写成所有构建都具备。

正常返回后，RCU核心已能接收读侧临界区、指针发布和回调登记；无周期时钟、无应用处理器、
无RCU内核线程的当前状态，仍不等于全部宽限期推进条件都已进入最终运行阶段。

``kvfree_rcu_init()`` 是否建立批量回收取决于构建配置
--------------------------------------------------

若没有启用 ``CONFIG_KVFREE_RCU_BATCHED``， ``kvfree_rcu_init()`` 是空函数：
带 ``rcu_head`` 的对象通过 ``call_rcu()`` 延后释放，单参数形式则同步等待宽限期后执行
``kvfree()``。

启用批量回收时，函数创建无绑定且可用于内存回收的 ``rcu_reclaim_wq``，然后遍历
``cpu_possible_mask`` 中的每个CPU，初始化两组 ``rcu_work``、批量释放链表、监视延迟工作和
页缓存补充延迟工作，并把
``kfree_rcu_cpu.initialized`` 置为真。它最后尝试创建并登记 ``slab-kvfree-rcu`` 收缩器；
收缩器申请失败会打印错误并返回，已经完成的逐CPU状态不会撤销。这里仍只是建立批处理和调度
对象，没有证据表明本章已经回收了某个实际对象。

``trace_init()`` 登记追踪事件而不重复分配早期缓冲区
--------------------------------------------------

第五十六章的 ``early_trace_init()`` 已尝试分配全局追踪缓冲区并初始化早期事件入口。当前
``trace_init()`` 只执行两项工作：

.. code-block:: c

   trace_event_init();
   if (boot_instance_index)
       enable_instances();

``trace_event_init()`` 创建 ``ftrace_event_field`` 与 ``trace_event_file`` 的SLAB缓存，初始化
系统调用追踪事件，遍历链接器收集的追踪事件并把初始化成功的项目加入 ``ftrace_events``，
登记触发命令和事件命令，应用启动参数请求的早期事件，最后建立通用字段与公共字段。个别字段
或事件初始化失败会产生警告或跳过对应项目，不应据此声称全部事件必然可用。

若启动参数曾写入追踪实例说明， ``enable_instances()`` 才解析这些说明并创建或恢复相应实例；
否则该分支不执行。 ``trace_init()`` 没有再次调用 ``tracer_alloc_buffers()``，也没有挂载
``tracefs``。因而本章新增的是事件定义和可选实例，而不是把第五十六章的缓冲区工作重复一遍。

``initcall_debug`` 为后续初始化函数登记追踪回调
---------------------------------------------

若解析后的 ``initcall_debug`` 为真， ``start_kernel()`` 在 ``trace_init()`` 之后执行
``initcall_debug_enable()``。启用追踪点的构建会为初始化函数的开始、结束和级别分别登记
回调，登记失败通过 ``WARN()`` 报告；没有追踪点支持时，该函数为空。固定GRUB命令行没有
``initcall_debug``，但最终命令行输入没有完全固定，因此两条路径都保留。

``context_tracking_init()`` 可能是空函数
--------------------------------------

只有启用 ``CONFIG_CONTEXT_TRACKING_USER_FORCE`` 时， ``context_tracking_init()`` 才遍历每个
``cpu_possible_mask`` 中的CPU并调用 ``ct_cpu_track_user()``。首次处理每个CPU时，它设置
``context_tracking.active`` 并增加 ``context_tracking_key``；首次全局处理还可为
``init_task`` 设置 ``TIF_NOHZ``，并检查此时任务表仍为空。没有该构建选项时，头文件把
``context_tracking_init()`` 定义为空函数。

因此，本章不能无条件声称所有CPU已经启用用户态上下文追踪。无论构建分支如何，当前CPU0仍在
内核态执行 ``start_kernel()``，没有用户任务，也没有发生用户态、客户机或空闲扩展静止状态
之间的切换。

本章结束状态
------------

``context_tracking_init()`` 返回后，CPU0仍以关闭普通中断的状态执行 ``init_task``。
基数树节点缓存与CPU下线清理回调已经登记；后台工作CPU掩码已经保持默认值，或按启动参数
完成普通分配器交接。工作队列、逐CPU工作池及Tree RCU或所选RCU实现的早期对象已经建立，
普通工作线程尚未开始执行。追踪事件定义与可选启动实例已处理，上下文追踪则取决于构建配置。

关键边界
--------

* ``radix_tree_init()`` 创建节点缓存，不会把磁盘页加入页缓存，也不会创建Maple Tree节点缓存。
* 固定GRUB命令行没有CPU隔离参数，但未固定的内建命令行和 ``bootconfig`` 要求保留
  ``housekeeping.flags`` 非零分支。
* ``workqueue_init_early()`` 允许创建和排队工作，不等于普通工作线程已经执行。
* Tree RCU、Tiny RCU以及批量 ``kvfree_rcu`` 都是构建分支，不能合并成单一必然状态。
* ``trace_init()`` 登记事件并处理可选实例，不重复第五十六章的早期缓冲区分配。
* ``context_tracking_init()`` 在未启用 ``CONFIG_CONTEXT_TRACKING_USER_FORCE`` 时不改变状态。
* 本章没有建立通用IRQ描述符，没有打开CPU的IF位，也没有产生调度时钟中断。

下一入口
--------

``start_kernel()`` 的下一条语句是：

.. code-block:: c

   early_irq_init();

第59章将从通用IRQ描述符开始，随后进入x86向量域、传统中断基础以及FRED或IDT入口分支。

资料
----

* `Linux 7.2-rc1 init/main.c：本章调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1052-L1078>`_
* `Linux 7.2-rc1 lib/radix-tree.c：节点缓存与CPU下线回调 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/radix-tree.c#L1569-L1607>`_
* `Linux 7.2-rc1 kernel/sched/isolation.c：housekeeping掩码交接 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/isolation.c#L165-L193>`_
* `Linux 7.2-rc1 kernel/workqueue.c：工作队列第一阶段初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c#L7961-L8077>`_
* `Linux 7.2-rc1 kernel/rcu/tree.c：Tree RCU初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree.c#L4901-L4949>`_
* `Linux 7.2-rc1 mm/slab_common.c：批量kvfree-RCU初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slab_common.c#L2168-L2219>`_
* `Linux 7.2-rc1 kernel/trace/trace.c：追踪事件与启动实例入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace.c#L9941-L9962>`_
* `Linux 7.2-rc1 kernel/trace/trace_events.c：早期事件登记 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace_events.c#L4685-L4849>`_
* `Linux 7.2-rc1 kernel/context_tracking.c：强制用户上下文追踪分支 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/context_tracking.c#L677-L708>`_
