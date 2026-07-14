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

最新三章：

#. ``LK-FORK-092``：x86-64 的 fork() 怎样创建一个尚不可运行的 task_struct？
#. ``LK-FORK-093``：copy_process() 怎样复制资源并建立 COW 子进程？
#. ``LK-FORK-094``：scheduler 怎样启动 child，并让 fork() 在父子进程返回不同结果？

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

#. ``read(fd, buf, 4096)`` cold page-cache miss；
#. ``O_SYNC write(fd, buf, 4096)`` buffered ext4 overwrite；
#. native x86-64 ``fork()``。

fork 固定场景
-------------

::

   userspace call      = native fork() syscall number 57
   process             = single-threaded SCHED_NORMAL userspace process
   clone flags         = 0
   exit signal         = SIGCHLD
   ptrace/seccomp      = disabled for the scenario
   namespaces          = inherited; no CLONE_NEW*
   files/fs/signals    = ordinary fork copy semantics, no CLONE_* sharing
   memory              = private user mm with one present writable private anonymous 4 KiB folio
   special exclusions  = no THP, hugetlb, userfaultfd, pinning, swap, VM_DONTCOPY or VM_WIPEONFORK
   failure policy      = no pending signal, limit, PID, allocation, LSM, cgroup or scheduler failure

完整控制流
----------

::

   userspace fork()
   → entry_SYSCALL_64
   → x64_sys_call / __x64_sys_fork
   → kernel_clone_args: flags=0, exit_signal=SIGCHLD
   → kernel_clone
   → copy_process
   → signal serialization / pending-signal check
   → dup_task_struct
   → independent task_struct and kernel stack
   → copy_creds
   → sched_fork
   → TASK_NEW
   → copy_files: new files_struct and fd table
   → fd entries retain references to shared struct file objects
   → copy_fs
   → copy_sighand / copy_signal
   → copy_mm
   → dup_mm / dup_mmap
   → duplicate VMA Maple Tree
   → copy_page_range
   → write-protect parent private PTE
   → install read-only child private PTE
   → parent and child share anonymous folio through COW mappings
   → copy_namespaces: reference-share nsproxy
   → copy_thread
   → childregs->ax = 0
   → child first return address = ret_from_fork_asm
   → alloc_pid
   → PID and process-tree publication under tasklist_lock
   → copy_process returns child task
   → wake_up_new_task
   → TASK_RUNNING / runqueue enqueue
   → parent returns child PID through normal syscall exit
   → child first schedule enters ret_from_fork_asm
   → schedule_tail / syscall_exit_to_user_mode
   → child IRETQ to userspace with RAX=0

当前精确状态
------------

parent：

* CPU mode：调度运行时为 x86-64 CPL 3；
* fork返回值：child PID；
* mm/page-table root：parent独立对象。

child：

* CPU mode：调度运行时为 x86-64 CPL 3；
* fork返回值：0；
* PID/TGID：新分配的 child PID；
* ``real_parent``：parent；
* ``exit_signal``：``SIGCHLD``；
* 首次用户态进入：``ret_from_fork_asm`` → IRETQ。

共同状态：

* parent与 child ``task_struct``、kernel stack、cred、files、fs、sighand、signal、mm和页表根均为不同对象；
* 对应 fd entries仍引用相同 ``struct file`` open descriptions；
* namespace objects相同；
* 固定 private anonymous folio仍由父子只读 PTE共享；
* 普通 fork没有立即复制该 folio的 4096-byte内容；
* parent或 child谁先执行 fork后的第一条用户指令没有固定顺序；
* fork runtime scenario：complete。

关键边界
--------

#. ``TASK_NEW``、task publication与 runqueue enqueue是三个不同阶段。
#. files_struct独立不等于 open file description独立。
#. 新 mm和新页表根不等于所有物理数据页已经复制。
#. COW建立需要同时 write-protect parent与 child的 private PTE。
#. child ``RAX=0`` 由 ``copy_thread()`` 预置，不重新执行 syscall入口。
#. parent通过普通 syscall return返回 child PID；child首次用户态返回经过 ``ret_from_fork_asm`` 与 IRETQ。
#. scheduler不保证 parent或 child谁先运行。
#. fork结束后不能虚构任一进程下一条用户指令。

下一任务
--------

当前没有已选定的 runtime scenario。优先候选是一个独立的 child COW write-fault实验：child对固定 private anonymous地址执行一次 userspace store。

预期入口需重新从固定源码核对：

::

   child userspace store to read-only private PTE
   → x86 #PF with user/write/protection error bits
   → exc_page_fault
   → do_user_addr_fault
   → VMA lookup and permissions
   → handle_mm_fault
   → __handle_mm_fault
   → do_wp_page
   → wp_page_copy or exclusive-page reuse branch
   → allocate/charge/copy anonymous folio when required
   → reverse-map and RSS updates
   → install writable child PTE
   → TLB update
   → retry and complete original userspace store

开始前必须固定 folio reference/mapcount状态，确保真正进入复制分支；不能只凭“fork后写入”假设一定复制，因为 exclusive-page reuse等优化可能改变结果。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
