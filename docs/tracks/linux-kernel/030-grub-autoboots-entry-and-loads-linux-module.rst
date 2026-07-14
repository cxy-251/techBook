第三十章：GRUB 怎样自动选择菜单项并装入 linux 命令模块？
=============================================================

上一章结束时，固定 ``grub.cfg`` 已经变成一个只含一项的 menu object：

::

   timeout = 0
   default = 0
   menu->size = 1
   menu->entry_list[0].title = Linux 6.12.95

菜单项内部保存着 ``setparams``、``linux`` 和 ``initrd`` 三行源码。它们还没有执行；磁盘上的
``bzImage`` 与 initramfs 也没有打开。

``grub_normal_execute()`` 接下来看到 ``menu`` 非空，进入：

.. code-block:: c

   grub_show_menu(menu, nested, 0);

本章追踪到 ``linux.mod`` 已完成动态装载，并停在真正的 ``grub_cmd_linux()`` 即将取得控制权的位置。

为什么 timeout=0 不会先画一次菜单
----------------------------------

``grub_show_menu()`` 进入 ``show_menu()``，后者调用 ``run_menu()`` 决定应该执行哪个 entry。
``run_menu()`` 先读取：

::

   default = 0

``get_entry_number()`` 将字符串 ``0`` 转换为整数索引 0。当前菜单大小为 1，因此该索引合法；若变量缺失、
格式错误或超出范围，代码才会退回第一个 entry。

随后 ``grub_menu_get_timeout()`` 读到：

::

   timeout = 0

源码对此有一条专门的快速路径：

.. code-block:: c

   if (timeout == 0)
     {
       *auto_boot = 1;
       return default_entry;
     }

这条路径发生在普通菜单界面初始化之前。因此固定流程不会先画出完整菜单再立即擦除，而是直接返回索引 0。
用户没有机会在这条路径上按方向键更换启动项。

自动启动与手动回车共用同一个执行入口
------------------------------------

``show_menu()`` 用索引 0 取得 ``grub_menu_entry``。由于这是 timeout 导致的自动选择，它调用：

::

   grub_menu_execute_with_fallback(menu, entry, autobooted, ...)
   → grub_menu_execute_entry(entry, auto_boot = 1)

手动按回车最终也会进入 ``grub_menu_execute_entry()``。两条路径的区别主要在提示信息和 fallback 处理，
菜单项 body 的执行机制相同。

当前固定配置没有 ``fallback`` 列表，也只有一个 entry。本章不经过第二个候选项。

执行前先建立 chosen
-------------------

``grub_menu_execute_entry()`` 先检查菜单项认证。当前固定配置没有定义用户数据库，执行继续。

随后它根据 entry id 构造并导出：

::

   chosen = Linux 6.12.95

若当前处于嵌套 submenu，``chosen`` 会使用 ``>`` 拼接各级 id，并对 id 内原有的 ``>`` 做转义。当前是顶层
单一菜单项，因此字符串就是 entry id 本身。

代码还会检查 ``default`` 中是否包含下一层 submenu 选择。当前 ``default=0`` 没有 ``>``，因此进入 entry
前会暂时取消 ``default``。菜单项执行完成或失败并返回后，旧值才会恢复。

sourcecode 在新的参数作用域中重新解析
-------------------------------------

菜单项不是调用上一章遗留的临时语法树，而是执行保存的文本：

.. code-block:: c

   grub_script_execute_new_scope(entry->sourcecode,
                                 entry->argc,
                                 entry->args);

新的 scope 让 ``$1``、``$2`` 等位置参数只属于当前 entry。保存的第一行是：

.. code-block:: cfg

   setparams 'Linux 6.12.95'

``setparams`` 将菜单项参数复制为当前脚本的位置参数。随后脚本读取第二行：

.. code-block:: cfg

   linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0

此刻才第一次真正执行名为 ``linux`` 的命令。

为什么 command.lst 不是模块本身
-------------------------------

进入 normal mode 时，上一批章节已经读过：

::

   (hd0,msdos1)/boot/grub/i386-pc/command.lst

这个文件提供“命令名由哪个模块实现”的索引。它不包含 ``grub_cmd_linux()`` 的机器码，也不会把所有模块
预先装入内存。对于当前尚未加载的 ``linux``，normal 注册的是一个 dynamic command placeholder：

::

   command name = linux
   module name  = linux
   flags        = DYNCMD | EXTCMD | BLOCKS
   callback     = grub_dyncmd_dispatcher

因此 ``grub_command_find("linux")`` 能找到命令对象，却找到的是占位命令。这样配置文件可以直接写
``linux``，无需显式先写 ``insmod linux``。

占位命令怎样变成真正命令
------------------------

脚本执行器展开参数后调用占位命令的 dispatcher。``grub_dyncmd_dispatcher()`` 取出保存的模块名并执行：

