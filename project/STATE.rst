项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082

最新三章：

#. ``LK-READ-080``：AHCI 中断怎样确认完成的 tag，并把结果交回 SCSI？
#. ``LK-READ-081``：blk-mq completion 怎样结束 bio，并让 ext4 folio 变成 uptodate？
#. ``LK-READ-082``：reader task 怎样复制 folio，并让 read() 返回用户态？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定 Linux commit 的 ``Makefile`` 标识为 ``7.2-rc1``。旧章节中的 ``Linux 6.12.95`` 是历史显示标签错误，技术事实继续以固定 commit 为准。

已完成的运行期场景
------------------

::

   userspace call       = read(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
   file                 = already-open regular ext4 file on /dev/sda1
   initial f_pos        = 0
   filesystem block     = 4096 bytes
   I/O                  = buffered; not O_DIRECT; not DAX
   file features        = no inline data, fscrypt, fs-verity, integrity metadata
   initial page cache   = target index 0 absent
   readahead            = synchronous readahead covers target folio
   extent               = logical block 0 mapped to existing physical storage
   user buffer          = mapped and writable
   partition            = /dev/sda1 starts at whole-disk LBA 2048
   completion result    = 4096 bytes copied; file->f_pos = 4096

磁盘 logical-sector size、SCSI READ(6/10/16) 选择以及 ATA DMA/NCQ negotiation 没有被无依据写死；相关真实分支均在 AHCI submission/completion 主线重新汇合。

完整控制流
----------

::

   userspace read(fd, buf, 4096)
   → entry_SYSCALL_64
   → do_syscall_64 / __x64_sys_read
   → ksys_read / fd position guard
   → vfs_read / new_sync_read
   → ext4_file_read_iter
   → generic_file_read_iter / filemap_read
   → cold page-cache miss
   → synchronous readahead
   → ext4_mpage_readpages / ext4_map_blocks
   → READ bio
   → submit_bio_noacct
   → /dev/sda1 partition remap
   → blk_mq_submit_bio
   → blk-mq request and tag
   → SCSI READ CDB
   → libata ATA DMA or NCQ taskfile
   → dma_map_sg
   → AHCI H2D FIS / PRDT / command header
   → PxCI[tag] = 1

   → device executes ATA READ
   → AHCI DMA writes page-cache folio
   → AHCI completion interrupt
   → compare software active mask with PxCI/PxSACT
   → ata_qc_complete
   → dma_unmap_sg
   → ata_scsi_qc_complete / scsi_done
   → blk_mq_complete_request
   → scsi_complete / scsi_finish_command
   → blk_update_request
   → bio_endio
   → ext4 mpage_end_io
   → folio_end_read(folio, true)
   → PG_uptodate set / PG_locked cleared / waiter wake

   → reader task retries filemap lookup
   → copy_folio_to_iter(user buffer)
   → ki_pos = 4096
   → local pos = 4096
   → file->f_pos = 4096
   → pt_regs->ax = 4096
   → syscall_exit_to_user_mode
   → SYSRETQ or IRETQ
   → CPL 3 userspace continuation

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* 当前执行者：完成 ``read()`` 后的 userspace task；
* CPU mode：x86-64 CPL 3；
* syscall result：``RAX = 4096``；
* user buffer：含文件 offset 0..4095 的数据；
* ``file->f_pos``：4096；
* target folio：仍位于 page cache，uptodate、unlocked；
* bio：已经完成并释放；
* blk-mq request/tag：已经完成并释放；
* SCSI command：已经完成；
* ATA queued command：已经完成，active tag 已清理；
* AHCI command slot：该 command 已结束；
* 固定 ``read()`` cold-miss 主线：完整闭环。

关键边界
--------

#. AHCI DMA 的目标是 page-cache folio，不是用户 ``buf``。
#. ``PxCI[tag]`` 清除只证明硬件 command 不再 active；folio 状态必须继续经过 libata、SCSI、blk-mq、bio 和 ext4 completion。
#. ``folio_end_read(folio, true)`` 同时发布 uptodate 状态、unlock 并唤醒等待者。
#. waiter 被 wake 只表示可运行，何时取得 CPU 由 scheduler 决定。
#. ``copy_folio_to_iter()`` 才执行 page cache 到用户 buffer 的复制。
#. ``access_ok()`` 不保证真正 user copy 一定成功；固定场景另行保证 buffer 在 copy 期间有效。
#. ``ki_pos``、local ``pos`` 与共享 ``file->f_pos`` 是分层更新的三个位置状态。
#. clean native frame 通常走 ``SYSRETQ``，不满足条件时走 ``IRETQ``。

下一任务
--------

下一条运行期场景尚未选定。不能把另一个 syscall 假装成这次 ``read()`` 的自动后续。

开始下一批前必须固定：

#. userspace syscall 和参数；
#. 文件、进程、内存或 socket 对象的初始状态；
#. cache、mapping、锁与并发条件；
#. 固定 filesystem/device/network 路径；
#. 成功或错误分支；
#. 章节终止边界。

buffered ext4 ``write(fd, buf, 4096)`` 是可用候选，可覆盖 user copy、page-cache dirty、ext4 journaling、writeback 与后续 storage submission；目前只记录为候选，尚未正式选定。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。