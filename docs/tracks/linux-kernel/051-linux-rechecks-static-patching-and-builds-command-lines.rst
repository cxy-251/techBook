第五十一章：Linux 为什么复查静态修补并建立两份正式命令行？
================================================================

第五十章结束时，CPU0仍在 ``start_kernel``、IF=0；node、zone、 ``struct page`` 与buddy containers
已经建立，但普通RAM尚未由memblock交给buddy。当前连续入口是：

.. code-block:: c

   jump_label_init();
   static_call_init();
   early_security_init();
   setup_boot_config();
   setup_command_line(command_line);

fixed x86路径在041的 ``setup_arch`` 前段已经执行过前两项。本章的generic calls因此是幂等复查，随后
early LSM才安装其早期hooks；bootconfig可能产生额外kernel/init参数，最后以memblock分配一份保留
原貌的 ``saved_command_line`` 和一份供later就地解析的 ``static_command_line``。本章只建立字符串，
尚不执行普通kernel parameter或init argument dispatch。

generic jump-label call在fixed x86上立即返回
----------------------------------------------

首次 ``jump_label_init`` 会在CPU hotplug读锁和jump-label锁下排序built-in ``__jump_table``，把需要
disabled形态的sites改写为NOP，标记init-section sites，并让每个 ``static_key`` 指向自己的首条
``jump_entry``；完成后发布 ``static_key_initialized=true``。

这里的“修改key”不是普通变量分支：site是kernel text中的NOP/JMP patch point，低频切换承担text
rewrite成本，让高频disabled path不必反复load一个boolean。具体instruction sequence与同步规则由x86
arch transform实现。

但fixed路径在 ``setup_arch`` 中已经完成上述首次初始化。本次function entry先读取
``static_key_initialized``，见true便直接return；不取得两把锁，不重新排序table，也不再次改写text。
generic ``start_kernel`` 保留这个call，是为了同一初始化顺序覆盖没有arch-early call的架构。

generic static-call call也只确认既有状态
-----------------------------------------

static call解决的是高频可变函数目标：链接器记录call sites，初始化时把indirect-style dispatch修补为
当前direct target；目标低频变化时再批量patch。它与static key的conditional branch不是一回事。

首次 ``static_call_init`` 会锁住CPU hotplug与static-call global state，对built-in
``__start_static_call_sites..__stop_static_call_sites`` 执行 ``__static_call_init``；modules build还注册
notifier，使later module sites能加入/撤销。失败不是可忽略降级：它打印错误并 ``BUG()``，成功后把
``static_call_initialized`` 置1。

fixed x86同样已在041做完首次call；本次入口检查值恰为1便返回0。 ``start_kernel`` 忽略其int return，
但在此路径返回值为成功；也没有调用会强制reinit的 ``static_call_force_reinit``，所以不能描述成第二轮
site patching。

early LSM在静态修补基础之后登记
--------------------------------

``early_security_init`` 遍历链接器登记的early LSM infos。每个entry依次被enable，名字追加到
``lsm_order`` 的 ``early`` 组，经过 ``lsm_prepare`` 后由 ``lsm_init_single`` 调用模块init，最后
``lsm_count_early`` 加一。LSM添加hooks时可借助已经可用的static call/branch slots优化security hot
paths，这正是源码把两种patching明确放在early security之前的原因。

具体early LSM集合取决于 ``.config`` 与link result，不能凭固定源码写死模块名单；没有entry时loop可
为空。function当前总是return 0， ``start_kernel`` 也没有检查返回值；这只完成early group，不是后面
``security_init`` 对ordinary LSMs、policy/userspace loading的完整安全子系统初始化。

bootconfig trailer先从initrd逻辑末端切走
-----------------------------------------

