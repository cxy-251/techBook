techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第七十一章：Linux 怎样释放 __init 内存并进入 SYSTEM_RUNNING？ <docs/tracks/linux-kernel/71-linux-frees-init-memory-and-enters-system-running.rst>`_
* `第七十二章：Linux 怎样选择用户态 init，并把可执行映像装入 PID 1？ <docs/tracks/linux-kernel/72-linux-selects-init-and-loads-userspace-image.rst>`_
* `第七十三章：x86 怎样让 PID 1 从 ret_from_fork 真正进入用户态？ <docs/tracks/linux-kernel/73-x86-returns-pid1-to-userspace.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d
   → PID 1 userspace init entry

固定 commit 的真实版本是 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 属于历史显示标签错误；源码事实以固定 commit 为准。

已经完成 ``LK-BOOT-001..LK-BOOT-073``。Linux 启动主线已追踪到：

::

   kernel_init()
   → async_synchronize_full()
   → free_initmem()
   → mark_readonly()
   → pti_finalize()
   → SYSTEM_RUNNING
   → choose init
   → kernel_execve()
   → ELF/script binary handler
   → START_THREAD()
   → ret_from_fork()
   → syscall_exit_to_user_mode()
   → PTI/FRED/iretq
   → PID 1 first userspace instruction

启动链已经到达自然终点。继续写作需要先固定一个运行期场景，例如 ``read()``、``openat()``、``fork()``、page fault、timer interrupt 或 block I/O，再从对应 syscall、exception 或 hardware interrupt 入口重新进入内核。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
