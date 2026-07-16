第三十二章：GRUB怎样选址并装入固定initramfs？
===============================================

第031章返回菜单脚本执行器时，fixed bzImage的protected payload已经位于relocator current
chunk，未来target记为 ``K``；header给出的初始化空间为 ``I``，GRUB保存：

::

   prot_mode_target = K
   prot_init_space  = PAGE_ALIGN(I)
   ramdisk_image    = 0
   ramdisk_size     = 0
   grub_loader_loaded = 1

CPU0上的BSP仍运行GNU GRUB 2.14，32位flat protected mode、paging off、A20 on、IF=0、DF=0。
同一entry scope继续执行最后一条配置：

.. code-block:: cfg

   initrd /boot/initramfs.img

本章追踪 ``grub_cmd_initrd`` 从检查Linux loader状态、打开原始initramfs、计算地址上下界到
更新 ``linux_params`` 的全过程，停在entry sourcecode成功结束、``grub_menu_execute_entry``
即将检查loader并隐式执行 ``boot`` 的位置。

本章继续保留artifact量
----------------------

initramfs不是Linux源码树直接生成的固定常量。本书只约定磁盘中的
``/boot/initramfs.img`` 与当前7.2-rc1场景匹配；其具体内容、压缩格式、inode、extent和长度来自
实际磁盘artifact。

后文记：

::

   N = /boot/initramfs.img的真实字节数，N > 0
   A = ALIGN_UP(N, 4096)
   L = K + PAGE_ALIGN(I)
   R = initrd_mem_target

``N`` 是Linux应读取的内容长度，``A`` 是relocator保留的地址跨度，``L`` 是initramfs target
允许的最低起点。三者不能混为一个数。

initrd命令不重新装入linux.mod
----------------------------

第030章的 ``GRUB_MOD_INIT(linux)`` 已同时注册真正的 ``linux`` 和 ``initrd`` command。
因此脚本执行器直接调用：

.. code-block:: c

   grub_cmd_initrd(cmd, 1, argv);

``argv[0]`` 为 ``/boot/initramfs.img``。函数先要求 ``argc != 0``，再检查module-local：

.. code-block:: c

   if (!loaded)
       error("you need to load the kernel first");

第031章已经在成功的 ``grub_loader_set`` 后写入 ``loaded=1``，所以当前通过。这一检查不只
表达脚本语法顺序：没有先装kernel，就没有 ``K``、``I`` 和可追加chunk的relocator，initrd地址
下界无法成立。

component数组先取得所有file所有权
--------------------------------

``grub_initrd_init`` 按argc分配component数组，初始化累计size，然后处理唯一参数。当前字符串
没有 ``newc:`` 前缀，所以直接打开：

.. code-block:: c

   grub_file_open(
       "/boot/initramfs.img",
       GRUB_FILE_TYPE_LINUX_INITRD |
       GRUB_FILE_TYPE_NO_DECOMPRESS);

没有显式device的路径仍由 ``root=hd0,msdos1`` 解析，经固定ext4、biosdisk和SeaBIOS AHCI磁盘
取得文件。

``NO_DECOMPRESS`` 约束的是GRUB file filter：即使文件字节本身采用gzip、xz、zstd或其他Linux
支持的封装，GRUB也不在这里把它展开。它稍后交给kernel的是磁盘上的原始字节流。

通用helper支持多个component和 ``newc:目标名:源文件`` 语法；那条路径会创建目录、cpio newc
header及 ``TRAILER!!!``。当前只有一个普通file，因此：

::

   nfiles           = 1
   newc_name        = NULL
   synthesized cpio = none
   initrd_ctx.size  = N

本章不能把helper的通用能力写成当前实际发生的cpio重打包。

真实长度与页对齐占用分开
------------------------

file打开后：

.. code-block:: c

   size = grub_get_initrd_size(&initrd_ctx);
   aligned_size = ALIGN_UP(size, 4096);

所以：

::

   size         = N
   aligned_size = A

``A - N`` 个尾部字节只属于地址占用，不属于initramfs内容。固定单component路径没有在读取完成
后显式清零这段页尾；但Linux收到的 ``ramdisk_size=N`` 会阻止它把尾部当作有效字节。正文既不能
把 ``ramdisk_size`` 写成 ``A``，也不能声称padding一定为0。

地址上界先读kernel header
------------------------

固定Linux 7.2-rc1源码在setup header无条件写入：

::

   initrd_addr_max = 0x7fffffff

protocol高于2.03，所以GRUB先取这个值，再用自身的i386 loader上界截断：

::

   GRUB_LINUX_INITRD_MAX_ADDRESS = 0x37ffffff

