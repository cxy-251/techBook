第三十一章：GRUB linux 命令怎样检查并装载 Linux bzImage？
================================================================

上一章结束时，``linux.mod`` 已完成 ELF 重定位和初始化，dynamic placeholder 已被真实 ``linux`` 命令
替换。dispatcher 正要调用：

.. code-block:: c

   grub_cmd_linux(cmd, argc, args);

当前参数是：

::

   /boot/bzImage-6.12.95
   root=/dev/sda1
   ro
   console=ttyS0

本章处理的是 ``grub-core/loader/i386/linux.c`` 中的现代 ``linux`` 命令。它使用 Linux/x86 的 32 位
boot protocol 装载入口，适用于本书固定的 x86-64 Linux 6.12.95 ``bzImage``。旧的 ``linux16`` 路径
不参与当前流程。

没有设备前缀的路径仍然落到 hd0,msdos1
---------------------------------------

``grub_cmd_linux()`` 首先增加 ``linux.mod`` 的引用计数，防止 loader 已建立后模块被卸载。随后打开：

.. code-block:: c

   grub_file_open("/boot/bzImage-6.12.95",
                  GRUB_FILE_TYPE_LINUX_KERNEL);

路径没有写成 ``(hd0,msdos1)/boot/...``。``grub_file_open()`` 因此没有解析出显式 device name，
``grub_device_open(NULL)`` 会读取 environment 中的：

::

   root = hd0,msdos1

最终仍是：

::

   hd0 → BIOS drive 0x80
   msdos1 → physical LBA 2048
   ext2 module → fixed ext4 filesystem
   /boot/bzImage-6.12.95

文件内容继续经 ``biosdisk → INT 13h AH=42h → SeaBIOS AHCI`` 进入 GRUB 的文件缓冲区。

GRUB 先读取一份能覆盖 setup header 的结构
-------------------------------------------

``grub_cmd_linux()`` 不会一开始把整个内核文件读进内存。它先读取：

.. code-block:: c

   struct linux_i386_kernel_header lh;

这个 packed 结构从文件偏移 0 开始，内部用 padding 跨过早期 boot code，直到 ``0x1f1`` 后的
``setup_sects``、``boot_flag``、``HdrS``、protocol version、``loadflags``、``code32_start``、
``kernel_alignment``、``relocatable_kernel``、``pref_address`` 和 ``init_size`` 等字段。

这一步的目的不是执行 boot sector，而是把 ``bzImage`` 当作一种有明确 header contract 的容器读取。

第一道检查：0xAA55
------------------

GRUB 首先要求：

::

   boot_flag at offset 0x1fe = 0xaa55

Linux 6.12.95 的 ``arch/x86/boot/header.S`` 在该位置生成 ``0xAA55``。这个字段源自传统可启动扇区格式，
在现代 ``bzImage`` 中仍被 Linux/x86 Boot Protocol 保留。

检查失败时，GRUB 报 ``invalid magic number``，不会继续把任意文件解释成内核镜像。

第二道检查：HdrS 与 protocol 版本
--------------------------------

现代 setup header 在偏移 ``0x202`` 写入 ASCII：

::

   HdrS

按小端整数读取就是：

::

   0x53726448

当前 GRUB ``linux`` 命令还要求 protocol version 至少为 ``0x0203``，因为这条 loader 路径使用 32 位
boot protocol。Linux 6.12.95 的 ``header.S`` 写入：

::

   version = 0x020f

因此它包含 GRUB 后续会使用的 command-line size、relocatable kernel、minimum alignment、
``pref_address`` 和 ``init_size`` 等字段。

第三道检查：必须是 big kernel
-----------------------------

GRUB 检查 ``loadflags`` 中的 ``BIG_KERNEL``，Linux 源码中的名字是 ``LOADED_HIGH``。固定
``bzImage`` 设置该位，表示 protected-mode kernel 不走传统 zImage 的低地址布局。

若该位没有设置，现代 ``linux`` 命令会拒绝文件，并提示 i386-pc 用户尝试 ``linux16``。固定路径不进入
这个分支。

setup_sects 怎样决定 payload 起点
---------------------------------

``setup_sects`` 表示 boot sector 之后还有多少个 512 字节 setup sector。若该字段为 0，协议规定按 4 处理。
Linux 6.12.95 在构建时写入实际 setup 大小。

GRUB 计算：

::

   real_size     = setup_sects × 512
   payload_start = 512 + real_size
   prot_file_size = total_file_size - payload_start

这里的第一个 512 字节是 legacy boot sector，``real_size`` 是其后的 setup code。``payload_start`` 才是
protected-mode kernel 部分在文件中的起点。

