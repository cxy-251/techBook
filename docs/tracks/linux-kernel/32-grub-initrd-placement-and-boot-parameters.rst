第三十二章：GRUB 怎样把 initramfs 放到内核允许的高地址？
==========================================================

上一章结束时，``linux`` 命令已经完成了两件事：

* Linux ``bzImage`` 中的 protected-mode payload 已经读入 GRUB relocator 管理的内存；
* ``grub_loader_set()`` 已经登记 ``grub_linux_boot``，表示以后执行 ``boot`` 时应调用这个函数。

但启动参数里的：

::

   ramdisk_image = 0
   ramdisk_size  = 0

仍然表明没有 initramfs。固定菜单项的下一条命令是：

.. code-block:: cfg

   initrd /boot/initramfs-6.12.95.img

这一章继续执行这条命令，说明 GRUB 为什么不能把 initramfs 随便塞进一块空闲内存，以及它怎样同时满足内核初始化区、Linux/x86 Boot Protocol 和 32 位传统启动路径的地址限制。

``initrd`` 命令已经由 ``linux.mod`` 注册
------------------------------------------

第三十章中，动态命令占位符促使 GRUB 装入 ``linux.mod``。模块初始化函数同时注册两个真实命令：

.. code-block:: c

   cmd_linux = grub_register_command("linux", grub_cmd_linux, ...);
   cmd_initrd = grub_register_command("initrd", grub_cmd_initrd, ...);

因此脚本执行器处理菜单项第二行时，不需要再次装模块。它在全局命令表里直接找到 ``initrd``，然后调用：

.. code-block:: c

   grub_cmd_initrd(cmd, argc, argv)

当前只有一个参数：

::

   argv[0] = /boot/initramfs-6.12.95.img

``grub_cmd_initrd()`` 首先检查 ``loaded``。这个变量只有 ``linux`` 命令成功装入内核并登记 loader 后才会设为 1。若用户在 ``linux`` 之前写 ``initrd``，GRUB 会直接报错：

::

   you need to load the kernel first

这里的顺序要求不是语法习惯，而是地址计算依赖。GRUB 必须先知道内核被放在哪里、初始化阶段最多会占用多大范围，才能确定 initramfs 的最低安全地址。

GRUB 打开的是原始 initramfs 字节
--------------------------------

``grub_initrd_init()`` 为每个参数建立一个 component，并通过当前 ``root`` 打开文件。固定路径没有显式设备前缀，因此仍使用：

::

   root = hd0,msdos1

文件访问继续经过：

::

   biosdisk
   → part_msdos
   → ext2
   → /boot/initramfs-6.12.95.img

打开时带有：

.. code-block:: c

   GRUB_FILE_TYPE_LINUX_INITRD | GRUB_FILE_TYPE_NO_DECOMPRESS

``NO_DECOMPRESS`` 很重要。initramfs 文件本身可以是 gzip、xz、zstd 或其他 Linux 支持的压缩格式；GRUB 此时不把它展开成文件树，也不替 Linux 解压。它读取并复制磁盘上的原始字节，之后由 Linux 早期 initramfs 代码识别和解包。

GRUB 的通用 initrd helper 还支持多个文件以及 ``newc:目标名:源文件`` 形式，可现场拼接 cpio newc 记录。当前固定配置只传入一个普通文件，因此不会额外生成 newc header 或 ``TRAILER!!!``；最终大小就是该文件本身的字节数。

``size`` 和 ``aligned_size`` 不是一回事
--------------------------------------

文件打开后：

.. code-block:: c

   size = grub_get_initrd_size(&initrd_ctx);
   aligned_size = ALIGN_UP(size, 4096);

``size`` 是稍后写入 Linux boot parameters 的真实 initramfs 长度。

``aligned_size`` 是 GRUB 为 relocator 保留的物理地址范围，向上取整到 4 KiB。假设文件大小为：

::

   size = N

则保留区大小是：

::

   aligned_size = (N + 4095) & ~4095

最后一页末尾可能存在未使用空间，但 ``ramdisk_size`` 仍填写 ``N``，Linux 不会把页对齐填充误认为 initramfs 内容。

地址上界首先来自内核头
----------------------

Linux/x86 Boot Protocol 2.03 引入 ``initrd_addr_max``，让内核告诉 bootloader：initramfs 最后一个字节允许放到多高。

