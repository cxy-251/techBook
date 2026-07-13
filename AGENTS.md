# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
```

启动主线已完结。第一个运行期场景 `read(fd, buf, 4096)` cold page-cache miss 也已经完整闭环。

最新三章：

- `LK-READ-080`：AHCI 中断怎样确认完成的 tag，并把结果交回 SCSI？
- `LK-READ-081`：blk-mq completion 怎样结束 bio，并让 ext4 folio 变成 uptodate？
- `LK-READ-082`：reader task 怎样复制 folio，并让 read() 返回用户态？

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

固定 `grub.cfg`：

```cfg
set timeout=0
set default=0

menuentry 'Linux 7.2-rc1' {
    linux /boot/bzImage-7.2-rc1 root=/dev/sda1 ro console=ttyS0
    initrd /boot/initramfs-7.2-rc1.img
}
```

Linux 资料始终使用 `gregkh/linux` 固定 commit `7404ce51637231382873d0b55edabc2f3b841a9d`。该 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中的 `Linux 6.12.95` 是历史显示标签错误，不得切换到真正的 `v6.12.95`。

## 已完成的 read() 固定场景

```text
userspace call       = read(fd, buf, 4096)
ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
file                 = already-open regular ext4 file on /dev/sda1
initial file position= 0
filesystem block     = 4096 bytes
I/O mode             = buffered; not O_DIRECT; not DAX
file features        = no inline data, fscrypt, fs-verity, integrity protection
initial page cache   = target index 0 absent
readahead            = synchronous readahead covers target folio
extent               = logical block 0 maps to existing physical storage
user buffer          = mapped and writable
partition offset     = /dev/sda1 begins at whole-disk LBA 2048
block path           = no injected failure or blk-cgroup throttle delay
queue limits         = bio fits limits and is not split
merge                = no compatible request
completion           = successful 4096-byte read
```

没有无依据写死磁盘 logical-sector size、SCSI READ(6/10/16) 或 ATA DMA/NCQ。真实分支在 AHCI submission/completion 处重新汇合。

## 已完成控制流

```text
userspace read(fd, buf, 4096)
→ entry_SYSCALL_64
→ do_syscall_64 / __x64_sys_read
→ ksys_read / fd position guard
→ vfs_read / new_sync_read
→ ext4_file_read_iter
→ generic_file_read_iter / filemap_read
→ cold page-cache miss
→ synchronous readahead
→ ext4_mpage_readpages / ext4_map_blocks
→ READ bio
→ submit_bio_noacct
→ partition remap
→ blk_mq_submit_bio
→ blk-mq request and tag
→ SCSI READ CDB
→ libata ATA DMA or NCQ taskfile
→ dma_map_sg
→ AHCI H2D FIS / PRDT / command header
→ PxCI[tag] = 1

→ AHCI DMA to page-cache folio
→ completion IRQ
→ compare software active mask with PxCI/PxSACT
→ ata_qc_complete
→ dma_unmap_sg
→ ata_scsi_qc_complete / scsi_done
→ blk_mq_complete_request
→ scsi_complete / scsi_finish_command
→ blk_update_request
→ bio_endio
→ ext4 mpage_end_io
→ folio_end_read(folio, true)
→ folio uptodate + unlock + waiter wake

→ reader task retries filemap lookup
→ copy_folio_to_iter(user buffer)
→ ki_pos = 4096
→ local pos = 4096
→ file->f_pos = 4096
→ pt_regs->ax = 4096
→ syscall_exit_to_user_mode
→ SYSRETQ or IRETQ
→ userspace CPL 3
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
current executor   = userspace task after read() return
CPU mode           = x86-64 CPL 3
RAX                = 4096
user buffer        = file bytes 0..4095
file->f_pos        = 4096
target folio       = in page cache, uptodate, unlocked
bio/request/tag    = completed and released
SCSI/ATA/AHCI      = command completed
runtime scenario   = complete
```

## 下一任务

下一条运行期主线尚未选定。不要把另一个 syscall 写成本次 `read()` 的自动时间线后续。

开始新场景前必须明确：

1. syscall 与参数；
2. 对象的初始状态；
3. cache/mapping/lock/concurrency 状态；
4. filesystem、device 或 network 路径；
5. 成功或错误分支；
6. 自然终止边界。

buffered ext4 `write(fd, buf, 4096)` 是优先候选，可覆盖 user copy、page-cache dirty、ext4 journaling、writeback 和 storage submission；它目前只是候选，没有被正式选为下一入口。

## 必须保持的技术边界

1. bio、blk-mq request、`scsi_cmnd`、`ata_queued_cmd` 和 AHCI command slot 是不同对象。
2. AHCI DMA 的目标是 page-cache folio，不是用户 buffer。
3. hardware tag 完成不等于 folio 已经 uptodate；completion 必须穿过 libata、SCSI、blk-mq、bio 和 ext4。
4. `folio_end_read(folio, true)` 发布 uptodate、unlock 并唤醒 waiters。
5. waiter wake 不等于 reader 立即运行。
6. `copy_folio_to_iter()` 才执行 page cache 到用户 buffer 的复制。
7. `access_ok()` 成功不保证真正 user copy 不 fault。
8. `ki_pos`、local `pos` 与共享 `file->f_pos` 必须分开描述。
9. clean native return frame 通常走 `SYSRETQ`，异常 frame 走 `IRETQ`。
10. 不同运行期场景之间不是自动连续时间线。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode 和运行环境；
- 关键代码与数据结构；
- 当前动作建立的条件；
- 下一控制入口；
- 固定源码文件、symbol 或规范依据。

不能用“block layer 处理请求”“驱动完成 I/O”“进程返回用户态”这样的概括跳过对象转换和控制权交接。

## 章节边界

章节不按 Roadmap 条目机械切分。连续叙述达到适合一次阅读的篇幅，并遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem 交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

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