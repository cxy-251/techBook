第二十九章：GRUB 怎样解析 grub.cfg 并建立第一个 Linux 菜单项？
================================================================

上一章结束时，``grub.cfg`` 已经通过 ``biosdisk → part_msdos → ext2`` 打开，外面套上了
``bufio``，第一条不以 ``#`` 开头的配置行也已经读入内存。控制流停在：

.. code-block:: c

   grub_normal_parse_line(line, read_config_file_getline, file);

这里的“解析配置文件”并不是把整个文件一次性读成一棵永久语法树。GRUB normal 以当前行作为入口；
当语法尚未闭合时，解析器再通过 ``read_config_file_getline`` 继续索取后续行。解析出一个完整脚本单元后，
它立即执行；执行结果可能只是设置环境变量，也可能把一段尚未运行的启动脚本保存成菜单项。

本书固定的 grub.cfg
--------------------

从本章开始，固定磁盘中的 ``/boot/grub/grub.cfg`` 使用下面这份最小配置：

.. code-block:: cfg

   set timeout=0
   set default=0

   menuentry 'Linux 6.12.95' {
       linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs-6.12.95.img
   }

这不是发行版自动生成配置的缩写，而是本书为了固定唯一控制流而采用的完整配置。它规定：

* 菜单等待时间为零；
* 默认选择第零项，也就是第一项；
* 内核文件位于同一 ext4 分区的 ``/boot/bzImage-6.12.95``；
* 内核命令行使用 ``/dev/sda1`` 作为根文件系统，并打开串口控制台；
* initramfs 位于 ``/boot/initramfs-6.12.95.img``。

本章只解释这份配置怎样变成一个 ``grub_menu_entry``。花括号中的 ``linux`` 和 ``initrd`` 还不会执行，
磁盘上的两个文件也不会在本章被读取。

grub_normal_parse_line 会先解析再执行
--------------------------------------

``grub-core/script/main.c`` 中的 ``grub_normal_parse_line()`` 主体非常短：

.. code-block:: c

   parsed_script = grub_script_parse(line, getline, getline_data);
   if (parsed_script)
     {
       grub_script_execute(parsed_script);
       grub_script_unref(parsed_script);
     }

这三步不能合并理解：

#. ``grub_script_parse`` 把文本变成 GRUB 脚本对象；
#. ``grub_script_execute`` 执行这个刚构造的对象；
#. 执行结束后，当前顶层脚本对象解除引用。

菜单项之所以能在第三步之后继续存在，是因为 ``menuentry`` 命令会把标题、参数和花括号中的源码复制到
``grub_menu_entry``，并挂入前一章创建的 menu object。保存下来的不是当前临时解析对象本身。

词法分析器与 Bison 语法分别做什么
---------------------------------

GRUB 的脚本语法由 ``grub-core/script/parser.y`` 描述。词法分析器先把输入拆成 ``NAME``、``WORD``、
换行、分号、左右花括号等 token；Bison 生成的语法分析器再把 token 组合为 command、statement、block
和 script。

普通命令行的核心规则可以概括为：

::

   command name
   + zero or more arguments
   + optional { block }
   → grub_script_cmdline

花括号块的处理更特殊。解析器在看见 ``{`` 时开始记录原始字符位置和临时内存；随后解析块内命令，直到
遇到配对的 ``}``。结束时它同时得到：

* 一份预解析的子脚本对象；
* 一份去掉最外层花括号的原始源码字符串。

``menuentry`` 需要长期保存启动项，所以两种表示都很重要。预解析对象帮助当前命令处理 block 参数；原始
源码字符串则会被复制到菜单项中，等用户真正选择该项时重新建立作用域并执行。

为什么解析器能跨越多行
----------------------

``read_config_file()`` 表面上每次只给 ``grub_normal_parse_line()`` 一行。读取到：

.. code-block:: cfg

   menuentry 'Linux 6.12.95' {

时，右花括号尚未出现，语法单元不完整。解析器不会把这一行当成错误立即结束，而是调用传入的
``read_config_file_getline`` 回调继续取得：

.. code-block:: cfg

       linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs-6.12.95.img
   }

直到花括号闭合，它才返回一个完整的顶层 ``menuentry`` 命令对象。换行因此既是文件读取边界，也是脚本
语法中的 delimiter；花括号决定这个命令需要跨越多少个读取边界。

前两行只是立即执行 set
----------------------

第一条有效配置行是：

.. code-block:: cfg

   set timeout=0

解析器将它构造成命令名 ``set`` 和参数 ``timeout=0``。``set`` 不是从磁盘临时加载的模块命令，
而是 ``grub_register_core_commands()`` 注册的核心命令。它在参数中寻找 ``=``，临时把字符串切成变量名
和变量值，然后调用：

.. code-block:: c

   grub_env_set("timeout", "0");

下一行同理建立：

::

   default = 0

这两个值此时只进入 GRUB environment。菜单选择逻辑尚未运行，``0`` 还没有被解释成“立即启动第一项”。

