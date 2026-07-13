第六十五章：Linux 怎样建立 PID、凭据、fork 与进程对象基础？
==========================================================

第六十四章结束时，x86 已经完成 boot CPU 的 feature、FPU、alternative instruction 与时间系统收尾。CPU0 允许普通外部中断，当前执行者仍是 ``init_task / swapper/0 / PID 0``。

``start_kernel()`` 接下来执行：

.. code-block:: c

   pid_idr_init();
   anon_vma_init();
   thread_stack_cache_init();
   cred_init();
   fork_init();
   proc_caches_init();

本章追踪到 ``proc_caches_init()`` 返回，停在 ``uts_ns_init()`` 之前。这一段建立的是“以后可以创建任务”的对象、编号与缓存基础，并没有真正调用 ``copy_process()``，也没有创建 PID 1。

``pid_idr_init()`` 建立 PID 分配器
---------------------------------

Linux 中用户看到的 PID 不是直接从一个全局整数自增得到的。每个 PID namespace 都有自己的编号视图，内核还要把同一个 ``struct pid`` 关联到 PID、TGID、PGID、SID 等不同类型。

当前入口首先检查 PID 表示范围，并依据 possible CPU 数量调整默认 ``pid_max`` 下限。CPU 数越多，系统可能同时容纳的任务越多，默认 PID 空间不能小到频繁回绕。

随后初始化初始 PID namespace 的 IDR：

.. code-block:: c

   idr_init(&init_pid_ns.idr);

IDR 为整数编号到内核对象提供可增长映射。后面的 ``alloc_pid()`` 会从当前 PID namespace 及其祖先 namespace 中分配编号，再建立相应 ``struct pid``。

最后创建 ``struct pid`` 的 slab cache：

.. code-block:: c

   pid_cachep = KMEM_CACHE(pid,
       SLAB_HWCACHE_ALIGN | SLAB_PANIC | SLAB_ACCOUNT);

这让后续任务创建可以从专用 cache 分配 PID 对象。

PID 0 为什么已经存在
--------------------

``pid_idr_init()`` 不是在这里创建 PID 0。

最早的 ``init_task``、``init_struct_pid`` 与 ``init_pid_ns`` 都是静态对象。启动 CPU 从进入正式内核开始就以 PID 0 身份执行，只是普通动态 PID allocator 尚未建立。

因此此刻状态是：

.. code-block:: text

   PID 0 / init_task      已存在并正在执行
   dynamic PID allocator 已建立
   PID 1                 尚未分配
   PID 2                 尚未分配

真正的 PID 1 会在后面的 ``rest_init()`` 中通过 ``user_mode_thread(kernel_init, ...)`` 创建。

``anon_vma_init()`` 为匿名内存 reverse mapping 建立对象池
------------------------------------------------------

匿名内存页没有磁盘 inode 可以反查“它被哪些虚拟地址映射”。Linux 使用 ``anon_vma`` 与 ``anon_vma_chain`` 建立匿名页、VMA 和 fork 继承关系之间的 reverse mapping。

``anon_vma_init()`` 创建两个 cache：

.. code-block:: c

   anon_vma_cachep
   anon_vma_chain_cachep

``anon_vma`` constructor 初始化：

* ``rwsem``：保护对应的 reverse-mapping tree；
* ``refcount``：管理对象生命周期；
* cached RB tree root：索引关联的 VMA 区间。

``anon_vma_chain`` 则把一个 VMA 接到一个或多个 ``anon_vma``。fork 时，子进程的 VMA 会继承父进程已有的 anon-vma 链，并在需要时加入新的 active anon-vma。

为什么 fork 前必须建立它
------------------------

fork 通常先复制父进程的 VMA 元数据，并让父子暂时共享物理页。之后任何一方写入时，page fault 才触发 Copy-on-Write。

内核要完成这一过程，必须能够：

#. 找到某个匿名 folio 被哪些 VMA 映射；
#. 在父子 VMA 之间建立继承关系；
#. 在 reclaim、migration、unmap 与 COW 时安全遍历 reverse mapping；
#. 让已脱离普通引用的 ``anon_vma`` 经过 RCU 安全回收。

当前只创建了这些对象的 cache。PID 0 没有因此产生新的匿名地址空间，任何用户 VMA 也尚未出现。

``thread_stack_cache_init()`` 的行为取决于构建配置
------------------------------------------------

每个新任务都需要内核栈，但 Linux 可以采用不同实现：

.. code-block:: text

   physically allocated thread stack pages
   或
   VMAP_STACK virtual stacks with guard pages
   或
   小于 PAGE_SIZE 时使用 dedicated slab cache

所以 ``thread_stack_cache_init()`` 不能脱离 ``.config`` 写成一个固定动作。

当体系结构使用小型、可由 slab 容纳的 thread stack 时，它建立允许架构 thread-info 区域进行 usercopy 的专用 cache。若 thread stack 直接按页分配，或者由 ``CONFIG_VMAP_STACK`` 路径管理，该入口可以退化为空操作或只承担对应配置的准备工作。

固定源码没有同时固定完整 ``.config``，本章只确认启动顺序和各配置分支的语义，不假设某个分支必然启用。

