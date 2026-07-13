第六十五章：Linux 怎样建立 PID 分配器与 fork 对象基础？
====================================================

第六十四章结束时，boot CPU 的 feature、FPU、alternative instructions、真实定时器和延时校准已经完成。当前仍由 ``init_task`` / ``swapper/0`` / PID 0 在 ``start_kernel()`` 中同步执行。

接下来的控制流是：

.. code-block:: c

   pid_idr_init();
   anon_vma_init();
   thread_stack_cache_init();
   cred_init();
   fork_init();
   proc_caches_init();

本章追踪到 ``proc_caches_init()`` 返回，停在 ``uts_ns_init()`` 之前。这一段建立“内核已经具备创建任务所需对象”的条件，不会直接调用 ``copy_process()``，也不会产生 PID 1。

PID 0 为什么早于 PID allocator 存在
--------------------------------

当前执行者早已显示为 PID 0，但 ``pid_idr_init()`` 现在才运行，两者并不冲突。

``init_task`` 和 ``init_struct_pid`` 是链接进内核映像的静态对象。``init_struct_pid`` 已经把数字 0、初始 PID namespace 和 ``init_task`` 的特殊启动身份固定下来。它不是通过普通动态 PID 分配路径产生的。

即将建立的 allocator 服务于后续新任务：

.. code-block:: text

   PID 1  kernel_init
   PID 2  kthreadd
   后续用户进程与内核线程

因此，``PID 0 已存在`` 与 ``动态 PID allocator 尚未初始化`` 是两个不同事实。

``pid_idr_init()`` 调整初始 PID 空间
----------------------------------

固定源码首先检查：

.. code-block:: c

   BUILD_BUG_ON(PID_MAX_LIMIT >= PIDNS_ADDING);

``pid_allocated`` 的高位还承载 ``PIDNS_ADDING`` 状态，PID 数值上限不能与该状态位重叠。这里使用构建期检查，错误配置不能生成内核映像。

随后根据 possible CPU 数量调整：

.. code-block:: text

   init_pid_ns.pid_max
   pid_max_min

CPU 越多，可并发存在的任务通常越多。内核使用 ``PIDS_PER_CPU_DEFAULT`` 与 ``PIDS_PER_CPU_MIN`` 给默认值和最小值提供随 CPU 数量增长的下限，同时仍受 ``PID_MAX_LIMIT`` 限制。

这一步依据的是 possible CPU，不是当前 online CPU。当前仍只有 CPU0 online，但固件和早期拓扑已经告诉 Linux 未来可能启动多少 AP，因此 PID 空间可以提前按完整机器规模准备。

初始化 IDR 不等于分配 PID
-----------------------

``pid_idr_init()`` 接着执行：

.. code-block:: c

   idr_init(&init_pid_ns.idr);

IDR（ID Radix Tree）提供整数 ID 到对象指针的映射和空闲 ID 分配能力。PID allocator 后续通过 ``idr_alloc_cyclic()`` 在 namespace 的 PID 范围中寻找数字，再把完整 ``struct pid`` 放进 IDR。

此刻 IDR 只是进入可用状态：

* 没有调用 ``alloc_pid()``；
* 没有占用数字 1；
* 没有把新 ``task_struct`` 加入 task list；
* 没有触发调度。

``struct pid`` 为什么需要专用 cache
----------------------------------

函数最后创建名为 ``pid`` 的 slab cache。对象大小按照初始 PID namespace 的一级 ``numbers[]`` 数组计算。

``struct pid`` 不是 ``task_struct`` 中一个普通整数。它负责把同一个数字身份连接到：

* PID/TID；
* thread-group ID；
* process-group ID；
* session ID；
* 不同层级 PID namespace 中的 ``upid``；
* pidfd 与等待队列；
* 查找该 ID 对应任务的 hlist。

普通初始 namespace 的对象只需要一级编号。嵌套 PID namespace 会创建尺寸更大的 cache，以容纳每一层 namespace 中的数字。

第一份动态 PID 为什么必须是 1
--------------------------

``alloc_pid()`` 中存在明确约束：若某个 PID namespace 尚未建立 ``child_reaper``，第一次成功分配的编号必须是 1。

后面的 ``rest_init()`` 会先创建 ``kernel_init``，它成为初始 PID namespace 的 PID 1 和 child reaper。只有这一步成功后，PID 2 及其他编号才允许正常出现。

