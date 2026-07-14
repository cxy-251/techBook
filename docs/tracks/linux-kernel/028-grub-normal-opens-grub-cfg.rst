第二十八章：GRUB normal 怎样找到并打开 grub.cfg？
=================================================

上一章结束时，GRUB 已经建立：

::

   cmdpath = (hd0)
   root    = hd0,msdos1
   prefix  = (hd0,msdos1)/boot/grub

``biosdisk``、``part_msdos``、``ext2`` 和 ``normal`` 模块也已经完成初始化。当前还没有菜单，
``grub.cfg`` 甚至尚未打开。

``grub_main()`` 接下来的调用是：

.. code-block:: c

   grub_load_normal_mode();

这一章追踪到配置文件第一条不以 ``#`` 开头的行已经读入内存、即将传给
``grub_normal_parse_line()`` 为止。配置语言怎样解析 ``set``、``insmod``、``menuentry`` 和
``linux`` 命令留给下一章。

normal 已经在内存中，为什么还要 grub_dl_load()
---------------------------------------------

``grub_load_normal_mode()`` 先执行：

.. code-block:: c

   grub_dl_load("normal");

上一章已经把 ``normal`` 作为 core.img 内建模块装载并初始化。``grub_dl_load()`` 首先查询已加载模块
链表，找到同名模块后直接返回，不会再从磁盘读取
``(hd0,msdos1)/boot/grub/i386-pc/normal.mod``。

保留这次调用的意义是让同一段 ``grub_main()`` 也能适应其他 core.img 组成：若 ``normal`` 没有内建，
GRUB 才会根据 ``prefix`` 从磁盘动态装载它。

随后：

.. code-block:: c

   grub_command_execute("normal", 0, 0);

模块初始化时已经把命令名 ``normal`` 注册到命令表，因此这里找到的是
``grub_cmd_normal()``。

normal 命令怎样得到完整配置文件名
---------------------------------

当前调用没有命令行参数，``argc == 0``。``grub_cmd_normal()`` 读取环境变量：

::

   prefix = (hd0,msdos1)/boot/grub

然后执行等价于：

.. code-block:: c

   config = prefix + "/grub.cfg";

得到：

::

   (hd0,msdos1)/boot/grub/grub.cfg

这不是在磁盘上搜索所有可能的配置文件。当前固定路径已经由安装时写入的 embedded prefix 和运行时
启动盘号共同确定，normal 只在该目录后附加固定文件名 ``grub.cfg``。

源码还包含 TFTP 网络启动时搜索带 UUID 后缀配置的分支。当前 prefix 以 ``(hd0,msdos1)`` 开头，
不是 ``(tftp...)``，所以不会进入网络配置搜索。

进入 normal mode 不代表菜单立即出现
------------------------------------

``grub_cmd_normal()`` 调用：

.. code-block:: c

   grub_enter_normal_mode(config);

它增加 normal mode 嵌套层级，再调用：

.. code-block:: c

   grub_normal_execute(config, 0, 0);

``nested=0`` 表示这是顶层 normal mode；``batch=0`` 表示配置执行结束后，如果确实形成了菜单，才会
进入交互菜单显示。

此刻菜单仍为空。``grub_normal_execute()`` 需要先准备自动加载索引，再打开和执行配置文件。

为什么先读取四类 lst 文件
-------------------------

顶层 normal mode 首先执行：

.. code-block:: c

   read_lists(prefix);

它尝试读取：

::

   (hd0,msdos1)/boot/grub/i386-pc/command.lst
   (hd0,msdos1)/boot/grub/i386-pc/fs.lst
   (hd0,msdos1)/boot/grub/i386-pc/crypto.lst
   (hd0,msdos1)/boot/grub/i386-pc/terminal.lst

这些文件不是 ``grub.cfg``，也不是需要立刻全部装入的模块。它们是名称到模块的索引：

