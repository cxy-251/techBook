第二十八章：GRUB normal 怎样从磁盘装入并打开 grub.cfg？
==========================================================

上一章结束时，BSP 仍在 CPU0 上执行 ``grub_main()``。处理器处于 32 位平坦保护模式，
paging 关闭，A20 已开启，``IF=0``、``DF=0``；GRUB heap、时间源和终端已经可用。
core.img 内嵌的 ``biosdisk``、``part_msdos`` 与 ``ext2`` 已注册，但没有打开的磁盘、
分区或文件对象。三个关键环境变量是：

::

   cmdpath = (hd0)
   root    = hd0,msdos1
   prefix  = (hd0,msdos1)/boot/grub

这里必须先纠正一个对象边界：本书采用的简单 ``grub-install`` 场景只把启动所必需的磁盘、
分区和文件系统模块及其依赖放入 core.img，``normal`` **没有**内嵌。因而
``grub_load_normal_mode()`` 的第一条实质路径不是命中已加载模块，而是从 ext4 动态读取
``normal.mod``。本章沿这条路径进入 normal mode，读取自动加载索引，再打开 ``grub.cfg``；
终点固定在配置文件第一条可解析行已经读入 heap、尚未调用
``grub_normal_parse_line()`` 的位置。

grub_dl_load 首先确认 normal 尚未出现
---------------------------------------

当前执行者仍是 ``grub_load_normal_mode()``：

.. code-block:: c

   grub_dl_load ("normal");

``grub_dl_load()`` 先用 ``grub_dl_get("normal")`` 查询全局 module list。查询失败并不是
错误，而是这次磁盘装载的入口。``grub_no_modules`` 没有置位，``prefix`` 又已经存在，函数便
按编译目标 ``i386-pc`` 拼出：

::

   (hd0,msdos1)/boot/grub/i386-pc/normal.mod

这个名称来自运行时 ``prefix`` 与编译期 ``GRUB_TARGET_CPU``、``GRUB_PLATFORM``，不是扫描磁盘
得到的候选项。若文件不存在、模块格式错误或依赖不能满足，``grub_load_normal_mode()`` 会打印并
清除错误，随后尝试执行 ``normal``；在本书固定成功路径中，文件和依赖均已由同一次 GRUB 安装放好。

第一个文件打开怎样重新建立 hd0,msdos1
-----------------------------------------

``grub_dl_load_file()`` 调用 ``grub_file_open()``。文件名开头的括号被拆成设备名
``hd0,msdos1``，其余部分成为文件系统路径 ``/boot/grub/i386-pc/normal.mod``。因为设备名已经
显式给出，``grub_device_open()`` 不需要用 ``root`` 补全。

``grub_disk_open("hd0,msdos1")`` 在第一个未转义逗号处分离原始磁盘与分区文本。已经注册的
``biosdisk`` 后端把 ``hd0`` 解释成 BIOS drive ``0x80``，为这次 open 分配
``grub_disk`` 与 biosdisk 私有数据。SeaBIOS 支持 INT 13h extensions，因此能力探测
``AH=41h`` 成功，``AH=48h`` 提供扩展参数；GRUB 仍会取得传统 CHS 几何，但数据读路径优先使用
LBA。保护模式中的 GRUB 通过实模式桥调用 ``INT 13h``，SeaBIOS 再把请求交给 q35 ICH9 AHCI
port 0 上的 SATA 磁盘。

``grub_partition_probe()`` 把显示编号 ``msdos1`` 转成内部编号 0。``part_msdos`` 读取 MBR
LBA 0，检查 ``0x55aa`` 签名、四个 boot flag 和 protective-GPT 类型，再返回第一个普通主分区。
本书固定镜像使它的起点为 LBA 2048。以后对该 ``grub_disk`` 的分区相对扇区访问，都会在下层加上
这个起点；``msdos1`` 不是另一个硬件设备。

ext2 驱动为什么能读取 ext4
---------------------------

