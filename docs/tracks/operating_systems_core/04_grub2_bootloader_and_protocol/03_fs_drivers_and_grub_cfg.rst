========================================================================================
第 3 节：最小文件系统驱动实现（ext2/4, FAT, Btrfs）与 /boot/grub/grub.cfg 语法解析引擎
========================================================================================

.. note::
   **前置背景与上下文承接**
   * **体系结构基准**：承接模块 04 第 2 节中关于 ``core.img`` 在物理内存 1MB 边界（``0x00100000``）完成自解压、进入 32 位保护模式执行环境，以及 ``dl.c`` 动态模块加载器与符号解析机制的建立。
   * **核心使命**：解构 GRUB2 如何在完全脱离操作系统内核支持的极简环境中，实现针对工业级现代文件系统（ext4, FAT32, Btrfs）的轻量级只读驱动；剖析 VFS 虚拟文件系统抽象层（``struct grub_fs``）与底层磁盘块抽象（``struct grub_disk``）；深入 ext4 Inode 寻址、Extent 树多级索引递归解析、FAT32 簇链追踪与 Btrfs B-Tree 键值检索；解构 ``/boot/grub/grub.cfg`` 声明式脚本语法分析引擎（Lexer / Parser / AST）、环境变量上下文与交互式引导菜单状态机的微观时序。

----------------------------------------------------------------------------------------

第一幕：引导器中的微型 VFS——``struct grub_fs`` 与设备寻址拓扑
-------------------------------------------------------------

在操作系统接管计算机之前，GRUB2 必须能够从硬盘上复杂的文件系统目录（如 ``/boot/vmlinuz-7.2-generic``）中精准定位并读取内核文件。为此，GRUB2 在用户态/保护模式中构建了一套微型虚拟文件系统（VFS）。

1.1 统一的设备与文件路径抽象
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GRUB2 定义了一套严密的设备拓扑命名规范：

::

   (hd0,msdos1)/boot/grub/grub.cfg
    │   │      │
    │   │      └─► 分区内部绝对路径 (Absolute File Path)
    │   └────────► 分区方案与分区号 (MBR 分区 1 / GPT 分区 2)
    └────────────► 物理磁盘设备 (Hard Disk 0, 对应 BIOS 驱动器号 0x80)

1.2 ``struct grub_fs`` 驱动核心抽象（``include/grub/fs.h``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
所有支持的文件系统驱动均实现为一个标准的函数指针矩阵结构体 ``struct grub_fs``：

::

   struct grub_fs {
       const char *name;                       /* 驱动标识: "ext2", "fat", "btrfs", "xfs" */
       
       /* 目录项枚举回调: 用于 ls 命令与路径逐级补全 */
       grub_err_t (*dir)(grub_device_t device, const char *path,
                         grub_fs_dir_hook_t hook, void *hook_data);
       
       /* 打开文件: 校验超级块，解析 Inode 并填充 grub_file_t 结构 */
       grub_err_t (*open)(struct grub_file *file, const char *name);
       
       /* 读数据: 从当前文件偏移读取指定字节数至物理内存缓冲区 */
       grub_ssize_t (*read)(struct grub_file *file, char *buf, grub_size_t len);
       
       /* 关闭文件并释放局部缓存 */
       grub_err_t (*close)(struct grub_file *file);
       
       /* 读取文件系统卷标 (Volume Label) 与 UUID (用于 search 动态寻根) */
       grub_err_t (*label)(grub_device_t device, char **label);
       grub_err_t (*uuid)(grub_device_t device, char **uuid);
       
       struct grub_fs *next;                   /* 挂载在全局文件系统驱动链表 (grub_fs_list) */
   };

当新驱动模块（如 ``ext2.mod``）加载时，调用 ``grub_fs_register(&grub_ext2_fs)`` 注册至链表；当打开文件时，GRUB2 遍历链表，依次调用各驱动的 ``open()`` 探测超级块魔数，首个成功识别的驱动即接管该分区。

----------------------------------------------------------------------------------------

第二幕：现代 ext4 文件系统只读驱动微观解构（``ext2.c``）
---------------------------------------------------------

在 Linux 系统中，``ext4`` 是最广泛使用的 rootfs 文件系统。GRUB2 在 ``grub-core/fs/ext2.c`` 中实现了一个向下兼容 ext2/ext3 并完全支持 64 位 Extent 树索引的统一驱动。

2.1 超级块（Superblock）与块组描述符（Block Group Descriptor）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **超级块物理位置**：固定位于分区起始偏移 **``1024 字节 (0x400)``** 处（避开 MBR/启动扇区）；
* **魔数校验**：读取超级块偏移 ``0x38`` 处的 16 位整数，必须为 **``0xEF53``**；
* **关键几何参数提取**：
  * ``s_log_block_size``：块大小计算公式为 $	ext{BlockSize} = 1024 \ll 	ext{s\_log\_block\_size}$（典型值为 4096 字节）；
  * ``s_blocks_per_group``：每个块组包含的物理块数（典型值 32768）；
  * ``s_inodes_per_group``：每个块组包含的 Inode 数量（典型值 8192）；
  * ``s_inode_size``：单个 Inode 结构体大小（ext4 默认为 256 字节）。

