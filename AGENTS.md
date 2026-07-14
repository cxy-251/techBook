# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-091
LK-FORK-092..LK-FORK-094
```

启动主线已完结。三个运行期实验已闭环：

- `read(fd, buf, 4096)` cold page-cache miss；
- `O_SYNC write(fd, buf, 4096)` buffered ext4 overwrite；
- native x86-64 `fork()`。

最新三章：

- `LK-FORK-092`：x86-64 的 fork() 怎样创建一个尚不可运行的 task_struct？
- `LK-FORK-093`：copy_process() 怎样复制资源并建立 COW 子进程？
- `LK-FORK-094`：scheduler 怎样启动 child，并让 fork() 在父子进程返回不同结果？

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
kernel            = /boot/bzImage-7.2-rc1
initramfs         = /boot/initramfs-7.2-rc1.img
```

固定 Linux commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中的 `Linux 6.12.95` 是历史显示标签错误，不得改用真正的 `v6.12.95`。

## 已完成 fork 固定场景

```text
userspace call      = native x86-64 fork() syscall number 57
process             = single-threaded SCHED_NORMAL process
clone flags         = 0
exit signal         = SIGCHLD
ptrace/seccomp      = disabled for the scenario
signals             = no pending or fatal signal
namespaces          = inherited, no CLONE_NEW*
files/fs/signals    = ordinary fork semantics, no CLONE_* sharing
memory              = private user mm with one present writable private anonymous 4 KiB folio
special exclusions  = no THP, hugetlb, userfaultfd, pinning, swap, VM_DONTCOPY or VM_WIPEONFORK
failure policy      = no limit, PID, allocation, LSM, cgroup or scheduler failure
```

## 已执行 fork 控制流

```text
userspace fork()
→ entry_SYSCALL_64 / __x64_sys_fork
→ kernel_clone_args: flags=0, exit_signal=SIGCHLD
→ kernel_clone
→ copy_process
→ signal serialization
→ dup_task_struct
→ child task_struct and kernel stack
→ copy_creds
→ sched_fork / TASK_NEW
→ copy_files / copy_fs
→ copy_sighand / copy_signal
→ copy_mm
→ dup_mm / dup_mmap
→ duplicate VMA Maple Tree
→ copy_page_range
→ write-protect parent private PTE
→ install read-only child private PTE
→ parent/child share anonymous folio by COW
→ copy_namespaces: reference-share nsproxy
→ copy_thread
→ childregs->ax = 0
→ child first return address = ret_from_fork_asm
→ alloc_pid
→ tasklist/PID/process-tree publication
→ copy_process returns child task
→ wake_up_new_task
→ TASK_RUNNING and runqueue enqueue
→ parent returns child PID through normal syscall return
→ child first schedule enters ret_from_fork_asm
→ schedule_tail / syscall_exit_to_user_mode
→ child IRETQ to userspace with RAX=0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = fork complete
parent CPU mode    = CPL 3 when scheduled
parent fork result = child PID
child CPU mode     = CPL 3 when scheduled
child fork result  = 0
parent/child order = scheduler-dependent, not fixed
parent mm          = independent parent mm/page-table root
child mm           = independent child mm/page-table root
fixed anon folio   = still physically shared by read-only parent/child PTEs
physical page copy = not performed by ordinary fork
next entry         = unselected runtime scenario
```

Additional object relations:

```text
task_struct       = separate
kernel stack      = separate
cred              = separate object
files_struct      = separate
fd table          = separate
struct file       = shared references for corresponding inherited fds
fs_struct         = separate
sighand_struct    = separate
signal_struct     = separate
mm_struct         = separate
VMA objects       = separate
page-table roots  = separate
namespace objects = shared through nsproxy reference
```

## 下一建议场景

下一批默认选择独立的 child COW write-fault场景，除非用户明确指定其他方向。

开始前必须固定：

```text
current task         = child after fork
userspace action     = store one byte/word to the fixed private anonymous address
PTE state            = present, user, read-only, COW private mapping
folio state          = normal anonymous small folio
sharing state        = parent and child both still map the folio
map/ref state         = sufficient to prevent exclusive-page reuse optimization
VMA                   = VM_READ | VM_WRITE, private anonymous
special exclusions    = no THP, KSM, userfaultfd-wp, uffd missing, swap, migration, device-private entry, long-term pin
failure policy        = allocation and memcg charge succeed; no signal or OOM
```

预计从固定源码核对：

```text
child userspace store
→ x86 #PF with P=1, W/R=1, U/S=1
→ exc_page_fault
→ do_user_addr_fault
→ VMA lookup / access check
→ handle_mm_fault
→ __handle_mm_fault
→ handle_pte_fault
→ do_wp_page
→ wp_page_copy
→ allocate and charge new anonymous folio
→ copy old folio contents
→ anon rmap / RSS / memcg updates
→ install writable child PTE
→ flush/update TLB
→ return from #PF
→ CPU retries original store successfully
```

必须从 fixed commit确认当前函数名称和优化分支。不能只写“触发 COW 后复制一页”；要明确 fault error code、VMA锁、PTE锁、old/new folio、rmap、memcg、PTE replacement和 TLB语义。

## 必须保持的技术边界

1. 不同运行期实验之间不是自动连续时间线。
2. `TASK_NEW`、task publication和 runqueue enqueue是三个阶段。
3. files_struct独立不等于 open file description独立。
4. 新 mm和新页表根不等于立即复制所有物理页。
5. ordinary fork COW需要 write-protect parent与 child private PTE。
6. child `RAX=0`由 `copy_thread()`预置，不重新执行 syscall入口。
7. parent可能通过 SYSRETQ或 IRETQ返回；child首次 userspace entry经过 `ret_from_fork_asm` 与 IRETQ。
8. scheduler不保证 parent或 child谁先运行。
9. COW write fault可能存在 exclusive-page reuse；只有固定 sharing/mapcount条件后才能写死 `wp_page_copy`。
10. 物理页复制、页表替换、rmap更新、memcg charge和用户 store重试必须分开叙述。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode和运行环境；
- 关键代码与数据结构；
- 当前动作建立的条件；
- 下一控制入口；
- 固定源码文件、symbol或规范依据。

不能使用“复制进程”“触发 COW”“调度 child”这样的概括跳过对象关系、权限变化、锁、引用计数和控制权交接。

## 章节边界

章节不按 Roadmap 条目机械切分。遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem交接时换章。

每章末尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest和当前入口；
2. 固定新的运行期场景；
3. 读取本章涉及的 fixed source；
4. 确定自然边界；
5. 写完并核对章节；
6. 更新目录、STATE、manifest、README和接续入口；
7. 从最新状态继续。

遇到 fixed source无法确认、重大平台分叉、仓库写入失败或达到场景终点时停止。

## 状态语义

- `draft`：正文正在编写，或关键事实链尚未核对完整；
- `verified`：关键结论已依据固定源码或规范核对，章节仍在续写；
- `complete`：章节到达自然终点，关键事实已经核对。

## 接手顺序

1. `AGENTS.md`；
2. `project/STATE.rst`；
3. `docs/tracks/linux-kernel/index.rst`；
4. 已完成章节；
5. `manifests/tracks/linux-kernel.toml`；
6. `main` 最近的相关提交。
