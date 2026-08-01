第六十九章：Linux 怎样启动应用处理器、工作队列与 SMP 调度器？
=================================================================

第六十八章完成了初始化主线的任务交接。PID 0已经进入CPU0永久空闲循环；PID 2及全局
``kthreadd_task`` 已经发布；PID 1在 ``kernel_init()`` 中越过 ``kthreadd_done``，接着调用：

.. code-block:: c

   kernel_init_freeable();

PID 1此时仍在内核态，没有装入 ``/init`` 或 ``/sbin/init``。它暂时带有
``PF_NO_SETAFFINITY``，允许CPU集合只有CPU0。本章跟踪 ``kernel_init_freeable()`` 从开放
后续分配条件，到 ``page_alloc_init_late()`` 返回；下一条尚未执行的语句是
``do_basic_setup()``。

PID 1先解除启动期内存分配限制
-----------------------------

内核早期把 ``gfp_allowed_mask`` 设为 ``GFP_BOOT_MASK``，屏蔽回收、I/O和文件系统相关分配
标志。调度器已经能够阻塞当前任务，PID 2也已经发布后，PID 1执行：

.. code-block:: c

   gfp_allowed_mask = __GFP_BITS_MASK;

此后分配请求可以保留完整的GFP标志，具体分配路径也可以按自身条件进入回收、I/O或文件系统。
这项赋值只解除全局掩码，不保证任何一次分配成功，也不表示块设备、最终根文件系统或交换空间
已经可用。

启用 ``CONFIG_CPUSETS`` 时，紧接着的 ``set_mems_allowed(node_states[N_MEMORY])`` 在任务锁和
本地中断保护下，把PID 1的 ``mems_allowed`` 设为所有具有内存的节点，并用序列计数发布变化。
禁用CPU集合控制器时，同名内联入口为空。它改变的是后续分配范围，不迁移此前已经分配的页面。

最后， ``cad_pid = get_pid(task_pid(current))`` 为当前PID 1的 ``struct pid`` 增加引用，使
Ctrl-Alt-Del处理路径以后可以向初始任务发送信号。这个引用不会创建新任务。

``smp_prepare_cpus()`` 只准备应用处理器启动条件
-----------------------------------------------

启用 ``CONFIG_SMP`` 时，固定x86路径通过 ``smp_ops.smp_prepare_cpus`` 进入
``native_smp_prepare_cpus()``。通用准备部分先把除CPU0以外的可能CPU标成尚未完成索引连接，
为每个可能CPU分配兄弟、核心、晶粒和共享缓存拓扑掩码，再建立CPU0自己的兄弟关系。

随后，x86按此前确定的 ``apic_intr_mode`` 分支：

* 使用传统PIC或没有配置的虚拟线模式时， ``disable_smp()`` 关闭SMP路径；
* 对称I/O但没有路由时，同样关闭SMP，只补上CPU0本地时钟事件；
* 虚拟线或完整对称I/O模式继续准备SMP，设置CPU0逐CPU时钟事件，输出CPU0信息，处理平台钩子、
  启动延时、共享线程推测执行缓解和可选SNP唤醒方法。

本入口没有调用应用处理器跳板，也没有把任何应用处理器标成在线。平台或虚拟化实现还可以替换
``smp_ops``， ``setup_max_cpus`` 也会在真正启动阶段限制目标数量。因此，此处只能得到“启动
条件已经准备或SMP已经按检测关闭”，不能提前写出在线CPU数。

``workqueue_init()`` 为既有工作池建立首批执行者
-----------------------------------------------

工作队列核心在更早的 ``workqueue_init_early()`` 中已经建立系统工作队列和工作池，但当时还
没有普通 ``kworker`` 执行排队工作。现在 ``workqueue_init()`` 进入三阶段初始化的第二阶段。

函数首先调用 ``wq_cpu_intensive_thresh_init()``。它通过 ``kthread_run_worker()`` 创建
``pool_workqueue_release`` 专用线程，失败由 ``BUG_ON()`` 停止当前路径；若启动参数没有指定
阈值，还根据 ``loops_per_jiffy`` 估算处理器速度，把CPU密集工作阈值限制在10毫秒到1秒之间。
这也是PID 1开始实际依赖PID 2处理内核线程创建请求的地方。

持有 ``wq_pool_mutex`` 时，函数为此前建立的逐CPU池补上NUMA节点信息，并尝试为请求
``WQ_MEM_RECLAIM`` 的工作队列创建早期救援线程。救援线程创建失败只打印警告，不与关键工作
线程使用相同的失败语义。

