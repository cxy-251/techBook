第八十二章：reader task 怎样复制 folio，并让 read() 返回用户态？
=================================================================

第八十一章结束时，AHCI、SCSI、blk-mq、bio 与 ext4 completion 已经完成：

.. code-block:: text

   target folio
   → storage data present
   → PG_uptodate = 1
   → PG_locked = 0
   → lock waiters woken

发起 ``read(fd, buf, 4096)`` 的 task 现在可以重新获得 CPU。本章追踪它怎样重新验证 page-cache folio、调用 ``copy_folio_to_iter()``、推进 ``ki_pos``，把共享 ``file->f_pos`` 更新为 4096，并通过 x86-64 syscall exit 返回用户态。

固定成功条件继续成立：文件至少有 4096 bytes，用户 buffer 在 copy 期间保持映射且可写，没有 signal、ptrace、seccomp 或 userfault 分支修改返回结果。

reader 为什么需要重新查找 folio
------------------------------

reader 最初在 ``filemap_get_pages()`` 中通过 synchronous readahead 创建并提交 I/O。它随后发现 folio 尚未 uptodate：

.. code-block:: text

   folio exists
   PG_locked = 1
   PG_uptodate = 0

``filemap_update_page()`` 尝试 ``folio_trylock()``。若该 lock 仍由 read I/O 持有，普通同步 read 进入：

.. code-block:: c

   folio_put_wait_locked(folio, TASK_KILLABLE);
   return AOP_TRUNCATED_PAGE;

这里的 ``AOP_TRUNCATED_PAGE`` 是内部 retry signal，不表示文件真的被 truncate。等待期间函数已经放弃当前 folio reference，因此 completion 唤醒 task 后，``filemap_get_pages()`` 回到 retry 路径，再次从 ``mapping->i_pages`` 查找 folio。

这样可以防止等待过程中发生 truncate、invalidate、migration 或 folio replacement 时继续使用过期对象。

重新取得 folio 后检查什么
------------------------

第二次 ``filemap_get_read_batch()`` 找到相同 index 0 的 folio。completion 已经执行：

.. code-block:: c

   folio_end_read(folio, true);

因此：

.. code-block:: text

   folio_test_uptodate(folio) == true
   folio_test_locked(folio)   == false

``filemap_get_pages()`` 无需再次调用 ``read_folio``，直接返回 folio batch 给 ``filemap_read()``。

如果上一章的 bio 失败，``PG_uptodate`` 不会设置；reader 会得到 I/O error 或尝试相应 recovery path。固定主线只走 successful completion。

``filemap_read`` 为什么再次读取 i_size
------------------------------------

拿到 uptodate folio 后，``filemap_read()`` 重新读取 inode size：

.. code-block:: c

   isize = i_size_read(inode);
   end_offset = min_t(loff_t, isize,
                      iocb->ki_pos + iter->count);

这个检查发生在 folio uptodate 之后，目的是处理 I/O 进行期间可能发生的 truncate。即使 page-cache folio 包含完整页面，函数也不能把当前 EOF 之后的字节复制给用户。

固定文件至少有 4096 bytes：

.. code-block:: text

   iocb->ki_pos = 0
   iter->count  = 4096
   end_offset   = 4096

所以本次可复制范围正好是 offset 0 开始的 4096 bytes。

``copy_folio_to_iter`` 才执行 page cache 到用户空间的数据移动
------------------------------------------------------------

``filemap_read()`` 对目标 folio 计算：

.. code-block:: c

   offset = iocb->ki_pos & (folio_size(folio) - 1);
   bytes  = min(end_offset - iocb->ki_pos,
                folio_size(folio) - offset);

当前：

.. code-block:: text

   offset = 0
   bytes  = 4096

随后执行：

.. code-block:: c

   copied = copy_folio_to_iter(folio, offset, bytes, iter);

这才是整个读取链的第二段数据移动：

.. code-block:: text

   第一段：SATA device → AHCI DMA → page-cache folio
   第二段：page-cache folio → CPU copy/uaccess → user buf

