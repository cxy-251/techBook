第三十三章：GRUB 怎样准备 boot_params 并把控制权交给 Linux？
=========================================================

上一章结束时，菜单项花括号内的两条命令都已成功返回：

.. code-block:: cfg

   linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
   initrd /boot/initramfs-6.12.95.img

内存里已经有 Linux protected-mode payload、initramfs、命令行模板和一份尚未放到最终低端位置的 ``linux_params``。``grub.cfg`` 没有显式写 ``boot``，但 ``grub_menu_execute_entry()`` 会在脚本结束后检查 loader 状态：

.. code-block:: c

   if (grub_errno == GRUB_ERR_NONE && grub_loader_is_loaded())
       grub_command_execute("boot", 0, 0);

这一章追踪这次隐式调用，直到 GRUB 不再返回，CPU 的 ``EIP`` 指向 Linux 6.12.95 compressed image 的 ``startup_32``。

``boot`` 命令本身很薄
--------------------

``boot`` 命令的实现只有一层转发：

.. code-block:: c

   grub_cmd_boot()
   {
       return grub_loader_boot();
   }

真正关键的是上一章之前由：

.. code-block:: c

   grub_loader_set(grub_linux_boot, grub_linux_unload, 0);

登记的 loader hook。

``grub_loader_set()`` 没有立刻运行 Linux。它把函数指针保存到全局 loader 状态，并把 ``grub_loader_loaded`` 设为 1。现在 ``grub_loader_boot()`` 才真正调用这个函数。

GRUB 先结束自己的机器环境
------------------------

``grub_loader_boot()`` 首先执行：

.. code-block:: c

   grub_machine_fini(grub_loader_flags);

当前 ``linux`` loader 注册时传入的 flags 是 0，不包含 ``GRUB_LOADER_FLAG_NORETURN``。因此 i386-pc 的 ``grub_machine_fini()`` 不关闭整个 GRUB console，只执行：

.. code-block:: c

   grub_stop_floppy();

这解释了 ``grub_loader_set(..., 0)`` 旁边的注释：GRUB 故意不在这里调用 ``grub_console_fini()``，因为 Linux loader 自己还要读取当前 video/console 状态并写入 ``boot_params``。

随后 GRUB 按优先级执行所有 preboot hooks。它们允许终端、网络或平台模块在最终交接前收尾。当前固定简单磁盘启动路径的主线继续落到保存的 loader hook：

::

   grub_simple_boot_hook()
   → grub_linux_boot()

从这一刻开始，如果成功，控制流不会再回到菜单。

Linux 32 位协议要求 bootloader 做什么
------------------------------------

当前使用的是 GRUB i386-pc 的现代 ``linux`` 命令，不是 ``linux16``。因此它采用 Linux/x86 的 **32-bit Boot Protocol**，跳过内核的 16 位 ``arch/x86/boot`` setup 执行路径，直接进入压缩内核的 32 位入口。

协议要求交接时：

* CPU 已处于 32 位保护模式；
* paging 关闭；
* 中断关闭；
* ``CS = __BOOT_CS = 0x10``；
* ``DS = ES = SS = __BOOT_DS = 0x18``；
* 两个段描述符都是 base 0、limit 4 GiB 的 flat segment；
* ``ESI`` 指向 ``struct boot_params``；
* ``EBP``、``EDI``、``EBX`` 为 0；
* ``EIP`` 指向 loaded kernel 的 32 位入口。

前几章已经看到 GRUB 自己运行在保护模式中，但“GRUB 当前能运行”不等于“寄存器和 GDT 已符合 Linux 协议”。最终 relocator 会重新建立一套明确满足协议的交接状态。

为什么此时才生成最终 boot_params
--------------------------------

``grub_cmd_linux()`` 阶段建立的是 GRUB 内部全局变量 ``linux_params``。当时它还不能完成所有字段：