menuentry 命令已经属于 normal 模块
----------------------------------

需要区分 ``menuentry`` 与后面将出现的 ``linux``：

* ``menuentry`` 在 normal 模块初始化时由 ``grub_menu_init()`` 注册；
* ``linux`` 在当前固定 core.img 中没有预装，稍后依赖 ``command.lst`` 动态加载 ``linux.mod``。

因此解析到 ``menuentry`` 时，``grub_command_find("menuentry")`` 能直接找到一个带
``GRUB_COMMAND_FLAG_BLOCKS`` 的 extended command，无需先读 ``menuentry.mod``。

脚本执行器先展开参数
--------------------

``grub_script_execute_cmdline()`` 先把解析器保留的 argument list 转成 ``argv``。在本例中，命令可概括为：

::

   argv[0] = menuentry
   argv[1] = Linux 6.12.95
   argv[2] = { ...block source... }

单引号已经在词法阶段用于保持空格，不会作为标题内容保留下来。block 参数还携带预解析脚本指针，所以
执行器发现该命令同时具有 ``BLOCKS`` 与 ``EXTCMD`` 标志后，会调用 extended-command dispatcher，
把普通参数、选项状态和 block script 一起交给 ``grub_cmd_menuentry()``。

菜单项保存的不是正在运行的 linux 命令
--------------------------------------

``grub_cmd_menuentry()`` 不会进入花括号执行 ``linux``。它先生成一段参数前缀：

.. code-block:: cfg

   setparams 'Linux 6.12.95'

随后把这段前缀与 block 原始源码拼接，形成菜单项的 ``sourcecode``。固定菜单项中保存的内容近似为：

.. code-block:: cfg

   setparams 'Linux 6.12.95'
   linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
   initrd /boot/initramfs-6.12.95.img

``setparams`` 让将来的菜单项执行拥有独立的位置参数作用域。即使标题或附加参数中包含空格、引号，进入
菜单项时仍能恢复成正确的 ``$1``、``$2`` 等参数。

grub_normal_add_menu_entry 建立长期对象
---------------------------------------

``grub_normal_add_menu_entry()`` 首先通过 environment 的 menu data slot 取得前一章创建的
``grub_menu``。随后逐项复制需要跨越当前解析生命周期的数据：

::

   title      = "Linux 6.12.95"
   id         = "Linux 6.12.95"
   argc/args  = 菜单项参数副本
   sourcecode = setparams 前缀 + block 源码副本
   submenu    = 0
   restricted = 1
   users      = ""

本例没有 ``--id``，因此 id 默认复制标题；没有 ``--class``、``--hotkey`` 和明确用户列表，对应字段保持
空值或默认值。默认的空 users 字符串使该项遵循 normal 的认证规则；当前固定环境没有配置认证用户，后续
执行不会因此产生交互。

新对象被接到 ``menu->entry_list`` 尾部，然后：

.. code-block:: c

   menu->size++;

从这一条加法完成开始，menu object 才真正拥有第一个启动项。

为什么 block 现在必须保持为文本
-------------------------------

配置解析完成后，``read_config_file()`` 会继续处理剩余行、关闭配置文件并返回 menu object。当前顶层解析
产生的临时脚本对象已经释放；若菜单项只保存其中的裸指针，后面选择菜单时会访问失效内存。

保存源码还有另一个作用：用户可以编辑菜单项、进入子菜单，或者以新的 environment context 执行同一项。
GRUB 在真正启动时重新解析 ``entry->sourcecode``，让变量展开、命令自动加载和当时的 environment 状态
共同决定执行结果。

本章结束时的状态
----------------

::

   当前执行者       GNU GRUB 2.14 normal mode
   CPU 模式          32 位保护模式
   paging            off
   timeout            0
   default            0
   menu->size         1
   first entry title  Linux 6.12.95
   first entry id     Linux 6.12.95
   entry sourcecode   setparams + linux + initrd
   linux command      尚未执行
   linux.mod          尚未动态加载
   bzImage            尚未打开
   initramfs          尚未打开
   Linux              尚未取得控制权

配置读取循环随后到达文件末尾，关闭 bufio 和底层 ``grub.cfg``，并把已经含有一个启动项的 menu object
返回给 ``grub_normal_execute()``。下一章从：

.. code-block:: c

   if (menu && menu->size)
       grub_show_menu(menu, nested, 0);

开始，追踪 ``timeout=0`` 怎样跳过菜单绘制、选择第零项，并进入该项保存的 ``sourcecode``。

资料
----

* `GNU GRUB 2.14 grub-core/normal/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/main.c>`_
* `GNU GRUB 2.14 grub-core/script/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/main.c>`_
* `GNU GRUB 2.14 grub-core/script/parser.y <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/parser.y>`_
* `GNU GRUB 2.14 grub-core/script/execute.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/execute.c>`_
* `GNU GRUB 2.14 grub-core/commands/menuentry.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/commands/menuentry.c>`_
* `GNU GRUB 2.14 grub-core/kern/corecmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/corecmd.c>`_
