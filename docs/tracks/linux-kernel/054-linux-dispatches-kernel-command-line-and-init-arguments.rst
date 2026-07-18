第五十四章：Linux 怎样把正式命令行分发给内核与 init？
========================================================

第五十三章结束时，CPU0已经使用正式per-CPU base并在hotplug ledger中标为ONLINE；IF=0，
``saved_command_line`` 与mutable ``static_command_line`` 仍未ordinary parse。当前连续入口是：

.. code-block:: c

   print_kernel_cmdline(saved_command_line);
   parse_early_param();
   after_dashes = parse_args("Booting kernel", static_command_line, ...);
   print_unknown_bootoptions();
   if (!IS_ERR_OR_NULL(after_dashes))
       parse_args("Setting init args", after_dashes, ..., set_init_arg);
   if (extra_init_args)
       parse_args("Setting extra init args", extra_init_args, ..., set_init_arg);

本章追踪到最后一项返回，停在 ``random_init_early(command_line)`` call前。它把 ``__param``、传统
``__setup``、bootloader markers、unknown kernel tokens与 ``--`` 后init tokens按不同规则分流；只
建立后续policy/argv/env state，不挂载root、不打开serial console，也不创建PID 1。

先打印保存副本，不触碰mutable parser buffer
---------------------------------------------

``print_kernel_cmdline`` 读取051建立的 ``saved_command_line``。wrap config为0或ideal length覆盖整个
``COMMAND_LINE_SIZE`` 时一次打印；否则寻找空格分段，每行加 ``Kernel command line:`` prefix，非末行
加反斜杠suffix。算法按raw spaces切割、刻意不理解quotes，所以长quoted value也可能仅在日志显示上被
分行；源字符串没有被修改。

saved副本可含bootconfig kernel/init extras及arch effective boot line。打印它只提供observable record，
不表示其中token已生效。真正parser操作另一份 ``static_command_line``，所以日志不会因in-place NUL
切分而丢失后半段。

fixed GRUB交给Linux的raw contribution为：

.. code-block:: text

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

但builtin append/override与bootconfig extras未固定，最终打印文本不能简化为只含这四项。

generic early-parameter call在x86上由 ``done`` guard返回
------------------------------------------------------

041的x86 ``setup_arch`` 已在E820后、其余大部分arch setup前调用 ``parse_early_param``。首次call把
``boot_command_line`` 复制到temporary buffer，扫描所有 ``early_param`` entries，随后设置static
``done=1``。本章generic call一进入就return，不复制字符串，也不再次调用handlers。

这有一个bootconfig边界： ``extra_command_line`` 是051才生成的，不在041首次early parse输入中。
若它包含只注册为early的名字，本章不会补执行；ordinary unknown path会把同名early ``__setup`` entry
认作already-done并consume。bootconfig因此不能倒流改变 ``mem=``、early topology等已经闭合的时间
边界。

``parse_args`` 的工作副本与直接参数表
--------------------------------------

main call在 ``static_command_line`` 上原地运行；它包含可选extra kernel prefix与arch传回的effective
line，不含独立 ``extra_init_args``。 ``next_arg`` 处理空白、 ``=`` 与quotes，返回mutable
``param/val`` pointers； ``-`` 与 ``_`` 在parameter name比较中视为等价。

``parse_one`` 先扫描 ``__start___param..__stop___param`` 的built-in ``struct kernel_param``。level
范围 ``-1..-1`` 选择boot-level parameters；match后检查no-argument flag，在module parameter lock下
执行setter。hardware parameter可能被lockdown拒绝，unsafe flag会taint；bool可无value，其他ops按
类型/范围返回error。handler也可能改变051已经可用的static keys。

每个token前若IRQ disabled，返回后却发现IRQ enabled，parser会warning但不自动关回。fixed raw四项的
actual handlers不打开IRQ，正常出口仍IF=0；这个check是防止有问题的unknown builtin parameter handler
悄悄破坏early-boot invariant。

direct setter error会记录但parser继续扫描
-----------------------------------------

