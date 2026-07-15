第六章：SeaBIOS 怎样建立中断基础并准备内部线程？
=================================================

上一章结束时，SeaBIOS 已经建立了 BIOS 软件接口，控制流回到重定位后的：

::

   post.c:maininit()

接下来执行：

.. code-block:: c

   platform_hardware_setup();

这个函数的完整调用顺序是：

.. code-block:: c

   static void
   platform_hardware_setup(void)
   {
       dma_setup();

       pic_setup();
       thread_setup();
       mathcp_setup();

       qemu_platform_setup();
       coreboot_platform_setup();

       timer_setup();
       clock_setup();

       tpm_setup();
   }

其中 ``qemu_platform_setup()`` 本身还会展开 PCI、SMM、MTRR、SMP、PIR、MP、SMBIOS 和 ACPI 等一整段
平台初始化。为了保留中间细节，本章先完成前四个调用：

::

   dma_setup()
   → pic_setup()
   → thread_setup()
   → mathcp_setup()

本章结束时，SeaBIOS 已经让传统 DMA 保持在安全状态，建立 8259A 中断路由，准备好
固件内部协作式线程策略，并装好旧式数学协处理器异常的兼容路径。真正的设备线程要
等后续代码调用 ``run_thread()`` 才会创建。下一段才进入 QEMU q35 专属的平台初始化。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

当前路径使用该提交的默认QEMU配置： ``CONFIG_HARDWARE_IRQ=y``、
``CONFIG_THREADS=y``、 ``CONFIG_RTC_TIMER=y``。本章仍只写
``platform_hardware_setup()`` 的当前四个调用；默认配置允许的RTC辅助线程执行要到
更晚的Option ROM阶段才可能开启。

DMA 控制器为什么必须先复位
-------------------------

``dma_setup()`` 位于 ``src/hw/dma.c``。源码注释直接写明它的目的：

.. code-block:: c

   // Make sure legacy DMA isn't running.
   dma_setup();

DMA 是 Direct Memory Access，直接内存访问。设备使用 DMA 时，可以让 DMA 控制器在设备端口和内存之间
搬运数据，而不必让 CPU 为每个字节执行一次读写。

这里处理的是传统 PC 中的 Intel 8237 兼容 DMA 控制器。经典 AT 结构包含两片级联的 8237：

::

   第一片 DMA 控制器
      管理低编号的 8 位 DMA 通道

   第二片 DMA 控制器
      管理高编号的 16 位 DMA 通道
      其中一个通道用于级联第一片控制器

SeaBIOS 还没有开始使用软盘等 DMA 设备。这里的源码也不先读取寄存器来证明某个通道正在传输；
它无条件重写控制器状态，使冷启动、固件重入等不同入口都在同一个边界继续。因而本章能从固定源码
确认的是“SeaBIOS主动建立静止状态”，不能把它写成当前QEMU冷启动中必然先有一笔活动DMA被停止。

如果 DMA 控制器仍然保留一个活动传输，后续内存被固件重新分配后，它可能继续向旧地址写入数据。CPU 不需要
执行相应写指令，内存也会被改坏。因此 SeaBIOS 在建立更复杂的平台状态前，先让两片控制器回到已知状态。

dma_setup 实际写了哪些端口
--------------------------

源码只有几行：

.. code-block:: c

   void
   dma_setup(void)
   {
       outb(0, PORT_DMA1_MASTER_CLEAR);
       outb(0, PORT_DMA2_MASTER_CLEAR);

       outb(0xc0, PORT_DMA2_MODE_REG);
       outb(0x00, PORT_DMA2_MASK_REG);
   }

相关 I/O 端口是：

::

   0x000d  第一片 DMA 控制器的 master clear
   0x00da  第二片 DMA 控制器的 master clear
   0x00d6  第二片 DMA 控制器的 mode register
   0x00d4  第二片 DMA 控制器的 single-channel mask register

