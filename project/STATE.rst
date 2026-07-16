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
   audit verified       = 001-027
   verified_through     = 027
   blocked batches      = none
   next batch           = 028-030
   next batch status    = ready

历史正文已经写到第193章，但只有001—027按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。028—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`025—027审查报告 <audits/linux-kernel/025-027.rst>`_：状态 ``repaired``。

本批修复了：

* 第025章把保存 ``DL`` 与INT 13h reset改回固定源码顺序，并核定当前SeaBIOS AHCI
  ``CMD_RESET`` 只走通用成功分支，不执行COMRESET或重新探测；
* 第025章补齐实模式/保护模式栈迁移、GDT selector、limit-0 IDT、A20 fallback、RS只保护
  已读入数据，以及LZMA 1 MiB输出与0x9000正式core两套地址身份；
* 第026章把console初始化收紧为只登记term对象，把E820固件payload地址修为
  ``ES:DI=6800:0004``，并补齐每项BIOS模式往返、32项候选上限、1 MiB/4 GiB裁剪和modend
  所有权边界；
* 第026章保留未唯一化CPU model带来的VIA workaround与TSC/RTC条件分支，并区分PIT校准、
  hardcoded rate与INT 1Ah fallback；
* 第027章撤销“default core内建normal”的关键错误：standard simple install只自动加入探测
  到的disk/partmap/fs后端及依赖，未显式 ``--modules`` 时 ``normal`` 缺席；
* 第027章区分module init注册方法表与打开 ``hd0``，固定 ``cmdpath/root/prefix`` 合成、
  环境字符串所有权、 ``[0x100000,modend)`` 回收和动态normal加载入口；
* 三章均改为连续时间线，并统一章末
  ``本章结束状态 → 关键边界 → 下一入口 → 资料``。

第027章已验证结束状态
---------------------

::

   current executor       = BSP in GNU GRUB 2.14 grub_main
   exact next call        = grub_load_normal_mode()
   CPU mode               = 32-bit flat protected mode
   paging                 = disabled
   A20                    = enabled and GRUB-verified
   FLAGS                  = IF=0, DF=0 on the protected-mode main path
   protected IDT          = limit 0
   formal core            = initialized image at link address 0x9000; BSS cleared
   grub_boot_device       = 0x80ffffff
   BIOS bridge            = available for later real-mode interrupts
   console                = BIOS input/output terms registered; Welcome already printed
   heap                   = initialized from filtered E820 regions
   time source            = installed; TSC/PIT or BIOS RTC according to runtime CPUID
   loaded modules         = biosdisk, part_msdos, ext2 and required dependencies
   registered backends    = BIOS disk, MSDOS partition map, ext2/ext3/ext4 reader
   grub_modbase           = 0
   reclaimed range        = [0x100000, modend), now allocator-owned
   cmdpath                = (hd0)
   root                   = hd0,msdos1
   prefix                 = (hd0,msdos1)/boot/grub
   embedded config        = absent under the simple-install convention
   normal module          = not embedded / not loaded
   open disk objects      = none
   partition/fs/file      = none opened
   grub.cfg / menu        = not read / not built
   Linux                  = not read / not executing

“loaded modules”沿用本批明确的simple-install叙事约定：i386-pc ``grub-install`` 使用默认
``biosdisk``，GRUB目录为第一块盘的 ``msdos1:/boot/grub``，安装到同一整盘，无
LVM/RAID/加密、debug或额外 ``--modules``。具体dependency集合与对象大小仍需artifact，
不在状态文件制造数值。

下一入口
--------

第028章从 ``grub_main()`` 的下一条调用继续：

::

   grub_load_normal_mode()
   → grub_dl_load("normal")
   → grub_dl_get("normal") misses
   → build (hd0,msdos1)/boot/grub/i386-pc/normal.mod
   → grub_file_open
   → grub_device_open
   → biosdisk opens BIOS drive 0x80
   → part_msdos reads MBR and selects partition 1
   → ext2 reader opens normal.mod from ext4

这是本书第一次由GRUB通用disk/partition/filesystem层实际打开当前磁盘对象；不能把
第027章“后端已注册”偷换成“磁盘已读取”。

028—030批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/025-027.rst`` 的“已核定的整批成功路径”、
   “失败与未发生边界”、“发现并修复”和“连续性检查”；
#. 第027章末尾、第028—030章全文和第031章开头；
#. 两份track manifest的审计游标片段；
#. 固定GRUB源码中 ``grub_load_normal_mode``、 ``grub_dl_load``/file-backed module loader、
   ``grub_file_open``、 ``grub_device_open``、PC ``biosdisk``、 ``part_msdos``、 ``ext2``、
   normal module init、 ``grub.cfg`` 查找/解析、menu创建与autoboot、linux module动态加载入口；
#. 只有正文实际下钻INT 13h或AHCI副作用时，才补读固定SeaBIOS/QEMU对应路径。

不要读取001—026全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669
   .sources/grub HEAD    = d38d6a1a9b79427848976f53d474392cd29c2a71

三个缓存均由 ``.gitignore`` 排除且源码worktree干净。QEMU和GRUB使用稀疏检出；GRUB当前已
包含boot/realmode/startup、PC init/mmap、allocator/module loader、grub-install、
biosdisk、part_msdos、ext2、normal等本批读取文件。下一批缺少文件时继续按需补齐，
不为未来章节预读全部源码。

已知结构与内容债务
------------------

* 第028章现有正文错误地假定 ``normal`` 已经嵌入并让 ``grub_dl_load`` 直接返回；固定
  simple-install路径是动态打开prefix下的 ``normal.mod``，028—030批次必须首先修正；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 028—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