设备建立后，``grub_fs_probe()`` 依次调用已注册文件系统的 ``fs_dir(device, "/", ...)``。
GRUB 名为 ``ext2`` 的驱动同时支持本场景所用的 ext4 特性；它先建立一个临时 mount data，读取
分区偏移 1024 字节处的 superblock，校验 magic 与 incompatible feature bits，并读取 root inode 2。
在 512 字节逻辑扇区的固定磁盘上，superblock 的首次位置是：

::

   partition-relative sector = 2
   whole-disk LBA             = 2048 + 2 = 2050

probe 的 dummy directory hook 一旦确认文件系统便返回，临时 mount data 随 ``fs_dir`` 结束释放。
随后真正的 ``grub_ext2_open()`` 再建立一份由 file object 持有的 mount data，沿 root inode 查找
``boot/grub/i386-pc/normal.mod``，把目标 inode 与文件大小写入 ``grub_file``，并令 offset 从 0
开始。这里出现两次 mount 是 probe 与 open 的两个生命期，不是两个同时遗留的文件系统对象。

具体元数据或文件块读可能命中 GRUB disk cache；cache miss 才继续到 BIOS INT 13h。因而固定源码
能够确定对象和地址换算，却不能仅凭提交号声称每个 inode 读取都产生一次新的 AHCI 命令。

normal.mod 先完整读入，再关闭文件
-----------------------------------

``grub_dl_load_file()`` 取得 ``normal.mod`` 大小，在 GRUB heap 分配同样大小的临时 buffer，
把文件完整读入。读取完成后，它在解析依赖之前调用 ``grub_file_close()``。关闭链释放 ext2 open
data、file、device、partition chain、``grub_disk`` 与 biosdisk 私有数据；ext2 模块引用也随 file
释放。磁盘 cache 中的块可以继续保留到失效时刻，但 cache 不等于仍有打开的磁盘对象。

先 close 的原因写在 ``grub_dl_load_file()`` 本身：有些 disk backend 不能安全处理同一设备的嵌套
open，而模块依赖可能马上再次打开同一磁盘。此时长期保留的是 heap 中的 ELF 文件镜像，不是原文件
句柄。

ET_REL 怎样成为正在运行的 normal 模块
----------------------------------------

