第五十一章：Linux 为什么再次检查 static key/static call，并怎样生成正式命令行？
================================================================================

第五十章结束时，``mm_core_init_early()`` 已经建立 node、zone、``struct page`` 和 ``free_area[]`` 等物理内存管理骨架。

``start_kernel()`` 接下来依次调用：

.. code-block:: c

   jump_label_init();
   static_call_init();
   early_security_init();
   setup_boot_config();
   setup_command_line(command_line);

这段流程把三个看似无关的问题连在一起：

* 运行时可修改的分支和调用点必须先可用；
* early LSM 注册 hook 时会使用 static key/static call；
* bootconfig 可能给内核和 ``init`` 增加参数，最终命令行必须在解析前固定下来。

固定 x86 主线还有一个容易遗漏的事实：``setup_arch()`` 早先已经调用过 ``jump_label_init()`` 和 ``static_call_init()``。因此本章开头的两个调用主要是通用 ``start_kernel()`` 顺序中的幂等确认，而不是第二次重写全部 call site。

static key 要解决什么问题
------------------------

内核中存在大量运行时开关，例如：

* tracing 是否启用；
* 调试或安全检查是否启用；
* 某种优化路径是否激活；
* 某类 LSM hook 当前是否有人注册。

普通写法可能是：

.. code-block:: c

   if (feature_enabled)
       slow_path();

即使 ``feature_enabled`` 几乎永远为 false，CPU 仍要反复读取变量并预测分支。

static key 把这种低频改变、高频执行的条件变成可修补机器指令：

.. code-block:: text

   disabled state → hot path 上是一段 NOP
   enabled state  → 把 NOP 改写成 JMP

开关改变时修改一次内核 text，之后每次执行几乎没有普通条件判断成本。

``jump_entry`` 怎样描述一个可修补分支
------------------------------------

链接器把所有 static branch site 收集到：

.. code-block:: text

   __start___jump_table
   ...
   __stop___jump_table

每个 ``struct jump_entry`` 记录：

* 需要修补的指令地址；
* 分支目标；
* 对应 ``struct static_key``；
* 当前 site 是 branch 语义还是 NOP 语义；
* site 是否位于 ``.init`` 区域。

``jump_label_init()`` 会先按 key 排序这些 entry，使同一个 static key 控制的所有 site 连续排列。

首次初始化真正做了什么
--------------------

第一次执行 ``jump_label_init()`` 时，源码会：

#. 锁住 CPU hotplug 读侧和 jump-label 全局锁；
#. 排序 built-in jump table；
#. 对应为 NOP 的 entry 调用架构 text transform；
#. 标记位于 init section 的 site；
#. 让每个 ``static_key`` 指向自己的第一条 ``jump_entry``；
#. 设置 ``static_key_initialized = true``。

在 x86 上，``arch_jump_label_transform_*()`` 会把目标 text 改写成架构定义的 NOP 或跳转指令，并处理 instruction patching 所需的同步。

这不是修改数据变量，而是修改已经加载到内存中的内核机器码。

为什么本章中的 ``jump_label_init()`` 很快返回
-------------------------------------------

固定 x86 路径在 ``setup_arch()`` 前段已经执行：

.. code-block:: c

   jump_label_init();
   static_call_init();

原因是 x86 架构初始化本身可能很早就需要 static key/static call。

现在回到通用 ``start_kernel()`` 再次调用时，``jump_label_init()`` 首先检查：

.. code-block:: c

   if (static_key_initialized)
       return;

所以本章当前位置不会重新排序 jump table，也不会再次遍历和重写全部 NOP/JMP。

通用入口仍保留这次调用，因为并非所有架构都像 x86 一样在 ``setup_arch()`` 内提前初始化。

static call 与 static key 的区别
------------------------------

static key 优化的是条件分支。

static call 优化的是目标函数可变的调用点。

普通函数指针调用：

.. code-block:: c

   ops->func(arg);

需要从内存读取目标地址，再执行间接 ``call``。间接分支会影响预测，也可能受到 retpoline 或其他间接调用缓解机制的额外开销。

static call 把 call site 直接修补成：

.. code-block:: text

   call current_target

当目标函数改变时，再统一改写所有相关 call site。

它适合目标偶尔变化、调用非常频繁的接口，例如架构操作、调度或安全 hook 快路径。

static call table 怎样关联 key 与 call site
-----------------------------------------

链接器收集：

.. code-block:: text

   __start_static_call_sites
   ...
   __stop_static_call_sites

每个 ``static_call_site`` 保存相对编码的：

* call instruction 地址；
* ``static_call_key``；
* tail-call 标志；
* init-section 标志。

首次 ``static_call_init()`` 会：