``outb()`` 是 x86 端口 I/O 指令的封装。这里的地址不是普通内存地址；CPU 会执行 ``OUT`` 指令，把一个字节
发送给 I/O 端口对应的设备模型。

先写两次 master clear
---------------------

SeaBIOS 首先向两片控制器的 master clear 端口各写一次：

.. code-block:: c

   outb(0, PORT_DMA1_MASTER_CLEAR);
   outb(0, PORT_DMA2_MASTER_CLEAR);

写入的数据值本身不重要，关键是对这个端口发生一次写操作。master clear 会清理控制器内部状态，并把普通
DMA 通道置于被屏蔽的安全状态。

这一步不会擦除内存，也不会主动搬运任何数据。它只是停止并重置 DMA 控制器自己的请求、模式和通道状态。

为什么随后又写入 0xc0
---------------------

两片 8237 不是完全独立的。第一片控制器需要通过第二片控制器的级联通道把请求送到系统总线。在 AT 兼容编号中，
第二片控制器的本地通道 0 对应系统 DMA 通道 4，它不用于普通设备数据传输，而是连接第一片控制器。

SeaBIOS 向第二片控制器的模式寄存器写入：

::

   0xc0 = 1100 0000b

对 8237 模式寄存器来说：

* 最高两位 ``11`` 选择 cascade mode，也就是级联模式；
* 最低两位 ``00`` 选择第二片控制器的本地通道 0；
* 中间位保持为零，不请求普通读写传输、地址递减或自动初始化。

随后写入：

.. code-block:: c

   outb(0x00, PORT_DMA2_MASK_REG);

对 single-channel mask register 来说，``0x00`` 表示清除本地通道 0 的 mask，也就是解除该级联通道的屏蔽。

最终状态不是“所有 DMA 通道已经可以随便传输”，而是：

::

   普通 DMA 通道：保持在安全、未活动状态
   两片控制器之间的级联通道：重新接通

以后软盘驱动真正需要 DMA 通道 2 时，SeaBIOS 才会使用 ``dma_floppy()`` 设置地址、长度、传输方向和页面寄存器。
本章这里没有发生任何软盘数据传输。

PIC 决定硬件中断进入哪个向量
---------------------------

DMA 安静下来后，SeaBIOS 调用：

.. code-block:: c

   pic_setup();

PIC 是 Programmable Interrupt Controller，可编程中断控制器。当前传统 PC 路径使用两片级联的 8259A：

::

   master PIC
      接收 IRQ0 - IRQ7

   slave PIC
      接收 IRQ8 - IRQ15
      输出连接到 master PIC 的 IRQ2

设备发出 IRQ 后，PIC 不会把字符串“键盘中断”或“时钟中断”交给 CPU。它向 CPU 提交一个中断向量号。CPU
再用这个向量号查询前面已经建立的 IVT，找到对应处理入口。

因此第四章建立 IVT，只是准备了“向量号对应哪个入口”；本章的 ``pic_setup()`` 则准备“硬件 IRQ 应该产生
哪个向量号”。两边必须一致。

两片 PIC 使用四轮初始化命令
-------------------------

``pic_setup()`` 调用：

.. code-block:: c

   pic_reset(BIOS_HWIRQ0_VECTOR, BIOS_HWIRQ8_VECTOR);

固定向量基址是：

::

   BIOS_HWIRQ0_VECTOR = 0x08
   BIOS_HWIRQ8_VECTOR = 0x70

``pic_reset()`` 依次发送四组 Initialization Command Word，也就是 ICW。

第一轮：ICW1 宣布重新初始化
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   outb(0x11, PORT_PIC1_CMD);
   outb(0x11, PORT_PIC2_CMD);

端口是：

::

   master command port = 0x20
   slave command port  = 0xa0

``0x11`` 告诉两片 8259A：开始初始化序列、系统采用级联结构，并且后面还会发送 ICW4。