* video mode 可能在执行 ``boot`` 前发生变化；
* initramfs 当时尚未装入；
* bootloader 最终占用和 relocator chunk 已经改变 GRUB 内存图；
* ``boot_params`` 自身的最终物理地址尚未选定；
* 命令行的最终物理指针依赖这个低端地址。

所以 ``grub_linux_boot()`` 在最后时刻重新完成交接数据，而不是直接把先前的 C 全局结构地址交给 Linux。

video 状态写进 ``screen_info``
-------------------------------

``grub_linux_boot()`` 首先处理 ``gfxpayload``。固定配置没有设置图形 payload，PC BIOS 路径默认尝试 text mode。

随后 ``grub_linux_setup_video()`` 查询当前 video driver、framebuffer、分辨率、颜色掩码和 EDID。若没有可传递的 framebuffer 信息，PC BIOS 路径回退为：

::

   orig_video_isVGA = text
   orig_video_mode  = 0x03

并从活动的 ``vga_text`` 或 ``console`` terminal 读取光标位置、列数和行数。若没有找到合适 terminal，则使用传统默认值：

::

   80 columns
   25 lines

这些字段不是为了让 GRUB 继续显示菜单，而是让 Linux 在自己的 console 与 framebuffer 驱动完全建立之前，知道 bootloader 留下的显示环境。

低端区域不仅放一个“zero page”
----------------------------

32-bit Boot Protocol 把 ``struct boot_params`` 传统地称为 **zero page**。名称容易让人误以为只需要 4096 字节。GRUB 实际为一个组合区域计算大小：

::

   boot_params
   + 扩展的 E820 缓冲余量
   + 页对齐间隔
   + kernel command line

``find_mmap_size()`` 先统计当前 GRUB memory map 的 entry 数量，再按每个 ``grub_boot_e820_entry`` 的大小计算空间，并额外增加一页安全余量。

接着：

.. code-block:: c

   cl_offset = ALIGN_UP(mmap_size + sizeof(linux_params), 4096);
   real_size = ALIGN_UP(cl_offset + maximal_cmdline_size, 4096);

``cl_offset`` 是命令行相对于低端区域起点的偏移。

如果这个偏移小于 setup header 表示的 setup 区长度，GRUB 还会把它提高到 setup 区末端之后。即使当前直接走 32 位入口，它仍避免让命令行覆盖传统 setup 数据范围。

为什么最终参数必须放在 0x10000 到 0x90000
-----------------------------------------

``grub_linux_boot_mmap_find()`` 只接受 ``GRUB_MEMORY_AVAILABLE``，并把搜索范围裁剪到：

::

   0x10000 <= region < 0x90000

低于 ``0x10000`` 的区域包含 IVT、BDA、GRUB/BIOS 低端用途以及历史保留区，不适合作为 Linux 参数区。

``0x90000`` 以上接近传统 EBDA、视频窗口和 BIOS 保留空间。第三十二章已经讲过，低端内存顶端并不一定完整属于 bootloader。

对一段足够大的可用区域，GRUB 从该区域末端向下计算：

.. code-block:: c

   real_mode_target = region_end - real_size;

因此参数区尽量靠近所选低端可用区域的高端，从而少占用更低地址。

虽然函数和变量仍使用 ``real_mode`` 名称，这条路径并不会跳进 Linux 16 位 setup。名称来自这片传统低端内存区域的历史用途；当前真正入口仍是 32 位 ``code32_start``。

relocator 为低端参数区保留最终物理地址
-------------------------------------

找到 ``real_mode_target`` 后，GRUB 继续在同一个 relocator 中申请固定地址 chunk：

.. code-block:: c

   grub_relocator_alloc_chunk_addr(
       relocator,
       &ch,
       real_mode_target,
       real_size);

得到：

::

   real_mode_mem     = GRUB 当前写入用地址
   real_mode_target  = Linux 最终看到的物理地址

然后：

