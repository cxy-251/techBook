第六十五章：Linux怎样建立PID与任务创建对象？
===========================================

第六十四章结束时，CPU0已经完成时间和体系结构收尾，但当前执行者仍是静态创建的
``init_task``，其PID为0。内核还没有可供新任务使用的PID分配器、 ``task_struct`` 缓存和
成组进程资源缓存。本章从 ``pid_idr_init()`` 开始，依次经过匿名映射、线程栈、凭据和任务
创建基础，到 ``proc_caches_init()`` 返回，并停在 ``uts_ns_init()`` 之前。

PID 0为何不需要本章现建
----------------------

启动任务使用编译期对象 ``init_struct_pid``。该对象的引用计数初值为1，层级为0，
``numbers[0].nr`` 为0，并指向 ``init_pid_ns``；初始PID名字空间本身也已经静态存在，其
``child_reaper`` 指向 ``init_task``。所以CPU0能够以PID 0运行到这里，并不依赖动态PID分配。

本章建立的是以后创建任务所需的动态路径。 ``pid_idr_init()`` 不会为 ``init_task`` 再分配
一次PID，也不会在执行期间生成PID 1。

初始PID名字空间怎样取得分配器
----------------------------

``pid_idr_init()`` 先以编译期断言保证 ``PID_MAX_LIMIT`` 不会与
``PIDNS_ADDING`` 状态位重叠。随后它按照 ``num_possible_cpus()`` 调整
``init_pid_ns.pid_max`` 和系统允许的最小 ``pid_max``：默认上限至少达到每个可能CPU对应的
建议值，但不会超过 ``pid_max_max``；最小值也随可能CPU数量增长。

函数接着重新初始化 ``init_pid_ns.idr``，并创建名为 ``pid`` 的SLUB缓存。对象大小使用
``struct_size_t(struct pid, numbers, 1)``，正好覆盖初始PID名字空间层级0所需的一项
``upid``； ``SLAB_PANIC`` 表示缓存创建失败会停止启动，而不是把错误交给后续调用者。

此处没有登记 ``pid_max`` 的 ``sysctl``。 ``pid_namespace_sysctl_init()`` 属于稍后的
``subsys_initcall`` 阶段；本章只准备分配器和对象缓存。

为什么下一次自动分配会从1开始
----------------------------

``init_pid_ns`` 的静态状态包含 ``pid_allocated=PIDNS_ADDING``。以后
``alloc_pid()`` 首次为该名字空间分配PID时，会在 ``pidmap_lock`` 下把IDR游标设为0；没有
指定PID时，分配下限先取1，只有游标已经越过 ``RESERVED_PIDS`` 后，循环分配的下限才改为
``RESERVED_PIDS``。

这段代码为将来的第一个动态任务保留PID 1语义，但它在本章尚未执行。真正的
``alloc_pid()`` 要等任务复制路径被调用；当前IDR中没有因为 ``pid_idr_init()`` 而出现PID 1
对象。

匿名映射对象先准备两类缓存
--------------------------

``anon_vma_init()`` 创建 ``anon_vma`` 与 ``anon_vma_chain`` 两个缓存。前者带有构造函数
``anon_vma_ctor()``，每次构造时初始化 ``rwsem``、把引用计数设为0，并建立空的缓存红黑树；
后者保存匿名VMA与映射关系之间的链节点。

这一步只使匿名反向映射对象能够按需分配。它没有创建用户VMA、页表或匿名页，也没有给
``init_task`` 建立用户地址空间。第055章已经建立的通用内存分配基础为这些SLUB缓存提供对象
内存，本章在其上增加用途明确的对象类型。

线程栈入口在当前x86-64路径为空
-----------------------------

``start_kernel()`` 无条件写出 ``thread_stack_cache_init()``，但定义取决于
``THREAD_SIZE``。当 ``THREAD_SIZE`` 不小于 ``PAGE_SIZE`` 时， ``init/main.c`` 提供一个弱
空实现；只有线程栈小于一页且未使用 ``CONFIG_VMAP_STACK`` 的构建， ``kernel/fork.c`` 才以
同名强定义创建 ``thread_stack`` 用户复制缓存。