文件里的 payload 与运行时所需空间不是一回事
--------------------------------------------

``prot_file_size`` 只是磁盘文件中 protected-mode 部分的字节数。Linux 6.12.95 setup header 还给出：

::

   init_size

它表示 kernel 初始化阶段需要的线性内存空间。该空间通常大于文件中的压缩 payload，因为 Linux 自带的
解压器以后要在目标区域展开真正的内核，并需要覆盖解压过程的额外安全边界。

对于 protocol ``0x020a`` 及以上，GRUB 使用 ``init_size`` 作为 relocator chunk 的容量，并将它按页对齐
记录为 ``prot_init_space``。GRUB 此时只会把 ``prot_file_size`` 字节从磁盘写入 chunk 前部，余下空间留给
Linux 自己的启动和解压代码。

GRUB 不在这里解压 bzImage
-------------------------

名称 ``bzImage`` 容易产生误解：GRUB 不是读取一个普通压缩包后替 Linux 解压。它装入的是 Linux 构建系统
生成的整体启动镜像，其中 protected-mode payload 自己包含入口代码和解压器。

本章结束时，内存中仍是 Linux 的压缩启动 payload。真正的解压发生在控制权交给 Linux 之后。

选址必须服从 kernel_alignment
------------------------------

Linux/x86 protocol 2.05 引入：

::

   kernel_alignment
   relocatable_kernel

固定 Linux 6.12.95 还提供：

::

   min_alignment
   pref_address
   init_size

GRUB 先验证 ``kernel_alignment`` 是非零的 2 的幂，再把它转换成对齐阶数。若
``relocatable_kernel`` 为 1，GRUB 优先尝试 header 中的 ``pref_address``；失败时可在 32 位可寻址范围内，
按允许的 alignment 逐步寻找其他可用地址，但不会低于 ``min_alignment`` 的要求。

因此不能仅凭“bzImage 传统加载到 1 MiB”断言本次最终 target 一定是 ``0x100000``。``code32_start`` 的
传统值确实是 ``0x100000``，现代可重定位 x86-64 镜像的实际目标还受其构建配置写入的 ``pref_address``、
``kernel_alignment``、``init_size`` 和当前内存占用共同决定。

relocator chunk 同时记录当前地址与目标地址
------------------------------------------

``allocate_pages()`` 创建 GRUB relocator，并取得一个 chunk：

::

   prot_mode_mem     = GRUB 当前写入 payload 的地址
   prot_mode_target  = 交给 Linux 前应该位于的物理目标地址

在 i386-pc 的分页关闭、平坦地址环境里，两者经常可以直接对应同一片物理内存；relocator 仍保留“当前位置”
和“最终目标”的区分，因为它还要统一处理重叠搬移、不同平台和启动前状态转换。

GRUB 怎样建立 linux_params
--------------------------

模块中有一份静态：

.. code-block:: c

   struct linux_kernel_params linux_params;

它对应 Linux ``boot_params`` 的关键布局，setup header 位于偏移 ``0x1f1``。GRUB 先把整个对象清零，再按
Linux header 中 jump 字段声明的 header 末尾，只复制镜像真正支持的 setup header 字节。

随后 GRUB 改写 loader 负责的字段：

* ``code32_start``：调整为本次 ``prot_mode_target`` 对应的实际 32 位入口；
* ``kernel_alignment``：记录最终使用的对齐；
* ``type_of_loader``：写入 GRUB 的 loader id；
* ``boot_flag``：在参数副本中清零，因为它不再作为交接时的 boot-sector magic 使用；
* ``heap_end_ptr`` 与 ``CAN_USE_HEAP``：允许 Linux setup 使用其低端 heap；
* ``ramdisk_image``、``ramdisk_size``：暂时保持 0，等待下一条 ``initrd`` 命令填写。

此时 ``linux_params`` 仍位于 GRUB 模块自己的内存中。它最终怎样与命令行、E820、EDD 等信息一起放入
Linux 可接收的位置，属于后续 ``grub_linux_boot()`` 的工作。

为什么 code32_start 要重新计算
------------------------------

镜像 header 中的 ``code32_start`` 以传统 ``GRUB_LINUX_BZIMAGE_ADDR`` 为基准描述入口。若 relocator 最终将
payload 放到其他目标地址，GRUB 使用：

::

   adjusted_code32_start
   = prot_mode_target
   + original_code32_start
   - 0x100000

这样保留入口在 payload 内的相对偏移，同时把它转换为本次实际物理目标中的入口地址。

命令行不是原样拼接 argv
-----------------------

GRUB 依据 header 的 ``cmdline_size`` 分配命令行缓冲区，至少保留 128 字节。缓冲区先写入：