第二轮：ICW2 设置中断向量基址
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   outb(0x08, PORT_PIC1_DATA);
   outb(0x70, PORT_PIC2_DATA);

于是硬件 IRQ 与 BIOS 向量的关系是：

::

   IRQ0  - IRQ7   → INT 0x08 - INT 0x0f
   IRQ8  - IRQ15  → INT 0x70 - INT 0x77

例如：

::

   IRQ0   系统计时器      → INT 0x08
   IRQ1   键盘            → INT 0x09
   IRQ8   实时时钟        → INT 0x70
   IRQ12  PS/2 鼠标       → INT 0x74
   IRQ13  数学协处理器    → INT 0x75
   IRQ14  第一 ATA 通道   → INT 0x76

``0x08`` 在 32 位保护模式中也属于 CPU 异常向量范围，因此现代操作系统通常会重新映射 PIC，避免硬件 IRQ 与
CPU 异常重叠。这里仍使用传统 BIOS 布局，因为 SeaBIOS 要为实模式 BIOS 服务和旧式启动软件保持兼容。Linux
以后接管中断系统时，会建立自己的 IDT 和中断控制器配置，不能继续把当前固件布局当作内核运行时布局。

第三轮：ICW3 描述两片 PIC 怎样级联
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   outb(0x04, PORT_PIC1_DATA);
   outb(0x02, PORT_PIC2_DATA);

master 收到 ``0x04``：

::

   0000 0100b

第 2 位为 1，表示 slave PIC 连接在 master 的 IRQ2。

slave 收到 ``0x02``，表示自己在级联链路中的 ID 是 2。这样 slave 发出的 IRQ8-IRQ15 会先经过 master 的
IRQ2，再送到 CPU。

第四轮：ICW4 选择 8086/88 模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   outb(0x01, PORT_PIC1_DATA);
   outb(0x01, PORT_PIC2_DATA);

``0x01`` 选择 8086/8088 interrupt mode。PIC 之后向 x86 CPU 提供前面配置的 8 位中断向量号。

初始化完成后先屏蔽几乎所有 IRQ
-----------------------------

``pic_reset()`` 最后执行：

.. code-block:: c

   pic_irqmask_write(PIC_IRQMASK_DEFAULT);

默认掩码定义为：

.. code-block:: c

   #define PIC_IRQMASK_DEFAULT ((u16)~PIC1_IRQ2)

换成 16 位值就是：

::

   0xfffb

掩码位为 1 表示对应 IRQ 被屏蔽。因此此时：

* IRQ0、IRQ1、IRQ3-IRQ15 都被屏蔽；
* master IRQ2 保持解除屏蔽；
* IRQ2 本身不是普通设备当前就要使用的通道，它是 slave PIC 向 master 传递 IRQ8-IRQ15 的级联入口。

只解除 master IRQ2 还不会让 slave 上的设备立即打断 CPU，因为 slave 自己的八个输入仍然全部被屏蔽。
后续每个硬件服务安装好处理函数后，才会单独解除对应 IRQ。

为什么 PIC 初始化后 CPU 仍没有持续响应中断
--------------------------------------

配置 PIC 不等于执行了 ``sti``。当前主控制流的中断标志仍不会被永久打开。

SeaBIOS 后面会在确定安全的位置短暂执行类似：

.. code-block:: asm

   sti
   nop
   rep; nop
   cli
   cld

这给待处理硬件中断一个很短的执行窗口，然后再次关闭可屏蔽中断。固件初始化期间频繁切换 CPU 模式、栈和
地址环境，长期保持中断开启会让处理函数在不适合的上下文中进入。

thread_setup 建立的不是多核线程
------------------------------

PIC 和 IVT 已经可以接住受控中断后，SeaBIOS 调用：

.. code-block:: c

   thread_setup();

源码是：