``parse_args`` 遇到 ``-ENOENT/-ENOSPC/other error`` 分别打印unknown/too-large/invalid，并把最后error
保存为 ``ERR_PTR``，但不会立刻停止其余tokens。若later遇到 ``--``，有既存error时返回error pointer
而不是tail；因此 ``start_kernel`` 的 ``!IS_ERR_OR_NULL`` guard会跳过command-line init tail。正常无错
时，没有 ``--`` 返回NULL；有 ``--`` 则返回其后地址。

unknown callback不是“全部交给init”
----------------------------------

direct ``__param`` 未match时进入 ``unknown_bootoption``。它先保存parameter-name长度，再恢复原地被
``next_arg`` 切开的 ``param=value`` 字符串，然后按顺序分类：

* sysctl compatibility alias只在这里被recognize并consume，later ``do_sysctl_args`` 才从命令行正式
  应用；
* ``BOOT_IMAGE=...`` 与 ``kexec`` bootloader identifiers直接忽略；
* ``obsolete_checksetup`` 遍历 ``__setup`` section：early entry只标already handled，non-early entry
  调用其 ``setup_func``，obsolete NULL handler打印并consume；
* parameter name在 ``=`` 前含dot时视为unused module parameter，保留在 ``/proc/cmdline`` 供later
  built-in/module handling，不放进init arrays；
* 剩余 ``name=value`` 写入 ``envp_init``，同名已有environment会被替换；
* 剩余无value token追加 ``argv_init``。

所以“unknown”是最后分类结果，而非报错同义词。 ``unknown_bootoption`` 自身返回0，让main parse继续。

fixed四个raw tokens各自落到明确分支
-----------------------------------

``BOOT_IMAGE=/boot/bzImage`` 命中bootloader prefix后丢弃，不进入PID 1 environment。
``root=/dev/sda1`` 命中 ``__setup("root=",root_dev_setup)``，只把文本复制进64-byte
``saved_root_name``；设备尚未解析/打开/挂载。 ``ro`` 命中readonly handler并设置
``root_mountflags`` 的 ``MS_RDONLY`` bit（它本来就是default，故fixed path为幂等）。

``console=ttyS0`` 在041 early pass还可能命中earlycon console alias，但 ``ttyS0`` 不是raw
``uart...`` earlycon spec，找不到early driver会被容忍；本章ordinary ``console_setup`` 再把tty name、
index与options送入preferred-console table。它不probe 8250、不注册正式console，也不保证字符已输出；
真正 ``console_init`` 在later IRQ enable之后。

仅从known raw tokens看，没有unknown argv/env contribution，也没有 ``--`` tail；但unknown builtin line、
bootconfig kernel/init roots未固定，所以不能把最终 ``argv_init/envp_init`` 写死为defaults。

unknown-options notice发生在explicit init args之前
-----------------------------------------------

kernel-side parse返回后， ``print_unknown_bootoptions`` 检查已由unknown callback加入的
``argv_init[1..]`` 与 ``envp_init[2..]``。没有新增项或已触发capacity ``panic_later`` 就return；否则
从memblock临时分配string，打印“将传给user space”的合并列表，再free该临时block。它不撤销arrays中
的pointers。

该call位于 ``--`` tail与 ``extra_init_args`` 解析之前，因此notice只覆盖kernel-side unknown tokens，
不把用户明确放在init side的tokens误报为unknown kernel options。allocation失败只丢notice，参数仍
保存在arrays。

``--`` tail的每个token都成为argv，不再区分environment
-----------------------------------------------------

无error且有 ``--`` 时，第二次 ``parse_args`` 不传parameter table，扫描到的tokens进入
``set_init_arg``。callback恢复 ``name=value`` 的完整字符串并一律append到 ``argv_init``；所以
``-- FOO=bar`` 是PID 1 argument，不是 ``envp_init`` entry。若tail又含bare ``--``，parser会再次停止，
其返回tail未被caller继续消费。 ``argv_init[0]`` 初始为 ``"init"``，future selected init program会
接收已追加entries。

最后才单独解析 ``extra_init_args``，其中被扫描的tokens也走 ``set_init_arg``（bare ``--`` 同样会让
本次parser停止）。通常的实际append顺序因此是：