2.2 Inode 物理定位公式推导
~~~~~~~~~~~~~~~~~~~~~~~~~~
当已知文件的 Inode 编号（根目录固定为 Inode 2）时，GRUB2 依照数学公式在磁盘上精确定位其物理字节偏移：

.. math::

   	ext{BlockGroup} = \frac{	ext{Inode} - 1}{	ext{s\_inodes\_per\_group}}

.. math::

   	ext{IndexInGroup} = (	ext{Inode} - 1) \pmod{	ext{s\_inodes\_per\_group}}

.. math::

   	ext{Inode\_Physical\_Offset} = (	ext{bg\_inode\_table} 	imes 	ext{BlockSize}) + (	ext{IndexInGroup} 	imes 	ext{s\_inode\_size})

2.3 Extent 树多级索引递归解析（取代传统间接块）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ext4 彻底废弃了传统 ext2 的 12 个直接块 + 间接块索引链，引入了 **Extent 树（区间树）**。在 Inode 结构体中，原本的 60 字节 ``i_block[15]`` 数组被重新定义为 Extent 树根节点：

::

   +-----------------------------------------------------------------------------------+
   |                               ext4 Extent 树物理结构                              |
   |                                                                                   |
   |  [struct ext4_extent_header (12 字节头部)]                                        |
   |  - eh_magic = 0xF30A (Extent 树魔数)                                              |
   |  - eh_entries: 当前节点包含的有效条目数量                                         |
   |  - eh_max: 当前节点最大条目容量                                                   |
   |  - eh_depth: 树深度 (0=当前为叶子节点, >0=内部索引节点)                           |
   +===================================================================================+
   |  情况 A：eh_depth == 0 (叶子节点，紧随 header 存放 struct ext4_extent)           |
   |  - ee_block: 该 Extent 覆盖的文件逻辑块起始号 (如 0)                              |
   |  - ee_len: 连续物理块数量 (最大可达 32768 个块 = 128MB 连续空间!)                 |
   |  - ee_start_lo / ee_start_hi: 48 位绝对物理磁盘块基地址                           |
   +-----------------------------------------------------------------------------------+
   |  情况 B：eh_depth > 0 (内部索引节点，存放 struct ext4_extent_idx)                 |
   |  - ei_block: 下级子树索引的最小逻辑块号                                          |
   |  - ei_leaf_lo / ei_leaf_hi: 存储下一级 Extent 节点的物理磁盘块地址                 |
   +-----------------------------------------------------------------------------------+

* **性能优势**：一个仅需 12 字节的 ``struct ext4_extent`` 条目即可连续映射多达 128MB 的物理磁盘数据。对于数十兆字节的 Linux 内核镜像（``vmlinuz``）与内存盘（``initrd``），GRUB2 仅需读取 1~2 个 Extent 条目即可完成全文件扇区映射，极大地加速了引导读取。

----------------------------------------------------------------------------------------

第三幕：FAT32 与 Btrfs 树状文件系统解析
---------------------------------------

3.1 FAT32 目录项与簇链追踪（``grub-core/fs/fat.c``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 UEFI 引导分区（ESP）或传统 U 盘引导中，FAT32 是绝对标准：
* **DBR 引导扇区参数**：读取每扇区字节数（512）、每簇扇区数（$S_c$）、保留扇区数（$S_r$）、FAT 表数量（2 份）；
* **簇号转绝对 LBA 物理扇区公式**：

.. math::

   	ext{LBA}_{	ext{cluster}} = 	ext{Data\_Start\_LBA} + (	ext{Cluster} - 2) 	imes S_c

* **簇链遍历（Cluster Chaining）**：FAT32 文件的数据由一张单向链表维系。每次读取一个簇后，GRUB2 访问保存在内存缓存中的第 1 份 FAT 表，读取 32 位表项获取下一簇号，直至遇到大于等于 ``0x0FFFFFF8`` 的 EOF 结束标记。

3.2 Btrfs COW 写时复制文件系统解析（``grub-core/fs/btrfs.c``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
现代 Linux 发行版（如 openSUSE、Fedora、Ubuntu）广泛采用 Btrfs：
* **超级块物理位置**：固定在分区偏移 ``0x10000 (64KB)``；
* **B-Tree 树状键值检索**：Btrfs 的一切数据与元数据均抽象为 $(Objectid, Type, Offset)$ 三元组键值对。GRUB2 遍历根节点树（Root Tree）找到默认子卷（如 ``@/boot``），再通过 Chunk Tree 进行物理地址映射，从 COW（写时复制）快照中精准读取内核。

----------------------------------------------------------------------------------------

第四幕：``/boot/grub/grub.cfg`` 语法解析引擎与 AST 构建
-------------------------------------------------------

当文件系统驱动成功定位到 ``/boot/grub/grub.cfg`` 文本文件后，GRUB2 的脚本解释器引擎开始运转。

