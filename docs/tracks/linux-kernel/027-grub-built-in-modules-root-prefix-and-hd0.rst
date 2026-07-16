第二十七章：GRUB怎样加载内建模块并建立hd0、root和prefix？
==========================================================

第026章在 ``grub_machine_init()`` 返回处停下。BSP仍运行32位flat保护模式、分页关闭、
A20开启、IF=0、DF=0；console与运行时CPU能力对应的时间源已经注册，initial heap已经避开
``[0x100000,modend)``，但embedded ELF还只是该范围内的原始输入，任何disk、partition或
filesystem后端都尚未注册。

固定平台只规定MBR、第一分区从LBA 2048开始且为ext4，并没有提供可解析的 ``core.img`` 或
完整安装命令。为使本章和后续文件路径可复现，以下数值路径采用明确的simple-install叙事约定：

* 使用默认i386-pc ``grub-install`` 和默认 ``biosdisk``；
* 安装目标是第一块BIOS硬盘整盘，GRUB目录在同一盘
  ``msdos1:/boot/grub``；
* 无LVM、RAID、加密、debug和额外 ``--modules``；
* 第023—024章的clean-gap embedding约定继续有效。

这组条件让安装器把 ``biosdisk``、 ``part_msdos``、 ``ext2`` 及其dependency closure放入
``core.img``，embedded prefix为 ``(,msdos1)/boot/grub``，且不生成embedded
``load.cfg``。重要的是：默认列表不加入 ``normal``；下一章必须从磁盘动态加载
``normal.mod``。这些是上述安装约定与固定源码共同得到的结果，不冒充仅由分区表就能推出的
事实。

Welcome为什么在machine init之后才出现
------------------------------------

返回 ``grub_main`` 后，第一步用新安装的time source记录：

.. code-block:: c

   grub_boot_time("After machine init.");

随后非EFI的PC BIOS路径设置highlight color，经已注册console输出：

::

   Welcome to GRUB!

每个实际的INT 10h输出或光标操作都通过第025章保存的
``prot_to_real → BIOS → real_to_prot`` 桥完成。字符输出期间BIOS按实模式ABI运行；每次返回
``grub_main`` 时仍恢复flat segments、limit-0保护模式IDT和IF=0。欢迎信息不读磁盘，也没有
建立menu。

verifier初始化不等于验证了文件
------------------------------

下一条 ``grub_verifiers_init()`` 只把 ``grub_verifiers_open`` 注册为
``GRUB_FILE_FILTER_VERIFY``。它建立以后打开文件时遍历verifier链的入口；当前普通SeaBIOS路径
没有Secure Boot条件，也没有因为调用了这个函数就产生某个已验证文件、签名结果或信任状态。

embedded config为什么在当前不存在
----------------------------------

``grub_load_config()`` 遍历 ``grub_modbase`` 指向的module-info对象，只接受
``OBJ_TYPE_CONFIG``。若找到，它会先用已经可用的heap复制文本到NUL结尾的 ``load_config``，
稍后再执行；它不会在原始对象区被回收后继续悬挂一个指针。

当前simple-install约定满足：

::

   disk module       = biosdisk
   one GRUB drive    = boot filesystem drive
   install drive     = same physical disk
   platform bootdev  = available on i386-pc
   abstractions      = none
   debug image       = none

固定 ``grub-install.c`` 因而走“hardcode partition in prefix”分支，不创建 ``load.cfg``；
``grub-mkimage`` 没有收到config path，所以module-info中没有 ``OBJ_TYPE_CONFIG``。
本次扫描结束后 ``load_config`` 仍是BSS初值NULL，后面embedded-config parser将被跳过。磁盘
``/boot/grub/grub.cfg`` 是另一个对象，本章尚未打开它。

为什么先注册core导出符号
------------------------

embedded ELF是ET_REL模块，会引用 ``grub_malloc``、disk/fs注册函数、BIOS bridge等core符号。
所以 ``grub_main`` 在装载前先执行生成的：

.. code-block:: c

   grub_register_exported_symbols();

它把允许模块解析的core符号放入GRUB自己的符号表；这一步没有复制ELF section，也没有执行
任何模块init。若构建器支持额外linker init，条件调用也发生在导出符号注册之后、模块遍历之前。

