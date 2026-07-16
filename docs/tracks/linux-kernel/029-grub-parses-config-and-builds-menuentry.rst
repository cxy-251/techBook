第二十九章：GRUB 怎样解析 grub.cfg 并建立 Linux 菜单项？
===========================================================

上一章停止在 ``read_config_file()`` 的循环中。CPU0 上的 BSP 仍以 32 位保护模式运行 GRUB，
paging 关闭，``IF=0``、``DF=0``。``grub.cfg`` 的 bufio wrapper 和底层 ext4 file/device/disk
对象仍然打开，第一条可解析行已经进入 heap；menu data slot 则只含一个空容器：

::

   menu->entry_list = NULL
   menu->size       = 0

当前下一条调用是 ``grub_normal_parse_line()``。本章追踪配置解析与即时执行，直到文件到达 EOF、
配置文件对象全部关闭、menu 返回给 ``grub_normal_execute()``；终点在 ``grub_show_menu()`` 的条件
判断之前。这个边界保证本章只建表，不执行菜单项 body。

本书固定的是磁盘内容，不是 GRUB 或 Linux 源码默认值
--------------------------------------------------------

从本章起，固定 ext4 分区中的 ``/boot/grub/grub.cfg`` 完整内容为：

.. code-block:: cfg

   set timeout=0
   set default=0

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

同时固定 ``/boot/bzImage`` 是由 Linux release ``7.2-rc1``、gregkh/linux commit
``7404ce51637231382873d0b55edabc2f3b841a9d`` 构建并安装的 x86 bzImage，
``/boot/initramfs.img`` 是与本场景匹配的 initramfs。文件路径和这份最小配置是本书的镜像内容约定；
它们不能从 GRUB commit 或 Linux commit 自动推导，也不是发行版生成器的隐含输出。

这个约定只固定唯一的成功控制流：timeout 为零，默认项是索引 0，内核将来以 ``/dev/sda1`` 为根并
启用串口 console。当前阶段不打开 bzImage 或 initramfs。

一行配置经历 parse、execute、unref
------------------------------------

当前执行者进入 ``grub_normal_parse_line(line, getline, file)``。它的主体分成三个生命期：

.. code-block:: c

   parsed_script = grub_script_parse (line, getline, getline_data);
   if (parsed_script)
     {
       grub_script_execute (parsed_script);
       grub_script_unref (parsed_script);
     }

``grub_script_parse()`` 把当前文本和必要的后续行组成临时 script object；
``grub_script_execute()`` 立即执行这个完整语法单元；执行返回后，顶层临时对象解除引用。因此
``read_config_file()`` 不是先把整个文件解析成一棵永久 AST 再统一执行，而是沿文件顺序反复完成
“解析一个完整单元—执行—释放”。

parser 需要更多行时仍由同一个 bufio 提供数据。这个回调关系也意味着，多行 block 消耗掉的行不会再被
外层 while 循环重复读取。

timeout=0 在本章就成为环境状态
--------------------------------

第一条文本是：

.. code-block:: cfg

   set timeout=0

lexer 保留 ``timeout=0`` 为一个参数，parser 生成普通 command line。脚本执行器先展开命令名和参数，
``grub_command_find("set")`` 命中 core command，而不是 dynamic placeholder；``set`` 在 ``=`` 处分离
变量名和值，调用 ``grub_env_set("timeout", "0")``。临时 script 随后释放，但 environment 中复制的
值继续存在。

下一次外层迭代对 ``set default=0`` 做同样的事：

::

   timeout = 0
   default = 0

这里的 ``0`` 仍只是字符串。选择逻辑尚未调用 ``grub_menu_get_timeout()`` 或
``get_entry_number()``，所以还没有发生“立即启动第零项”。空行也可进入 parser，但不会创建 menu
entry 或改变这两个变量。

menuentry 的左花括号把一次解析扩展到多行
------------------------------------------

外层循环读到：

.. code-block:: cfg

   menuentry 'Linux 7.2-rc1' {

时，语法单元还未闭合。lexer/parser 通过传入的 ``read_config_file_getline`` 继续从同一个 bufio 取得
两条 body 命令和右花括号。只有配对 ``}`` 到达后，``grub_script_parse()`` 才返回完整 command object。

