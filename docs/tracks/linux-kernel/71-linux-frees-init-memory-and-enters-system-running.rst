第七十一章：Linux 怎样释放 __init 内存并进入 SYSTEM_RUNNING？
============================================================

第七十章结束时，PID 1 已经完成 ``kernel_init_freeable()``：AP、workqueue、SMP scheduler、driver model 和全部 built-in initcall 已运行，initramfs 处理与 root 路径选择也已完成。

当前执行者仍是 PID 1，仍在内核态执行 ``kernel_init()``。下一段控制流是：

.. code-block:: c

   async_synchronize_full();

   system_state = SYSTEM_FREEING_INITMEM;
   kprobe_free_init_mem();
   ftrace_free_init_mem();
   kgdb_free_init_mem();
   exit_boot_config();
   free_initmem();
   mark_readonly();
   pti_finalize();

   system_state = SYSTEM_RUNNING;
   numa_default_policy();
   rcu_end_inkernel_boot();
   do_sysctl_args();

本章追踪到 ``do_sysctl_args()`` 返回，停在 PID 1 选择用户态 init 程序之前。这里完成的是“启动期内核”向“正常运行内核”的状态交接。

``async_synchronize_full()`` 汇合全部异步初始化
------------------------------------------------

``wait_for_initramfs()`` 只等待 initramfs 专属 async domain。其他 initcall、driver probe 或 subsystem 仍可能通过 async framework 排队工作。

``async_synchronize_full()`` 等待全局 async 队列中已经登记的工作完成。它建立一个关键保证：后续释放 ``__init`` text/data 时，不再有异步回调仍准备执行其中的函数。

必须区分：

.. code-block:: text

   do_initcalls() returned
   ≠ every asynchronous callback finished

   async_synchronize_full() returned
   = previously queued async initialization has reached the barrier

这个屏障也不意味着系统从此没有 workqueue、timer 或异步 I/O。它只收束启动阶段需要在回收 init memory 前完成的 async 初始化。

为什么先设置 ``SYSTEM_FREEING_INITMEM``
--------------------------------------

PID 1 随后写入：

.. code-block:: c

   system_state = SYSTEM_FREEING_INITMEM;

``system_state`` 是全局阶段标志。此值告诉调试器、allocator、module、RCU 和其他 subsystem：

* 普通启动初始化已经完成；
* 正在销毁只供 boot 使用的 section；
* 还没有正式宣布 ``SYSTEM_RUNNING``；
* 任何继续引用 ``__init`` 地址的路径都属于错误。

它不是 CPU mode，也不是 scheduler state。CPU 仍处于正常 64 位 kernel mode，所有 online CPU 和内核线程仍可被调度。

先清理依赖 init section 的调试元数据
-----------------------------------

在释放物理页前依次执行：

.. code-block:: c

   kprobe_free_init_mem();
   ftrace_free_init_mem();
   kgdb_free_init_mem();

启动期间，kprobe、ftrace 和 KGDB 可能记录位于 ``.init.text`` 中的地址、符号或 patch state。若直接把这些页交还 allocator，调试设施可能仍把已经复用的内存解释成旧函数。

这些入口清理的是对 init section 的引用和调试状态，不是关闭整个 kprobe、ftrace 或 KGDB。正常 kernel text 上的运行期能力仍然保留。

``exit_boot_config()`` 销毁 bootconfig 解析树
--------------------------------------------

bootconfig 数据在早期被解析，用于扩展 kernel command line 和 init 参数。此时这些参数已经被消费，PID 1 不再需要保留启动期 XBC 解析树。

``exit_boot_config()`` 释放对应结构。它不会删除 ``saved_command_line``，也不会从 ``/proc/cmdline`` 隐藏启动命令行。保存命令行与临时解析结构是两类对象。

``free_initmem()`` 真正回收启动代码和数据
----------------------------------------

链接脚本把带有下列标记的内容集中到专门 section：

.. code-block:: text

   __init
   __initdata
   __initconst
   initcall tables
   architecture boot-only helpers

这些内容只在启动期间使用。所有 initcall 与异步初始化完成后，继续永久占用 RAM 没有意义。

通用 ``free_initmem()`` 最终通过架构/通用内存释放路径：

