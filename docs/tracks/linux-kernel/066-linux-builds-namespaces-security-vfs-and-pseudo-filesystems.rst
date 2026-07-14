第六十六章：Linux 怎样建立 namespace、LSM、VFS 与伪文件系统基础？
================================================================

第六十五章结束时，PID、task、credential、signal、files、fs、mmap 与 nsproxy 的对象分配基础已经存在。当前仍只有 ``init_task / PID 0``，下一条调用是：

.. code-block:: c

   uts_ns_init();

随后 ``start_kernel()`` 连续执行：

.. code-block:: c

   uts_ns_init();
   time_ns_init();
   key_init();
   security_init();
   dbg_late_init();
   net_ns_init();
   vfs_caches_init();
   pagecache_init();
   signals_init();
   seq_file_init();
   proc_root_init();
   nsfs_init();
   pidfs_init();

本章追踪到 ``pidfs_init()`` 返回，停在 ``cpuset_init()`` 之前。这一段把“任务以后属于哪些隔离域、通过哪些安全钩子访问对象、怎样拥有文件路径和内核伪文件”所需的核心基础接起来。

``uts_ns_init()`` 建立主机名隔离对象
-----------------------------------

UTS namespace 隔离 ``uname()`` 能看到的系统标识，其中最常修改的是：

.. code-block:: text

   nodename   主机名
   domainname NIS domain name

``uts_ns_init()`` 创建 ``struct uts_namespace`` 的 usercopy-aware slab cache。允许 usercopy 的区域只覆盖 namespace 中的 ``name`` 字段，避免把对象内其他内核元数据意外复制给用户空间。

随后把静态的：

.. code-block:: c

   init_uts_ns

加入 namespace tree。

``init_task`` 早已通过静态 ``init_nsproxy`` 指向初始 UTS namespace。这里不是给 PID 0 切换 namespace，而是让 namespace 核心能够统一索引初始对象，并为未来 ``CLONE_NEWUTS`` 分配新的对象。

``time_ns_init()`` 只登记初始 time namespace
-------------------------------------------

Time namespace 不改变系统的真实 realtime clock。它主要给 namespace 内的：

* ``CLOCK_MONOTONIC``；
* ``CLOCK_BOOTTIME``；

附加偏移量，使 checkpoint/restore 后的进程可以继续看到符合原环境的单调时间和启动时间。

静态 ``init_time_ns`` 的 offset 被标记为 frozen，代表初始 namespace 直接使用 host 时间基准。``time_ns_init()`` 当前只执行：

.. code-block:: c

   ns_tree_add(&init_time_ns);

新 time namespace 的对象分配与 VDSO/VVAR page 准备发生在以后真正请求 ``CLONE_NEWTIME`` 时。

``key_init()`` 建立内核 key 管理基础
----------------------------------

Linux key retention service 为认证 token、密钥、证书和用户 keyring 提供统一对象模型。

``key_init()`` 创建 ``struct key`` slab cache，然后注册最早的内建 key type：

.. code-block:: text

   keyring
   dead
   user
   logon

它还把 root user 的 key quota tracking 对象插入全局 RB tree。

Key serial number 后续使用随机候选值分配，避免简单顺序编号形成不必要的可观测通道。第六十二章已经完成 RNG 的正式启动阶段，因此这里可以使用内核随机接口。

此刻还没有用户 session keyring，也没有读取磁盘证书。这里只是让 credentials、LSM 和后续 initcall 能创建、查找和限制 key 对象。

``security_init()`` 完成主要 LSM 框架初始化
-----------------------------------------

更早的 ``early_security_init()`` 已处理必须在内存和命令行系统完整可用前启动的 early LSM。当前 ``security_init()`` 进入完整的 LSM 选择与对象布局阶段。

它先依据：

.. code-block:: text

   lsm= command line
   security= legacy command line
   CONFIG_LSM built-in order

确定启用顺序，再让每个 LSM 报告它需要附加到哪些内核对象的 security blob，以及对应大小。

这些 blob 可以附着在：

* credential；
* task；
* inode、file、superblock；
* key；
* socket；
* IPC object；
* BPF object；
* perf event。

框架按最终大小创建必要的专用 cache，并给当前 PID 0 的静态 credential 与 task 分配 LSM 私有状态。之后才依次执行非 early LSM 的初始化函数和 hook registration。

因此这里建立的是访问控制决策入口。它不表示 SELinux、AppArmor 或其他某个具体 LSM 必然启用；具体组合取决于固定源码之外的构建配置与命令行。

LSM hook 怎样进入普通操作
------------------------

后续的文件打开、inode 创建、task signal、ptrace、socket、key 和 BPF 路径不会在每个调用点硬编码某个安全模块，而是调用统一接口，例如：