当前主线沿x86-64路径， ``THREAD_SIZE`` 不小于页大小，因此这里执行空入口。若启用了
``CONFIG_VMAP_STACK``，虚拟映射栈的逐CPU回收机制不是在该空入口建立，而是在后面的
``fork_init()`` 登记CPU热插拔状态。旧正文若把本行写成必然创建线程栈缓存，就把另一种构建
条件误写进了当前执行路径。

凭据缓存只准备新对象存放位置
----------------------------

``cred_init()`` 以 ``KMEM_CACHE(cred, ...)`` 创建 ``cred_jar``，并使用
``SLAB_HWCACHE_ALIGN``、 ``SLAB_PANIC`` 和 ``SLAB_ACCOUNT``。以后复制任务或内核服务准备
凭据时，才会从这个缓存取得 ``struct cred``。

当前 ``init_task`` 的凭据仍来自静态初始对象，函数不会替换 ``current->cred``，也不会改变
UID、GID、能力集合或安全标记。安全模块附加在当前凭据上的私有数据，要等第066章
``security_init()`` 根据启用的LSM分配。

fork_init怎样准备task_struct
----------------------------

``fork_init()`` 先让 ``task_struct_whitelist()`` 取得体系结构允许用户复制的
``thread_struct`` 区间，再按L1缓存行和体系结构最小对齐要求创建 ``task_struct`` 用户复制
缓存。缓存使用 ``SLAB_PANIC|SLAB_ACCOUNT``；创建失败不会留下一个可继续但无法复制任务的
内核。

随后调用弱定义的 ``arch_task_cache_init()``，让需要额外任务缓存的体系结构覆盖；固定x86
没有在此提供强定义，因此采用空实现。至此只是可以分配 ``task_struct``，尚未执行
``dup_task_struct()``，也没有为任何新任务分配内核栈。

任务数量上限来自可用内存估计
----------------------------

``set_max_threads(MAX_THREADS)`` 读取 ``memblock_estimated_nr_free_pages()``，按“线程栈结构
最多消耗估计可用内存的八分之一”计算建议数量，再限制到传入上限和
``MIN_THREADS``、 ``MAX_THREADS`` 之间。由此得到的 ``max_threads`` 取决于内存规模和构建
常量，不能从固定机器模型推导为某个数字。

``fork_init()`` 随后把 ``init_task.signal`` 中的 ``RLIMIT_NPROC`` 软硬限制都设为
``max_threads/2``，并让 ``RLIMIT_SIGPENDING`` 使用同一上限；初始用户名字空间的各类
``ucount_max`` 也先取 ``max_threads/2``。指定的用户名字空间资源限制上界再按源码设为
``RLIM_INFINITY``。这些是后续创建和计数对象的限制，不是已经存在的任务数量。

可选栈回收、影子调用栈和启动任务检查
------------------------------------

启用 ``CONFIG_VMAP_STACK`` 时，函数登记 ``CPUHP_BP_PREPARE_DYN`` 状态，使CPU离线准备阶段
能够释放其虚拟映射栈缓存。随后 ``scs_init()`` 按影子调用栈配置执行，再对现有
``init_task`` 调用 ``lockdep_init_task()``，最后执行 ``uprobes_init()``。

这些操作仍由CPU0同步完成。CPU热插拔状态登记不等于其他CPU已经上线，
``lockdep_init_task()`` 也不是创建新任务；它只把已经存在的启动任务接入相应检查状态。

proc_caches_init不是proc文件系统初始化
--------------------------------------

名称中的 ``proc`` 指进程创建基础，而不是 ``procfs``。 ``proc_caches_init()`` 依次创建：

* 带 ``sighand_ctor()`` 的 ``sighand_cache``，构造时初始化 ``siglock`` 和
  ``signalfd_wqh``；
* 保存 ``struct signal_struct`` 的 ``signal_cache``；
* 保存 ``struct files_struct`` 的 ``files_cache``；
* 保存 ``struct fs_struct`` 的 ``fs_cache``。

