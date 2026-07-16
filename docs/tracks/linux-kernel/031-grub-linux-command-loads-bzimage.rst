第三十一章：GRUB linux命令怎样验证并装入固定bzImage？
=======================================================

第030章停在dynamic command已经被替换后的精确边界。CPU0上的BSP仍在GNU GRUB 2.14
32位flat保护模式中，paging关闭、A20开启、IF=0、DF=0；``linux.mod`` 已完成重定位和
初始化，``grub_dyncmd_dispatcher`` 已经重新找到真正的command对象，下一调用是：

::

   grub_cmd_linux(cmd, 4, args)

   args[0] = /boot/bzImage
   args[1] = root=/dev/sda1
   args[2] = ro
   args[3] = console=ttyS0

``/boot/bzImage`` 是本书镜像约定中的Linux 7.2-rc1构建结果，对应
gregkh/linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``。本章沿
``grub-core/loader/i386/linux.c:grub_cmd_linux`` 的成功路径前进，停在kernel file已经
关闭、loader hook已经登记、脚本即将执行下一条 ``initrd`` 命令的位置。

本章固定哪些值、保留哪些运行时量
--------------------------------

固定Linux源码无条件写入setup header的值包括：

::

   boot_flag       = 0xaa55
   header          = "HdrS"
   version         = 0x020f
   loadflags       contains LOADED_HIGH
   code32_start    = 0x00100000
   initrd_addr_max = 0x7fffffff
   cmdline_size    = 2047

另一些字段不能只凭commit写成数字：

* ``setup_sects`` 由最终setup输出大小决定；
* ``kernel_alignment`` 来自 ``CONFIG_PHYSICAL_ALIGN``；
* ``relocatable_kernel`` 来自 ``CONFIG_RELOCATABLE``；
* ``pref_address`` 由 ``CONFIG_PHYSICAL_START`` 与alignment共同决定；
* ``init_size`` 由最终compressed image、解压安全余量和vmlinux大小共同决定；
* 文件总长度、protected payload长度和最终relocator地址来自实际artifact与运行时memory map。

后文用符号保存这些真实关系：

::

   S = setup_sects的有效值；header为0时按4
   F = /boot/bzImage的实际文件长度
   P = F - 512 - S * 512
   I = header.init_size
   K = prot_mode_target

``P`` 是实际读入的protected-mode文件字节数，``I`` 是Linux初始化阶段要求的连续空间；
两者不是同一个量。当前成功叙事只要求artifact合法且地址分配成功，不制造缺失的构建数字。

模块引用先于文件打开
--------------------

``grub_cmd_linux`` 一进入就执行：

.. code-block:: c

   grub_dl_ref(my_mod);

第030章的dynamic dispatcher已经为 ``linux.mod`` 留下一份autoload引用；这里再增加一份，
让已经登记的Linux loader在以后被执行或卸载以前继续持有模块代码及其dependency closure。
成功返回时这份新引用不会在函数尾部释放。

随后：

.. code-block:: c

   grub_file_open("/boot/bzImage", GRUB_FILE_TYPE_LINUX_KERNEL);

路径没有显式device，``grub_device_open(NULL)`` 使用当前：

::

   root = hd0,msdos1

于是文件读取仍沿：

::

   ext2 driver读取固定ext4
   → msdos1，whole-disk start LBA 2048
   → biosdisk hd0 / BIOS drive 0x80
   → SeaBIOS INT 13h extensions
   → q35 ICH9 AHCI SATA port 0

具体inode、extent、文件data LBA与cache命中次数由磁盘artifact决定，本章不把它们写成源码
常量。打开期间file拥有device/fs data；关闭后这些对象可以释放，GRUB全局disk cache仍可保留
已经读过的block。

GRUB只先读固定大小的头部结构
----------------------------

文件打开后，GRUB从offset 0读取：

.. code-block:: c

   struct linux_i386_kernel_header lh;

这个packed结构跨过legacy boot code，覆盖从 ``setup_sects`` 到现代setup header的关键字段。
此时GRUB是在解析bzImage容器，不执行boot sector或16位setup code。

校验顺序首先是：

#. ``boot_flag == 0xaa55``，否则报 ``invalid magic number``；
#. ``setup_sects <= 64``，否则报setup sector过多；
#. offset ``0x202`` 为 ``HdrS`` 且protocol至少 ``0x0203``；
#. ``loadflags`` 含 ``BIG_KERNEL/LOADED_HIGH``，否则当前PC BIOS路径提示尝试
   ``linux16``。