``cred_init()`` 建立任务凭据 cache
---------------------------------

每个 task 的凭据并不直接散落在 ``task_struct`` 中，而是通过引用指向 ``struct cred``。其中包含：

* real/effective/saved UID、GID；
* supplementary groups；
* capability sets；
* user namespace；
* keyring 引用；
* LSM security blob；
* per-user resource accounting 引用。

``cred_init()`` 创建：

.. code-block:: c

   cred_jar = KMEM_CACHE(cred,
       SLAB_HWCACHE_ALIGN | SLAB_PANIC | SLAB_ACCOUNT);

后续 ``prepare_creds()``、``copy_creds()`` 和 kernel service credential 路径都从这里分配对象。

凭据对象通常以 RCU 方式延迟释放，因为其他 CPU 可能正在无锁读取 task 的 credentials。当前仅建立 cache；PID 0 已经使用静态 ``init_cred``，不会在这里重新获得一套身份。

``fork_init()`` 建立 task_struct 分配路径
---------------------------------------

``fork_init()`` 首先创建 ``task_struct`` cache，并根据体系结构要求完成 task cache 的附加初始化。

之后它估算系统可支持的默认线程数量。核心约束是：即使大量任务同时存在，所有 thread stack 消耗也不应轻易占满内存。源码以可用页和每个 thread stack 所需页数计算 ``max_threads``，并设置启动期的：

.. code-block:: text

   RLIMIT_NPROC
   RLIMIT_SIGPENDING
   user namespace ucount maxima

这些值不是已经创建的线程数量，而是后续 fork/clone 路径使用的上限基础。

根据构建配置，``fork_init()`` 还会准备：

* VMAP stack 的 CPU hotplug 状态；
* shadow call stack cache；
* ``init_task`` 的 lockdep task state；
* uprobes task duplication 基础。

``fork_init()`` 返回后，内核已经能够分配新的 task shell，但 task 的 PID、mm、files、signal、credentials、namespace 与 scheduler 状态仍要由 ``copy_process()`` 按顺序组合。

“fork 基础已建立”不等于已经执行 fork
-------------------------------------

此刻没有调用：

.. code-block:: text

   kernel_clone()
   copy_process()
   user_mode_thread()
   kernel_thread()

所以：

* task list 仍只有启动期静态任务；
* PID 1 不存在；
* ``kthreadd`` 不存在；
* scheduler 也没有因为 cache 初始化而切换任务。

``proc_caches_init()`` 补齐进程共享对象 cache
--------------------------------------------

任务创建不仅需要 ``task_struct``。Linux 把许多可共享或独立复制的状态拆成专门对象。

``proc_caches_init()`` 创建：

.. code-block:: text

   sighand_cache → signal handler table and siglock
   signal_cache  → thread-group shared signal/accounting state
   files_cache   → file descriptor table owner
   fs_cache      → cwd, root and umask state

它还调用：

.. code-block:: c

   exec_state_init();
   mmap_init();
   nsproxy_cache_init();

分别为 exec 状态、VMA 管理对象和 namespace 引用组合 ``nsproxy`` 建立基础。

``mm_struct`` cache 不是在这里创建
---------------------------------

源码中 ``mm_cache_init()`` 与 ``proc_caches_init()`` 是独立入口。前者根据 ``nr_cpu_ids`` 动态计算 ``mm_struct`` 尾部 cpumask 大小，并建立 mm cache；它已经在更早的内存管理初始化路径完成。

本章不能把 ``proc_caches_init()`` 写成“创建了所有进程对象”。它补齐的是 signal/files/fs/mmap/nsproxy 等这一组 cache。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``proc_caches_init()`` 已返回，``uts_ns_init()`` 尚未调用；
* current task：``init_task / swapper/0 / PID 0``；
* CPU：只有 CPU0 online；
* interrupts：CPU0 IF=1；
* PID allocator：初始 namespace IDR 与 ``struct pid`` cache 已建立；
* PID 0：仍由静态对象表示；
* PID 1 / PID 2：尚未创建；
* anonymous reverse mapping：``anon_vma`` 与 chain cache 已建立；
* task allocation：``task_struct`` 与配置相关 thread-stack 路径已准备；
* credentials：``cred`` cache 已建立，PID 0 仍使用 ``init_cred``；
* process shared objects：sighand、signal、files、fs、mmap 与 nsproxy cache 已建立；
* namespace 初始化：下一步才开始；
* VFS 正式 cache、procfs、nsfs、pidfs：尚未建立；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   uts_ns_init();

资料
----

* `Linux 7.2-rc1 init/main.c：start_kernel 中的进程对象初始化顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/pid.c：pid_idr_init、init_pid_ns 与 struct pid cache <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c>`_
* `Linux 7.2-rc1 mm/rmap.c：anon_vma cache、reverse mapping 与 fork 链接 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/rmap.c>`_
* `Linux 7.2-rc1 kernel/cred.c：credential cache 与 RCU 生命周期 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cred.c>`_
* `Linux 7.2-rc1 kernel/fork.c：thread stack、fork_init 与 proc_caches_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
