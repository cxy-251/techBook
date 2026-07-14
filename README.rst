techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第九十二章：x86-64 的 fork() 怎样创建一个尚不可运行的 task_struct？ <docs/tracks/linux-kernel/92-x86-fork-builds-inactive-task.rst>`_
* `第九十三章：copy_process() 怎样复制资源并建立 COW 子进程？ <docs/tracks/linux-kernel/93-copy-process-builds-cow-child.rst>`_
* `第九十四章：scheduler 怎样启动 child，并让 fork() 在父子进程返回不同结果？ <docs/tracks/linux-kernel/94-fork-parent-and-child-return.rst>`_

固定来源
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定 commit 的真实版本是 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 属于历史显示标签错误；源码事实以固定 commit 为准。

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094

运行期实验
----------

已经完整闭环：

#. ``read(fd, buf, 4096)`` cold page-cache miss；
#. ``O_SYNC write(fd, buf, 4096)`` buffered ext4 overwrite；
#. native x86-64 ``fork()``。

fork 主线：

::

   userspace fork()
   → entry_SYSCALL_64 / __x64_sys_fork
   → kernel_clone / copy_process
   → new task_struct and kernel stack
   → independent files/fs/sighand/signal/mm
   → dup_mmap / copy_page_range
   → parent and child read-only COW PTEs
   → PID and process-tree publication
   → wake_up_new_task
   → parent returns child PID
   → child ret_from_fork_asm / IRETQ
   → child returns 0

当前状态
--------

parent与 child均已回到 CPL 3。parent观察到 child PID，child观察到 0。两者拥有不同 ``task_struct``、kernel stack、``mm_struct`` 和页表根；固定 private anonymous folio仍由父子只读 PTE共享，普通 fork没有立即复制其 4096-byte内容。

下一条 runtime scenario尚未选择。优先候选是 child对该 private anonymous地址执行一次 userspace store，追踪 x86 protection fault、``do_user_addr_fault()``、``handle_mm_fault()`` 与真正的 COW folio复制。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