.. code-block:: text

   kernel-side unknown no-value argv entries
   → original command-line tokens after --
   → bootconfig extra_init_args

这与051为了显示而构造的saved文本顺序不同：saved text把bootconfig init tokens插在原 ``--`` tail前，
runtime ``argv_init`` 却在tail之后追加它们。display order不能代替执行顺序。

容量超限只登记later panic
-------------------------

``argv_init/envp_init`` 上限来自 ``CONFIG_INIT_ENV_ARG_LIMIT``。unknown callback或 ``set_init_arg`` 超限
时设置 ``panic_later`` 与 ``panic_param``，后续append停止；当前不立刻panic。later ``console_init``
之后 ``start_kernel`` 才以 ``Too many boot ... vars`` panic，使诊断有正式console机会可见。本章出口
因此可能携带pending fatal state，但fixed known raw tokens本身不会触发容量。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``；下一条是 ``random_init_early(command_line)``；
* CPU/mode：logical CPU0，x86-64 CPL0，normal fixed handlers后IF仍为0；
* printed line： ``saved_command_line`` 已按wrap policy输出且未修改；
* early parameters：041首次pass结果保持，本章generic call幂等返回；
* ``static_command_line``：ordinary parse已原地切分，charp等setter pointers可继续引用它；
* direct kernel params/ ``__setup``：actual matches已执行，errors按parser state保留；
* fixed ``BOOT_IMAGE``：已忽略； ``root``/``ro``/``console`` state已记录但未落实设备操作；
* kernel-side unknowns：按sysctl/module/argv/env规则分类，notice已条件打印；
* original ``--`` tail：无parse error时已追加 ``argv_init``；fixed raw line没有tail；
* bootconfig extra init：若存在，已最后追加 ``argv_init``；
* capacity failure：若发生仅登记 ``panic_later``，later console init后panic；
* root filesystem/serial driver/PID1：均未挂载、打开或创建；
* ordinary buddy RAM/slab/scheduler/initramfs：仍未完成。

关键边界
--------

#. saved副本只用于观察；static副本才被ordinary parser原地修改。
#. x86 early pass已经done，051新增bootconfig kernel extras不能补做early effects。
#. ``__param`` direct setter、early ``__setup`` marker与ordinary ``__setup`` handler是三种路径。
#. sysctl alias与dotted module parameter在这里consume但留给later机制，并非立即应用。
#. ``BOOT_IMAGE`` 被忽略；unknown有值/无值才分别进入init env/argv。
#. ``--`` 后 ``name=value`` 也是argv，不是environment。
#. runtime argv顺序是原 ``--`` tail先、bootconfig extra init后；saved display顺序相反。
#. parse error可阻止 ``--`` tail dispatch；capacity error延迟到console init后panic。
#. ``root=``、 ``ro``、 ``console=`` 只建立policy/spec，不完成mount或driver registration。

下一入口
--------

第055章从：

.. code-block:: c

   random_init_early(command_line);

开始。注意传入的是arch ``command_line`` pointer，不是已经拼入所有bootconfig extras的saved副本；随后
large bootmem allocations与 ``mm_core_init`` 才把ordinary RAM交给buddy并启动slab/vmalloc阶段。

资料
----

* `Linux 7.2-rc1固定提交：start_kernel命令行与init args dispatch顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1008-L1024>`_；
* `Linux 7.2-rc1固定提交：print_kernel_cmdline wrapping <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L876-L969>`_；
* `Linux 7.2-rc1固定提交：parse_early_param one-shot guard <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L720-L755>`_；
* `Linux 7.2-rc1固定提交：init arg与unknown bootoption分类 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L462-L561>`_；
* `Linux 7.2-rc1固定提交：unknown-options notice <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L820-L861>`_；
* `Linux 7.2-rc1固定提交：parse_one与parse_args error/-- semantics <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/params.c#L117-L212>`_；
* `Linux 7.2-rc1固定提交：root/ro setup handlers <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/do_mounts.c#L31-L62>`_；
* `Linux 7.2-rc1固定提交：ordinary console setup只登记preferred spec <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c#L2621-L2689>`_。