固定7.2-rc1源码生成 ``0x020f`` 协议头并设置 ``LOADED_HIGH``，所以成功路径通过四道
检查。``linux16``、zImage和16位setup执行路径均不发生。

命令行容量为什么恰好是2048字节
------------------------------

protocol不低于2.06时，GRUB读取：

.. code-block:: c

   maximal_cmdline_size = le32(lh.cmdline_size) + 1;

固定x86源码把 ``COMMAND_LINE_SIZE - 1`` 写入header，而
``COMMAND_LINE_SIZE=2048``，所以本次得到：

::

   maximal_cmdline_size = 2048

GRUB还会把异常的小值提高到128；当前不触发这个兼容分支。这里的2048来自固定源码中不依赖
``.config`` 的x86 command-line常量，可以明确写出；它不同于最终command-line字符串的实际
长度。

setup sector怎样划开文件
------------------------

GRUB取得header中的原始 ``setup_sects``。若为0，协议规定有效值为4；否则使用artifact给出的
值 ``S``。接着计算：

::

   real_size      = S * 512
   payload_offset = 512 + real_size
   prot_file_size = F - payload_offset = P

第一个512字节是legacy boot sector，随后 ``S`` 个sector是setup，protected-mode payload从
``(S + 1) * 512`` 开始。固定成功条件保证文件完整，``P`` 足以覆盖后续读取；本章不根据源码树
猜测 ``S``、``F`` 或 ``P``。

alignment判断先于relocator分配
-----------------------------

protocol至少2.05、``kernel_alignment`` 非零且为2的幂时，GRUB把它转换成alignment阶数，并从
header读取 ``relocatable_kernel``。否则它把镜像当作不可重定位，回到传统1 MiB目标。

固定protocol又高于2.10，所以当前分支读取：

::

   min_align        = lh.min_alignment
   prot_size        = I
   prot_init_space  = PAGE_ALIGN(I)
   preferred_address = lh.pref_address，若镜像可重定位

对x86-64构建，``min_alignment`` 由 ``MIN_KERNEL_ALIGN_LG2=PMD_SHIFT`` 生成；但首选alignment、
preferred address和是否可重定位仍由构建配置写入实际header。GRUB以读出的值为准。

allocate_pages先撤销旧relocator
------------------------------

``allocate_pages`` 先把 ``prot_size`` 按4 KiB对齐，然后调用：

.. code-block:: c

   free_pages();
   relocator = grub_relocator_new();

本场景此前没有Linux loader，旧 ``relocator=NULL``，所以第一次 ``free_pages`` 没有chunk可撤销。
随后分配protected chunk。

若镜像可重定位，GRUB先尝试header给出的精确preferred address；若那里不可用，再从16 MiB到
32位上限以内按header alignment搜索，并按实现允许的阶数逐步放宽但不越过
minimum-alignment target边界。若镜像不可重定位，只能申请传统preferred address。成功后保存：

::

   prot_mode_mem    = chunk的current address
   K                = chunk的physical target

current address是GRUB现在写payload的位置，target是relocation trampoline完成后Linux真正执行的
物理位置。接口允许两者不同；即使某次分配恰好相同，正文也不能抹掉这层所有权。

init_size空间不等于已经读入init_size字节
-----------------------------------------

relocator chunk按 ``I`` 取得足够空间，是因为compressed startup、解压输出和搬移过程需要整个
初始化窗口。GRUB稍后只从文件读取 ``P`` 字节：

::

   [prot_mode_mem, prot_mode_mem + P)       = bzImage protected payload
   [prot_mode_mem + P, prot_mode_mem + I)   = 为Linux初始化保留的容量

后一区间不是第二份kernel，也不能声称已经由GRUB解压或填零。bzImage内的Linux解压器在取得控制权
之后才使用这片布局。

linux_params先清零再复制有效header
---------------------------------

protected chunk分配成功后，GRUB清零模块内的静态：

.. code-block:: c

   struct linux_kernel_params linux_params;

setup header的有效末端不是用C结构大小猜测，而按boot protocol从jump第二字节计算：

::

   header_end = 0x202 + byte_at_0x201

GRUB先确认这个末端没有越过 ``linux_params.edd_mbr_sig_buffer``，再把从offset ``0x1f1``
开始的有效header复制到zeroed参数模板；若固定头部结构尚未覆盖全部有效header，就从当前file
位置继续读取剩余字节。

这个顺序保证：

