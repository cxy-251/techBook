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
LK-DELALLOC-107..LK-DELALLOC-109
LK-UNLINK-110..LK-UNLINK-112
```

九个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 openat create-open、新文件首次delalloc write + fsync、open-unlinked文件的final close与回收。

最新三章：

- `LK-UNLINK-110`：unlinkat() 怎样锁住父目录并进入 ext4_unlink()？
- `LK-UNLINK-111`：ext4_unlink() 怎样删除名称，却让 fd 6 继续访问 inode？
- `LK-UNLINK-112`：close(6) 怎样触发最后一次 __fput() 并回收 ext4 inode？

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

## 已完成 unlink + close 固定场景

```text
current task       = parent
userspace calls    = unlinkat(AT_FDCWD, "/work/demo.txt", 0); close(6)
initial fd         = 6, sole file reference, write-only, f_pos=4096
initial inode      = regular 0644, nlink=1, size=4096, i_blocks=8
initial extent     = logical block 0 -> physical block P, written
initial folio      = uptodate, clean, no writeback
mount              = data=ordered,barrier; fast commit disabled
extra references   = no dup, mmap, SCM_RIGHTS, io_uring, other open or hardlink
cache state        = parent/target dentries, inodes, directory and allocation metadata resident
background commit  = disabled during both syscalls
failure policy     = no race, delegation, LSM, journal, allocation or I/O failure
```

## 已执行控制流

```text
unlinkat(AT_FDCWD, "/work/demo.txt", 0)
→ __x64_sys_unlinkat
→ filename_unlinkat
→ filename_parentat returns /work + demo.txt
→ mnt_want_write
→ start_dirop locks /work and gets positive dentry
→ ihold(target inode)
→ vfs_unlink
→ lock target inode
→ ext4_unlink / __ext4_unlink
→ ext4_find_entry cache hit
→ start EXT4_HT_DIR JBD2 handle
→ ext4_delete_entry removes demo.txt dirent
→ update /work mtime/ctime
→ drop_nlink: 1 -> 0
→ ext4_orphan_add
→ mark target inode dirty
→ journal_stop without forced commit
→ d_delete_notify removes name from normal lookup
→ release target and parent locks
→ temporary iput does not evict because fd 6 remains
→ unlinkat returns 0

close(6)
→ __x64_sys_close
→ file_close_fd clears fdtable slot 6
→ filp_flush
→ fput_close_sync
→ final __fput
→ ext4_release_file
→ put_file_access
→ final dput / iput
→ ext4_evict_inode
→ truncate_inode_pages_final drops clean folio
→ start EXT4_HT_TRUNCATE transaction
→ i_size = 0
→ ext4_truncate / ext4_ext_remove_space
→ remove logical extent and queue physical P for transaction-protected free
→ ext4_orphan_del
→ set i_dtime
→ ext4_free_inode clears inode bitmap metadata
→ ext4_clear_inode
→ file_free
→ close returns 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = open-unlinked file final close complete
current executor   = parent
CPU mode           = x86-64 CPL 3
close return        = 0
fd 6                = free and reusable
path                = /work/demo.txt absent
target struct file  = final __fput complete
target dentry       = released
target inode        = ext4 eviction complete and inaccessible
page-cache mapping  = removed
logical extent      = removed
physical block P    = pending-free under JBD2 transaction protection
inode bitmap bit    = cleared in journaled metadata
orphan tracking     = removed
forced commit       = none
forced device flush = none
durability          = close return does not guarantee transaction is stable
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. unlink删除namespace name，不删除仍被open fd引用的inode。
2. `i_nlink=0` 与inode reference count是两个独立状态。
3. orphan tracking保护已unlink但仍open的崩溃窗口。
4. `file_close_fd` 先撤销descriptor publication，file teardown随后进行。
5. close普通文件不隐含fsync。
6. 最后一个 `fput_close_sync` 在当前syscall context同步执行 `__fput`。
7. `ext4_release_file` 与 `ext4_evict_inode` 是不同阶段。
8. clean page-cache folio可以在eviction中无I/O删除。
9. extent free、orphan removal与inode bitmap free位于journal transaction中。
10. block/inode在transaction commit前不能视为已安全复用。
11. VFS对象不可访问与slab内存最终经过RCU重用不是同一时刻。

## 下一建议场景

优先候选是parent执行10毫秒monotonic sleep：

```text
clock_nanosleep(CLOCK_MONOTONIC, 0, {0, 10ms}, NULL)
→ convert userspace timespec
→ hrtimer setup and enqueue
→ current TASK_INTERRUPTIBLE
→ schedule away
→ local APIC timer interrupt
→ hrtimer interrupt and callback
→ try_to_wake_up(parent)
→ scheduler selects parent
→ clock_nanosleep returns 0
```

开始前固定：CPU数量、timer base、clockevent模式、是否迁移CPU、signal状态、调度竞争者、精确expiry与overrun策略。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
