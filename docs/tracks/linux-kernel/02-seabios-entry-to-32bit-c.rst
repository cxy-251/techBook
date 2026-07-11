第二章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？
===================================================

上一章结束时，BSP 已经离开 x86 特殊的复位向量，通过 SeaBIOS 的第一条远跳转来到：

::

   CS:IP = f000:e05b
   物理地址 = 0x000fe05b
   源码入口 = src/romlayout.S:entry_post

CPU 仍在 16 位启动环境中。分页没有开启，64 位模式没有开启，固件的主要 C 代码也还不能直接运行。
SeaBIOS 接下来要做的，是建立一个可供 32 位 C 代码使用的最小执行环境。

本章继续使用固定源码：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

entry_post 先判断这是不是第一次启动
-----------------------------------

``entry_post`` 在 ``src/romlayout.S`` 中只有三行核心逻辑：

.. code-block:: asm

           ORG 0xe05b
   entry_post:
           cmpl $0, %cs:HaveRunPost
           jnz entry_resume
           ENTRY_INTO32 _cfunc32flat_handle_post

第一条比较读取 ``HaveRunPost``。它在 ``src/misc.c`` 中定义：

.. code-block:: c

   int HaveRunPost VARFSEG;

它不是在判断 Linux 是否启动过，而是在判断 SeaBIOS 的 POST 初始化阶段是否已经运行过。

同一个复位入口不只会在机器第一次开机时到达。软件请求重启、某些恢复路径以及故障处理，也可能重新把
CPU 带到 BIOS 复位向量。SeaBIOS 因此不能看到 ``reset_vector`` 就无条件重做一次完整冷启动。

当前故事选择正常首次启动路径。此时：

::

   HaveRunPost == 0

所以 ``jnz entry_resume`` 不跳转，执行继续落入 ``ENTRY_INTO32``。

这里使用 ``%cs:HaveRunPost``，是因为固件此刻还没有建立新的数据段环境。``CS`` 已经由上一章的远跳转
装载为 SeaBIOS 确定的 ``0xf000``，使用 ``CS`` 段覆盖前缀可以直接从当前固件段访问这个状态变量，
不必先假设 ``DS`` 指向哪里。

ENTRY_INTO32 不是一个函数
-------------------------

``ENTRY_INTO32`` 定义在 ``src/entryfuncs.S``。它是汇编宏，构建时会直接展开到调用位置：

.. code-block:: asm

           .macro ENTRY_INTO32 cfunc
           xorw %dx, %dx
           movw %dx, %ss
           movl $BUILD_STACK_ADDR, %esp
           movl $\cfunc, %edx
           jmp transition32
           .endm

把 ``cfunc`` 替换成当前参数以后，``entry_post`` 实际执行的逻辑相当于：

.. code-block:: asm

           xorw %dx, %dx
           movw %dx, %ss
           movl $0x7000, %esp
           movl $_cfunc32flat_handle_post, %edx
           jmp transition32

这几条指令分别准备栈、保存最终目的地，然后进入统一的模式切换代码。

为什么栈放在 0x7000
-------------------

SeaBIOS 的 ``src/config.h`` 定义：

.. code-block:: c

   #define BUILD_STACK_ADDR 0x7000

宏先把 ``SS`` 设置为 ``0``，再把 ``ESP`` 设置为 ``0x7000``。在当前 16 位分段环境中，栈顶对应的线性
地址是：

::

   SS.base + ESP
   = 0x0000 + 0x7000
   = 0x7000

这里需要区分真实主板和当前固定平台。

真实裸机固件在使用普通 DRAM 前，通常要先完成内存控制器初始化和 DRAM 训练。当前主线是
``QEMU q35 + SeaBIOS``：QEMU 在启动虚拟 CPU 之前已经创建客户机 RAM，SeaBIOS 可以按约定使用低端
客户机内存。因此它能够直接把 ``0x7000`` 作为早期栈位置。

这个选择没有让整个内存系统“初始化完成”。它只说明在当前虚拟平台上，SeaBIOS 已经有一小块确定的低端
RAM 可以承载返回地址、局部变量和 C 函数调用栈。