``setup_boot_config`` 的首要边界不只是“是否启用参数”。在 ``CONFIG_BOOT_CONFIG`` build中，它先调用
``get_boot_config_from_initrd(&size)``；若initrd存在，就从 ``initrd_end`` 前寻找bootconfig magic，并
额外检查前3字节以容忍GRUB 4-byte alignment。找到后读取magic前的little-endian size/checksum，验证
数据仍在 ``initrd_start..initrd_end`` 内且checksum相符，最后把 ``initrd_end`` 截到data开头。

这一步把有效bootconfig trailer从later initramfs payload范围剥离，甚至command line没有
``bootconfig`` 时也会做。若magic/header/checksum无效，函数报告相应错误或返回NULL，不改变payload
末端。 ``CONFIG_BLK_DEV_INITRD`` 未启用时helper恒为NULL； ``CONFIG_BOOT_CONFIG`` 未启用时的stub仍
调用helper以切除可能存在的有效trailer，却不解析树。

initrd没有trailer时，enabled build再尝试builtin embedded bootconfig。选择数据来源只决定候选data，
不等于已经接受它。

是否解析由bootconfig开关或force build决定
--------------------------------------------

enabled build把 ``boot_command_line`` 复制到固定大小temporary buffer，用一次local ``parse_args`` 只
寻找 ``bootconfig`` token。若parse在 ``--`` 停下，还保存对应 ``initargs_offs``；没有该token且build
也未启用 ``CONFIG_BOOT_CONFIG_FORCE``，便直接return，即使trailer已经从initrd末端切走。

要求解析但没有data时只报告并return。有data时还要小于 ``XBC_DATA_MAX`` 且通过 ``xbc_init``；成功
才从 ``kernel`` root生成 ``extra_command_line``，从 ``init`` root生成 ``extra_init_args``。二者由
memblock分配，可能各自为NULL（相应root不存在、输出为空或分配/格式化失败）。

fixed GRUB原始命令行没有 ``bootconfig``，但kernel ``.config``、embedded data和initramfs trailer
contents没有固定，因此不能把此场景写死为no-op，也不能臆造extra参数。此时initramfs仍未ordinary
unpack；只可能调整它的logical end并解析附加的XBC data。

两种输入命令行已有不同语义
----------------------------

041从 ``setup_arch(&command_line)`` 带回的 ``command_line`` 指向arch选择并复制好的effective kernel
line；global ``boot_command_line`` 保留供未来引用的boot line。fixed GRUB交给Linux的原始字符串是：

.. code-block:: text

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

若build含 ``CONFIG_CMDLINE``，041已经按append或override policy改变effective结果，所以本章不能只凭
GRUB字符串写死两者的最终内容。 ``setup_command_line`` 也不再次执行该policy，只消费现成的两个
inputs与可选bootconfig extras。

saved副本保留完整可观察命令行
--------------------------------

``setup_command_line`` 先计算extra kernel string长度 ``xlen``。若有extra init string，则先
``strim`` 去除尾空白，并为可能需要的 ``" -- "`` 额外计四字节。它按cache-line alignment从memblock
用 ``memblock_alloc_or_panic`` 分配 ``saved_command_line``；allocation失败会panic，不存在继续使用
NULL的路径。

extra kernel string必须前置，再复制 ``boot_command_line``。前置而非附加，是为了其中若存在
``--``，不会被原命令行更早的separator遮蔽。若有extra init args：

* 原boot line已有 ``--`` 时，把bootconfig init参数插在原command-line init参数之前；
* 原line没有 ``--`` 时，在saved末尾补 ``" -- "`` 后附加bootconfig init参数。

所以init侧顺序固定为bootconfig init参数在前、command-line init参数在后。最终
``saved_command_line_len`` 记录字符串长度。这份副本供打印、 ``/proc/cmdline`` 等later observers
保留完整语义，不作为本章的就地parameter tokenization对象。

static副本只承载待解析的kernel line
-------------------------------------

第二份 ``static_command_line`` 以 ``xlen + strlen(command_line) + 1`` 单独memblock分配，同样失败即
panic；内容是 ``extra_command_line`` 前缀加arch传回的 ``command_line``。它没有把
``extra_init_args`` 拼进去，因为后者later通过独立 ``parse_args("Setting extra init args", ...)``
送给init argv。

