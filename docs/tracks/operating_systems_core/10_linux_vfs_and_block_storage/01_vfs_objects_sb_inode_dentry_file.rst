========================================================================================
第 1 节：VFS 四大核心对象：super_block、inode、dentry 与 file 拓扑与函数指针分发
========================================================================================

.. note::
   **前置背景与上下文承接**
   * **体系结构基准**：承接模块 09 中关于 Linux 7.2 任务管理、进程生命周期、EEVDF 调度器、抢占状态机与内核上下文切换的完整推导。
   * **核心使命**：解构 Linux 存储与 I/O 抽象的万物总纲——**虚拟文件系统（Virtual File System / VFS）**；深度剖析 VFS 统一面向对象多态架构；全面解构四大核心元数据对象：
     1. **超级块（``struct super_block``）**：描述整个挂载文件系统的全局物理与逻辑元数据（块大小、魔数、``s_op``、``s_writers`` 三级冻结锁与双 LRU 链表）；
     2. **索引节点（``struct inode``）**：代表物理磁盘上唯一真实存在的静态文件/目录元数据实体（``i_ino``、``i_mode``、``i_size``、``i_mapping``、``i_op``、``i_fop``、``i_nlink`` 硬链接）；
     3. **目录项（``struct dentry``）**：代表内存中动态构建的树状文件路径命名空间（``d_name`` 短名内嵌优化 ``d_shortname``、``d_parent``、``d_children``、``d_hash`` 散列链、``d_lockref`` 锁与引用、正向/负向/白出目录项）；
     4. **打开文件描述符（``struct file``）**：代表进程视角下对文件的动态访问上下文（``f_pos`` 读写游标、``f_mode`` 访问权限、``f_op``、``f_mapping``、``f_path``、``f_ref`` 引用计数与 ``files_struct`` fdtable 数组映射）；
   * 逐级推导四大操作函数表（``super_operations``, ``inode_operations``, ``dentry_operations``, ``file_operations``）的函数指针多态分发流水线；
   * 穿透展示从进程 ``task_struct->files->fd_array[fd]`` 贯通到底层物理块设备的微观指针引力网。

----------------------------------------------------------------------------------------

第一幕：一切皆文件——VFS 统一抽象哲学与 C 语言多态架构
------------------------------------------------------

在 UNIX 与 Linux 的系统哲学中，“一切皆文件”（Everything is a file）是最具前瞻性的软件工程设计之一。普通文件、目录、字符设备（如终端 ``/dev/tty``）、块设备（如磁盘 ``/dev/sda``）、套接字（Socket）、匿名管道（Pipe）乃至内核自省接口（``/proc`` 与 ``/sys``），在用户态视角下均被抽象为统一的文件描述符（File Descriptor / ``fd``）。

1.1 异构存储的统一屏蔽层
~~~~~~~~~~~~~~~~~~~~~~~~
不同的底层介质与文件系统格式在物理结构上存在天壤之别：
* **ext4 / F2FS**：基于物理磁盘块组、Extent 树与元数据日志（JBD2）；
* **Btrfs / ZFS**：基于写时复制（COW）、B 树与子卷（Subvolumes）；
* **NFS / SMB**：跨越千兆/万兆以太网的远程网络协议 RPC 调用；
* **procfs / sysfs**：完全驻留在 RAM 中的内核数据结构动态视图。

VFS 在用户空间系统调用（``open``, ``read``, ``write``, ``close``）与具体文件系统驱动之间，构建了一层极度精密的面向对象抽象网：

::

   +-----------------------------------------------------------------------------------+
   |                             Linux VFS 多态分发全景架构                            |
   |                                                                                   |
   |  [用户空间应用程序] ──► open(), read(), write(), ioctl(), mmap(), close() 系统调用 |
   |                                │                                                  |
   |                                ▼                                                  |
   |  [VFS 虚拟文件系统抽象层] (include/linux/fs.h)                                    |
   |  ├── struct super_block ──► 驱动分发: struct super_operations                     |
   |  ├── struct inode       ──► 驱动分发: struct inode_operations                     |
   |  ├── struct dentry      ──► 驱动分发: struct dentry_operations                    |
   |  └── struct file        ──► 驱动分发: struct file_operations                      |
   |            │                                                                      |
   |            ├───────────────┬───────────────┬───────────────┬──────────────────────┤
   |            ▼               ▼               ▼               ▼                      ▼
   |     [ext4 驱动实现]  [Btrfs 驱动实现] [XFS 驱动实现]  [NFS 网络协议]  [字符/块设备驱动]
   |            │               │               │               │                      │
   |            ▼               ▼               ▼               ▼                      ▼
   |      (SATA/NVMe 磁盘)  (SSD 闪存介质)  (企业级 RAID)   (远程以太网服务器)      (物理芯片/总线)
   +-----------------------------------------------------------------------------------+