每个embedded ELF怎样取得新所有权
--------------------------------

``grub_load_modules()`` 按module-info中的对象顺序遍历，只把
``header->type == OBJ_TYPE_ELF`` 的payload交给 ``grub_dl_load_core``。每个对象先经
``grub_dl_load_core_noinit``：

#. 校验ELF header和section table没有越过对象size；
#. 要求 ``e_type == ET_REL``；
#. 分配并初始化 ``struct grub_dl``，初始 ``ref_count=1``；
#. 解析module name、license与dependency；
#. 从initial heap为alloc sections及loader metadata取得新内存；
#. 复制section，解析core/已加载模块符号并应用i386 relocation；
#. 同步指令cache接口，再把模块链接到 ``grub_dl_head``；
#. 调用 ``grub_dl_init`` 执行该模块的init。

任一embedded ELF无法装载时， ``grub_load_modules`` 调用 ``grub_fatal``，不存在“忽略坏模块
仍把本章标为成功”的分支。当前成功路径结束后，真正执行的section、module name、dependency和
loader对象都由heap持有；1 MiB附近的原始ELF只剩可回收输入身份。

standard install实际内建哪些后端
--------------------------------

默认 ``grub-install`` 先probe GRUB目录所在filesystem并把其driver name加入module list。
固定分区是ext4，而实现它的GRUB driver名仍是 ``ext2``；沿partition parent链又加入
``part_msdos``，i386-pc默认disk module加入 ``biosdisk``。 ``grub-mkimage`` 再根据
``moddep.lst`` 补齐它们的依赖。

默认module list没有一条加入 ``normal`` 的路径；normal也不是上述三个后端的依赖。因此当前
embedded ELF完成时：

* ``biosdisk`` 已init；
* ``part_msdos`` 已init；
* ``ext2`` 已init；
* ``normal`` 不在 ``grub_dl_head``， ``normal`` command尚未注册。

用户显式给 ``grub-install --modules=normal`` 会产生另一条合法路径，但不属于当前
simple-install约定。

biosdisk init为何还不等于打开hd0
--------------------------------

``GRUB_MOD_INIT(biosdisk)`` 先在 ``0x68000`` scratch准备El Torito参数，通过BIOS bridge对
``grub_boot_device`` 高字节所示drive做一次INT 13h AH=4b01探测。当前从普通hard disk
``0x80`` 启动，不建立一个有效no-emulation CD身份。随后它调用：

.. code-block:: c

   grub_disk_dev_register(&grub_biosdisk_dev);

注册对象只是一组 ``disk_iterate/open/close/read/write`` 方法。它没有分配持久
``struct grub_disk``，没有打开 ``hd0``，也没有读取MBR。以后通用disk层传入字符串时，
``grub_biosdisk_get_drive`` 才执行：

::

   hd0 → numeric suffix 0 → 0 + 0x80 → BIOS drive 0x80

所以 ``hd0`` 是GRUB的命名规则，不是SeaBIOS传入的字符串。此刻应说“后端已经能够解析
``hd0``”，不能说“一个hd0磁盘对象已经存在”。

part_msdos和ext2此刻只注册解析器
-------------------------------

``GRUB_MOD_INIT(part_msdos)`` 把名为 ``msdos`` 的partition map及其iterate方法登记到全局
partition-map链； ``GRUB_MOD_INIT(ext2)`` 把名为 ``ext2`` 的
``dir/open/read/close/label/uuid/mtime`` 方法登记到filesystem链。

两者都没有在init中主动打开固定磁盘。LBA 0的四个partition entries、第一项LBA 2048以及ext4
superblock只有下一章真正打开带设备的module路径时才会读取。模块注册是“具备解释能力”，不是
“已经产生分区或inode对象”。

boot_device怎样先得到cmdpath
----------------------------

模块全部成功后， ``grub_main`` 检查可能的disable-CLI object；当前约定没有该对象。随后
``grub_set_prefix_and_root()`` 先扫描出embedded prefix，再注册 ``root`` write hook，接着
调用：

