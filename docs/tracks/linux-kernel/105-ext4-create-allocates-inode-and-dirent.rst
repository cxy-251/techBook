第一百零五章：ext4_create() 怎样分配 inode 并把 demo.txt 写进目录？
================================================================================

第一百零四章结束时，VFS持有 ``/work`` directory inode lock和mount write hold，``/work/demo.txt`` 是经过ext4 lookup确认的negative dentry。现在进入：

.. code-block:: c

   ext4_create(idmap, dir, dentry, S_IFREG | 0644, true);

固定条件补充如下：

* ext4启用journal，使用 ``data=ordered``；
* mount不是 ``sync``，``/work`` inode没有 ``S_DIRSYNC``；
* quota、fscrypt、casefold、default POSIX ACL和security xattr创建分支均不改变本场景；
* inode bitmap、group descriptor、目标inode-table block和``/work`` directory block均已在cache；
* parent directory block中有足够rec_len空间，不需要扩目录、分裂block或创建htree；
* 选择到的inode bitmap bit空闲；
* 不发生ENOSPC、journal abort、checksum error、allocation race或metadata I/O error。

本章中的“创建成功”首先指内核namespace与journal transaction中的metadata已经建立。它不等于metadata已经落到稳定存储。

``ext4_create`` 为什么先计算 journal credits
-------------------------------------------

``ext4_create()`` 先初始化directory quota state，然后计算一次create可能修改的metadata数量：

.. code-block:: text

   inode bitmap
   group descriptor
   new inode table record
   parent directory inode
   parent directory data block
   possible xattr/ACL metadata
   fast-commit tracking metadata

随后调用：

.. code-block:: c

   ext4_new_inode_start_handle(idmap, dir, mode,
                               &dentry->d_name,
                               0, NULL, EXT4_HT_DIR, credits);

这个helper把“分配inode”和“若当前没有handle则启动JBD2 transaction”组合起来。固定场景建立一个 ``handle_t``，并从当前running transaction预留足够credits。

journal handle是什么
--------------------

``handle_t`` 不是磁盘上的journal block，也不是独立transaction。它是当前task参与JBD2 transaction的修改额度与上下文：

.. code-block:: text

   current task
   → handle_t
   → running jbd2 transaction
   → metadata buffers attached to transaction

后面的bitmap、group descriptor、inode record和directory block修改都先通过 ``ext4_journal_get_write_access()`` 告诉JBD2，再通过 ``ext4_handle_dirty_metadata()`` 或专用dirty helper登记。

``new_inode`` 先建立内存 VFS inode
--------------------------------

``__ext4_new_inode()`` 首先调用：

.. code-block:: c

   inode = new_inode(sb);

这会分配并初始化内存中的：

.. code-block:: text

   struct inode
   + embedded struct ext4_inode_info

接着 ``inode_init_owner()`` 根据current fsuid/fsgid、parent setgid规则与mode初始化：

.. code-block:: text

   type       = regular file
   permission = 0644
   uid/gid    = current identity / inherited directory rules
   nlink      = 1
   size       = 0

此时还没有分配filesystem inode number，也没有在directory中出现名字。

ext4 怎样选择 inode group
-------------------------

普通非directory inode走：

.. code-block:: c

   find_group_other(sb, dir, &group, mode);

选择策略从parent directory所在group或其邻近group寻找free inode，兼顾flex group与allocation locality。固定场景选中一个已有空闲inode的group。

随后：

.. code-block:: text

   ext4_get_group_desc
   → ext4_read_inode_bitmap
   → find_inode_bit

这些metadata buffer都cache hit，没有READ bio。

bitmap bit怎样被原子占用
-----------------------

在修改inode bitmap前，ext4调用：

.. code-block:: c

   ext4_journal_get_write_access(handle, sb, inode_bitmap_bh,
                                 EXT4_JTR_NONE);

然后在per-group lock下：

.. code-block:: c

   ext4_test_and_set_bit(ino, inode_bitmap_bh->b_data);

固定bit原本为0，因此当前create成功占用它。锁保证同一group中的并发inode allocator不会分配相同bit。

占用后：

.. code-block:: text

   inode bitmap buffer → journal dirty metadata
   group free-inode count → decrement
   flex-group free-inode counter → decrement
   superblock percpu free-inode counter → decrement

若metadata checksum启用，inode bitmap checksum与group descriptor checksum也同步更新。

inode number与 ext4 私有字段怎样建立
------------------------------------

relative bitmap bit与group number组合成全局inode number：

.. code-block:: c

   inode->i_ino = ino + group * EXT4_INODES_PER_GROUP(sb);

随后初始化：

.. code-block:: text

   i_blocks          = 0
   i_size            = 0
   i_mtime/i_ctime   = current time
   i_crtime          = current time
   i_generation      = random generation
   ext4 i_data       = zero
   i_disksize        = 0
   block group       = selected group
   extent flag       = enabled
   empty extent tree = initialized

新regular file此刻没有data block。分配inode不等于为文件内容预分配一个filesystem block。

``insert_inode_locked()`` 把新inode加入VFS inode hash，同时保留 ``I_NEW`` 状态，防止其他lookup在初始化完成前观察半成品。

inode-table record怎样进入journal
--------------------------------

ext4完成quota/security/ACL初始化后调用：

.. code-block:: c

   ext4_mark_inode_dirty(handle, inode);

这会把内存inode转换为on-disk ``struct ext4_inode`` 格式，取得对应inode-table buffer的journal write access，并登记为dirty metadata。固定inode-table buffer已在cache，所以不需要读盘。