.. code-block:: c

   void
   thread_setup(void)
   {
       CanInterrupt = 1;
       call16_override(1);
       if (!CONFIG_THREADS)
           return;
       ThreadControl = romfile_loadint("etc/threads", 1);
   }

这里的 SeaBIOS thread 不是 Linux 线程，也不是让多个 CPU 同时执行任务。它是一套固件内部的协作式任务切换
机制。

``CanInterrupt = 1`` 的含义是：

::

   IVT 已经建立
   PIC 已经初始化
   SeaBIOS 现在允许在受控位置短暂开放硬件中断

在这之前，``check_irqs()`` 即使被调用也不能安全执行 ``sti``，因为到来的 IRQ 可能没有正确的向量和处理入口。

call16_override 为什么选择 big real 环境
---------------------------------------

``call16_override(1)`` 先检查当前 ``ESP`` 没有高于早期栈顶 ``0x7000``，然后清零
``Call16Data``，把 ``method`` 设为 ``C16_BIG``，并把保存的A20状态设为1。它为下一次
16/32位转换准备一份无调用者残留的初始记录；当前调用本身没有切换CPU模式，也没有
立即进入16位代码。

SeaBIOS 经常需要从当前 32 位平坦 C 代码进入 16 位 BIOS 入口，再返回 32 位代码。普通实模式段寄存器只能自然
描述 64 KiB 段；固件内部的一些转换代码还需要保持更大的地址访问能力。

``C16_BIG`` 路径会先在保护模式中装入拥有大段界限的 16 位段描述符，再关闭 ``CR0.PE``。处理器进入实模式后，
段寄存器隐藏缓存中的大界限仍暂时保留，这种环境常被称为 big real mode 或 unreal mode。

这不是新的正式 CPU 模式，也不是 32 位保护模式仍然开启。它利用的是段寄存器可见值与隐藏描述符缓存之间的
差异，让 16 位代码在特定固件路径中访问超过普通 64 KiB 段界限的地址。

保存值 ``a20=1`` 使对应转换返回路径不把A20恢复成关闭状态，避免1 MiB以上地址在
16位兼容调用中发生回绕。

SeaBIOS 的协作式线程怎样切换
---------------------------

启用线程支持时，``ThreadControl`` 从 QEMU ``fw_cfg`` 的 ``etc/threads`` 项读取，缺省值是 1：

::

   0  不创建固件线程，任务同步执行
   1  允许协作式线程
   2  允许线程，并可在 Option ROM 阶段配合 RTC 检查线程执行

真正创建任务时，``run_thread()`` 会为每个任务从临时高端内存分配：

::

   4096 字节栈
   4096 字节对齐

每个线程的 ``thread_info`` 位于自己栈空间的底部，保存：

* 当前栈指针；
* 线程链表节点。

切换线程的核心不是改变 CPU，也不是进入操作系统调度器，而是保存和替换 ``ESP``：

.. code-block:: asm

   pushl return_address
   pushl %ebp
   movl  %esp, current->stackpos
   movl  next->stackpos, %esp
   popl  %ebp
   retl

``retl`` 会从新线程栈中取出该线程上次保存的返回地址，于是 CPU 从另一个任务之前让出执行的位置继续。

线程只有在代码主动调用 ``yield()``、等待事件或进入相应检查点时才切换，所以这是 cooperative scheduling，
协作式调度。某个任务一直不让出 CPU，其他任务就无法运行。

这套机制的用途是让不同设备初始化可以交错等待。例如一个设备在等待控制器状态变化时调用 ``yield()``，CPU
可以暂时推进另一个设备的探测，而不是空转等待。

现在还没有创建任何设备线程
-------------------------

``thread_setup()`` 只建立能力和策略。当前调用结束时，通常仍只有：

::

   MainThread

设备线程要等后面的 ``usb_setup()``、存储控制器初始化等代码调用 ``run_thread()`` 才会出现。

