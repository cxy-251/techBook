第二十七章：GRUB 怎样加载内建模块并建立 hd0、root 和 prefix？
============================================================

上一章结束时，``grub_machine_init()`` 已经返回。GRUB 现在拥有可用堆、早期字符控制台和毫秒时间源，
终于能够把 ``core.img`` 中预装的对象变成真正可调用的模块和设备接口。

``grub_main()`` 接下来的主流程是：

.. code-block:: c

   grub_verifiers_init();
   grub_load_config();
   grub_register_exported_symbols();
   grub_load_modules();
   grub_set_prefix_and_root();
   reclaim_module_space();
   grub_register_core_commands();

这一章停在 embedded config 执行之前。它要回答三个容易混在一起的问题：

#. ``core.img`` 中的 ``.mod`` 文件什么时候真正执行初始化函数；
#. BIOS 驱动号 ``0x80`` 怎样变成 GRUB 设备名 ``hd0``；
#. 启动盘信息和 embedded prefix 怎样合并成 ``root=hd0,msdos1`` 与
   ``prefix=(hd0,msdos1)/boot/grub``。

本书固定 core.img 中的最小模块集合
---------------------------------

当前固定磁盘布局继续补充为：

::

   MBR partition table
   first partition = msdos1, starts at LBA 2048
   filesystem      = ext4
   GRUB directory  = /boot/grub

为了让后续路径唯一，本书固定 ``core.img`` 至少嵌入以下模块及其自动依赖：

::

   biosdisk
   part_msdos
   ext2
   normal

模块名 ``ext2`` 并不表示只能读取 ext2。GRUB 的 ``ext2`` 文件系统模块同时实现 ext2、ext3 和
ext4 家族所需的读取能力。

``grub-mkimage`` 会先解析 ``moddep.lst``，把显式模块和依赖都作为 ``OBJ_TYPE_ELF`` 对象附加到
core 映像；它还附加一个 ``OBJ_TYPE_PREFIX`` 对象。当前 prefix 固定为：

::

   (,msdos1)/boot/grub

这里故意没有写驱动名。``grub-install`` 已经知道 GRUB 文件位于第一块启动盘的第一个 MBR 分区，
但运行时的 BIOS 驱动号应由固件传入，所以它只把分区部分 ``,msdos1`` 硬编码进 prefix。

先建立 verifier API，不等于已经验证了所有文件
---------------------------------------------

``grub_main()`` 在欢迎信息之后调用：

.. code-block:: c

   grub_verifiers_init();

这一步建立 GRUB 文件验证器框架。以后加载模块、内核或配置时，签名验证模块可以挂接到该框架。

当前普通 SeaBIOS 主线没有 Secure Boot，也没有因此自动拒绝未签名文件。这里发生的是 API 和验证器
链表初始化，不应写成“GRUB 已完成安全启动验证”。

embedded config 与磁盘上的 grub.cfg 不是同一个对象
----------------------------------------------------

随后 ``grub_load_config()`` 遍历预装对象，寻找：

::

   header->type == OBJ_TYPE_CONFIG

若存在，它会把文本复制到堆上并保存到 ``load_config``，稍后在加载 ``normal`` 之前执行。

当前固定的简单路径满足：

* BIOS ``biosdisk`` 访问；
* GRUB 目录与安装目标位于同一块磁盘；
* 没有 LVM、RAID、加密磁盘或跨盘启动；
* 分区号可以写进 embedded prefix。

因此不需要安装器额外生成 ``load.cfg`` 搜索脚本，本书固定：

::

   embedded OBJ_TYPE_CONFIG = absent
   load_config              = NULL

这不代表磁盘上没有 ``grub.cfg``。真正的
``(hd0,msdos1)/boot/grub/grub.cfg`` 仍将在下一章由 normal mode 打开。

为什么必须先注册 core 导出符号
-----------------------------

动态模块会引用 GRUB core 提供的函数，例如：

::

   grub_malloc
   grub_free
   grub_disk_dev_register
   grub_fs_register
   grub_register_command
   grub_bios_interrupt

所以 ``grub_load_modules()`` 前先执行：

.. code-block:: c

   grub_register_exported_symbols();

该函数由构建过程生成，把可供模块使用的 core 符号加入 GRUB 自己的符号表。没有这一步，模块 ELF
重定位时只能看到未解析的外部符号，无法得到正确函数地址。

core.img 里的模块还不是可直接执行的代码
--------------------------------------

``grub_load_modules()`` 使用 ``FOR_MODULES`` 遍历 ``grub_modbase`` 指向的 ``gmim`` 区域。每个对象
都有：

::

   type
   size
   payload

只有 ``OBJ_TYPE_ELF`` 会送入：

.. code-block:: c

   grub_dl_load_core(payload, payload_size);

