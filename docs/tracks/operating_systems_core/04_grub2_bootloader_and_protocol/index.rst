======================================================
模块 04：GRUB2 引导加载器与内核协议握手
======================================================

本模块深入 GRUB2 引导加载器底层，系统化剖析 MBR Stage 1 (boot.S) 446 字节机器码极限空间与跳转、`core.img` (Stage 1.5/2) 压缩自解压与动态模块加载器 (`dl.c`)、ext4/FAT/Btrfs 最小文件系统驱动与 `grub.cfg` 解析引擎、A20 地址线开启与 GDT 32 位保护模式/64 位长模式跃迁，以及 Linux 16/32 位 Boot Protocol 规范 (`struct boot_params` / `setup_header`) 与 `vmlinuz` / initramfs 物理内存装配全流程。

.. toctree::
   :maxdepth: 2

   01_mbr_boot_s_diskboot
   02_core_img_dynamic_modules
   03_fs_drivers_and_grub_cfg
   04_a20_line_and_gdt_mode_switch
   05_linux_boot_protocol_structs
   06_vmlinuz_elf_initrd_loading
