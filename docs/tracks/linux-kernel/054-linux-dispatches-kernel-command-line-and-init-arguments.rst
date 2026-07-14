第五十四章：Linux 怎样把 GRUB 命令行分发给内核参数和 init？
================================================================

第五十三章结束时，CPU0 已经拥有完整的 per-CPU NUMA 与 hotplug 初始状态。

``start_kernel()`` 接下来执行：

.. code-block:: c

   print_kernel_cmdline(saved_command_line);
   parse_early_param();
   after_dashes = parse_args("Booting kernel", ...);
   print_unknown_bootoptions();
   parse_args("Setting init args", after_dashes, ...);
   parse_args("Setting extra init args", extra_init_args, ...);

本章追踪到所有 kernel command line 与 init arguments 分发完成，``random_init_early()`` 尚未调用。

命令行最初是谁提供的
------------------

固定启动路径中的 ``grub.cfg`` 包含：

.. code-block:: cfg

   linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
   initrd /boot/initramfs-6.12.95.img

GRUB 的 ``linux`` 命令把：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

写入 Linux boot protocol 的 command-line buffer，并在 ``boot_params.hdr.cmd_line_ptr`` 等字段中告诉内核该字符串位于哪里。

Linux 进入 ``setup_arch()`` 后已经把字符串复制进 ``boot_command_line``，处理 bootconfig 后又建立：

``saved_command_line``
   保留一份完整、可供日志和后续 ``/proc/cmdline`` 使用的命令行。

``static_command_line``
   供参数解析器原地切分和修改的工作副本。

现在 ``start_kernel()`` 才开始把其中每个 token 交给对应子系统。

为什么先打印 ``saved_command_line``
---------------------------------

调用为：

.. code-block:: c

   print_kernel_cmdline(saved_command_line);

打印的是保存副本，而不是即将被解析器修改的 ``static_command_line``。

参数解析器会把空格、等号和引号处理成独立的 ``param``、``val`` 字符串，部分字符会被临时替换为 ``NUL``。若直接打印工作副本，日志可能只能看到第一段或已经被切碎的内容。

``print_kernel_cmdline()`` 还会按照 ``CONFIG_CMDLINE_LOG_WRAP_IDEAL_LEN`` 尝试在空格处分行，使很长的启动参数不会形成一条难以阅读的日志。

日志中的命令行不表示参数已经生效。打印完成后，分发才真正开始。

为什么又调用一次 ``parse_early_param()``
--------------------------------------

``early_param()`` 注册的参数必须在内存、CPU 拓扑和其他早期初始化前生效，例如：

.. code-block:: text

   mem=
   numa=
   nosmp
   nr_cpus=
   maxcpus=
   loglevel=
   quiet
   mitigations=
   init_on_alloc=

x86 ``setup_arch()`` 已经在更早阶段调用过 ``parse_early_param()``。

该函数内部有静态 ``done`` 标志：

.. code-block:: c

   if (done)
       return;

所以固定路径中，``start_kernel()`` 此处的调用主要是跨架构保险点，不会再次执行所有 early parameter handler。

这与前面的 ``jump_label_init()``、``static_call_init()`` 类似：通用代码保证调用顺序成立，具体架构若已经提前完成，幂等检查直接返回。

三类参数注册机制必须分开
----------------------

Linux 启动参数并非全部进入同一张表。

``early_param("name", fn)``
   极早参数。由 ``parse_early_param()`` 扫描 ``__setup`` section 中标记为 early 的项目。

``__setup("name=", fn)``
   传统启动参数。它们通过 ``unknown_bootoption()`` 内的 ``obsolete_checksetup()`` 匹配并执行。

``core_param``、``module_param`` 等
   编译时生成 ``struct kernel_param``，链接进 ``__param`` section。通用 ``parse_args()`` 会直接在这张表中查找。

同一个命令行从左到右扫描时，参数可能由上述任一机制消费。

不能把“没有在 ``__param`` 表中找到”直接理解为“未知参数”，因为它仍可能是合法的 ``__setup`` 参数。

``parse_args()`` 收到什么
------------------------

主调用为：

.. code-block:: c

   after_dashes = parse_args("Booting kernel",
                             static_command_line,
                             __start___param,
                             __stop___param - __start___param,
                             -1, -1, NULL,
                             &unknown_bootoption);

关键输入包括：

