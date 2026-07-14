第二章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？
===================================================

上一章结束时，BSP 已经离开 x86 特殊的复位向量，通过 SeaBIOS 的第一条远跳转来到：

::

   CS:IP = f000:e05b
   物理地址 = 0x000fe05b
   源码入口 = src/romlayout.S:entry_post

CPU 仍在 16 位启动环境中。分页没有开启，64 位模式没有开启，固件的主要 C 代码也还不能直接运行。
SeaBIOS 接下来要做的，是建立一个可以安全执行 32 位 C 代码的最小环境。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

entry_post 先判断这是不是第一次启动
-----------------------------------

``entry_post`` 位于 ``src/romlayout.S`` 的固定偏移 ``0xe05b``：

.. code-block:: asm

           ORG 0xe05b
   entry_post:
           cmpl $0, %cs:HaveRunPost
           jnz entry_resume
           ENTRY_INTO32 _cfunc32flat_handle_post

第一条比较读取 ``HaveRunPost``。它在 ``src/misc.c`` 中定义：

.. code-block:: c

   int HaveRunPost VARFSEG;

这个变量表示 SeaBIOS 的 POST 阶段是否已经运行。它不表示 Linux 是否启动过。

同一个复位入口可能由多种情况到达：

* 机器第一次冷启动；
* 软件请求重启；
* 某些恢复路径重新进入固件；
* 固件自身触发复位。

所以 SeaBIOS 不能看见 ``reset_vector`` 就无条件再做一遍完整 POST。

当前故事跟随正常首次启动路径。此时：

::

   HaveRunPost == 0

``jnz entry_resume`` 不发生跳转，执行落到 ``ENTRY_INTO32``。

为什么使用 ``%cs:HaveRunPost``
-----------------------------

当前代码刚从复位向量跳到 ``f000:e05b``。SeaBIOS 还没有重新建立自己的数据段，``DS`` 当前指向哪里不能
作为可靠前提。

``CS`` 已经被上一章的远跳转明确装入 ``0xf000``。使用 ``%cs:`` 段覆盖前缀，CPU 会从当前固件代码段
读取 ``HaveRunPost``，不需要先依赖 ``DS``。

这里体现了早期启动代码的一个特点：每次内存访问都必须知道当前段寄存器是否已经处于可依赖状态。

ENTRY_INTO32 是汇编宏
--------------------

``ENTRY_INTO32`` 定义在 ``src/entryfuncs.S``：

.. code-block:: asm

           .macro ENTRY_INTO32 cfunc
           xorw %dx, %dx
           movw %dx, %ss
           movl $BUILD_STACK_ADDR, %esp
           movl $\cfunc, %edx
           jmp transition32
           .endm

它不是运行时调用的函数。汇编器会在构建 SeaBIOS 时，把宏中的指令直接展开到 ``entry_post`` 所在位置。

把当前参数 ``_cfunc32flat_handle_post`` 代入后，实际逻辑相当于：

.. code-block:: asm

   xorw %dx, %dx
   movw %dx, %ss
   movl $0x7000, %esp
   movl $_cfunc32flat_handle_post, %edx
   jmp transition32

这几条指令完成三件事：

#. 建立早期栈；
#. 保存最终 32 位 C 入口；
#. 跳入通用的 16 位到 32 位模式转换代码。

为什么先把 DX 清零
-----------------

第一条：

.. code-block:: asm

   xorw %dx, %dx

把 ``DX`` 变为 ``0``。随后：

.. code-block:: asm

   movw %dx, %ss

把栈段 ``SS`` 设为 ``0``。

这里使用 ``xor``，因为它不需要从内存读取常量，而且可以产生确定的零值。接下来所有早期栈地址都以线性
地址零为段基址。

为什么栈放在 0x7000
-------------------

SeaBIOS 的 ``src/config.h`` 定义：

.. code-block:: c

   #define BUILD_STACK_ADDR 0x7000

宏设置：

::

   SS  = 0x0000
   ESP = 0x00007000

当前线性栈顶是：

::

   SS.base + ESP
   = 0x00000000 + 0x00007000
   = 0x00007000

真实裸机固件通常需要先初始化内存控制器并完成 DRAM 训练，才能把普通 DRAM 当成栈使用。当前固定平台是
``QEMU q35 + SeaBIOS``：QEMU 在虚拟 CPU 开始执行前已经创建客户机 RAM，所以 SeaBIOS 可以按照平台
约定直接使用低端客户机内存 ``0x7000``。

这不表示全部内存已经完成固件层面的识别和分类。这里只能得出一个较小的结论：当前平台已经提供一块可用
低端 RAM，可以承载早期 C 调用所需的返回地址和局部变量。

为什么目标函数地址放在 EDX
-------------------------

下面的指令保存最终目标：

.. code-block:: asm

   movl $_cfunc32flat_handle_post, %edx

紧接着执行：

.. code-block:: asm

   jmp transition32

