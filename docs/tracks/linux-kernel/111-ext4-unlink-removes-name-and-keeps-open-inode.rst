第一百一十一章：ext4_unlink() 怎样删除名称，却让 fd 6 继续访问 inode？
================================================================================

第一百一十章结束时，parent 正在 ``unlinkat()`` 的内核路径中：

.. code-block:: text

   /work inode lock   = held exclusive
   demo.txt inode lock= held exclusive
   dentry             = positive
   nlink              = 1
   fd 6               = open
   extent             = logical 0 → physical P, written

本章追踪 ext4 如何移除 directory entry、把 ``i_nlink`` 降为0并加入 orphan tracking，同时保留 open file description、page cache与extent。

``ext4_unlink`` 为什么先初始化 quota
-----------------------------------

VFS dispatch 到：

.. code-block:: c

   ext4_unlink(dir, dentry);

函数先检查 filesystem 没有 forced shutdown，再调用：

.. code-block:: text

   dquot_initialize(dir)
   dquot_initialize(target)

固定场景关闭quota，因此不会读quota文件或产生quota transaction，随后进入：

.. code-block:: c

   __ext4_unlink(dir, &dentry->d_name,
                 d_inode(dentry), dentry);

为什么还要扫描一次目录块
------------------------

即使VFS已经有positive dentry，ext4仍必须定位磁盘格式中的 ``ext4_dir_entry_2``：

.. code-block:: c

   ext4_find_entry(dir, "demo.txt", &de, NULL);

固定 ``/work`` 只有一个已缓存的4 KiB非htree directory block，因此：

.. code-block:: text

   directory folio/buffer cache hit
   → verify dirent checksum/layout
   → find de->inode == target inode number

VFS dentry是内存name cache；ext4 dirent才是filesystem metadata中需要被journal修改的记录。删除前必须确认两者仍指向同一inode number。

JBD2 transaction覆盖哪些metadata
---------------------------------

``__ext4_unlink()`` 建立：

.. code-block:: c

   ext4_journal_start(dir, EXT4_HT_DIR,
                      EXT4_DATA_TRANS_BLOCKS(sb));

固定parent不是 ``S_DIRSYNC``，handle不标记同步。transaction将覆盖：

* ``/work`` directory block；
* ``/work`` inode的mtime/ctime等metadata；
* target inode的nlink、ctime与orphan字段；
* orphan tracking所需的orphan file或legacy orphan链metadata。

这不是data transaction。文件的4096-byte数据已经clean且durable，本次unlink不会重写physical block P中的data。

``ext4_delete_entry`` 怎样移除 name
----------------------------------

核心调用是：

.. code-block:: c

   ext4_delete_entry(handle, dir, de, bh);

对于固定线性目录块，它取得journal write access，然后把 ``demo.txt`` 的目录空间并回前一个dirent的 ``rec_len``，或清除首项inode字段，再重新计算directory block checksum并标记buffer为journal dirty。

删除后，磁盘格式的有效entry集合中不再包含：

.. code-block:: text

   name="demo.txt", inode=<target ino>

随后更新parent：

.. code-block:: text

   dir mtime = now
   dir ctime = now
   ext4_update_dx_flag(dir)
   ext4_mark_inode_dirty(handle, dir)

固定目录不是htree，``ext4_update_dx_flag`` 不引出额外index操作。

``drop_nlink`` 为什么还不释放 inode
----------------------------------

原inode只有一个hard link：

.. code-block:: text

   inode->i_nlink: 1 → 0

``i_nlink=0`` 表示没有任何namespace name指向这个inode；它不表示没有内存引用，也不表示block已经释放。

当前仍存在：

.. code-block:: text

   fdtable[6]
   → struct file
   → f_path.dentry
   → target inode

因此target仍是一个可用的open file。通过fd 6仍可执行 ``write``、``fsync``、``fstat`` 等操作；本场景不执行这些额外调用。

orphan tracking解决什么崩溃窗口
-------------------------------

当 ``i_nlink`` 变成0时，ext4调用：

.. code-block:: c

   ext4_orphan_add(handle, inode);