AHCI PRDT 从未指向当前 user buffer。buffered I/O 使用 page cache 作为中间层，因此设备 DMA 与 user copy 属于两个独立动作。

为什么 ``access_ok`` 成功仍不够
------------------------------

第七十五章中的 ``vfs_read()`` 已调用 ``access_ok(buf, 4096)``，它只证明地址范围位于允许的 user address space。真正访问页面发生在 ``copy_folio_to_iter()`` 内部，仍可能因为以下情况失败或只复制部分数据：

* mapping 被并发解除；
* user page permission 改变；
* page fault 无法解决；
* architecture uaccess 检测失败。

固定场景规定 buffer 在 copy 期间保持 mapped and writable，因此：

.. code-block:: text

   copied = 4096

若 ``copied < bytes``，``filemap_read()`` 会记录 ``-EFAULT``；已经成功复制的 bytes 仍可能作为 partial read 返回。

``ki_pos`` 在哪里变成 4096
-------------------------

copy 成功后，``filemap_read()`` 更新：

.. code-block:: c

   already_read += copied;
   iocb->ki_pos += copied;

因此：

.. code-block:: text

   already_read  = 4096
   iocb->ki_pos  = 4096
   iter->count   = 0

函数释放 folio references，更新 readahead ``prev_pos`` 与 file access time/accounting，然后返回：

.. code-block:: c

   return already_read ? already_read : error;

当前返回值为 4096。

注意 ``iocb->ki_pos`` 仍是本次 I/O control block 中的位置。共享 open file description 的 ``file->f_pos`` 尚未在 ``filemap_read()`` 内直接修改。

位置怎样逐层传回 ``ksys_read``
-----------------------------

``generic_file_read_iter()`` 和 ``ext4_file_read_iter()`` 把 4096 原样返回给 ``new_sync_read()``。

``new_sync_read()`` 在调用 read iterator 前曾执行：

.. code-block:: c

   kiocb.ki_pos = *ppos;

read iterator 返回后，它执行：

.. code-block:: c

   *ppos = kiocb.ki_pos;

当前 ``ppos`` 指向 ``ksys_read()`` 栈上的 local ``pos``，所以：

.. code-block:: text

   local pos = 4096

``vfs_read()`` 随后执行 successful-read accounting：

* ``fsnotify_access(file)``；
* 增加 task 的 read-character accounting；
* 增加 read syscall accounting。

这些动作不会再次复制数据。

``file->f_pos`` 为什么最后才提交
-------------------------------

``ksys_read()`` 进入时通过 ``fd_pos`` guard 取得 fd，并在需要时串行化共享 file position。它没有把 ``file->f_pos`` 直接传给整个下游，而是先复制到 local variable：

.. code-block:: c

   pos = file->f_pos;
   ret = vfs_read(file, buf, count, &pos);

只有调用返回非负值时才提交：

.. code-block:: c

   if (ret >= 0)
       file->f_pos = pos;

当前：

.. code-block:: text

   ret         = 4096
   local pos   = 4096
   file->f_pos = 4096

这种提交方式保证共享 position 在 ``fd_pos`` lock 保护下完成一次原子 read-position transaction。``pread64()`` 使用显式 offset，不会按这套语义更新 ``file->f_pos``。

系统调用返回值怎样写回 ``RAX``
------------------------------

``__x64_sys_read()`` 返回 ``ksys_read()`` 的结果。x86-64 dispatcher 在 ``do_syscall_x64()`` 中执行：

.. code-block:: c

   regs->ax = x64_sys_call(regs, nr);

于是保存的 user register frame 变为：

.. code-block:: text

   pt_regs->ax = 4096

用户 buffer 已经含有文件的前 4096 bytes，``file->f_pos`` 也已经推进。后续 exit machinery 主要恢复 userspace execution state。

``syscall_exit_to_user_mode`` 处理哪些延迟工作
---------------------------------------------

``do_syscall_64()`` 在 syscall body 返回后调用：

.. code-block:: c

   syscall_exit_to_user_mode(regs);

