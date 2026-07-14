第一百零四章：openat() 怎样保留 fd 并把 /work/demo.txt 解析成 negative dentry？
====================================================================================

上一场景结束后，parent 已经通过 ``wait4()`` 回收 child，并回到用户态。本章开始一个独立的 VFS create-open 场景：

.. code-block:: c

   int fd = openat(AT_FDCWD, "/work/demo.txt",
                   O_CREAT | O_EXCL | O_WRONLY, 0644);

固定条件：

* current 是上一场景中的 parent，单线程、native x86-64；
* fd 0 到 5 已占用，最低空闲 descriptor 是 6；
* 没有传入 ``O_CLOEXEC``；
* process umask 是 ``0022``；
* ``/work`` 位于 ``/dev/sda1`` 的 ext4，mode 0755，由 current uid 所有；
* mount 可写、非 idmapped，目录不是 sticky、encrypted、casefold 或 inline-data directory；
* ``/`` 与 ``/work`` 的 mount、dentry、inode 已在 cache；
* ``demo.txt`` 在 dcache 中没有现成 dentry，在 ext4 directory block 中也不存在；
* ``/work`` 是单个 4 KiB、非 htree directory block，block 已在 buffer/page cache；
* 没有并发 rename/create/unlink、mount topology 变化、permission failure、LSM denial 或 allocation failure。

这一章先完成 pathname lookup，并把最后一个名字变成受 parent-directory lock 保护的 negative dentry。真正分配 ext4 inode 留到下一章。

系统调用怎样变成 ``open_flags``
--------------------------------

native x86-64 ``openat`` 的 syscall number 是 257。用户态进入 ``SYSCALL`` 时，主要参数是：

.. code-block:: text

   RDI = AT_FDCWD
   RSI = pointer to "/work/demo.txt"
   RDX = O_CREAT | O_EXCL | O_WRONLY
   R10 = 0644

控制流：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_openat
   → do_sys_open
   → do_sys_openat2

64 位 ``openat`` 自动加入 ``O_LARGEFILE``。``build_open_how()`` 与 ``build_open_flags()`` 把用户 flags 转换为内部 ``struct open_flags``：

.. code-block:: text

   open_flag   = O_WRONLY | O_CREAT | O_EXCL | O_LARGEFILE
   acc_mode    = MAY_WRITE
   intent      = LOOKUP_OPEN | LOOKUP_CREATE | LOOKUP_EXCL
   mode        = S_IFREG | 0644

``mode`` 只有在 create-like flags 存在时才有效。最终 mode 还要经过 parent directory、umask、ACL 与 filesystem 的创建流程；固定目录没有 default ACL，``0644 & ~0022`` 仍是 ``0644``。

为什么 pathname lookup 前已经保留 fd 6
--------------------------------------

``do_sys_openat2()`` 使用：

.. code-block:: c

   FD_ADD(how->flags, do_file_open(dfd, name, &op));

``FD_ADD`` 不是先打开文件再找 descriptor。它先调用：

.. code-block:: c

   get_unused_fd_flags(how->flags);

``alloc_fd()`` 在 ``current->files->file_lock`` 下：

#. 从 ``files->next_fd`` 与 ``open_fds`` bitmap 查找最低空位；
#. 选中 fd 6；
#. 在 ``open_fds`` 中把 bit 6 标记为占用；
#. 因为没有 ``O_CLOEXEC``，``close_on_exec`` bit 6 保持 clear；
#. 把 ``files->next_fd`` 推进到 7；
#. 确认 ``fdt->fd[6]`` 仍为 ``NULL``。

此时 fd 6 是 **reserved slot**：

.. code-block:: text

   open_fds[6] = 1
   fd[6]        = NULL

其他线程即使共享同一 ``files_struct``，也不能再次分配 fd 6。当前场景单线程，但这个顺序仍是 fd-table API 的并发语义。

如果后续 pathname lookup 或 ext4 create 失败，``fd_prepare`` cleanup 会调用 ``put_unused_fd(6)`` 清除 reservation。

``alloc_empty_file`` 创建的对象还没有 pathname
---------------------------------------------

fd reservation 成功后才计算 ``do_file_open()``。``path_openat()`` 首先调用：

.. code-block:: c

   alloc_empty_file(op->open_flag, current_cred());

得到新的 ``struct file``。此时它已有：

* open flags；
* current credentials reference；
* 初始 file mode；
* file refcount；

还没有：

* ``f_path``；
* ``f_inode``；
* ``f_mapping``；
* ext4 ``f_op``；
* ``FMODE_OPENED``。

``struct file`` 是一次 open file description。它和 fd 6 是不同对象：fd table稍后只保存指向该 ``struct file`` 的指针。

绝对路径为什么忽略 ``AT_FDCWD``
--------------------------------

``path_openat()`` 调用：

.. code-block:: text

   path_init
   → link_path_walk
   → open_last_lookups
   → do_open

pathname以 ``/`` 开头，所以 ``path_init()`` 从 current filesystem root 开始。``AT_FDCWD`` 只有相对路径时才决定起点；这里不会读取 current working directory。

当前 nameidata 的主要状态变成：

.. code-block:: text

   nd.path = process root path
   nd.name = "/work/demo.txt"
   lookup  = open/create/exclusive intent

``link_path_walk`` 只处理非最终分量
----------------------------------

``link_path_walk()`` 解析 ``work``，把最后的 ``demo.txt`` 留给 open-specific final-component logic。

