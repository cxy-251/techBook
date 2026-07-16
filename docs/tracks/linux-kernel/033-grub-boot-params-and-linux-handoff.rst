第三十三章：GRUB怎样完成boot_params并跳入Linux startup_32？
===========================================================

第032章结束在菜单项sourcecode成功返回之后。CPU0上的BSP仍由GNU GRUB 2.14执行，32位flat
protected mode、paging off、A20 on、IF=0、DF=0。内存中已经有三个尚未最终交接的核心对象：

::

   protected payload chunk
     target = K
     initialized span = header.init_size I

   initramfs chunk
     target = R
     true size = N

   module-global linux_params + linux_cmdline
     ramdisk_image = R
     ramdisk_size  = N
     code32_start  = K

``grub_errno=GRUB_ERR_NONE``，``grub_loader_is_loaded()`` 为真。当前精确入口是
``grub_menu_execute_entry`` 的隐式boot：

.. code-block:: c

   grub_command_execute("boot", 0, 0);

本章沿loader core、i386 Linux boot hook和relocator32 trampoline连续执行，直到far jump令
``EIP=K``、``ESI`` 指向最终低端 ``boot_params``，Linux 7.2-rc1 compressed
``startup_32`` 即将执行第一条指令。

boot command在dependency closure中已经可用
------------------------------------------

``linux.mod`` 引用loader core、memory-map和relocator导出符号；固定GRUB的module dependency
解析已经在第030章装入并初始化相应的 ``boot``、``mmap`` 和 ``relocator`` dependency。
其中 ``GRUB_MOD_INIT(boot)`` 注册真实 ``boot`` command。因此这里不再打开
``boot.mod``，command直接进入：

.. code-block:: c

   grub_cmd_boot()
   → grub_loader_boot()

``grub_cmd_boot`` 本身只转发；真正的状态来自第031章发布的：

::

   boot wrapper   = grub_simple_boot_hook
   unload wrapper = grub_simple_unload_hook
   simple boot    = grub_linux_boot
   simple unload  = grub_linux_unload
   loader flags   = 0

machine_fini为什么没有先关console
--------------------------------

``grub_loader_boot`` 首先执行：

.. code-block:: c

   grub_machine_fini(grub_loader_flags);

i386-pc实现只有：

.. code-block:: c

   if (flags & GRUB_LOADER_FLAG_NORETURN)
       grub_console_fini();
   grub_stop_floppy();

当前flags为0，所以不会调用 ``grub_console_fini``，但仍调用 ``grub_stop_floppy``。是否有正在
转动的floppy由运行时设备状态决定；控制流上的stop调用确定发生。

保留console是Linux loader的实际需要：``grub_linux_boot`` 随后还会查询video driver、terminal
坐标和text/framebuffer状态，填入 ``screen_info``。因此“最终boot不返回”和loader flag中的
``NORETURN`` 不是同一个判断；固定实现刻意用flags 0避免过早拆console。

当前preboot链为什么为空
-----------------------

loader core接着按priority从head到tail运行注册过的preboot hooks。GRUB源码中USB host、native
AHCI、network、at_keyboard、drivemap/sendkey和PC mmap overlay都可能注册这种hook，但当前
simple-install路径只实际使用BIOS console、biosdisk、MSDOS、ext4、normal和Linux loader：

* 没有装入或启用GRUB native AHCI、USB、network或at_keyboard设备；
* 没有执行 ``drivemap`` 或 ``sendkey``；
* 虽已因dependency装入 ``mmap.mod``，却没有执行 ``badram``、``cutmem`` 或其他
  ``grub_mmap_register`` overlay路径；仅加载module不会注册PC memory preboot hook。

所以本场景 ``preboots_head=NULL``，循环执行0个callback。若以后镜像约定加入这些模块或命令，
这项结论必须重新核定，不能沿用。

随后：

::

   grub_simple_boot_hook(&simple_loader_hooks)
   → grub_linux_boot()

从这里到成功handoff没有正常返回。

Linux 32位协议绕过16位setup
--------------------------

当前GRUB target是 ``i386-pc``，使用现代 ``linux`` command的Linux/x86 32-bit Boot Protocol。
它不会跳到bzImage的boot sector或 ``arch/x86/boot`` 16位setup入口，而是直接把CPU整理为：

* 32位protected mode；
* paging disabled；
* flat ``__BOOT_CS=0x10`` 与 ``__BOOT_DS=0x18``；
* interrupt disabled；
* ``ESI`` 指向 ``struct boot_params``；
* ``EBP``、``EDI``、``EBX`` 为0；
* entry为loaded protected payload的32位起点。