* kernel声明的字段被保留；
* 不存在的尾字段仍为0；
* 恶意header不能借长度越界覆盖参数对象后部。

loader字段怎样覆盖kernel原值
----------------------------

复制完成后，GRUB写回由bootloader负责的字段：

.. code-block:: c

   linux_params.hdr.code32_start =
       K + lh.code32_start - 0x00100000;
   linux_params.hdr.kernel_alignment = 1U << align;
   linux_params.hdr.boot_flag = 0;
   linux_params.hdr.type_of_loader = 0x72;
   linux_params.hdr.ramdisk_image = 0;
   linux_params.hdr.ramdisk_size = 0;
   linux_params.hdr.heap_end_ptr = 0x8e00;
   linux_params.hdr.loadflags |= CAN_USE_HEAP;

固定Linux header原始 ``code32_start`` 正是 ``0x00100000``，所以本次关系可进一步化简为：

::

   adjusted code32_start = K

这个结论不要求把 ``K`` 猜成1 MiB。它只说明protected payload offset 0处的
``startup_32`` 将在实际target起点执行。

``boot_flag`` 在artifact校验时必须是 ``0xaa55``，但参数副本随后被GRUB清零；不要把“文件头
通过magic检查”和“交接zero page中的字段值”写成同一个时刻。ramdisk字段仍为0，因为
``initrd`` 尚未运行。

当前参数没有触发GRUB特殊分支
----------------------------

GRUB把file cursor移到 ``payload_offset``，随后扫描 ``args[1..3]``：

* 没有 ``vga=``，不改 ``gfxpayload``；
* 没有 ``mem=``，所以 ``linux_mem_size=0``；
* 没有 ``quiet``，不额外设置loader quiet flag。

然后它为command line分配zeroed buffer，先写 ``BOOT_IMAGE=``，再由
``grub_create_loader_cmdline`` 逐个转义并拼接全部四个argv。当前参数不含空格、引号或反斜杠，
结果精确为：

::

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

该字符串还通过 ``GRUB_VERIFY_KERNEL_CMDLINE`` verifier链。``BOOT_IMAGE`` 部分不是用户
command line里额外写的一项；它由GRUB loader主动加上。

现在才读取protected payload
---------------------------

GRUB执行：

.. code-block:: c

   grub_file_read(file, prot_mode_mem, P);

读取成功后，relocator protected chunk前 ``P`` 字节持有固定bzImage的protected-mode部分。
这仍然是包含 ``startup_32``、compressed kernel和解压器的构建产物，不是已解压的vmlinux。

文件读取可能多次进入ext4、biosdisk和SeaBIOS AHCI路径；实际I/O次数受extent与GRUB cache影响。
本章只固定“全部 ``P`` 字节成功进入chunk”这一完成边界。

grub_loader_set只发布未来动作
-----------------------------

``grub_errno`` 仍为0时：

.. code-block:: c

   grub_loader_set(grub_linux_boot, grub_linux_unload, 0);
   loaded = 1;

当前没有旧loader，``grub_loader_set_ex`` 不需要调用旧unload hook；它把simple boot/unload
wrapper、context和flags发布到全局loader状态，再写入 ``grub_linux_boot`` 与
``grub_linux_unload``。

flags为0的直接含义是以后 ``grub_machine_fini`` 不因 ``NORETURN`` 关闭console。这里既不执行
``grub_linux_boot``，也不搬relocator chunk，更不进入Linux。

``grub_linux_unload`` 这个名字也不能扩写成“释放全部Linux装载状态”。固定实现只撤销本次
loader持有的module ref、清 ``loaded`` 并释放 ``linux_cmdline``；它没有调用
``free_pages``。当前成功路径将直接handoff而不运行unload，但对象生命期说明必须以函数实际
内容为准。

成功路径最后关闭kernel file
----------------------------

函数统一经过 ``fail:`` 标签关闭非NULL file；标签名不表示当前一定失败。成功路径因此也执行：

.. code-block:: c

   grub_file_close(file);

file、ext4 per-open data、device和disk引用到此释放。payload、``linux_params``、command-line
buffer和relocator不依赖已关闭file。``grub_cmd_linux`` 返回0，dynamic dispatcher再返回脚本
执行器；菜单项还有下一条 ``initrd /boot/initramfs.img``，所以此刻不会隐式boot。

失败回滚不能写成“全部恢复”
--------------------------

固定实现的失败出口只保证：

* 关闭已经打开的kernel file；
* ``grub_dl_unref(my_mod)`` 撤销本次command取得的模块引用；
* 把 ``loaded`` 写回0。