.. code-block:: c

   ctx.params = real_mode_mem;
   *ctx.params = linux_params;

这一步把先前准备的 ``linux_params`` 模板复制进最终参数 chunk。第三十二章写入的 ``ramdisk_image`` 与 ``ramdisk_size`` 也随之复制。

命令行指针此时才固定
--------------------

GRUB 设置：

.. code-block:: c

   ctx.params->hdr.cmd_line_ptr = real_mode_target + cl_offset;

再把：

::

   BOOT_IMAGE=/boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0

复制到 ``real_mode_mem + cl_offset``。

注意 ``cmd_line_ptr`` 保存的是 **最终物理地址**，不是 GRUB 当前的 C 指针。Linux 接管后不会知道 ``real_mode_mem`` 这个临时映射概念，它只会按照物理地址读取参数。

E820 在交接前重新生成
--------------------

SeaBIOS 最早建立过 E820；GRUB 初始化堆时读取过 E820；现在 GRUB 又遍历自己的 memory map，并写入：

::

   ctx.params->e820_table[]
   ctx.params->e820_entries

这不是无意义的第三次复制。GRUB 运行期间已经为内核 payload、initramfs、低端参数区和其他对象保留物理区域。bootloader 必须向 Linux 提供交接时的最终视图，避免 Linux 把这些仍然有用的区域当作普通空闲 RAM 覆盖。

相邻且类型相同的区间会由 ``grub_e820_add_region()`` 合并，减少 zero page 中有限 E820 entry 数量的消耗。

PC BIOS 路径不会执行 EFI 分支
----------------------------

``grub_linux_boot()`` 同时服务 PC BIOS、EFI 和其他 x86 平台，因此源码中还有 EFI memory map、ExitBootServices 和 64 位 EFI 直接入口分支。

当前固定目标是：

::

   GNU GRUB 2.14 i386-pc

所以这些 EFI 分支不会执行。最终采用源码末尾的 32 位状态：

.. code-block:: c

   state.ebp = 0;
   state.edi = 0;
   state.ebx = 0;
   state.esi = ctx.real_mode_target;
   state.esp = ctx.real_mode_target;
   state.eip = ctx.params->hdr.code32_start;

``ESI`` 是协议规定的 boot_params 指针。

``ESP`` 也暂时设成参数区起点。Linux ``startup_32`` 很快会计算并切换到自己的 boot stack，所以这里不是 Linux 长期使用的栈。

``code32_start`` 已经随实际装载地址修正
--------------------------------------

第三十一章中，GRUB 根据实际 ``prot_mode_target`` 修改：

::

   linux_params.hdr.code32_start

固定 ``bzImage`` 原始 header 默认值是 ``0x100000``。若 relocatable kernel 最终仍按 preferred address 装到 ``0x100000``，该字段保持这一值；若因内存冲突按允许的 alignment 改放到其他地址，GRUB 会把 ``code32_start`` 修正为对应的实际入口。

因此此处不能在通用叙述中把跳转目标无条件写死为 ``0x100000``。可以确定的是：

::

   EIP = 实际装载后的 code32_start

在当前无冲突的标准布局下，它通常就是 ``0x00100000``。

relocator 为什么必须最后执行
----------------------------

GRUB 先前拿到的每个 chunk 都区分：

* current address：GRUB 当前复制和修改数据的位置；
* target address：交接后数据必须出现的物理位置。

多个 target 区域之间可能存在覆盖依赖。如果直接逐个 ``memcpy``，先搬动一个 chunk 可能覆盖另一个 chunk 尚未搬走的源数据。

``grub_relocator_prepare_relocs()`` 为所有 chunk 计算安全搬运序列并生成一小段 relocation trampoline。之后 ``grub_relocator32_boot()``：

#. 在 ``0x1000`` 到 ``0x9a000`` 间为 32 位 trampoline 找低地址；
#. 把目标寄存器值写进 trampoline 模板；
#. 准备所有 chunk 的最终搬运步骤；
#. 执行 ``cli``；
#. 跳入 relocation trampoline。