* ``command.lst`` 记录某条命令由哪个 ``.mod`` 提供；
* ``fs.lst`` 记录可自动探测或装载的文件系统模块；
* ``crypto.lst`` 记录加密算法与模块；
* ``terminal.lst`` 记录终端驱动与模块。

以 ``command.lst`` 为例，每一项大致是：

::

   command-name: module-name

GRUB 会先为尚未装入的命令注册一个动态占位处理器。配置以后第一次执行该命令时，占位处理器才调用：

.. code-block:: c

   grub_dl_load(module_name);

模块完成初始化后，原占位命令被真正命令替换，然后再执行。

这让 core.img 不需要预装所有 GRUB 功能。它只保留启动所需的最小模块，其他功能按配置内容动态加载。

读取 lst 已经是第一次经文件系统访问 GRUB 目录
--------------------------------------------

四个索引文件同样通过 ``grub_file_open()`` 打开，因此在 ``grub.cfg`` 之前，GRUB 已经验证了这条磁盘
访问链能够工作：

::

   hd0
   → BIOS drive 0x80
   → msdos1
   → partition start LBA 2048
   → ext4 filesystem
   → /boot/grub/i386-pc/*.lst

索引文件缺失或某一项读取失败不会直接终止 normal mode。对应函数清除错误并继续；缺少的功能以后只会
在需要自动装载时无法找到模块映射。

``prefix`` 变化时为什么还要重新读列表
-------------------------------------

完成首次 ``read_lists(prefix)`` 后，normal 注册一个 ``prefix`` 环境变量写入 hook。

以后配置若执行：

::

   set prefix=(other-device)/other/path

hook 会重新读取新目录中的四类索引和翻译资源。这样模块自动加载表始终与当前 ``prefix`` 指向的 GRUB
安装目录一致。

现在开始创建 menu 容器
---------------------

随后：

.. code-block:: c

   menu = read_config_file(config);

``read_config_file()`` 先查询当前环境是否已有 menu。顶层第一次进入时没有，于是分配一个清零的
``struct grub_menu``，并把它挂入当前环境上下文。

此时：

::

   menu exists
   menu->entry_list = NULL
   menu->size       = 0

创建 menu 容器不代表已经存在启动项。真正的 ``menuentry`` 只有在下一章配置行被解析执行后才会加入。

``grub_file_open()`` 先拆设备名和文件路径
-----------------------------------------

配置路径是：

::

   (hd0,msdos1)/boot/grub/grub.cfg

``grub_file_open()`` 首先找出圆括号中的设备部分：

::

   device_name = hd0,msdos1

右括号后的部分成为文件系统内路径：

::

   file_name = /boot/grub/grub.cfg

随后调用：

.. code-block:: c

   grub_device_open("hd0,msdos1");

如果文件名没有显式设备，``grub_device_open(NULL)`` 才会回退到 ``root``。当前路径已经带完整设备名，
所以这里不需要隐式使用 ``root``。

``grub_disk_open()`` 怎样把 hd0 与 msdos1 分开
---------------------------------------------

``grub_device_open()`` 首先尝试磁盘设备，进入：

.. code-block:: c

   grub_disk_open("hd0,msdos1");

``grub_disk_open()`` 找到第一个未转义逗号，拆成：

::

   raw disk name = hd0
   partition text = msdos1

它先遍历已注册的 ``grub_disk_dev``。``biosdisk`` 后端识别 ``hd0``，把名称中的序号 0 加到 BIOS
硬盘起始号 ``0x80``：

::

   hd0 → BIOS drive 0x80

打开时，biosdisk 会通过 SeaBIOS ``INT 13h`` 查询驱动能力和几何信息。GRUB 仍处于 32 位保护模式，
调用仍通过 ``prot_to_real`` / ``real_to_prot`` 桥往返实模式。

分区解析为什么把 msdos1 转成内部编号 0
-------------------------------------

原始磁盘打开后，``grub_disk_open()`` 调用：

.. code-block:: c

   grub_partition_probe(disk, "msdos1");

解析器先分离字母前缀和数字：

::

   partition map name = msdos
   displayed number   = 1

对外名称从 1 开始，内部 ``partnum`` 从 0 开始，所以源码立即执行：

::

   1 - 1 = 0

它遍历已注册 partition map，找到 ``part_msdos`` 注册的 ``msdos`` 实现，然后从磁盘 LBA 0 读取 MBR。

``part_msdos`` 会检查：

* 末尾签名必须是 ``0x55aa``；
* 四项 boot flag 不能含非法位；
* protective GPT MBR 不应被当作普通 MBR；
* 扩展分区链不能形成循环。

当前固定磁盘第一项是普通主分区。它从 MBR entry 读取：

::

   start = 2048 sectors
   number = 0 internally
   name = msdos1 externally

返回的 ``grub_partition`` 被挂到 ``disk->partition``。从此以后，通用 ``grub_disk_read()`` 接收的是
分区内相对 sector，并在下发给 biosdisk 前加上分区起始 LBA。

ext2 模块怎样确认这其实是可读的 ext4
-----------------------------------

设备打开后，``grub_file_open()`` 调用：

.. code-block:: c

   grub_fs_probe(device);

已注册文件系统逐个尝试。``ext2`` 模块读取分区内偏移 1024 字节的 superblock：

::

   partition-relative sector = 2
   physical disk LBA         = 2048 + 2 = 2050

这是 512 字节逻辑扇区路径。它检查：

::

   superblock magic = 0xef53

并检查 incompatible feature bits。GRUB 2.14 的该模块明确理解多项 ext4 特性，包括 extents、flex_bg、
64-bit block numbers 和 meta_bg；对不支持且不能安全忽略的 incompatible feature 会拒绝挂载。

因此模块名字仍是 ``ext2``，当前固定分区可以是 ext4。GRUB 使用的是只读启动路径，不会回放日志或
把文件系统以 Linux VFS 的方式正式挂载。

从根 inode 2 逐级寻找 grub.cfg
-----------------------------

``grub_ext2_mount()`` 把 ext 家族根目录 inode 固定为：

::

   inode 2

``grub_ext2_open()`` 随后让通用 ``fshelp`` 路径查找器逐级解析：

::

   inode 2 /
   → boot
   → grub
   → grub.cfg

每一级都需要读取目录 inode、定位数据块、扫描目录项，并在遇到符号链接时调用 ext2 模块的 symlink
读取函数继续解析。

找到最终普通文件后，模块把 inode 的低 32 位和高 32 位 size 组合成 ``file->size``，保存当前 inode
和文件系统私有数据，并把 ``file->offset`` 置零。

底层数据最终怎样从 AHCI 硬盘进入 GRUB 缓冲区
-------------------------------------------

上述 MBR、superblock、inode、目录项和文件数据读取最终都会落到：

::

   grub_disk_read()
   → GRUB disk cache
   → biosdisk read
   → SeaBIOS INT 13h AH=42h
   → SeaBIOS AHCI driver
   → DMA between guest RAM and q35 AHCI port 0 disk

biosdisk 不能让传统 BIOS 随意 DMA 到 GRUB heap 中任意位置。它使用低端 scratch/bounce 区：

::

   0x68000...

SeaBIOS 先把扇区读到这块 BIOS 可表示的低端缓冲区，biosdisk 再复制到 GRUB 的目标缓冲区。

GRUB 通用磁盘层还带有 sector cache。同一组 MBR、superblock 或目录块被后续模块重复访问时，可以直接
命中缓存，减少实模式往返和 ``INT 13h`` 调用。

为什么打开后还要套一层 bufio
----------------------------

``grub_file_open()`` 成功后返回原始文件对象。``read_config_file()`` 接着执行：

.. code-block:: c

   file = grub_bufio_open(rawfile, 0);

配置解析按行进行，单次读取通常很小。如果每次取少量字符都直接向 ext2 和磁盘层发请求，会频繁进行
inode block 映射和 BIOS 磁盘访问。``bufio`` 在原文件之上增加顺序读取缓冲，后面的
``grub_file_getline()`` 优先从缓冲区取数据。

原始文件仍由该包装对象持有，关闭 ``bufio`` 时会一并释放底层文件、ext2 私有数据、partition 和
biosdisk 对象引用。

记录 config_file 和 config_directory
-------------------------------------

因为传入配置名本身以 ``(`` 开头，normal 直接设置：

::

   config_file = (hd0,msdos1)/boot/grub/grub.cfg

然后复制该字符串，找到最后一个 ``/`` 并截断，得到：

::

   config_directory = (hd0,msdos1)/boot/grub

两个变量都被 export。以后配置中的子配置、主题、字体或相对资源可以知道当前主配置文件及其所在目录。

如果 normal mode 是嵌套调用，函数会先保存旧值，配置执行完成后再恢复；当前顶层首次进入没有旧值。

第一行怎样到达解析器门口
------------------------

``read_config_file()`` 进入循环并调用：

.. code-block:: c

   read_config_file_getline(&line, 0, file);

内部使用：

.. code-block:: c

   line = grub_file_getline(file);

它按行从 bufio 中读取文本。若该行第一个字节就是 ``#``，normal 释放该行并继续取下一行。

这里的规则很具体：它只在 ``buf[0] == '#'`` 时由这一层直接跳过。前面带空格的 ``#``、空行、续行、
引号和 shell 语法都不在这个简单函数中解释，而要交给真正的脚本解析器。

当第一条不以 ``#`` 开头的行已经放进 ``line`` 后，下一条源码是：

.. code-block:: c

   grub_normal_parse_line(line, read_config_file_getline, file);

本章在这条调用执行前停止。

本章结束时的状态
----------------

::

   当前执行者       GNU GRUB 2.14 normal mode
   CPU 模式          32 位保护模式
   paging            off
   prefix            (hd0,msdos1)/boot/grub
   config path       (hd0,msdos1)/boot/grub/grub.cfg
   BIOS disk         hd0 → INT 13h drive 0x80
   partition         msdos1, physical start LBA 2048
   filesystem        ext2 module reading fixed ext4 filesystem
   config raw file   已打开
   bufio             已包装配置文件
   config_file       已导出
   config_directory  已导出
   menu object       已创建，仍无 menuentry
   config line       第一条不以 # 开头的行已读入内存
   parser            grub_normal_parse_line() 尚未调用
   Linux bzImage     尚未读取
   Linux             尚未取得控制权

下一章从 ``grub_normal_parse_line()`` 开始，进入 GRUB 脚本词法分析、命令查找和 ``menuentry`` 定义，
直到菜单对象真正获得第一个 Linux 启动项。

资料
----

* `GNU GRUB 2.14 grub-core/kern/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c>`_
* `GNU GRUB 2.14 grub-core/normal/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/main.c>`_
* `GNU GRUB 2.14 grub-core/normal/dyncmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/dyncmd.c>`_
* `GNU GRUB 2.14 grub-core/kern/file.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/file.c>`_
* `GNU GRUB 2.14 grub-core/kern/device.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/device.c>`_
* `GNU GRUB 2.14 grub-core/kern/disk.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/disk.c>`_
* `GNU GRUB 2.14 grub-core/kern/partition.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/partition.c>`_
* `GNU GRUB 2.14 grub-core/partmap/msdos.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/partmap/msdos.c>`_
* `GNU GRUB 2.14 grub-core/fs/ext2.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/fs/ext2.c>`_
* `GNU GRUB 2.14 grub-core/disk/i386/pc/biosdisk.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/disk/i386/pc/biosdisk.c>`_
