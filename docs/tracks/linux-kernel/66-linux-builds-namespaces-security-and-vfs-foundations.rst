第六十六章：Linux 怎样建立 namespace、安全框架与 VFS/proc 基础？
================================================================

第六十五章结束时，PID allocator、``task_struct``、credential、匿名反向映射和 fork 相关对象 cache 已经建立。内核现在能够为未来任务分配基本对象，但仍未创建 PID 1。

``start_kernel()`` 接下来依次执行：

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

本章追踪到 ``pidfs_init()`` 返回，停在 ``cpuset_init()`` 之前。

namespace 初始化不等于创建容器
----------------------------

namespace 是内核对象隔离机制。容器运行时会组合 mount、PID、UTS、IPC、network、user、cgroup 和 time namespace，但这些内核机制并不依赖 Docker 或 Kubernetes 才存在。

当前阶段做的是：

.. code-block:: text

   准备初始 namespace
   → 建立未来 clone/unshare 所需的对象分配与操作表
   → 把初始对象加入 namespace 管理结构

此时没有容器进程，没有 ``clone(CLONE_NEW*)``，也没有用户空间 runtime。

``uts_ns_init()`` 准备 hostname/domainname 隔离
--------------------------------------------

UTS namespace 隔离 ``uname()`` 可见的系统身份，主要包括：

* system name；
* node name / hostname；
* release；
* version；
* machine；
* domain name。

``uts_ns_init()`` 创建 ``uts_namespace`` slab cache。它使用 usercopy whitelist，只允许 ``struct uts_namespace`` 中的 ``name`` 区域参与受控用户复制，避免把引用计数、namespace linkage 或内部指针误暴露给用户空间。

函数随后把静态 ``init_uts_ns`` 加入 namespace tree。

初始 UTS namespace 早已存在
-------------------------

与 PID 0 类似，``init_uts_ns`` 是静态对象。启动 banner 和早期内核代码早已可以读取 ``init_utsname()``。

当前调用解决的是两件后续问题：

#. 新 UTS namespace 从哪里分配；
#. 初始 namespace 怎样进入统一的 namespace 枚举与生命周期管理结构。

它不会修改当前 hostname，也不会执行 ``sethostname()``。

``time_ns_init()`` 登记初始 time namespace
----------------------------------------

Time namespace 允许不同任务看到带 offset 的：

* ``CLOCK_MONOTONIC``；
* ``CLOCK_BOOTTIME``；
* 与这些时钟相关的 VDSO 数据。

它不会隔离 realtime wall clock。这样容器可以拥有独立的“启动后经过时间”，又不会任意改变整台机器的 UTC 时间。

固定实现中的 ``init_time_ns`` 是静态对象，offset 已冻结。``time_ns_init()`` 只把它加入 namespace tree。

未来创建新 time namespace 时，``clone_time_ns()`` 才会：

* 分配 ``struct time_namespace``；
* 分配该 namespace 的 VVAR page；
* 复制 monotonic/boottime offsets；
* 关联 owning user namespace；
* 加入 namespace tree。

当前没有创建第二个 time namespace，也没有改变 CPU0 timekeeping。

``key_init()`` 建立内核 key management 基础
--------------------------------------

启用 ``CONFIG_KEYS`` 时，Linux key subsystem 管理：

* authentication token；
* keyring；
* request-key 授权；
* filesystem encryption key；
* asymmetric key/certificate；
* 用户、session、process 与 thread keyring。

``key_init()`` 建立 key 对象 cache、serial-number 索引、用户 quota 记录以及初始 key/keyring 类型所需基础。

key serial 不是 PID
------------------

每个 key 有自己的 serial number，由 key subsystem 的树索引。它与 PID namespace、file descriptor 或 inode number 无关。

源码会使用随机数选择 key serial，前面先完成 ``random_init()`` 的顺序因此具有实际意义：key subsystem 不必在更早的低质量状态下生成全部身份编号。

若内核未启用 ``CONFIG_KEYS``，该入口可以编译为空操作。正文记录调用顺序，不能在没有固定 ``.config`` 时断言一定创建了所有 key type。

``security_init()`` 进入完整 LSM 初始化阶段
----------------------------------------

前面的 ``early_security_init()`` 只处理必须在 allocator 和大部分通用子系统之前运行的早期 security hooks。

现在 ``security_init()`` 进入完整 Linux Security Module（LSM）框架初始化，按构建配置和 ``lsm=`` 顺序启动例如：

* capability；
* SELinux；
* AppArmor；
* Smack；
* TOMOYO；
* Yama；
* Landlock；
* lockdown；
* integrity 相关模块。

具体启用集合由内核配置和命令行决定。固定启动路径没有提供完整 ``.config``，因此只能确认 LSM init sequence 已执行，不能声称某个特定 MAC policy 已加载。

