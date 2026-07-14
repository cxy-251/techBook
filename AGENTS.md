# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-091
LK-FORK-092..LK-FORK-094
LK-COW-095..LK-COW-097
LK-EXEC-098..LK-EXEC-100
```

五个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve。

最新三章：

- `LK-EXEC-098`：x86-64 的 execve() 怎样打开静态 ELF 并进入 load_elf_binary()？
- `LK-EXEC-099`：begin_new_exec() 怎样替换旧 mm 并建立静态 ELF 映射？
- `LK-EXEC-100`：start_thread() 怎样让 execve 进入新静态 ELF 的第一条指令？

## 固定实现

```text
SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
GNU GRUB release  = 2.14
GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
GRUB target       = i386-pc
Linux release     = 7.2-rc1
Linux repository  = gregkh/linux
Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d
partition table   = MBR
first partition   = LBA 2048, ext4
storage           = q35 ICH9 AHCI SATA port 0
```

旧章节中的 `Linux 6.12.95` 是历史显示标签错误；固定commit始终是Linux 7.2-rc1。

## 已完成 exec 固定场景

```text
current task       = fork child after COW store
userspace call     = execve("/bin/static-demo", argv, envp)
argv               = ["/bin/static-demo", "cow-complete"]
envp               = ["LANG=C", "PATH=/bin"]
executable         = ext4 regular 0755 x86-64 static non-PIE ET_EXEC
PT_INTERP          = absent
credentials        = no setuid/setgid/file capabilities
ptrace/seccomp     = disabled
close-on-exec      = fd 5 has FD_CLOEXEC
cache state        = pathname metadata, ELF headers, phdrs and entry text folio resident
failure policy     = no lookup, permission, allocation, ELF, LSM, signal or page-fault failure
```

## 已执行 exec 控制流

```text
userspace execve
→ entry_SYSCALL_64 / __x64_sys_execve
→ do_execveat_common
→ do_open_execat
→ alloc_bprm / bprm_mm_init
→ bprm temporary stack VMA
→ copy argv/envp from old mm into bprm mm
→ bprm_execve / prepare creds
→ search_binary_handler
→ prepare_binprm / load_elf_binary
→ validate static ET_EXEC; no interpreter
→ begin_new_exec / point_of_no_return
→ exec_mmap
→ current->mm = new mm
→ close fd 5 through do_close_on_exec
→ reset thread and caught signal handlers
→ commit non-privileged creds
→ setup_new_exec / release old child mm
→ setup_arg_pages
→ map static PT_LOAD VMAs
→ BSS / brk / argc / argv / envp / auxv
→ finalize_exec
→ start_thread rewrites current pt_regs
→ syscall exit to ELF e_entry
→ missing text PTE instruction #PF
→ filemap_fault cache hit
→ install executable PTE
→ minor fault accounting
→ IRETQ retry
→ first instruction at e_entry executes
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = static execve complete
current executor   = original fork child task
CPU mode           = x86-64 CPL 3
PID/TGID            = unchanged by exec
current image       = /bin/static-demo
current RIP         = ELF e_entry, first instruction executing
current mm          = new executable mm
old child mm        = released
parent mm           = unchanged
fd 5                = closed by FD_CLOEXEC
other fds           = retained unless CLOEXEC
signal handlers     = caught handlers reset
credentials         = committed without privilege elevation
entry VMA           = ext4 file-backed private read+execute
entry PTE           = present, user, young, read-only, executable
entry fault         = cache-hit minor instruction fault
next entry          = unselected runtime scenario
```

## 下一建议场景

优先候选是static child调用 `_exit(42)`，parent随后执行 `wait4()`：

```text
child _exit(42)
→ __x64_sys_exit / do_exit
→ exit_signals
→ exit_mm
→ exit_files / exit_fs
→ exit_notify
→ SIGCHLD to parent
→ EXIT_ZOMBIE
→ parent wait4
→ do_wait
→ copy exit status/rusage
→ release_task
→ PID/task final release
```

开始前必须固定：

```text
parent state        = running or already sleeping in wait4; choose one
child exit code     = 42
threading           = both parent and child single-threaded
ptrace/subreaper    = disabled
children            = only this child
signals             = default SIGCHLD disposition; no SA_NOCLDWAIT
wait options        = exact wait4/waitid arguments
failure policy      = no signal interruption or userspace copy fault
```

不要把exec描述为创建新进程；task/PID保留。不要把ELF mmap描述成已填满PTE。不要把successful exec写成返回旧call site。

## 连续叙事

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

## 章节边界与流程

遇到执行者、CPU mode、对象所有权或subsystem交接时换章。章节正文不添加上一章/下一章导航；资料使用可点击RST链接。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
