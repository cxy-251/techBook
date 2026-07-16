项目状态
========

最后更新
--------

2026-07-16。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-030
   verified_through     = 030
   blocked batches      = none
   next batch           = 031-033
   next batch status    = ready

历史正文已经写到第193章，但只有001—030按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。031—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`028—030审查报告 <audits/linux-kernel/028-030.rst>`_：状态 ``repaired``。

本批修复了：

* 第028章撤销“normal已内嵌、 ``grub_dl_load`` 直接返回”的错误；simple-install路径从
  ``prefix/i386-pc/normal.mod`` 首次实际打开BIOS disk、MSDOS partition与ext4；
* 第028章补齐module file在dependency processing前关闭、临时ELF buffer与长期sections、
  fs probe/open两份ext2 mount data、disk cache和bufio/raw file所有权边界；
* 第029章把旧 ``Linux 6.12.95`` 改为固定 ``Linux 7.2-rc1``，并显式约定磁盘中的
  ``/boot/bzImage``、 ``/boot/initramfs.img`` 与最小 ``grub.cfg``；
* 第029章核定逐语法单元parse/execute/unref、多行menuentry callback、sourcecode复制、entry
  独立所有权、默认 ``restricted=1``，以及EOF后config变量恢复和配置文件关闭；
* 第030章核定timeout=0在menu viewer初始化前选中index 0，restricted auth因未设置superusers
  而短路，chosen发布、default暂时unset和entry新scope；
* 第030章补齐linux dynamic placeholder的精确flags、linux.mod先关闭file再重定位/init、module
  ref，以及注销placeholder后重新查找真实linux command的顺序；
* 三章均按连续时间线重写，章末统一为
  ``本章结束状态 → 关键边界 → 下一入口 → 资料``。

第030章已验证结束状态
---------------------

::

   current executor       = CPU0 BSP in grub_dyncmd_dispatcher
   exact next call        = grub_cmd_linux(cmd, 4, args)
   CPU mode               = 32-bit flat protected mode
   paging                 = disabled
   A20                    = enabled
   FLAGS                  = IF=0, DF=0
   root                   = hd0,msdos1
   prefix                 = (hd0,msdos1)/boot/grub
   config_file            = unset after EOF
   config_directory       = unset after EOF
   menu size              = 1
   selected entry         = Linux 7.2-rc1 / index 0
   entry restricted       = 1; auth succeeded because superusers is unset
   chosen                 = Linux 7.2-rc1, exported
   default                = temporarily unset; old value "0" saved for return
   timeout                = "0"
   entry scope            = active; setparams completed
   linux argc             = 4
   linux args             = /boot/bzImage; root=/dev/sda1; ro; console=ttyS0
   linux placeholder      = unregistered
   linux.mod              = loaded, relocated, initialized and ref-held
   real linux command     = registered; cmd->func is grub_cmd_linux
   real initrd command    = registered
   module file objects    = closed
   disk/partition/fs/file = none open; disk cache may retain blocks
   bzImage                = not opened
   initramfs              = not opened
   loader hook            = not installed
   Linux                  = not executing

timeout fast path的 ``auto_boot``、 ``grub_show_menu`` 的 ``autoboot`` 与fallback wrapper的
``autobooted`` 是不同参数。本章真实路径由fallback wrapper以 ``auto_boot=1`` 执行entry；当前entry
不是submenu。dynamic dispatcher仍持有脚本展开的argc/args，下一条普通command call才进入loader。

固定磁盘内容约定
----------------

::

   /boot/grub/grub.cfg:
     set timeout=0
     set default=0
     menuentry 'Linux 7.2-rc1' {
         linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
         initrd /boot/initramfs.img
     }

``/boot/bzImage`` 固定为Linux release 7.2-rc1、gregkh/linux commit
``7404ce51637231382873d0b55edabc2f3b841a9d`` 构建结果；initramfs与本场景匹配。
这些是显式镜像约定，不是源码commit自动产生的artifact路径。具体文件size、inode、extent、LBA和
relocator target仍须按实际artifact/runtime header确定，后续正文不得制造数值。

下一入口
--------

第031章从 ``grub_dyncmd_dispatcher()`` 调用真实command继续：

::

   grub_cmd_linux(cmd, 4, args)
   → grub_dl_ref(my_mod)
   → grub_file_open("/boot/bzImage", GRUB_FILE_TYPE_LINUX_KERNEL)
   → no explicit device, so grub_device_open(NULL) uses root=hd0,msdos1
   → validate Linux/x86 setup header from the fixed 7.2-rc1 image
   → allocate relocator-backed kernel/setup/cmdline state
   → grub_loader_set(grub_linux_boot, grub_linux_unload, 0)

031—033必须把旧 ``6.12.95`` 源码、title与artifact路径全部改为固定7.2-rc1路径，并重新核定：

* ``grub_cmd_linux`` 的file/module/relocator引用与失败回滚；
* setup header字段、protocol version、pref_address/init_size/kernel_alignment等值哪些来自实际
  bzImage header，哪些能由固定Linux构建配置确定；
* initrd components、地址上下界、4 KiB alignment、ramdisk字段与sourcecode结束边界；
* implicit boot、preboot hooks、machine_fini、boot_params最终复制、E820/command line、relocator32
  trampoline与Linux compressed ``startup_32`` 的精确交接寄存器；
* 第034章开头必须与第033章出口对齐，但第034章正文留给后续031—033之后的顺序批次。

031—033批次必须先读取
--------------------

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/028-030.rst`` 的“已核定的整批成功路径”、
   “失败与未发生边界”、“发现并修复”和“连续性检查”；
#. 第030章末尾、第031—033章全文和第034章开头；
#. 两份track manifest的审计游标片段；
#. 固定GRUB源码的i386 Linux loader、通用Linux/initrd loader、boot command、loader core、
   relocator、PC machine_fini、memory map和相关结构定义；
#. 固定Linux 7.2-rc1源码的x86 boot protocol、 ``arch/x86/boot/header.S``、compressed
   ``head_64.S`` 与本批实际引用的结构/常量；
#. 只有正文继续下钻INT 13h/AHCI副作用时，才补读固定SeaBIOS/QEMU路径。

不要读取001—029全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

四个固定工作树均为完整checkout而非sparse checkout，且必须保持干净。
``/Volumes/LinuxKernel/linux`` 是原有master工作树，不作为正文证据；固定Linux worktree由该仓库创建，
避免改变master。项目内 ``.sources/`` 不再承担当前源码缓存；旧 ``.gitignore`` 规则保留，防止未来误加
临时源码目录。

已知结构与内容债务
------------------

* 第031—034章仍使用旧 ``Linux 6.12.95`` 标签与版本化artifact路径；从031—033下一批开始顺序修复；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 031—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