为什么目的函数地址放进 EDX
-------------------------

下面这条指令把最终要执行的 32 位 C 入口保存到 ``EDX``：

.. code-block:: asm

   movl $_cfunc32flat_handle_post, %edx

紧接着执行的是：

.. code-block:: asm

   jmp transition32

这里使用 ``jmp``，不是 ``call``。模式切换代码不会返回到 16 位的 ``entry_post``。它完成转换后，直接
通过 ``EDX`` 跳到指定的 C 入口。

``transition32`` 是一个通用跳板，SeaBIOS 的其他入口也可以把不同目标地址放进 ``EDX``，然后复用同一套
16 位到 32 位的转换过程。

transition32 先冻结不稳定的外部事件
---------------------------------

``transition32`` 位于 ``src/romlayout.S``：

.. code-block:: asm

   transition32:
           cli
           cld

``cli`` 清除 ``RFLAGS.IF``，阻止可屏蔽硬件中断进入。此时还没有安装可工作的保护模式中断处理环境；
如果键盘、定时器或其他设备中断恰好进入，CPU 找不到正确处理入口，模式切换就可能中断在半完成状态。

``cld`` 清除方向标志 ``DF``。当 ``DF=0`` 时，字符串指令从低地址向高地址移动。C 编译器和后面的内存
操作通常把 ``DF=0`` 当作调用约定的一部分，所以进入 C 环境前要把它恢复为确定状态。

``cli`` 只能屏蔽普通可屏蔽中断，不能屏蔽 NMI。SeaBIOS 随后通过 CMOS/RTC 索引端口处理 NMI：

.. code-block:: asm

           movl %eax, %ecx
           movl $CMOS_RESET_CODE|NMI_DISABLE_BIT, %eax
           outb %al, $PORT_CMOS_INDEX
           inb $PORT_CMOS_DATA, %al
           movl %ecx, %eax

对应常量是：

.. code-block:: c

   #define PORT_CMOS_INDEX   0x0070
   #define PORT_CMOS_DATA    0x0071
   #define NMI_DISABLE_BIT   0x80
   #define CMOS_RESET_CODE   0x0f

向端口 ``0x70`` 写入的最高位控制 NMI 屏蔽。SeaBIOS 暂时阻止 NMI，在新的 IDT 和执行环境稳定前，不让
不可屏蔽中断把控制流带到未知位置。

这段代码先把 ``EAX`` 保存到 ``ECX``，操作端口后再恢复 ``EAX``。模式切换跳板可以改变内部临时状态，
仍尽量不无故破坏调用方可能保留的寄存器值。

A20：地址的第 20 位必须真正生效
-------------------------------

接下来是：

.. code-block:: asm

           inb $PORT_A20, %al
           orb $A20_ENABLE_BIT, %al
           outb %al, $PORT_A20

SeaBIOS 定义：

.. code-block:: c

   #define PORT_A20        0x0092
   #define A20_ENABLE_BIT  0x02

A20 是地址总线的第 20 位，从位 0 开始计数。它决定地址是否能够越过 1 MiB 边界。

早期 IBM PC 为了兼容 8086 的 20 位地址回绕行为，允许强制关闭 A20。关闭时，地址 ``0x100000`` 会把
第 20 位丢掉，别名到 ``0x000000``。这种回绕行为对旧软件有兼容价值，对即将建立的 32 位平坦地址空间
却是错误的。

SeaBIOS 通过系统控制端口 ``0x92`` 打开 A20，让：

::

   0x000000 和 0x100000

成为真正不同的地址。否则后面访问 1 MiB 以上内存时，数据可能悄悄覆盖低端内存。

lgdt 和 lidt 装入的不是整张表
-----------------------------

接下来执行：

.. code-block:: asm

   transition32_nmi_off:
           lidtw %cs:pmode_IDT_info
           lgdtw %cs:rombios32_gdt_48

``lidt`` 和 ``lgdt`` 的操作数不是 IDT、GDT 表本身，而是一个描述表位置的结构。这个结构包含：

* 表的长度减一；
* 表的线性基地址。