随后，内核为所有可能CPU的底半部池创建伪工作执行者，为当时每个在线CPU的逐CPU池创建首批
真正工作线程，并为所有无绑定池创建工作线程。此刻应用处理器尚未由 ``smp_init()`` 启动，
所以逐在线CPU循环至少覆盖CPU0，不能预先写成覆盖所有可能CPU。关键工作线程创建失败由
``BUG_ON()`` 处理；全部完成后， ``wq_online`` 置为真，工作队列看门狗也随之初始化。

``init_mm_internals()`` 接通运行期内存统计
------------------------------------------

``init_mm_internals()`` 分配带有 ``WQ_MEM_RECLAIM | WQ_PERCPU`` 标志的
``mm_percpu_wq``。启用SMP时，它分别登记VM统计的CPU离线和上线热插拔状态；登记失败只记录
错误，函数仍继续初始化节点状态并启动 ``vmstat`` 汇总定时器。源码没有在本函数内检查
``mm_percpu_wq`` 的分配结果，也没有提供本地恢复分支。

启用 ``CONFIG_PROC_FS`` 时，该入口创建 ``buddyinfo``、 ``pagetypeinfo``、 ``vmstat`` 和
``zoneinfo`` 顺序文件入口，并登记 ``vm`` 系统控制表。第六十六章已经登记 ``procfs`` 类型，但它
仍未成为当前根下的挂载；这里建立目录项不等于用户空间现在已经能从最终根读取它们。

SMP之前只执行专门的早期初始化调用
---------------------------------

``do_pre_smp_initcalls()`` 把跟踪级别标记为 ``early``，然后遍历链接器
``__initcall_start`` 到 ``__initcall0_start`` 之间的条目。链接脚本把
``.initcallearly.init`` 放在这个区间，纯初始化调用级别0从 ``__initcall0_start`` 才开始。
因此，本入口执行的是以 ``early_initcall()`` 登记、明确要求在SMP启动前完成的函数，而不是
后面0到7级的完整初始化调用序列。

具体条目取决于构建配置。固定源码可在这里启动RCU宽限期线程、软中断线程、CPU迁移线程、
``kthread`` 后续设施或其他内建早期服务，但不能在最终 ``.config`` 未固定时声称每个候选入口
都存在。每个条目都通过 ``do_one_initcall()`` 执行并接受其调试、黑名单和返回值检查。

锁死检测器保留配置、维护CPU集合与探测结果
-----------------------------------------

启用 ``CONFIG_LOCKUP_DETECTOR`` 时， ``lockup_detector_init()`` 先根据
``HK_TYPE_TIMER`` 维护CPU集合生成 ``watchdog_cpumask``；使用 ``nohz_full`` 的CPU默认
不在其中。硬锁死探测成功会发布可用状态，失败则允许稍后重试，最后
``lockup_detector_setup()`` 按当前开关建立检测状态。

这个入口不保证所有CPU都已经有看门狗线程，也不能从函数返回推导硬锁死探测一定可用。禁用
对应构建选项时，入口为空。

``smp_init()`` 才真正尝试唤醒应用处理器
---------------------------------------

启用SMP时， ``smp_init()`` 先调用 ``idle_threads_init()`` 和
``cpuhp_threads_init()``，为非启动CPU准备空闲任务与CPU热插拔线程。随后，
``bringup_nonboot_cpus(setup_max_cpus)`` 才把目标CPU沿热插拔状态机向在线状态推进。
``setup_max_cpus`` 为0时，该函数直接结束。

若构建和体系结构都支持并行启动，热插拔核心可以先向一组CPU推进启动请求，再逐个完成后半段
上线；x86在SMT场景下先处理主线程，避免同一核心的兄弟线程在微码更新期间同时推进。未启用
并行路径时，内核按CPU串行推进 ``cpu_present_mask``。两种方式都受目标数量和逐CPU状态转换
结果限制。

x86的实际唤醒路径先验证CPU对应的APIC ID和物理存在位，保存MTRR状态，清除该CPU的FPU所有者，
再准备空闲任务与逐CPU基础。 ``do_boot_cpu()`` 把目标空闲任务栈和 ``start_secondary`` 入口
写入启动状态，然后优先选择平台提供的64位唤醒方法，其次选择普通APIC方法，最后才使用INIT
启动序列。唤醒失败会清理相关状态并把错误交回热插拔路径，因此“被枚举为可能CPU”不等于
“本章必然在线”。

应用处理器从跳板进入 ``start_secondary()``
-------------------------------------------

成功响应唤醒的应用处理器从低级跳板进入 ``start_secondary()``。每个处理器先设置CR4和异常
处理基础，在与控制CPU的存活同步点之前加载应用处理器微码；并行启动时，控制CPU会在该同步点
逐步放行后续上线过程。