到这里，transaction已经包含：

.. code-block:: text

   inode bitmap bit = allocated
   group descriptor free count = updated
   new inode-table record = initialized

directory中仍然没有 ``demo.txt`` dirent，因此创建还不能对pathname lookup可见。

``ext4_add_nondir`` 怎样加入名字
--------------------------------

``ext4_create()`` 为新inode安装：

.. code-block:: text

   inode->i_op  = ext4_file_inode_operations
   inode->i_fop = ext4_file_operations
   address_space operations = ext4 buffered-file aops

然后调用：

.. code-block:: c

   ext4_add_nondir(handle, dentry, &inode);

其核心是：

.. code-block:: c

   ext4_add_entry(handle, dentry, inode);

固定 ``/work`` 是一个非indexed 4 KiB directory，已有buffer中存在足够slack。``__ext4_add_entry()``：

#. 把``demo.txt``编码为ext4 filename；
#. 读取已缓存directory block；
#. 在现有dirent链中查找可容纳新记录的 ``rec_len``；
#. 取得该directory block的journal write access；
#. 缩短旧dirent的 ``rec_len``；
#. 在释放出的空间写入新dirent。

新dirent包含：

.. code-block:: text

   inode    = newly allocated inode number
   rec_len  = aligned record length / remaining space
   name_len = 8
   file_type= EXT4_FT_REG_FILE
   name     = "demo.txt"

若metadata checksum启用，directory block tail checksum随修改重新计算。

parent directory哪些字段变化
-----------------------------

加入dirent后，ext4更新：

.. code-block:: text

   directory i_version
   directory mtime
   directory ctime
   parent directory inode metadata
   directory data block metadata

``ext4_handle_dirty_dirblock()`` 把directory block登记进当前transaction；``ext4_mark_inode_dirty(handle, dir)`` 把parent inode更新也登记进去。

这里没有为new file分配data block；被修改的4 KiB block是 **parent directory的数据块**，承载pathname到inode number的映射。

negative dentry什么时候变成 positive
------------------------------------

``ext4_add_nondir()`` 在dirent与new inode metadata都准备好后调用：

.. code-block:: c

   d_instantiate_new(dentry, inode);

状态变化：

.. code-block:: text

   before: dentry->d_inode = NULL
   after : dentry->d_inode = new inode

``d_instantiate_new()`` 还结束new inode的 ``I_NEW`` 初始化状态，使后续lookup能够安全取得它。

从这一刻起，namespace中：

.. code-block:: text

   /work/demo.txt → new ext4 inode

已经对并发VFS lookup可见。inode reference被dentry实例化消费，``ext4_add_nondir()`` 把caller的inode pointer清为NULL，避免重复 ``iput``。

fast commit tracking记录了什么
-------------------------------

create成功后：

.. code-block:: c

   ext4_fc_track_create(handle, dentry);

这让启用ext4 fast commit时，后续需要同步transaction可以用create record表示本次namespace变化。它不在当前 ``openat`` 中自动执行fast commit。

``ext4_journal_stop`` 是否已经持久化文件
---------------------------------------

``ext4_create()`` 最后调用：

.. code-block:: c

   ext4_journal_stop(handle);

它结束当前task对transaction的handle，归还未用credits，并允许transaction按JBD2策略继续运行或之后提交。

固定场景没有：

* ``O_SYNC``；
* synchronous mount；
* ``S_DIRSYNC`` parent；
* 显式 ``fsync``；
* journal error。

因此 ``ext4_journal_stop()`` 成功返回不要求等待commit record、cache flush或home-block checkpoint。

当前语义是：

.. code-block:: text

   VFS namespace visible = yes
   journal transaction contains metadata = yes
   metadata transaction committed = not guaranteed yet
   metadata checkpointed to home blocks = no requirement
   power-loss durability = not guaranteed by openat return

当前精确边界
------------

``ext4_create()`` 已返回0，控制权回到 ``lookup_open()``，但新 ``struct file`` 还未完成 ``vfs_open()``。

当前状态：

* current task：parent，CPL 0；
* parent directory inode lock：仍held；
* mount write hold：仍held；
* fd 6：reserved，fd pointer仍NULL；
* target dentry：positive；
* new inode：regular 0644，size 0，nlink 1；
* new inode data blocks：0；
* directory dirent：已加入cached ``/work`` block；
* inode bitmap/group descriptor/inode table/directory block：已在JBD2 transaction中标脏；
* ext4 create handle：已stopped；
* journal commit：未强制等待；
* storage I/O：没有发生；
* ``struct file``：尚未 ``FMODE_OPENED``；
* next entry：``do_open()`` 与 ``vfs_open()``。

关键边界
--------

#. ext4创建regular file首先分配inode，不会自动分配file data block。
#. bitmap/group descriptor/inode table/directory block属于同一metadata transaction。
#. directory block保存name到inode number的映射。
#. ``d_instantiate_new`` 是negative dentry变positive的内存可见边界。
#. journal handle结束不等于transaction已经durable。
#. pathname立即可见与crash后仍存在是两个不同保证。

资料
----

* `Linux 7.2-rc1 fs/ext4/namei.c：ext4_create、ext4_add_nondir 与 ext4_add_entry <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/namei.c>`_
* `Linux 7.2-rc1 fs/ext4/ialloc.c：__ext4_new_inode 与inode bitmap分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/ialloc.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c：ext4_mark_inode_dirty 与inode-table update <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 fs/jbd2/transaction.c：journal handle与metadata access <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/jbd2/transaction.c>`_
