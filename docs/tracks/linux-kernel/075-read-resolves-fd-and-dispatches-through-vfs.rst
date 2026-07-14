第七十五章：read() 怎样从 fd 找到 ext4 文件并进入 generic_file_read_iter？
=====================================================================

第七十四章停在 ``__x64_sys_read(regs)``。x86 wrapper 已把 ``pt_regs`` 中的参数解码为：

.. code-block:: text

   fd
   buf
   count = 4096

当前 CPU 仍在发起调用的 task 上下文中，以 CPL 0 运行在该 task 的 kernel stack。本章继续追踪：

.. code-block:: text

   __x64_sys_read
   → __do_sys_read
   → ksys_read
   → vfs_read
   → new_sync_read
   → ext4_file_read_iter
   → generic_file_read_iter

本章结束时，VFS 已经把“整数 fd 的读取请求”转换为“对 ext4 ``struct file`` 的 buffered iterator read”，但 page cache 尚未查找。

``SYSCALL_DEFINE3(read)`` 的函数体为什么很短
------------------------------------------

``fs/read_write.c`` 中的通用实现只有：

.. code-block:: c

   SYSCALL_DEFINE3(read, unsigned int, fd,
                   char __user *, buf, size_t, count)
   {
       return ksys_read(fd, buf, count);
   }

上一章说明的 x86 wrapper 负责寄存器解码与类型整理。进入实际 syscall body 后，``read`` 自身不解析 pathname、不接触 inode，也不直接调用 ext4。它把 fd-based read 的通用工作交给 ``ksys_read()``。

``CLASS(fd_pos, f)(fd)`` 同时承担什么工作
---------------------------------------

``ksys_read()`` 首先执行：

.. code-block:: c

   CLASS(fd_pos, f)(fd);

``fd_pos`` 是带自动 cleanup 的 class。构造时调用 ``fdget_pos(fd)``，函数返回时自动调用 ``fdput_pos()``。因此正常路径和所有 error path 都会统一释放临时 reference，并在需要时解开 ``f_pos_lock``。

``fdget_pos()`` 先通过 ``fdget()`` 从 ``current->files`` 的 fd table 找到 ``struct file``。这里存在两个 reference 策略：

.. code-block:: text

   files_struct 只由当前 task 独占
   → 可以借用 fd table 中的 file pointer
   → 不增加 file refcount

   files_struct 被多个 task/thread 共享
   → __fget_files() 取得稳定 reference
   → cleanup 时 fput()

借用不是“没有生命周期保护”。它只在满足轻量 fd lookup 的约束时使用：调用者必须在 syscall 返回用户态前结束使用，期间不能破坏该 file object 的 fd 生命周期。

为什么普通 ``read()`` 需要保护 ``file->f_pos``
---------------------------------------------

``read(fd, ...)`` 使用 open file description 中共享的 ``file->f_pos``。同一 ``struct file`` 可能通过：

* ``dup()`` 得到的多个 fd；
* fork 后继承的 fd；
* 同一进程的多个 thread；
* ``pidfd_getfd()`` 等机制；

被并发访问。

``fdget_pos()`` 检查 ``FMODE_ATOMIC_POS`` 与 file reference 状态。若文件位置可能被并发访问，它设置 ``FDPUT_POS_UNLOCK`` 并锁住：

.. code-block:: c

   mutex_lock(&file->f_pos_lock);

这使一次普通 read 的“读取当前位置、执行 I/O、更新当前位置”成为原子序列。若 file 只有单一安全访问者，内核跳过 mutex，避免每次 read 都付出锁开销。

``ksys_read()`` 为什么先复制一份局部 ``pos``
-------------------------------------------

取得 file 后，``ksys_read()`` 对普通非 stream 文件执行：

.. code-block:: c

   pos = file->f_pos;
   ret = vfs_read(file, buf, count, &pos);
   if (ret >= 0)
       file->f_pos = pos;

局部变量有两个作用：

* 深层 read path 通过 ``loff_t *`` 更新位置，不需要直接修改共享 ``file->f_pos``；
* 只有 read 返回非负值时，新的位置才提交回 open file description。

对于 pipe、socket 等带 ``FMODE_STREAM`` 的对象，``file_ppos()`` 返回 ``NULL``，因为 stream 不使用普通 seekable file position。当前固定场景是 ext4 regular file，因此 ``ppos`` 指向局部 ``pos``。

无效 fd 在哪里失败
-----------------

如果 fd table 中没有该 entry，``fdget_pos()`` 返回 empty fd，``ksys_read()`` 保留初始返回值 ``-EBADF``。

因此：

.. code-block:: text

   integer fd
   → current->files fdtable lookup
   → no struct file
   → -EBADF

此错误发生在 VFS permission、ext4 与 page cache 之前。当前固定场景中 fd 有效，因此继续进入 ``vfs_read()``。

``vfs_read()`` 先验证 file 能力和用户 buffer
-----------------------------------------

``vfs_read()`` 首先检查：

.. code-block:: text

   file->f_mode contains FMODE_READ
   file->f_mode contains FMODE_CAN_READ
   access_ok(buf, count)

三者含义不同：

* ``FMODE_READ`` 表示该 open file description 允许读；
* ``FMODE_CAN_READ`` 表示 file operations 确实提供可用的 read 接口；
* ``access_ok`` 只验证用户地址范围是否可能合法，不会预先把全部用户页读写一遍。

