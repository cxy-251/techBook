第八十三章：x86-64 的 write() 怎样进入 ext4 buffered write？
================================================================

第八十二章已经把独立的 ``read(fd, buf, 4096)`` 场景完整闭环。本章开始一条新的运行期故事，不把它伪装成上一条 read 的时间线后续。

固定场景如下：

.. code-block:: text

   userspace call       = write(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL
   open flags           = O_WRONLY | O_SYNC
   file                 = already-open regular ext4 file on /dev/sda1
   initial file->f_pos  = 0
   file size            = at least 4096 bytes
   logical block 0      = existing initialized mapped block
   filesystem block     = 4096 bytes
   I/O mode             = buffered; not O_DIRECT; not DAX
   ext4 mode            = journal enabled, data=ordered, delayed allocation enabled
   page cache index 0   = absent before the call
   user buffer          = mapped, readable, stable during copy
   excluded             = inline data, fscrypt, fs-verity, atomic write, ENOSPC and injected faults

本章追踪 syscall entry、fd 与 position 保护、VFS 写检查以及 ext4 file operation 分派，停在 ``generic_perform_write()`` 即将开始修改 page cache 的位置。

``SYSCALL`` 怎样再次进入 ``entry_SYSCALL_64``
------------------------------------------------

用户态按 x86-64 syscall ABI 准备寄存器：

.. code-block:: text

   RAX = __NR_write = 1
   RDI = fd
   RSI = buf
   RDX = 4096

CPU 执行 ``SYSCALL`` 后进入 ``entry_SYSCALL_64``。入口汇编仍会完成：

* ``swapgs``；
* 保存用户 ``RSP``；
* 在启用 PTI 时切换到 kernel CR3；
* 切换到当前 task 的 kernel stack；
* 构造 ``struct pt_regs``；
* 调用 ``do_syscall_64()``。

这条入口与 read 场景相同，真正的分叉来自 syscall number。``x64_sys_call()`` 对 number 1 选择：

.. code-block:: c

   __x64_sys_write(regs)

wrapper 从保存的寄存器中恢复 ``fd``、``buf`` 和 ``count``，随后进入 ``ksys_write()``。

``ksys_write`` 为什么不直接修改 ``file->f_pos``
------------------------------------------------

``ksys_write()`` 使用 ``fd_pos`` guard 查找 fd，并在该 open file description 需要原子 position 时取得 ``f_pos_lock``。

它先复制共享位置：

.. code-block:: c

   pos = file->f_pos;
   ppos = &pos;
   ret = vfs_write(file, buf, count, ppos);

当前：

.. code-block:: text

   file->f_pos = 0
   local pos   = 0

只有 ``vfs_write()`` 返回非负值后，``ksys_write()`` 才执行：

.. code-block:: c

   file->f_pos = pos;

因此写入期间存在三个不同的位置状态：

* 共享 ``file->f_pos``；
* ``ksys_write()`` 栈上的 local ``pos``；
* 后续 ``kiocb->ki_pos``。

本章停止时三者尚未全部提交。

``vfs_write`` 建立哪些保护
--------------------------

``vfs_write()`` 依次检查：

* ``FMODE_WRITE``；
* ``FMODE_CAN_WRITE``；
* ``access_ok(buf, 4096)``；
* ``rw_verify_area(WRITE, ...)``；
* ``MAX_RW_COUNT`` 限制。

``access_ok()`` 只验证用户地址范围，真正读取用户页面发生在 page-cache copy 阶段。固定条件保证 copy 期间 buffer 保持 mapped and readable。

普通 ext4 文件通过 ``write_iter`` 实现写入，所以 VFS 选择：

.. code-block:: c

   file_start_write(file);
   ret = new_sync_write(file, buf, count, pos);
   file_end_write(file);

``file_start_write()`` 取得 superblock freeze protection，阻止文件系统在该 write 尚未结束时进入不兼容的 freeze 阶段。它不是 inode lock，也不负责 page-cache 序列化。

``new_sync_write`` 怎样建立 ``kiocb`` 和 source iterator
--------------------------------------------------------

``new_sync_write()`` 创建同步 I/O control block 与用户 iterator：

.. code-block:: c

   init_sync_kiocb(&kiocb, file);
   kiocb.ki_pos = *ppos;
   iov_iter_ubuf(&iter, ITER_SOURCE, buf, 4096);

``ITER_SOURCE`` 表示数据从 iterator 指向的用户 buffer 流向文件。

文件以 ``O_SYNC`` 打开，``iocb_flags(file)`` 把 open flags 转换成：

.. code-block:: text

   IOCB_DSYNC
   IOCB_SYNC

``IOCB_SYNC`` 表示同步范围不仅包含数据，还包含普通 fsync 所要求的 metadata。它不会让 copy 动作绕开 page cache；它决定写入数据变脏后，返回用户态前必须执行同步阶段。

随后调用：

.. code-block:: c

   file->f_op->write_iter(&kiocb, &iter);

ext4 怎样选择 buffered 分支
---------------------------

普通 ext4 regular file 的 ``write_iter`` 是 ``ext4_file_write_iter()``。固定 inode：

* 不是 DAX inode；
* ``IOCB_DIRECT`` 未设置；
* ``IOCB_ATOMIC`` 未设置。

所以真实分派为：

.. code-block:: text

   ext4_file_write_iter
   → ext4_buffered_write_iter

``ext4_buffered_write_iter()`` 不支持 ``IOCB_NOWAIT``。当前是普通同步调用，于是取得 inode 的 exclusive ``i_rwsem``：

.. code-block:: c

   inode_lock(inode);

这个 lock 串行化会修改同一 inode 数据与 size 的普通 buffered writes。它与 ``fd_pos`` lock、superblock freeze protection 分别保护不同对象。

ext4 写检查确认什么
-------------------

``ext4_write_checks()`` 先调用通用限制检查，再处理 ext4 特有状态：

* inode 不是 immutable；
* offset 与 count 未超过文件系统上限；
* 当前写不是非法 append/position；
* 文件系统不在 emergency/forced-shutdown 状态；
* 更新必要的 modification state 与时间戳；
* 当前 offset 0 位于已有文件范围内，不需要 zero beyond EOF。

固定写是对已存在 4096-byte 范围的完整覆盖，因此没有：

* file extension；
* orphan-list 处理；
* partial block beyond EOF zeroing；
* 新文件大小发布。

检查成功后，ext4 执行：

.. code-block:: c

   ret = generic_perform_write(iocb, from);

这才是 buffered write 真正准备 page-cache folio 并复制用户数据的入口。

当前精确边界
------------

CPU 即将执行：

.. code-block:: c

   generic_perform_write(&kiocb, &iter);

此刻机器状态：

* 当前执行者：调用 ``write()`` 的用户 task；
* CPU mode：x86-64 CPL 0，syscall process context；
* ``file->f_pos``：仍为 0；
* local ``pos``：仍为 0；
* ``kiocb->ki_pos``：0；
* iterator：``ITER_SOURCE``，剩余 4096 bytes；
* inode ``i_rwsem``：exclusive held；
* superblock write/freeze protection：held；
* target folio：尚未加入 page cache；
* 用户数据：尚未复制；
* folio dirty/writeback：尚未发生；
* O_SYNC 持久化阶段：尚未开始；
* ``write()``：尚未返回。

关键边界
--------

#. ``access_ok()`` 不等于用户数据已复制。
#. ``file_start_write()`` 是 superblock freeze protection，不是 inode lock。
#. ``fd_pos`` guard 保护共享 position；``inode_lock()`` 保护 inode 写入语义。
#. ``O_SYNC`` 不会把 buffered write 变成 direct I/O。
#. ``ext4_file_write_iter()`` 选择 buffered 分支后，数据仍先进入 page cache。
#. ``file->f_pos`` 只有在整个下游返回后才由 ``ksys_write()`` 提交。

资料
----

* `Linux 7.2-rc1 arch/x86/entry/entry_64.S <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 fs/read_write.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 include/linux/fs.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fs.h>`_