* ``static_command_line``：允许原地修改的参数字符串；
* ``__start___param`` 至 ``__stop___param``：内建 kernel parameters 表；
* level 范围 ``-1`` 至 ``-1``：处理普通 boot-time 内建参数；
* ``unknown_bootoption``：直接参数表没有匹配时的后备处理函数。

``next_arg()`` 怎样切分 token
---------------------------

``parse_args()`` 循环调用：

.. code-block:: c

   args = next_arg(args, &param, &val);

典型输入：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

会依次得到近似结果：

.. code-block:: text

   param="root"     val="/dev/sda1"
   param="ro"       val=NULL
   param="console"  val="ttyS0"

解析器支持引号，因此值中包含空格时不会简单地按每个空格截断。

切分是原地完成的，这也是 ``static_command_line`` 必须长期保留的原因之一。某些早期 ``charp`` 参数在 slab 尚不可用时不会复制字符串，只保存指向该工作 buffer 的指针。

直接匹配 ``struct kernel_param``
--------------------------------

``parse_one()`` 首先遍历 ``__param`` 表：

.. code-block:: c

   if (parameq(param, params[i].name))
       params[i].ops->set(val, &params[i]);

匹配成功后，对应 ``param_ops`` 把文本转换成目标类型，例如：

* ``bool``；
* ``int``、``uint``、``ulong``；
* 字符串；
* 子系统自定义 setter。

参数 setter 在这里可以修改全局变量、static key 或启动策略。

源码因此在调用前注明：

.. code-block:: c

   /* parameters may set static keys */

static key 基础必须已经初始化，否则参数 handler 无法安全启用或关闭相应快速路径。

参数为什么可能没有值
------------------

``ro`` 这样的 token 没有 ``=``，所以 ``val == NULL``。

某些布尔参数允许无值形式，并把它解释为启用；另一些参数必须提供值。``parse_one()`` 会检查参数操作是否带有 ``KERNEL_PARAM_OPS_FL_NOARG``，缺少必需值时返回 ``-EINVAL``。

因此：

.. code-block:: text

   feature

可能对布尔开关合法，而：

.. code-block:: text

   log_buf_len

若要求数值却没有 ``=value``，会被判定为无效。

``unknown_bootoption()`` 不是简单报错
-----------------------------------

若 ``__param`` 表没有匹配，``parse_one()`` 调用：

.. code-block:: c

   unknown_bootoption(param, val, ...);

它按顺序进行多类判断。

内核 sysctl 别名
^^^^^^^^^^^^^^^

若参数是某个 sysctl 的命令行别名，由对应机制处理，不再传给用户空间。

bootloader 标识
^^^^^^^^^^^^^^^

``BOOT_IMAGE=...`` 和 ``kexec`` 等 bootloader 标识被识别后忽略。

它们可用于记录启动来源，不应成为 PID 1 的参数或环境变量。

传统 ``__setup`` 参数
^^^^^^^^^^^^^^^^^^^^

``obsolete_checksetup()`` 遍历 ``__setup`` section。

若找到非 early handler，调用其 ``setup_func``。固定命令行中的 ``root=``、``ro``、``console=`` 等选项会由相应的内核启动处理器消费，建立根文件系统策略、只读挂载状态和控制台选择，而不是原样交给 ``init``。

函数名字带有 ``obsolete`` 是历史遗留，不能据此认为所有 ``__setup`` 参数都已废弃。大量核心启动选项仍使用该机制。

模块参数形式
^^^^^^^^^^^^

若参数名中包含点号，例如：

.. code-block:: text

   driver.option=value

而对应驱动尚未初始化，当前代码通常保留它，后续模块或内建模块初始化阶段再处理。这里不会立即把它塞入 PID 1 参数。

真正未知的 ``name=value``
^^^^^^^^^^^^^^^^^^^^^^^^

若仍无人消费且带有值，它被放入：

.. code-block:: c

   envp_init[]

也就是未来 PID 1 的环境变量。

例如：

.. code-block:: text

   MYMODE=maintenance

可能最终以环境变量形式传给 init。

真正未知的无值 token
^^^^^^^^^^^^^^^^^^^

若没有值，则进入：

.. code-block:: c

   argv_init[]

它将成为 PID 1 的命令行参数。

参数数量为何只记录延迟 panic
--------------------------

``argv_init`` 和 ``envp_init`` 容量由 ``CONFIG_INIT_ENV_ARG_LIMIT`` 限制。

超过限制时，代码记录：

.. code-block:: c

   panic_later = "init";  /* 或 "env" */
   panic_param = param;