嵌入 core.img 的模块是可重定位 ELF，也就是 ``ET_REL``，并没有一个安装时已经固定好的运行地址。
``grub_dl_load_core_noinit()`` 逐步完成：

#. 验证 ELF header 和 section table 都位于对象边界内；
#. 确认 ``e_type == ET_REL``；
#. 读取模块名和许可证信息；
#. 解析模块依赖；
#. 从刚建立的 GRUB heap 为 alloc section 分配运行内存；
#. 把代码、只读数据和可写数据复制到新位置；
#. 解析对 core 和其他模块导出符号的引用；
#. 应用 i386 ELF relocation；
#. 刷新指令缓存接口；
#. 把模块加入已加载模块链表。

所以 ``core.img`` 中的原始模块区域只是输入材料。真正运行的模块代码和数据已经被重新分配到 heap。

GRUB_MOD_INIT 什么时候执行
-------------------------

完成装载和重定位后，``grub_dl_load_core()`` 调用：

.. code-block:: c

   grub_dl_init(mod);

这会执行模块通过 ``GRUB_MOD_INIT(name)`` 声明的初始化函数。

动态装载的意义就在这里。一个模块不是“代码存在内存中”就自动生效；它必须执行 init，把自己注册到
GRUB 的全局框架中。例如：

* disk module 注册 ``struct grub_disk_dev``；
* partition module 注册 ``struct grub_partition_map``；
* filesystem module 注册 ``struct grub_fs``；
* command module 注册命令名与处理函数；
* terminal module 注册输入输出终端。

biosdisk 模块注册的是后端，不是一张预先生成的磁盘对象表
-------------------------------------------------------

``biosdisk`` 的初始化函数最终执行：

.. code-block:: c

   grub_disk_dev_register(&grub_biosdisk_dev);

``grub_biosdisk_dev`` 提供：

::

   disk_iterate
   disk_open
   disk_close
   disk_read
   disk_write

它把 GRUB 通用磁盘层连接到 BIOS ``INT 13h``。此时并没有为每块磁盘永久创建一个 ``hd0`` 结构体；
GRUB 注册的是一套能够按名称打开 BIOS 磁盘的操作表。

当通用磁盘层之后要求打开 ``hd0`` 时，``grub_biosdisk_get_drive()`` 解析：

::

   hd0
   → name starts with "hd"
   → numeric suffix = 0
   → BIOS hard-disk flag 0x80
   → BIOS drive = 0x80

同理：

::

   hd1 → BIOS 0x81
   fd0 → BIOS 0x00

所以 ``hd0`` 不是 SeaBIOS 传给 GRUB 的字符串。SeaBIOS 传入的是 ``DL=0x80``，GRUB 的 biosdisk
命名规则把它表示成 ``hd0``。

为什么 biosdisk 还会再次调用 INT 13h
-----------------------------------

以后打开或枚举 ``hd0`` 时，biosdisk 会通过保护模式/实模式桥调用 SeaBIOS：

* ``AH=41h`` 检查 EDD；
* ``AH=48h`` 取得扩展驱动参数；
* ``AH=08h`` 取得 CHS 回退几何；
* ``AH=42h`` 按 LBA 读取；
* ``AH=02h`` 作为旧式 CHS 回退。

读写数据仍使用物理 ``0x68000`` 的 scratch/bounce buffer，然后复制到 GRUB 调用者的目标缓冲区。

前面 ``boot.img`` 和 ``diskboot.img`` 直接手写 BIOS 调用，是因为模块系统尚不存在；现在 core 已经
运行，所有后续磁盘访问都可以经由 ``grub_disk`` 抽象和 ``biosdisk`` 后端完成。

part_msdos 与 ext2 分别解决哪一层
--------------------------------

``part_msdos`` 模块负责解释磁盘 LBA 0 中从偏移 ``0x1be`` 开始的四项 MBR partition entry，把第一项
表示成：

::

   msdos1

它只解决“分区从哪里开始、长度是多少”。

``ext2`` 模块负责在该分区范围内读取 ext4 superblock、inode、目录和文件数据。它解决的是：

::

   /boot/grub/grub.cfg 在分区文件系统中的位置

两者不能互相替代：

::

   biosdisk    物理/固件磁盘扇区访问
   part_msdos  MBR 分区切片
   ext2        ext4 文件系统解释
   normal      配置语言和菜单环境

从 grub_boot_device 得到 fwdevice=hd0
------------------------------------

模块加载完成后，``grub_set_prefix_and_root()`` 先调用：

.. code-block:: c

   grub_machine_get_bootlocation(&fwdevice, &fwpath);

当前：

::

   grub_boot_device = 0x80ffffff

字段被拆为：

::

   boot_drive = 0x80
   dos_part   = 0xff
   bsd_part   = 0xff

``0xff`` 表示该字段没有在早期 boot device 编码中指定。函数先根据 ``0x80`` 生成：