SeaBIOS 在 ``src/misc.c`` 中定义保护模式 IDT 描述符：

.. code-block:: c

   u8 dummy_IDT VARFSEG;

   struct descloc_s pmode_IDT_info VARFSEG = {
       .length = sizeof(dummy_IDT) - 1,
       .addr = (u32)&dummy_IDT,
   };

它目前不是一张完整的中断门表，而是故意极小的占位 IDT。源码注释说明：如果保护模式切换阶段真的发生
中断，这个 dummy IDT 会使机器停止，而不是让 CPU 跳进一段未经准备的处理代码。

这也是前面同时执行 ``cli`` 和 NMI 屏蔽的原因：当前阶段的目标是无干扰地穿过模式边界，不是开始正常
处理中断。

GDT 描述 32 位代码和数据怎样解释地址
----------------------------------

SeaBIOS 的 ``rombios32_gdt`` 至少包含这几项：

.. code-block:: c

   u64 rombios32_gdt[] = {
       0x0000000000000000LL,
       /* 32 位平坦代码段 */
       GDT_GRANLIMIT(0xffffffff) | GDT_CODE | GDT_B,
       /* 32 位平坦数据段 */
       GDT_GRANLIMIT(0xffffffff) | GDT_DATA | GDT_B,
       /* 后面还有供 16 位兼容路径使用的描述符 */
   };

第一项是不能使用的空描述符。第二项是 32 位平坦代码段，第三项是 32 位平坦数据段。

``src/config.h`` 把它们对应的选择子定义为：

.. code-block:: c

   #define SEG32_MODE32_CS (1 << 3)
   #define SEG32_MODE32_DS (2 << 3)

因此：

::

   32 位代码段选择子 = 0x08
   32 位数据段选择子 = 0x10

选择子的高位保存描述符索引，低三位保存 TI 和 RPL。每个 GDT 描述符占 8 字节，所以索引左移三位就
得到选择子值。

这里的“平坦”表示代码段和数据段基址都为 ``0``，范围覆盖 32 位线性地址空间。进入这个环境后，程序
使用的地址不再需要像实模式那样反复计算 ``segment × 16 + offset``。段寄存器仍然存在，段描述符把它们
配置成接近普通 32 位线性地址的用法。

CR0.PE：打开保护模式开关
-----------------------

GDT 和临时 IDT 的位置已经装入 CPU 后，SeaBIOS 修改 ``CR0``：

.. code-block:: asm

           movl %cr0, %ecx
           andl $~(CR0_PG|CR0_CD|CR0_NW), %ecx
           orl $CR0_PE, %ecx
           movl %ecx, %cr0

这些位的含义是：

``CR0.PE``
   Protection Enable。设置后启用保护模式的分段规则。

``CR0.PG``
   Paging。SeaBIOS 此刻没有建立页表，因此把它清零。

``CR0.CD`` 与 ``CR0.NW``
   缓存相关控制位。这里被清除，让接下来的环境不继承异常的禁用缓存状态。

真正触发模式变化的是 ``CR0.PE = 1``。

写入 ``CR0`` 后，处理器已经打开保护模式规则，当前 ``CS`` 缓存里仍然保留着进入前的代码段状态。
所以代码不能把下一条普通指令当作整个切换已经结束，还必须重新装载 ``CS``。

为什么设置 PE 后必须远跳转
------------------------

SeaBIOS 立刻执行：

.. code-block:: asm

   ljmpl $SEG32_MODE32_CS, $(BUILD_BIOS_ADDR + 1f)

这里装入：

::

   CS = 0x08

CPU 使用 ``0x08`` 作为 GDT 选择子，取出第一个可用的 32 位平坦代码段描述符。远跳转还把新的指令地址
装入 ``EIP``，并清理掉模式切换边界上的旧取指状态。

跳转目标使用 ``BUILD_BIOS_ADDR + 1f``。``BUILD_BIOS_ADDR`` 是 ``0x000f0000``；``1f`` 表示当前汇编
文件中后方编号为 ``1`` 的局部标签。这样，进入基址为零的 32 位代码段后，``EIP`` 仍然指向 BIOS 映像中
正确的线性地址。