GRUB 的 block 表示同时保留两份信息：一份带引用的子 script，供当前 extended-command dispatcher
识别 block；一份覆盖花括号原始字符的源码字符串，供 ``menuentry`` 复制。两者不能混同：当前临时
script 会在本次执行后释放，而菜单项需要把将来要运行的文本保存得更久。

单引号只控制词法边界，标题值本身是：

::

   Linux 7.2-rc1

它不会包含两个 quote 字符。

为什么 menuentry 此刻能执行而 linux 不能
------------------------------------------

``menuentry`` 已由 ``normal`` 模块的 ``grub_menu_init()`` 注册为 extended command，带
``BLOCKS`` 与 ``EXTRACTOR`` 等标志。因此脚本执行器能立即把展开后的标题、option state、block
script 和 block 原文交给 ``grub_cmd_menuentry()``。

``linux`` 与 ``initrd`` 的位置不同：它们只是 block 内尚未执行的文本。上一章读取的
``command.lst`` 已为 ``linux`` 注册按需加载映射；固定 GRUB 构建中两条命令都由 ``linux.mod``
提供，但建表阶段不会查找它们，也不会打开 ``linux.mod``。是否有 dynamic placeholder 只影响未来
执行 body，不改变当前 ``menuentry`` 的构造。

menuentry 不运行 block，而是剪下并复制 block
-----------------------------------------------

