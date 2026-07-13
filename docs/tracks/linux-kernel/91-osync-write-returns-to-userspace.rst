第九十一章：O_SYNC write 怎样提交 file position 并返回用户态？
=================================================================

第九十章结束时，``ext4_sync_file()`` 已经返回 0。file data WRITE、required journal commit、barrier/flush policy和 writeback-error检查均已成功完成。

当前仍处在原 ``write(fd, buf, 4096)`` 的 kernel call stack 中：

.. code-block:: text

   generic_write_sync
   → ext4_buffered_write_iter
   → ext4_file_write_iter
   → new_sync_write
   → vfs_write
   → ksys_write
   → __x64_sys_write
   → do_syscall_64

``kiocb->ki_pos`` 已经是 4096，但 ``new_sync_write()`` 栈上的 local ``pos`` 与共享 ``file->f_pos`` 仍是 0。本章追踪这些状态怎样逐层提交，并让用户态最终在 ``RAX`` 中得到 4096。

``generic_write_sync`` 什么时候返回原字节数
------------------------------------------

函数此前计算并同步范围：

.. code-block:: text

   start = ki_pos - count = 0
   end   = ki_pos - 1     = 4095

``vfs_fsync_range()`` 现在返回 0，因此：

.. code-block:: c

   return count;

结果是：

.. code-block:: text

   generic_write_sync(iocb, 4096) = 4096

若 fsync、journal、flush或 writeback error非零，它会直接返回该负错误码，而不是返回先前已经复制到 page cache的 4096。``O_SYNC`` 的系统调用成功语义要求同步阶段也成功。

ext4 怎样结束 ``write_iter``
----------------------------

``ext4_buffered_write_iter()`` 接收 4096 并返回。inode ``i_rwsem`` 已在进入 ``generic_write_sync()`` 前释放，因此这里没有再次解锁 inode。

控制权回到 ``ext4_file_write_iter()``。固定对象不是 DAX、direct I/O或 atomic write，函数直接把 buffered result传回 VFS：

.. code-block:: text

   ext4_file_write_iter(...) = 4096

此刻 page cache与 storage durability已经完成，position提交仍只发生在 ``kiocb`` 内：

.. code-block:: text

   kiocb.ki_pos = 4096
   local pos    = 0
   file->f_pos  = 0

``new_sync_write`` 怎样提交 local ``pos``
---------------------------------------

``new_sync_write()`` 创建 ``kiocb`` 时执行过：

.. code-block:: c

   kiocb.ki_pos = *ppos;

这里的 ``ppos`` 指向 ``ksys_write()`` 栈上的 local ``pos``，不是直接指向 ``file->f_pos``。

``write_iter`` 成功返回后：

.. code-block:: c

   if (ret > 0 && ppos)
       *ppos = kiocb.ki_pos;

因此状态变为：

.. code-block:: text

   kiocb.ki_pos = 4096
   local pos    = 4096
   file->f_pos  = 0

这一步只把 iterator position传回 synchronous VFS wrapper。共享 open-file position仍由更外层统一提交。

``vfs_write`` 在返回前做哪些收尾
-------------------------------

``new_sync_write()`` 返回 4096 后，``vfs_write()`` 执行：

.. code-block:: c

   fsnotify_modify(file);
   add_wchar(current, 4096);
   inc_syscw(current);
   file_end_write(file);

这些动作分别表示：

* 向 fsnotify观察者发布 file modification event；
* 把 4096 bytes计入 task write-character accounting；
* 增加 write syscall accounting；
* 释放第八十三章由 ``file_start_write()`` 取得的 superblock freeze protection。

freeze protection覆盖了整个 O_SYNC过程，包括 data writeback、journal commit和可能的 device flush；它不会在 dirty folio建立后提前释放。

``file_end_write()`` 不修改 file position，也不再次刷新数据。它只结束 superblock writer section。

``ksys_write`` 为什么最后才写 ``file->f_pos``
-------------------------------------------

第八十三章中，``CLASS(fd_pos, f)(fd)`` 已经取得 fd reference，并在需要时持有 position serialization lock。函数最初复制：

.. code-block:: c

   pos = file->f_pos;  /* 0 */

现在 ``vfs_write()`` 返回 4096，local ``pos`` 已由 ``new_sync_write()`` 更新为 4096。``ksys_write()`` 因而执行：

.. code-block:: c

   if (ret >= 0 && ppos)
       file->f_pos = pos;

最终：

.. code-block:: text

   file->f_pos = 4096

这种“先在 local pos中推进，成功后一次提交”的结构防止下游失败时把共享 position留在半更新状态。

如果文件是 ``FMODE_STREAM``，``file_ppos()`` 返回 NULL，不存在共享 seek position更新。固定对象是普通 ext4 regular file，所以使用 ``file->f_pos``。

fd guard 在哪里释放
-------------------

``ksys_write()`` 返回前，``fd_pos`` scoped guard自动执行清理：

* 释放可能持有的 ``f_pos_lock``；
* 释放 fd lookup取得的 file reference；
* 结束本次 position-serialized operation。

锁释放不改变已经提交的 ``file->f_pos=4096``。

syscall wrapper 怎样把 4096 返回 dispatch 层
-------------------------------------------

``SYSCALL_DEFINE3(write, ...)`` 只是：

.. code-block:: c

   return ksys_write(fd, buf, count);

因此：

.. code-block:: text

   __x64_sys_write(regs) = 4096

``x64_sys_call()`` 的 syscall-number 1 case返回这个值。``do_syscall_x64()`` 写入保存的 register frame：

