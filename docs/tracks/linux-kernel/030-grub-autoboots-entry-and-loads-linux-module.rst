第三十章：GRUB 怎样自动选择菜单项并装入 linux.mod？
======================================================

上一章结束时，CPU0 上的 BSP 已从 ``read_config_file()`` 回到 ``grub_normal_execute()``。
处理器仍处于 32 位平坦保护模式，paging 关闭，``IF=0``、``DF=0``；``grub.cfg`` 及其底层磁盘
对象已经关闭。当前 environment 与 menu 的关键状态是：

::

   timeout        = "0"
   default        = "0"
   menu->size     = 1
   entry[0].title = "Linux 7.2-rc1"
   entry[0].id    = "Linux 7.2-rc1"
   entry[0].restricted = 1

唯一 entry 持有 ``setparams``、``linux``、``initrd`` 三行 sourcecode，但 body 还没有执行。
``command.lst`` 中已经有 ``linux → linux`` 的自动加载映射，``linux.mod`` 本身则尚未进入 module
list。本章从 ``grub_show_menu()`` 开始，沿 timeout fast path 执行 entry，并在
``grub_dyncmd_dispatcher()`` 内完成 ``linux.mod`` 动态装载；终点停在真实
``grub_cmd_linux()`` 即将取得控制权的位置。

timeout=0 在 menu_init 之前直接返回默认索引
----------------------------------------------

``grub_normal_execute()`` 满足 ``menu && menu->size``，调用：

.. code-block:: c

   grub_show_menu (menu, nested, 0);

这里 ``nested=0``，第三个参数也为 0，表示不是上层 submenu 传下来的 autoboot。内部
``show_menu()`` 先进入 ``run_menu()``。``get_entry_number(menu, "default")`` 把字符串 ``0``
转换成索引 0；它在 ``[0, menu->size)`` 内，无需回退。随后 ``grub_menu_get_timeout()`` 把
``timeout`` 转成整数 0。固定配置没有设置 ``timeout_style``，所以 ``get_timeout_style()`` 采用
普通 menu style。

在这个固定 style 下，源码随即在普通 ``menu_init()`` 与界面绘制之前检查：

.. code-block:: c

   if (timeout == 0)
     {
       *auto_boot = 1;
       return default_entry;
     }

所以当前路径不建立 menu viewer、不画一次完整菜单，也不读取键盘。``run_menu()`` 返回索引 0，
并把 ``auto_boot`` 标成 1。这个普通-menu fast path 没有 unset ``timeout``，因此本章终点它仍为
字符串 ``0``。若配置显式选择 hidden/countdown style，源码会先进入另一段可中断等待并撤销 timeout；
那不是本书当前路径。

自动选择为什么进入 fallback wrapper
-----------------------------------

``show_menu()`` 取得第零个 ``grub_menu_entry``。因为 ``auto_boot=1``，它调用
``grub_menu_execute_with_fallback()``，而不是手动选择分支中的
``grub_menu_execute_entry(entry, 0)``。fallback wrapper 会通知即将启动的 entry，然后固定调用：

.. code-block:: c

   grub_menu_execute_entry (entry, 1);

这里传入的 1 是 entry 执行的 ``auto_boot`` 参数；它与外层 ``grub_show_menu(..., autoboot=0)``
不是同一个变量。当前 entry 不是 submenu，所以该参数不会创建子菜单或为子菜单重设 timeout。

固定配置没有 ``fallback`` 环境变量。只有第一次 entry 执行返回，wrapper 才会检查 fallback 列表；
本章尚未到那个边界，成功启动路径以后也不会返回到这里。

restricted entry 为什么没有认证交互
----------------------------------

``grub_menu_execute_entry()`` 看到 ``entry->restricted=1``，确实调用
``grub_auth_check_authentication(entry->users)``，其中 users 是空字符串。认证实现首先读取
``superusers``；固定配置没有设置该变量，``is_authenticated()`` 立即返回成功，不枚举用户，也不提示
用户名或密码。

所以“没有认证交互”的原因不是 entry 被标成 unrestricted，而是 restricted 检查在
``superusers`` 不存在时短路通过。如果配置设置了 superusers，这个空 users 项默认只允许已认证的
superuser，控制流就会不同。

chosen 被发布，default 被暂时撤销
---------------------------------

认证通过后，函数保存进入 entry 前的 ``chosen`` 与 ``default``。当前没有旧 chosen，旧 default 是
``"0"``，因此栈上/heap 中留有一份待恢复的 default 副本。

entry id 中没有 ``>``，当前也不在 submenu，于是函数构造、设置并导出：

::

   chosen = Linux 7.2-rc1

``default="0"`` 不含表示下一层 submenu 的单个 ``>``。源码因此在执行 body 前 unset 当前
``default``，而不是把 0 继续传入 entry scope：

::

   default = unset       # entry 执行期间

如果 entry 脚本失败并返回，函数末尾会恢复旧 default 并撤销/恢复 chosen；成功 Linux handoff 不会走
到这段恢复逻辑。本章终点位于 body 内，所以 ``chosen`` 已导出，``default`` 仍暂时不存在。