1.2 C 语言面向对象多态实现（Vtables）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Linux 内核完全使用纯 C 语言编写，其实现面向对象多态的核心机制是 **操作函数指针表（Operations Virtual Method Tables）**：
* 每一个 VFS 核心对象均内嵌一个指向操作方法表的指针（如 ``file->f_op`` 指向 ``struct file_operations``）；
* 当用户发起 ``read(fd, buf, len)`` 系统调用时，VFS 核心代码只需执行：
  
  .. code-block:: c

     file->f_op->read_iter(iocb, &iter);

* 硬件控制权将在几纳秒内瞬间多态路由至 ext4 的 ``ext4_file_read_iter()``、管道的 ``pipe_read()`` 或套接字的 ``sock_read_iter()``！

----------------------------------------------------------------------------------------

第二幕：超级块（``struct super_block``）——文件系统的全局物理元数据中枢
-----------------------------------------------------------------------

超级块（Superblock）代表一个已安装（Mounted）的文件系统实例，它在内存中精确描述了整个文件系统的全局参数与物理拓扑。

2.1 ``struct super_block`` 核心拓扑解构（``include/linux/fs/super_types.h``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   +-----------------------------------------------------------------------------------+
   |                        struct super_block 关键物理字段                            |
   |                                                                                   |
   |  struct super_block {                                                             |
   |      struct list_head        s_list;         /* 全局已挂载超级块双向链表 */       |
   |      dev_t                   s_dev;          /* 底层块设备号标识 */               |
   |      unsigned char           s_blocksize_bits; /* 块大小比特位移 (如 12 表示 4KB) */|
   |      unsigned long           s_blocksize;    /* 物理块字节大小 (如 4096 字节) */  |
   |      loff_t                  s_maxbytes;     /* 该文件系统支持的最大单文件长度 */ |
   |      struct file_system_type *s_type;        /* 归属的文件系统驱动类型 (如 ext4)*/|
   |      const struct super_operations *s_op;    /* 超级块操作函数指针表 */           |
   |      unsigned long           s_magic;        /* 文件系统物理魔数 (如 ext4 0xEF53)*/|
   |      struct dentry           *s_root;        /* 整个文件系统根目录的 Dentry 节点 */|
   |      struct rw_semaphore     s_umount;       /* 卸载与读写信号量 */               |
   |      int                     s_count;        /* 超级块引用计数 */                 |
   |      atomic_t                s_active;       /* 活跃挂载引用计数 */               |
   |      struct block_device     *s_bdev;        /* 指向底层块设备描述符 */           |
   |      struct sb_writers       s_writers;      /* 三级文件系统冻结锁状态机 */       |
   |      struct list_lru         s_dentry_lru;   /* 该 SB 下空闲 Dentry 内存回收链表*/|
   |      struct list_lru         s_inode_lru;    /* 该 SB 下空闲 Inode 内存回收链表 */|
   |      struct list_head        s_inodes;       /* 挂载在该 SB 下的所有活跃 Inode 链表*/
   |      spinlock_t              s_inode_list_lock; /* 保护 s_inodes 的自旋锁 */      |
   |      void                    *s_fs_info;     /* 文件系统私有物理超级块 (如 ext4_sb_info)*/
   |  };                                                                               |
   +-----------------------------------------------------------------------------------+

2.2 超级块操作方法表（``struct super_operations``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **``alloc_inode(sb)``**：由具体文件系统从专属 SLUB 缓存池中分配包含私有数据的 Inode 内存（如 ``ext4_alloc_inode``）；
* **``destroy_inode(inode)``**：释放 Inode 结构体；
* **``write_inode(inode, wbc)``**：将内存中脏 Inode 的元数据回写到磁盘物理扇区；
* **``evict_inode(inode)``**：当 Inode 彻底从内存移除且链接数归零时，释放其在磁盘上的全部物理数据块与 Inode 节点；
* **``sync_fs(sb, wait)``**：强制刷盘，将超级块、日志与脏数据同步至物理介质；
* **``statfs(dentry, kstatfs)``**：获取文件系统全局统计信息（总容量、剩余空间、空闲 Inode 数量等）。