这里使用 ``jmp``，不是 ``call``。``entry_post`` 不等待模式转换代码返回。``transition32`` 完成转换后，会
直接通过 ``EDX`` 跳到目标函数。

这样，``transition32`` 可以成为通用跳板：不同入口只需要把不同的 32 位目标地址装入 ``EDX``，然后复用
同一套模式切换过程。

transition32 先阻止外部事件打断切换
---------------------------------

``transition32`` 位于 ``src/romlayout.S``：

.. code-block:: asm

   transition32:
           cli
           cld

``cli`` 清除 ``EFLAGS.IF``，暂时阻止可屏蔽硬件中断。

此时保护模式中断环境还没有建立完成。如果键盘、定时器或其他设备中断在模式切换中途进入，CPU 可能使用
不完整的 IDT，控制流会落到错误位置。

``cld`` 清除方向标志 ``DF``。清零后，``movs``、``stos`` 等字符串指令默认从低地址向高地址移动。C 编译器
通常要求函数入口处 ``DF=0``，所以 SeaBIOS 在进入 C 环境前把它设为确定状态。

cli 不能屏蔽 NMI
---------------

``cli`` 只影响可屏蔽中断。NMI，即 Non-Maskable Interrupt，不受 ``IF`` 控制。

SeaBIOS 接着操作 CMOS/RTC 索引端口：

.. code-block:: asm

           movl %eax, %ecx
           movl $CMOS_RESET_CODE|NMI_DISABLE_BIT, %eax
           outb %al, $PORT_CMOS_INDEX
           inb $PORT_CMOS_DATA, %al
           movl %ecx, %eax

对应常量是：

.. code-block:: c

   #define PORT_CMOS_INDEX  0x0070
   #define PORT_CMOS_DATA   0x0071
   #define NMI_DISABLE_BIT  0x80
   #define CMOS_RESET_CODE  0x0f

向端口 ``0x70`` 写入的最高位用于控制 NMI 屏蔽。SeaBIOS 暂时阻止 NMI，在新的执行环境稳定前，不让它把
控制流带入尚未准备好的处理路径。

代码先把 ``EAX`` 保存到 ``ECX``，完成端口访问后再恢复 ``EAX``，避免通用跳板无故破坏调用入口可能保留
的寄存器值。

A20 必须打开
-----------

接下来执行：

.. code-block:: asm

   inb $PORT_A20, %al
   orb $A20_ENABLE_BIT, %al
   outb %al, $PORT_A20

SeaBIOS 定义：

.. code-block:: c

   #define PORT_A20        0x0092
   #define A20_ENABLE_BIT  0x02

A20 是地址的第 20 位，从位 0 开始计数。它决定地址能否真正越过 1 MiB 边界。

为了兼容 8086 的 20 位地址回绕行为，早期 PC 允许关闭 A20。A20 关闭时：

::

   0x00100000

可能回绕到：

::

   0x00000000

这对某些旧软件有兼容意义，对即将使用的 32 位平坦地址空间却是错误行为。SeaBIOS 通过端口 ``0x92``
打开 A20，让低端地址和 1 MiB 以上地址真正分离。

如果不完成这一步，后面访问高于 1 MiB 的内存可能悄悄覆盖最低端的 IVT、BDA 或其他关键数据。

lidt 和 lgdt 装入的是描述符位置
-----------------------------

模式转换继续执行：

.. code-block:: asm

   transition32_nmi_off:
           lidtw %cs:pmode_IDT_info
           lgdtw %cs:rombios32_gdt_48

``lidt`` 和 ``lgdt`` 的操作数不是整张 IDT 或 GDT，而是一个描述表位置结构，其中保存：

* 表长度减一；
* 表的线性基地址。

SeaBIOS 在 ``src/misc.c`` 中定义临时保护模式 IDT：

.. code-block:: c

   u8 dummy_IDT VARFSEG;

   struct descloc_s pmode_IDT_info VARFSEG = {
       .length = sizeof(dummy_IDT) - 1,
       .addr = (u32)&dummy_IDT,
   };

这不是一张完整的中断门表。它只是一个故意极小的占位 IDT。

如果切换期间真的发生没有被屏蔽的异常或中断，CPU 无法从这张表取得正常门描述符，机器会停止，而不是
跳入一段随机代码。当前阶段追求的是可预测失败，不是正常处理中断。

GDT 建立 32 位平坦段
------------------

SeaBIOS 的 ``rombios32_gdt`` 包含多组描述符，其中前几项是：

.. code-block:: c

   u64 rombios32_gdt[] = {
       0x0000000000000000LL,
       GDT_GRANLIMIT(0xffffffff) | GDT_CODE | GDT_B,
       GDT_GRANLIMIT(0xffffffff) | GDT_DATA | GDT_B,
       /* 后面还有 16 位兼容段 */
   };

第一项是不可使用的空描述符。第二项是 32 位平坦代码段，第三项是 32 位平坦数据段。

``src/config.h`` 定义选择子：

.. code-block:: c

   #define SEG32_MODE32_CS (1 << 3)
   #define SEG32_MODE32_DS (2 << 3)

