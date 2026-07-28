第六十三章：Linux怎样接通早期控制台并准备页面集、NUMA策略和ACPICA？
========================================================================

第六十二章结束时，CPU0上的 ``start_kernel()`` 仍由 ``init_task`` 执行，IF位已经为1，但最终
x86中断模式和硬件时间初始化尚未开始。本章处理允许普通中断之后、调用
``late_time_init`` 之前的连续区间：

.. code-block:: c

   kmem_cache_init_late();
   console_init();
   if (panic_later)
       panic(...);
   lockdep_init();
   locking_selftest();
   /* 检查初始内存盘位置 */
   setup_per_cpu_pageset();
   numa_policy_init();
   acpi_early_init();

本章跟踪到 ``acpi_early_init()`` 返回。此时普通中断可以异步进入CPU0，因此各函数必须遵守已经
建立的锁和中断状态协议；执行这些入口本身仍不会创建PID 1或应用处理器。

``kmem_cache_init_late()`` 只补充SLUB的晚期对象
----------------------------------------------

Linux 7.2-rc1的通用对象分配器固定为SLUB。第六十章以前， ``kmem_cache_init()`` 已经建立
SLUB基础缓存、 ``kmalloc`` 缓存和逐CPU快速路径。本次 ``kmem_cache_init_late()`` 不会重新
创建这些对象，它只申请：

.. code-block:: c

   alloc_workqueue("slub_flushwq",
                   WQ_MEM_RECLAIM | WQ_PERCPU, 0);

``slub_flushwq`` 用于后续跨CPU清理SLUB状态。申请失败时源码只触发 ``WARN_ON()``，因此正常
控制流可以继续而该指针仍为空。启用 ``CONFIG_SLAB_FREELIST_RANDOM`` 时，函数还调用
``prandom_init_once()`` 初始化晚期伪随机状态；未启用时没有这一步。

系统工作队列尚未拥有普通工作线程，但早期工作队列设施已经允许创建工作队列。此处也没有登记
SLUB的 ``sysfs`` 文件，不能从函数名推断 ``/sys/kernel/slab`` 已经出现。

``console_init()`` 先建立行规程再运行控制台入口
-----------------------------------------------

``console_init()`` 首先调用 ``n_tty_init()`` 建立默认TTY行规程，然后遍历
``__con_initcall_start`` 到 ``__con_initcall_end``，依次执行当前构建链接进内核的控制台初始
化函数。每次调用都进入初始化追踪，返回值被记录后继续遍历，不由这一层统一中止。

固定GRUB命令行含有 ``console=ttyS0``，表示首选第一个串口终端。实际能否在此登记相应控制台，
仍取决于内核配置、平台入口和控制台初始化函数结果。因此本章能够确认默认行规程和控制台入口
区间已经执行，不能无条件确认某个8250实例已经接管输出。

控制台登记只把 ``printk`` 记录连接到可用终端。它不会创建用户态 ``/dev/console`` 文件描述
符，不会启动 ``getty``，也不表示PCI、DRM或完整TTY设备枚举已经完成。

``panic_later`` 在能够输出以后决定是否停止
-----------------------------------------

命令行解析过程中，如果内核参数或环境变量超过预留数量，解析代码会保存 ``panic_later`` 和
``panic_param``，延后到控制台入口执行后再触发 ``panic()``。这使错误信息有机会经过刚登记的
控制台输出。

固定GRUB命令行本身很短，但是内建命令行和启动配置内容没有固定，所以不能删除这个失败分支。
只有 ``panic_later`` 为空时，本章才继续进入锁检查和内存状态准备；如果它非空，启动在此结束，
不会到达本章结束状态。

``lockdep_init()`` 不在这里重新创建依赖图
----------------------------------------

未启用 ``CONFIG_LOCKDEP`` 时， ``lockdep_init()`` 是空宏。启用时，锁类别表、依赖边表、哈希表
和链表等主要存储本来就是静态对象；当前函数打印各表容量、已占内存和
``task_struct.held_locks`` 占用，不会遍历现有锁重新构造一张依赖图。

真正的依赖关系仍在以后每次加锁和解锁时逐步记录。把这一入口称为锁依赖检查的当前启动点可以
说明调用顺序，但不能声称此前锁操作没有使用任何锁调试状态。

锁接口自检是独立的构建分支
--------------------------