2.3 三级冻结保护状态机（``struct sb_writers``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了在执行快照（LVM Snapshot）、热备份或在线检查时防止数据被破坏，Linux 7.2 内核为超级块设计了三级冻结屏障：
1. **``SB_FREEZE_WRITE``**：冻结普通用户态 ``write()``、目录修改与截断操作；
2. **``SB_FREEZE_PAGEFAULT``**：冻结通过 ``mmap()`` 共享内存映射产生的写缺页异常；
3. **``SB_FREEZE_FS``**：冻结文件系统内部守护线程与日志事务（JBD2）。

----------------------------------------------------------------------------------------

第三幕：索引节点（``struct inode``）——物理文件实体的真实化身
-------------------------------------------------------------

在 Linux 文件系统中，**文件名并不是文件的本质**。文件的唯一物理身份标识是 **索引节点（Inode / Index Node）**。

3.1 Inode 的物理本质与多重引用
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **独立于文件名**：Inode 存储了除文件名和真实数据内容之外的所有元数据（权限、所有者、物理磁盘块映射、时间戳、长度等）；
* **硬链接（Hard Links）机制**：一个物理 Inode 可以被目录树中的多个文件名同时指向（通过 ``inode->i_nlink`` 计数）。只有当所有硬链接都被删除（``i_nlink == 0``）且没有任何进程打开该文件（``i_count == 0``）时，物理磁盘空间才会被真正回收。

3.2 ``struct inode`` 核心字段拓扑（``include/linux/fs.h``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   +-----------------------------------------------------------------------------------+
   |                           struct inode 核心物理字段                               |
   |                                                                                   |
   |  struct inode {                                                                   |
   |      umode_t                 i_mode;         /* 文件类型与访问权限 (S_IFREG/S_IFDIR)*/
   |      kuid_t                  i_uid;          /* 文件所有者用户 ID */              |
   |      kgid_t                  i_gid;          /* 文件归属用户组 ID */              |
   |      const struct inode_operations *i_op;    /* Inode 级元数据操作函数指针表 */   |
   |      struct super_block      *i_sb;          /* 指向归属的超级块 */               |
   |      struct address_space    *i_mapping;     /* 指向该文件的 Page Cache 页缓存中枢*/
   |      u64                     i_ino;          /* 全局唯一 Inode 编号 (64 位整型) */|
   |      union {                                                                      |
   |          const unsigned int  i_nlink;        /* 物理硬链接计数 */                 |
   |          unsigned int        __i_nlink;                                           |
   |      };                                                                           |
   |      loff_t                  i_size;         /* 文件逻辑字节长度 (64 位有符号) */ |
   |      struct timespec64       i_atime;        /* 最后访问时间 (Access Time) */     |
   |      struct timespec64       i_mtime;        /* 最后数据修改时间 (Modify Time) */ |
   |      struct timespec64       i_ctime;        /* 最后元数据变更时间 (Change Time) */|
   |      spinlock_t              i_lock;         /* 保护 Inode 状态与计数的自旋锁 */  |
   |      struct rw_semaphore     i_rwsem;        /* 读写排他读写信号量 (文件写入锁) */|
   |      struct list_head        i_lru;          /* 挂载在 SB 的 Inode LRU 回收链表 */|
   |      struct hlist_node       i_hash;         /* 全局 Inode 哈希表节点 */          |
   |      struct hlist_head       i_dentry;       /* 指向引用该 Inode 的所有 Dentry 链表*/
   |      atomic_t                i_count;        /* 内存中正在使用该 Inode 的引用计数*/
   |      atomic_t                i_writecount;   /* 当前以写模式打开该文件的计数器 */ |
   |      union {                                                                      |
   |          const struct file_operations *i_fop;/* 默认内容读写操作方法表 */         |
   |          void (*free_inode)(struct inode *);                                      |
   |      };                                                                           |
   |      struct address_space    i_data;         /* 内嵌的默认 address_space 实体 */  |
   |      void                    *i_private;     /* 文件系统私有 Inode 结构体 (如 ext4_inode_info)*/
   |  };                                                                               |
   +-----------------------------------------------------------------------------------+