固定 Linux 6.12.95 ``bzImage`` 的 setup header 中，该字段由内核构建为：

::

   initrd_addr_max = 0x7fffffff

GRUB 先读取这个值：

.. code-block:: c

   addr_max = linux_params.hdr.initrd_addr_max;

但 i386 PC BIOS 启动路径不会完全接受这个上界。GRUB 又施加自己的限制：

.. code-block:: c

   if (addr_max > GRUB_LINUX_INITRD_MAX_ADDRESS)
       addr_max = GRUB_LINUX_INITRD_MAX_ADDRESS;

其中：

::

   GRUB_LINUX_INITRD_MAX_ADDRESS = 0x37ffffff

所以当前路径的有效上界先从 ``0x7fffffff`` 被压低到：

::

   0x37ffffff

这不是机器 RAM 的真实末端，也不是 initramfs 的最终起始地址。它是 GRUB 传统 32 位 Linux loader 为 initrd 使用的最高候选边界。

若内核命令行存在 ``mem=``，GRUB 还会把 ``linux_mem_size`` 作为更低的上限。固定命令行只有：

::

   root=/dev/sda1 ro console=ttyS0

因此本路径没有 ``mem=`` 进一步缩小地址范围。

为什么还要从上界减去 64 KiB
----------------------------

接下来源码执行：

.. code-block:: c

   addr_max -= 0x10000;

这 64 KiB 是 GRUB 为很老的 Linux 内核内存边界缺陷保留的兼容余量。Linux 6.12.95 本身不需要依靠这个古老 workaround，GRUB 的通用 i386 loader 仍然沿用这一安全规则。

因此当前候选上界成为：

::

   0x37ffffff - 0x10000 = 0x37feffff

后面的起始地址还要减去整个页对齐后的 initramfs 大小，并再向下按 4 KiB 对齐。

地址下界为什么是内核目标加 ``init_size``
----------------------------------------

上一章中，GRUB 读取 setup header 的：

::

   pref_address
   init_size
   relocatable_kernel
   kernel_alignment
   min_alignment

并为 protected-mode payload 选择了实际目标 ``prot_mode_target``。

``init_size`` 不是磁盘上压缩 payload 的文件大小。它表示内核从进入 compressed startup 到完成解压和早期重定位期间，需要保持可用的连续线性内存范围。

GRUB 将它向上按页对齐保存为：

::

   prot_init_space = page_align(init_size)

然后规定 initramfs 的最低地址：

.. code-block:: c

   addr_min = prot_mode_target + prot_init_space;

这意味着 initramfs 不能只避开磁盘上读入的压缩数据，还必须避开 compressed kernel 解压时可能使用的整个初始化工作区。

否则 Linux 解压自己的 payload 时，输出区、输入区或临时空间可能覆盖 initramfs。等内核稍后尝试挂载初始根文件系统时，读到的已经是被破坏的数据。

GRUB 从高地址向下放置 initramfs
-------------------------------

有了：

::

   addr_min = prot_mode_target + prot_init_space
   addr_max = min(initrd_addr_max, 0x37ffffff, optional mem=) - 0x10000

GRUB 先计算理想起点：

.. code-block:: c

   addr = (addr_max - aligned_size) & ~0xfff;

它的含义是：

#. 从允许上界减去 initramfs 页对齐后的占用大小；
#. 清除最低 12 位，使起点按 4 KiB 对齐；
#. 尽量让 initramfs 靠近允许范围的高端。

随后检查：

.. code-block:: c

   if (addr < addr_min)
       error("the initrd is too big");

所以“系统总内存能放下这个文件”还不够。必须在内核初始化区末端与 initrd 上界之间，找到一段足够大的连续区域。

relocator 仍然区分当前地址和最终物理地址
---------------------------------------

GRUB 请求 relocator 分配：

.. code-block:: c

   grub_relocator_alloc_chunk_align(
       relocator,
       &ch,
       addr_min,
       addr,
       aligned_size,
       0x1000,
       GRUB_RELOCATOR_PREFERENCE_HIGH,
       1);

参数表达了四个关键约束：

* 允许范围从 ``addr_min`` 到高端候选 ``addr``；
* 大小为 ``aligned_size``；
* 对齐为 ``0x1000``；
* 偏好高地址。

