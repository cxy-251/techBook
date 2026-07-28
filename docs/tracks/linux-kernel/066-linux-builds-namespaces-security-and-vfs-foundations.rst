第六十六章：Linux怎样建立名字空间、安全框架与VFS基础？
=====================================================

第六十五章结束时，动态任务所需的PID、 ``task_struct``、凭据和共享对象缓存已经就绪，但初始
任务仍是唯一运行者。内核接下来要把静态初始名字空间接入名字空间树，完成可选密钥与安全框架，
再建立网络名字空间、VFS、内部根文件系统和几个伪文件系统。本章从 ``uts_ns_init()`` 开始，
执行到 ``pidfs_init()`` 返回，并停在第067章的 ``cpuset_init()`` 之前。

初始名字空间对象与动态创建能力是两件事
------------------------------------

相应名字空间配置启用时， ``init_uts_ns`` 和 ``init_time_ns`` 在进入本章前已经是静态对象。
初始化函数的任务，是把初始对象接入全局名字空间索引，并为以后复制名字空间准备动态对象能力；
它们不会在当前CPU0之外创建任务或名字空间实例。

启用 ``CONFIG_UTS_NS`` 时， ``uts_ns_init()`` 创建 ``uts_namespace`` 用户复制缓存，再把
``init_uts_ns`` 加入名字空间树。缓存只允许用户复制其中的 ``name`` 字段范围。未启用该配置
时，头文件提供空实现，带 ``CLONE_NEWUTS`` 的后续请求也会因不支持而失败。

启用 ``CONFIG_TIME_NS`` 时， ``time_ns_init()`` 只把 ``init_time_ns`` 加入名字空间树；
该初始对象的 ``user_ns`` 指向 ``init_user_ns``，时间偏移已经冻结。未启用时入口为空。本行
不会修改主机时间，也不会为当前任务施加新的时间偏移。

密钥子系统按构建配置出现
----------------------

启用 ``CONFIG_KEYS`` 时， ``key_init()`` 创建保存 ``struct key`` 的 ``key_jar`` 缓存，把
``keyring``、 ``dead``、 ``user`` 和 ``logon`` 四种特殊密钥类型加入全局类型链表，再把
``root_key_user`` 插入密钥用户红黑树。缓存创建带 ``SLAB_PANIC``，无法建立时不会继续启动。

未启用 ``CONFIG_KEYS`` 时， ``key_init()`` 是空宏。即使启用并正常返回，本章也没有为
``init_task`` 安装线程、进程或会话密钥环；这里只是建立密钥对象与根用户记账的全局基础。

security_init承接更早的早期安全初始化
-------------------------------------

第050章已经执行 ``early_security_init()``，只初始化标记为早期的LSM。本章启用
``CONFIG_SECURITY`` 时， ``security_init()`` 先按 ``lsm=`` 启动参数或内建顺序解析普通
LSM列表，再对所选模块执行 ``lsm_prepare()``，由此累计各类安全私有数据所需空间。

如果文件、底层文件或inode需要单独私有对象，函数会创建相应SLUB缓存。随后它为当前
``init_task`` 的既有凭据分配LSM私有区，并为当前任务分配任务私有区；任一步失败都会触发
``panic()``。最后，函数跳过已经执行的早期模块，依次初始化其余选中LSM。

未启用 ``CONFIG_SECURITY`` 时， ``security_init()`` 直接返回0。配置启用也不意味着某个具体
LSM必然出现，因为最终集合还受构建选择和 ``lsm=`` 参数影响。本章能够确认的是框架按该集合
完成准备并把当前启动任务接入，而不是预先断言SELinux、AppArmor或其他模块的具体状态。

dbg_late_init只属于KGDB和KDB
----------------------------

启用 ``CONFIG_KGDB`` 时， ``dbg_late_init()`` 把 ``dbg_is_early`` 清为假；已经登记KGDB输入
输出模块时，它执行体系结构晚期处理；随后以完整模式初始化KDB。如果启动参数要求尽早中断且
输入输出模块已经登记，它还会等待远程调试连接并触发断点。

未启用 ``CONFIG_KGDB`` 时，该入口由宏展开为空。它不是调试对象、锁检查或内存检测器的通用
初始化函数；旧正文把它解释成“晚期调试设施全面就绪”，超过了函数的真实边界。

初始网络名字空间怎样上线
------------------------

未启用 ``CONFIG_NET`` 时， ``net_ns_init()`` 是空函数。启用网络时，函数先为
``init_net`` 分配通用的逐网络名字空间数据；如果还启用 ``CONFIG_NET_NS``，它会先创建
``net_namespace`` 缓存和单线程清理工作队列。工作队列创建失败会触发 ``panic()``。