3.3 Inode 操作方法表（``struct inode_operations``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
负责处理路径分发与目录树结构变更（元数据层面）：
* **``lookup(dir, dentry, flags)``**：在父目录中查找指定名称的子节点，将物理 Inode 与该 Dentry 绑定（``d_splice_alias``）；
* **``create(idmap, dir, dentry, mode, excl)``**：在指定目录下创建普通文件；
* **``link(old_dentry, dir, new_dentry)``**：创建硬链接；
* **``unlink(dir, dentry)``**：删除硬链接，递减 ``i_nlink``；
* **``symlink(idmap, dir, dentry, symname)``**：创建符号软链接；
* **``mkdir(idmap, dir, dentry, mode)``**：创建子目录；
* **``rmdir(dir, dentry)``**：删除空目录；
* **``setattr(idmap, dentry, iattr)``**：修改文件属性（如 ``chmod``, ``chown``, ``truncate``）。

----------------------------------------------------------------------------------------

第四幕：目录项（``struct dentry``）——内存路径拓扑与 Dcache 加速引擎
-------------------------------------------------------------------

在物理磁盘上，目录本质上只是一种特殊的数据文件，里面保存着由 ``[文件名, Inode编号]`` 构成的键值表。如果每次路径解析（如查找 ``/usr/bin/gcc``）都要逐级读取磁盘数据块，系统 I/O 吞吐将彻底崩溃。

4.1 内存目录项缓存（Dentry Cache / Dcache）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了实现纳秒级的路径解析，VFS 在内存中构建了 **目录项（``struct dentry``）树状层级网**：
* **只存在于 RAM 中**：Dentry 在磁盘上没有直接对应的物理结构，完全是由内核在运行过程中动态生成的路径索引节点；
* **路径与 Inode 的粘合剂**：Dentry 将字符串路径名与底层物理 ``struct inode`` 强力锚定。

4.2 ``struct dentry`` 核心字段拓扑（``include/linux/dcache.h``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   +-----------------------------------------------------------------------------------+
   |                           struct dentry 核心内存布局                              |
   |                                                                                   |
   |  struct dentry {                                                                  |
   |      unsigned int            d_flags;        /* 状态标志位 (DCACHE_* 位图) */     |
   |      seqcount_spinlock_t     d_seq;          /* 无锁 RCU 路径查找顺序锁 (Seqlock)*/
   |      struct hlist_bl_node    d_hash;         /* 全局 Dcache 散列表节点 */         |
   |      struct dentry           *d_parent;      /* 指向父目录的 Dentry (根目录指向自身)*/
   |      struct qstr             d_name;         /* 目录项名称 (含 32 位 Hash 与长度) */|
   |      struct inode            *d_inode;       /* 关联的 Inode 实体 (NULL 表示负向目录项)*/
   |      union shortname_store   d_shortname;    /* 40 字节短文件名内嵌存储池 (免内存分配)*/
   |      const struct dentry_operations *d_op;   /* 目录项操作函数指针表 */           |
   |      struct super_block      *d_sb;          /* 归属的超级块 */                   |
   |      struct lockref          d_lockref;      /* 结合自旋锁与引用计数的无锁化原子结构*/
   |      struct list_head        d_lru;          /* 未使用 Dentry 的 LRU 回收链表 */  |
   |      struct hlist_node       d_sib;          /* 挂载在父目录子节点链表中的兄弟节点*/
   |      struct hlist_head       d_children;     /* 当前目录下所有子 Dentry 的链表头 */
   |      union {                                                                      |
   |          struct hlist_node   d_alias;        /* 挂载在 inode->i_dentry 上的别名节点*/
   |          struct rcu_head     d_rcu;          /* RCU 延迟释放节点 */               |
   |      };                                                                           |
   |  };                                                                               |
   +-----------------------------------------------------------------------------------+

4.3 短文件名内嵌优化（``d_shortname``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 64 位系统下，绝大多数文件名短于 40 字节。Linux 在 ``struct dentry`` 结构体内部直接开辟了 40 字节的内嵌数组 ``d_shortname.string``。当文件名小于 40 字节时，直接就地存储，**无需调用 SLUB 分配额外的字符串内存**，彻底消除了微小对象的内存碎片与寻址延迟！