``locking_selftest()`` 只有启用 ``CONFIG_DEBUG_LOCKING_API_SELFTESTS`` 时才有函数体，否则为空
宏。启用后，如果 ``debug_locks`` 已经因更早错误关闭，函数只输出禁用信息并返回；否则它把
当前 ``init_task`` 设为自检任务，构造递归、解锁错误、锁顺序环以及硬中断和软中断状态组合，
并比较每种场景的预期结果。

源码要求这组测试在IF位已经打开后运行，因为其中包含中断开启与关闭状态的反转检查。测试会在
局部范围切换中断状态并恢复，不会登记设备IRQ处理动作；如果测试发现异常，锁调试状态可以被
关闭，而 ``start_kernel()`` 仍继续后续入口。

初始内存盘检查只决定是否保留地址
------------------------------

启用 ``CONFIG_BLK_DEV_INITRD`` 时，源码检查三个条件： ``initrd_start`` 非零、
``initrd_below_start_ok`` 为假，并且起始页帧低于 ``min_low_pfn``。三者同时成立说明初始内存盘
落在可能已被覆盖的低端范围，内核打印严重错误并把 ``initrd_start`` 清零，阻止后续把该区域
当作归档。

运行期装载地址没有固定，所以正文同时保留“地址继续有效”和“起始地址被清零”两条路径。这里
不读取归档内容，不解压 ``cpio``，也不创建 ``/init``。

``setup_per_cpu_pageset()`` 替换启动期页面集
-------------------------------------------

在此之前，每个内存区暂时指向静态 ``boot_pageset`` 和 ``boot_zonestats``。正常返回的
``setup_per_cpu_pageset()`` 对每个已填充内存区执行以下步骤：

#. 申请正式的逐CPU ``per_cpu_pages``，并在结构非空时申请逐CPU
   ``per_cpu_zonestat``；
#. 遍历 ``cpu_possible_mask``，初始化每个CPU的本地页链表、自旋锁和统计字段；
#. 根据内存区大小计算页面集的高水位和批量阈值；
#. 为每个在线内存节点申请逐CPU ``per_cpu_nodestat``。

未填充内存区继续使用启动期页面集；启用NUMA时，函数还清理启动期逐CPU NUMA事件统计，避免这些
共享统计污染其他节点。逐CPU页面集缓存的是仍属于原内存区和节点的空闲页，不会改变页面归属，
也不会在这里迁移已分配页面。

``numa_policy_init()`` 可以改变当前启动任务的分配策略
-----------------------------------------------------

未启用 ``CONFIG_NUMA`` 时， ``numa_policy_init()`` 是空函数。启用时，它以
``SLAB_PANIC`` 创建 ``mempolicy`` 和 ``sp_node`` 缓存，并为每个节点建立带固定引用的
``MPOL_PREFERRED`` 对象。

函数随后选择容量至少16 MiB的所有内存节点作为交错集合；如果没有节点达到阈值，就只选择容量
最大的节点。 ``do_set_mempolicy(MPOL_INTERLEAVE, ...)`` 把当前 ``init_task`` 的策略临时改为
在该集合内交错分配。设置失败会记录错误并继续，不会迁移已经存在的内核页面。这个临时策略要
到以后 ``rest_init()`` 创建PID 1之后才恢复默认，不能写成只准备对象而不改变当前任务状态。

``acpi_early_init()`` 保留禁用、失败和成功路径
---------------------------------------------

未启用 ``CONFIG_ACPI`` 时， ``acpi_early_init()`` 是空函数；即使已经构建ACPI支持，
``acpi_disabled`` 为真时也会直接返回。只有ACPI仍启用时，函数才继续：

#. 允许兼容模式并把 ``acpi_permanent_mmap`` 置为真；
#. 在x86上应用DSDT相关DMI兼容处理；
#. 调用 ``acpi_reallocate_root_table()`` 把根表转入正式分配；
#. 调用 ``acpi_initialize_subsystem()`` 初始化ACPICA核心、互斥对象和名字空间根等基础；
#. 根据当前采用PIC还是IOAPIC，修正SCI触发方式或覆盖后的GSI。

根表重新分配或ACPICA初始化失败时，函数调用 ``disable_acpi()`` 后返回。正常返回也只表示早期
ACPICA基础可用；事件处理和ACPI全局锁尚未初始化，表装载、完整名字空间对象初始化、普通AML方法
执行以及设备扫描仍在后续 ``acpi_bus_init()`` 等入口。

硬件时间初始化仍停在下一条语句
------------------------------