当前阶段未必立刻 panic，因为早期控制台和日志设施仍未完整建立。``console_init()`` 之后，``start_kernel()`` 会检查 ``panic_later``，届时给出更可见的错误。

``--`` 是内核与 init 的明确分界
--------------------------------

``parse_args()`` 遇到：

.. code-block:: text

   --

会停止当前解析并返回其后字符串的地址：

.. code-block:: c

   if (!val && strcmp(param, "--") == 0)
       return err ?: args;

所以命令行：

.. code-block:: text

   root=/dev/sda1 ro -- single rescue

被分成：

.. code-block:: text

   kernel side:
       root=/dev/sda1
       ro

   init side:
       single
       rescue

``--`` 后面的 token 不再尝试匹配 kernel parameter 或 ``__setup`` handler。

``set_init_arg()`` 怎样建立 PID 1 argv
-----------------------------------

若 ``after_dashes`` 非空，``start_kernel()`` 调用：

.. code-block:: c

   parse_args("Setting init args", after_dashes,
              NULL, 0, -1, -1, NULL, set_init_arg);

这里参数表为空，每个 token 都进入 ``set_init_arg()``。

``argv_init`` 初始为：

.. code-block:: c

   { "init", NULL }

后续 token 从索引 1 开始追加。

最终启动 PID 1 时，内核选择 ``/init``、``init=`` 指定路径或系统默认 init 程序，并把这个数组作为 ``argv`` 传入。

bootconfig 的 ``init.*`` 参数排在哪里
------------------------------------

第五十一章已经说明，bootconfig 可以产生：

``extra_command_line``
   来自 ``kernel.*`` 节点，拼到内核命令行前部。

``extra_init_args``
   来自 ``init.*`` 节点，专门交给 PID 1。

普通 ``--`` 后参数处理完后，``start_kernel()`` 再执行：

.. code-block:: c

   if (extra_init_args)
       parse_args("Setting extra init args", extra_init_args,
                  NULL, 0, -1, -1, NULL, set_init_arg);

所以 bootconfig 中的 init arguments 与 GRUB 命令行 ``--`` 后的参数都会进入 ``argv_init``，但来源和拼接位置是明确控制的。

固定命令行最终形成什么
--------------------

本书固定命令行没有 ``--``，也没有额外 bootconfig init 参数：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

因此当前阶段的主要结果是：

* 根设备选择信息被内核保存；
* 初始根文件系统按只读方式挂载；
* 串口控制台参数被控制台子系统保存；
* 没有新增 PID 1 命令行参数；
* ``argv_init`` 仍以默认 ``"init"`` 开头；
* ``envp_init`` 仍至少包含 ``HOME=/`` 和 ``TERM=linux``。

这里尚未挂载 ``/dev/sda1``，也尚未打开串口驱动。

参数解析只是把字符串转换为后续子系统要使用的状态。真正挂载根文件系统和初始化控制台发生在更晚阶段。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``extra_init_args`` 条件解析已完成，``random_init_early(command_line)`` 尚未调用；
* CPU：仍只有 CPU0 online；
* interrupts：关闭；
* GRUB 提供的 command line：已打印并完成内核侧分发；
* early parameters：固定 x86 路径此前已执行，本处幂等返回；
* kernel parameters：已通过 ``__param`` 表和 setter 处理；
* ``__setup`` 参数：已通过 ``unknown_bootoption()`` 后备路径处理；
* 真正未知参数：已按有值/无值分别准备进入 PID 1 环境和参数；
* ``--`` 后参数：若存在，已进入 ``argv_init``；
* ``root=/dev/sda1``：已保存为后续根挂载策略，根文件系统尚未挂载；
* ``console=ttyS0``：已保存为控制台选择，正式 console 尚未初始化；
* buddy：尚未接收全部普通 RAM；
* slab、scheduler：尚未初始化；
* initramfs：尚未解包；
* 用户空间：尚未创建。

下一条控制流是：

.. code-block:: c

   random_init_early(command_line);

资料
----

* `Linux 6.12.95 init/main.c：命令行打印、early 参数和 init 参数分发 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/params.c：parse_args 与 parse_one <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/params.c>`_
* `Linux 6.12.95 include/linux/moduleparam.h：kernel parameter 描述结构与注册宏 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/moduleparam.h>`_
* `Linux 6.12.95 init/do_mounts.c：root 与只读根挂载启动参数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/do_mounts.c>`_
* `Linux 6.12.95 kernel/printk/printk.c：console 启动参数处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c>`_