.. code-block:: c

   regs->ax = x64_sys_call(regs, nr);

当前：

.. code-block:: text

   pt_regs->ax = 4096

这还不是 CPU 已经执行到用户态；它只是内核将来恢复 ``RAX`` 时使用的值。

``syscall_exit_to_user_mode`` 处理什么
------------------------------------

``do_syscall_64()`` 调用：

.. code-block:: c

   syscall_exit_to_user_mode(regs);

exit work会按需要处理：

* pending signal；
* reschedule request；
* audit与 syscall tracing；
* ptrace/single-step state；
* task-work与 architecture-specific exit work；
* context tracking和 RCU user transition。

固定主线没有信号改写返回值，也没有 ptrace要求停下，因此 ``regs->ax`` 保持 4096。

SYSRET 与 IRET 怎样选择
-----------------------

``do_syscall_64()`` 检查保存的 user register state是否满足 SYSRET约束：

* ``RCX`` 与 user RIP一致；
* ``R11`` 与 user RFLAGS一致；
* user ``CS/SS`` 是标准 selector；
* RIP是合法 canonical user address；
* flags不要求 SYSRET无法恢复的状态；
* 不是必须使用 IRET的环境。

满足时返回 true，entry assembly使用快速 SYSRET path；否则使用完整 IRET path。

两条路径都恢复：

.. code-block:: text

   user RIP
   user RSP
   user flags
   general registers including RAX=4096
   CPL 3 segments

启用 PTI时，return trampoline还会切回 user CR3；classic path在返回前执行相应 ``swapgs``。

用户态看到什么
--------------

CPU完成 SYSRETQ或 IRETQ 后：

.. code-block:: text

   CPU mode      = x86-64 CPL 3
   RAX           = 4096
   file->f_pos   = 4096
   target folio  = page cache中 clean、uptodate、unlocked
   data range    = file offset 0..4095 已写入

C library wrapper把非负 ``RAX`` 作为 ``write()`` 返回值交给程序：

.. code-block:: c

   ssize_t n = write(fd, buf, 4096);
   /* n == 4096 */

返回 4096表示全部 4096 bytes成功，并且在固定 ``O_SYNC`` filesystem policy下，同步要求已经满足。

它不表示：

* file已经 close；
* page-cache folio已经回收；
* journal transaction已经 checkpoint回 home blocks；
* 后续 writes也自动同步；
* 另一个独立 fd的 position发生变化。

commit与 checkpoint为什么不同
-----------------------------

full或 fast journal commit提供 crash recovery所需的 durable log状态。JBD2后续 checkpoint可以把 committed metadata从 journal对应关系整理回 filesystem home blocks，并回收 log空间。

``write()`` 不需要等待所有 checkpoint完成才返回。只要 recovery记录与 ordering要求满足，crash后 journal replay仍能恢复一致状态。

因此：

.. code-block:: text

   transaction committed
   ≠ transaction fully checkpointed and removed from journal

这也是 O_SYNC不会强制整个 filesystem停止并清空全部历史 journal工作的原因。

当前场景终点
------------

本章结束时，独立的 ``O_SYNC write(fd, buf, 4096)`` 场景已经完整闭环：

.. code-block:: text

   userspace write
   → x86 syscall entry
   → VFS / ext4 buffered copy
   → dirty page-cache folio
   → WB_SYNC_ALL writeback
   → ext4 WRITE bio
   → blk-mq / SCSI / libata / AHCI
   → data completion / folio_end_writeback
   → fast or full journal commit
   → commit barrier or standalone device flush
   → error propagation
   → local position commit
   → file->f_pos commit
   → syscall exit
   → userspace RAX=4096

最终状态：

* 当前执行者：原 writer task；
* CPU mode：x86-64 CPL 3；
* syscall result：4096；
* ``file->f_pos``：4096；
* ``kiocb`` 与 local ``pos``：调用栈退出，不再存在；
* superblock freeze protection：已释放；
* fd position lock：已释放；
* data bio/request/ATA command：已完成并释放；
* optional flush command：若需要，已完成并释放；
* target folio：clean、uptodate、unlocked；
* runtime scenario：complete。

下一条 kernel runtime主线尚未选择。不能把任意后续 syscall伪装成本次 write的自动下一步。

关键边界
--------

#. O_SYNC同步失败时，``generic_write_sync`` 返回错误，而不是已复制的 byte count。
#. ``kiocb->ki_pos`` 先更新，local ``pos`` 后更新，共享 ``file->f_pos`` 最后提交。
#. ``file_end_write`` 释放 freeze protection，不更新 position。
#. syscall return value先写入 ``pt_regs->ax``，随后才由 SYSRET/IRET恢复到用户 ``RAX``。
#. SYSRET与 IRET路径不同，用户可见结果相同。
#. journal commit不要求所有 metadata已经 checkpoint回 home blocks。
#. ``write() == 4096`` 结束当前场景，不决定程序下一条 syscall。

资料
----

* `Linux 7.2-rc1 include/linux/fs.h：generic_write_sync 与 file_end_write <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fs.h>`_
* `Linux 7.2-rc1 fs/read_write.c：new_sync_write、vfs_write 与 ksys_write <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c：ext4 buffered write return path <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 arch/x86/entry/syscall_64.c：return value与 SYSRET eligibility <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscall_64.c>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：SYSRET/IRET user return <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 fs/jbd2/checkpoint.c：committed transaction checkpointing <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/jbd2/checkpoint.c>`_