4.4 目录项的三种生命状态
~~~~~~~~~~~~~~~~~~~~~~~~
1. **正向目录项（Positive Dentry）**：``d_inode != NULL``，成功与物理文件 Inode 绑定；
2. **负向目录项（Negative Dentry）**：``d_inode == NULL``，记录“该目录下绝对不存在这个文件”。当攻击者或程序高频查询不存在的文件时，内核直接在 Dcache 中瞬间命中并返回 ``-ENOENT``，**完全不需要下发磁盘 I/O 扫描盘块**！
3. **未使用目录项（Unused Dentry）**：引用计数 ``d_count == 0``，代表当前没有任何进程打开该路径，挂入 ``d_lru`` 链表，等待内存紧张时由 shrinker 回收。

----------------------------------------------------------------------------------------

第五幕：打开文件描述符（``struct file``）——进程视角的动态交互会话
-----------------------------------------------------------------

超级块、Inode 与 Dentry 描述的是文件系统的静态组织与物理实体。而 **``struct file`` 则代表一个进程与某个文件建立的动态交互会话（Open File Session）**。

5.1 进程独立会话隔离
~~~~~~~~~~~~~~~~~~~~
* 每次进程调用 ``open("/etc/passwd", O_RDONLY)``，内核都会在内存中动态分配一个全新的 ``struct file`` 实例；
* 如果两个独立进程同时打开了同一个文件，它们各自拥有独立的 ``struct file``（拥有各自独立的读写游标 ``f_pos``），但它们的 ``f_path.dentry`` 指向内存中唯一的那个 ``struct dentry``，并进一步指向唯一的物理 ``struct inode``！

5.2 ``struct file`` 核心字段拓扑（``include/linux/fs.h``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   +-----------------------------------------------------------------------------------+
   |                            struct file 核心内存布局                               |
   |                                                                                   |
   |  struct file {                                                                    |
   |      spinlock_t              f_lock;         /* 保护文件标志与状态的自旋锁 */     |
   |      fmode_t                 f_mode;         /* 访问模式 (FMODE_READ / FMODE_WRITE)*/
   |      const struct file_operations *f_op;     /* 文件级内容操作函数指针表 */       |
   |      struct address_space    *f_mapping;     /* 指向 inode->i_mapping 页缓存 */   |
   |      void                    *private_data;  /* 驱动或文件系统私有会话指针 */     |
   |      struct inode            *f_inode;       /* 直连的 Inode 缓存指针 */          |
   |      unsigned int            f_flags;        /* 打开标志位 (O_NONBLOCK/O_APPEND/O_DIRECT)*/
   |      const struct cred       *f_cred;        /* 打开该文件时的进程安全凭据凭证 */ |
   |      struct path             f_path;         /* 包含 vfsmount 挂载点与 dentry 路径*/
   |      struct mutex            f_pos_lock;     /* 读写游标并发保护互斥锁 */         |
   |      loff_t                  f_pos;          /* 当前文件读写字节偏移游标 (File Offset)*/
   |      file_ref_t              f_ref;          /* 原子引用计数 (由 dup/fork 共享) */|
   |  };                                                                               |
   +-----------------------------------------------------------------------------------+

5.3 文件操作方法表（``struct file_operations``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
负责处理文件内容的读写与设备控制：
* **``llseek(file, offset, whence)``**：移动文件读写游标 ``f_pos``；
* **``read_iter(iocb, iter)``**：高性能向量化异步读操作（Page Cache / Direct I/O）；
* **``write_iter(iocb, iter)``**：高性能向量化异步写操作；
* **``mmap(file, vma)``**：将文件物理页映射到进程用户态虚拟地址空间（VMA）；
* **``unlocked_ioctl(file, cmd, arg)``**：设备专用输入输出控制通道；
* **``fsync(file, start, end, datasync)``**：强制将该文件的脏数据与元数据刷写至磁盘介质；
* **``splice_read() / splice_write()``**：管道零拷贝数据泵通道；
* **``uring_cmd(ioucmd, issue_flags)``**：Linux 现代异步 I/O 引擎 ``io_uring`` 高速直连通道。

----------------------------------------------------------------------------------------

第六幕：穿透微观全景——从 ``task_struct->files`` 到物理磁盘扇区的指针引力网
---------------------------------------------------------------------------

当用户态代码执行 ``int fd = open("log.txt", O_RDWR); read(fd, buf, 1024);`` 时，操作系统内部展开了一条壮丽的指针跃迁链路：