::

   fwdevice = "hd0"
   fwpath   = NULL

这里仍然只有启动磁盘，没有分区。

embedded prefix 怎样补上 msdos1
-------------------------------

``grub_set_prefix_and_root()`` 接着扫描 ``OBJ_TYPE_PREFIX``，取得：

::

   (,msdos1)/boot/grub

它把右括号前解析成 device 部分：

::

   ,msdos1

把右括号后的内容解析成 path：

::

   /boot/grub

device 以逗号开头，表示“分区已经确定，驱动名仍需由固件启动位置补充”。函数于是从 ``fwdevice``
中取驱动部分 ``hd0``，拼接得到：

::

   hd0 + ,msdos1 = hd0,msdos1

最终设置：

::

   cmdpath = (hd0)
   root    = hd0,msdos1
   prefix  = (hd0,msdos1)/boot/grub

``root`` 不带括号保存；在命令或文件名中引用设备时才写成 ``(hd0,msdos1)``。

为什么 root 和 prefix 都要存在
-----------------------------

``root`` 是未显式写设备名的文件路径所使用的默认设备。例如：

::

   /vmlinuz

可被解释为当前 root 设备上的文件。

``prefix`` 是 GRUB 自身资源目录。它用于寻找：

::

   (hd0,msdos1)/boot/grub/i386-pc/*.mod
   (hd0,msdos1)/boot/grub/*.lst
   (hd0,msdos1)/boot/grub/grub.cfg
   (hd0,msdos1)/boot/grub/fonts/...

两者当前指向同一分区，但语义不同。以后 ``grub.cfg`` 可以修改 ``root``，而 ``prefix`` 仍描述 GRUB
自己的模块和配置目录。

原始预装模块区什么时候可以归还堆
--------------------------------

模块已被重定位到 heap，embedded prefix 已复制到环境变量，embedded config 当前不存在，所以原来
1 MiB 附近的输入对象区不再需要长期保留。

``reclaim_module_space()`` 在 PC BIOS 目标中使用：

::

   modstart = 0x100000
   modend   = grub_modules_get_end()

然后把：

::

   [modstart, modend)

再次交给 ``grub_mm_init_region()``。

``GRUB_KERNEL_PRELOAD_SPACE_REUSABLE`` 对 PC BIOS 明确为 1。由于 allocator 支持合并相邻 region，
这块空间可能与上一章已经建立的高端堆合并。

这解释了为什么上一章必须先保护模块区，而这一章又会把它回收：

::

   加载前  原始 ELF/prefix 仍是唯一副本，不能覆盖
   加载后  模块已重定位，字符串已复制，原始输入可以复用

最后注册 core 自带命令
---------------------

``grub_register_core_commands()`` 注册不依赖额外模块即可使用的基础命令。到这里，GRUB 已经拥有：

* 可用 heap；
* BIOS console；
* 模块和符号系统；
* BIOS disk backend；
* MBR partition map；
* ext4 文件读取能力；
* normal mode 命令；
* 正确的 ``root`` 与 ``prefix``。

本章结束时的状态
----------------

::

   当前执行者       GNU GRUB 2.14 grub_main()
   CPU 模式          32 位保护模式
   paging            off
   heap              已建立，并回收原预装模块输入区
   exported symbols  已注册
   built-in ELF      已验证、重定位并执行 GRUB_MOD_INIT
   biosdisk          已注册到通用 disk 层
   BIOS drive 0x80   可按名称 hd0 打开
   partition map     part_msdos 已注册
   filesystem        ext2 模块已注册，可读取固定 ext4 分区
   normal            normal 命令和 normal 环境已注册
   cmdpath           (hd0)
   root              hd0,msdos1
   prefix            (hd0,msdos1)/boot/grub
   embedded config   absent
   disk grub.cfg     尚未打开
   menu              尚未建立
   Linux bzImage     尚未读取

``grub_main()`` 接下来会尝试进入 normal mode。normal 命令将根据 ``prefix`` 构造完整配置文件名，并
第一次通过 ``biosdisk → part_msdos → ext2`` 打开磁盘上的 ``grub.cfg``。

资料
----

* `GNU GRUB 2.14 grub-core/kern/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c>`_
* `GNU GRUB 2.14 grub-core/kern/dl.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c>`_
* `GNU GRUB 2.14 grub-core/kern/i386/pc/init.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c>`_
* `GNU GRUB 2.14 grub-core/disk/i386/pc/biosdisk.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/disk/i386/pc/biosdisk.c>`_
* `GNU GRUB 2.14 util/grub-install.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/grub-install.c>`_
* `GNU GRUB 2.14 util/grub-install-common.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/grub-install-common.c>`_
* `GNU GRUB 2.14 util/mkimage.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/mkimage.c>`_
* `GNU GRUB 2.14 include/grub/kernel.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/kernel.h>`_