所以：

::

   代码段选择子 = 0x08
   数据段选择子 = 0x10

每个 GDT 描述符占 8 字节，选择子中的索引需要左移 3 位。低三位用于 TI 和 RPL，不属于描述符索引。

这里的“平坦”表示段基址为 ``0``，段范围覆盖整个 32 位地址空间。段寄存器仍然存在，只是地址使用方式
不再像实模式那样频繁计算 ``segment × 16 + offset``。

CR0.PE 打开保护模式
-----------------

GDT 和临时 IDT 的位置已经装入 CPU 后，SeaBIOS 修改 ``CR0``：

.. code-block:: asm

   movl %cr0, %ecx
   andl $~(CR0_PG|CR0_CD|CR0_NW), %ecx
   orl $CR0_PE, %ecx
   movl %ecx, %cr0

几个位的作用是：

``CR0.PE``
   Protection Enable。设置为 1 后启用保护模式分段规则。

``CR0.PG``
   Paging。SeaBIOS 此时没有建立页表，因此明确清零。

``CR0.CD``
   Cache Disable。清零后不再全局禁用缓存。

``CR0.NW``
   Not Write-through。这里也清零，避免继承异常缓存控制状态。

真正改变处理器模式的是：

::

   CR0.PE = 1

写入以后，CPU 已经启用保护模式规则。当前 ``CS`` 的隐藏缓存仍然保留切换前状态，模式转换还没有完成。

为什么还必须远跳转
----------------

SeaBIOS 立刻执行：

.. code-block:: asm

   ljmpl $SEG32_MODE32_CS, $(BUILD_BIOS_ADDR + 1f)

远跳转同时装入：

::

   CS  = 0x08
   EIP = BUILD_BIOS_ADDR + 局部标签 1

CPU 使用 ``0x08`` 查询 GDT，加载 32 位平坦代码段描述符。新的 ``CS`` 隐藏缓存由这项描述符重新建立。

``BUILD_BIOS_ADDR`` 是：

::

   0x000f0000

``1f`` 表示当前汇编文件中后方编号为 ``1`` 的局部标签。进入基址为零的代码段后，``EIP`` 必须是完整的
线性代码地址，因此目标要加上 BIOS 低地址基址。

源码随后出现：

.. code-block:: asm

   .code32
   1:

``.code32`` 只是告诉汇编器从这里开始使用 32 位指令编码。运行时真正改变 CPU 状态的是前面的
``CR0.PE`` 和远跳转。

数据段也要重新装载
----------------

进入局部标签 ``1`` 后，SeaBIOS 设置所有常用数据段：

.. code-block:: asm

   movl $SEG32_MODE32_DS, %ecx
   movw %cx, %ds
   movw %cx, %es
   movw %cx, %ss
   movw %cx, %fs
   movw %cx, %gs

``SEG32_MODE32_DS`` 是 ``0x10``。装载完成后：

* ``DS``、``ES`` 使用基址为零的 32 位数据段；
* ``SS`` 使用同一个平坦数据段；
* ``FS``、``GS`` 先进入相同的基础数据环境。

栈指针仍然是：

::

   ESP = 0x00007000

切换前 ``SS=0``，切换后 ``SS`` 指向基址为零的数据段，所以栈的线性位置在模式转换前后都保持
``0x7000``，没有突然移动。

最后一跳进入 handle_post
-----------------------

模式转换代码最后执行：

.. code-block:: asm

   jmpl *%edx

``EDX`` 从 ``entry_post`` 开始一直保存：

::

   _cfunc32flat_handle_post

这个链接器符号指向 ``post.c:handle_post()`` 的 32 位平坦入口。间接跳转后，CPU 第一次进入 SeaBIOS 的
主要 32 位 C 初始化代码：

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

前两章一直依靠固定位置的少量 16 位汇编。现在 SeaBIOS 已经拥有：

* 可用的早期栈；
* 32 位平坦代码段；
* 32 位平坦数据段；
* 已开启的 A20；
* 被控制住的中断状态；
* 可以直接运行编译器生成 C 代码的环境。

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

* 当前执行者：SeaBIOS ``handle_post()``；
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

下一段控制流从 ``handle_post()`` 的第一批调用继续：建立早期调试输出、检查 Xen 路径、把 BIOS 低地址
映射改成可写，然后进入真正的 POST 初始化 ``dopost()``。

资料
----

* `SeaBIOS src/romlayout.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S>`_；
* `SeaBIOS src/entryfuncs.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/entryfuncs.S>`_；
* `SeaBIOS src/config.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_；
* `SeaBIOS src/x86.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/x86.h>`_；
* `SeaBIOS src/hw/rtc.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/rtc.h>`_；
* `SeaBIOS src/misc.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/misc.c>`_；
* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS execution and code flow <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Execution_and_code_flow.md>`_；
* `SeaBIOS memory model <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Memory_Model.md>`_；
* `Intel® 64 and IA-32 Architectures Software Developer’s Manual <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_。