.. code-block:: text

   security_file_open()
   security_inode_permission()
   security_task_kill()
   security_socket_create()

LSM 框架把这些调用分派给已注册的 hook。当前初始化必须发生在正式 VFS cache 和后续 task 创建前，保证这些对象从诞生开始就能获得正确的 security blob。

``dbg_late_init()`` 是配置相关的内核调试入口
-------------------------------------------

``dbg_late_init()`` 由内核调试配置提供实现。启用 KGDB/KDB 等功能时，它完成不能在极早阶段执行的调试器状态；未启用对应配置时，该调用可以退化为空操作。

本书没有固定完整 ``.config``，因此不把它写成“调试器已经连接”或“串口已被 KGDB 接管”。控制流只确认 late debug hook 在这里执行。

``net_ns_init()`` 建立初始 network namespace
-------------------------------------------

Network namespace 隔离的不只是网卡名称。它包含路由、socket、netfilter、协议栈参数、网络设备集合和大量 per-net subsystem state。

``net_ns_init()`` 首先按配置创建：

* ``struct net`` cache；
* namespace cleanup workqueue；
* generic per-net pointer array。

随后初始化静态 ``init_net``：

.. code-block:: text

   preinit_net(init_net)
   → setup_net(init_net)
   → run registered pernet init callbacks
   → mark init_net_initialized

最后注册 network namespace 自身的 pernet subsystem 与 rtnetlink namespace-ID message handlers。

这不等于网络已经可用
--------------------

当前没有完成：

* PCI network device enumeration；
* NIC driver probe；
* loopback 与协议族的全部 initcall；
* DHCP 或静态地址配置；
* 用户空间 network manager。

这里建立的是 ``init_net`` 容器和 per-network-namespace 生命周期框架。

``vfs_caches_init()`` 把 VFS 对象模型接上
---------------------------------------

第六十一章以前只有极早期 VFS hash 基础。现在普通 allocator、LSM、credentials 与 namespace 已经可用，``vfs_caches_init()`` 可以建立正式 VFS 对象 cache 和全局管理结构。

固定调用顺序是：

.. code-block:: c

   filename_init();
   dcache_init();
   inode_init();
   files_init();
   files_maxfiles_init();
   mnt_init();
   bdev_cache_init();
   chrdev_init();

它们分别准备：

* pathname lookup 使用的 ``filename`` object；
* dentry cache 与 dentry hash；
* inode cache 与 inode hash；
* ``struct file`` cache 和系统 file 上限；
* mount object、mount hash 与初始 mount namespace 相关基础；
* block-device inode/cache；
* character-device number 与 cdev 管理基础。

``dcache_init_early()`` 可能已经根据 NUMA/hashdist 配置建立过 hash。正式 ``dcache_init()`` 仍需要创建 dentry slab，并在延迟分配配置下建立最终 hash。

建立 VFS cache 不等于已有根文件系统
---------------------------------

此刻还没有：

.. code-block:: text

   unpack initramfs
   mount root=/dev/sda1
   create /dev /sys final tree
   execute /init

VFS 现在只是拥有表示路径、inode、打开文件与 mount 的通用对象。

``pagecache_init()`` 建立 folio 等待基础
--------------------------------------

Page cache 通过 ``address_space`` 和 XArray 把文件 offset 映射到 folio。大量调用者需要等待 folio unlock、writeback 或其他状态变化。

``pagecache_init()`` 初始化 page/folio wait table，使这些等待者能够按 folio 地址进入对应 waitqueue。它不是读取磁盘，也不会主动向 page cache 填入文件内容。

``signals_init()`` 创建排队 signal 对象 cache
------------------------------------------

普通非实时 signal 可以合并，实时 signal 和携带 ``siginfo`` 的通知通常需要独立 queue object。

``signals_init()`` 先执行 ``siginfo`` ABI/build-time consistency checks，然后创建：

.. code-block:: c

   sigqueue_cachep

这让未来 task 可以排队 signal record。当前 PID 0 没有因此收到信号，也没有用户 signal handler。

``seq_file_init()`` 为内核生成文本接口准备对象
--------------------------------------------

``seq_file`` 解决 `/proc`、debugfs、sysfs 等接口输出长列表时的迭代、seek、buffer expansion 和 partial read 问题。

它的核心模型是：

.. code-block:: text

   start()
   → show()
   → next()
   → ...
   → stop()

``seq_file_init()`` 建立 ``struct seq_file`` cache。后续 ``seq_open()`` 从该 cache 分配 per-open state，并按需分配输出 buffer。

``proc_root_init()`` 注册 procfs，而不是挂载最终 ``/proc``
-------------------------------------------------------

