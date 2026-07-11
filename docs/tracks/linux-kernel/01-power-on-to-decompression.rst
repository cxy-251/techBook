设备上电后，x86-64 Linux 内核怎样被装入并完成解压？
========================================================

本文固定一条具体启动主线：

::

   x86-64 PC
   → SeaBIOS
   → GRUB
   → bzImage
   → Linux 6.12.95

终点是压缩启动桩完成内核解压，并跳入解压后正式内核的 ``startup_64``。此时
``start_kernel()`` 还没有执行。

源码基线
--------

* Linux release：``6.12.95``；
* 架构：``x86_64``；
* 内核映像：``arch/x86/boot/bzImage``；
* 启动协议：Linux/x86 Boot Protocol；
* 固件与引导方式：SeaBIOS 的 legacy BIOS 路径，随后由 GRUB 装入 Linux。

本篇涉及的核心源码文件：

::

   arch/x86/boot/header.S
   arch/x86/boot/main.c
   arch/x86/boot/pm.c
   arch/x86/boot/pmjump.S
   arch/x86/boot/compressed/head_64.S
   arch/x86/boot/compressed/misc.c
   arch/x86/kernel/head_64.S

上电：CPU 先执行固件
--------------------

电源稳定后，处理器从架构规定的复位入口取第一条指令。此时 Linux 不在执行，GRUB 也不在执行；
CPU 正在运行主板固件。

SeaBIOS 完成这条主线所需的最早工作：建立可以继续执行的处理器环境，初始化基础芯片组和内存，
枚举可启动设备，然后按照启动顺序选择一个设备。选中磁盘后，它把磁盘启动代码装入内存并把控制权
交出去。

从这一刻开始，固件不再决定 Linux 内核内部怎样启动。它只完成了第一棒：让机器具备读取启动介质的
能力，并找到下一段可执行代码。

GRUB 接管：找到并读取 bzImage
------------------------------

GRUB 接管后，能够读取文件系统，并根据配置找到内核映像、内核命令行和 initramfs。对于当前主线，
关键对象是 ``bzImage``。

``bzImage`` 不是单纯压缩后的 ``vmlinux``。它是一个带有启动协议头、实模式 setup 代码、压缩启动桩
和压缩内核负载的复合映像。GRUB 需要先读取映像中的 Linux boot protocol header，才能知道各部分的
尺寸、装载要求和入口信息。

协议头位于映像前部。几个关键字段包括：

``setup_sects``
   setup 区域占用多少个 512 字节扇区。

``header``
   偏移 ``0x202`` 处的 ``HdrS`` 标记，用来识别现代 Linux/x86 boot protocol。

``version``
   映像支持的启动协议版本。

``loadflags`` 与 ``xloadflags``
   描述映像装载与 64 位启动能力。

``code32_start``
   32 位保护模式入口地址。

``cmd_line_ptr``
   内核命令行的物理地址。

``ramdisk_image`` 与 ``ramdisk_size``
   initramfs 的装载地址和长度。

``kernel_alignment``、``pref_address`` 与 ``init_size``
   描述压缩内核的对齐、首选装载地址和早期运行所需空间。

GRUB 根据这些信息把 setup 区域放入低端内存，把受保护模式部分放到高端内存，并准备一块
``struct boot_params``。这块结构也常被称为 ``zero page``。内存布局、命令行地址、initramfs 地址、
固件信息和引导器信息都通过它传给 Linux。

Linux/x86 boot protocol 对现代 ``bzImage`` 的典型要求是：setup 代码位于低端内存，受保护模式内核
从 ``0x100000`` 或满足协议约束的更高地址开始装载。GRUB 完成装载后，把控制权交给 setup 入口。

header.S：Linux 自己的第一段启动代码
-----------------------------------

``arch/x86/boot/header.S`` 既定义映像前部的协议字段，也包含 setup 的汇编入口。

控制权进入 ``start_of_setup`` 时，CPU 仍处于 16 位实模式环境。这里不能假设已经拥有正常的内核栈、
分页、完整中断环境或 C 运行时。代码首先整理段寄存器和栈，使接下来的 setup C 代码能够可靠执行。

``start_of_setup`` 完成最小汇编准备后调用：

::

   arch/x86/boot/main.c:main()

这不是用户程序的 ``main``，也不是正式内核入口。它属于 ``arch/x86/boot`` 下的 setup 小程序，目标是
收集启动信息并把处理器从实模式送入保护模式。

main.c：补齐 boot_params
-----------------------

``main()`` 继续使用 BIOS 能力和 setup 自己的代码补充 ``boot_params``。这段过程包含几个关键动作：

#. 复制并整理 boot protocol header；
#. 建立 setup 阶段可用的堆；
#. 检查 CPU 是否满足当前内核要求；
#. 探测物理内存布局；
#. 收集视频模式、键盘、固件和平台相关信息；
#. 处理早期命令行参数；
#. 为进入保护模式准备 GDT、IDT 和入口参数。

这些信息不能等到正式内核运行后再补。实模式 BIOS 接口即将失效，而内核后续仍然需要知道固件提供的
内存地图、显示状态、initramfs 位置和命令行。因此 setup 阶段的主要产物不是某个设备已经完全驱动，
而是一份可供后续阶段继续使用的 ``boot_params``。

