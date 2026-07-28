第五十六章：Linux怎样准备Maple Tree、文本修补与早期追踪？
==========================================================

第五十五章结束时，普通空闲页已经进入伙伴系统，SLUB和虚拟地址映射管理器也已经可用。CPU0仍在
内核态执行 ``start_kernel()``，当前任务是 ``init_task``， ``IF=0``，调度器尚未初始化。接下来的
四个入口为：

.. code-block:: c

   maple_tree_init();
   poking_init();
   ftrace_init();
   early_trace_init();

本章按照Linux 7.2-rc1固定提交追踪这四项初始化。它们依次建立Maple Tree节点缓存、x86文本修补
专用页表、动态函数追踪记录以及早期追踪缓冲区。只有 ``ftrace_init()`` 可能在本章真正改写函数追踪
指令位置； ``poking_init()`` 本身只准备以后安全改写文本所需的地址空间。

Maple Tree首先取得专用SLUB缓存
-----------------------------

``maple_tree_init()`` 构造 ``kmem_cache_args``，把对齐设置为
``sizeof(struct maple_node)``，把 ``sheaf_capacity`` 设置为32，然后创建名为
``maple_node`` 的缓存。创建标志包含 ``SLAB_PANIC``，因此分配失败没有可继续执行的正常出口。

该缓存供以后Maple Tree分裂和扩展区间时分配节点。当前调用没有创建用户进程的
``mm_struct``，没有向 ``init_mm`` 插入VMA，也没有建立一棵具体的用户地址树。Maple Tree用于描述
区间；第058章仍将初始化的基数树与XArray基础用于不同的数据组织方式，两者不能互相替代。

``poking_init()`` 只预分配页表
-----------------------------

x86的 ``poking_init()`` 先调用 ``mm_alloc()`` 创建 ``text_poke_mm``；分配失败会触发
``BUG_ON``。Xen PV环境可以通过 ``paravirt_enter_mmap()`` 固定其PGD，随后
``set_notrack_mm()`` 把这份地址空间排除在上下文跟踪之外。

函数从 ``TASK_UNMAPPED_BASE`` 选择临时地址。启用 ``CONFIG_RANDOMIZE_BASE`` 时，它加入
``kaslr_get_random_long("Poking")`` 产生的页对齐偏移；如果第二页恰好落到下一PMD，基址再向后移动
一页。这样，以该地址为起点的连续两页始终位于同一个PMD之内。

``get_locked_pte()`` 为这个地址创建所需页表层级并取得PTE锁，确认PTE存在后立即解锁。新建
``mm_struct`` 中的PTE仍为空，没有映入任何内核文本页。提前分配页表是因为以后的文本修补可能发生
在原子上下文中，届时不能依赖可能睡眠或失败的页表分配。

真正执行文本修补时，x86代码才会把目标页面以不带全局属性的 ``PAGE_KERNEL`` 权限临时映射到
``text_poke_mm_addr``，切换到这份临时页表完成写入，再清除PTE、恢复原页表并刷新对应TLB范围。
因此，修补过程不会把整个 ``.text`` 永久设为可写，也不会留下同时可写可执行的常驻别名。

动态函数追踪先筛选位置记录再改写初始指令
----------------------------------------

启用动态函数追踪时， ``ftrace_init()`` 先保存本地中断状态，在中断关闭的区间调用
``ftrace_dyn_arch_init()``，然后恢复原状态。当前进入函数时 ``IF=0``，恢复后仍为0。架构初始化失败
会进入统一失败分支。

接着，函数计算 ``__start_mcount_loc`` 到 ``__stop_mcount_loc`` 的记录数。表为空时，它输出提示并将
``ftrace_disabled`` 设为1。表非空时， ``ftrace_process_locs()`` 按需排序位置记录，为
``dyn_ftrace`` 记录分配页面，然后逐项处理：

* 位置为0时跳过该项；
* 内置内核位置不属于内核正文段或初始化正文段时也跳过该项；
* 合法位置经过 ``ftrace_call_adjust()`` 后写入 ``dyn_ftrace`` 记录。

跳过单个无效位置不会使整个初始化失败。内置内核路径在记录页面分配失败时返回
``-ENOMEM``， ``ftrace_init()`` 才会进入失败分支并设置 ``ftrace_disabled=1``。

记录建立后， ``ftrace_process_locs()`` 在保存本地中断状态的区间执行
``ftrace_update_code()``。这一调用按照架构约定检查并改写内置函数追踪指令位置；第五十一章已经建立
静态修补基础，本章开头又建立了 ``text_poke_mm``，因此这里可能真正发生受控文本改写。修补完成后，
``ftrace_init()`` 将 ``last_ftrace_enabled`` 和 ``ftrace_enabled`` 设为1，并应用启动期过滤规则。