第六十一章已经把 ``late_time_init`` 指向 ``x86_late_time_init``，但本章只为它提供更完整的
控制台、页面分配和可选ACPI状态。无论ACPI正常、禁用还是因错误关闭，
``start_kernel()`` 都要到下一条条件调用才会选择最终中断模式并尝试建立HPET或PIT路径。

因此CPU0的IF位虽然为1，仍不能把本章发生的异步中断等同于周期时钟滴答，也不能提前断言TSC已
成为通用时钟源。

本章结束状态
------------

在没有触发 ``panic_later`` 的连续路径上，SLUB已经尝试创建每CPU清理工作队列，可选空闲链表
随机状态已经初始化；默认TTY行规程和控制台初始化函数区间已经执行。锁依赖报告和锁接口自检
已经按构建与当前调试状态处理。初始内存盘地址根据低端检查结果保留或清零；已填充内存区已经
取得覆盖所有可能CPU的正式页面集。启用NUMA且设置成功时，当前 ``init_task`` 暂时采用交错
分配策略。ACPI可能保持禁用、因初始化失败被关闭，或正常建立早期ACPICA基础。CPU0仍处于
CPL0且IF位为1，最终x86硬件时间入口、应用处理器、PID 1、PID 2和初始内存盘解包均尚未执行。

关键边界
--------

* ``kmem_cache_init_late()`` 只申请SLUB清理工作队列并处理可选随机状态；申请失败只警告，不会
  重新建立分配器。
* ``console_init()`` 已运行不保证 ``ttyS0`` 控制台一定登记成功，也不表示用户态终端已经存在。
* ``panic_later`` 非空时启动在控制台之后立即停止；本章其余状态只属于继续执行的路径。
* ``lockdep_init()`` 在启用时报告静态容量，不是依赖图第一次存在的时点；锁接口自检是另一
  配置分支。
* 初始内存盘位置检查可能清零 ``initrd_start``，但无论结果如何都没有解包归档。
* 正式逐CPU页面集不改变页面所属内存区；NUMA初始化则可能改变当前 ``init_task`` 的后续分配
  策略。
* ``acpi_early_init()`` 正常返回仍不允许普通AML执行；失败会关闭ACPI而不是阻塞
  ``start_kernel()`` 继续。

下一入口
--------

``start_kernel()`` 接下来执行：

.. code-block:: c

   if (late_time_init)
       late_time_init();

当前x86路径的函数指针是 ``x86_late_time_init()``。第六十四章将从该条件调用开始，重新核验
最终中断模式、HPET或PIT、TSC、调度时钟和延时校准；第六十四章在其自身审查前仍为待审状态。

资料
----

* `Linux 7.2-rc1 init/main.c：SLUB晚期入口到早期ACPI的调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1105-L1139>`_
* `Linux 7.2-rc1 mm/slub.c：清理工作队列和可选随机状态 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slub.c#L8619-L8627>`_
* `Linux 7.2-rc1 kernel/printk/printk.c：默认行规程和控制台初始化函数区间 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c#L4378-L4411>`_
* `Linux 7.2-rc1 kernel/locking/lockdep.c：锁依赖容量报告 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/locking/lockdep.c#L6632-L6669>`_
* `Linux 7.2-rc1 include/linux/lockdep.h：未启用锁依赖检查时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/lockdep.h#L318-L343>`_
* `Linux 7.2-rc1 lib/locking-selftest.c：锁接口与中断状态自检 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/locking-selftest.c#L2828-L2945>`_
* `Linux 7.2-rc1 mm/page_alloc.c：正式逐CPU页面集和节点统计 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/page_alloc.c#L6170-L6260>`_
* `Linux 7.2-rc1 mm/mempolicy.c：当前任务的启动期交错策略 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mempolicy.c#L3335-L3386>`_
* `Linux 7.2-rc1 include/linux/mempolicy.h：关闭NUMA配置时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/mempolicy.h#L210-L244>`_
* `Linux 7.2-rc1 drivers/acpi/bus.c：早期ACPICA初始化、SCI分支和失败关闭 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/bus.c#L1361-L1431>`_
* `Linux 7.2-rc1 drivers/acpi/acpica/utxfinit.c：ACPICA全局对象、互斥对象和名字空间根 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/acpica/utxfinit.c#L38-L96>`_
* `Linux 7.2-rc1 include/linux/acpi.h：关闭ACPI配置时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/acpi.h#L910-L923>`_
