第十七章：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？
====================================================================

上一章结束时，``platform_hardware_setup()`` 已经返回，控制流回到：

.. code-block:: c

   static void maininit(void)
   {
       interface_init();
       platform_hardware_setup();

       if (threads_during_optionroms())
           device_hardware_setup();

       vgarom_setup();
       sercon_setup();
       enable_vga_console();

       if (!threads_during_optionroms()) {
           device_hardware_setup();
           wait_threads();
       }
       ...
   }

这里第一次出现一个看似奇怪的顺序问题：USB、PS/2 和磁盘控制器可能还没有初始化，SeaBIOS 却先准备执行一段来自显卡的 16 位 Option ROM。

要理解这段控制流，需要先确定 ``threads_during_optionroms()`` 在当前固定环境中到底返回什么。

ThreadControl 决定设备探测是否与 Option ROM 并行
---------------------------------------------

第六章建立 SeaBIOS 内部协作式线程时，``thread_setup()`` 读取：

.. code-block:: c

   ThreadControl = romfile_loadint("etc/threads", 1);

``romfile_loadint()`` 的第二个参数是默认值，所以在没有 ``etc/threads`` 覆盖项时：

::

   ThreadControl = 1

``threads_during_optionroms()`` 的条件不是“线程功能已启用”这么简单：

.. code-block:: c

   return CONFIG_THREADS
       && CONFIG_RTC_TIMER
       && ThreadControl == 2
       && in_post();

四个条件分别表示：

``CONFIG_THREADS``
   构建时包含 SeaBIOS 协作式线程。

``CONFIG_RTC_TIMER``
   RTC periodic interrupt 可在 Option ROM 执行期间提供定期抢占检查。

``ThreadControl == 2``
   明确允许硬件初始化线程与 Option ROM 执行交错。

``in_post()``
   当前仍处于 POST 阶段。

当前固定 QEMU 提交中没有默认创建 ``etc/threads`` fw_cfg 文件，因此沿默认路径：

::

   ThreadControl = 1
   threads_during_optionroms() = false

于是本章的真实顺序是：

::

   platform_hardware_setup() 返回
   → 第一次 threads_during_optionroms() 为 false
   → 跳过提前 device_hardware_setup()
   → vgarom_setup()
   → sercon_setup()
   → enable_vga_console()
   → 第二次 threads_during_optionroms() 仍为 false
   → 下一章进入同步 device_hardware_setup()

这不是说 SeaBIOS 没有线程。``run_thread()`` 仍然可用于 USB 端口、AHCI 端口等并行探测；这里只是这些线程不会跨过 Option ROM 的 16 位执行阶段继续运行。

为什么 VGA 必须较早建立
---------------------

启动过程接下来可能需要显示：

* SeaBIOS 版本和机器 UUID；
* 设备探测信息；
* Option ROM 输出；
* 启动菜单；
* 启动失败提示；
* GRUB 自己的文字或图形界面。

SeaBIOS 本体提供 ``INT 10h`` 的占位入口，但它并不包含某一款显卡全部寄存器、模式设置和 VBE 实现。传统 BIOS 设计把这部分交给 VGA Option ROM。

因此 VGA ROM 的任务不是“显示一张开机图片”这么简单。它通常会：

* 初始化显示控制器；
* 建立文本模式；
* 设置 BDA 中的视频状态；
* 接管 IVT 中的 ``INT 10h``；
* 条件提供 VBE 服务；
* 让后续 BIOS、bootloader 和实模式程序拥有统一视频接口。

QEMU q35 默认创建哪一种显示设备
----------------------------

固定 QEMU ``pc_q35_machine_options()`` 设置：

.. code-block:: c

   m->default_display = "std";

``MachineState.enable_graphics`` 的通用默认值为true，所以没有 ``-nographic``、
``-vga none`` 或显式display device覆盖时，q35创建QEMU standard VGA。
``-display none`` 只可关闭display frontend，不必然移除guest所见的VGA device。
``default_display="std"`` 是默认选择，不是“无论命令行怎样都必有VGA”的保证。

这个事实与 SeaBIOS 的职责要分开：