通用 exit loop 可以处理：

* pending signal；
* task work；
* reschedule；
* audit / tracing；
* notification resume；
* architecture-specific user-return work。

因此“C 函数返回 4096”与“CPU 已执行用户态下一条指令”仍不是同一时刻。固定成功场景没有额外机制修改 ``RAX``，exit work 完成后结果仍为 4096。

什么时候使用 ``SYSRETQ``
------------------------

``do_syscall_64()`` 最后检查保存的 user frame 是否满足 SYSRET 限制：

* ``RCX`` 与保存的 user RIP 一致；
* ``R11`` 与 user RFLAGS 一致；
* CS/SS 是标准 64-bit user selectors；
* RIP 位于合法 canonical user range；
* RF/TF 等不兼容 flag 未设置；
* 不是 Xen PV 强制 IRET 场景。

普通干净的 native x86-64 ``read()`` 返回满足这些条件时，assembly 走：

.. code-block:: text

   syscall_return_via_sysret
   → restore general registers
   → switch to trampoline stack
   → switch to user CR3 when PTI enabled
   → restore user RSP
   → swapgs
   → sysretq

``sysretq`` 把 CPU 恢复到 CPL 3，user RIP 指向发出 ``SYSCALL`` 后的下一条指令，``RAX = 4096``。

什么时候退回 ``IRETQ``
----------------------

若 user frame 不满足 SYSRET 条件，``do_syscall_64()`` 返回 false，assembly 进入 ``swapgs_restore_regs_and_return_to_usermode``，最终通过 ``iretq`` 恢复完整 frame。

所以真实结论是：

.. code-block:: text

   clean normal frame → SYSRETQ
   exceptional frame  → IRETQ

两条路径都返回同一个 userspace continuation；差别在于可恢复状态范围和退出成本。正文不把“系统调用返回”错误地等同于只能使用 SYSRETQ。

用户态最终看到什么
------------------

CPU 返回 CPL 3 后，调用者观察到：

.. code-block:: c

   ssize_t n = read(fd, buf, 4096);

对应结果：

.. code-block:: text

   n            = 4096
   RAX          = 4096
   buf[0..4095] = 文件 offset 0..4095 的内容
   file->f_pos  = 4096

目标 folio 继续留在 page cache 中。下一次读取相同范围时，如果 folio 尚未被 reclaim 或 invalidated，可能直接命中 page cache，不再经过 ext4 block mapping、blk-mq、SCSI、libata 和 AHCI。

本章结束时的状态
----------------

本章结束时：

* 执行者：发起 ``read()`` 的 userspace task；
* CPU mode：已从 CPL 0 返回 CPL 3；
* syscall return：4096；
* user buffer：已经包含 4096 bytes 文件数据；
* ``file->f_pos``：已经从 0 更新为 4096；
* page-cache folio：uptodate、unlocked，并继续缓存文件数据；
* blk-mq/SCSI/ATA/AHCI command：已经完成并释放相关 request/tag 状态；
* fixed cold-miss ``read()`` 主线：完成。

本阶段已经完整贯通：

.. code-block:: text

   userspace read()
   → x86 syscall entry
   → fd / VFS / ext4
   → page-cache miss
   → bio / blk-mq / SCSI
   → libata / AHCI
   → device DMA completion
   → folio uptodate
   → copy to user
   → file position commit
   → SYSRETQ or IRETQ

下一运行期场景不应假装与这个 ``read()`` 自动连续。需要重新固定入口、对象状态和观察目标后，再展开下一条源码主线。

资料
----

* `Linux 7.2-rc1 mm/filemap.c：filemap_get_pages、filemap_read 与 copy_folio_to_iter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/read_write.c：new_sync_read、vfs_read 与 ksys_read position commit <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 arch/x86/entry/syscall_64.c：do_syscall_64 与 SYSRET eligibility <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscall_64.c>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：SYSRETQ 与 IRETQ exit paths <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 include/linux/entry-common.h：syscall exit-to-user work <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/entry-common.h>`_