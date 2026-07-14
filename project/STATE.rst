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

最新三章：

#. ``LK-EXEC-098``：x86-64 的 execve() 怎样打开静态 ELF 并进入 load_elf_binary()？
#. ``LK-EXEC-099``：begin_new_exec() 怎样替换旧 mm 并建立静态 ELF 映射？
#. ``LK-EXEC-100``：start_thread() 怎样让 execve 进入新静态 ELF 的第一条指令？

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
#. child static ELF ``execve()``。

exec 固定场景
-------------

::

   current task       = fork child after completed COW store
   userspace call     = execve("/bin/static-demo", argv, envp)
   argv               = ["/bin/static-demo", "cow-complete"]
   envp               = ["LANG=C", "PATH=/bin"]
   executable         = ext4 regular 0755 x86-64 static non-PIE ET_EXEC
   interpreter        = none; no PT_INTERP
   credentials        = no setuid, setgid or file capabilities
   ptrace/seccomp     = disabled
   close-on-exec      = fd 5 has FD_CLOEXEC
   cache state        = path metadata, ELF headers, phdrs and entry text folio resident
   failure policy     = no lookup, permission, allocation, ELF, LSM or fault failure

完整控制流
----------

::

   userspace execve
   → entry_SYSCALL_64 / __x64_sys_execve
   → do_execveat_common
   → do_open_execat
   → alloc_bprm / bprm_mm_init
   → new temporary stack VMA
   → copy argv and envp from old mm into bprm mm
   → bprm_execve
   → prepare credentials / check unsafe state
   → search_binary_handler
   → prepare_binprm / cache-hit ELF header read
   → load_elf_binary
   → static ET_EXEC validation; no PT_INTERP
   → begin_new_exec / point_of_no_return
   → de_thread no-op for single-threaded child
   → exec_mmap
   → current->mm = new exec mm
   → do_close_on_exec closes fd 5
   → reset architecture and caught signal handlers
   → commit non-privileged credentials
   → setup_new_exec releases old child mm
   → setup_arg_pages
   → mmap PT_LOAD segments
   → establish BSS, brk, argc/argv/envp/auxv
   → finalize_exec
   → start_thread rewrites pt_regs with new RIP/RSP
   → syscall exit to ELF e_entry
   → missing executable PTE instruction #PF
   → filemap_fault cache hit
   → install read-only executable file PTE
   → minor-fault accounting
   → IRETQ retries instruction fetch
   → first instruction at static ELF e_entry executes

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current task：仍是原fork child；
* PID/TGID：exec前后不变；
* CPU mode：x86-64 CPL 3；
* current RIP：``/bin/static-demo`` 的ELF ``e_entry``；
* current mm：new executable mm；
* old child mm：已释放；
* parent mm：不变；
* old child COW mapping：已销毁；
* fd 5：已由close-on-exec关闭；
* 其他非-CLOEXEC fd：保留；
* caught signal handlers：已reset；
* credentials：已重新提交，无提权变化；
* entry text VMA：private file-backed read+execute；
* entry PTE：present、user、young、read-only、executable；
* first instruction fault：minor，未发生storage I/O；
* successful execve：complete；
* next runtime scenario：unselected。

关键边界
--------

#. exec替换image和mm，不创建新task或PID。
#. ``bprm->mm`` 在 ``exec_mmap`` 前与旧 ``current->mm`` 同时存在。
#. ``begin_new_exec`` 后失败不能恢复旧image。
#. close-on-exec只处理带 ``FD_CLOEXEC`` 的descriptor。
#. ELF ``PT_LOAD`` mmap建立VMA，不保证PTE已经present。
#. static ELF无interpreter，entry来自自身 ``e_entry``。
#. successful exec不会返回旧call site；syscall-exit使用已改写的 ``pt_regs``。
#. 首次text instruction仍可产生cache-hit minor page fault。

下一任务
--------

当前没有已选定场景。优先候选是static child执行 ``_exit(42)``，parent再调用 ``wait4()`` 或 ``waitid()``：

::

   child _exit(42)
   → do_exit
   → exit_mm / exit_files / exit_fs
   → release task resources
   → exit_notify / SIGCHLD
   → EXIT_ZOMBIE
   → parent wait4
   → do_wait
   → reap child / release_task

开始前必须重新固定parent是否已在wait、child与parent调度顺序、返回status格式以及无ptrace/subreaper等条件。