4.1 脚本解释引擎架构（``grub-core/script/``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GRUB2 的配置脚本并非简单的 INI 键值对，而是一种功能完备的 **类 Bash 解释型脚本语言**：

::

   [grub.cfg 原始文本流]
            │
            ▼ 词法分析器 (Lexer, yylex)
   [Token 标记流: MENUENTRY, STRING, IF, THEN, SET...]
            │
            ▼ 语法分析器 (Bison/Yacc 生成的 Parser: grub_script_parse)
   [抽象语法树 (Abstract Syntax Tree, struct grub_script)]
            │
            ▼ 执行器 (Executor, grub_script_execute)
   [动态环境变量更新 (set root=...) + 注册菜单项到系统引导列表]

4.2 典型 ``grub.cfg`` 脚本片段在内存中的 AST 展开
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   set default="0"
   set timeout=5

   menuentry 'Linux 7.2-rc1 Mainline' --class ubuntu --class gnu-linux {
       search --no-floppy --fs-uuid --set=root e820a1b2-c3d4-4e5f-9a8b-123456789abc
       linux   /boot/vmlinuz-7.2-rc1 root=UUID=e820a1b2-... ro quiet splash
       initrd  /boot/initramfs-7.2-rc1.img
   }

1. **``set`` 节点**：调用 ``grub_env_set("default", "0")`` 与 ``grub_env_set("timeout", "5")`` 更新全局环境变量哈希表；
2. **``menuentry`` 节点**：在内存中分配一个 ``struct grub_menu_entry``，保存菜单显示标题、类选择器以及包裹在大括号内部的代码块指针（此时并不执行，仅在用户按下回车选中时求值）。

----------------------------------------------------------------------------------------

第五幕：交互式引导菜单状态机与倒计时选择
-----------------------------------------

在 ``grub-core/normal/menu.c`` 中，GRUB2 驱动图形/文本终端进入主交互循环：

5.1 屏幕绘制与终端渲染（``term.c`` / ``gfxmenu.mod``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **文本控制台模式**：通过调用此前初始化的 VGA/BIOS 接口，在 80x25 屏幕上绘制 ASCII 边框与菜单项列表；
* **高亮选择指示**：通过改变字符前景色与背景色属性（如黑底白字切换为蓝底白字）标识当前选中的引导条目。

5.2 倒计时时钟与按键状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~
在菜单显示主循环中，系统通过 PIT / RTC 时钟进行精确计时：

::

   +-----------------------------------------------------------------------------------+
   |                             GRUB2 菜单事件主循环                                  |
   |                                                                                   |
   |  [读取环境变量 timeout]                                                           |
   |  - 若 timeout > 0: 在屏幕底部打印 "The highlighted entry will be executed         |
   |    automatically in %d seconds...";                                               |
   |                                                                                   |
   |  [时钟与按键轮询循环]                                                             |
   |  1. 每隔 1 秒: timeout 递减 1，刷新屏幕倒计时数字;                                |
   |  2. 若 timeout == 0: 自动触发默认菜单项 (default entry) 执行!                     |
   |  3. 捕获按键 (grub_getkey()):                                                     |
   |     - UP / DOWN: 清除 timeout 倒计时 (用户介入)，切换高亮菜单索引;                |
   |     - 'e' (Edit): 弹出内联脚本编辑器，允许用户交互式临时修改 linux 内核参数       |
   |                   (如在末尾追加 "init=/bin/bash" 进入单用户救援模式);             |
   |     - 'c' (Command-line): 弹出全功能交互式 GRUB 终端命令行 (grub>);               |
   |     - ENTER: 终止菜单循环，开始执行选中的 menuentry 代码块!                       |
   +-----------------------------------------------------------------------------------+

当用户按下回车确认后，GRUB2 提取 ``linux`` 命令所指向的内核路径，正式启动向 **32 位保护模式/64 位长模式的彻底跃迁** 与 **Linux Boot Protocol 协议装配**。

----------------------------------------------------------------------------------------

小结与下章导读
--------------

本节系统化剖析了 GRUB2 的微型 VFS 抽象层（``struct grub_fs``）、ext4 Inode 与 Extent 树解析算法、FAT32 簇链追踪、Btrfs B-Tree 键值检索，以及 ``grub.cfg`` 语法解释器与交互式引导菜单状态机的微观运转。

当用户在菜单中选中内核并按下回车后，引导加载器面临着最后一道模式封印——为了向物理内存 1MB 以上空间装载动辄数十兆的现代 Linux 内核镜像（``vmlinuz``），CPU 必须彻底告别实模式，完成 A20 地址线的物理锁定、全局描述符表（GDT）重构，并在 32 位保护模式与 64 位长模式之间建立起畅通无阻的通道。

在 **第 4 节：打开 A20 地址线、加载 GDT 并完成 16 位实模式向 32 位保护模式/64 位长模式跃迁** 中，我们将深入剖析 GRUB2 如何在汇编层构筑最终的 GDT 描述符表、配置控制寄存器（CR0.PE, CR4.PAE, EFER.LME），并完成模式穿越。