``ThreadControl == 2`` 对应的 RTC 辅助抢占也还没有启动。它需要后面的时钟初始化，并且只在特定 Option ROM
执行阶段由 ``start_preempt()`` 临时开启。

mathcp_setup 保留早期 PC 的数学协处理器接口
----------------------------------------

第四个调用是：

.. code-block:: c

   mathcp_setup();

``mathcp`` 指 math coprocessor，也就是早期 x86 体系中的 80x87 浮点协处理器。现代 x86 CPU 已经把浮点执行单元
集成进处理器，但传统 BIOS 数据结构和中断接口仍然保留这段兼容历史。

源码只有两项操作：

.. code-block:: c

   void
   mathcp_setup(void)
   {
       set_equipment_flags(0x02, 0x02);
       enable_hwirq(13, FUNC16(entry_75));
   }

先在 BDA 声明存在数学协处理器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``set_equipment_flags(0x02, 0x02)`` 把 BDA ``equipment_list_flags`` 的第 1 位设为 1。

以后软件调用 ``INT 11h`` 时，SeaBIOS 会返回这份 equipment word。该位告诉传统软件：系统提供 80x87 兼容的
数学协处理能力。

它不是在这里探测现代 CPU 的每一项 SSE、AVX 或 x87 特性，也没有初始化 Linux 将来使用的 FPU 上下文管理。
这里只是在填写传统 BIOS 兼容标志。

再为 IRQ13 安装 INT 75h 入口
~~~~~~~~~~~~~~~~~~~~~~~~~~~

``enable_hwirq(13, FUNC16(entry_75))`` 做两件事。

第一，解除 slave PIC 上 IRQ13 的屏蔽。由于 master IRQ2 已经保持开启，IRQ13 现在拥有完整路径：

::

   数学协处理器兼容 IRQ13
   → slave PIC
   → master PIC IRQ2
   → CPU

第二，把对应 IVT 项指向 ``entry_75``。IRQ13 在 slave PIC 中是第 5 个输入，因此向量为：

::

   0x70 + (13 - 8) = 0x75

所以这项 BIOS 服务通常称为 ``INT 75h``。

INT 75h 处理函数做了什么
-----------------------

``entry_75`` 最终进入 ``handle_75()``：

.. code-block:: c

   void
   handle_75(void)
   {
       outb(0, 0x00f0);
       pic_eoi2();

       struct bregs br;
       memset(&br, 0, sizeof(br));
       br.flags = F_IF;
       call16_int(0x02, &br);
   }

它先向端口 ``0xf0`` 写入，清除旧式 IRQ13 锁存状态。

随后 ``pic_eoi2()`` 依次向 slave PIC 和 master PIC 发送 End Of Interrupt。由于 IRQ13 经过两片 PIC，只有
slave 收到 EOI 还不够；master 的级联 IRQ2 也必须结束，否则后续 slave 中断可能一直被阻塞。

最后，SeaBIOS 主动调用 ``INT 02h``，进入传统 NMI 风格的数学异常通知路径。

现代操作系统通常使用 CPU 的原生浮点异常机制和自己的异常向量，不依赖这条 BIOS IRQ13 路径。SeaBIOS 仍然
建立它，是为了保证传统启动软件和旧式运行环境看到完整的 PC BIOS 接口。

本章结束状态
------------

控制权目前走过：

::

   maininit()
   → platform_hardware_setup()
   → dma_setup()
   → 复位两片 8237 兼容 DMA 控制器
   → 重新接通 DMA 级联通道
   → pic_setup()
   → 初始化 master/slave 8259A
   → IRQ0-7 映射到 0x08-0x0f
   → IRQ8-15 映射到 0x70-0x77
   → 默认屏蔽全部设备 IRQ，只保留级联 IRQ2
   → thread_setup()
   → 允许后续受控中断窗口
   → 建立 big-real 兼容调用状态
   → 读取 SeaBIOS 内部线程策略
   → mathcp_setup()
   → 在 BDA 声明数学协处理器
   → 为 IRQ13 安装 INT 75h 兼容入口

