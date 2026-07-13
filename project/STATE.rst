项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091

最新三章：

#. ``LK-WRITE-089``：ext4 fsync 怎样选择 fast commit 或完整 JBD2 commit？
#. ``LK-WRITE-090``：ext4 barrier 怎样把 journal 顺序落实到设备 cache？
#. ``LK-WRITE-091``：O_SYNC write 怎样提交 file position 并返回用户态？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

旧章节中的 ``Linux 6.12.95`` 是历史显示标签错误，技术事实继续以固定 Linux commit 为准。

已完成的运行期实验
------------------

``read(fd, buf, 4096)`` cold page-cache miss 已完整闭环：VFS、ext4、page cache、block、SCSI、libata、AHCI、completion、user copy 与 syscall return 均已完成。

``O_SYNC write(fd, buf, 4096)`` buffered overwrite 也已完整闭环：page-cache copy、writeback、storage data command、journal durability、barrier/flush、position commit 与 syscall return 均已完成。

O_SYNC write 固定场景
---------------------

::

   userspace call       = write(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL
   open flags           = O_WRONLY | O_SYNC
   file                 = independent already-open regular ext4 file
   filesystem           = /dev/sda1, journal enabled, data=ordered, delalloc enabled
   initial f_pos        = 0
   final f_pos          = 4096
   file size            = at least 4096 bytes
   filesystem block     = 4096 bytes
   write type           = full-block overwrite, not extending
   extent               = logical block 0 already initialized and mapped
   I/O mode             = buffered; not O_DIRECT; not DAX
   excluded             = inline data, fscrypt, fs-verity, atomic write
   failure policy       = no copy, writeback, journal, flush or storage error

完整控制流
----------

::

   userspace write(fd, buf, 4096)
   → entry_SYSCALL_64 / __x64_sys_write
   → ksys_write / vfs_write / new_sync_write
   → ext4_file_write_iter / ext4_buffered_write_iter
   → generic_perform_write
   → ext4_da_write_begin
   → copy_folio_from_iter_atomic
   → ext4_da_write_end
   → dirty page-cache folio
   → generic_write_sync
   → vfs_fsync_range(file, 0, 4095, datasync=0)
   → ext4_sync_file
   → file_write_and_wait_range
   → WB_SYNC_ALL / ext4_writepages
   → folio_clear_dirty_for_io
   → ext4_bio_write_folio / PG_writeback
   → REQ_OP_WRITE | REQ_SYNC bio
   → blk-mq / SCSI WRITE
   → libata ATA WRITE
   → AHCI H2D FIS / PRDT / PxCI
   → AHCI completion interrupt
   → SCSI / blk-mq / bio completion
   → ext4_end_bio / folio_end_writeback
   → file_write_and_wait_range returns 0
   → ext4_fsync_journal(inode, false, &needs_barrier)
   → choose i_sync_tid
   → already committed / fast commit / full JBD2 commit
   → commit barrier or standalone blkdev_issue_flush
   → file_check_and_advance_wb_err
   → ext4_sync_file returns 0
   → generic_write_sync returns 4096
   → new_sync_write: local pos = 4096
   → vfs_write: accounting / file_end_write
   → ksys_write: file->f_pos = 4096
   → pt_regs->ax = 4096
   → syscall_exit_to_user_mode
   → SYSRETQ or IRETQ
   → userspace RAX = 4096

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* 当前执行者：完成 O_SYNC write 的原 writer task；
* CPU mode：x86-64 CPL 3；
* syscall result / ``RAX``：4096；
* ``file->f_pos``：4096；
* target folio：clean、uptodate、unlocked，``PG_writeback=0``；
* data bio/request/SCSI/ATA/AHCI command：已完成并释放；
* journal requirement：已由 already-committed、fast commit 或 full JBD2 commit成功满足；
* barrier-enabled路径：commit内 barrier或 standalone FLUSH CACHE 已完成；
* writeback error：无，file error cursor已检查；
* superblock freeze protection：已释放；
* fd position guard/lock：已释放；
* ``kiocb`` 与 local ``pos``：调用栈已经退出；
* current runtime scenario：complete。

关键边界
--------

#. fast commit、full JBD2 commit与 already-committed是运行时分支，不能凭未固定 mount state写死其中一个。
#. fast-commit tail或 full commit record可以携带 ``REQ_PREFLUSH|REQ_FUA``。
#. journal commit无法替本次 fsync携带 barrier时，ext4单独执行 ``blkdev_issue_flush``。
#. standalone flush没有 payload、sector或 folio；SCSI将其表示为 SYNCHRONIZE CACHE，libata翻译为 ATA FLUSH CACHE/EXT。
#. transaction commit不等于所有 metadata已经 checkpoint回 home blocks。
#. ``kiocb->ki_pos``、local ``pos``、共享 ``file->f_pos`` 按顺序逐层提交。
#. 运行期场景结束后，不能虚构用户程序的下一条 syscall。

下一任务
--------

当前没有已选定的 runtime scenario。建议下一批固定为单线程 x86-64 用户进程直接执行 native ``fork()`` syscall：

::

   userspace fork()
   → entry_SYSCALL_64 / __x64_sys_fork
   → kernel_clone
   → copy_process
   → task_struct / PID / credentials / files / fs / signals
   → copy_mm
   → page-table copy-on-write
   → copy_thread
   → wake_up_new_task
   → scheduler first runs child
   → parent returns child PID
   → child returns 0

下一批开始前必须从固定 commit重新核对实际函数链，并记录明确的 fork flags、单线程条件、无 ptrace/seccomp/error和父子返回状态。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