``grub_linux_boot`` 先准备最后的参数数据，relocator trampoline再建立这些CPU条件。

video信息必须在低端参数分配前完成
--------------------------------

当前配置没有设置 ``gfxpayload``。PC BIOS分支因此尝试默认 ``text`` mode，再调用
``grub_linux_setup_video(&linux_params)`` 取得当前video信息并结束对应video mode接口。

若没有可传递的framebuffer信息，固定PC分支回退：

::

   orig_video_isVGA = GRUB_VIDEO_LINUX_TYPE_TEXT
   orig_video_mode  = 0x03

随后遍历active output terminal；若找到 ``vga_text`` 或 ``console``，就读取其光标、列数和
行数。只有没有匹配terminal时才回退80x25。当前书稿不制造实际光标位置，也不把fallback值写成
必然的terminal查询结果。

video mode设置失败会打印错误、清除 ``grub_errno`` 并继续blind boot；本章成功路径不要求存在
framebuffer。此阶段仍在GRUB C环境中，console还可用。

低端参数区的大小怎样形成
------------------------

``find_mmap_size`` 先遍历一次GRUB memory map统计entry数 ``E``，计算：

::

   mmap_size = PAGE_ALIGN(E * sizeof(grub_boot_e820_entry) + 4096)

每个entry为20字节，额外一页用于应对稍后分配造成的entry增长。接着：

.. code-block:: c

   cl_offset = ALIGN_UP(mmap_size + sizeof(linux_params), 4096);

   if (cl_offset < (linux_params.hdr.setup_sects << 9))
       cl_offset = ALIGN_UP(linux_params.hdr.setup_sects << 9, 4096);

   real_size = ALIGN_UP(cl_offset + maximal_cmdline_size, 4096);

第031章已经证明 ``maximal_cmdline_size=2048``。用符号记：

::

   C = cl_offset
   Q = real_size

于是最终低端chunk同时容纳：

* ``struct linux_kernel_params`` 与E820 table；
* 为memory-map entry增长预留的空间；
* 到 ``C`` 的页对齐间隔；
* 2048字节command-line buffer。

“zero page”是协议历史名称，不表示GRUB这里只申请一页。

目标只在0x10000到0x90000之间寻找
--------------------------------

非EFI路径调用 ``grub_mmap_iterate(grub_linux_boot_mmap_find)``。callback只接受
``GRUB_MEMORY_AVAILABLE``，并把每段裁到：

::

   [0x10000, 0x90000)

低于64 KiB的IVT/BDA/BIOS区域不参与；0x90000以上的EBDA与传统高端低内存区域也不参与。对于
迭代中第一段足以容纳 ``Q`` 的available区间，GRUB选择：

::

   Z = clipped_region_end - Q

``Z`` 是最终 ``boot_params`` 区的physical target。本书没有固定SeaBIOS报告的低端available
region末端与GRUB当时的runtime布局，所以不把 ``Z`` 写成某个传统地址。

同一个relocator取得第三个data chunk
-----------------------------------

PC BIOS的 ``efi_mmap_size=0``。GRUB在已有protected/initramfs relocator中追加固定target：

.. code-block:: c

   grub_relocator_alloc_chunk_addr(relocator, &ch, Z, Q);

得到：

::

   real_mode_mem    = current address
   real_mode_target = Z

变量名保留“real mode”历史称呼，但当前控制流不会运行Linux 16位real-mode setup。GRUB在
``real_mode_mem`` 写入，最终relocator把该chunk放到 ``Z``。

模板复制后才发布physical command-line指针
-----------------------------------------

GRUB先执行：

.. code-block:: c

   ctx.params = real_mode_mem;
   *ctx.params = linux_params;

第031章复制并修改的setup header、第032章发布的 ``ramdisk_image=R`` 与
``ramdisk_size=N`` 因而进入最终参数chunk。然后：

.. code-block:: c

   ctx.params->hdr.cmd_line_ptr = Z + C;
   memcpy((char *)ctx.params + C, linux_cmdline, 2048);

Linux看到的是physical address ``Z+C``，不是GRUB current pointer。该位置的NUL-terminated
字符串为：

::

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

GRUB复制完整2048字节buffer；实际字符串后的zero bytes来自第031章的zero allocation。

E820不会因relocator chunk自动变成reserved
----------------------------------------

接着GRUB再次遍历自己的memory map，依次写入：

::

   ctx.params->e820_table[]
   ctx.params->e820_entries

``grub_e820_add_region`` 会把相邻且type相同的区间合并。这是SeaBIOS firmware map加
``grub_mmap`` overlays后的类型视图，不是GRUB heap allocator或relocator内部chunk表的转储。