.. code-block:: c

   grub_machine_get_bootlocation(&fwdevice, &fwpath);

第025章交出的 ``grub_boot_device=0x80ffffff`` 被拆为：

::

   boot_drive = 0x80
   dos_part   = 0xff
   bsd_part   = 0xff

PC实现从heap分配字符串，按high bit规则生成 ``fwdevice="hd0"``；两个partition字段为
``0xff``，所以不会在这里附加partition， ``fwpath`` 仍为NULL。接着先建立并export：

::

   cmdpath = (hd0)

``cmdpath`` 记录固件把core带入系统的位置；它的建立同样不触发disk open。

embedded prefix怎样补全启动盘
-----------------------------

当前原始prefix对象是：

::

   (,msdos1)/boot/grub

解析结果是device ``,msdos1`` 和path ``/boot/grub``。device以逗号开头，表示安装器固定了
partition但故意留空drive；源码于是从 ``fwdevice=hd0`` 取drive部分并拼接：

::

   hd0 + ,msdos1 = hd0,msdos1

随后 ``grub_env_set`` 在heap中复制name/value，最终得到：

::

   cmdpath = (hd0)
   root    = hd0,msdos1
   prefix  = (hd0,msdos1)/boot/grub

``root`` write hook会去掉调用者可能给出的外围括号，所以环境变量本身不带括号；
``prefix`` 是完整GRUB资源路径。两者随后被export为global context变量。此过程只做字符串和
环境表操作，没有验证磁盘上该目录已经可读。

为什么现在才能回收1 MiB输入区
------------------------------

到这里，embedded ELF的运行section与metadata已经迁到heap；config若存在会先复制，当前为NULL；
prefix、root和cmdpath也已经由env层复制。原始module-info对象不再是任何后续状态的唯一副本。

PC BIOS目标的 ``reclaim_module_space()`` 执行：

.. code-block:: c

   modstart = 0x100000;
   modend   = grub_modules_get_end();
   grub_modbase = 0;
   grub_mm_init_region((void *) modstart, modend - modstart);

回收范围不只包含“原始模块”：它还包含第025章留在1 MiB的临时initialized kernel副本、module-info
和全部原始对象。正式kernel仍在0x9000，模块运行副本已在heap，所以PC BIOS的
``GRUB_KERNEL_PRELOAD_SPACE_REUSABLE=1`` 允许把整个半开区间加入allocator。若它紧邻第026章
已有heap， ``grub_mm_init_region`` 会合并region；具体合并形态依赖未知的 ``modend``。

把 ``grub_modbase`` 清零发生在调用allocator之前，之后不能再用 ``FOR_MODULES`` 扫原始列表。
因此load config、load ELF、set prefix三个动作必须全部先于reclaim。

core commands与embedded config出口
---------------------------------

回收后， ``grub_register_core_commands()`` 注册core自身的 ``set``、 ``unset``、 ``ls`` 和
``insmod``。这组命令不等于normal mode；当前仍没有 ``normal`` command。

``load_config==NULL`` 使：

.. code-block:: c

   if (load_config)
       grub_parser_execute(load_config);

直接跳过。第027章停在下一条 ``grub_load_normal_mode()`` 尚未调用的边界。此时第一次普通
filesystem访问、 ``normal.mod`` 加载、配置文件打开和menu构造都尚未发生。

本章结束状态
------------

控制流已经走过：

::

   grub_machine_init returns
   → grub_boot_time("After machine init.")
   → print Welcome through BIOS console bridge
   → register verifier file filter
   → scan embedded config; none under simple-install convention
   → register core exported symbols
   → load/init embedded ELF modules
      → biosdisk backend registered
      → msdos partition map registered
      → ext2/ext3/ext4 filesystem reader registered as ext2
   → derive fwdevice=hd0 from grub_boot_device
   → cmdpath=(hd0)
   → combine embedded (,msdos1)/boot/grub with hd0
   → root=hd0,msdos1; prefix=(hd0,msdos1)/boot/grub
   → reclaim [0x100000,modend); grub_modbase=0
   → register set/unset/ls/insmod
   → skip absent embedded config

此刻：