函数把通用数据发布到 ``init_net.gen``，按密钥配置连接 ``init_net_key_domain``，再执行
``preinit_net()`` 和 ``setup_net()``。后者在 ``pernet_ops_rwsem`` 写锁保护下运行此前已经
登记的逐网络名字空间初始化操作；失败会停止启动。成功后设置
``init_net_initialized=true``，登记网络名字空间自身的逐网络操作和名字空间标识路由消息
处理函数。

这个入口使初始网络名字空间能够承接已经登记的网络子系统，不等于所有协议、网卡驱动和网络
设备都已初始化。多数网络组件仍要在后续初始化调用阶段进入。

VFS缓存入口还建立了初始挂载树
----------------------------

``vfs_caches_init()`` 的固定顺序是：

.. code-block:: c

   filename_init();
   dcache_init();
   inode_init();
   files_init();
   files_maxfiles_init();
   mnt_init();
   bdev_cache_init();
   chrdev_init();

前五个入口分别建立文件名、目录项、inode和打开文件对象的缓存与哈希基础，并根据内存规模确定
文件对象上限。 ``dcache_init()`` 与 ``inode_init()`` 会接续第055章建立的早期哈希表；是否
重新分配分布式哈希表取决于此前的 ``hashdist`` 决策，不能把两个阶段写成重复初始化。

``mnt_init()`` 不只是建立挂载对象缓存和哈希表。它还初始化 ``kernfs``，尝试初始化
``sysfs`` 和 ``fs_kobj``，初始化共享内存与 ``rootfs`` 文件系统，然后执行
``init_mount_tree()``。 ``sysfs_init()`` 或 ``fs_kobj`` 失败只记录警告；挂载哈希表、
``nullfs``、可变 ``rootfs`` 或叠加挂载建立失败则会触发 ``panic()``。

内部根文件系统在这里成为当前根与工作目录
--------------------------------------

``init_mount_tree()`` 创建两个挂载：挂载标识1的 ``nullfs`` 作为初始挂载名字空间根，挂载
标识2的可变 ``rootfs`` 叠加在其上。函数把两者加入 ``init_mnt_ns``，令
``init_task.nsproxy->mnt_ns`` 指向该名字空间，并把当前任务的根目录和工作目录都设为可变
``rootfs``，最后把 ``init_mnt_ns`` 加入名字空间树。

因此，本章结束时已经存在供内核启动继续使用的内部根挂载。它不是固定磁盘
``/dev/sda1`` 上的最终ext4根文件系统；初始内存盘归档也尚未在本章解包。后续
``populate_rootfs``、 ``prepare_namespace()`` 或用户空间切根仍有各自边界。

页缓存入口建立等待与回写基础
----------------------------

``pagecache_init()`` 初始化 ``folio_wait_table`` 中的全部等待队列头，然后执行
``page_writeback_init()`` 并按 ``CONFIG_SYSCTL`` 登记 ``vm/page_lock_unfairness``。这些
对象使页与folio锁等待、脏页回写控制能够工作，但本入口没有读取磁盘文件，也没有把初始内存盘
内容填入 ``rootfs``。

信号与顺序文件准备按需对象
--------------------------

``signals_init()`` 先执行 ``siginfo`` 构建期布局检查，再创建 ``sigqueue`` 缓存。这个缓存
供以后排队的实时信号和其他信号信息使用；当前没有给 ``init_task`` 发送信号。

``seq_file_init()`` 创建 ``seq_file`` 缓存，为以后按序生成虚拟文件内容提供对象。它不创建
任何具体 ``/proc`` 文件，实际目录和入口由下一步建立。

proc_root_init登记但不挂载procfs
-------------------------------

启用 ``CONFIG_PROC_FS`` 时， ``proc_root_init()`` 创建proc对象缓存，设置按PID目录链接数，
建立 ``self``、 ``thread-self``、 ``mounts`` 链接以及 ``net``、 ``fs``、 ``driver``、
``tty``、 ``bus`` 和 ``sys`` 等顶层结构，最后登记名为 ``proc`` 的文件系统类型。

未启用该配置时入口为空。启用并返回也只表示文件系统类型和内核侧目录结构已登记；
``procfs`` 尚未挂载到当前 ``rootfs`` 的某个路径，用户任务也尚不存在，不能在此声称用户已经
能访问 ``/proc``。

nsfs与pidfs建立内部挂载
----------------------