``proc_root_init()`` 建立 procfs 内部目录和对象 cache，包括：

.. code-block:: text

   self
   thread-self
   mounts -> self/mounts
   net
   fs
   driver
   tty
   bus
   sysctl tree

并预留 ``fs/nfsd`` mount point，最后注册 ``proc`` filesystem type。

这里的关键边界是：

.. code-block:: text

   procfs internal tree and filesystem type  已建立
   final root namespace 中的 /proc mount      尚未发生

用户空间必须等根文件系统和 mount 操作可用后，才能从最终路径正常看到 `/proc`。

``nsfs_init()`` 给 namespace file descriptor 建立内部 mount
---------------------------------------------------------

Namespace file descriptor 需要一个真实 inode/dentry 身份，才能支持：

* ``/proc/<pid>/ns/*``；
* ``setns()``；
* namespace ioctl；
* bind mount namespace handle；
* namespace lifetime pinning。

``nsfs_init()`` 在内核内部 ``kern_mount()`` 一个 nsfs pseudo filesystem，并保存 root path。Namespace dentry 的显示名称采用：

.. code-block:: text

   uts:[inode-number]
   net:[inode-number]
   mnt:[inode-number]
   ...

这个 mount 是内核内部支撑对象，不等于用户 rootfs 上出现一个普通 nsfs mount point。

``pidfs_init()`` 给 pidfd 建立稳定的文件身份
-----------------------------------------

传统 PID 数字会复用。Pidfd 需要绑定 ``struct pid`` 的生命周期，而不是只保存一个可能失效的整数。

``pidfs_init()`` 完成三项基础：

#. 初始化 pid inode-number 到 ``struct pid`` 的 rhashtable；
#. 创建 ``pidfs_attr`` cache，用于退出状态、cgroup ID、coredump 与 xattr 等 pidfd metadata；
#. 在内核内部挂载 ``pidfs`` pseudo filesystem，并保存 root path。

未来创建 pidfd 时，内核可以为对应 ``struct pid`` 建立或复用 stashed dentry。64 位 x86 上，pidfs 使用 64 位 cookie 生成稳定 inode identifier。

Pidfs 初始化仍未创建任何 pidfd
------------------------------

当前没有 PID 1，也没有用户 file descriptor table 中的 pidfd。``pidfs_init()`` 只是建立表示机制和内部 mount。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``pidfs_init()`` 已返回，``cpuset_init()`` 尚未调用；
* current task：``init_task / swapper/0 / PID 0``；
* CPU：只有 CPU0 online；
* interrupts：CPU0 IF=1；
* UTS/time namespace：初始静态对象已加入 namespace tree；
* key service：对象 cache、基本 key type 与 root quota tracking 已建立；
* LSM：主要框架、object blob 和已选择模块 hook 已初始化；
* network namespace：``init_net`` 与 pernet 生命周期框架已建立；
* network devices/protocol stack：仍未完成全部 initcall；
* VFS：filename、dentry、inode、file、mount、bdev 与 cdev 基础已建立；
* page cache：folio wait infrastructure 已建立；
* signal：sigqueue cache 已建立；
* procfs：内部树与 filesystem type 已注册，最终 ``/proc`` 尚未挂载；
* nsfs/pidfs：内核内部 pseudo filesystem 已挂载；
* pidfd：尚未创建；
* cgroup/cpuset/memcg：下一阶段完成；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   cpuset_init();

资料
----

* `Linux 7.2-rc1 init/main.c：namespace、security、VFS 与伪文件系统初始化顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/utsname.c：UTS namespace cache 与初始对象登记 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/utsname.c>`_
* `Linux 7.2-rc1 kernel/time/namespace.c：time namespace offset 与 init_time_ns <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/namespace.c>`_
* `Linux 7.2-rc1 security/keys/key.c：key cache、类型与 root quota tracking <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/keys/key.c>`_
* `Linux 7.2-rc1 security/lsm_init.c：LSM order、blob layout 与 hook 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/lsm_init.c>`_
* `Linux 7.2-rc1 net/core/net_namespace.c：init_net 与 pernet subsystem <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/net_namespace.c>`_
* `Linux 7.2-rc1 fs/dcache.c：vfs_caches_init 与 dentry cache <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c>`_
* `Linux 7.2-rc1 mm/filemap.c：page cache 与 folio wait infrastructure <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/proc/root.c：proc_root_init 与 proc filesystem registration <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/proc/root.c>`_
* `Linux 7.2-rc1 fs/nsfs.c：namespace file identity 与 internal mount <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/nsfs.c>`_
* `Linux 7.2-rc1 fs/pidfs.c：pidfd inode identity、rhashtable 与 internal mount <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c>`_
