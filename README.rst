techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第七十四章：x86-64 的 read() 怎样从用户态进入 __x64_sys_read？ <docs/tracks/linux-kernel/74-x86-read-syscall-enters-kernel.rst>`_
* `第七十五章：read() 怎样从 fd 找到 ext4 文件并进入 generic_file_read_iter？ <docs/tracks/linux-kernel/75-read-resolves-fd-and-dispatches-through-vfs.rst>`_
* `第七十六章：page cache miss 怎样让 ext4 构造并提交 READ bio？ <docs/tracks/linux-kernel/76-filemap-miss-builds-ext4-read-bio.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d
   → boot handoff complete
   → fixed runtime read(fd, buf, 4096)

固定 commit 的真实版本是 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 属于历史显示标签错误；源码事实以固定 commit 为准。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-076

当前运行期路径：

::

   userspace SYSCALL
   → entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_read
   → ksys_read
   → fdget_pos
   → vfs_read
   → ext4_file_read_iter
   → generic_file_read_iter
   → filemap_read
   → cold page-cache miss
   → ext4_readahead / ext4_mpage_readpages
   → ext4_map_blocks
   → READ bio
   → blk_crypto_submit_bio

下一步从 ``blk_crypto_submit_bio()`` 进入 block layer，继续追踪 ``submit_bio_noacct()``、bio split/merge、blk-mq request、SCSI 与 q35 ICH9 AHCI submission。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
