项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-076

最新三章：

#. ``LK-READ-074``：x86-64 的 read() 怎样从用户态进入 __x64_sys_read？
#. ``LK-READ-075``：read() 怎样从 fd 找到 ext4 文件并进入 generic_file_read_iter？
#. ``LK-READ-076``：page cache miss 怎样让 ext4 构造并提交 READ bio？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定平台与源码
--------------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

固定 Linux commit 的 ``Makefile`` 标识为 ``7.2-rc1``。旧章节中残留的 ``Linux 6.12.95`` 是历史显示标签错误；技术事实继续以固定 commit 为权威来源。

固定运行期场景
--------------

::

   userspace call       = read(fd, buf, 4096)
   ABI                  = x86-64 native SYSCALL
   syscall entry        = entry_SYSCALL_64
   fd                   = already-open regular ext4 file
   file position        = 0
   filesystem block     = 4096 bytes
   I/O mode             = buffered
   excluded             = O_DIRECT, DAX, inline data, fscrypt, fs-verity
   page cache           = target index 0 absent
   readahead            = nonzero window covering index 0
   extent               = logical block 0 mapped to physical storage
   user buffer          = mapped and writable

当前控制流位置
--------------

第七十四至七十六章已经完成：

::

   userspace read(fd, buf, 4096)
   → RAX=0, RDI=fd, RSI=buf, RDX=4096
   → SYSCALL
   → entry_SYSCALL_64
   → swapgs
   → optional SWITCH_TO_KERNEL_CR3
   → switch to current task kernel stack
   → construct pt_regs
   → do_syscall_64
   → x64_sys_call case 0
   → __x64_sys_read

   → ksys_read
   → fdget_pos
   → optional file->f_pos_lock
   → copy file->f_pos into local pos
   → vfs_read
   → FMODE/access_ok/range checks
   → security_file_permission
   → fsnotify_file_area_perm
   → new_sync_read
   → build kiocb and ITER_DEST iov_iter
   → ext4_file_read_iter
   → select buffered path
   → generic_file_read_iter

   → filemap_read
   → filemap_get_pages
   → filemap_get_read_batch misses index 0
   → page_cache_sync_ra
   → allocate/insert page-cache folio(s)
   → ext4_readahead
   → ext4_mpage_readpages
   → ext4_map_blocks
   → logical block 0 maps to physical block
   → bio_alloc(REQ_OP_READ)
   → set starting 512-byte sector
   → bio_add_folio
   → set mpage_end_io
   → blk_crypto_submit_bio

精确停点：

.. code-block:: c

   blk_crypto_submit_bio(bio);

此刻状态
--------

* system state：``SYSTEM_RUNNING``；
* 当前执行者：发起 ``read()`` 的 user task；
* CPU mode：x86-64 CPL 0，运行在该 task 的 kernel stack；
* syscall：native ``read`` number 0；
* ``pt_regs``：保存 user return frame 与 syscall 参数；
* fd：已经解析为 ext4 regular ``struct file``；
* ``f_pos``：需要时由 ``f_pos_lock`` 保护；
* ``kiocb``：保存 file 与 offset 0；
* ``iov_iter``：``ITER_DEST``，指向 4096-byte user buffer；
* page cache：目标 folio 已插入 ``mapping->i_pages``；
* folio：已加入 READ bio，尚不能假设 uptodate；
* ext4：logical block 已映射为 physical block 与 sector；
* bio：``REQ_OP_READ``，completion 为 ``mpage_end_io``；
* block layer：尚未展开 ``submit_bio_noacct`` 与 blk-mq；
* SCSI/AHCI：尚未创建 command/request；
* user buffer：尚未执行 ``copy_folio_to_iter()``；
* syscall：尚未返回，return value 尚未确定。

关键边界
--------

#. page-cache miss、user-buffer page fault 与 ext4 metadata cache miss是三个不同状态。
#. ``access_ok`` 只做地址范围检查，不能保证后续 user copy 不发生 fault。
#. ``read()`` 通过 fd 复用已经打开的 ``struct file``，不会重新进行 pathname lookup。
#. ``fdget_pos`` 保护共享 open file description 的 ``f_pos``；``pread64`` 不走同一 position 更新语义。
#. ``ext4_file_read_iter`` 负责选择 buffered/direct/DAX，当前固定 buffered。
#. readahead 可能创建多个 folio，不能写成固定恰好一页。
#. ``bio_add_folio`` 描述 storage-to-page-cache buffer，不向 user buffer 复制数据。
#. ``blk_crypto_submit_bio`` 被调用不等于设备已完成读取。
#. ext4 hole 会零填并跳过磁盘 I/O，当前固定 extent 已映射。

当前下一步
----------

从 ``block/blk-crypto.c:blk_crypto_submit_bio()`` 开始：

::

   blk_crypto_submit_bio
   → no encryption transformation required
   → submit_bio_noacct
   → bio checks / remap / split
   → plugging and merge decisions
   → blk-mq request allocation
   → SCSI disk request
   → libata translation
   → AHCI command-table / command-slot submission

completion interrupt、DMA completion、``mpage_end_io``、folio uptodate、``copy_folio_to_iter``、``file->f_pos`` commit 与 syscall exit 留给后续章节。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