* 当前执行者：BSP上的GNU GRUB 2.14 ``grub_main()``，即将调用
  ``grub_load_normal_mode()``；
* CPU mode：32位flat保护模式，分页关闭，A20开启，主路径IF=0、DF=0；
* heap：initial regions仍有效， ``[0x100000,modend)`` 已加入并可能与相邻region合并；
* ``grub_modbase=0``；高端临时kernel/module-info/raw objects不再具有对象身份；
* loaded modules： ``biosdisk``、 ``part_msdos``、 ``ext2`` 及依赖的运行副本由heap持有；
* disk backend：可把名字 ``hd0`` 映射到BIOS drive0x80，但当前没有打开的
  ``grub_disk``、partition、filesystem或file对象；
* environments： ``cmdpath=(hd0)``、 ``root=hd0,msdos1``、
  ``prefix=(hd0,msdos1)/boot/grub``，三者值均由env层拥有；
* embedded config：不存在， ``load_config=NULL``；
* ``normal``：不在默认embedded module集合中，command尚未注册；
* ``normal.mod``、 ``grub.cfg``、menu与Linux bzImage：均尚未读取或建立。

关键边界
--------

* simple-install的modules/prefix/config是明确约定下的安装器结果，不是只凭MBR和ext4推出的事实。
* 当前default core包含disk/partition/filesystem后端及依赖，但不包含 ``normal``。
* module init注册方法表；直到下一章请求具体路径， ``hd0``、msdos1与ext4对象才会被打开和读取。
* ``cmdpath`` 先只用firmware drive生成；embedded prefix随后补上partition与path。
* reclaim覆盖 ``[0x100000,modend)`` 整个临时解压/原始对象区，并把 ``grub_modbase`` 清零；
  它必须晚于ELF装载和环境字符串复制。
* verifier filter注册不产生“文件已验证”结论；当前也没有Secure Boot信任链。
* embedded config与磁盘 ``grub.cfg`` 是不同对象；当前前者缺席，后者尚未打开。

下一入口
--------

下一章从 ``grub_load_normal_mode() → grub_dl_load("normal")`` 开始。因为
``grub_dl_get("normal")`` 当前miss，固定下一路径会构造：

::

   (hd0,msdos1)/boot/grub/i386-pc/normal.mod

并首次进入 ``grub_file_open → grub_device_open``，由
``biosdisk → part_msdos → ext2`` 真正打开drive0x80、MBR第一分区和ext4文件。现有第028章把
这一步写成“normal已经内建、直接返回”，下一顺序批次必须首先修正。

资料
----

* `GRUB固定提交：grub_main完整顺序 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c#L302-L370>`_；
* `GRUB固定提交：embedded config与ELF遍历 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c#L57-L101>`_；
* `GRUB固定提交：prefix/root/cmdpath合成 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c#L103-L229>`_；
* `GRUB固定提交：module区回收 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c#L278-L300>`_；
* `GRUB固定提交：ELF重定位、登记与init <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c#L736-L821>`_；
* `GRUB固定提交：normal miss时按prefix动态加载 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/dl.c#L867-L902>`_；
* `GRUB固定提交：grub-install探测fs、partmap与disk module <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/grub-install.c#L1320-L1361>`_；
* `GRUB固定提交：simple-install prefix与config分支 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/grub-install.c#L1411-L1583>`_；
* `GRUB固定提交：prefix/config/modules传给mkimage <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/grub-install.c#L1672-L1684>`_；
* `GRUB固定提交：boot drive转换为hd0 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c#L68-L106>`_；
* `GRUB固定提交：biosdisk命名、open与模块init <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/disk/i386/pc/biosdisk.c#L249-L440>`_；
* `GRUB固定提交：biosdisk注册 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/disk/i386/pc/biosdisk.c#L635-L686>`_；
* `GRUB固定提交：part_msdos注册 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/partmap/msdos.c#L419-L438>`_；
* `GRUB固定提交：ext2/ext3/ext4 reader注册 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/fs/ext2.c#L1127-L1155>`_；
* `GRUB固定提交：verifier filter注册 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/verifiers.c#L207-L228>`_；
* `GRUB固定提交：core command注册 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/corecmd.c#L176-L192>`_。