此刻：

* 当前执行者：重定位后的 SeaBIOS ``platform_hardware_setup()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* NMI：仍由CMOS index bit 7屏蔽；
* 当前 ``ESP``：不高于早期栈顶 ``0x7000``，精确值不固定；
* 传统 DMA：控制器已复位，普通通道未开始传输；
* PIC：两片 8259A 已初始化；
* PIC 向量布局：已采用传统 BIOS ``0x08`` 和 ``0x70`` 基址；
* 当前解除屏蔽的关键线路：master IRQ2 级联线和 slave IRQ13；
* 可屏蔽中断：只会在 SeaBIOS 受控位置短暂开放；
* ``Call16Data``：已清零并预置 ``C16_BIG``、A20保持开启；
* SeaBIOS 内部线程机制：策略已经初始化，链表中仍只有 ``MainThread``；
* 设备线程栈与RTC辅助执行：均尚未创建或开启；
* 数学协处理器 BIOS 标志和 IRQ13 兼容入口：已经建立；
* PCI 枚举：尚未执行；
* SMM、MTRR 和其他处理器启动：尚未建立；
* ACPI、SMBIOS、MP table：尚未生成；
* 定时器和周期时钟：尚未初始化；
* 磁盘控制器和具体启动设备：尚未探测；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

关键边界
--------

#. ``dma_setup()`` 无条件重写DMA控制器；它证明本章结束时的状态，不证明调用前必然
   存在活动传输。
#. PIC向量基址、PIC掩码和IVT入口是三组不同状态； ``pic_setup()`` 先建立前两组，
   ``mathcp_setup()`` 再解除IRQ13并覆盖对应 ``INT 75h`` 项。
#. 初始化PIC不等于长期执行 ``sti``； ``CanInterrupt=1`` 只允许 ``check_irqs()``
   在受控位置短暂开放后重新关闭IF。
#. ``call16_override(1)`` 只准备下一次转换所用的 ``Call16Data``，本身没有把当前CPU
   切到big real环境。
#. 即使 ``CONFIG_THREADS=y`` 且运行时 ``ThreadControl`` 非零，也只是允许后续
   ``run_thread()`` 创建线程；本章没有调用它，不能提前产生设备线程或4 KiB线程栈。
#. ``ThreadControl=2`` 的RTC辅助执行还要求之后的时钟初始化与
   ``start_preempt()``，当前尚未发生。

下一入口
--------

控制流仍在 ``platform_hardware_setup()``，下一条真实调用是：

.. code-block:: c

   qemu_platform_setup();

第007章从 ``qemu_platform_setup()`` 的普通QEMU分支继续； ``kvmclock_init()`` 先按
KVM检测结果选择是否返回，随后 ``pci_setup()`` 才开始当前q35的PCI主线。

资料
----

* `SeaBIOS src/post.c：platform_hardware_setup顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L137-L158>`_；
* `SeaBIOS src/hw/dma.c：8237复位与级联 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/dma.c#L56-L67>`_；
* `SeaBIOS src/hw/pic.c：8259A初始化与enable_hwirq <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pic.c#L40-L80>`_；
* `SeaBIOS src/hw/pic.h：向量、掩码与EOI <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pic.h#L29-L51>`_；
* `SeaBIOS src/stacks.c：Call16Data与call16_override <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c#L22-L130>`_；
* `SeaBIOS src/stacks.c：线程初始化、创建与受控中断窗口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c#L466-L621>`_；
* `SeaBIOS src/misc.c：mathcp与INT 75h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/misc.c#L40-L85>`_；
* `SeaBIOS src/Kconfig：线程默认配置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L35-L53>`_；
* `SeaBIOS src/Kconfig：RTC与硬件中断默认配置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L326-L345>`_；
* `SeaBIOS execution and code flow <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Execution_and_code_flow.md>`_。