#. 按 key 排序 site；
#. 标记 init text 中的调用点；
#. 把 built-in key 与它的第一条 site 关联；
#. 调用 ``arch_static_call_transform()``，把 call site 指向 key 当前目标；
#. 注册 module notifier，使以后装卸模块时能加入或移除模块 call site；
#. 设置 ``static_call_initialized = 1``。

为什么 built-in 初始化不依赖 slab
--------------------------------

当前 slab allocator 尚未建立。

``__static_call_init()`` 对 vmlinux 内建 site 不分配额外链表对象，而是直接把第一条 site 指针编码到 key 中。模块出现以后，slab 已可用，才为 module site 分配 ``struct static_call_mod``。

这使 x86 可以在非常早期初始化 static call，而不需要 ``kmalloc()``。

本章中的 ``static_call_init()`` 同样是幂等确认
--------------------------------------------

函数开头检查：

.. code-block:: c

   if (static_call_initialized == 1)
       return 0;

固定 x86 主线早已完成首次初始化，因此这里直接返回。

一个特殊接口 ``static_call_force_reinit()`` 可以把状态递增，使后续初始化重新执行；当前主线没有调用它。

为什么 LSM 必须排在这两个入口之后
--------------------------------

接下来：

.. code-block:: c

   early_security_init();

LSM（Linux Security Modules）让多个安全模块向统一 hook 点注册回调，例如文件打开、凭据变更、进程执行或 BPF 操作。

Linux 6.12 的 LSM hook 快路径使用 static call 与 static branch：

.. code-block:: text

   没有 hook 使用某槽位
   → static branch 关闭
   → 热路径跳过调用

   LSM 注册 hook
   → static call 指向该 hook
   → static branch 开启

因此 static key/static call 基础必须先完成，否则 early LSM 无法安全安装优化后的 hook。

``early_security_init()`` 不是完整安全系统初始化
---------------------------------------------

函数只遍历链接器区间：

.. code-block:: text

   __start_early_lsm_info
   ...
   __end_early_lsm_info

对每个 early LSM，它依次：

#. 标记为 enabled；
#. 加入 LSM order；
#. 计算该 LSM 请求的 security blob 大小和偏移；
#. 执行该 LSM 的 early init；
#. 增加 early LSM 计数。

这里还没有完成：

* 普通 LSM 的最终排序与初始化；
* SELinux policy 文件加载；
* AppArmor profile 加载；
* root filesystem 上的安全标签读取；
* 用户空间安全服务启动。

普通 ``security_init()`` 和各 LSM 后续 initcall 仍在更后面。

security blob 为什么要提前计算布局
--------------------------------

多个 LSM 可能都需要在同一个内核对象后附加私有安全数据，例如：

.. code-block:: text

   cred security blob
   inode security blob
   file security blob
   task security blob
   socket security blob

内核不会为每个 LSM 在对象中固定添加一根独立指针。LSM framework 汇总各模块请求的大小，按指针对齐计算偏移，最终分配一个组合 blob。

``lsm_prepare()`` 在对象 cache 建立前确定这些尺寸，后续 slab cache 才能按正确对象大小创建。

``security_add_hooks()`` 怎样使用 static call
-------------------------------------------

early LSM 的 init 若注册 hook，``security_add_hooks()`` 会为每条 hook 找到一个未使用的 static-call 槽位：

.. code-block:: c

   __static_call_update(key, trampoline, hook_function);
   static_branch_enable(active_key);

这样安全 hook 从通用链表间接遍历，转成可预测的 static branch 加直接 call。

每个 hook 类型的槽位数量有限；全部耗尽时内核会 panic，因为继续运行会丢失声明需要启用的安全检查。

``setup_boot_config()`` 为什么要读取 initramfs 尾部
------------------------------------------------

安全早期基础完成后：

.. code-block:: c

   setup_boot_config();

bootconfig 是比传统单行 kernel command line 更适合表达层次化配置的 XBC 数据。

bootloader 可以把 bootconfig 附加在 initramfs 末尾，布局近似：

.. code-block:: text

   [original initramfs]
   [bootconfig data]
   [u32 data size]
   [u32 checksum]
   [BOOTCONFIG magic]

GRUB 可能把 initrd 大小对齐到 4 字节，所以 Linux 会从 ``initrd_end`` 前最后四个候选位置搜索 magic。

bootconfig 不属于 cpio payload
----------------------------

找到合法 trailer 后，内核校验：

* size 没有越过 ``initrd_start``；
* checksum 与数据一致；
* 数据不超过 XBC 最大尺寸。

随后最关键的一步是：

.. code-block:: c

   initrd_end = (unsigned long)bootconfig_data;

也就是把 bootconfig 从 initramfs 的逻辑末端裁掉。

以后解包 initramfs 时，cpio 解包器只看到原始归档，不会把 bootconfig trailer 当作损坏的归档内容。

即使内核未启用 ``CONFIG_BOOT_CONFIG``，它仍会尝试识别并移除 trailer；只是不会解析 XBC 内容。