* 修改 init section 页的映射属性；
* 对释放区域进行 poison，帮助暴露 use-after-init；
* 把对应物理页重新交给 buddy allocator；
* 更新内存统计。

从此以后，这些虚拟地址对应的旧函数内容不再可靠。页面可能被分配给任意内核对象。

``__init`` 不是“初始化过的普通函数”
---------------------------------

``__init`` 的真正语义是：函数在启动完成后可以消失。

因此下列写法是严重错误：

.. code-block:: text

   permanent function pointer
   → points to __init function
   → free_initmem()
   → later indirect call
   → execute freed/reused memory

内核的 section mismatch 检查会在构建期发现一部分此类引用；``free_initmem()`` 的 poison 和页复用则让漏网错误尽快暴露。

PID 1 自己为什么不会被一起释放
------------------------------

``kernel_init_freeable()`` 位于 init section，因此它必须先返回。外层 ``kernel_init()`` 使用 ``__ref`` 而不是普通 ``__init``，它继续驻留到本阶段完成。

第六十八章中 ``rest_init()`` 也特意是独立的 ``__ref``、``__noreturn`` 函数，防止 PID 0 的 idle 返回链依赖会被释放的 ``start_kernel()``。

此刻：

.. code-block:: text

   PID 0 → permanent idle loop
   PID 1 → permanent kernel_init wrapper
   freed  → boot-only init functions/data

``mark_readonly()`` 固化 kernel text 与 rodata 权限
-----------------------------------------------

释放 init memory 后，PID 1 调用 ``mark_readonly()``。启用 ``CONFIG_STRICT_KERNEL_RWX`` 时，其核心顺序包括：

.. code-block:: text

   flush_module_init_free_work()
   → jump_label_init_ro()
   → mark_rodata_ro()
   → debug_checkwx()
   → optional rodata_test()

``flush_module_init_free_work()`` 先等待 module 初始化期间排队的 W+X 清理，避免权限检查把仍在收尾的临时映射误判为永久漏洞。

``mark_rodata_ro()`` 根据架构页表实现把内核映像的只读区域真正改成不可写。常见目标状态是：

.. code-block:: text

   kernel text   = readable + executable, not writable
   rodata        = readable, not writable, not executable
   writable data = readable + writable, not executable

这就是 W^X 原则：同一页不应同时可写和可执行。

``jump_label_init_ro()`` 不会让 static key 失效
---------------------------------------------

static key 和 alternative instruction 在启动期间需要修改内核 text。进入只读阶段后，普通写入被页表权限禁止。

``jump_label_init_ro()`` 把 jump-label 系统切入受控 text-patching 阶段。后续动态 static-key 更新仍可通过专门的 text poke 机制临时建立安全写路径，而不是直接把整个 kernel text 长期映射成 writable。

``debug_checkwx()`` 验证最终内核映射
----------------------------------

权限固化后，``debug_checkwx()`` 扫描内核页表，查找不符合 W^X 的映射。它是验证步骤，不负责替代前面的权限设置。

出现 W+X 页面不一定立刻说明可利用漏洞，也可能来自架构 trampoline、JIT 或短暂 patch 区域；正常实现必须通过明确机制限制其范围与生命周期。

``pti_finalize()`` 为什么必须晚于只读化
-------------------------------------

x86 的 PTI（Page Table Isolation）在早期 ``pti_init()`` 已经创建用户页表需要共享的最小 kernel entry 映射。但那时 kernel image 中部分页仍是启动期 RW，init section 也尚未回收。

现在 ``free_initmem()`` 和 ``mark_readonly()`` 已改变 kernel image 映射：

* 某些 init 页被解除或重建；
* text/rodata 权限变成最终值；
* huge-page/PMD 可能因不同权限被拆分；
* entry text 的 NX/RO 状态已经稳定。

``pti_finalize()`` 重新 clone entry text 和必要 kernel text 到 userspace page table，并执行用户页表 W^X 检查。

它不表示现在才第一次启用 PTI。早期 PTI 已能保护启动期间发生的 user-mode helper；这里同步最终页表权限。

未启用 PTI 时会发生什么
----------------------

