techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第九十八章：x86-64 的 execve() 怎样打开静态 ELF 并进入 load_elf_binary()？ <docs/tracks/linux-kernel/98-execve-opens-static-elf.rst>`_
* `第九十九章：begin_new_exec() 怎样替换旧 mm 并建立静态 ELF 映射？ <docs/tracks/linux-kernel/99-begin-new-exec-replaces-mm-and-maps-elf.rst>`_
* `第一百章：start_thread() 怎样让 execve 进入新静态 ELF 的第一条指令？ <docs/tracks/linux-kernel/100-exec-enters-new-static-elf-image.rst>`_

固定来源
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100

最新场景
--------

fork child执行静态 ``ET_EXEC``：

::

   execve("/bin/static-demo", argv, envp)
   → open executable / new bprm mm
   → copy argv and envp
   → search_binary_handler / load_elf_binary
   → begin_new_exec / current->mm replacement
   → close-on-exec / signal reset / credential commit
   → PT_LOAD VMAs / user stack / auxv
   → start_thread
   → first cached text instruction fault
   → execute ELF e_entry

当前task与PID保持不变，旧child mm已经释放，fd 5因 ``FD_CLOEXEC`` 关闭。新static程序位于CPL 3，已经开始执行 ``e_entry`` 第一条指令。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
