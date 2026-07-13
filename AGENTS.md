# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

固定启动平台：

```text
x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 7.2-rc1
```

Linux boot 主线已经完成 `LK-BOOT-001..LK-BOOT-073`。当前运行期主线已完成 `LK-READ-074..LK-READ-076`：

- `LK-READ-074`：x86-64 的 read() 怎样从用户态进入 __x64_sys_read？
- `LK-READ-075`：read() 怎样从 fd 找到 ext4 文件并进入 generic_file_read_iter？
- `LK-READ-076`：page cache miss 怎样让 ext4 构造并提交 READ bio？

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

Linux 资料使用 `gregkh/linux` 固定 commit `7404ce51637231382873d0b55edabc2f3b841a9d`。该 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中的 `Linux 6.12.95` 是历史显示标签错误，不得切换到真正的 `v6.12.95`。

## 固定 read() 运行期场景

```text
userspace call       = read(fd, buf, 4096)
ABI                  = x86-64 native SYSCALL
entry                = entry_SYSCALL_64
FRED syscall path    = excluded from this scenario
fd                   = already-open regular ext4 file
file position        = 0
filesystem block     = 4096 bytes
I/O mode             = buffered
excluded             = O_DIRECT, DAX, inline data, fscrypt, fs-verity
page cache           = target index 0 absent
readahead            = nonzero window covering index 0
extent               = logical block 0 mapped to an existing physical block
user buffer          = mapped and writable
```

不要把以下分支混进固定主线：stream file、invalid fd、permission denial、direct I/O、DAX、hole、inline data、encryption、verity 或 user-buffer fault。可以解释这些分支，但章节结束状态必须回到固定路径。

## 当前控制流

已经执行：

```text
userspace read(fd, buf, 4096)
→ RAX=0, RDI=fd, RSI=buf, RDX=4096
→ SYSCALL
→ entry_SYSCALL_64
→ swapgs / optional kernel CR3 / kernel stack
→ construct pt_regs
→ do_syscall_64
→ x64_sys_call case 0
→ __x64_sys_read

→ ksys_read
→ fdget_pos
→ optional f_pos_lock
→ vfs_read
→ access/range/LSM/fsnotify permission checks
→ new_sync_read
→ ext4_file_read_iter
→ generic_file_read_iter

→ filemap_read
→ filemap_get_pages
→ cold page-cache miss
→ page_cache_sync_ra
→ ext4_readahead
→ ext4_mpage_readpages
→ ext4_map_blocks
→ bio_alloc(REQ_OP_READ)
→ bio_add_folio
→ blk_crypto_submit_bio
```

当前精确停点：

```c
blk_crypto_submit_bio(bio);
```

当前状态：

- 当前执行者是发起 `read()` 的 userspace task，正在 CPL 0 process context；
- fd、`struct file`、`kiocb`、`iov_iter` 与 ext4 inode 已确定；
- `f_pos` 需要时由 `f_pos_lock` 保护；
- 目标 folio 已加入 page cache，并挂入 READ bio；
- ext4 logical block 已映射到 physical block 与 512-byte sector；
- bio operation 是 `REQ_OP_READ`，completion 是 `mpage_end_io`；
- 尚未创建最终 blk-mq/SCSI/AHCI request；
- 尚未向 q35 AHCI command list 写入命令；
- folio 尚不能假设 uptodate；
- user buffer 尚未由 `copy_folio_to_iter()` 填充；
- `read()` 尚未返回。

## 下一任务

从 `block/blk-crypto.c:blk_crypto_submit_bio()` 开始，继续固定的未加密 bio 路径：

```text
blk_crypto_submit_bio
→ submit_bio_noacct
→ block bio checks / remap / split
→ current plug or direct submit
→ blk-mq request allocation
→ request merge / queue
→ SCSI disk path
→ libata / AHCI qc issue
```

下一批适合按自然边界拆分：

1. bio 如何进入 `submit_bio_noacct()` 并被 block layer 校验、拆分和归并；
2. bio 怎样变成 blk-mq request，并进入 SCSI disk queue；
3. SCSI command 怎样经过 libata 到达 AHCI command slot 与 port registers。

completion interrupt、DMA 完成、folio uptodate、`copy_folio_to_iter()` 与 syscall exit 应留到后续章节，不能在 submission 章节提前宣布。

## 必须保持的技术边界

1. page-cache miss 不等于 user-buffer page fault，也不等于 ext4 metadata cache miss。
2. `access_ok()` 成功不保证后续 user copy 一定成功。
3. `fdget_pos()` 取得的是 open file description；pathname lookup 不会在 `read()` 中重做。
4. `read()` 使用共享 `file->f_pos`；`pread64()` 使用调用者提供的位置，不更新 `f_pos`。
5. `ext4_file_read_iter()` 选择 buffered/direct/DAX 路径；当前固定为 buffered。
6. readahead 窗口大小依赖运行时状态，不能固定为恰好一个 folio。
7. `bio_add_folio()` 不执行 user copy，只描述 storage-to-folio I/O buffer。
8. bio submission 不等于设备已经完成 I/O。
9. `do_initcalls()`、boot 和 PID 1 进入用户态已经结束；运行期场景之间不是自动连续时间线。

## 用户输入与技术事实

用户提供的是关注方向、线索和阅读感受，不直接作为完整技术事实。正文根据固定平台、固定源码与明确运行期状态补全中间过程。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode 和运行环境；
- 关键代码与数据；
- 当前动作建立的条件；
- 下一控制入口；
- 对应规范、固定源码文件和符号。

不能用“VFS 读取文件”“block layer 发送请求”“驱动访问磁盘”这样的概括跳过中间主流程。

## 章节边界

章节不按 Roadmap 条目机械切分。连续叙述达到适合一次阅读的篇幅，并遇到执行者、CPU mode、数据结构所有权或 subsystem 交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户要求连续完成 N 章时：

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、STATE、manifest、README 和接续入口；
6. 再从最新状态开始下一章。

遇到固定源码无法确认、重大平台分叉、仓库写入失败或达到指定终点时停止。

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
