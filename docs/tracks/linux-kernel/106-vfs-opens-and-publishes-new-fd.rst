第一百零六章：VFS 怎样打开新 inode、发布 fd 6 并让 openat() 返回？
================================================================================

第一百零五章结束时，``/work/demo.txt`` 已有positive dentry与size-0 ext4 inode；create metadata已进入JBD2 transaction。fd 6仍只是reserved slot，新 ``struct file`` 还没有绑定inode。

本章完成：

.. code-block:: text

   lookup_open returns positive dentry
   → do_open
   → vfs_open / do_dentry_open
   → ext4_file_open
   → path_openat returns struct file
   → fd_install(6, file)
   → openat returns 6 to userspace

parent directory lock何时释放
----------------------------

``lookup_open()`` 返回positive dentry后，``open_last_lookups()`` 观察到：

.. code-block:: c

   file->f_mode & FMODE_CREATED

它把 ``nd->path.dentry`` 从parent ``/work`` 更新成new file dentry，然后依次：

.. code-block:: text

   fsnotify_create
   → inode_unlock(/work inode)
   → mnt_drop_write(/dev/sda1 mount)

从此其他directory operation可以进入 ``/work``。新name/inode已实例化，所以释放parent lock不会暴露半创建对象。

mount write hold在这里释放只表示create syscall不再占用“filesystem write operation in progress”引用，不表示metadata已经写盘。

新文件为什么不再做一次普通write-permission检查
---------------------------------------------

``path_openat()`` 随后调用：

.. code-block:: c

   do_open(nd, file, op);

因为 ``FMODE_CREATED`` 已设置，``do_open()``：

.. code-block:: text

   clears O_TRUNC for this path
   sets acc_mode = 0 for duplicate permission check
   still validates object type and open invariants

create前已经在locked parent与negative dentry上完成 ``MAY_WRITE | MAY_EXEC``、LSM create检查与mode建立。此时不再用普通“打开一个既有文件”的路径重复拒绝刚创建的inode。

``O_EXCL`` 也已经完成使命：它保证last component在同一parent lock临界区内从不存在变成存在。后续不会把它保存成持续影响I/O的file flag。

``vfs_open`` 怎样把 path 装进 struct file
-----------------------------------------

``do_open()`` 调用：

.. code-block:: c

   vfs_open(&nd->path, file);

``vfs_open()`` 先把mount与dentry写入file：

.. code-block:: c

   file->__f_path = *path;

然后进入 ``do_dentry_open()``。主要状态连接如下：

.. code-block:: text

   file->f_path    → /work/demo.txt dentry + ext4 mount
   file->f_inode   → new ext4 inode
   file->f_mapping → inode->i_mapping
   file->f_pos     = 0

``struct file`` 从“只有flags/cred的空对象”变成绑定一个具体open file description的对象。

write open怎样取得inode write access
-----------------------------------

因为open mode包含 ``FMODE_WRITE`` 且目标是regular file，``do_dentry_open()`` 调用：

.. code-block:: c

   file_get_write_access(file);

成功后：

.. code-block:: text

   inode write-access count increments
   file->f_mode gains FMODE_WRITER

这项引用用于协调deny-write、executable write exclusion和filesystem write access。它不会把任何用户数据写入文件。

regular file还得到 ``FMODE_ATOMIC_POS``，表示共享 ``struct file`` 的implicit file-position操作需要按open-file-description语义串行化。

ext4 operations怎样绑定到 file
------------------------------

new inode在 ``ext4_create()`` 中已经设置：

.. code-block:: c

   inode->i_fop = &ext4_file_operations;

``do_dentry_open()`` 取得该operation table reference：

.. code-block:: c

   file->f_op = fops_get(inode->i_fop);

并执行security、fsnotify permission与lease checks。固定场景没有fanotify denial、lease conflict或LSM rejection。

随后调用filesystem open callback：

.. code-block:: text

   ext4_file_operations.open
   → ext4_file_open

``ext4_file_open()`` 检查：

* filesystem没有forced shutdown/emergency error；
* fscrypt与fsverity允许；
* quota file-open逻辑成功；
* write inode需要的ext4 journal attachment可用。

它还设置普通ext4 file支持的mode能力，例如NOWAIT与direct-I/O capability标记。当前实际I/O仍是普通buffered write，因为用户没有传 ``O_DIRECT``。

``FMODE_OPENED`` 与 ``FMODE_CAN_WRITE`` 何时出现
-----------------------------------------------

filesystem open callback成功后：

.. code-block:: c

   file->f_mode |= FMODE_OPENED;

因为 ``ext4_file_operations`` 提供 ``write_iter``，并且file是write-open：

.. code-block:: c

   file->f_mode |= FMODE_CAN_WRITE;

同时初始化：

.. code-block:: text

   readahead state
   IOCB flags
   llseek/pwrite capability
   file position = 0

