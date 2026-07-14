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
LK-EXIT-101..LK-EXIT-103
LK-OPEN-104..LK-OPEN-106
```

七个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 openat create-open。

最新三章：

- `LK-OPEN-104`：openat() 怎样保留 fd 并把 /work/demo.txt 解析成 negative dentry？
- `LK-OPEN-105`：ext4_create() 怎样分配 inode 并把 demo.txt 写进目录？
- `LK-OPEN-106`：VFS 怎样打开新 inode、发布 fd 6 并让 openat() 返回？

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

## 已完成 openat 固定场景

```text
current task       = parent after successful wait4 reap
userspace call     = openat(AT_FDCWD, "/work/demo.txt", O_CREAT|O_EXCL|O_WRONLY, 0644)
fd state           = fd 0..5 occupied; fd 6 lowest free
O_CLOEXEC          = absent
umask              = 0022
filesystem         = writable ext4 /dev/sda1, journal enabled, data=ordered
parent directory   = /work, owner current uid, mode 0755, non-sticky
lookup state       = root and /work cached; demo.txt absent from dcache and directory
layout              = one cached non-indexed 4 KiB directory block with free space
metadata cache     = inode bitmap, group descriptor, inode table and directory block resident
sync policy        = no O_SYNC, sync mount, S_DIRSYNC or fsync
failure policy     = no race, permission/LSM failure, ENOSPC, allocation or I/O error
```

## 已执行控制流

```text
userspace openat
→ entry_SYSCALL_64 / __x64_sys_openat
→ do_sys_open / do_sys_openat2
→ build_open_flags
→ FD_ADD / alloc_fd reserves fd 6
→ alloc_empty_file
→ path_init from root
→ link_path_walk through cached /work
→ O_EXCL forces locked final lookup
→ mnt_want_write / inode_lock(/work)
→ lookup_open
→ dcache miss / d_alloc_parallel
→ ext4_lookup scans cached directory block
→ negative dentry
→ ext4_create
→ ext4_new_inode_start_handle
→ JBD2 metadata handle
→ allocate inode bitmap bit
→ update group descriptor and inode-table record
→ initialize regular extent inode, size 0, blocks 0
→ ext4_add_nondir / ext4_add_entry
→ write demo.txt dirent into cached directory block
→ d_instantiate_new
→ ext4_fc_track_create
→ ext4_journal_stop without forced commit wait
→ release directory lock and mount write hold
→ do_open / vfs_open / do_dentry_open
→ file_get_write_access
→ ext4_file_open
→ FMODE_OPENED | FMODE_CAN_WRITE
→ fd_install(6, file)
→ syscall exit, userspace RAX=6
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = openat create-open complete
current executor   = parent
CPU mode           = x86-64 CPL 3
openat return      = 6
fd 6               = published; close-on-exec clear
struct file        = write-only, opened, f_pos=0
path               = /work/demo.txt
dentry             = positive
inode              = ext4 regular 0644, nlink=1, size=0
data blocks         = 0
parent dir lock     = released
mount write hold    = released
create metadata     = attached to JBD2 transaction
durability          = not forced by openat return
storage I/O         = none in this scenario
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. `FD_ADD` reserve fd在pathname lookup之前。
2. reservation阶段 `open_fds[6]=1`，但 `fd[6]=NULL`。
3. absolute pathname不使用 `AT_FDCWD` 作为lookup起点。
4. `O_EXCL` final component必须在parent inode lock下确认不存在并创建。
5. negative dentry不是错误值。
6. ext4 inode create不分配file data block。
7. `d_instantiate_new` 发布positive dentry/inode关系。
8. `ext4_journal_stop` 不等于metadata durable。
9. `fd_install` 是完整file对象对fd readers可见的publication边界。

## 下一建议场景

优先候选是对fd 6首次写入4 KiB，并显式fsync：

```text
write(fd6, buf, 4096)
→ allocate page-cache folio
→ ext4 delayed-allocation reservation
→ dirty folio; i_size=4096
→ write returns before block allocation
→ fsync / writeback
→ allocate first extent
→ data bio completion
→ journal transaction and barrier
→ fsync return
```

开始前必须固定：write是否独立于fsync、delalloc cluster reservation、physical extent连续性、writeback触发者、journal transaction关系、cache状态和无ENOSPC/I/O failure策略。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