两份allocation也没有让字符串进入slab：memblock仍是owner。当前 ``setup_command_line`` return后，
``static_command_line`` 仍未被破坏；later第054章的 ``parse_args("Booting kernel", ...)`` 才会原地切
name/value，并把 ``--`` 后部分送给init argument parser。更早的 ``parse_early_param`` 也是later call，
尽管041/042已有arch-triggered one-shot early parse。

出口停在CPU数量收缩之前
------------------------

``setup_command_line`` return后， ``start_kernel`` 的下一条是 ``setup_nr_cpu_ids``。当前possible CPU
mask来自048，但generic ``nr_cpu_ids`` 尚未按最后possible bit收缩；per-CPU areas尚未分配，CPU0也
尚未迁移到正式per-CPU base。CPU0仍是唯一online/active executor，IF仍为0，没有schedule或AP启动。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``；
* precise next： ``setup_nr_cpu_ids()`` 尚未调用；
* CPU/mode：logical CPU0，x86-64 long mode，IF=0，只有CPU0 online/active；
* jump labels/static calls：arch-early初始化仍有效，generic calls均幂等返回；
* early LSM：linked early entries已按顺序初始化，具体集合由build决定；
* bootconfig trailer：若有效则已从initrd logical end切除；是否解析/生成extras按config与token决定；
* fixed raw GRUB line：含 ``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``；
* ``saved_command_line``：extra kernel前缀、boot line及可选init extras的完整副本已建立；
* ``static_command_line``：extra kernel前缀与arch effective line的mutable副本已建立；
* command-line dispatch：ordinary kernel parameters与init args均未解析；
* memory owner：两份字符串和可选extras仍由memblock承载；普通RAM尚未free-to-buddy；
* per-CPU/scheduler/AP：尚未初始化或启动；initramfs尚未ordinary unpack。

关键边界
--------

#. fixed x86本章的两项static初始化是状态复查，不是第二轮text patch。
#. static key优化条件分支，static call优化可变函数目标；二者不能合并描述。
#. ``early_security_init`` 只处理early LSM group，不代表完整security/policy初始化。
#. 有效bootconfig trailer的切除与是否接受/解析bootconfig是两个边界。
#. fixed raw GRUB line已知，但builtin append/override、bootconfig extras与build config未知。
#. extra kernel参数前置；extra init参数位于 ``--`` 后且排在原init参数之前。
#. ``saved_command_line`` 保存完整可观察文本； ``static_command_line`` 留给later就地kernel parse。
#. 本章分配字符串但不分发参数，也不因此执行 ``root=``、 ``console=`` 或init argv效果。
#. ``setup_nr_cpu_ids``、per-CPU areas和CPU0迁移均属于下一章。

下一入口
--------

第052章从：

.. code-block:: c

   setup_nr_cpu_ids();

开始，随后建立per-CPU areas并由 ``smp_prepare_boot_cpu`` 把CPU0接入正式per-CPU环境；参数dispatch继续
留到第054章。

资料
----

* `Linux 7.2-rc1固定提交：start_kernel从静态修补到命令行副本的顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L971-L1005>`_；
* `Linux 7.2-rc1固定提交：x86 setup_arch提前初始化jump label与static call <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L927-L941>`_；
* `Linux 7.2-rc1固定提交：jump_label_init幂等guard与首次table处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/jump_label.c#L525-L560>`_；
* `Linux 7.2-rc1固定提交：static_call_init状态与module notifier <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/static_call_inline.c#L495-L523>`_；
* `Linux 7.2-rc1固定提交：early LSM遍历与初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/lsm_init.c#L382-L400>`_；
* `Linux 7.2-rc1固定提交：bootconfig trailer与XBC command-line生成 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L271-L430>`_；
* `Linux 7.2-rc1固定提交：saved/static command-line allocation与ordering <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L598-L658>`_。