此时inode还不能被删除，因为fd 6仍打开。若系统在final close之前崩溃，重启后的普通pathname无法找到它，也没有用户进程继续持有fd。orphan tracking使ext4 mount recovery能够找到这个nlink-zero inode并完成truncate与释放。

固定filesystem支持orphan file时优先记录到orphan file；否则使用superblock/legacy orphan链。两种实现都表达同一状态：

.. code-block:: text

   namespace unreachable
   + inode/resources still allocated
   + recovery must finish deletion

``ext4_mark_inode_dirty`` 保存哪些状态
-------------------------------------

ext4设置target ctime并执行：

.. code-block:: c

   ext4_mark_inode_dirty(handle, inode);

journal中的inode record至少反映：

.. code-block:: text

   i_links_count = 0
   ctime         = unlink time
   size          = 4096
   blocks        = 8 sectors
   extent        = logical 0 → P
   orphan state  = active

size和extent现在故意保留。它们要等最后open reference消失后，由 ``ext4_evict_inode()`` 释放。

transaction stop不等于durable
-----------------------------

``ext4_journal_stop(handle)`` 结束当前handle。固定没有 ``S_DIRSYNC``、没有随后对parent directory执行 ``fsync``、也没有 ``syncfs``，所以unlink成功返回时不保证：

.. code-block:: text

   unlink transaction committed          = no guarantee
   journal commit record on stable media = no guarantee
   directory home block checkpointed     = no guarantee

内核运行状态中的namespace变化已经成功；power-loss durability仍取决于后续JBD2 commit。

VFS 怎样让新 lookup 看不到旧 dentry
-----------------------------------

返回 ``vfs_unlink()`` 后，VFS：

.. code-block:: text

   unlock target inode
   → fsnotify_link_count
   → d_delete_notify

由于fd 6的 ``struct file`` 仍持有dentry reference，VFS不需要立刻销毁dentry对象。它把该name/inode关联从正常dcache lookup中摘除；固定场景中open file仍可通过 ``f_path`` 持有这个unhashed dentry与inode。

随后：

.. code-block:: text

   end_dirop(dentry)
   → release /work inode lock
   → iput(temporary ihold)
   → mnt_drop_write
   → path_put(parent)

临时 ``iput`` 不会触发eviction，因为fd 6路径引用仍然存在。

``unlinkat`` 返回后的精确状态
----------------------------

syscall exit回到parent CPL 3，返回值为0：

* pathname ``/work/demo.txt``：不再解析到target；
* parent directory entry：已从运行中namespace移除；
* fd 6：仍published、write-only、``f_pos=4096``；
* ``struct file``：仍存在，file reference count为1；
* target dentry：open file持有，已从normal name lookup摘除；
* target inode：``i_nlink=0``、``i_size=4096``；
* ``i_disksize``：4096；
* extent：logical block 0 → P，仍为written；
* ``i_blocks``：8个512-byte sectors；
* page-cache folio：仍uptodate、clean；
* orphan tracking：active；
* inode eviction：尚未发生；
* block bitmap：P仍allocated；
* inode bitmap：target inode bit仍allocated；
* unlink metadata：已加入JBD2 transaction；
* transaction commit/durability：尚未强制；
* storage I/O：固定syscall路径中未发生。

关键边界
--------

#. VFS dentry与ext4 directory entry是不同层的对象。
#. ``ext4_delete_entry`` 删除name，不删除open file description。
#. ``i_nlink=0`` 表示namespace无链接，不表示inode无引用。
#. open fd使size、extent、page cache和inode继续存活。
#. orphan tracking保护“已unlink但仍open”的崩溃窗口。
#. ``d_delete_notify`` 让新pathname lookup看不到target，同时允许open file保留dentry引用。
#. ``unlinkat`` 成功不保证删除metadata已经durable。
#. physical block P与inode bitmap bit都要等final close后的eviction才开始释放。

资料
----

* `Linux 7.2-rc1 fs/ext4/namei.c：ext4_unlink、ext4_delete_entry、drop_nlink与orphan add <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/namei.c>`_
* `Linux 7.2-rc1 fs/namei.c：vfs_unlink、d_delete_notify与directory-lock release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/namei.c>`_
* `Linux 7.2-rc1 fs/ext4/orphan.c：ext4 orphan tracking与recovery <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/orphan.c>`_