entry sourcecode 在新的参数作用域中重新解析
-------------------------------------------

接着执行：

.. code-block:: c

   grub_script_execute_new_scope (entry->sourcecode,
                                  entry->argc,
                                  entry->args);

新 ``grub_script_scope`` 初始带 ``argc=1`` 和标题参数 ``Linux 7.2-rc1``，旧 scope 指针由调用栈保存。
``grub_script_execute_sourcecode()`` 仍按“取一个完整单元—parse—execute—free”处理 entry 文本，
不是复用第 029 章已经释放的 block AST。

第一行：

.. code-block:: cfg

   setparams 'Linux 7.2-rc1'

把当前 scope 的位置参数重建为同一个标题。它不写普通 GRUB environment，也不影响长期 entry->args。
脚本随后取得第二行：

.. code-block:: cfg

   linux /boot/bzImage root=/dev/sda1 ro console=ttyS0

argument expansion 完成后，command name 与传给 command function 的参数分离为：

::

   cmdname = linux
   argc    = 4
   args[0] = /boot/bzImage
   args[1] = root=/dev/sda1
   args[2] = ro
   args[3] = console=ttyS0

此时 ``/boot/bzImage`` 仍只是 heap 中的参数字符串，尚未作为文件名打开。

command.lst 留下的是 extended placeholder
-----------------------------------------

``grub_command_find("linux")`` 命中第 028 章读取 ``command.lst`` 时注册的 dynamic command。
GRUB 的构建规则从模块中的 command markers 生成安装目录里的索引；i386-pc 的 ``linux`` 模块由
``loader/i386/linux.c``、通用 ``loader/linux.c`` 与 ``lib/cmdline.c`` 等组成，并提供 ``linux`` 与
``initrd`` 两条命令。

``read_command_list()`` 没有预先读模块机器码。对一条 ``linux: linux`` 映射，它复制命令名与模块名，
注册一个带下列标志的 extended command：

::

   GRUB_COMMAND_FLAG_BLOCKS
   GRUB_COMMAND_FLAG_EXTCMD
   GRUB_COMMAND_FLAG_DYNCMD

其 extended callback 是 ``grub_dyncmd_dispatcher``，私有 data 是字符串 ``"linux"``。通用脚本执行器
看到 ``BLOCKS|EXTCMD`` 后先走 ``grub_extcmd_dispatcher()``；当前命令没有 block 参数，但同一 dispatch
接口仍把普通 argc/args 带到 dynamic callback。

dispatcher 用 prefix 构造 linux.mod 的唯一位置
----------------------------------------------

``grub_dyncmd_dispatcher()`` 从 placeholder data 取出模块名并调用：

.. code-block:: c

   mod = grub_dl_load ("linux");

全局 module list 中还没有 linux，``prefix`` 仍为 ``(hd0,msdos1)/boot/grub``，所以 loader 构造：

::

   (hd0,msdos1)/boot/grub/i386-pc/linux.mod

这个文件再次经历 ``grub_file_open → grub_device_open → grub_disk_open``。biosdisk 打开 ``hd0``
对应 BIOS drive ``0x80``，part_msdos 将 ``msdos1`` 解析为 LBA 2048 起始的第一主分区，ext2 driver
在 ext4 中沿目录/inode/extent 查找 ``linux.mod``。GRUB disk cache 可能满足部分 MBR、superblock、
目录或文件块读取；cache miss 才经保护模式—实模式桥发出 INT 13h，由固定 SeaBIOS/QEMU AHCI 链完成。

实际 ``linux.mod`` inode 与 extent 没有被固定提交号编码，因此不能凭源码写死其数据 LBA或 AHCI
command 次数。

模块文件关闭先于依赖与重定位
----------------------------

``grub_dl_load_file()`` 按文件大小分配临时 heap buffer，完整读入 ``linux.mod``，然后在解析依赖前
关闭 file。ext2 file data、模块 file 引用、device、partition、disk 与 biosdisk 私有 data 在这里释放；
cache 可独立保留。这样后续依赖装载可以重新打开同一设备而不与旧 open object 嵌套。

``grub_dl_load_core()`` 验证 ``ET_REL`` 与 section 边界，解析名称、许可证和 dependency records，
装入所需依赖，为 allocatable sections 分配长期内存，解析导出符号并执行 i386 relocation，设置内存
属性、刷新 cache，把 module 加入全局 list，最后调用 init。原始文件 buffer 随后释放；长期保留的是
重定位后的 sections、``grub_dl`` 元数据和依赖引用。

linux init 同时注册两个真实 command
-----------------------------------

i386-pc 路径的 ``GRUB_MOD_INIT(linux)`` 执行：

.. code-block:: c

   cmd_linux = grub_register_command ("linux", grub_cmd_linux, ...);
   cmd_initrd = grub_register_command ("initrd", grub_cmd_initrd, ...);