若 boot CPU 没有 ``X86_FEATURE_PTI``，``pti_finalize()`` 立即返回。正文不能据固定 x86-64 平台断言 PTI 必定开启，因为它取决于：

* kernel config；
* CPU vulnerability/feature 判定；
* ``pti=`` 命令行；
* hypervisor 与 mitigation policy。

无论 PTI 是否启用，``free_initmem()`` 与 kernel rodata 权限收尾仍是独立步骤。

``SYSTEM_RUNNING`` 是内核启动阶段的正式终点
-----------------------------------------

完成页表与权限收尾后，PID 1 执行：

.. code-block:: c

   system_state = SYSTEM_RUNNING;

现在内核正式宣布进入正常运行阶段。它表示：

* 同步与异步 boot initialization 已收束；
* init section 已回收；
* kernel image 权限已固化；
* scheduler、SMP、workqueue、driver model 和主要 subsystem 已运行；
* 后续故障、warning 与 hotplug 应按运行期语义处理。

它不表示 PID 1 已进入用户态。当前指令仍在 ``kernel_init()`` 中执行。

恢复 PID 1 的默认 NUMA policy
----------------------------

启动过程中 PID 1 曾临时获得所有 memory node 的分配权限，以便完成跨 node 初始化。现在调用：

.. code-block:: c

   numa_default_policy();

它把当前 task 的 memory policy 恢复到正常默认状态。实际分配仍受 cpuset、memcg、NUMA topology 和 task policy 影响。

``rcu_end_inkernel_boot()`` 结束 RCU 启动特例
-------------------------------------------

RCU 在启动期间允许若干特殊假设。进入 ``SYSTEM_RUNNING`` 后，CPU、task、idle、interrupt 与 userspace 边界已经稳定存在。

``rcu_end_inkernel_boot()`` 通知 RCU 结束 in-kernel boot phase。后续 grace period、callback 与 stall 检测全部按正常运行系统处理。

这不同于第六十八章的 ``rcu_scheduler_starting()``：

.. code-block:: text

   rcu_scheduler_starting()
   → scheduler/context-switch quiescent states begin

   rcu_end_inkernel_boot()
   → entire special boot phase ends

``do_sysctl_args()`` 消费启动命令行中的 sysctl
--------------------------------------------

内核允许通过启动参数为部分 sysctl 提供初始值。``do_sysctl_args()`` 在 sysctl tables 已由 initcall 注册后处理这些参数。

它必须晚于 initcall：过早执行时，对应 table 可能还不存在。它也必须早于用户态 init：用户空间看到的初始运行环境应已经包含这些设置。

本章结束时的机器状态
--------------------

本章结束时：

* 当前主线执行者：PID 1 ``init/main.c:kernel_init()``；
* precise position：``do_sysctl_args()`` 已返回，尚未调用 ``run_init_process()``；
* CPU mode：64 位 kernel mode；
* system state：``SYSTEM_RUNNING``；
* PID 0：CPU0 idle task；
* PID 2：``kthreadd`` 正常运行；
* AP：成功启动的 AP 已 online/idle；
* async initialization：全局 barrier 已完成；
* ``__init`` memory：已释放并可被 allocator 复用；
* kernel text/rodata：已执行最终权限固化；
* PTI：按 feature/config 完成最终 userspace page-table 同步；
* RCU：in-kernel boot 特例已结束；
* PID 1 userspace image：尚未选择和执行。

下一条控制流开始选择 init 程序：

.. code-block:: c

   if (ramdisk_execute_command)
       run_init_process(ramdisk_execute_command);

成功 ``kernel_execve()`` 之前，PID 1 仍然只是运行内核函数的特殊 task。

资料
----

* `Linux 7.2-rc1 init/main.c：kernel_init、free_initmem、mark_readonly 与 SYSTEM_RUNNING <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 arch/x86/mm/pti.c：pti_init 与 pti_finalize <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/pti.c>`_
* `Linux 7.2-rc1 include/linux/init.h：init section 与 free-init interfaces <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/init.h>`_
* `Linux 7.2-rc1 kernel/async.c：async_synchronize_full <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/async.c>`_
* `Linux 7.2-rc1 arch/x86/mm/init_64.c：x86 kernel mapping permission finalization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c>`_