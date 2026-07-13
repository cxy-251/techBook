# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-085
```

启动主线已完结；`read(fd, buf, 4096)` cold page-cache miss 已完整闭环。当前正在写独立的 ext4 `O_SYNC` buffered write 主线。

最新三章：

- `LK-WRITE-083`：x86-64 的 write() 怎样进入 ext4 buffered write？
- `LK-WRITE-084`：ext4 怎样把用户数据复制进 page-cache folio 并标脏？
- `LK-WRITE-085`：O_SYNC write 怎样进入 ext4 writeback？

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

## 当前 write 固定场景

```text
userspace call       = write(fd, buf, 4096)
ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
open flags           = O_WRONLY | O_SYNC
file                 = independent already-open regular ext4 file on /dev/sda1
initial file position= 0
file size            = at least 4096 bytes
filesystem block     = 4096 bytes
write type           = full-block overwrite, not extending
extent               = logical block 0 already initialized and mapped
I/O mode             = buffered; not O_DIRECT; not DAX
ext4 mode            = journal enabled, data=ordered, delayed allocation enabled
initial page cache   = target index 0 absent
user buffer          = mapped, readable, stable during copy
excluded             = inline data, fscrypt, fs-verity, atomic write
failure policy       = no ENOSPC, copy fault, freeze conflict, forced shutdown or injected I/O failure
```

该 write 场景独立于前一条 read；不要沿用 read 结束后的 page-cache folio。

## 已执行控制流

```text
userspace write(fd, buf, 4096)
→ entry_SYSCALL_64
→ do_syscall_64 / __x64_sys_write
→ ksys_write / fd position guard
→ vfs_write / new_sync_write
→ IOCB_SYNC + IOCB_DSYNC
→ ext4_file_write_iter
→ ext4_buffered_write_iter
→ inode_lock
→ ext4_write_checks
→ generic_perform_write
→ ext4_da_write_begin
→ allocate and lock page-cache folio
→ prepare existing mapped block
→ copy_folio_from_iter_atomic
→ ext4_da_write_end / block_write_end
→ folio dirty, uptodate, unlocked
→ iocb->ki_pos = 4096
→ inode_unlock
→ generic_write_sync
→ vfs_fsync_range(file, 0, 4095, datasync=0)
→ ext4_sync_file
→ file_write_and_wait_range
→ filemap_fdatawrite_range
→ writeback_control: WB_SYNC_ALL, range 0..4095
→ do_writepages
→ ext4_writepages
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
current executor   = task that invoked O_SYNC write(fd, buf, 4096)
CPU mode           = x86-64 CPL 0, syscall process context
writeback mode     = WB_SYNC_ALL
writeback range    = file offset 0..4095
target folio       = page cache, dirty, uptodate, unlocked
stable storage     = not updated yet
inode i_rwsem      = released
superblock writer  = still protected by file_start_write
kiocb->ki_pos      = 4096
local pos          = 0
file->f_pos        = 0
PG_writeback       = not established by this writepages call yet
WRITE bio          = not created
blk-mq request/tag = not created
SCSI/ATA/AHCI      = not created
journal commit     = not waited
write syscall      = not returned
```

## 下一任务边界

下一批从固定源码中的：

```c
ext4_writepages(mapping, wbc)
```

开始，连续追踪：

```text
ext4_writepages
→ scan and lock dirty folio
→ clear dirty-for-I/O and set PG_writeback
→ prepare ext4 writeback extent
→ preserve data=ordered journal dependency
→ ext4_io_submit
→ WRITE bio
→ submit_bio / partition remap
→ blk-mq request
→ SCSI WRITE
→ libata ATA write taskfile
→ AHCI H2D FIS / PRDT / PxCI
→ completion interrupt
→ bio completion / folio end_writeback
→ file_write_and_wait_range returns
→ ext4 journal commit / optional flush
→ generic_write_sync returns
→ local pos and file->f_pos become 4096
→ write() returns userspace
```

必须从固定 commit 核对实际函数链后再决定下一章自然边界，不要直接复用 read 路径的函数名称。

## 必须保持的技术边界

1. `O_SYNC` buffered write 仍先写 page cache，再执行同步 writeback。
2. dirty、uptodate folio 不表示 stable storage 已更新。
3. delayed-allocation aops 被选中，不表示覆盖已有 extent 时重新分配磁盘块。
4. `generic_write_sync()` 对 `O_SYNC` 使用 `datasync=0`。
5. `file_write_and_wait_range()` 的 write 与 wait 是不同阶段。
6. `WB_SYNC_ALL` 不表示 bio 已创建或 I/O 已完成。
7. `PG_writeback`、WRITE bio、blk-mq request、SCSI command、ATA queued command 和 AHCI slot 是不同状态与对象。
8. storage WRITE DMA 从 page-cache folio 读取数据；用户 buffer 已在更早的 CPU copy 阶段退出主线。
9. data completion 与 journal commit/device flush 不得混为同一件事。
10. `kiocb->ki_pos`、local `pos`、共享 `file->f_pos` 必须分开描述。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode 和运行环境；
- 关键代码与数据结构；
- 当前动作建立的条件；
- 下一控制入口；
- 固定源码文件、symbol 或规范依据。

不能用“ext4 刷盘”“block layer 处理”“journal 提交完成”这样的概括跳过对象转换、等待与控制权交接。

## 章节边界

章节不按 Roadmap 条目机械切分。连续叙述达到适合一次阅读的篇幅，并遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem 交接时换章。

每章末尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户要求连续完成 N 章时：

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、STATE、manifest、README 和接续入口；
6. 从最新状态继续下一章。

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