结果先变为 ``0x37ffffff``。这不是本机RAM末端，也不是initramfs起点；它只是当前loader愿意
考虑的最高地址边界。

第031章没有解析到 ``mem=``，``linux_mem_size=0``，所以command-line memory limit不再压低
它。随后固定实现无条件保留历史64 KiB兼容余量：

.. code-block:: c

   addr_max -= 0x10000;

当前得到：

::

   M = 0x37feffff

这一步来自GRUB对旧Linux 2.2/2.3 range-check问题的兼容，不表示7.2-rc1自身只能使用这个上界。

地址下界来自完整初始化窗口
--------------------------

GRUB计算：

.. code-block:: c

   addr_min = prot_mode_target + prot_init_space;

代入上一章符号：

::

   addr_min = L = K + PAGE_ALIGN(I)

这里避开的不是仅有 ``P`` 字节的compressed file输入，而是Linux header声明的完整初始化窗口。
compressed startup以后可能在该窗口内放置页表、搬移输入并展开输出；若initramfs只避开
``K + P``，它仍可能在kernel自解压时被覆盖。

理想高端起点怎样计算
--------------------

GRUB先确认 ``M >= A``，再算：

.. code-block:: c

   H = (M - A) & ~0xfff;

``H`` 是4 KiB向下对齐后的最高候选target起点。随后检查：

::

   H >= L

否则即使系统总RAM很大，也不能在kernel初始化窗口和当前loader上界之间放下这份连续initramfs，
函数会报 ``the initrd is too big``。

成功路径的可用target范围由此固定为：

::

   start >= L
   start <= H
   start is 4 KiB aligned
   allocation span = A
   start + A <= M

relocator偏好高地址但不承诺等于H
------------------------------

GRUB向第031章建立的同一个relocator追加chunk：

.. code-block:: c

   grub_relocator_alloc_chunk_align(
       relocator, &ch,
       L, H,
       A, 0x1000,
       GRUB_RELOCATOR_PREFERENCE_HIGH,
       1);

``PREFERENCE_HIGH`` 让搜索尽量靠近上界，但已有target冲突、GRUB current-memory可用性和memory
map都会影响返回结果，所以不能无条件写：

::

   R = H

可以确定的是：

::

   L <= R <= H
   R mod 4096 = 0
   [R, R + A)不与relocator中其他target chunk重叠

返回对象仍有两种地址身份：

::

   initrd_mem        = current address
   R                 = physical target

GRUB现在向 ``initrd_mem`` 写文件；最终trampoline才保证字节出现在 ``R``。

单一普通component按原字节复制
----------------------------

``grub_initrd_load`` 遍历一个component。因为没有前一个component、没有newc name，也没有需要插入
的对齐记录，核心动作就是：

.. code-block:: c

   grub_file_read(component.file, initrd_mem, N);

成功要求返回值严格等于 ``N``。GRUB不检查cpio member、``/init``、userspace程序或kernel module，
也不在此验证Linux以后能否解包；这些属于kernel取得控制权后的initramfs路径。

读取过程仍可能经ext4、BIOS INT 13h和AHCI发出多次I/O；实际命令数由artifact与cache决定。完成
边界只固定：

::

   [initrd_mem, initrd_mem + N) = 磁盘原始initramfs字节

参数字段只在复制成功后发布
--------------------------

全部 ``N`` 字节读入后，GRUB才写：

.. code-block:: c

   linux_params.hdr.ramdisk_image = R;
   linux_params.hdr.ramdisk_size  = N;
   linux_params.hdr.root_dev      = 0x0100;

所以parameter publication晚于file data completion。``ramdisk_image`` 是最终physical target，
不是GRUB当前指针 ``initrd_mem``；``ramdisk_size`` 是真实内容长度，不是页对齐跨度 ``A``。

``root_dev=0x0100`` 是固定GRUB实现保留的历史赋值。当前实际root选择仍由：

::

   root=/dev/sda1

以及initramfs早期userspace共同决定，不能把旧字段解释成GRUB已经挂载某个Linux根文件系统。

component与relocator的生命期在这里分开
-------------------------------------

成功和失败最终都经过：

.. code-block:: c

   grub_initrd_close(&initrd_ctx);

它关闭component file、释放可选newc name和component数组。因此本章结束时没有存活的initramfs
file、ext4 per-open data、device或disk object。

relocator chunk不属于 ``initrd_ctx``，不会随close释放。它继续由全局relocator持有，等待
``grub_linux_boot`` 的最终搬移。``linux.mod`` 的两份既有引用也没有因 ``initrd`` command
增加或减少。

失败出口同样不是chunk级事务
---------------------------