* QEMU 创建并模拟 PCI VGA 设备及其寄存器、显存和 ROM 数据来源；
* SeaBIOS 枚举到 PCI display function，找到它的 x86 Option ROM；
* VGA ROM 自己执行初始化并安装 ``INT 10h`` 服务。

换成 ``virtio-vga``、``qxl``、``bochs-display`` 或无显示设备时，本章中寻找 ROM 的分支可能变化，但 SeaBIOS 的总体机制不变。

vgarom_setup 先读取四个策略开关
----------------------------

``vgarom_setup()`` 首先读取：

.. code-block:: c

   EnforceChecksum = romfile_loadint("etc/optionroms-checksum", 1);
   S3ResumeVga = romfile_loadint("etc/s3-resume-vga-init", CONFIG_QEMU);
   RunPCIroms = romfile_loadint("etc/pci-optionrom-exec", 2);
   ScreenAndDebug = romfile_loadint("etc/screen-and-debug", 1);

``EnforceChecksum``
   Option ROM checksum 错误时是否拒绝执行。默认值 1 表示严格检查。

``S3ResumeVga``
   S3 resume 时是否重新调用 VGA ROM。QEMU 构建默认允许。

``RunPCIroms``
   是否从 PCI ROM BAR 映射并执行 ROM。值 2 允许 VGA 和普通 PCI ROM。

``ScreenAndDebug``
   屏幕输出时是否同时复制到调试输出通道。

这些值可以由 fw_cfg 覆盖，因此同一份 SeaBIOS 二进制可以由虚拟机配置改变行为。

Option ROM 使用 0xc0000 开始的低端地址窗口
--------------------------------------

SeaBIOS 固定：

.. code-block:: c

   BUILD_ROM_START = 0x000c0000
   BUILD_BIOS_ADDR = 0x000f0000

VGA 与其他 Option ROM 被部署到传统的 ``0xc0000`` 起始区域，主 BIOS 自己位于 ``0xf0000`` 起始的 F-segment。

``vgarom_setup()`` 在扫描前清空当前可用 ROM 区：

.. code-block:: c

   memset((void*)BUILD_ROM_START,
          0,
          rom_get_max() - BUILD_ROM_START);

这里清理的是 SeaBIOS 管理的 Option ROM shadow 区，不是抹掉 PCI 设备内部永久 ROM。随后找到的 ROM 会被复制到这块低于 1 MiB、实模式代码容易访问的位置。

SeaBIOS 怎样确认一个 PCI function 是当前 VGA
-----------------------------------------

``is_pci_vga()`` 检查三层条件。

第一层，PCI class 必须是：

::

   PCI_CLASS_DISPLAY_VGA

第二层，PCI command register 必须已经打开：

::

   I/O Space Enable
   Memory Space Enable

第三层，如果设备位于 PCI bridge 后面，每一级 bridge 的 ``VGA Enable`` bit 都必须打开。

这三层共同保证：

* 它的身份是 VGA controller；
* 它的 I/O 和 MMIO decode 已开启；
* 传统 VGA I/O 与显存窗口能够穿过上游 bridge 到达它。

第九章选择默认 VGA 并配置 bridge VGA forwarding 的结果，正是在这里被消费。

ROM 数据可能来自 fw_cfg，也可能来自 PCI ROM BAR
--------------------------------------------

``init_pcirom()`` 先按设备 vendor/device ID 构造名字：

.. code-block:: c

   pciVVVV,DDDD.rom

如果 QEMU 通过 fw_cfg 提供同名 romfile，SeaBIOS 直接把它部署到低端 ROM 区。

没有同名 romfile 时，``RunPCIroms`` 允许的话，SeaBIOS 调用 ``map_pcirom()`` 访问设备的 PCI Expansion ROM BAR。

这两条路径的来源不同：

::

   fw_cfg romfile
      QEMU 直接把 ROM blob 作为固件文件交给 SeaBIOS

   PCI ROM BAR
      SeaBIOS 临时打开设备配置空间中的 Expansion ROM decode，
      从映射地址读取 ROM image

最终都会得到一份位于客户机物理内存中的 x86 Option ROM image。

PCI Expansion ROM BAR 为什么需要临时打开
------------------------------------

PCI ROM BAR 平时可以关闭，因为启动完成后多数设备不需要持续暴露 ROM 内容。