“函数追踪基础已经启用”不等于所有函数正在写入追踪缓冲区。实际启用哪些位置仍由追踪器、过滤器和
命令行选项决定。未启用相关构建配置时，调用入口可能由空实现替代；此时不能从
``start_kernel()`` 中存在函数名推断位置表或代码修补一定存在。

早期追踪缓冲区拥有独立失败路径
------------------------------

``early_trace_init()`` 先处理 ``tracepoint_printk``。该选项启用时，函数分配
``tracepoint_print_iter``；分配失败会清除选项，成功后才启用 ``tracepoint_printk_key``。
这套迭代器和追踪缓冲区不同于普通日志环形缓冲区。

随后， ``tracer_alloc_buffers()`` 依次分配全局CPU掩码、临时环形缓冲区、命令名存储、
管道CPU掩码和全局追踪缓冲区，并注册 ``CPUHP_TRACE_RB_PREPARE`` 状态。任一步失败都会沿对应路径
释放已经取得的对象；安全锁定禁止 ``tracefs`` 时，函数直接返回 ``-EPERM``。只有全部成功后，它才把
``tracing_disabled`` 从1改为0，注册严重错误和致命异常通知器、 ``nop_trace``，并应用启动期追踪选项。

``early_trace_init()`` 没有检查 ``tracer_alloc_buffers()`` 的返回值，仍会继续调用
``init_events()``。后者注册内置的追踪输出事件类型，单项注册失败只产生警告。因此，本章结束时
可能存在“事件类型已经尝试注册，但全局追踪缓冲区不可用”的状态，不能一概写成完整追踪系统已经
建立。

这些初始化放在调度器之前，使后续调度、中断和计时器启动有机会被启动期追踪观察；它们本身不要求
已经发生调度。 ``trace_init()`` 仍要等到第058章执行，用于继续初始化追踪事件和启动实例。

本章结束状态
------------

* 当前执行者：CPU0上的 ``start_kernel()``，当前任务仍为 ``init_task``；
* 精确位置： ``early_trace_init()`` 已结束， ``sched_init()`` 尚未执行；
* CPU状态：x86-64内核态， ``IF=0``，没有调度，也没有AP执行；
* Maple Tree： ``maple_node`` 缓存已经创建，尚无用户VMA或本章新建的具体Maple Tree；
* 文本修补： ``text_poke_mm``、临时双页地址和所需页表已经建立，当前PTE为空；
* 动态函数追踪：按构建配置建立记录并改写初始位置、因空表或分配失败而禁用，或者使用空实现；
* 无效函数追踪位置：逐项跳过，不会单独导致整体初始化失败；
* ``tracepoint_printk``：按命令行与迭代器分配结果启用或关闭；
* 早期追踪：全局缓冲区可能成功建立，也可能按失败路径保持 ``tracing_disabled=1``；
* 调度器、运行队列和CPU0空闲任务登记：尚未开始；设备中断仍未启用。

关键边界
--------

#. ``maple_tree_init()`` 只创建节点缓存，不创建用户地址空间或VMA。
#. ``poking_init()`` 创建页表但不映射文本页；临时文本别名只在真正修补时存在。
#. 无效位置由 ``ftrace_process_locs()`` 跳过；空表和记录页面分配失败才会使本次内置函数追踪初始化失败。
#. ``ftrace_update_code()`` 位于本章，可能真正改写内置函数追踪指令位置。
#. 函数追踪记录存在、函数追踪基础启用和函数事件正在写入缓冲区是三个不同状态。
#. ``maple_node`` 缓存分配失败会触发 ``panic()``；函数追踪与追踪缓冲区则具有禁用或清理路径。
#. ``tracepoint_printk`` 与普通日志环形缓冲区使用不同的开关和缓冲区。
#. 早期追踪位于调度器之前，不代表已经发生任务切换或计时器中断。

下一入口
--------

第057章从：

.. code-block:: c

   sched_init();

开始，并包含该函数结束后对中断状态的检查与修复，停在 ``radix_tree_init()`` 之前。

资料
----

* `Linux 7.2-rc1固定提交：Maple Tree、文本修补、ftrace和早期追踪的调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1034-L1047>`_；
* `Linux 7.2-rc1固定提交：maple_node缓存参数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/maple_tree.c#L5630-L5640>`_；
* `Linux 7.2-rc1固定提交：x86文本修补地址空间和PTE预分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c#L815-L853>`_；
* `Linux 7.2-rc1固定提交：临时映射、文本写入与TLB刷新 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/alternative.c#L2560-L2640>`_；
* `Linux 7.2-rc1固定提交：函数追踪位置筛选和ftrace_update_code <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/ftrace.c#L7566-L7750>`_；
* `Linux 7.2-rc1固定提交：ftrace_init成功与禁用路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/ftrace.c#L8365-L8407>`_；
* `Linux 7.2-rc1固定提交：早期追踪缓冲区和事件注册顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace.c#L9789-L9954>`_。