LSM hook 已存在不代表 policy 已可用
--------------------------------

``security_init()`` 建立 hook dispatch、security blob 布局和已配置 LSM 的初始化状态。某些 LSM 的完整 policy 仍依赖：

* securityfs；
* initramfs 中的 policy 文件；
* filesystem mount；
* userspace loader；
* 后续 initcall。

当前 initramfs 尚未解包，用户空间也不存在，因此“LSM 框架已初始化”和“SELinux policy 已加载”必须分开。

``dbg_late_init()`` 扩展 debug objects 运行能力
-------------------------------------------

第五十八章以前的 debug objects 只能依赖启动期静态对象池。现在 slab、interrupt、timer 和 workqueue 基础都已具备，``dbg_late_init()`` 可以把该调试框架推进到晚期运行方式。

根据配置，它会补充动态对象分配和后续回收能力，让 timer、work、RCU head 等对象生命周期检查不再受最早静态池限制。

未启用 ``CONFIG_DEBUG_OBJECTS`` 时，这个调用可以为空。

``net_ns_init()`` 先建立 network namespace 核心
-------------------------------------------

Network namespace 隔离：

* network devices；
* IPv4/IPv6 protocol state；
* route tables；
* netfilter；
* sockets；
* ``/proc/net``；
* sysctl network state。

``net_ns_init()`` 初始化 ``struct net`` 的通用分配和生命周期管理，准备初始 ``init_net``，并建立 per-network-subsystem 注册框架。

这里不会扫描网卡
--------------

此时还没有完整 driver initcall，也没有 PCI network driver probe。``init_net`` 的存在只表示网络协议和设备对象有一个初始 namespace 容器。

以下事项仍未发生：

* 创建 ``eth0``；
* DHCP；
* 配置 IP address；
* 注册具体 NIC IRQ handler；
* 启动 userspace network service。

``vfs_caches_init()`` 把 VFS 对象分配推入正式阶段
--------------------------------------------

前面的 ``vfs_caches_init_early()`` 在普通 allocator 完全建立之前，只创建最早的 dentry/inode hash sizing 和必要基础。

现在的 ``vfs_caches_init()`` 可以使用 slab、per-CPU 和 shrinker 基础，正式准备 VFS 高频对象，例如：

* pathname/name buffer；
* dentry；
* inode；
* open file object；
* files table 相关全局限制；
* VFS cache 回收所需状态。

VFS 是对象模型，不是某个具体磁盘格式
--------------------------------

VFS 让 ext4、tmpfs、procfs、sysfs 等不同 filesystem 通过统一对象工作：

.. code-block:: text

   super_block
   → inode
   → dentry
   → path
   → file
   → file_operations

初始化这些 cache 不代表 ext4 root 已挂载。当前 ``root=/dev/sda1`` 仍只是启动参数，block device 和 ext4 driver 还没有走完 initcall。

``pagecache_init()`` 准备文件页缓存基础
-----------------------------------

Page cache 把文件 offset 映射到内存 folio，使普通 read、write 和 mmap 可以共享缓存数据。

``pagecache_init()`` 建立 page-cache 核心所需的等待、锁和对象基础，使后面的 ``address_space->i_pages``、folio wait、readahead、writeback 与 filemap fault 能进入正常路径。

它不会读取磁盘，也不会为 root filesystem 缓存任何页面。只有后续 filesystem 被挂载并发生文件访问时，具体 folio 才会进入 page cache。

``signals_init()`` 为 queued signal 建立分配基础
-------------------------------------------

Linux task 的 signal state 一部分嵌在 ``task_struct``、``signal_struct`` 和 ``sighand_struct`` 中，带 ``siginfo`` 的排队信号还需要动态 ``sigqueue`` 对象。

``signals_init()`` 建立 signal queue cache 和相关全局基础。此时 PID 0 没有进入用户态，也不会因为初始化函数执行而收到用户 signal。

真正向新任务复制 signal state 要等 ``copy_process()`` 中的 ``copy_sighand()`` 和 ``copy_signal()``。

``seq_file_init()`` 准备稳定输出可变内核数据
---------------------------------------

``seq_file`` 解决一类常见问题：内核对象列表可能很长且会变化，用户又可能用多次 ``read()`` 分段读取。

它提供：

.. code-block:: text

   start()
   → next()
   → show()
   → stop()

以及自动 buffer 扩展和 file position 管理。大量 ``/proc``、debugfs 和 sysfs-style text output 都依赖这一接口。

当前只建立 seq_file 对象分配基础，没有用户进程打开文件。

``proc_root_init()`` 注册 procfs 核心
---------------------------------

procfs 把运行中的任务和内核状态投影成伪文件，例如：

