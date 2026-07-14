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
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109

最新三章：

#. ``LK-DELALLOC-107``：首次 buffered write 怎样只预留空间而不分配物理块？
#. ``LK-DELALLOC-108``：fsync() 怎样让 writeback 分配第一个 unwritten extent 并提交数据？
#. ``LK-DELALLOC-109``：data completion 怎样转换 extent，并让 fsync() 真正返回？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault；
#. child static ELF ``execve()``；
#. child ``_exit(42)`` 与 parent ``wait4()`` 回收；
#. ext4 ``openat(O_CREAT|O_EXCL)``；
#. 新文件首次delalloc buffered write与显式 ``fsync``。

本批固定场景
------------

::

   current task       = parent
   fd                 = 6, write-only, f_pos=0 before write
   path               = /work/demo.txt
   initial inode      = regular 0644, nlink=1, size=0, data blocks=0
   userspace calls    = write(6, buf, 4096); fsync(6)
   ext4 block/page    = 4 KiB
   mount              = data=ordered,delalloc,dioread_nolock,barrier
   bigalloc/inline    = disabled
   fast commit        = disabled
   quota              = disabled
   cache state        = page-cache index 0 absent; allocation metadata resident
   allocation         = one free physical block P
   background WB      = none before write returns
   failure policy     = no signal, ENOSPC, allocation, copy or I/O failure

完整控制流
----------

::

   write(6, buf, 4096)
   → __x64_sys_write / ksys_write / vfs_write
   → ext4_file_write_iter / ext4_buffered_write_iter
   → generic_perform_write
   → ext4_da_write_begin
   → allocate and attach page-cache folio index 0
   → ext4_da_map_blocks finds hole
   → reserve one cluster
   → extent-status tree delayed [0,1)
   → copy 4096 bytes from userspace
   → dirty folio
   → i_size=4096, i_disksize=0
   → write returns 4096, f_pos=4096

   fsync(6)
   → ext4_sync_file
   → file_write_and_wait_range
   → ext4_writepages / ext4_do_writepages
   → collect BH_Delay logical block 0
   → JBD2 EXT4_HT_WRITE_PAGE handle
   → ext4_map_blocks / allocator
   → reserve consumed; physical block P allocated
   → create one-block unwritten extent
   → map folio buffer to P
   → REQ_SYNC data bio
   → blk-mq / SCSI WRITE / libata / AHCI
   → successful data completion
   → ext4_end_bio defers completion
   → ext4_end_io_rsv_work
   → unwritten-to-written extent conversion
   → folio_end_writeback
   → full JBD2 commit
   → standalone blkdev_issue_flush
   → fsync returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU mode：x86-64 CPL 3；
* fd 6：仍打开，write-only；
* ``file->f_pos``：4096；
* pathname：``/work/demo.txt``；
* inode：ext4 regular 0644，nlink 1；
* ``i_size``：4096；
* ``i_disksize``：4096；
* ``i_blocks``：8个512-byte sectors；
* extent：logical block 0 → physical block ``P``，written；
* delayed reservation：0；
* page-cache folio：uptodate、clean、not under writeback；
* data request：complete并released；
* unwritten conversion：complete；
* target JBD2 transaction：committed；
* required device flush：complete；
* durability：create dirent、inode size、extent与4096-byte data满足本次fsync；
* home-block checkpoint：不要求已经完成；
* next runtime scenario：unselected。

关键边界
--------

#. page-cache folio allocation与physical block allocation相互独立。
#. delalloc reservation只改变空间accounting，write返回时没有physical block。
#. ``i_size`` 可以领先于 ``i_disksize``。
#. writeback消费reservation并建立unwritten extent。
#. unwritten extent防止data I/O失败时暴露stale block内容。
#. data completion与written conversion是两个阶段。
#. folio writeback直到conversion完成后才结束。
#. journal commit durable不等于metadata home-block checkpoint完成。
#. ``fsync`` 不改变file position，也不关闭fd。

下一任务
--------

优先候选是文件仍被fd 6打开时删除pathname，再关闭最后一个open reference：

::

   unlinkat(AT_FDCWD, "/work/demo.txt", 0)
   → pathname lookup finds positive dentry
   → lock /work and ext4_unlink
   → remove directory entry
   → inode nlink 1 → 0
   → add inode to ext4 orphan tracking
   → pathname no longer resolves, fd 6 remains valid
   → close(6)
   → file_close_fd / __fput
   → final inode eviction
   → free extent P, inode bitmap bit and inode object

开始前必须固定directory/inode cache、journal transaction、fd reference count、unlink与close之间是否发生额外I/O，以及无race/ENOSPC/I/O failure策略。