被放行后，应用处理器依次建立本地CPU状态和FPU，向RCU报告启动，初始化逐CPU早期时钟，完成
``ap_starting()``，再与控制CPU检查TSC同步并校准延时循环。只有取得 ``vector_lock`` 后，它
才同时发布CPU在线状态并启用本地APIC向量空间，避免其他CPU看到半完成的中断向量状态。

应用处理器随后初始化NMI，打开本地中断，设置自己的逐CPU时钟事件，最后进入
``cpu_startup_entry(CPUHP_AP_ONLINE_IDLE)``。它从此以对应空闲任务等待调度，不会回到PID 1的
调用栈。

所有目标处理完后， ``smp_init()`` 打印实际在线节点和CPU数量，再调用x86的
``native_smp_cpus_done()`` 建立体系结构调度拓扑描述，执行NMI自检和缓存应用处理器收尾。
固定QEMU参数没有限定vCPU数量、CPU模型、加速器或 ``maxcpus``，所以本章只能以运行后
``cpu_online_mask`` 为事实，不能给出固定数量。

``sched_init_smp()`` 按实际活动CPU建立调度域
--------------------------------------------

应用处理器启动尝试完成后，PID 1调用 ``sched_init_smp()``。函数先初始化NUMA调度信息和随机
状态，再持有 ``sched_domains_mutex``，按当前 ``cpu_active_mask`` 建立调度域。失败上线的
CPU不在活动集合中，也不会被正文虚构进调度拓扑。

接着，函数把当前PID 1的允许CPU集合设为 ``HK_TYPE_DOMAIN`` 维护CPU集合。若CPU0属于
隔离集合，设置亲和性可能把PID 1迁移到其他非隔离在线CPU；若CPU0仍被允许，PID 1可以继续在
原CPU运行。成功后才清除 ``PF_NO_SETAFFINITY``，解除第六十八章设置的临时禁止改亲和性状态。
设置失败由 ``BUG()`` 处理，不存在继续使用旧范围的普通分支。

最后，函数完成调度粒度、实时调度类、截止期限调度类及其服务器初始化，并把
``sched_smp_initialized`` 置为真。这个标志说明SMP调度器已经按实际活动CPU完成当前阶段，
不表示PID 1必定迁移过，也不表示所有可能CPU均在线。

工作队列、异步执行和并行数据路径消费最终拓扑
--------------------------------------------

``workqueue_init_topology()`` 是工作队列三阶段初始化的最后一步。它分别按CPU、SMT、共享缓存、
缓存分片和NUMA关系建立无绑定工作队列分组，然后把 ``wq_topo_initialized`` 置为真。持有
``wq_pool_mutex`` 时，函数遍历已有工作队列，为每个实际在线CPU重新连接无绑定池，并更新无
绑定工作队列的逐节点活跃上限。

``async_init()`` 随后创建专用无绑定工作队列 ``async``。异步初始化任务可能互相依赖，普通
无绑定工作队列的最小活跃数可能造成停滞，所以函数把该队列的最小活跃数提高到
``WQ_DFL_ACTIVE``；分配失败由 ``BUG_ON()`` 停止当前路径。

``padata_init()`` 按 ``CONFIG_HOTPLUG_CPU`` 登记应用处理器在线多实例状态，然后依据
``num_possible_cpus()`` 分配 ``padata_work`` 数组，把每个对象加入空闲工作链表。热插拔状态
登记或数组分配失败时，函数撤销已经登记的状态并打印警告，启动链仍可继续；因此本章出口不能
无条件宣称并行数据转换设施可用。

``page_alloc_init_late()`` 收束延后页元数据与 ``memblock``
----------------------------------------------------------

启用 ``CONFIG_DEFERRED_STRUCT_PAGE_INIT`` 时， ``page_alloc_init_late()`` 为每个具有内存的
节点启动 ``pgdatinit`` 线程，并等待所有线程完成延后的 ``struct page`` 初始化。等待结束后，
它关闭按需页元数据初始化静态分支，并按最终空闲页数重新计算系统文件数限制。这里没有检查
各次 ``kthread_run()`` 的返回值；持续路径依赖每个节点线程都能启动并递减完成计数，否则全局
完成量等待不能正常结束。

无论是否启用延后初始化，函数都会在总内存和空闲内存记账稳定后打印内存信息，调用
``buffer_init()``，丢弃 ``memblock`` 的私有元数据，并逐内存节点随机化空闲内存顺序。随后，
它为每个已填充 ``zone`` 计算并发布连续性标志；若早期确实延后了页元数据，还在所有
``struct page`` 可用后执行 ``page_ext_init()``。最后， ``page_alloc_sysctl_init()`` 按
系统控制构建配置登记页分配器控制项。