从这一步开始，普通 GRUB C 环境不再可用。

trampoline 重建 Linux 要求的 CPU 状态
-------------------------------------

``relocator32.S`` 装入一张很小的 GDT：

::

   selector 0x10：32 位 code，base 0，4 GiB，execute/read
   selector 0x18：32 位 data，base 0，4 GiB，read/write

然后把：

::

   DS = ES = FS = GS = SS = 0x18

并确保：

* paging 关闭；
* PAE 关闭；
* direction flag 清除；
* 中断已经由外层 ``cli`` 关闭。

它恢复 GRUB 为 Linux 准备的 ``ESP``、``EBP``、``ESI``、``EDI``、``EBX`` 等寄存器，最后使用 far jump：

::

   CS:EIP = 0x10:code32_start

far jump 同时重新装入 ``CS`` descriptor cache，保证执行环境确实使用 Linux 协议要求的 code segment。

执行者第一次变成 Linux
----------------------

far jump 完成后，当前指令不再属于 GRUB。CPU 开始执行 Linux 6.12.95 ``arch/x86/boot/compressed/head_64.S`` 中的：

::

   startup_32

交接寄存器中的关键值是：

::

   EIP = code32_start
   ESI = boot_params 物理地址
   EBP = 0
   EDI = 0
   EBX = 0
   CS  = 0x10
   DS  = ES = SS = 0x18

此时：

* CPU 仍是 32 位保护模式；
* paging 关闭；
* long mode 尚未开启；
* compressed payload 尚未解压；
* initramfs 只是一段由 ``boot_params`` 指向的高地址字节；
* Linux 尚未建立自己的完整页表、IDT、内存管理器或调度器。

“进入 Linux”不等于“Linux 内核已经初始化”。它只表示第一条 Linux 自己的 compressed startup 指令已经取得控制权。

当前机器状态
------------

* 当前执行者：Linux 6.12.95 compressed ``startup_32``；
* 当前主流程 CPU：BSP；
* CPU 模式：32 位保护模式；
* paging：关闭；
* PAE：关闭；
* interrupts：关闭；
* direction flag：清除；
* ``CS``：``0x10`` flat code segment；
* ``DS``、``ES``、``SS``：``0x18`` flat data segment；
* ``ESI``：最终低端 ``struct boot_params`` 物理地址；
* ``boot_params``：包含 setup header、video 信息、命令行指针、E820、initramfs 地址和大小；
* protected payload：位于 ``code32_start`` 对应的目标区域；
* initramfs：位于高地址 relocator target；
* GRUB：已完成最后一次跳转，不再是执行者；
* Linux payload：尚未解压；
* long mode：尚未开启。

下一段从 Linux ``startup_32`` 第一条指令开始，追踪它怎样保存 boot_params 指针、计算自己的实际装载基址、建立 boot stack、验证 CPU、建立最初的 4 级页表并进入 64 位模式。

资料
----

* `GNU GRUB 2.14：boot 命令、loader hook 与 preboot 流程 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/commands/boot.c>`_
* `GNU GRUB 2.14：grub_linux_boot() 的 boot_params、命令行、E820 与寄存器设置 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_
* `GNU GRUB 2.14：i386-pc grub_machine_fini() <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c>`_
* `GNU GRUB 2.14：32 位 relocator C 入口 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/i386/relocator.c>`_
* `GNU GRUB 2.14：32 位 relocator trampoline 与 GDT <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/i386/relocator32.S>`_
* `Linux 6.12.95：Linux/x86 32-bit Boot Protocol <https://github.com/gregkh/linux/blob/v6.12.95/Documentation/arch/x86/boot.rst>`_
* `Linux 6.12.95：compressed startup_32 入口 <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/boot/compressed/head_64.S>`_
