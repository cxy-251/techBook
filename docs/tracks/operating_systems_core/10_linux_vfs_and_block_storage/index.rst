======================================================
模块 10：Linux 7.2 虚拟文件系统 (VFS) 与块设备存储架构
======================================================

本模块深入 Linux 7.2-rc1 虚拟文件系统 (VFS)、页缓存 (Page Cache)、通用块层 (blk-mq) 与物理文件系统内部机制：`super_block` / `inode` / `dentry` / `file` 四大核心对象、路径查找与 Dcache RCU 无锁并发遍历、`rootfs` 内存文件系统与 `initramfs` cpio 解包、`address_space` 与 XArray 检索及脏页异步回写、通用块层多队列架构 (blk-mq) 与 `struct bio` 流转，以及 ext4 / F2FS 物理磁盘布局、JBD2 日志事务与闪存写入优化。

.. toctree::
   :maxdepth: 2

   01_vfs_objects_sb_inode_dentry_file
   02_path_lookup_dcache_rcu
   03_rootfs_and_initramfs_unpacking
   04_page_cache_address_space_writeback
   05_blk_mq_architecture_and_bio
   06_ext4_f2fs_disk_layout_journal