当前场景没有调用 ``grub_mmap_register`` 添加overlay；``allocate_pages``、
``grub_relocator_alloc_chunk_align`` 和 ``grub_relocator_alloc_chunk_addr`` 也不因此自动注册
E820 reserved overlay。所以即使 ``K``、``R`` 或 ``Z`` 落在firmware RAM内，最终E820 entry
仍可把对应range报告为RAM。

这不是让Linux立刻覆盖自己。boot protocol另行传递：

* 当前执行地址/``code32_start=K`` 与 ``init_size=I``；
* ``ESI=Z`` 所指的参数区；
* ``cmd_line_ptr=Z+C``；
* ``ramdisk_image=R``、``ramdisk_size=N``。

Linux早期代码根据这些专用身份保护kernel、boot params、command line和initramfs。旧正文把
“relocator占用”直接等同于“E820 reserved”是不成立的，必须在此撤销。

PC BIOS路径跳过全部EFI分支
--------------------------

固定target是GNU GRUB 2.14 ``i386-pc``，不是i386-efi或x86_64-efi。因此：

* 不申请EFI memory-map尾区；
* 不调用 ``grub_efi_finish_boot_services``；
* 不填写EFI system-table/memory-map交接；
* 不进入64位EFI direct entry。

最后一定建立 ``struct grub_relocator32_state`` 并调用
``grub_relocator32_boot(relocator, state, 0)``。

GRUB只初始化协议要求的寄存器
----------------------------

固定源码明确赋值：

.. code-block:: c

   state.ebp = 0;
   state.edi = 0;
   state.ebx = 0;
   state.esi = Z;
   state.esp = Z;
   state.eip = ctx.params->hdr.code32_start;

第031章已由固定header原值证明 ``code32_start=K``，所以：

::

   EIP = K
   ESI = Z
   ESP = Z
   EBP = EDI = EBX = 0

``ESP=Z`` 只是GRUB提供的瞬时值。Linux ``startup_32`` 在第一次 ``call`` 前就把它改到
``boot_params.scratch+4``，不会把参数区起点当长期stack。

``struct grub_relocator32_state state`` 是未整体清零的automatic object，源码没有给
``eax``、``ecx``、``edx`` 赋值；32-bit Boot Protocol也不要求这些寄存器具有固定输入。
因此最终书稿必须把：

::

   EAX, ECX, EDX = unspecified

而不能声称它们为0或保留某个GRUB C调用值。

relocator先为自身寻找低端trampoline
---------------------------------

``grub_relocator32_boot`` 在：

::

   0x1000 .. 0x9a000

之间申请16-byte aligned的safe chunk，用于relocator32模板。它把state各字段写入模板的立即数
位置，再把模板复制到chunk current address。随后：

.. code-block:: c

   grub_relocator_prepare_relocs(
       relocator,
       trampoline_target,
       &relst,
       NULL);

prepare阶段为protected payload、initramfs、低端参数区和trampoline所有current/target关系生成
不会互相破坏的搬移序列。若source和target重叠，不能用书写顺序逐个普通 ``memcpy`` 代替。

``grub_relocator32_boot`` 最后执行：

.. code-block:: asm

   cli
   call/jump relst

从进入生成的relocation code开始，普通GRUB C stack和menu环境不再是可返回的成功路径。

trampoline怎样建立flat 32位交接状态
----------------------------------

``relocator32.S`` 先加载自身小GDT并far jump刷新 ``CS``。GDT定义：

::

   selector 0x10 = base 0, limit 4 GiB, 32-bit execute/read code
   selector 0x18 = base 0, limit 4 GiB, read/write data

然后：

::

   DS = ES = FS = GS = SS = 0x18

它显式清除 ``CR0.PG``，再清除 ``CR4.PAE``。当前GRUB build target是i386，模板不执行只为
``__x86_64__`` build准备的long-mode关闭分支；CPU本来就没有进入long mode。

所有data chunk完成搬移后，模板恢复：

::

   ESP = Z
   EBP = 0
   ESI = Z
   EDI = 0
   EBX = 0
   EAX/ECX/EDX = unspecified inputs from unassigned state fields

外层 ``cli`` 保证IF=0，``cld`` 保证DF=0。最后的far jump是：

::

   CS:EIP = 0x10:K

far jump既改变instruction pointer，也用flat code descriptor刷新 ``CS`` hidden state。此时
Linux/x86 32-bit Boot Protocol的必需寄存器、segments、paging和interrupt条件全部成立。

执行身份在K处变成Linux
----------------------

固定Linux ``arch/x86/boot/header.S`` 把protected 32-bit entry定义为payload offset 0；
``arch/x86/boot/compressed/head_64.S`` 在同一位置定义：

