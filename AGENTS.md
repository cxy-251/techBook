# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-088
```

启动主线已完结；`read(fd, buf, 4096)` cold page-cache miss 已完整闭环。当前正在写独立的 ext4 `O_SYNC` buffered write 主线。

最新三章：

- `LK-WRITE-086`：ext4 writeback 怎样把 dirty folio 变成 WRITE bio？
- `LK-WRITE-087`：WRITE bio 怎样变成 AHCI command 并写入 PxCI？
- `LK-WRITE-088`：WRITE completion 怎样结束 folio writeback，并让 O_SYNC 等待继续？

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
block path           = REQ_OP_WRITE | REQ_SYNC, no REQ_FUA, no split, no merge target
```

该 write 场景独立于前一条 read；不要沿用 read 结束后的 page-cache folio。

## 已执行控制流

```text
userspace write(fd, buf, 4096)
→ entry_SYSCALL_64 / __x64_sys_write
→ ksys_write / vfs_write / new_sync_write
→ ext4_file_write_iter / ext4_buffered_write_iter
→ generic_perform_write
→ ext4_da_write_begin
→ copy_folio_from_iter_atomic
→ ext4_da_write_end
→ dirty page-cache folio
→ generic_write_sync
→ vfs_fsync_range(file, 0, 4095, datasync=0)
→ ext4_sync_file
→ file_write_and_wait_range
→ WB_SYNC_ALL / ext4_writepages
→ existing mapped buffer submitted in do_map=0 pass
→ folio_clear_dirty_for_io
→ ext4_bio_write_folio
→ __folio_start_writeback
→ REQ_OP_WRITE | REQ_SYNC bio
→ blk_crypto_submit_bio / submit_bio
→ partition remap
→ blk-mq request and tag
→ SCSI WRITE(10 or 16)
→ libata ATA DMA/NCQ WRITE
→ dma_map_sg(DMA_TO_DEVICE)
→ AHCI H2D FIS / PRDT / AHCI_CMD_WRITE
→ PxCI[tag] = 1
→ AHCI completion interrupt
→ ata_qc_complete / dma_unmap_sg
→ ata_scsi_qc_complete / scsi_done
→ blk_mq_complete_request
→ scsi_complete / blk_update_request
→ bio_endio / ext4_end_bio
→ ext4_finish_bio
→ folio_end_writeback
→ file_write_and_wait_range returns 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
current executor   = O_SYNC writer task inside ext4_sync_file
CPU mode           = x86-64 CPL 0, syscall process context
target folio       = clean, uptodate, unlocked, PG_writeback=0
data WRITE bio     = completed and released
blk-mq request/tag = completed and released
SCSI/ATA/AHCI      = command completed
DMA mapping        = unmapped
data range wait    = returned 0
writeback error    = none
device durability  = not fully established yet
JBD2 commit        = not executed at next entry
optional flush     = not issued
kiocb->ki_pos      = 4096
local pos          = 0
file->f_pos        = 0
write syscall      = not returned
```

## 下一任务边界

下一批从固定源码中的：

```c
ext4_fsync_journal(inode, false, &needs_barrier)
```

开始，连续追踪：

```text
select EXT4_I(inode)->i_sync_tid
→ ext4_fc_commit
→ fast commit or full JBD2 commit
→ transaction wait and commit record
→ determine needs_barrier
→ optional blkdev_issue_flush
→ file_check_and_advance_wb_err
→ ext4_sync_file returns
→ generic_write_sync returns 4096
→ new_sync_write updates local pos
→ vfs_write accounting and file_end_write
→ ksys_write commits file->f_pos = 4096
→ pt_regs->ax = 4096
→ syscall_exit_to_user_mode
→ SYSRETQ or IRETQ
→ userspace receives 4096
```

必须从固定 commit 核对 `ext4_fc_commit()`、JBD2 commit、barrier 与 flush 的真实分支。不要假设 fast commit 一定启用，也不要假设一定或一定不执行 flush。

## 必须保持的技术边界

1. `O_SYNC` buffered write 先写 page cache，再执行同步 writeback。
2. 已有 initialized extent 的覆盖写在 `ext4_writepages` 第一遍直接提交，不新分配 extent。
3. `folio_clear_dirty_for_io`、`PG_writeback` 与 folio lock 是不同状态。
4. WRITE DMA 从 page-cache folio读取数据，不直接读取用户 buffer。
5. `REQ_SYNC` 不等于 `REQ_FUA`。
6. AHCI completion必须穿过 SCSI、blk-mq、bio和 `ext4_end_bio` 才能调用 `folio_end_writeback`。
7. data I/O completion、JBD2 transaction commit与 device cache flush是三个独立阶段。
8. clean folio不等于 O_SYNC durability已经全部满足。
9. `kiocb->ki_pos`、local `pos`、共享 `file->f_pos` 必须分开描述。
10. 不同运行期场景之间不是自动连续时间线。

## 连续叙事

每一段必须交代：当前执行者、CPU mode、关键数据结构、当前动作建立的条件、下一控制入口，以及固定源码依据。

不能用“ext4 刷盘”“journal 提交完成”“系统调用返回”这样的概括跳过 transaction、flush、error propagation 和 position commit。

## 章节边界

章节不按 Roadmap 条目机械切分。遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem 交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 确定自然边界；
4. 写完并核对章节；
5. 更新目录、STATE、manifest、README 和接续入口；
6. 从最新状态继续。

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