即使 ``access_ok`` 成功，后续复制数据时仍可能发生 page fault，最终也可能因无法写入用户 buffer 返回 ``-EFAULT``。

``rw_verify_area()`` 不只是检查 offset
-------------------------------------

接下来：

.. code-block:: c

   rw_verify_area(READ, file, pos, count);

它检查 count 能否用 ``ssize_t`` 表示、当前 position 是否允许、``pos + count`` 是否 overflow。随后调用：

.. code-block:: text

   security_file_permission(file, MAY_READ)
   → fsnotify_file_area_perm(file, MAY_READ, pos, count)

LSM 可以在这里拒绝本次读取；fanotify permission event 也可能介入。这些检查针对已经打开的 file object，不是重新执行 pathname lookup。

当前固定场景通过所有检查。``vfs_read()`` 还会把过大的请求截断到 ``MAX_RW_COUNT``；4096 字节不会触发截断。

为什么 ext4 走 ``read_iter`` 而不是旧 ``read``
--------------------------------------------

VFS 根据 ``file->f_op`` 选择接口：

.. code-block:: c

   if (file->f_op->read)
       ...
   else if (file->f_op->read_iter)
       new_sync_read(...);

ext4 regular file 使用 ``ext4_file_operations``，其中：

.. code-block:: c

   .read_iter = ext4_file_read_iter

没有为这条普通路径设置旧式 ``.read``，因此进入 ``new_sync_read()``。

``new_sync_read()`` 怎样把 read buffer 变成 iterator
--------------------------------------------------

``new_sync_read()`` 在 kernel stack 上建立：

.. code-block:: text

   struct kiocb kiocb
   struct iov_iter iter

然后初始化：

.. code-block:: text

   kiocb.ki_filp = ext4 struct file
   kiocb.ki_pos  = current read position
   iter type     = ITER_DEST
   iter buffer   = user buf
   iter count    = 4096

``ITER_DEST`` 表示数据流向 iterator 指向的目的地，也就是从 kernel/page cache 复制到用户 buffer。

这是同步 syscall，因此 ``read_iter`` 不允许返回 ``-EIOCBQUEUED``。完成后 ``new_sync_read()`` 把 ``kiocb.ki_pos`` 写回局部 ``pos``，再由 ``ksys_read()`` 提交到 ``file->f_pos``。

``ext4_file_read_iter()`` 先排除哪些特殊路径
-------------------------------------------

ext4 的 read iterator 依次检查：

.. code-block:: text

   ext4 forced shutdown
   → zero-length request
   → DAX inode
   → IOCB_DIRECT
   → generic_file_read_iter

当前场景明确固定：

* filesystem 没有 forced shutdown；
* count 为 4096；
* inode 不是 DAX；
* open 时没有 ``O_DIRECT``，``IOCB_DIRECT`` 未设置。

因此 ext4 不走 ``dax_iomap_rw()``，也不走 ``iomap_dio_rw()``，最终调用：

.. code-block:: c

   generic_file_read_iter(iocb, to);

到这里 ext4 已完成“选择 I/O 模型”的职责。普通 buffered read 的数据获取由通用 filemap/page-cache 层完成。

返回值最终怎样传播
----------------

后续若成功复制 4096 字节，返回链将执行：

.. code-block:: text

   generic_file_read_iter returns 4096
   → ext4_file_read_iter returns 4096
   → new_sync_read updates ki_pos
   → vfs_read records fsnotify_access and task read accounting
   → ksys_read commits file->f_pos
   → __x64_sys_read writes result to regs->ax
   → syscall exit restores RAX to userspace

若只读到 EOF 前的部分数据，read 可以返回 short count。只要已经复制至少一个字节，深层发生的后续错误通常不会覆盖已完成的 byte count。

本章结束时的状态
----------------

本章结束时：

* 当前执行者：发起 read 的 task，仍在 process context；
* CPU mode：CPL 0；
* ``fd``：已解析为稳定 ``struct file``；
* ``f_pos``：需要时由 ``f_pos_lock`` 保护，当前值复制到 ``kiocb.ki_pos``；
* user buffer：通过初始 ``access_ok``，尚未实际复制数据；
* permission：LSM 与 fsnotify area permission 已通过；
* filesystem：确定为 ext4 regular file；
* I/O model：buffered I/O，不是 DAX/direct I/O；
* 当前入口：``generic_file_read_iter(iocb, iter)``；
* page cache：尚未 lookup；
* block I/O：尚未提交。

下一章进入 ``filemap_read()``。固定 page cache 中目标 index 不存在，追踪 readahead/``read_folio``、ext4 logical-to-physical block mapping 与 READ bio submission。

资料
----

* `Linux 7.2-rc1 fs/read_write.c：ksys_read、vfs_read 与 new_sync_read <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 include/linux/file.h：fd、fd_pos cleanup class 与 fdput_pos <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/file.h>`_
* `Linux 7.2-rc1 fs/file.c：fdget、fdget_pos 与 f_pos_lock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c：ext4_file_operations 与 ext4_file_read_iter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 include/linux/fs.h：struct file、file_operations 与 f_mode <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fs.h>`_
* `Linux 7.2-rc1 security/security.c：security_file_permission hook dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/security.c>`_