::

   BOOT_IMAGE=

然后由 ``grub_create_loader_cmdline()`` 处理 argv。固定配置最终形成近似：

::

   BOOT_IMAGE=/boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0

这里还会经过 kernel-command-line verifier，而不是不加检查地复制字符串。参数中的 ``quiet``、``mem=``
和旧式 ``vga=`` 还会影响 GRUB 自己保存的 loader 状态；当前固定参数只有 ``root``、``ro`` 和
``console``，它们主要留给 Linux 解析。

现在才读取 protected-mode payload
----------------------------------

header 处理完成后，GRUB 将文件 offset 移到：

::

   (setup_sects + 1) × 512

然后执行：

.. code-block:: c

   grub_file_read(file, prot_mode_mem, prot_file_size);

这次读取可能跨越大量 ext4 extent 和磁盘扇区。数据路径仍是：

::

   ext2 file mapping
   → GRUB disk cache
   → biosdisk bounce buffer
   → SeaBIOS INT 13h
   → q35 AHCI
   → fixed boot disk

读完后，``prot_mode_mem`` 的前 ``prot_file_size`` 字节包含 Linux protected-mode payload；为
``init_size`` 预留的其余部分尚未由 Linux 解压器使用。

grub_loader_set 只登记未来的 boot 动作
--------------------------------------

读取无错误后，GRUB 执行：

.. code-block:: c

   grub_loader_set(grub_linux_boot, grub_linux_unload, 0);
   loaded = 1;

这一步把全局 loader hook 设置为 ``grub_linux_boot``，并登记失败或替换 loader 时的清理函数。它不会立即
调用 ``grub_linux_boot``，也不会跳到 ``code32_start``。

第三个参数为 0，使当前注册不带 ``NORETURN`` 标志；真正执行 ``boot`` 时仍由 Linux loader 自己完成最终
机器状态整理和不可返回的控制权转移。

内核文件随后可以关闭
--------------------

payload 已经读入 relocator chunk，setup header 已复制到 ``linux_params``，命令行也有独立缓冲区，因此
``grub_cmd_linux()`` 关闭 ``bzImage`` 文件。ext2 inode、文件对象与磁盘引用可以释放，已装载的内核数据不受
影响。

``linux.mod`` 的引用仍被 loader 持有。若后续 ``initrd`` 失败、另一个 loader 替换当前 loader，或启动流程
返回错误，``grub_linux_unload()`` 才会释放对应状态。

为什么这里还不能隐式 boot
--------------------------

``grub_menu_execute_entry()`` 的确会在 entry sourcecode 执行完毕后检查 ``grub_loader_is_loaded()``，并
隐式执行 ``boot``。当前 sourcecode 尚未结束，下一行是：

.. code-block:: cfg

   initrd /boot/initramfs-6.12.95.img

因此 ``grub_loader_set()`` 完成后，控制权先返回脚本执行器，再继续执行 ``initrd``。此刻跳转会让内核看不到
固定配置要求的 initramfs。

本章结束时的状态
----------------

::

   当前执行者          GNU GRUB 2.14 grub_cmd_linux()
   CPU 模式             32 位保护模式
   paging               off
   root                 hd0,msdos1
   kernel file          已关闭
   boot header          0xaa55 / HdrS / protocol 0x020f 已通过检查
   image type           bzImage / loaded high
   linux_params         已清零并填入 setup header 副本
   kernel command line  已建立
   relocator             已建立
   protected payload    已读入 prot_mode_mem
   protected target     由 header 对齐、pref_address 与可用内存决定
   initrd address/size  仍为 0
   loader hook          grub_linux_boot
   loader loaded        true
   initrd command       尚未执行
   boot command         尚未执行
   Linux payload        尚未解压
   Linux                尚未取得控制权

下一章从 ``grub_cmd_linux()`` 返回脚本执行器开始，执行 ``initrd`` 命令，将固定 initramfs 放到允许的高地址，
更新 ``linux_params.hdr.ramdisk_image`` 与 ``ramdisk_size``，并停在 entry sourcecode 全部执行完毕、隐式
``boot`` 即将开始的位置。

资料
----

* `GNU GRUB 2.14 grub-core/loader/i386/linux.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_
* `GNU GRUB 2.14 include/grub/i386/linux.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/linux.h>`_
* `GNU GRUB 2.14 include/grub/lib/cmdline.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/lib/cmdline.h>`_
* `Linux 6.12.95 Linux/x86 Boot Protocol <https://github.com/gregkh/linux/blob/v6.12.95/Documentation/arch/x86/boot.rst>`_
* `Linux 6.12.95 arch/x86/boot/header.S <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/boot/header.S>`_