源文件随后切换汇编器解释模式：

.. code-block:: asm

           .code32
   1:

``.code32`` 不会在运行时改变 CPU。它告诉汇编器，从这里开始按 32 位指令编码；真正让 CPU 进入保护模式
并装载 32 位代码段的是前面的 ``CR0.PE`` 和远跳转。

数据段也要全部换成 32 位描述符
----------------------------

进入局部标签 ``1`` 后，SeaBIOS 设置数据段：

.. code-block:: asm

   1:      movl $SEG32_MODE32_DS, %ecx
           movw %cx, %ds
           movw %cx, %es
           movw %cx, %ss
           movw %cx, %fs
           movw %cx, %gs

``SEG32_MODE32_DS`` 是 ``0x10``。加载这些段寄存器后：

* ``DS`` 和 ``ES`` 使用基址为零的 32 位数据段；
* ``SS`` 让前面位于 ``0x7000`` 的栈继续以平坦地址工作；
* ``FS`` 和 ``GS`` 也先进入同一基础数据段环境。

此时栈指针仍然是：

::

   ESP = 0x00007000

区别在于，进入保护模式后 ``SS`` 不再表示实模式段基址 ``SS × 16``，而是选择 GDT 中基址为零的数据段。
由于切换前 ``SS`` 本来就是零，栈的线性位置在切换前后都保持为 ``0x7000``，不会因为模式变化突然移动。

最后一跳进入 C
-------------

模式转换代码的最后一条核心指令是：

.. code-block:: asm

   jmpl *%edx

``EDX`` 仍保存：

::

   _cfunc32flat_handle_post

这是链接器为 ``post.c:handle_post()`` 生成的 32 位平坦入口符号。间接跳转执行后，CPU 第一次进入
SeaBIOS 的主要 32 位 C 初始化代码：

.. code-block:: c

   void VISIBLE32FLAT
   handle_post(void)
   {
       if (!CONFIG_QEMU && !CONFIG_COREBOOT)
           return;

       serial_debug_preinit();
       debug_banner();
       xen_preinit();
       make_bios_writable();
       dopost();
   }

本章不继续展开这些函数。此处发生了清晰的运行环境交接：前两章一直依靠少量固定位置的 16 位汇编代码，
现在 SeaBIOS 已经拥有栈、平坦段、受控中断状态和 32 位 C 执行入口，可以开始大规模初始化平台。

第二章结束时的机器状态
----------------------

控制权目前走过：

::

   SeaBIOS entry_post
   → 检查 HaveRunPost
   → SS:ESP 指向 0x0000:0x7000
   → EDX 保存 handle_post 入口
   → transition32
   → cli / cld / 屏蔽 NMI
   → 打开 A20
   → 装入临时 IDT 和 GDT
   → 设置 CR0.PE
   → 远跳转并装入 CS=0x08
   → 装入 DS/ES/SS/FS/GS=0x10
   → 跳入 post.c:handle_post()

此刻：

* 当前执行者：SeaBIOS 的 ``handle_post()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* 64 位模式：关闭；
* A20：开启；
* 栈：平坦地址 ``0x7000``；
* 可屏蔽中断：关闭；
* NMI：临时屏蔽；
* 当前代码：SeaBIOS 32 位平坦 C 代码；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

第二章在这里结束。下一段控制流从 ``handle_post()`` 的第一批调用继续：串口调试、启动横幅、Xen 检测、
把 BIOS 区域改成可写，然后进入真正的 POST 初始化 ``dopost()``。

资料
----

* SeaBIOS ``src/romlayout.S``；
* SeaBIOS ``src/entryfuncs.S``；
* SeaBIOS ``src/config.h``；
* SeaBIOS ``src/x86.h``；
* SeaBIOS ``src/hw/rtc.h``；
* SeaBIOS ``src/misc.c``；
* SeaBIOS ``src/post.c``；
* SeaBIOS ``docs/Execution_and_code_flow.md``；
* Intel® 64 and IA-32 Architectures Software Developer’s Manual，保护模式、分段、控制寄存器与中断相关章节。