``map_pcirom()`` 的主要步骤是：

::

   保存原 PCI_ROM_ADDRESS
   → 写入 sizing mask
   → 读取 ROM BAR 能力与地址
   → 拒绝明显无效或危险地址
   → 设置 ROM Address Enable bit
   → 从该地址检查 ROM images
   → 复制匹配的 x86 image 到低端 ROM 区
   → 恢复原 PCI_ROM_ADDRESS

它不会把“ROM BAR 中第一个看起来像 ROM 的字节序列”直接执行。

一块 PCI ROM 里可能包含多个 image
-------------------------------

PCI Expansion ROM 可以串联多个 image，例如为不同 CPU 架构或不同执行环境准备代码。

SeaBIOS 从 ROM header 的 ``pcioffset`` 找到 ``PCIR`` data structure，然后检查：

* ``PCIR`` signature；
* vendor ID；
* device ID；
* code type；
* image length；
* last-image indicator。

当前主线只接受：

::

   vendor/device 与当前 PCI function 匹配
   code type = x86

如果当前 image 不匹配且 indicator 没有标记最后一项，SeaBIOS 按 ``ilen * 512`` 跳到下一个 image。

因此“显卡 ROM”不等于一个无结构的机器码 blob，它本身也是带 header、目录和多 image 链的固件容器。

0x55aa、长度字段与 checksum
------------------------

复制到低端内存后，``is_valid_rom()`` 检查：

.. code-block:: c

   rom->signature == 0xaa55
   rom->size != 0
   checksum(rom, rom->size * 512) == 0

内存中的前两个字节通常显示为：

::

   55 aa

因为 x86 是 little-endian，16 位读取值为 ``0xaa55``。

``rom->size`` 的单位是 512 字节。例如：

::

   size = 0x80
   actual length = 0x80 × 512 = 64 KiB

传统 Option ROM checksum 要求指定长度范围内所有字节按 8 位相加结果为零。默认 ``EnforceChecksum=1`` 时，校验失败的 ROM 不会进入执行路径。

SeaBIOS 为什么还要重新 reserve ROM 空间
-----------------------------------

``init_optionrom()`` 调用：

.. code-block:: c

   newrom = rom_reserve(rom->size * 512);

Option ROM 初始化代码有时会修改自己的 size 字段，或者声明初始化后只需要保留较小的 resident 部分。

SeaBIOS 的流程是：

::

   按初始长度预留空间
   → 必要时把 ROM 移到正式位置
   → 执行 ROM
   → 用执行后的 size 字段确认最终占用

这样后续 ROM 可以紧接着使用剩余低端空间，避免每个 ROM 永久占用其最大初始 image 长度。

VGA ROM 执行前会进入 TPM measured-boot 记录
--------------------------------------

``init_optionrom()`` 在执行前无条件调用：

.. code-block:: c

   tpm_option_rom(newrom, rom->size * 512);

固定默认机器没有TPM， ``TPM_working=0``，所以该调用立即返回而不产生measurement。
只有上一章的显式TPM条件分支成功时，它才先对将要执行的ROM image做measurement，再
把控制权交给ROM。

顺序必须是：

::

   确认最终执行字节
   → hash / PCR extend / event log
   → 执行 ROM

执行以后再测量会失去“记录实际即将运行内容”的意义，也可能让 ROM 有机会先修改被测量区域。

Option ROM 从 offset 3 开始执行
-----------------------------

传统 x86 Option ROM header 的前部通常是：

::

   +0x00  55 aa signature
   +0x02  image size in 512-byte units
   +0x03  initialization entry

SeaBIOS 使用 ``OPTION_ROM_INITVECTOR`` 调用该入口，也就是 ROM segment 的 offset ``0x0003``。

``__callrom()`` 为 ROM 准备寄存器：

.. code-block:: c

   FLAGS.IF = 1
   AX = PCI BDF
   BX = 0xffff
   DX = 0xffff
   ES = SEG_BIOS
   DI = PnP BIOS structure offset
   CS:IP = ROM segment:0003