返回的 chunk 提供两个地址：

.. code-block:: c

   initrd_mem        = get_virtual_current_address(ch);
   initrd_mem_target = get_physical_target_address(ch);

``initrd_mem`` 是 GRUB 当前复制文件时使用的地址。

``initrd_mem_target`` 是 relocator 完成最终搬运后，Linux 将看到的物理地址。两者在某次布局中可能相同，但接口没有假设它们必须相同。

文件内容被完整复制到 chunk
--------------------------

``grub_initrd_load()`` 逐 component 读取内容。当前只有一个普通 component，因此主动作就是：

::

   从 ext4 文件读取 size 字节
   → 写入 initrd_mem

GRUB 不解析其中的 ``/init``、驱动模块或用户空间程序，也不会在此时检查 cpio 是否有效。对当前流程而言，它只是一个需要原样交给 Linux 的字节区间。

复制完成后，文件句柄会由 ``grub_initrd_close()`` 关闭，component 数组也被释放；relocator chunk 本身仍保留，因为后面的 Linux 启动还需要它。

``ramdisk_image`` 与 ``ramdisk_size`` 终于有值
--------------------------------------------

装载成功后：

.. code-block:: c

   linux_params.hdr.ramdisk_image = initrd_mem_target;
   linux_params.hdr.ramdisk_size  = size;
   linux_params.hdr.root_dev      = 0x0100;

前两个字段是 Linux 真正需要的信息：

::

   ramdisk_image = initramfs 最终物理起始地址
   ramdisk_size  = initramfs 真实字节数

``root_dev = 0x0100`` 是 GRUB 保留的历史兼容赋值。现代 Linux 的根文件系统选择主要由命令行 ``root=/dev/sda1`` 和 initramfs 早期用户空间决定，不依赖这个旧字段完成当前启动。

菜单项脚本到这里执行完毕
------------------------

``grub_cmd_initrd()`` 返回后，脚本执行器发现 entry sourcecode 已经没有下一条命令。当前固定菜单项：

.. code-block:: cfg

   menuentry 'Linux 6.12.95' {
       linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs-6.12.95.img
   }

已经全部执行完成。

现在内存中同时存在：

* protected-mode Linux payload；
* Linux 命令行；
* ``linux_params`` 模板；
* initramfs relocator chunk；
* 指向 ``grub_linux_boot`` 的 loader hook。

但 ``grub.cfg`` 并没有显式写 ``boot``。控制流返回 ``grub_menu_execute_entry()`` 后，它将检查：

.. code-block:: c

   if (grub_errno == GRUB_ERR_NONE && grub_loader_is_loaded())
       grub_command_execute("boot", 0, 0);

本章停在这次隐式 ``boot`` 调用之前。

当前机器状态
------------

* 当前执行者：GNU GRUB 2.14 菜单项脚本执行器；
* 当前主流程 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* ``bzImage`` protected-mode payload：已装入 relocator chunk；
* initramfs 文件：已从 ext4 读取并关闭；
* initramfs 内容：保持磁盘原始字节，GRUB 未解压；
* initramfs 目标：位于 ``prot_mode_target + prot_init_space`` 以上，并尽量靠近受限高地址；
* initramfs 对齐：4 KiB；
* ``ramdisk_image``：已写为 ``initrd_mem_target``；
* ``ramdisk_size``：已写为文件真实大小；
* entry sourcecode：执行完成；
* loader hook：``grub_linux_boot``；
* 隐式 ``boot``：尚未调用；
* Linux：尚未取得控制权。

下一段真实控制流是：

::

   grub_menu_execute_entry()
   → grub_command_execute("boot")
   → registered loader hook
   → grub_linux_boot()

资料
----

* `GNU GRUB 2.14：i386 Linux loader 的 grub_cmd_initrd() <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_
* `GNU GRUB 2.14：通用 initrd component、newc 和复制实现 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/linux.c>`_
* `GNU GRUB 2.14：Linux loader 常量与 boot parameter 结构 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/linux.h>`_
* `Linux 6.12.95：Linux/x86 Boot Protocol <https://github.com/gregkh/linux/blob/v6.12.95/Documentation/arch/x86/boot.rst>`_
* `Linux 6.12.95：setup header 中的 initrd_addr_max 与 init_size <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/boot/header.S>`_
