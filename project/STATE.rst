项目状态
========

最后更新
--------

2026-07-12

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-032``。最新章节：

``LK-BOOT-032``：GRUB 怎样把 initramfs 放到内核允许的高地址？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，各章起止入口见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

固定来源与布局
--------------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 6.12.95
   Linux source tag  = gregkh/linux v6.12.95
   target            = i386-pc
   partition table   = MBR
   first partition   = LBA 2048
   filesystem        = ext4
   GRUB directory    = /boot/grub
   kernel            = /boot/bzImage-6.12.95
   initramfs         = /boot/initramfs-6.12.95.img

固定 grub.cfg
-------------

.. code-block:: cfg

   set timeout=0
   set default=0

   menuentry 'Linux 6.12.95' {
       linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs-6.12.95.img
   }

当前控制流位置
--------------

第三十二章结束在：

::

   grub_cmd_initrd()
   → verify kernel loader is already present
   → open /boot/initramfs-6.12.95.img with NO_DECOMPRESS
   → size = true file size
   → aligned_size = ALIGN_UP(size, 4096)
   → addr_max = min(initrd_addr_max, 0x37ffffff, optional mem=)
   → addr_max -= 0x10000
   → addr_min = prot_mode_target + prot_init_space
   → choose high 4 KiB-aligned target
   → allocate relocator chunk
   → copy original initramfs bytes
   → ramdisk_image = initrd_mem_target
   → ramdisk_size = size
   → close initrd components
   → finish entry sourcecode
   → stop before implicit grub_command_execute("boot")

此刻机器状态：

* 当前执行者：GNU GRUB 2.14 菜单项执行路径；
* 当前主流程 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* Linux protected-mode payload：已装入 relocator chunk；
* initramfs：已装入另一个 relocator chunk；
* initramfs 内容：保持磁盘原始字节，GRUB 未解压；
* ``linux_params.hdr.ramdisk_image``：已填写；
* ``linux_params.hdr.ramdisk_size``：已填写；
* kernel command line：``BOOT_IMAGE=/boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0``；
* loader hook：``grub_linux_boot``；
* entry sourcecode：执行完成；
* 隐式 ``boot``：尚未调用；
* Linux payload：尚未解压；
* Linux：尚未取得控制权。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``grub_menu_execute_entry()`` 的隐式 ``grub_command_execute("boot")`` 开始，追踪 loader hook 调用、video 信息、低端 ``boot_params``、命令行、E820、relocator 最终搬运和 32 位寄存器状态，直到 ``EIP=code32_start``、``ESI=boot_params`` 进入 Linux compressed ``startup_32``。