当前 ``pid_idr_init()`` 只为这次分配准备 IDR 和 cache，没有执行第一次分配。

``anon_vma_init()`` 为匿名页建立反向关系对象
---------------------------------------

进程创建不仅需要 ``task_struct``，还要处理地址空间复制。父进程中的匿名内存通常通过 fork 建立 copy-on-write 关系：父子先共享物理页，任一方写入时再复制。

页回收、迁移、写保护和解除映射需要回答：

.. code-block:: text

   这个匿名 folio 被哪些 VMA 映射？
   应该到哪些进程页表中修改 PTE？

``anon_vma`` 提供匿名内存反向映射的共同根，``anon_vma_chain`` 把一个 VMA 连接到相关 ``anon_vma`` 层级。

``anon_vma_init()`` 为这两类高频对象建立专用 slab cache。它不会为 ``init_task`` 创建用户匿名地址空间，也不会发生 COW fault；它只是保证未来 ``anon_vma_prepare()`` 和 ``anon_vma_fork()`` 能分配连接对象。

反向映射和页表不是同一个结构
--------------------------

页表回答虚拟地址怎样找到物理页：

.. code-block:: text

   virtual address → PTE/PMD → physical folio

reverse mapping 回答相反方向：

.. code-block:: text

   physical folio → anon_vma/mapping → VMA → page table entries

fork、migration、memory reclaim 和 ``try_to_unmap()`` 都需要第二条路径。``anon_vma_init()`` 建立对象分配基础，不修改当前页表。

``thread_stack_cache_init()`` 是配置相关入口
-----------------------------------------

每个任务都需要内核栈，但具体分配方式取决于架构和配置：

* ``CONFIG_VMAP_STACK``：通过 vmalloc 虚拟区建立带 guard page 的栈，并使用 per-CPU cache 减少反复 ``vmap``/``vfree``；
* ``THREAD_SIZE >= PAGE_SIZE``：可以直接从 page allocator 分配整页或高阶页；
* 更小的独立 stack：使用 ``thread_stack`` slab cache。

固定 x86-64 内核通常启用 ``CONFIG_VMAP_STACK``，此时 ``thread_stack_cache_init()`` 可能落到通用空实现；真正的 vmapped-stack cache 已由 ``kernel/fork.c`` 中的 per-CPU ``cached_stacks`` 路径定义。

因此不能看到函数名就断言“这里创建了 thread_stack slab”。准确结论是：内核执行了架构/配置规定的线程栈 cache 初始化入口。

``cred_init()`` 建立 credential 对象 cache
---------------------------------------

Linux 把任务身份放在 ``struct cred`` 中，包括：

* real/effective/saved UID 与 GID；
* filesystem UID/GID；
* supplementary groups；
* capability sets；
* user namespace；
* keyring 引用；
* LSM security blob；
* ucounts。

``cred_init()`` 创建带硬件 cache 对齐、内存记账和 panic-on-failure 属性的 ``cred`` slab cache。

当前 ``init_task`` 已经引用静态 ``init_cred``。这里不会重新生成 PID 0 的身份，而是让后面的 ``prepare_creds()``、``copy_creds()`` 和 kernel service credential 创建能够分配动态对象。

credential 为什么采用复制后提交
-----------------------------

运行中的任务不会随意原地修改一份被多个读者共享的 credential。常见路径是：

.. code-block:: text

   prepare_creds()
   → copy old cred
   → modify private copy
   → security hooks validate
   → commit_creds()
   → RCU release old cred

专用 cache 和引用计数使这种不可变快照模型可行。``cred_init()`` 只是建立分配池，不执行用户身份切换。

``fork_init()`` 创建 ``task_struct`` cache
---------------------------------------

``fork_init()`` 的第一项主体工作是创建 ``task_struct`` slab cache。

对象按 L1 cache line 和架构最小对齐要求排列，并带：

* ``SLAB_PANIC``：启动期无法建立核心任务 cache 时直接停止；
* ``SLAB_ACCOUNT``：支持 kernel-memory cgroup accounting；
* usercopy whitelist：只允许架构明确声明的 ``thread_struct`` 范围参与受控 usercopy。

后面的 ``dup_task_struct()`` 才会从该 cache 分配新任务。当前函数返回时 cache 已存在，里面还没有 PID 1 对象。

``max_threads`` 来自可用内存，而不是 PID 上限
------------------------------------------