``O_CREAT``、``O_EXCL`` 等只控制open过程的flags从 ``file->f_flags`` 清除；留下的是后续I/O真正需要的access/status flags。

此时 ``path_openat()`` 检查 ``FMODE_OPENED`` 并返回完整的 ``struct file *``。

fd 6怎样从 reservation 变成 published descriptor
-------------------------------------------------

控制回到 ``FD_ADD`` 的 ``fd_publish()``：

.. code-block:: c

   fd_install(6, file);

此前：

.. code-block:: text

   open_fds[6] = 1
   fdt->fd[6]  = NULL

``fd_install()`` 在RCU保护下取得current fdtable。固定场景没有fdtable resize，走fast path：

.. code-block:: c

   rcu_assign_pointer(fdt->fd[6], file);

发布后：

.. code-block:: text

   open_fds[6]       = 1
   close_on_exec[6]  = 0
   fdt->fd[6]        = new struct file

release/acquire与RCU规则保证其他合法fd lookup在看到non-NULL pointer时，也能看到已经初始化完成的 ``f_path``、``f_inode``、``f_op`` 与mode字段。

``fd_install`` 消费caller持有的file reference。fd table现在负责维持该open file description的生命周期。

syscall怎样把 6 返回用户态
--------------------------

``fd_publish()`` 返回descriptor number 6，控制流依次返回：

.. code-block:: text

   FD_ADD
   → do_sys_openat2
   → do_sys_open
   → __x64_sys_openat
   → do_syscall_64

``do_syscall_64()`` 把6写入：

.. code-block:: c

   pt_regs->ax = 6;

随后：

.. code-block:: text

   syscall_exit_to_user_mode
   → SYSRETQ or IRETQ
   → CPL 3
   → userspace RAX = 6

用户变量 ``fd`` 获得6。pathname string可以在syscall后修改或释放，因为kernel object graph已经保存dentry/inode/path references，不再依赖用户字符串。

open返回时文件已经具备什么
--------------------------

内存与VFS层面：

.. code-block:: text

   /work/demo.txt name exists
   dentry is positive
   ext4 inode exists
   inode mode = regular 0644
   inode nlink = 1
   inode size = 0
   inode data blocks = 0
   fd 6 points to opened struct file
   file access = write-only
   file position = 0

这意味着parent可以立即：

* 用fd 6执行 ``write``；
* 通过pathname再次lookup该文件；
* 把fd传递或dup给其他descriptor；
* 关闭fd而不删除文件，因为nlink是1。

open返回时还没有保证什么
------------------------

固定open没有 ``O_SYNC``，也没有调用 ``fsync(fd)`` 或父directory ``fsync``。因此：

.. code-block:: text

   JBD2 metadata commit complete      = not guaranteed
   journal commit record durable      = not guaranteed
   directory home block checkpointed  = not guaranteed
   inode-table home block checkpointed= not guaranteed

``openat`` 的成功保证当前运行系统中的create/open语义成功，不单独构成power-loss durability保证。

另外，文件size为0且没有data block。open/create阶段没有为未来write猜测或预留一个data block；真正data block allocation取决于后续write、delayed allocation与writeback。

当前精确状态
------------

* current task：parent；
* CPU mode：x86-64 CPL 3；
* syscall result/RAX：6；
* fd 6：published并open；
* close-on-exec bit 6：clear；
* ``struct file``：``FMODE_OPENED | FMODE_WRITE | FMODE_CAN_WRITE``，``f_pos=0``；
* pathname：``/work/demo.txt``；
* dentry：positive；
* inode：ext4 regular 0644，nlink 1，size 0；
* data blocks：0；
* parent directory lock：released；
* mount write hold：released；
* create metadata：attached toJBD2 transaction；
* journal durability：尚未由本场景强制；
* storage I/O：整个场景没有发生；
* runtime scenario：complete；
* next runtime scenario：unselected。

关键边界
--------

#. descriptor reservation与file pointer publication是两个阶段。
#. ``struct file`` 表示open file description，fd只是指向它的table index。
#. write-open取得inode write access，但不会写入file data。
#. ``FMODE_OPENED`` 在filesystem open callback成功后才设置。
#. ``fd_install`` 是其他fd lookup可看到完整file对象的publication边界。
#. create/open成功不等于create metadata已经持久化。
#. size-0新文件没有data block；后续write才引出delayed allocation与block allocation。

资料
----

* `Linux 7.2-rc1 fs/namei.c：do_open、path_openat 与created-file处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/namei.c>`_
* `Linux 7.2-rc1 fs/open.c：vfs_open、do_dentry_open 与file mode初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c：ext4_file_open 与ext4_file_operations <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 fs/file.c：alloc_fd、fd_install 与fdtable publication <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 include/linux/file.h：FD_ADD 与fd_publish <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/file.h>`_