在信号缓存之后，函数还执行 ``exec_state_init()``；在文件和文件系统状态缓存之后，执行
``mmap_init()`` 和 ``nsproxy_cache_init()``。 ``mmap_init()`` 建立
``vm_committed_as`` 逐CPU计数器、可选的虚拟内存 ``sysctl`` 和VMA状态；后者创建
``nsproxy`` 缓存。

``mm_struct`` 缓存不在这里创建。它已由更早的内存初始化路径调用 ``mm_cache_init()`` 建立。
同样， ``proc_root_init()`` 还要到第066章后半段才建立 ``/proc`` 根结构并登记文件系统。

对象缓存就绪仍不等于任务已经存在
-------------------------------

截至本章结束，动态PID、匿名映射关系、凭据、 ``task_struct``、信号处理、共享信号、文件表、
文件系统上下文和名字空间代理都已经有了分配基础。但是没有代码调用 ``kernel_clone()``、
``copy_process()`` 或 ``alloc_pid()``；运行队列中仍只有启动阶段原有的CPU0空闲任务。

这种区分决定了连续性：本章准备“怎样创建”，第067章接近结尾的 ``rest_init()`` 才真正创建
PID 1和PID 2。

本章结束状态
------------

::

   当前执行者          = CPU0上的start_kernel()；proc_caches_init()已返回
   下一入口            = uts_ns_init()
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   初始PID名字空间     = IDR已初始化，动态pid缓存已经建立
   动态PID             = 尚未分配；PID 1尚不存在
   匿名映射对象        = anon_vma与anon_vma_chain缓存已经建立
   线程栈入口          = 当前x86-64路径为空；可选VMAP栈回收状态在fork_init()登记
   凭据                = cred缓存已经建立；init_task仍使用原有静态凭据
   任务对象            = task_struct缓存已经建立
   任务限制            = max_threads及初始任务和用户名字空间限制已经设置
   进程共享对象        = sighand、signal、files、fs与nsproxy缓存已经建立
   VMA基础             = vm_committed_as与VMA状态已经初始化
   proc文件系统        = 尚未初始化
   新任务              = 尚未创建
   任务切换            = 尚未发生
   PID1/PID2           = 尚未创建

关键边界
--------

* ``init_task`` 与PID 0使用静态对象； ``pid_idr_init()`` 建立的是后续动态分配能力；
* IDR首次自动分配从1开始，使PID 1可由后续首个动态任务取得，但本章没有执行分配；
* 当前x86-64的 ``thread_stack_cache_init()`` 是弱空实现，不能写成必然创建SLUB缓存；
* ``fork_init()`` 创建任务对象缓存并设置资源上限，不会自行调用任务复制路径；
* ``proc_caches_init()`` 准备进程共享对象，不是 ``procfs`` 根目录初始化，也不创建
  ``mm_struct`` 缓存。

下一入口
--------

``start_kernel()`` 下一条语句是 ``uts_ns_init()``。第066章将从已经存在的初始名字空间对象
出发，建立可选名字空间、密钥与安全框架，再初始化网络名字空间、VFS、页缓存等待队列、信号
队列和三个伪文件系统；第067章的 ``cpuset_init()`` 在这些基础之后才会开始。

资料
----

* `start_kernel()中的PID与任务对象调用区间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1143-L1152>`_
* `初始PID对象和初始PID名字空间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c#L49-L84>`_
* `alloc_pid()首次从PID 1开始的条件
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c#L159-L266>`_
* `pid_idr_init()的上限、IDR和对象缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c#L848-L867>`_
* `anon_vma_init()创建的两类缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/rmap.c#L543-L559>`_
* `线程栈缓存的条件实现
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L390-L468>`_
* `THREAD_SIZE不小于页大小时的弱空入口
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L759-L771>`_
* `cred_init()建立凭据缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cred.c#L533-L541>`_
* `fork_init()的任务缓存、上限和现有启动任务处理
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L808-L897>`_
* `proc_caches_init()建立的共享对象与后续入口
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L3089-L3137>`_
* `mmap_init()建立提交计数与VMA状态
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mmap.c#L1564-L1577>`_
* `nsproxy_cache_init()建立名字空间代理缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/nsproxy.c#L609-L613>`_