``nsfs_init()`` 以内核挂载方式建立 ``nsfs``。失败会触发 ``panic()``；成功后函数清除超级块
的 ``SB_NOUSER`` 标志，并保存根路径。这个文件系统为名字空间文件描述符提供统一inode和路径
表示，不会额外创建名字空间。

``pidfs_init()`` 先初始化PID inode散列表，再创建 ``pidfs_attr_cache``，最后内核挂载
``pidfs`` 并保存根路径。散列表或挂载失败都会停止启动。第065章的 ``alloc_pid()`` 已经会为
将来的 ``struct pid`` 准备 ``pidfs`` 状态，而到这里支撑pidfd路径和属性的全局文件系统才
完整可用。

本章结束状态
------------

::

   当前执行者          = CPU0上的start_kernel()；pidfs_init()已返回
   下一入口            = cpuset_init()
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   UTS名字空间         = 按配置建立缓存并接入名字空间树，或入口为空
   时间名字空间        = 按配置接入名字空间树，或入口为空
   密钥基础            = 按配置建立缓存、特殊类型与根用户记账，或入口为空
   安全框架            = 按配置和启动参数完成LSM准备并接入init_task，或入口为空
   KGDB/KDB            = 按配置完成晚期切换，或入口为空
   初始网络名字空间    = CONFIG_NET启用时已经设置；完整协议与设备尚未初始化
   VFS                 = 文件名、目录项、inode、文件、挂载、块设备和字符设备基础已建立
   初始挂载名字空间    = nullfs与可变rootfs已经挂载并接入init_task
   当前根与工作目录    = 指向可变rootfs
   最终磁盘根          = 尚未挂载
   初始内存盘          = 尚未在本章解包
   页缓存等待/回写     = 基础已经初始化
   信号队列/seq_file   = 对象缓存已经建立
   procfs              = 按配置登记但尚未挂载
   nsfs/pidfs          = 内部挂载已经建立
   新任务              = 尚未创建
   PID1/PID2           = 尚未创建

关键边界
--------

* UTS、时间、密钥、安全、KGDB、网络和proc入口都有明确构建条件，不能把一次调用写成所有子系统
  必然存在；
* ``security_init()`` 按最终LSM顺序处理当前启动任务，不证明某个具名LSM必然启用；
* ``vfs_caches_init()`` 不只创建缓存， ``mnt_init()`` 还建立初始挂载名字空间和内部
  ``rootfs``；
* 当前 ``rootfs`` 是启动期可变根，不是最终ext4磁盘根，初始内存盘也尚未由本章解包；
* ``proc_root_init()`` 只登记 ``procfs``，而 ``nsfs_init()`` 与 ``pidfs_init()`` 会立即建立
  各自的内核内部挂载；
* 全部工作仍在CPU0和 ``init_task`` 上同步完成，没有创建PID 1、PID 2或应用处理器任务。

下一入口
--------

``start_kernel()`` 下一条语句是 ``cpuset_init()``。第067章将进入CPU集合、内存控制组、控制
组、任务统计和延迟记账等基础，随后经过ACPI子系统和KCSAN条件入口，到达
``rest_init()``；只有那里才会创建PID 1与PID 2并把启动流程交给调度器。

资料
----

* `start_kernel()中的第066章完整调用区间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1151-L1167>`_
* `uts_ns_init()创建缓存并登记初始UTS名字空间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/utsname.c#L142-L164>`_
* `time_ns_init()登记初始时间名字空间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/namespace.c#L341-L360>`_
* `key_init()的密钥缓存、特殊类型和根用户记账
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/keys/key.c#L1271-L1293>`_
* `security_init()的LSM顺序、私有对象和当前任务处理
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/lsm_init.c#L403-L494>`_
* `dbg_late_init()的KGDB与KDB晚期行为
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/debug/debug_core.c#L1010-L1031>`_
* `net_ns_init()建立初始网络名字空间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/net_namespace.c#L1251-L1302>`_
* `vfs_caches_init()的固定子入口顺序
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c#L3499-L3520>`_
* `mnt_init()和初始挂载树
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/namespace.c#L6172-L6277>`_
* `pagecache_init()的等待队列与回写入口
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c#L1070-L1097>`_
* `signals_init()建立sigqueue缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c#L5000-L5014>`_
* `seq_file_init()建立顺序文件对象缓存
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/seq_file.c#L1141-L1144>`_
* `proc_root_init()建立目录结构并登记procfs
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/proc/root.c#L369-L403>`_
* `nsfs_init()建立名字空间文件系统内部挂载
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/nsfs.c#L662-L689>`_
* `pidfs_init()建立散列表、属性缓存和内部挂载
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c#L1141-L1156>`_
