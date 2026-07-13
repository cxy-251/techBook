# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

固定启动主线：

```text
x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 7.2-rc1
```

Linux boot 主线已经完成 `LK-BOOT-001..LK-BOOT-073`。当前运行期 `read()` 主线已经完成 `LK-READ-074..LK-READ-079`。最新章节：

- `LK-READ-077`：READ bio 怎样通过校验与分区重映射进入 blk-mq？
- `LK-READ-078`：blk-mq 怎样把 bio 变成 SCSI READ request？
- `LK-READ-079`：SCSI READ 怎样变成 ATA taskfile 并写入 AHCI command slot？

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

GRUB 资料使用 GNU 官方 `grub-2.14.tar.xz` 和 `GitMirroring/grub` 固定提交。Linux 资料使用 `gregkh/linux` 固定 commit `7404ce51637231382873d0b55edabc2f3b841a9d`。

重要纠正：该 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中残留的 `Linux 6.12.95` 只是历史显示标签错误。不得切换到真正的 `v6.12.95`；技术事实以固定 commit 和链接为准。

## 固定运行期场景

```text
userspace call       = read(fd, buf, 4096)
ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
file                 = already-open regular ext4 file on /dev/sda1
file position        = 0
filesystem block     = 4096 bytes
I/O mode             = buffered, not O_DIRECT, not DAX
file features        = no inline data, fscrypt, fs-verity, integrity protection
page cache           = target index 0 absent
readahead            = synchronous readahead covers target folio
extent               = logical block 0 maps to an existing physical block
user buffer          = mapped and writable
partition offset     = /dev/sda1 begins at whole-disk LBA 2048
block path           = no injected failure or blk-cgroup throttle delay
queue limits         = target bio fits limits and is not split
merge                = no compatible existing request
SCSI CDB             = sd selects applicable READ(6), READ(10), or READ(16)
ATA protocol         = negotiated DMA or NCQ read; both converge in AHCI
```

不要把 ext4 4096-byte filesystem block 推导成磁盘一定使用 4096-byte logical sector。当前 QEMU block backend 的 IDENTIFY sector-size 参数、`sd` 的 `use_10_for_rw/use_16_for_rw` 和 libata NCQ negotiation 没有完全锁定；正文保留这些真实分支，并只在它们重新汇合后继续单一路径。

## 当前控制流

已经执行：

```text
userspace read(fd, buf, 4096)
→ entry_SYSCALL_64
→ do_syscall_64
→ __x64_sys_read
→ ksys_read / fdget_pos
→ vfs_read / new_sync_read
→ ext4_file_read_iter
→ generic_file_read_iter / filemap_read
→ cold page-cache miss
→ page_cache_sync_ra
→ ext4_readahead / ext4_mpage_readpages
→ ext4_map_blocks
→ READ bio with target folio

→ blk_crypto_submit_bio
→ submit_bio
→ submit_bio_noacct
→ operation/range checks
→ add /dev/sda1 bd_start_sect = 2048
→ submit_bio_noacct_nocheck
→ blk_mq_submit_bio
→ queue-limit check; fixed path no split
→ fixed path no merge target
→ allocate request and blk-mq tag
→ attach bio to request
→ plug/elevator/direct issue convergence

→ scsi_queue_rq
→ scsi_prepare_cmd
→ sd_init_command
→ applicable SCSI READ CDB
→ scsi_dispatch_cmd
→ ata_scsi_queuecmd
→ ata_scsi_rw_xlat
→ ata_build_rw_tf
→ ata_scsi_qc_issue
→ ata_qc_issue
→ dma_map_sg(..., DMA_FROM_DEVICE)
→ ahci_qc_prep
→ H2D Register FIS
→ PRDT entries point to page-cache folio DMA addresses
→ AHCI command header/slot
→ optional PxSACT[tag] for NCQ
→ PxCI[tag] = 1
```

当前状态：