.. code-block:: c

   grub_dl_load("linux");

``grub_dl_load()`` 先检查模块是否已经存在于 GRUB module list。当前没有，于是它使用 ``prefix`` 构造：

::

   (hd0,msdos1)/boot/grub/i386-pc/linux.mod

其中：

::

   prefix        = (hd0,msdos1)/boot/grub
   GRUB_TARGET_CPU = i386
   GRUB_PLATFORM   = pc

这个路径再次经过 ``grub_file_open() → biosdisk → part_msdos → ext2``。底层仍通过 SeaBIOS
``INT 13h`` 和 q35 AHCI 磁盘读入文件，只是读取对象从配置文件变成了一个 GRUB ELF relocatable module。

模块文件为什么先完整读入 heap
----------------------------

``grub_dl_load_file()`` 不会边读边重定位。它先取得文件大小，在 GRUB heap 分配同等大小的临时缓冲区，
将 ``linux.mod`` 全部读入，然后关闭文件。

关闭文件后再处理依赖有实际意义：某些磁盘 backend 无法安全处理同一设备上的嵌套 open。先释放 ext2、
partition 和 biosdisk 打开状态，再根据 ELF 依赖装载其他模块，可以避免递归打开造成冲突。

ELF 模块怎样接入正在运行的 GRUB
-------------------------------

``grub_dl_load_core()`` 把临时缓冲区当作 ELF ``ET_REL`` 模块处理。主流程依次完成：

#. 检查 ELF header 与 section 边界；
#. 读取模块名和许可证信息；
#. 解析依赖；
#. 为 allocatable sections 分配运行内存；
#. 解析 GRUB 导出符号；
#. 执行体系结构重定位；
#. 刷新必要的指令缓存；
#. 把新模块加入全局 module list；
#. 调用模块 init 函数。

临时的文件镜像随后释放，真正长期存在的是已分配、已重定位的 section 和 ``grub_dl`` 元数据。

linux.mod 注册了两个真实命令
----------------------------

当前 i386-pc 的现代 Linux loader 来自：

::

   grub-core/loader/i386/linux.c

它的 ``GRUB_MOD_INIT(linux)`` 注册：

::

   linux  → grub_cmd_linux
   initrd → grub_cmd_initrd

这里不要与 ``grub-core/loader/i386/pc/linux.c`` 中的 ``linux16``、``initrd16`` 混淆。固定配置使用
``linux``，走的是 Linux/x86 32 位 boot protocol 入口；它以后可以启动 64 位 Linux 内核，因为此处的
“32 位”描述的是 boot protocol 交接入口，不代表最终内核只能运行在 32 位模式。

占位命令必须先删除再重新查找
----------------------------

模块 init 完成后，命令表中一度同时涉及旧占位对象和新真实对象。dispatcher 保存原命令名，注销旧
placeholder，再调用：

.. code-block:: c

   cmd = grub_command_find("linux");

此时返回的是 ``linux.mod`` 刚注册的真实 command。dispatcher 保留原来已经展开好的参数：

::

   argv[0] = /boot/bzImage-6.12.95
   argv[1] = root=/dev/sda1
   argv[2] = ro
   argv[3] = console=ttyS0

下一条实际调用是：

.. code-block:: c

   ret = cmd->func(cmd, argc, args);

其中 ``cmd->func`` 已经等于 ``grub_cmd_linux``。本章在该调用执行前停止。

本章结束时的状态
----------------

::

   当前执行者       GNU GRUB 2.14 dynamic command dispatcher
   CPU 模式          32 位保护模式
   paging            off
   selected entry    Linux 6.12.95
   chosen             Linux 6.12.95
   entry scope        已建立
   setparams          已执行
   linux placeholder  已注销
   linux.mod          已从 ext4 读取、重定位并初始化
   real linux command 已注册
   initrd command     已注册
   linux argv         已展开
   grub_cmd_linux     尚未调用
   bzImage            尚未打开
   initramfs          尚未打开
   Linux              尚未取得控制权

下一章从 ``grub_cmd_linux()`` 开始，打开 ``/boot/bzImage-6.12.95``，检查 Linux/x86 setup header，
分配 relocator-backed 内存并装入 protected-mode kernel payload。章节停在 ``grub_loader_set()`` 完成后，
尚不执行下一行 ``initrd``，也不把控制权交给 Linux。

资料
----

* `GNU GRUB 2.14 grub-core/normal/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/main.c>`_
* `GNU GRUB 2.14 grub-core/normal/menu.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/menu.c>`_
* `GNU GRUB 2.14 grub-core/normal/dyncmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/dyncmd.c>`_
* `GNU GRUB 2.14 grub-core/script/execute.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/execute.c>`_
* `GNU GRUB 2.14 grub-core/kern/dl.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c>`_
* `GNU GRUB 2.14 grub-core/loader/i386/linux.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_