``AX`` 中的 BDF 让 ROM 知道自己对应哪一个 PCI function。``ES:DI`` 则把 SeaBIOS 的 PnP expansion header 位置交给遵循 PnP BIOS 约定的 ROM。

为什么使用 farcall16big
----------------------

SeaBIOS 当前主流程仍在 32 位保护模式，而 Option ROM 是传统 16 位代码。

``farcall16big()`` 让 SeaBIOS：

* 临时进入 16 位 big-real 环境；
* 保持可访问较大平坦地址所需的 segment cache；
* 调用 ROM 的远地址入口；
* ROM 返回后恢复 SeaBIOS 32 位执行环境。

“big real mode” 不是 CPU 手册中的独立正式模式名称。它通常指 CPU 已回到实模式语义，但某些 segment hidden cache 仍保留由保护模式载入的较大 limit。

Option ROM 运行期间的线程抢占是条件功能
----------------------------------

``__callrom()`` 在远调用前后执行：

.. code-block:: c

   start_preempt();
   farcall16big(&br);
   finish_preempt();

只有 ``threads_during_optionroms()`` 为 true 时，``start_preempt()`` 才会开启 RTC periodic interrupt，并让中断处理路径定期检查 32 位设备初始化线程。

当前默认 ``ThreadControl=1``，所以：

* 不会在 VGA ROM 内部异步运行 USB/AHCI 探测线程；
* ``start_preempt()`` 实际不会开启这套抢占；
* VGA ROM 返回后才开始同步设备初始化。

不过 ``finish_preempt()`` 在该条件为false时仍调用一次 ``yield()``。当前还没有启动
USB/AHCI worker可供切换，但MainThread可在这个边界通过 ``check_irqs()`` 短暂开IF，
使第016章已放行的pending PIT/RTC中断得到处理。ROM自己的寄存器帧则以
``FLAGS.IF=1`` 进入16位代码；返回到32位MainThread后仍恢复为IF=0。

这避免外部 16 位 ROM 与固件设备线程共享复杂状态，也让默认执行顺序更容易复现。

VGA ROM 返回后怎样判断 INT 10h 是否可用
------------------------------------

SeaBIOS 在第四章建立 IVT 时，``INT 10h`` 最初指向自己的占位入口 ``entry_10``。

VGA ROM 初始化成功后，通常会把 IVT vector ``0x10`` 改成 ROM 中的 handler。SeaBIOS 的屏幕输出代码也会检查这一点：

.. code-block:: c

   if (GET_IVT(0x10) == entry_10)
       return;

如果 vector 仍指向占位 handler，SeaBIOS 不会假装屏幕已经可用。

``vgarom_setup()``、 ``init_pcirom()`` 和 ``enable_vga_console()`` 都不向 ``maininit()``
返回“VGA已成功”的状态。因此判断VGA ROM是否真正建立BIOS video service的关键，不
只是控制流已经返回，还包括 ``INT 10h`` 是否已经离开占位入口；失败只会让screen
character output静默跳过，不会终止POST。

sercon_setup 可以把 INT 10h 镜像到串口
----------------------------------

``vgarom_setup()`` 之后，``maininit()`` 调用 ``sercon_setup()``。

它只在配置了：

::

   etc/sercon-port

时启用。若 VGA ROM 已接管 ``INT 10h``，sercon 保存原 VGA handler，然后把 IVT ``0x10`` 改为自己的入口，形成 split mode：

::

   INT 10h
   → SeaBIOS serial-console wrapper
   → 条件输出 ANSI/UTF-8 serial terminal sequence
   → 条件转发给真实 VGA BIOS handler

没有 ``etc/sercon-port`` 时，当前固定默认路径直接跳过，不改变 ``INT 10h``。

SeaBIOS 最后怎样打开文字控制台
---------------------------

``enable_vga_console()`` 构造 BIOS video call：

.. code-block:: c

   AX = 0x0003
   INT 10h

AH=0 表示设置视频模式，AL=3 是经典的 80×25 彩色文本模式。

``enable_vga_console()`` 不先检查vector，也不检查 ``INT 10h`` 的返回状态；它总是发出
这次mode-set调用，然后执行：

.. code-block:: c

   printf("SeaBIOS (version %s)\n", VERSION);
   display_uuid();