``grub_dl_load_core()`` 把 buffer 交给 GRUB module loader。loader 要求 ELF 类型为 ``ET_REL``，
验证 section 范围，解析模块名、许可证和依赖，为 allocatable sections 分配运行内存，解析 GRUB
导出符号，完成 i386 重定位与内存属性设置，并刷新指令 cache。依赖也经
``grub_dl_load()`` 按同一 ``prefix/i386-pc/*.mod`` 规则装入。每个依赖的文件对象同样在处理其自身
依赖前关闭。

module 被加入全局 module list 后才调用 init。原始 ``normal.mod`` 文件镜像随
``grub_dl_load_core()`` 返回而释放；已重定位 sections、``grub_dl`` 元数据和依赖引用继续存活。
``grub_dl_load_file()`` 在返回前撤掉 loader 的临时引用，模块以后是否能卸载由真实持有者决定。

normal init 建立了哪些长期能力
-------------------------------

``GRUB_MOD_INIT(normal)`` 先兼容性地尝试 ``grub_dl_load("gzio")``，随后清除这次尝试的错误。
若 ``gzio`` 尚未装入，它也从固定模块目录动态读取。接着 init 初始化认证、environment context、
脚本与菜单子系统，把 ``grub_xputs`` 切换到 normal 实现，并为 normal 模块增加长期引用，防止它在
normal mode 期间被卸载。

此后 ``clear``、``normal``、``normal_exit``、``menuentry``、``submenu`` 等命令已经注册，
``pager`` 与颜色 hook 已安装，``grub_cpu=i386``、``grub_platform=pc`` 和 normal feature variables
已导出。这里仍没有 menu entry，也没有读取 ``grub.cfg``；这些只是后续解析可以依赖的运行设施。

``grub_load_normal_mode()`` 打印并清空装载阶段的错误后执行：

.. code-block:: c

   grub_command_execute ("normal", 0, 0);

此时命令表中的 ``normal`` 已经是刚才 init 注册的真实命令，控制流进入 ``grub_cmd_normal()``。

normal 命令只按 prefix 构造一个配置路径
------------------------------------------

当前 ``argc=0``。``grub_cmd_normal()`` 读取 ``prefix`` 并在末尾追加 ``/grub.cfg``：

::

   (hd0,msdos1)/boot/grub/grub.cfg

它不枚举分区，也不搜索多个本地配置。源码中的 UUID/TFTP 搜索只在 prefix 设备名以 ``tftp`` 开头
且没有禁用该功能时发生；固定本地磁盘路径不进入该分支。``grub_enter_normal_mode()`` 增加 normal
nested level，然后以 ``nested=0``、``batch=0`` 调用 ``grub_normal_execute()``。

四份 lst 是索引，不是四批预装模块
------------------------------------

顶层 normal mode 先调用 ``read_lists(prefix)``，依次尝试：

::

   /boot/grub/i386-pc/command.lst
   /boot/grub/i386-pc/fs.lst
   /boot/grub/i386-pc/crypto.lst
   /boot/grub/i386-pc/terminal.lst

每个完整名称都带同一个 ``(hd0,msdos1)`` prefix，因此分别经历 file、device、disk、partition 与
ext2 open。每份索引读完就关闭自己的对象；先前 disk cache 可以被后一次 open 复用。

``command.lst`` 的 ``name: module`` 行会为尚未加载的命令注册 dynamic placeholder，机器码仍留在
对应 ``.mod`` 文件中。``fs.lst``、``crypto.lst`` 与 ``terminal.lst`` 保存各自的自动加载映射，
也不等于立刻装入列出的全部模块。缺失索引的错误会被各读取函数清除，normal mode 可继续；直到配置
真的使用缺失映射，故障才落到具体命令或功能上。

列表读完后，normal 为 ``prefix`` 注册 write hook。以后配置若改变 prefix，hook 会重读这些索引与
翻译资源，使自动加载表跟随新的安装目录。当前配置尚未执行，prefix 仍是原值。

menu 容器先于 grub.cfg 文件创建
-------------------------------

``grub_normal_execute()`` 调用 ``read_config_file(config)``。函数先查询当前 environment context
中的 menu data slot；顶层首次进入没有 menu，于是分配清零的 ``struct grub_menu`` 并发布到该 slot：

::

   menu->entry_list = NULL
   menu->size       = 0

这个发布只建立容器。任何 ``menuentry`` 都还没有执行，``linux`` 与 ``initrd`` 更没有执行。

随后 ``grub_file_open()`` 才打开完整的 ``grub.cfg`` 路径。设备、MBR、分区和 ext4 查找与前面的
module/list 文件相同，只是最终 inode 换成 ``/boot/grub/grub.cfg``。成功的 raw file 被
``grub_bufio_open(rawfile, 0)`` 包装：默认 buffer 请求为 8192 字节，若文件更小便受文件大小限制，
再向上取适合二进制运算的 2 次幂。bufio wrapper 持有 raw file；关闭 wrapper 时才会递归关闭 raw
file，并把 wrapper 的 device 指针清零以避免外层再次关闭同一设备。

配置读取期间还发布两个环境变量
----------------------------------

在读取第一行前，``read_config_file()`` 保存旧 ``config_file`` 与 ``config_directory``。当前顶层
没有旧值，于是设置并导出：

::

   config_file      = (hd0,msdos1)/boot/grub/grub.cfg
   config_directory = (hd0,msdos1)/boot/grub

这些值只描述正在执行的配置上下文；到文件处理完成时会恢复旧值，若原来不存在就 unset。现在文件仍在
读取中，所以两者仍有效。

``read_config_file_getline()`` 通过 bufio 取行。它只在返回字符串的第 0 个字节就是 ``#`` 时丢弃
该行；前导空格后的 ``#`` 不属于这条 C 级过滤，空行也会交给 parser。固定配置的第一条有效行被分配在
heap 中并赋给 ``line`` 后，下一条语句是：

.. code-block:: c

   grub_normal_parse_line (line, read_config_file_getline, file);

本章在调用发生前停止。此时 parser 尚未解释 ``set``，menu 仍为空。

本章结束状态
------------

* 当前执行者是 CPU0 上的 ``read_config_file()``，BSP 仍处于 32 位平坦保护模式，paging 关闭，
  ``IF=0``、``DF=0``。
* ``normal`` 不是 core.img 内嵌模块；它及所需依赖已从
  ``(hd0,msdos1)/boot/grub/i386-pc`` 动态装入、重定位、初始化并保留。
* ``biosdisk``、``part_msdos``、``ext2`` 仍已注册；module 与 lst 文件对象均已关闭，disk cache
  可仍保留块内容。
* ``prefix=(hd0,msdos1)/boot/grub``，``root=hd0,msdos1``；prefix write hook 与四类自动加载索引
  已建立。
* menu 容器已发布，但 ``entry_list=NULL``、``size=0``。
* ``grub.cfg`` 的 bufio wrapper、raw file、ext2 open data、partition/disk/device 对象仍存活并相互持有。
* ``config_file`` 与 ``config_directory`` 已在配置上下文中设置并导出。
* 第一条可解析行已在 heap 中，``grub_normal_parse_line()`` 尚未调用；Linux 镜像和 initramfs 均未打开。

关键边界
--------

* embedded prefix 与“normal 已内嵌”不是一回事；本场景的第一项动态装载正是 ``normal.mod``。
* ``grub_dl_load_file()`` 在处理依赖前关闭模块文件；长期 module sections 与临时 ELF 文件镜像是两类对象。
* ``grub_fs_probe()`` 的临时 ext2 mount 与真正 ``fs_open`` 持有的 mount data 不可合并。
* MBR 分区起点、ext4 块映射和 BIOS LBA 是三层地址；固定 superblock 首地址可算为整盘 LBA 2050，
  任意文件数据块 LBA 则必须由实际 inode/extent 决定。
* bufio wrapper 仍代表一个打开的配置文件；只有第 029 章读到 EOF 并 close 后，这条对象链才消失。

下一入口
--------

.. code-block:: c

   grub_normal_parse_line (line, read_config_file_getline, file);

下一章固定本书的最小 ``grub.cfg``，追踪 ``set timeout``、``set default`` 与多行 ``menuentry``
怎样立即解析执行并生成一份长期 menu entry；``linux`` body 仍不会在建表时执行。

资料
----

* `GNU GRUB 2.14 grub-core/kern/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c>`_
* `GNU GRUB 2.14 grub-core/kern/dl.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c>`_
* `GNU GRUB 2.14 grub-core/kern/file.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/file.c>`_
* `GNU GRUB 2.14 grub-core/kern/disk.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/disk.c>`_
* `GNU GRUB 2.14 grub-core/kern/fs.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/fs.c>`_
* `GNU GRUB 2.14 grub-core/partmap/msdos.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/partmap/msdos.c>`_
* `GNU GRUB 2.14 grub-core/fs/ext2.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/fs/ext2.c>`_
* `GNU GRUB 2.14 grub-core/io/bufio.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/io/bufio.c>`_
* `GNU GRUB 2.14 grub-core/normal/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/main.c>`_
* `GNU GRUB 2.14 grub-core/normal/dyncmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/dyncmd.c>`_
* `GNU SeaBIOS hw/blockcmd.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/blockcmd.c>`_
* `QEMU hw/ide/ich.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/ide/ich.c>`_