固定 ``/`` 与 ``/work`` 已在 dcache，RCU-walk 可以完成：

.. code-block:: text

   d_lookup_rcu(root, "work")
   → validate sequence counters
   → follow_managed
   → check MAY_EXEC/search permission on /work
   → nd.path = /work
   → nd.last = "demo.txt"

没有 symlink、mount crossing、``..``、automount 或 revalidation。中间 pathname component 的“可访问”依赖 directory execute/search permission，不是读取文件内容的 read permission。

为什么 ``O_EXCL`` 不采用 final-component fast lookup
----------------------------------------------------

``open_last_lookups()`` 先调用：

.. code-block:: c

   lookup_fast_for_open(nd, open_flag);

对 ``O_CREAT | O_EXCL``，该函数直接返回 ``NULL``，因为 exclusive create 必须在 parent inode lock 下原子确认“名字不存在并创建”。单纯依赖一个无锁 negative-dentry cache hit 会破坏这一原子性。

当前仍可能处于 RCU-walk。创建路径需要锁和可睡眠操作，因此：

.. code-block:: text

   try_to_unlazy
   → 从 RCU-walk 切换到 ref-walk
   → 对当前 mount 取得 write hold
   → inode_lock(/work inode)

从这里直到 filesystem create完成，parent directory inode lock阻止同目录中冲突的 create/unlink/rename 修改最终名字。

``lookup_open`` 怎样构造 negative dentry
---------------------------------------

``lookup_open()`` 先查普通 dcache：

.. code-block:: c

   dentry = d_lookup(dir, &nd->last);

固定场景没有 ``demo.txt`` dentry，所以进入：

.. code-block:: c

   dentry = d_alloc_parallel(dir, &nd->last);

新 dentry 此时：

.. code-block:: text

   d_parent = /work dentry
   d_name   = "demo.txt"
   d_inode  = NULL
   state    = in-lookup

因为需要确认磁盘目录中也没有该名字，VFS调用 ``/work`` inode 的：

.. code-block:: c

   dir_inode->i_op->lookup
   → ext4_lookup(dir, dentry, flags)

``ext4_lookup()`` 进入：

.. code-block:: text

   ext4_lookup_entry
   → __ext4_find_entry
   → ext4_read_dirblock
   → search_dirblock

固定directory block已在cache，扫描结果是“没有 demo.txt”，所以没有READ bio或AHCI请求。``ext4_lookup()`` 最终执行等价于：

.. code-block:: c

   d_splice_alias(NULL, dentry);

lookup结束后 dentry从 ``in-lookup`` 变成可使用的 **negative dentry**：

.. code-block:: text

   /work/demo.txt dentry exists in memory
   dentry->d_inode = NULL
   ext4 directory contains no matching dirent

negative dentry不是错误对象。它是“这个 parent/name 组合当前不存在”的缓存表示，也是即将创建inode的挂接点。

创建权限在哪里确认
------------------

在调用 filesystem ``create`` 前，``lookup_open()`` 计算最终mode并调用create permission logic。固定路径通过：

* filesystem与mount可写；
* parent inode不是immutable/dead；
* current fsuid可映射到filesystem；
* current对 ``/work`` 有 ``MAY_WRITE | MAY_EXEC``；
* LSM ``security_inode_create`` 允许；
* target dentry仍为negative；
* ``O_EXCL`` 原子条件仍成立。

当前精确边界
------------

CPU即将调用：

.. code-block:: c

   dir_inode->i_op->create(idmap, dir_inode, dentry,
                           mode, true);

对ext4，该callback是 ``ext4_create()``。

当前状态：

* current task：parent；
* CPU mode：x86-64 CPL 0，openat syscall context；
* reserved fd：6；
* ``open_fds[6]``：set；
* ``fdt->fd[6]``：仍为 ``NULL``；
* close-on-exec bit 6：clear；
* new ``struct file``：已分配，尚未opened；
* pathname root与 ``/work``：cache hit；
* parent directory inode lock：held exclusive；
* mount write hold：held；
* target dentry：negative ``/work/demo.txt``；
* ext4 directory lookup：cache hit，确认不存在；
* target inode：尚未分配；
* journal handle：尚未创建；
* storage I/O：没有发生；
* next entry：``ext4_create()``。

关键边界
--------

#. ``FD_ADD`` 先reserve descriptor，再执行pathname open。
#. reserved fd slot的bitmap已经占用，但pointer仍是NULL。
#. 绝对路径不使用 ``AT_FDCWD`` 作为lookup起点。
#. pathname walk把中间component与最后component分开处理。
#. ``O_EXCL`` final lookup必须退出RCU-walk并持有parent inode lock。
#. negative dentry表示“名字已查证不存在”，不是一个失败返回值。
#. cached directory lookup不等于dentry cache hit；ext4仍扫描了cached directory block。

资料
----

* `Linux 7.2-rc1 fs/open.c：openat、do_sys_openat2 与 build_open_flags <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 include/linux/file.h：FD_ADD、fd_prepare 与 fd_publish <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/file.h>`_
* `Linux 7.2-rc1 fs/file.c：alloc_fd 与 reserved fd slot <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/namei.c：path_openat、open_last_lookups 与 lookup_open <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/namei.c>`_
* `Linux 7.2-rc1 fs/ext4/namei.c：ext4_lookup 与 directory entry search <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/namei.c>`_