这不是“内存管理从此不再变化”。页面回收、NUMA、内存热插拔和各子系统缓存仍会继续工作。
本入口只完成依赖线程、最终内存规模和全部页元数据的晚期收尾。

本章结束状态
------------

::

   当前执行者          = PID 1；page_alloc_init_late()已返回
   下一入口            = do_basic_setup()
   CPU模式             = x86-64长模式，CPL0
   system_state        = SYSTEM_SCHEDULING
   PID 0               = CPU0空闲任务
   PID 1               = kernel_init；允许在非隔离housekeeping CPU运行
   PID 2               = kthreadd；已能处理内核线程创建请求
   CPU在线集合         = 按SMP配置、APIC模式、setup_max_cpus与逐CPU启动结果确定
   应用处理器          = 按SMP构建与目标限额尝试上线；成功者进入各自空闲循环
   SMP调度器           = 按实际cpu_active_mask建立并发布
   工作队列            = 首批执行者在线，无绑定池已按最终拓扑重新连接
   内存统计            = 逐CPU工作队列、热插拔状态和汇总定时器按配置建立
   早期初始化调用      = early_initcall链接区间已经执行
   锁死检测            = 按配置、housekeeping集合和探测结果设置
   async               = 专用无绑定工作队列已经建立
   padata              = 已建立，或在登记/分配失败后警告并撤销
   延后页元数据        = 启用时已经全部初始化并关闭按需分支
   memblock私有元数据  = 已丢弃
   最终磁盘根          = 尚未挂载
   初始内存盘          = 尚未解包
   用户空间init       = 尚未装入

关键边界
--------

* ``smp_prepare_cpus()`` 只建立拓扑掩码和体系结构启动条件，真正唤醒发生在
  ``smp_init()``；
* ``workqueue_init()`` 为更早建立的池创建首批执行者，不是从零创建全部工作队列；
* ``do_pre_smp_initcalls()`` 只执行 ``early_initcall()`` 链接区间，不执行0到7级完整初始化
  调用；
* 应用处理器是否在线受构建、APIC模式、 ``setup_max_cpus``、平台唤醒方法和逐CPU错误控制；
* ``sched_init_smp()`` 按实际活动CPU建立调度域，并解除PID 1的临时亲和限制，但不保证发生
  迁移；
* ``padata_init()`` 失败只警告并撤销， ``async_init()`` 和关键工作线程失败则停止当前路径；
* 延后页元数据初始化依赖每个节点的 ``kthread_run()`` 成功，源码没有检查各次返回值；
* ``page_alloc_init_late()`` 完成页元数据和 ``memblock`` 晚期收尾，不挂载最终根，也不解包
  初始内存盘。

下一入口
--------

下一章从PID 1调用 ``do_basic_setup()`` 开始。该函数先执行 ``cpuset_init_smp()``，随后建立
内核对象文件系统入口和设备模型，初始化中断的 ``procfs`` 入口，运行构造函数，并进入0到7级完整
初始化调用序列。

资料
----

* `kernel_init_freeable()的本章调用区间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1629-L1658>`_
* `启动期GFP掩码的含义
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/gfp.h#L408-L414>`_
* `set_mems_allowed()发布PID 1的内存节点范围
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/cpuset.h#L166-L178>`_
* `x86准备应用处理器
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c#L1175-L1255>`_
* `workqueue_init()建立首批执行者
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c#L8118-L8178>`_
* `工作队列CPU密集阈值与释放线程
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c#L8079-L8116>`_
* `init_mm_internals()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/vmstat.c#L2266-L2300>`_
* `SMP前的早期初始化调用区间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1448-L1455>`_
* `链接脚本区分early与0级初始化调用
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/asm-generic/vmlinux.lds.h#L938-L955>`_
* `lockup_detector_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/watchdog.c#L1386-L1400>`_
* `smp_init()和实际在线结果
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smp.c#L1004-L1023>`_
* `并行或串行推进应用处理器
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c#L1821-L1881>`_
* `x86选择应用处理器唤醒方法
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c#L1018-L1120>`_
* `应用处理器进入start_secondary()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c#L229-L313>`_
* `sched_init_smp()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8860-L8887>`_
* `workqueue_init_topology()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c#L8418-L8457>`_
* `async_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/async.c#L350-L362>`_
* `padata_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/padata.c#L1089-L1118>`_
* `page_alloc_init_late()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c#L2300-L2345>`_