``grub_cmd_menuentry()`` 验证标题和 block 后，把 block 原文最后一个 ``}`` 暂时改成 NUL，并从开头
``{`` 之后取正文。它还根据标题参数生成前缀：

.. code-block:: cfg

   setparams 'Linux 7.2-rc1'

随后 ``grub_normal_add_menu_entry()`` 把前缀与去掉外层花括号的 body 拼接成长期 ``sourcecode``。
本场景保存的语义内容是：

.. code-block:: cfg

   setparams 'Linux 7.2-rc1'
   linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
   initrd /boot/initramfs.img

``setparams`` 不是现在执行的命令；它与 ``linux``、``initrd`` 一起留待 entry 被选中后在新作用域中
重新解析。加上这个前缀，使标题和其他菜单参数在未来能作为该脚本的位置参数重建。

grub_normal_add_menu_entry 建立独立所有权
-----------------------------------------

``grub_normal_add_menu_entry()`` 从 environment 的 menu data slot 取回空容器，然后逐项复制跨越
本轮 parser 生命期所需的数据。固定 entry 的结果是：

::

   title      = "Linux 7.2-rc1"
   id         = "Linux 7.2-rc1"
   argc       = 1
   args[0]    = "Linux 7.2-rc1"
   sourcecode = setparams prefix + block body
   submenu    = 0
   hotkey     = 0
   restricted = 1
   users      = ""

没有 ``--id`` 时 id 复制 title；没有 ``--class`` 与 ``--hotkey`` 时对应链表/值为空。还要保留一个
容易写反的认证边界：没有 ``--users`` 也没有 ``--unrestricted`` 时，handler 传入的是已分配的空
``users`` 字符串，因此 entry 的 ``restricted`` 位确实为 1。后续是否询问认证由 ``superusers``
环境变量决定，而不是把这里误写成 unrestricted。

新 entry 被接到 ``menu->entry_list`` 尾部，最后执行 ``menu->size++``。从这条写入开始，menu 才拥有
一个可选择项。title、id、args、users 与 sourcecode 各自属于长期 entry；当前 parser 的 argv、
block script 和原始 line 可以安全释放。

释放临时 script 不会释放菜单项
--------------------------------

``grub_cmd_menuentry()`` 返回后，脚本执行器完成本语法单元，``grub_normal_parse_line()`` 对临时
script unref。它包含的预解析 block 可以被回收，但 entry 中保存的是复制后的字符串和参数数组，
不指向已释放的 parser 临时内存。

这也是 GRUB 保存 sourcecode 而非只保存一棵 AST 的原因：真正启动时会在当时的 environment 和新的
位置参数作用域中重新解析文本，变量展开与 dynamic command loading 都以选择时的状态为准。

EOF 关闭的是一条完整 wrapper 所有权链
--------------------------------------

menuentry 已消耗右花括号；外层 while 再次调用 getline，最终得到 EOF。``read_config_file()`` 先恢复
此前保存的配置上下文变量。顶层进入前没有旧值，所以此刻：

::

   config_file      = unset
   config_directory = unset

这不会影响 menu entry 的 sourcecode，因为 entry 已经拥有自己的副本。随后
``grub_file_close(file)`` 关闭 bufio wrapper；``grub_bufio_close()`` 先关闭所持 raw ext4 file，释放
ext2 open data 与模块引用，再关闭 device/disk/partition/biosdisk 私有对象，最后释放 buffer 并把 wrapper
的 device 清零。外层 file close 再释放 wrapper 本身，避免重复关闭底层设备。

``read_config_file()`` 返回 menu，``grub_normal_execute()`` 按源码约定清掉配置执行遗留的
``grub_errno``。当前执行者已回到 ``grub_normal_execute()``，下一条重要判断才是 menu 是否非空。

本章结束状态
------------

* CPU0 上的 BSP 仍在 GRUB 32 位平坦保护模式，paging 关闭，``IF=0``、``DF=0``；当前执行者是
  ``grub_normal_execute()``。
* 固定 ``grub.cfg`` 已按顺序解析执行；``timeout="0"``、``default="0"`` 已进入 environment。
* menu 已发布且 ``size=1``；唯一 entry 的 title/id 是 ``Linux 7.2-rc1``，它独立拥有 args、空 users
  字符串和 ``setparams + linux + initrd`` sourcecode。
* entry 的 ``restricted=1``；本章尚未调用认证检查。
* ``config_file`` 与 ``config_directory`` 已恢复为进入配置前的状态，即顶层场景中的 unset。
* ``grub.cfg`` 的 bufio、raw file、ext2、partition、disk 与 device open objects 均已关闭；disk cache
  可以继续存在。
* ``linux.mod`` 尚未装载，``grub_cmd_linux()`` 与 ``grub_cmd_initrd()`` 尚未注册；bzImage 和
  initramfs 均未打开。

关键边界
--------

* ``grub_normal_parse_line()`` 逐个完整语法单元执行，不永久保存整份 ``grub.cfg`` 的 AST。
* 多行 ``menuentry`` 由 parser 的 getline callback 继续取行；这些行不会再回到外层循环。
* 建立 menu entry 只复制 body，不执行 ``linux`` 或 ``initrd``。
* 默认无 ``--unrestricted`` 的 entry 是 restricted；只有未设置 ``superusers`` 才会让后续认证检查
  直接成功。
* Linux commit 固定了内核源码，``/boot/bzImage`` 与 ``/boot/initramfs.img`` 则是本书明确增加的
  磁盘内容约定，二者不可互相冒充。

下一入口
--------

.. code-block:: c

   if (menu && menu->size)
     grub_show_menu (menu, nested, 0);

下一章追踪 ``timeout=0`` 的 fast path 如何选择索引 0、建立 ``chosen`` 与 entry scope，随后由
``linux`` dynamic placeholder 装入 ``linux.mod``；终点停在真正 ``grub_cmd_linux()`` 调用之前。

资料
----

* `GNU GRUB 2.14 grub-core/normal/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/main.c>`_
* `GNU GRUB 2.14 grub-core/script/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/main.c>`_
* `GNU GRUB 2.14 grub-core/script/parser.y <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/parser.y>`_
* `GNU GRUB 2.14 grub-core/script/execute.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/execute.c>`_
* `GNU GRUB 2.14 grub-core/commands/menuentry.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/commands/menuentry.c>`_
* `GNU GRUB 2.14 grub-core/kern/corecmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/corecmd.c>`_
* `GNU GRUB 2.14 grub-core/io/bufio.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/io/bufio.c>`_
* `GNU GRUB 2.14 grub-core/Makefile.am <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/Makefile.am>`_
* `GNU GRUB 2.14 grub-core/Makefile.core.def <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/Makefile.core.def>`_
* `Linux v7.2-rc1 fixed commit <https://github.com/gregkh/linux/tree/7404ce51637231382873d0b55edabc2f3b841a9d>`_