这是 ``grub-core/loader/i386/linux.c`` 中的现代 x86 Linux loader，不是同目录 ``pc/linux.c`` 提供的
``linux16``/``initrd16`` 命令。GRUB 当前仍在 32 位保护模式；这描述的是 GRUB 与 Linux x86 boot
protocol 的装载/交接入口，不表示固定 7.2-rc1 内核最终只能运行 32 位代码。

``grub_dl_load_file()`` 撤销装载过程的临时 module 引用后返回。dynamic dispatcher 随即
``grub_dl_ref(mod)``，为这次自动加载建立长期持有，使真实 command 依赖的 module 不会在执行中消失。

旧 placeholder 注销后必须按名称重新查找
-----------------------------------------

dispatcher 保存旧 command name，释放 placeholder 私有模块名，并调用 ``grub_unregister_extcmd()``。
这一步撤销旧 ``linux`` placeholder；刚才 module init 注册的真实 ``linux`` command 仍在 command
list。dispatcher 再执行：

.. code-block:: c

   cmd = grub_command_find (name);

返回对象的 ``func`` 已是 ``grub_cmd_linux``，标志也已变成普通 command 的真实标志。原脚本展开出的
四个 args 仍由当前 cmdline argv 持有，并未重新解析或复制成另一条命令。

dynamic dispatcher 的下一条分支发现真实 command 不再是 ``BLOCKS|EXTCMD`` 组合，于是将执行：

.. code-block:: c

   ret = (cmd->func) (cmd, argc, args);

本章恰好停在这条调用之前。``linux.mod`` 已就绪，但 ``grub_cmd_linux()`` 尚未打开
``/boot/bzImage``；第三行 ``initrd`` 更没有开始解析执行。

本章结束状态
------------

* 当前执行者是 CPU0 上的 ``grub_dyncmd_dispatcher()``；处理器仍在 32 位平坦保护模式，paging
  关闭，``IF=0``、``DF=0``。
* timeout fast path 已选择索引 0，没有建立/绘制 menu viewer，也没有读取键盘。
* restricted entry 的认证检查已执行；因 ``superusers`` 未设置而直接成功，没有认证交互。
* ``chosen="Linux 7.2-rc1"`` 已设置并导出；旧 ``default="0"`` 已保存，当前 default 暂时 unset；
  ``timeout="0"`` 仍存在。
* entry 新 scope 正在执行，``setparams`` 已完成；``linux`` 的四个参数已经展开并仍由当前 cmdline 持有。
* 旧 ``linux`` dynamic placeholder 已注销；``linux.mod`` 已从 ext4 读取、关闭文件、完成依赖解析、
  重定位与 init，并由 dispatcher 增加长期引用。
* 真实 ``linux`` 与 ``initrd`` command 已注册，当前重新查找得到的 ``cmd->func`` 是
  ``grub_cmd_linux``。
* linux.mod 及依赖的文件/device/disk open objects 已关闭；module sections 与 disk cache 是各自独立
  的存活对象。
* ``grub_cmd_linux()`` 尚未调用，``/boot/bzImage`` 与 ``/boot/initramfs.img`` 均未打开，Linux
  尚未取得控制权。

关键边界
--------

* timeout fast path 的 ``auto_boot``、``grub_show_menu`` 的 ``autoboot`` 参数和 fallback wrapper 的
  ``autobooted`` 参数是三处不同状态，不能按同名概念合并。
* entry 是 restricted，但没有 ``superusers`` 时认证直接成功；“无提示”不等于 unrestricted。
* ``command.lst`` 只建立名称映射和 placeholder；直到 body 执行 ``linux`` 才读取 ``linux.mod``。
* module 文件在依赖处理前关闭；临时 ELF buffer、长期重定位 sections 和 dispatcher module ref 有不同
  生命期。
* 真实 command 不是在原 placeholder 对象上原地改写；dispatcher 注销旧对象后按名称重新查找 init
  新注册的对象。

下一入口
--------

.. code-block:: c

   grub_cmd_linux (cmd, 4, args);

下一章从真实 ``linux`` command 打开固定 ``/boot/bzImage`` 开始，校验 Linux/x86 setup header，
分配 relocator-backed 内存并安装 loader 回调；``initrd`` 行仍在当前 entry sourcecode 中等待执行。

资料
----

* `GNU GRUB 2.14 grub-core/normal/menu.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/menu.c>`_
* `GNU GRUB 2.14 grub-core/normal/auth.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/auth.c>`_
* `GNU GRUB 2.14 grub-core/normal/dyncmd.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/normal/dyncmd.c>`_
* `GNU GRUB 2.14 grub-core/script/execute.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/script/execute.c>`_
* `GNU GRUB 2.14 grub-core/kern/dl.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c>`_
* `GNU GRUB 2.14 grub-core/loader/i386/linux.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c>`_
* `GNU GRUB 2.14 grub-core/Makefile.am <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/Makefile.am>`_
* `GNU GRUB 2.14 grub-core/Makefile.core.def <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/Makefile.core.def>`_
* `GNU SeaBIOS disk.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c>`_
* `QEMU hw/ide/ahci.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/ide/ahci.c>`_