什么时候真正采用 bootconfig 参数
--------------------------------

启用 ``CONFIG_BOOT_CONFIG`` 时，内核还会检查命令行是否包含：

.. code-block:: text

   bootconfig

或者构建是否启用强制 bootconfig。

满足条件后，``xbc_init()`` 解析树形配置，并把两个命名空间转换成普通字符串：

.. code-block:: text

   kernel.* → extra_command_line
   init.*   → extra_init_args

固定主线命令行是：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

其中没有 ``bootconfig``。同时本书没有规定 initramfs 尾部附带 bootconfig，因此固定控制流不会假定存在额外 kernel/init 参数。

``setup_command_line()`` 为什么需要两份命令行
------------------------------------------

随后调用：

.. code-block:: c

   setup_command_line(command_line);

此前存在的 ``boot_command_line`` 和架构传回的 ``command_line`` 位于启动期静态缓冲，后面的参数解析会原地写入 NUL、拆分 name/value，并可能保留指向字符串内部的指针。

内核因此使用 memblock 分配两份持久副本：

.. code-block:: text

   saved_command_line
   static_command_line

``saved_command_line`` 保存可供日志、``/proc/cmdline`` 和诊断使用的完整原貌。

``static_command_line`` 是允许 ``parse_args()`` 原地修改的工作副本。

为什么不能只解析原始缓冲
----------------------

参数解析通常会把：

.. code-block:: text

   root=/dev/sda1

临时变成：

.. code-block:: text

   root\0/dev/sda1\0

并让 setup handler 接收 ``param`` 与 ``val`` 指针。

若只保留这一份，之后无法可靠显示用户实际传入的完整命令行；某些 handler 保存的指针也可能在 init memory 回收后失效。

所以内核在 memblock 仍可用时，为命令行申请不会被早期静态缓冲覆盖的存储。

bootconfig 参数如何并入最终顺序
-----------------------------

若存在 ``extra_command_line``，它被放在 bootloader command line 前面：

.. code-block:: text

   [bootconfig kernel parameters][bootloader kernel parameters]

这样 bootloader 命令行中用于分隔 init 参数的 ``--`` 不会提前截断 bootconfig kernel 参数。

若存在 ``extra_init_args``，则以：

.. code-block:: text

   " -- "

加入保存命令行的 init 参数部分，并维护 bootconfig init 参数与命令行 init 参数的正确先后关系。

当前固定主线最终得到的核心内容仍是：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

具体内存地址由 memblock 在当次启动的物理布局中选择，本书不虚构固定地址。

此时仍没有正式解析普通参数
------------------------

``setup_command_line()`` 只建立最终字符串和副本。

下一阶段才会执行：

.. code-block:: text

   print_kernel_cmdline(saved_command_line)
   parse_early_param()
   parse_args("Booting kernel", static_command_line, ...)

所以此刻 ``root=``、``ro`` 等普通参数尚未在通用 parser 中全部分发。

部分 early parameter 已在 ``setup_arch()`` 阶段解析过；后面的 ``parse_early_param()`` 是幂等入口，不会重复执行已完成的 early parse。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``setup_command_line(command_line)`` 已返回，``setup_nr_cpu_ids()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* interrupts：关闭；
* static key：固定 x86 主线早已初始化，本章调用完成幂等确认；
* static call：固定 x86 主线早已初始化，本章调用完成幂等确认；
* early LSM：已遍历、准备 blob 布局并执行 early init；
* 普通 LSM/policy：尚未完成；
* bootconfig：已完成 trailer 搜索与条件解析；
* initramfs：若尾部带 bootconfig，``initrd_end`` 已裁掉该 trailer；归档仍未解包；
* ``saved_command_line``：已建立不可供 parser 破坏的完整副本；
* ``static_command_line``：已建立可原地解析的工作副本；
* memblock：仍为上述副本提供启动期分配；
* per-CPU area：尚未建立；
* scheduler：尚未初始化；
* AP：尚未唤醒。

下一条控制流是：

.. code-block:: c

   setup_nr_cpu_ids();

资料
----

* `Linux 6.12.95 init/main.c：static key、LSM、bootconfig 与命令行调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 jump_label.c：jump table 排序、NOP 修补与幂等状态 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/jump_label.c>`_
* `Linux 6.12.95 static_call_inline.c：built-in call-site 关联与 static_call_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/static_call_inline.c>`_
* `Linux 6.12.95 x86 setup.c：setup_arch 中更早的 jump_label_init/static_call_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 lsm_init.c：early LSM、blob 布局与 static-call hook <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/lsm_init.c>`_
* `Linux bootconfig 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/admin-guide/bootconfig.rst>`_
* `Linux static keys 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/staging/static-keys.rst>`_
* `Linux static calls 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/staging/static-calls.rst>`_