- `system_state = SYSTEM_RUNNING`；
- 发起 `read()` 的 task 仍在 syscall 的 kernel process context 中；
- blk-mq request 已 started，拥有 tag；
- SCSI READ 已翻译成 ATA DMA/NCQ taskfile；
- target folio scatterlist 已 DMA-map；
- AHCI H2D FIS、PRDT、command header 与 command table 已填写；
- q35 AHCI `PxCI` 对应 tag bit 已置位；
- AHCI engine/device 可以并发执行 command 和 DMA；
- completion interrupt 尚未处理；
- target folio 仍不能视为 uptodate；
- user buffer 尚未由 `copy_folio_to_iter()` 填充；
- `read()` 尚未返回。

## 下一任务边界

下一批从 AHCI completion interrupt 开始。IRQ mode 可能是 legacy INTx、MSI 或 MSI-X，固定配置没有锁定具体入口；这些路径在 libahci 中汇合到：

```text
AHCI IRQ handler
→ ahci_handle_port_intr()
→ ahci_port_intr()
→ read PxCI/PxSACT and determine completed tag
→ ata_qc_complete()
→ ata_scsi_qc_complete()
→ scsi_done()
→ blk_mq_complete_request()
→ scsi_complete()/scsi_finish_command()
→ blk_mq end request
→ bio_endio
→ mpage_end_io
→ folio_end_read(success)
→ folio uptodate + unlock
```

随后再回到等待的 reader：

```text
folio waiter wakes
→ filemap_get_pages/filemap_read
→ copy_folio_to_iter(user buf)
→ ki_pos and f_pos update
→ vfs/read accounting
→ syscall return value
→ syscall_exit_to_user_mode
→ SYSRETQ or IRETQ
```

不要把 `PxCI[tag] = 1` 写成 DMA 已完成，也不要把 interrupt handler 识别 tag 写成 folio 已经 uptodate。completion 必须完整穿过 libata、SCSI、blk-mq、bio 和 ext4 callback。

## 必须保持的技术边界

1. `blk_crypto_submit_bio()` 是统一入口；无 crypt context 时直接进入普通 `submit_bio()`。
2. 分区 remap 只增加 `bd_start_sect` 并改变块地址坐标，不重新做 ext4 extent lookup。
3. bio、request、scsi_cmnd、ata_queued_cmd 和 AHCI command slot 是不同层次的对象。
4. plug/elevator 影响 dispatch 时间与顺序，不改变最终 SCSI `queue_rq`。
5. SCSI READ(6/10/16) 选择取决于 device flags、LBA 和 block count；不能无依据写死。
6. ATA DMA/NCQ protocol 取决于 IDENTIFY 和 negotiation；NCQ 额外写 `PxSACT`，所有路径都写 `PxCI`。
7. DMA target 是 page-cache folio，不是用户 `buf`。
8. `PxCI` write 表示 command 已 issue，不表示 DMA、bio 或 read syscall 已完成。
9. hardware completion 与 reader task 是并发线，必须在 folio unlock/wakeup 处重新汇合。

## 用户输入与技术事实

用户提供的是关注方向、线索和阅读感受，不直接作为完整技术事实。正文根据固定硬件路径、规范、固定源码和真实状态变化补全中间过程。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode 和运行环境；
- 关键代码与数据；
- 当前动作建立的条件；
- 下一控制入口；
- 对应规范、固定源码文件和符号。

不能用“block layer 处理请求”“SCSI 发给磁盘”“AHCI 完成读取”这样的概括跳过对象转换与 completion chain。

## 章节边界

章节不按 Roadmap 条目机械切分，也不预先规划整本书。连续叙述达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户要求连续完成 N 章时，仍逐章执行：

1. 重新读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 只确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、STATE、manifest、README 和接续入口；
6. 再从最新状态开始下一章。

不能先批量生成多章后统一核对。遇到固定源码无法确认、重大平台分叉、仓库写入失败或达到指定终点时停止。

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