.. code-block:: text

   /proc/<pid>/status
   /proc/meminfo
   /proc/interrupts
   /proc/cmdline
   /proc/sys

``proc_root_init()`` 建立 proc inode/cache、根目录和 filesystem type，并准备 ``self``、``thread-self`` 等特殊入口所需结构。

注册 filesystem 不等于挂载
------------------------

``register_filesystem(&proc_fs_type)`` 只让 VFS 知道名为 ``proc`` 的 filesystem 怎样创建 superblock。用户可见的 ``/proc`` 仍需要 kernel/initramfs/userspace 在某个 mount point 执行挂载。

所以当前不能读取 ``/proc/1/status``：PID 1 尚不存在，procfs 也未必已挂载。

``nsfs_init()`` 给 namespace 文件描述符提供 inode 身份
-----------------------------------------------

``nsfs`` 是 namespace 对象的内部 pseudo filesystem。``/proc/<pid>/ns/*`` 打开的 namespace fd 需要一个稳定的 ``struct file``/inode 身份，才能支持：

* ``setns()``；
* namespace fd 传递；
* ``stat()`` 区分 namespace object；
* 生命周期引用计数。

``nsfs_init()`` 注册并建立该内部 filesystem。它不创建新的 namespace，只为已有和未来 namespace 提供 file representation。

``pidfs_init()`` 为 pidfd 建立 filesystem 表示
-----------------------------------------

pidfd 用文件描述符稳定引用某个 ``struct pid``，避免只使用数字 PID 时的复用竞态。

``pidfs`` 为 pidfd 提供内部 inode/file 表示，使：

* pidfd poll；
* pidfd signal；
* pidfd info；
* task exit 后的稳定状态；
* ``struct pid`` 与 inode 生命周期连接；

能够通过标准 file descriptor 模型工作。

``pidfs_init()`` 建立 pidfs 的内部 mount 和 inode 基础。它不会分配 PID 1，也不会自动创建任何 pidfd；后面实际调用 ``pidfd_prepare()`` 或相关 syscall 时才产生 file object。

本章结束时，内核已经能“表示”任务和 namespace
-------------------------------------------

现在的基础链为：

.. code-block:: text

   task / pid / cred caches
   → UTS/time/network namespace roots
   → key and LSM framework
   → VFS inode/dentry/file caches
   → page cache and signals
   → seq_file
   → procfs/nsfs/pidfs filesystem representations

这使未来 PID 1、内核线程和用户进程可以被 VFS、procfs、namespace fd 与 pidfd 观察和引用。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``pidfs_init()`` 已返回，``cpuset_init()`` 尚未调用；
* current：``init_task`` / ``swapper/0`` / PID 0；
* CPU：只有 CPU0 online；
* interrupts：CPU0 IF=1；
* UTS namespace：初始对象已登记，动态 cache 已建立；
* time namespace：初始对象已登记，offset 保持初始值；
* key subsystem：按配置完成核心初始化；
* LSM：按配置执行完整 security init sequence，具体 policy 未必加载；
* network namespace：``init_net`` 核心已准备，网络设备尚未枚举；
* VFS：dentry/inode/file/name cache 基础已建立；
* page cache：核心基础已建立，没有读取 root disk；
* procfs：filesystem type 与根结构已准备，未断言已挂载；
* nsfs/pidfs：内部 pseudo-filesystem representation 已建立；
* cgroup/cpuset/memcg：尚未初始化；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   cpuset_init();

接下来将建立 cpuset、memory cgroup、完整 cgroup hierarchy、task accounting、ACPI mode 与最后的并发访问检查，随后到达 ``rest_init()``。

资料
----

* `Linux 7.2-rc1 init/main.c：namespace、security、VFS 与 pseudo filesystem 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/utsname.c：uts_ns_init 与 UTS namespace cache <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/utsname.c>`_
* `Linux 7.2-rc1 kernel/time/namespace.c：初始 time namespace 与 offsets <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/namespace.c>`_
* `Linux 7.2-rc1 security/keys/key.c：key object、serial tree 与 key_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/keys/key.c>`_
* `Linux 7.2-rc1 security/security.c：LSM framework initialization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/security.c>`_
* `Linux 7.2-rc1 net/core/net_namespace.c：initial network namespace <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/net_namespace.c>`_
* `Linux 7.2-rc1 fs/dcache.c：VFS dentry/name cache <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c>`_
* `Linux 7.2-rc1 fs/inode.c：inode cache initialization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/inode.c>`_
* `Linux 7.2-rc1 mm/filemap.c：page cache core <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/proc/root.c：proc_root_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/proc/root.c>`_
* `Linux 7.2-rc1 fs/nsfs.c：namespace filesystem <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/nsfs.c>`_
* `Linux 7.2-rc1 fs/pidfs.c：pidfd filesystem representation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c>`_