正常standard-VGA分支中，屏幕上的SeaBIOS banner依赖此前完成的完整链：

::

   PCI VGA 被发现并启用
   → VGA ROM blob 可访问
   → ROM header / PCIR / checksum 合法
   → ROM 被复制到 0xc0000 区域
   → ROM 在 16 位环境执行
   → INT 10h 被安装
   → INT 10h AX=0003 设置文本模式
   → SeaBIOS printf 通过 INT 10h AH=0e 输出字符

如果ROM缺失、校验失败或没有安装 ``INT 10h``，mode 3调用不会被当成致命错误；随后
``screenc()`` 发现vector仍是 ``entry_10`` 时直接丢弃屏幕字符，debug输出是否仍可见
则由 ``ScreenAndDebug`` 决定。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``，位于 ``enable_vga_console()`` 返回后的
  ``maininit()``；
* CPU/mode：32位保护模式，分页关闭，A20开启，MainThread IF=0；16位ROM与INT 10h调用帧
  曾以IF=1运行，返回后恢复；
* ``ThreadControl=1``， ``threads_during_optionroms()=false``，提前的
  ``device_hardware_setup()`` 未执行；
* no-override display：QEMU standard VGA；禁用graphics或显式display覆盖时保留不同分支；
* ROM shadow：扫描前已清零，从 ``0xc0000`` 起只对通过部署/确认的ROM推进 ``RomEnd``；
* normal standard-VGA branch：匹配的x86 image通过signature/size/checksum检查，固定默认
  TPM路径没有测量，ROM已从segment offset 3执行并通常安装 ``INT 10h``；
* VGA failure branch：ROM缺失/无效或未安装vector不会终止POST， ``screenc()`` 可静默丢弃
  screen output；
* ``sercon``：固定默认没有 ``etc/sercon-port``，未包装 ``INT 10h``；显式配置时才建立
  primary或split wrapper；
* video mode： ``AX=0003`` 已被无条件请求，但SeaBIOS没有验证结果；
* USB、PS/2与block driver：尚未进入当前设备初始化阶段；
* 普通非VGA Option ROM：尚未扫描；
* next entry：第二次 ``threads_during_optionroms()`` 判断。

关键边界
--------

#. 固定QEMU不发布 ``etc/threads``，默认值1不会让设备worker跨VGA Option ROM运行。
#. q35的 ``default_display="std"`` 只决定无override时的默认display，不能覆盖禁用graphics
   或显式设备选择。
#. ``vgarom_setup`` 清零的是客户机低端ROM shadow窗口，不是PCI设备的持久ROM内容。
#. PCI ROM BAR只在映射/复制期间临时enable，完成或失败都恢复原 ``PCI_ROM_ADDRESS``。
#. 固定默认TPM缺席时 ``tpm_option_rom`` 是no-op；显式TPM分支才执行PCR/event-log测量。
#. Option ROM以16位入口和IF=1执行；MainThread返回32位路径后保持IF=0。
#. ``finish_preempt()`` 即使未开启ROM抢占也会yield一次，但此时尚无设备初始化worker。
#. ``enable_vga_console`` 请求mode 3后不校验返回；控制流返回不能冒充VGA成功证明。

下一入口
--------

``maininit()`` 接下来再次执行：

.. code-block:: c

   if (!threads_during_optionroms()) {
       device_hardware_setup();
       wait_threads();
   }

条件成立，下一章从 ``device_hardware_setup() → usb_setup()`` 开始，只追踪USB与
``ps2port_setup()``，并停在 ``block_setup()`` 调用之前； ``wait_threads()`` 仍在更后面。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/stacks.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c>`_；
* `SeaBIOS src/optionroms.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c>`_；
* `SeaBIOS src/bootsplash.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/bootsplash.c>`_；
* `SeaBIOS src/output.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/output.c>`_；
* `SeaBIOS src/sercon.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/sercon.c>`_；
* `SeaBIOS src/config.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_；
* `QEMU hw/i386/pc_q35.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c>`_；
* `QEMU hw/core/machine.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/core/machine.c>`_；
* `PCI Firmware Specification <https://pcisig.com/specifications>`_；
* `Plug and Play BIOS Specification <https://uefi.org/specifications>`_。