若失败发生在 ``allocate_pages`` 内部，该函数会调用 ``free_pages`` 撤销刚建的relocator。但若
protected chunk已经成功、随后header尾读取、command-line分配/验证或payload读取失败，公共
``fail:`` 并不再次调用 ``free_pages``，也不统一释放新command-line buffer。因此这份固定源码
不是“任意失败点都完整回滚”的实现。本章成功路径不触发该缺口，但正文必须区分已证明的file/ref
回滚与没有发生的全状态回滚。

本章结束状态
------------

* current executor：CPU0 BSP上的GNU GRUB 2.14菜单脚本执行器；
* CPU mode：32位flat protected mode，paging off，A20 on，IF=0、DF=0；
* ``root=hd0,msdos1``，``prefix=(hd0,msdos1)/boot/grub``；
* fixed kernel identity：Linux 7.2-rc1，commit
  ``7404ce51637231382873d0b55edabc2f3b841a9d``；
* kernel file：已完整读取并关闭；当前无file/device/fs/disk object，disk cache可保留block；
* header checks：``0xaa55``、``HdrS``、``0x020f``、``LOADED_HIGH`` 已通过；
* ``S``、``F``、``P``、``I``：来自实际artifact，不伪造数值；
* protected chunk：current address为 ``prot_mode_mem``，target为 ``K``；
* protected bytes：前 ``P`` 字节已装入，尚未解压；
* ``prot_init_space=PAGE_ALIGN(I)``；
* ``linux_params``：zeroed后复制有效header并由GRUB改写loader字段；
* adjusted ``code32_start=K``；
* command line：``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``；
* ``linux_mem_size=0``；
* ``ramdisk_image=0``、``ramdisk_size=0``；
* loader hook：``grub_linux_boot``；
* loader unload hook：``grub_linux_unload``；
* loader flags：0；``grub_loader_loaded=1``，module-local ``loaded=1``；
* ``linux.mod``：autoload引用与本次loader引用仍在；
* entry sourcecode：尚未结束；
* Linux：尚未取得控制权。

关键边界
--------

#. 固定commit能证明protocol头的源码常量，不能代替最终 ``.config``、链接输出和运行时memory map。
#. ``P`` 是从文件读取的protected payload长度；``I`` 是初始化窗口，不能互换。
#. relocator的current address与physical target是两个地址身份。
#. fixed header原始 ``code32_start=1 MiB``，所以GRUB调整后入口精确等于 ``K``，但
   ``K`` 本身仍由header和运行时分配决定。
#. ``boot_flag`` 先用于验证artifact，随后在 ``linux_params`` 副本中清零。
#. command line包含GRUB添加的 ``BOOT_IMAGE=/boot/bzImage``。
#. ``grub_loader_set`` 只登记hook；菜单项后续还有 ``initrd``，不会提前启动Linux。
#. 成功关闭kernel file不会释放relocator、参数模板、command line或loader module引用。
#. ``grub_linux_unload`` 本身也不调用 ``free_pages``，不能称为完整relocator destructor。
#. 固定失败出口不是完整事务回滚；正文不得声称所有后分配对象都在失败时释放。

下一入口
--------

下一章从同一entry scope中的第二条命令开始：

::

   initrd /boot/initramfs.img
   → grub_cmd_initrd(cmd, 1, argv)
   → verify module-local loaded == 1
   → grub_initrd_init

它将读取initramfs的真实大小，以 ``K + PAGE_ALIGN(I)`` 为最低target边界，在GRUB的i386
initrd上界以内取得4 KiB对齐chunk，并在成功复制后填写 ``ramdisk_image`` 与
``ramdisk_size``。

资料
----

* `GRUB固定提交：i386 grub_cmd_linux、allocate_pages与loader登记 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_；
* `GRUB固定提交：Linux header与loader常量 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/linux.h>`_；
* `GRUB固定提交：kernel command-line构造 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/cmdline.c>`_；
* `GRUB固定提交：dynamic command模块引用与真实command调用 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/dyncmd.c>`_；
* `Linux 7.2-rc1固定提交：x86 setup header生成 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/header.S>`_；
* `Linux 7.2-rc1固定提交：Linux/x86 Boot Protocol <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_；
* `Linux 7.2-rc1固定提交：x86 command-line容量 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/setup.h>`_；
* `Linux 7.2-rc1固定提交：x86 minimum alignment <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/boot.h>`_。
