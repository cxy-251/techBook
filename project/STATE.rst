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

最新三章：

#. ``LK-OPEN-104``：openat() 怎样保留 fd 并把 /work/demo.txt 解析成 negative dentry？
#. ``LK-OPEN-105``：ext4_create() 怎样分配 inode 并把 demo.txt 写进目录？
#. ``LK-OPEN-106``：VFS 怎样打开新 inode、发布 fd 6 并让 openat() 返回？

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
#. parent ext4 ``openat(O_CREAT|O_EXCL)`` create-open。

openat 固定场景
---------------

::

   current task       = parent after wait4 reaped child
   userspace call     = openat(AT_FDCWD, "/work/demo.txt", O_CREAT|O_EXCL|O_WRONLY, 0644)
   fd table           = 0..5 occupied; descriptor 6 is lowest free
   O_CLOEXEC          = absent
   umask              = 0022
   filesystem         = writable ext4 /dev/sda1, journal enabled, data=ordered
   parent directory   = /work, mode 0755, current uid owner, non-sticky
   target             = absent from dcache and ext4 directory before call
   directory layout   = one cached 4 KiB non-indexed block with free dirent space
   metadata cache     = directory block, inode bitmap, group descriptor and inode table resident
   sync policy        = no O_SYNC, sync mount, S_DIRSYNC or explicit fsync
   failure policy     = no race, permission failure, LSM denial, ENOSPC or I/O error

完整控制流
----------

::

   userspace openat
   → entry_SYSCALL_64 / __x64_sys_openat
   → do_sys_open / do_sys_openat2
   → build_open_flags
   → FD_ADD reserves fd 6
   → alloc_empty_file
   → path_init at process root
   → RCU link_path_walk through cached /work
   → O_EXCL final component leaves RCU walk
   → mnt_want_write / inode_lock(/work)
   → lookup_open
   → d_lookup miss / d_alloc_parallel
   → ext4_lookup scans cached directory block
   → negative dentry /work/demo.txt
   → ext4_create
   → start JBD2 metadata handle
   → allocate ext4 inode bitmap bit
   → update group descriptor and inode table record
   → initialize size-0 extent inode
   → ext4_add_entry writes demo.txt dirent into cached /work block
   → d_instantiate_new turns dentry positive
   → ext4_journal_stop without forced commit wait
   → release parent inode lock and mount write hold
   → do_open / vfs_open / do_dentry_open
   → file_get_write_access / ext4_file_open
   → FMODE_OPENED | FMODE_CAN_WRITE
   → fd_install(6, file)
   → syscall return RAX=6

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU mode：x86-64 CPL 3；
* ``openat`` result/RAX：6；
* fd 6：published，close-on-exec bit clear；
* ``struct file``：write-only、opened、``f_pos=0``；
* pathname：``/work/demo.txt``；
* dentry：positive；
* inode：ext4 regular 0644，nlink 1，size 0；
* file data blocks：0；
* parent directory lock：released；
* mount write hold：released；
* create metadata：已加入JBD2 transaction；
* journal commit/durability：尚未由本场景强制；
* storage I/O：本场景没有发生；
* open/create scenario：complete；
* next runtime scenario：unselected。

关键边界
--------

#. ``FD_ADD`` 先reserve fd，再执行pathname lookup与open。
#. reserved slot的 ``open_fds`` bit已设置，但 ``fd[6]`` 在publish前仍为NULL。
#. ``O_EXCL`` final lookup在parent directory inode lock下原子完成。
#. negative dentry是已确认不存在的name缓存对象。
#. ext4分配inode不会自动分配file data block。
#. ``d_instantiate_new`` 是negative dentry变positive的内存可见边界。
#. ``ext4_journal_stop`` 不等于transaction已经durable。
#. ``fd_install`` 是完整 ``struct file`` 对fd lookup可见的publication边界。

下一任务
--------

当前没有已选定场景。优先候选是parent使用fd 6首次写入新文件：

::

   write(fd6, buf, 4096)
   → page-cache folio allocation
   → delayed-allocation reservation
   → size grows from 0 to 4096
   → dirty folio
   → writeback allocates first physical extent
   → data bio + metadata transaction
   → optional fsync durability

开始前必须固定是否使用普通write后显式fsync、extent allocation目标、cache状态、writeback触发者和失败策略。
