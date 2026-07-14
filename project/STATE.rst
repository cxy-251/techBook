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
   LK-UNLINK-110..LK-UNLINK-112

最新三章：

#. ``LK-UNLINK-110``：unlinkat() 怎样锁住父目录并进入 ext4_unlink()？
#. ``LK-UNLINK-111``：ext4_unlink() 怎样删除名称，却让 fd 6 继续访问 inode？
#. ``LK-UNLINK-112``：close(6) 怎样触发最后一次 __fput() 并回收 ext4 inode？

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
#. 新文件首次delalloc buffered write与显式 ``fsync``；
#. open-unlinked ext4文件的final close与inode/extent回收。

本批固定场景
------------

::

   current task       = parent
   userspace calls    = unlinkat(AT_FDCWD, "/work/demo.txt", 0); close(6)
   initial fd         = 6, sole file reference, write-only, f_pos=4096
   initial inode      = regular 0644, nlink=1, size=4096, i_blocks=8
   initial extent     = logical block 0 -> physical block P, written
   initial folio      = uptodate, clean, no writeback
   mount              = data=ordered,barrier; fast commit disabled
   extra references   = no dup, mmap, SCM_RIGHTS, io_uring, other open or hardlink
   cache state        = parent/target dentries, inodes, directory and allocation metadata resident
   background commit  = disabled during both syscalls
   failure policy     = no race, delegation, LSM, journal, allocation or I/O failure

完整控制流
----------

::

   unlinkat(AT_FDCWD, "/work/demo.txt", 0)
   → __x64_sys_unlinkat
   → filename_unlinkat
   → filename_parentat returns /work + demo.txt
   → mnt_want_write
   → start_dirop locks /work and gets positive dentry
   → ihold(target inode)
   → vfs_unlink
   → lock target inode
   → ext4_unlink / __ext4_unlink
   → ext4_find_entry cache hit
   → start EXT4_HT_DIR JBD2 handle
   → ext4_delete_entry removes demo.txt dirent
   → update /work mtime/ctime
   → drop_nlink: 1 -> 0
   → ext4_orphan_add
   → mark target inode dirty
   → journal_stop without forced commit
   → d_delete_notify removes name from normal lookup
   → release target and parent locks
   → temporary iput does not evict because fd 6 remains
   → unlinkat returns 0

   close(6)
   → __x64_sys_close
   → file_close_fd clears fdtable slot 6
   → filp_flush
   → fput_close_sync
   → final __fput
   → ext4_release_file
   → put_file_access
   → final dput / iput
   → ext4_evict_inode
   → truncate_inode_pages_final drops clean folio
   → start EXT4_HT_TRUNCATE transaction
   → i_size = 0
   → ext4_truncate / ext4_ext_remove_space
   → remove logical extent and queue physical P for transaction-protected free
   → ext4_orphan_del
   → set i_dtime
   → ext4_free_inode clears inode bitmap metadata
   → ext4_clear_inode
   → file_free
   → close returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU mode：x86-64 CPL 3；
* ``close`` result/RAX：0；
* fd 6：free，可被重新分配；
* pathname ``/work/demo.txt``：不存在；
* target ``struct file``：final ``__fput`` complete；
* target dentry：已释放；
* target inode：ext4 eviction complete，不再可访问；
* page-cache folio：已从mapping移除；
* logical extent [0,1)：已删除；
* physical block P：位于JBD2 transaction的pending-free保护下；
* inode bitmap bit：已在journaled metadata中清除；
* orphan tracking：已删除；
* forced JBD2 commit：未发生；
* forced device flush：未发生；
* deletion durability：close返回不保证transaction已经stable；
* next runtime scenario：unselected。

关键边界
--------

#. unlink删除namespace name，不删除仍被open fd引用的inode。
#. ``i_nlink=0`` 与inode reference count是两个独立状态。
#. orphan tracking保护已unlink但仍open的崩溃窗口。
#. ``file_close_fd`` 先撤销descriptor publication，file teardown随后进行。
#. close普通文件不隐含fsync。
#. 最后一个 ``fput_close_sync`` 在当前syscall context同步执行 ``__fput``。
#. clean page-cache folio可以在eviction中无I/O删除。
#. extent free、orphan removal与inode bitmap free位于journal transaction中。
#. block/inode在transaction commit前不能视为已安全复用。
#. VFS对象不可访问与slab内存最终经过RCU重用不是同一时刻。

下一任务
--------

当前没有已选定场景。优先候选是parent执行10毫秒monotonic sleep：

::

   clock_nanosleep(CLOCK_MONOTONIC, 0, {0, 10ms}, NULL)
   → convert userspace timespec
   → hrtimer setup and enqueue
   → current TASK_INTERRUPTIBLE
   → schedule away
   → local APIC timer interrupt
   → hrtimer interrupt and callback
   → try_to_wake_up(parent)
   → scheduler selects parent
   → clock_nanosleep returns 0

开始前必须固定CPU数量、timer base、clockevent模式、是否迁移CPU、signal状态、调度竞争者与实际expiry/overrun边界。