``main()`` 的最后阶段进入：

::

   arch/x86/boot/pm.c:go_to_protected_mode()

从实模式切到保护模式
--------------------

``go_to_protected_mode()`` 处理切换前最后一批架构状态：

* 确保 A20 地址线已经开启；
* 安装 setup 阶段使用的 GDT 和 IDT；
* 处理 PIC、NMI 等会干扰模式切换的旧式中断状态；
* 取得协议头中的 ``code32_start``；
* 调用 ``protected_mode_jump()``。

``arch/x86/boot/pmjump.S`` 中的 ``protected_mode_jump`` 设置 ``CR0.PE``，通过远跳转刷新代码段，
CPU 从 16 位实模式进入 32 位保护模式。跳转时，``ESI`` 携带 ``boot_params`` 的物理地址，下一阶段
因此可以继续访问前面收集的启动信息。

目标入口位于压缩启动桩：

::

   arch/x86/boot/compressed/head_64.S:startup_32

此时仍没有进入解压后的正式内核。CPU 只是进入了能够运行压缩启动桩的 32 位环境。

startup_32：为 64 位解压环境铺路
-------------------------------

``startup_32`` 首先处理自身位置。压缩启动桩可能被 bootloader 放在允许范围内的不同物理地址，代码
需要计算当前实际装载基址，并为可重定位内核选择安全区域。

接下来它完成进入 64 位模式所需的架构准备：

#. 检查处理器是否支持当前 64 位内核需要的能力；
#. 建立临时栈；
#. 建立早期页表；
#. 打开 ``CR4.PAE``；
#. 在 ``IA32_EFER`` 中设置 ``LME``；
#. 打开 ``CR0.PG``；
#. 通过远跳转进入 64 位代码段。

跳转目标仍在同一个压缩启动桩文件中：

::

   arch/x86/boot/compressed/head_64.S:startup_64

这个 ``startup_64`` 属于 ``arch/x86/boot/compressed``。它的任务是让解压程序运行起来，不能与
``arch/x86/kernel/head_64.S`` 中正式内核的同名入口混淆。

压缩启动桩的 startup_64
-----------------------

进入 64 位模式后，压缩启动桩重新设置段寄存器和栈，处理重定位需要的地址，清理自己的 BSS，并确定：

* 压缩输入位于哪里；
* 解压输出应该写到哪里；
* 输出区域是否会覆盖仍在执行的压缩启动桩；
* KASLR 是否需要改变最终物理装载位置；
* ``boot_params`` 和命令行怎样继续传递。

必要时，压缩启动桩先把自己移动到安全位置。完成这些准备后，它调用：

::

   arch/x86/boot/compressed/misc.c:extract_kernel()

extract_kernel：生成可执行的正式内核
----------------------------------

``extract_kernel()`` 接收 ``boot_params``、压缩输入范围、输出缓冲区和当前堆空间。它先检查输出地址、
内存范围和映像布局，然后调用当前内核配置选中的解压实现。

压缩算法可能是 gzip、bzip2、LZMA、XZ、LZO、LZ4 或 Zstandard；具体算法在构建 ``bzImage`` 时确定。
启动时不会自动尝试所有算法，而是链接进与当前映像格式对应的解压器。

解压得到的内容不是可以直接从文件偏移顺序执行的裸字节流。正式内核来自 ``vmlinux`` 的 ELF 布局。
压缩启动桩需要根据 ELF program header 把可装载段放到正确位置，并处理可重定位内核需要的重定位信息。
完成后，输出区域中已经形成可以接管处理器的解压后内核映像。

``extract_kernel()`` 返回正式内核入口地址。汇编代码恢复需要传递的参数，然后执行一次间接跳转。

解压结束：进入另一个 startup_64
--------------------------------

跳转目标是：

::

   arch/x86/kernel/head_64.S:startup_64

这一次的 ``startup_64`` 已经属于解压后的正式内核。

到这里，控制权经历了完整交接：

::

   CPU reset entry
   → SeaBIOS
   → GRUB
   → bzImage boot protocol
   → arch/x86/boot/header.S:start_of_setup
   → arch/x86/boot/main.c:main
   → go_to_protected_mode
   → compressed/head_64.S:startup_32
   → compressed/head_64.S:startup_64
   → extract_kernel
   → arch/x86/kernel/head_64.S:startup_64

固件已经退出，GRUB 已经退出，16 位 setup 已经退出，压缩启动桩也完成了使命。内存中现在存在解压后的
正式 Linux 内核，CPU 正在它的 64 位汇编入口执行。

本篇在这里结束。

资料
----

* `The Linux/x86 Boot Protocol <https://docs.kernel.org/arch/x86/boot.html>`_；
* `Linux Kernel Archives <https://www.kernel.org/>`_；
* `GNU GRUB Manual: linux <https://www.gnu.org/software/grub/manual/grub/html_node/linux.html>`_；
* Linux 6.12.95 源码中的 ``arch/x86/boot``、``arch/x86/boot/compressed`` 与
  ``arch/x86/kernel/head_64.S``。