::

   startup_32:
       cld
       cli
       ...

所以 ``EIP=K`` 的第一条待执行指令属于Linux 7.2-rc1 compressed ``startup_32``。16位setup
没有运行，compressed payload尚未解压，long mode与paging尚未开启。

到这个边界，``K`` 处是relocator搬好的protected image，``R`` 处是原始initramfs字节，
``Z`` 处是最终boot parameters，``Z+C`` 是command line。GRUB成功路径不再返回
``grub_loader_boot``，也不会执行preboot restore、menu环境恢复或loader unload。

本章结束状态
------------

* current executor：Linux 7.2-rc1 compressed ``startup_32``，第一条指令尚未执行；
* current CPU：BSP / CPU0；
* CPU mode：32位protected mode；
* paging：off；``CR0.PG=0``；
* PAE：off；``CR4.PAE=0``；
* A20：on；
* interrupts：disabled，IF=0；
* direction flag：DF=0；
* GDT：relocator32 flat GDT active；
* ``CS=0x10``；
* ``DS=ES=FS=GS=SS=0x18``；
* ``EIP=K``，即protected payload/startup_32 target；
* ``ESI=Z``，指向最终 ``struct boot_params``；
* ``ESP=Z``；
* ``EBP=EDI=EBX=0``；
* ``EAX/ECX/EDX``：unspecified；
* boot params at ``Z``：含GRUB修改后的setup header、screen info、E820、command-line pointer和
  initramfs identity；
* command line at ``Z+C``：
  ``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``；
* protected payload at ``K``：已在target，尚未解压；
* initramfs at ``R``：``N`` 个原始有效字节已在target，尚未解析；
* 16-bit Linux setup：未执行；
* Linux paging/IDT/final GDT/scheduler：均未建立；
* GRUB file/device/fs/disk objects：none open；
* GRUB normal success path：不再取得控制权。

关键边界
--------

#. loader flags为0使PC ``grub_machine_fini`` 保留console，但仍执行 ``grub_stop_floppy``。
#. 当前module/command路径没有注册任何preboot hook；``mmap.mod`` 被加载不等于memory overlay
   hook已安装。
#. low chunk容纳参数、E820余量和command line；“zero page”不是本次allocation size。
#. ``cmd_line_ptr``、``ramdisk_image`` 和 ``ESI`` 都使用最终physical target，不使用GRUB
   current pointer。
#. relocator chunk不会自动成为 ``grub_mmap`` overlay；E820仍可把kernel/initrd/params所在range
   标为RAM。
#. PC BIOS路径不执行EFI boot services或64位direct entry。
#. GRUB只显式设置协议要求的 ``EBX/EBP/EDI/ESI`` 等字段；``EAX/ECX/EDX`` 没有保证。
#. relocator在搬完所有chunk并重建flat GDT、关闭paging/PAE、清IF/DF后才far jump。
#. fixed header令adjusted ``code32_start=K``；这证明入口等于实际target，不证明target必为1 MiB。
#. 成功far jump后GRUB不运行restore hook、menu cleanup或unload；执行者已经变成Linux。

下一入口
--------

第034章从固定Linux源码的第一条指令开始：

.. code-block:: asm

   startup_32:
       cld
       cli
       leal (BP_scratch+4)(%esi), %esp
       call 1f

Linux将先借用 ``boot_params.scratch`` 取得 ``startup_32`` 的实际运行基址，加载自己的GDT和
boot stack，验证CPU long-mode能力，再建立早期4 GiB identity map并进入compressed
``startup_64``。第034章仍是含旧版本标签的pending历史稿，留给下一批按fixed source整章审查。

资料
----

* `GRUB固定提交：entry结束后的implicit boot <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/menu.c>`_；
* `GRUB固定提交：loader set、machine fini、preboot与boot hook顺序 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/commands/boot.c>`_；
* `GRUB固定提交：i386-pc grub_machine_fini <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c>`_；
* `GRUB固定提交：grub_linux_boot的video、low chunk、E820与handoff state <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_；
* `GRUB固定提交：mmap overlay与PC preboot hook注册条件 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/mmap/i386/pc/mmap.c>`_；
* `GRUB固定提交：relocator chunk与搬移序列 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/relocator.c>`_；
* `GRUB固定提交：relocator32 state与trampoline <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/i386/relocator.c>`_；
* `GRUB固定提交：relocator32 flat GDT、paging/PAE与far jump <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/i386/relocator32.S>`_；
* `Linux 7.2-rc1固定提交：32-bit Boot Protocol交接条件 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_；
* `Linux 7.2-rc1固定提交：compressed startup_32 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S>`_。
