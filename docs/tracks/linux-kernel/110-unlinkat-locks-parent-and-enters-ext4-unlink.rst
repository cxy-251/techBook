第一百一十章：unlinkat() 怎样锁住父目录并进入 ext4_unlink()？
=======================================================================

上一场景结束时，parent 在 CPL 3 持有：

.. code-block:: text

   fd 6 → write-only struct file
        → /work/demo.txt
        → ext4 inode: nlink=1, size=4096
        → logical block 0 → physical block P, written

本章固定执行：

.. code-block:: c

   unlinkat(AT_FDCWD, "/work/demo.txt", 0);

固定条件：

* pathname 是绝对路径，``AT_FDCWD`` 不参与起点选择；
* ``/work``、``demo.txt`` 的 dentry/inode 与目录数据块均在 cache；
* target 是普通文件，不是 directory、swapfile、mountpoint、immutable 或 append-only inode；
* 当前凭据对 ``/work`` 有 write+execute 权限；
* ``/work`` 不是 sticky directory；
* 没有 delegation、lease、LSM 拒绝、rename/unlink/create race；
* target 只有一个硬链接；
* 除 fd 6 外，没有其他 open file、dup、mmap、cwd/root 或 handle reference；
* fast commit、quota、encryption、casefold 与 bigalloc 均关闭；
* metadata buffers 已缓存，当前 syscall 内不发生设备 I/O；
* 所有 allocation 与 journal 操作成功。

系统调用入口如何区分 unlink 与 rmdir
------------------------------------

native x86-64 ``unlinkat`` 进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_unlinkat
   → filename_unlinkat

``SYSCALL_DEFINE3(unlinkat)`` 首先检查 flag：

.. code-block:: c

   if ((flag & ~AT_REMOVEDIR) != 0)
       return -EINVAL;

固定 ``flag=0``，所以不会进入 ``filename_rmdir()``，而是调用：

.. code-block:: c

   filename_unlinkat(AT_FDCWD, name);

此时 current 仍是 parent，CPU 位于 CPL 0 的 syscall process context。fd 6 没有被查找或修改；unlink 操作使用 pathname，而不是 open file description。

为什么先解析 parent 而不是完整 target path
------------------------------------------

``filename_unlinkat()`` 调用：

.. code-block:: c

   filename_parentat(dfd, name, lookup_flags,
                     &path, &last, &type);

结果拆成：

.. code-block:: text

   path → parent /work
   last → "demo.txt"
   type → LAST_NORM

删除最后一个 component 必须在 parent directory lock 下重新确认。若先完成无锁的完整路径解析，再晚些删除，另一个线程可能在两者之间 rename 或替换 target。

固定 pathname 是绝对路径，因此 lookup 从 process root 开始，沿 cached ``/`` 与 ``/work`` 到达 parent；没有 ext4 directory READ。

mount write hold 保护什么
-------------------------

在修改 namespace 前：

.. code-block:: c

   mnt_want_write(path.mnt);

它取得 mount write hold，防止 filesystem 在操作中间切换到 read-only 或 freeze 完成。这个引用不等于 inode write access，也不分配 journal transaction；它保护的是整个 mount 上即将发生的 metadata mutation。

``start_dirop`` 怎样建立原子删除窗口
-----------------------------------

``filename_unlinkat()`` 随后调用：

.. code-block:: c

   dentry = start_dirop(path.dentry, &last, lookup_flags);

固定路径中，它完成两个关键动作：

#. 独占取得 ``/work`` inode 的 ``i_rwsem``；
#. 在锁内 lookup ``demo.txt``，得到 cached positive dentry。

锁内状态是：

.. code-block:: text

   parent inode /work  = exclusively locked
   target dentry       = positive
   target inode        = original demo.txt inode
   target nlink        = 1

此后同一 parent 下的 create、unlink 与 rename 不能越过当前删除窗口改变这个 name-to-inode 关系。

为什么额外执行 ``ihold(inode)``
-------------------------------

取得 target 后，代码执行：

.. code-block:: c

   inode = dentry->d_inode;
   ihold(inode);

这个临时 inode reference 保证后续在释放 parent directory lock 后仍能安全调用 ``iput(inode)``。源码注释明确要求：可能耗时的 final truncation 不应发生在 parent ``i_rwsem`` 内，否则删除大文件会长期阻塞整个目录。

当前文件还有 fd 6 引用，因此本次临时 ``iput`` 最终不会触发 eviction；它仍然保持了通用 VFS 删除路径需要的生命周期边界。

VFS 删除前检查了什么
--------------------

``security_path_unlink()`` 通过后进入：

.. code-block:: c

   vfs_unlink(mnt_idmap(path.mnt),
              path.dentry->d_inode,
              dentry,
              &delegated_inode);

``vfs_unlink()`` 首先通过 ``may_delete_dentry()`` 检查：

* parent write+execute permission；
* sticky-directory 规则；
* target 是否存在；
* target 不是 directory；
* inode/mount id mapping 合法；
* append-only、immutable 等删除限制。

固定检查全部通过，且 ``/work`` 的 inode operations 提供 ``unlink`` callback。

为什么 VFS 还要锁 target inode
------------------------------

parent lock保护目录中的 name mapping；target inode lock保护被删除对象自身状态。``vfs_unlink()`` 执行：

.. code-block:: c

   inode_lock(target);

然后排除：

.. code-block:: text

   swapfile
   local mountpoint
   security rejection
   directory deletion lease/delegation
   target lease/delegation

固定没有 delegation，因此不会释放锁后等待再重试。

最终 dispatch 是：

.. code-block:: text

   dir->i_op->unlink(dir, dentry)
   → ext4_unlink(/work inode, demo.txt dentry)

当前精确边界
------------

CPU 即将进入 ``ext4_unlink()``：

* current executor：parent；
* CPU mode：x86-64 CPL 0；
* syscall：``unlinkat(AT_FDCWD, "/work/demo.txt", 0)``；
* mount write hold：held；
* ``/work`` inode ``i_rwsem``：exclusive held；
* target inode ``i_rwsem``：exclusive held；
* target dentry：cached positive；
* target inode：nlink 1、size 4096、written extent P；
* fd 6：仍在 fdtable 中，仍指向原 ``struct file``；
* target temporary ``ihold``：held；
* JBD2 handle：尚未建立；
* directory entry：仍存在；
* orphan tracking：尚未加入；
* physical block P：仍分配给该 inode；
* pathname：仍可解析；
* storage I/O：未发生。

关键边界
--------

#. unlink 使用 pathname，不使用 fd 6。
#. absolute pathname 使 ``AT_FDCWD`` 与 lookup 起点无关。
#. namespace mutation 需要 mount write hold。
#. 删除最后一个 component 必须在 parent inode lock 内重新 lookup。
#. parent lock保护 name mapping，target lock保护 victim inode状态。
#. ``ihold`` 允许潜在 final eviction 延后到 directory lock 释放之后。
#. 进入 ``ext4_unlink`` 时，目录项、nlink、orphan和extent均尚未改变。

资料
----

* `Linux 7.2-rc1 fs/namei.c：unlinkat、filename_unlinkat 与 vfs_unlink <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/namei.c>`_
* `Linux 7.2-rc1 fs/ext4/namei.c：ext4_unlink callback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/namei.c>`_
