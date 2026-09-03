======================================================
模块 05：Linux 7.2 内核解压缩与 64 位长模式穿越
======================================================

本模块深入 Linux 7.2-rc1 内核解压缩子系统（`arch/x86/boot/compressed/`），解构 `head_64.S` 32 位汇编入口、位置无关代码 (PIC) 运行期基地址测算、早期 4 级/5 级页表（1GB/2MB 大页恒等映射）构建与 64 位长模式 (IA-32e) 穿越时序、Zstandard 极限解压算法与 KASLR 物理地址随机化，以及 ELF64 头部重定位与最终向内核 `startup_64` 的历史性跃迁。

.. toctree::
   :maxdepth: 2

   01_head_64_pic_relocation
   02_early_paging_and_long_mode
   03_decompression_zstd_kaslr
   04_elf64_parsing_kernel_jump