若参数缺失、kernel尚未loaded、file open失败、大小越界或chunk分配失败，helper会关闭已打开的
component。若错误发生在chunk已经追加之后的file读取阶段，公共 ``fail:`` 只关闭
``initrd_ctx``，没有从relocator单独删除刚追加的chunk；参数字段因为写入发生在成功读取之后，
仍保持先前值。

当前路径读取成功，所以不会进入该状态。但这再次说明：固定实现保证file/component引用回滚，
不保证每个后分配relocator对象都能按command单独回滚。

entry sourcecode在initrd返回后结束
---------------------------------

``grub_cmd_initrd`` 返回0，脚本中的block没有第三条命令：

.. code-block:: cfg

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

``grub_script_execute_new_scope`` 因而完成，控制流回到 ``grub_menu_execute_entry``。此时
``grub_errno=GRUB_ERR_NONE`` 且 ``grub_loader_is_loaded()`` 为真，但下一行隐式
``grub_command_execute("boot", 0, 0)`` 尚未执行。把本章停在这里，可以把“装入initramfs”和
“最终改造机器状态、交接Linux”分成两个自然源码边界。

本章结束状态
------------

* current executor：CPU0 BSP上的GNU GRUB 2.14 ``grub_menu_execute_entry``，entry脚本刚返回；
* CPU mode：32位flat protected mode，paging off，A20 on，IF=0、DF=0；
* kernel target：``K``；
* kernel init span：``PAGE_ALIGN(I)``；
* initramfs true size：``N``，来自磁盘artifact；
* initramfs allocation span：``A=ALIGN_UP(N,4096)``；
* effective upper boundary：``M=0x37feffff``；
* minimum initrd target：``L=K+PAGE_ALIGN(I)``；
* actual initrd target：``R``，满足 ``L <= R <= H`` 且4 KiB aligned；
* initramfs current bytes：已在 ``initrd_mem`` 完整读取；
* initramfs target bytes：尚待relocator最终搬移；
* initramfs file/components：已关闭并释放；disk cache可保留block；
* ``linux_params.hdr.ramdisk_image=R``；
* ``linux_params.hdr.ramdisk_size=N``；
* ``linux_params.hdr.root_dev=0x0100``；
* kernel command line：``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``；
* loader hook：``grub_linux_boot``，仍loaded；
* ``linux.mod`` 引用：未改变；
* entry sourcecode：成功结束；
* implicit ``boot``：尚未调用；
* Linux：尚未取得控制权。

关键边界
--------

#. ``NO_DECOMPRESS`` 让GRUB复制原始file bytes；当前没有newc合成或GRUB侧解压。
#. ``N`` 是内容长度，``A`` 是地址占用；页尾不属于Linux可见initramfs内容，也不保证为0。
#. 固定kernel header上界 ``0x7fffffff`` 先被GRUB截为 ``0x37ffffff``，再减64 KiB得到
   ``0x37feffff``。
#. initramfs下界避开的是 ``PAGE_ALIGN(init_size)``，不是只避开compressed payload长度。
#. high preference不等于target必为最高候选；``R`` 必须保留为实际allocator结果。
#. ``ramdisk_image`` 使用physical target ``R``，``ramdisk_size`` 使用true size ``N``。
#. component close不释放relocator chunk；两者是不同所有权。
#. 读取失败后的component回滚完整，但已追加的chunk没有在这个command出口单独撤销。
#. initrd成功返回仍不会直接启动Linux；隐式boot只在整个entry sourcecode结束后发生。

下一入口
--------

下一章从 ``grub_menu_execute_entry`` 的loader检查开始：

::

   if (grub_errno == GRUB_ERR_NONE && grub_loader_is_loaded())
       grub_command_execute("boot", 0, 0);

随后将进入：

::

   grub_cmd_boot
   → grub_loader_boot
   → grub_machine_fini(flags=0)
   → grub_simple_boot_hook
   → grub_linux_boot

``grub_linux_boot`` 才会选择最终低端 ``boot_params`` 地址、写command-line physical pointer和
E820、准备32位handoff state，并让relocator完成所有chunk搬移。

资料
----

* `GRUB固定提交：i386 grub_cmd_initrd与initrd地址规则 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_；
* `GRUB固定提交：通用initrd component、newc与load/close生命期 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/linux.c>`_；
* `GRUB固定提交：initrd上界和Linux参数结构 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/linux.h>`_；
* `GRUB固定提交：relocator aligned chunk分配 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/relocator.c>`_；
* `GRUB固定提交：entry结束后的隐式boot <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/menu.c>`_；
* `Linux 7.2-rc1固定提交：setup header中的initrd_addr_max与init_size <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/header.S>`_；
* `Linux 7.2-rc1固定提交：initrd地址与Linux/x86 Boot Protocol <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_。