``fork_init()`` 调用 ``set_max_threads()``，根据估计的空闲物理页、``PAGE_SIZE`` 和 ``THREAD_SIZE`` 计算任务数量上限，使所有线程栈和任务结构不会轻易吃掉过大比例的内存。

需要区分：

.. code-block:: text

   pid_max      可分配 PID 数字范围
   max_threads  系统允许同时存在的任务数量上限

PID 数字空间很大，并不代表内存足以同时容纳同样数量的任务。

初始 rlimit 与 ucount 上限
-----------------------

``fork_init()`` 使用 ``max_threads / 2`` 初始化 ``init_task`` 的：

* ``RLIMIT_NPROC``；
* ``RLIMIT_SIGPENDING``；
* 初始 user namespace 的多类 ucount 默认上限。

同时为若干 user-namespace rlimit category 设置内部最大值。这些限制稍后参与 ``copy_process()`` 的资源检查。

这里没有用户 shell，也没有 ``ulimit`` 命令；只是内核先给初始 namespace 建立可执行的限制模型。

VMAP stack、SCS、lockdep 与 uprobes 收尾
------------------------------------

根据构建配置，``fork_init()`` 还会：

* 为 VMAP stack cache 注册 CPU hotplug 清理回调；
* 初始化 shadow call stack 支持；
* 把 ``init_task`` 接入 task-level lockdep 状态；
* 初始化 uprobes 的进程复制基础。

注册 CPU hotplug callback 不会启动 AP。它只规定某个 CPU 离线时怎样释放该 CPU 缓存的 vmapped stacks。

``proc_caches_init()`` 准备任务共享子对象
-------------------------------------

一个新进程不只有 ``task_struct``。``copy_process()`` 还需要创建或共享：

* ``signal_struct``：thread group 共享的信号、rlimit 和进程级状态；
* ``sighand_struct``：signal handler 表；
* ``files_struct``：文件描述符表；
* ``fs_struct``：root、pwd 和 umask 等 filesystem context；
* ``mm_struct``：用户地址空间；
* 其他 fork/proc 路径中的高频辅助对象。

``proc_caches_init()`` 为这些对象建立专用 slab caches。函数名中的 ``proc`` 指进程对象基础，不代表 ``/proc`` filesystem 已经挂载。真正的 procfs 根结构要到后面的 ``proc_root_init()``。

到这里内核“能分配进程对象”，仍未创建进程
--------------------------------------

现在已经具备：

.. code-block:: text

   PID namespace IDR 与 struct pid cache
   anon_vma / anon_vma_chain caches
   线程内核栈分配路径
   cred cache
   task_struct cache
   signal/files/fs/mm 等 caches
   max_threads 与初始 resource limits

仍未发生：

* ``copy_process()``；
* ``alloc_pid()``；
* ``wake_up_new_task()``；
* 第一次 ``schedule()``；
* PID 1/PID 2 创建；
* 用户地址空间建立；
* initramfs 解包。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``proc_caches_init()`` 已返回，``uts_ns_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* interrupts：CPU0 IF=1；
* PID allocator：初始 namespace IDR、范围和 ``struct pid`` cache 已建立；
* dynamic PID：尚未分配；
* anonymous rmap：对象 caches 已建立；
* thread stack：配置对应的分配/cache 入口已准备；
* credentials：``cred`` cache 已建立，PID 0 仍使用静态 ``init_cred``；
* fork：``task_struct`` 与进程子对象 caches、资源上限已准备；
* namespaces：UTS/time/network 初始化尚未执行；
* VFS/proc：正式 caches 和 pseudo-filesystem 基础尚未建立；
* PID 1 / PID 2：尚未创建。

下一条控制流是：

.. code-block:: c

   uts_ns_init();

接下来将建立 namespace、安全框架、VFS/page cache、signal 和 proc/nsfs/pidfs 基础。

资料
----

* `Linux 7.2-rc1 init/main.c：PID、fork 与进程对象初始化顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/pid.c：pid_idr_init、PID IDR 与 struct pid cache <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c>`_
* `Linux 7.2-rc1 mm/rmap.c：anon_vma 与 anon_vma_chain <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/rmap.c>`_
* `Linux 7.2-rc1 kernel/fork.c：thread stack、fork_init、task caches 与 copy_process 基础 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 kernel/cred.c：cred_init 与 credential 生命周期 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cred.c>`_
* `Linux credentials documentation：credential 模型 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/security/credentials.rst>`_