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
```

八个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 openat create-open、新文件首次delalloc write + fsync。

最新三章：

- `LK-DELALLOC-107`：首次 buffered write 怎样只预留空间而不分配物理块？
- `LK-DELALLOC-108`：fsync() 怎样让 writeback 分配第一个 unwritten extent 并提交数据？
- `LK-DELALLOC-109`：data completion 怎样转换 extent，并让 fsync() 真正返回？

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

## 已完成 delalloc + fsync 固定场景

```text
current task       = parent
calls              = write(6, buf, 4096); fsync(6)
path               = /work/demo.txt
fd before write    = 6, write-only, f_pos=0
inode before write = regular 0644, nlink=1, size=0, blocks=0
block/page size    = 4 KiB
mount              = data=ordered,delalloc,dioread_nolock,barrier
bigalloc/inline    = disabled
fast commit        = disabled
quota              = disabled
folio state        = page-cache index 0 absent before write
allocation         = one free physical block P
background WB      = none before write returns
failure policy     = no signal, ENOSPC, allocation, copy, journal or I/O error
```

## 已执行控制流

```text
write(6, buf, 4096)
→ __x64_sys_write / vfs_write
→ ext4_buffered_write_iter
→ generic_perform_write
→ ext4_da_write_begin
→ allocate page-cache folio index 0
→ ext4_da_map_blocks finds logical hole
→ ext4_da_reserve_space(1)
→ extent-status delayed [0,1)
→ copy 4096 bytes
→ dirty folio
→ i_size=4096, i_disksize=0
→ write returns 4096; f_pos=4096

fsync(6)
→ ext4_sync_file
→ file_write_and_wait_range
→ ext4_writepages / ext4_do_writepages
→ collect BH_Delay logical block 0
→ start JBD2 write-page transaction
→ ext4_map_blocks / extent allocator
→ consume reservation
→ logical block 0 maps to physical P as unwritten
→ submit REQ_SYNC data bio
→ blk-mq / SCSI / libata / AHCI
→ ext4_end_bio
→ deferred io_end conversion work
→ ext4_ext_mark_initialized
→ extent becomes written
→ folio_end_writeback
→ full JBD2 commit
→ blkdev_issue_flush
→ fsync returns 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = first delalloc write + fsync complete
current executor   = parent
CPU mode           = x86-64 CPL 3
fd 6               = open, write-only
file position      = 4096
path                = /work/demo.txt
inode mode/nlink    = regular 0644 / 1
i_size              = 4096
i_disksize          = 4096
i_blocks            = 8 sectors
extent              = logical block 0 -> physical P, written
delalloc reservation= 0
folio               = uptodate, clean, no writeback
data I/O            = complete and released
extent conversion   = complete
JBD2 transaction    = committed
required flush      = complete
checkpoint          = not required to be complete
durability          = create, size, extent and data satisfy fsync
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. page-cache folio allocation不等于physical block allocation。
2. delalloc reservation不写block bitmap，也没有physical block number。
3. ordinary write可在`i_size=4096, i_disksize=0`时成功返回。
4. writeback消费reservation并先建立unwritten extent。
5. unwritten extent在data completion前保持zero-read语义。
6. data DMA completion、extent conversion、journal commit、device flush是不同阶段。
7. `folio_end_writeback()` 在影响数据可见性的conversion完成后发生。
8. journal commit durable不等于home-location checkpoint complete。
9. `fsync`不改变`file->f_pos`，也不关闭fd。

## 下一建议场景

优先继续文件仍被fd 6打开时的unlink与最后close：

```text
unlinkat(AT_FDCWD, "/work/demo.txt", 0)
→ cached positive pathname lookup
→ lock /work
→ ext4_unlink removes dirent
→ nlink 1 -> 0
→ ext4 orphan tracking
→ pathname disappears, fd 6 remains valid
→ close(6)
→ file_close_fd / __fput
→ final inode eviction
→ free extent P and inode allocation
```

开始前固定directory/inode cache、journal transaction、file/inode reference counts、unlink与close间是否额外写入、orphan handling、metadata durability目标和failure policy。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
