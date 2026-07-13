# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-091
```

启动主线已完结。两个运行期实验均已闭环：

- `read(fd, buf, 4096)` cold page-cache miss；
- `O_SYNC write(fd, buf, 4096)` buffered ext4 overwrite。

最新三章：

- `LK-WRITE-089`：ext4 fsync 怎样选择 fast commit 或完整 JBD2 commit？
- `LK-WRITE-090`：ext4 barrier 怎样把 journal 顺序落实到设备 cache？
- `LK-WRITE-091`：O_SYNC write 怎样提交 file position 并返回用户态？

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

## 已完成 O_SYNC 场景

```text
userspace call       = write(fd, buf, 4096)
ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
open flags           = O_WRONLY | O_SYNC
file                 = regular ext4 file on /dev/sda1
initial file position= 0
final file position  = 4096
file size            = at least 4096 bytes
filesystem block     = 4096 bytes
write type           = full-block overwrite, not extending
extent               = existing initialized mapped logical block 0
I/O mode             = buffered; not O_DIRECT; not DAX
ext4 mode            = journal enabled, data=ordered, delalloc enabled
excluded             = inline data, fscrypt, fs-verity, atomic write
failure policy       = no copy, writeback, journal, flush or storage error
```

完整结果：

```text
userspace RAX       = 4096
file->f_pos         = 4096
target folio        = clean, uptodate, unlocked, PG_writeback=0
data I/O            = complete
journal requirement = satisfied by already-committed, fast commit, or full JBD2 commit
barrier requirement = satisfied by commit barrier or standalone FLUSH CACHE when enabled and needed
freeze protection   = released
fd position guard   = released
```

## 当前精确状态

```text
system_state     = SYSTEM_RUNNING
current executor = original writer task
CPU mode         = x86-64 CPL 3
current location = userspace immediately after successful O_SYNC write
runtime scenario = none selected
next entry       = unselected
```

不要把任意后续 syscall伪装成 O_SYNC write的自动时间线后续。

## 下一建议场景

下一批默认选择单线程 x86-64 用户进程直接执行 native `fork()` syscall，除非用户明确指定其他方向。

建议固定：

```text
userspace call      = native fork() syscall
process             = single-threaded userspace process
parent state        = normal running task with private user mm
signals             = no pending signal; default fork success path
ptrace/seccomp      = disabled for the scenario
namespaces/cgroups  = inherited without creating new namespaces
files/fs/sighand    = copied with ordinary fork semantics, not CLONE_* sharing
memory              = private anonymous and file-backed VMAs; enough memory
failure policy      = no RLIMIT_NPROC, PID exhaustion, allocation failure, fatal signal or LSM denial
```

从固定源码核对实际调用链后，预计连续追踪：

```text
entry_SYSCALL_64
→ __x64_sys_fork
→ kernel_clone
→ copy_process
→ dup_task_struct
→ copy_creds / copy_files / copy_fs / copy_sighand / copy_signal
→ copy_mm
→ dup_mm / dup_mmap
→ copy_page_range
→ page-table write-protect / COW setup
→ alloc_pid
→ copy_thread
→ tasklist and PID publication
→ wake_up_new_task
→ scheduler first runs child
→ parent returns child PID
→ child returns 0 through ret_from_fork
```

是否拆成上述精确函数，必须以固定 commit源码为准。不要从 glibc wrapper推断内核入口；场景直接规定 native `fork` syscall。

## 必须保持的技术边界

1. 不同运行期实验之间不是自动连续时间线。
2. fork创建新 task与 exec替换当前 image是不同机制。
3. task_struct、PID、mm、files、fs、sighand、signal、credentials分别说明复制或共享语义。
4. 页表复制与物理页复制不同；普通 fork主要建立 COW，不立即复制所有用户 data pages。
5. parent与 child从同一次 syscall获得不同返回值，但由不同 task执行。
6. child首次运行入口、`ret_from_fork` 与返回用户态必须按 x86 fixed source说明。
7. scheduler enqueue不等于 child已经运行。
8. 遇到配置或运行时分支，保留条件，不凭空写死。

## 连续叙事

每一段必须交代：当前执行者、CPU mode、关键数据结构、当前动作建立的条件、下一控制入口，以及固定源码依据。

不能使用“复制进程”“建立 COW”“调度 child”这样的概括跳过对象创建、引用关系、页表权限变化和控制权交接。

## 章节边界

章节不按 Roadmap 条目机械切分。遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem 交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 固定新的运行期场景；
3. 读取本章涉及的固定源码与规范；
4. 确定自然边界；
5. 写完并核对章节；
6. 更新目录、STATE、manifest、README 和接续入口；
7. 从最新状态继续。

遇到固定源码无法确认、重大平台分叉、仓库写入失败或达到场景终点时停止。

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