::

   +-----------------------------------------------------------------------------------+
   |                     从进程描述符到物理磁盘扇区的全链路指针跃迁                    |
   |                                                                                   |
   |  [当前进程: current (struct task_struct)]                                         |
   |       │                                                                           |
   |       └──► files (struct files_struct) ──► 进程打开文件表总控                     |
   |                 │                                                                 |
   |                 └──► fdt (struct fdtable)                                         |
   |                           │                                                       |
   |                           └──► fd_array[fd] (根据整型 fd 索引数组)                |
   |                                     │                                             |
   |  ┌──────────────────────────────────┘                                             |
   |  ▼                                                                                |
   |  [动态打开文件: struct file]                                                      |
   |  ├── f_pos: 0x2000 (当前读写游标)                                                 |
   |  ├── f_op  ──► ext4_file_operations (分发 read_iter/write_iter)                   |
   |  └── f_path.dentry                                                                |
   |            │                                                                      |
   |            ▼                                                                      |
   |  [内存路径节点: struct dentry]                                                    |
   |  ├── d_name: "log.txt" (文件名)                                                   |
   |  ├── d_parent ──► 指向父目录 Dentry                                               |
   |  └── d_inode                                                                      |
   |            │                                                                      |
   |            ▼                                                                      |
   |  [物理文件实体: struct inode]                                                     |
   |  ├── i_ino: 1048577 (物理 Inode 号)                                               |
   |  ├── i_size: 40960 (文件总大小)                                                   |
   |  ├── i_mapping ──► struct address_space (Page Cache 缓存管理树)                   |
   |  └── i_sb                                                                         |
   |            │                                                                      |
   |            ▼                                                                      |
   |  [挂载超级块: struct super_block]                                                 |
   |  ├── s_blocksize: 4096 (物理块大小)                                               |
   |  ├── s_op ──► ext4_sops (超级块操作表)                                            |
   |  └── s_bdev                                                                       |
   |            │                                                                      |
   |            ▼                                                                      |
   |  [底层块设备: struct block_device (/dev/nvme0n1p1)] ──► 物理存储介质扇区!         |
   +-----------------------------------------------------------------------------------+

.. table:: VFS 四大核心对象属性与生命周期对比矩阵
   :widths: 15 20 20 20 25

   +======================+======================+======================+======================+==========================================+
   | VFS 对象             | 存储介质与位置       | 核心管理职责         | 生命周期             | 关键操作方法表                           |
   +======================+======================+======================+======================+==========================================+
   | **super_block**      | 内存 (对应磁盘超级块)| 全局文件系统元数据   | 挂载 (Mount) 到卸载  | ``struct super_operations``              |
   +----------------------+----------------------+----------------------+----------------------+------------------------------------------+
   | **inode**            | 内存 (对应磁盘 Inode)| 物理文件唯一实体元数据| 首个打开至彻底析构   | ``struct inode_operations``              |
   +----------------------+----------------------+----------------------+----------------------+------------------------------------------+
   | **dentry**           | 仅驻留内存 (RAM)     | 树状路径拓扑与高速缓存| 动态建立至 LRU 驱逐  | ``struct dentry_operations``             |
   +----------------------+----------------------+----------------------+----------------------+------------------------------------------+
   | **file**             | 仅驻留内存 (RAM)     | 进程访问会话与读写游标| ``open()`` 至 ``close()`` | ``struct file_operations``               |
   +----------------------+----------------------+----------------------+----------------------+------------------------------------------+

----------------------------------------------------------------------------------------

小结与下章导读
--------------

本节深入解构了 Linux 7.2 虚拟文件系统（VFS）的面向对象多态架构、四大核心元数据对象（``super_block``, ``inode``, ``dentry``, ``file``）的物理内存拓扑、操作函数指针分发模型、三级冻结保护状态机、短文件名内嵌优化，以及从进程描述符 ``task_struct`` 穿透至底层块设备的完整指针引力网。

VFS 构建了优雅的抽象网，但在海量文件与深层目录结构中，如何实现极速的路径检索？例如，当系统解析 ``/var/log/nginx/access.log`` 时，内核如何避免全量遍历磁盘，如何在完全不加锁的高并发状态下实现无锁路径解析？

在 **第 2 节：路径查找与目录项缓存 (Dcache)：RCU 无锁并发路径遍历与哈希快速查找** 中，我们将深入剖析 Dcache 散列表拓扑、RCU-walk 无锁路径遍历算法、``namei.c`` 逐级状态机跃迁，以及从 RCU-walk 优雅回退至 Ref-walk 的深层物理时序。
