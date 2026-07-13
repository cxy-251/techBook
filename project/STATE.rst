项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-067``。最新三章：

#. ``LK-BOOT-065``：Linux 怎样建立 PID 分配器与 fork 对象基础？
#. ``LK-BOOT-066``：Linux 怎样建立 namespace、安全框架与 VFS/proc 基础？
#. ``LK-BOOT-067``：Linux 怎样建立 cgroup 与 accounting，并到达 rest_init？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 7.2-rc1
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

源码版本纠正
------------

固定 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d`` 的 ``Makefile`` 标识为 ``7.2-rc1``。此前状态文件把它误写成 ``v6.12.95``；真正的 ``v6.12.95`` 是另一提交，且 ``start_kernel()`` 顺序不同。

第三十四章之后的技术调查和源码链接一直指向固定 commit，因此后续继续以该 commit 为权威来源。旧章节正文中残留的 ``Linux 6.12.95`` 仅是显示标签错误，不能据此更换源码路径。

当前控制流位置
--------------

第六十五至六十七章已经完成：

::

   pid_idr_init()
   → initialize initial PID namespace IDR and pid limits
   → create struct pid slab cache
   → anon_vma_init()
   → create anon_vma and anon_vma_chain caches
   → thread_stack_cache_init()
   → cred_init()
   → create credential cache
   → fork_init()
   → create task_struct cache and establish task limits
   → initialize VMAP stack/SCS/lockdep/uprobe fork foundations
   → proc_caches_init()
   → create signal/files/fs/mm and process-related caches
   → uts_ns_init()
   → register initial UTS namespace and allocation cache
   → time_ns_init()
   → register initial time namespace
   → key_init()
   → security_init()
   → dbg_late_init()
   → net_ns_init()
   → vfs_caches_init()
   → pagecache_init()
   → signals_init()
   → seq_file_init()
   → proc_root_init()
   → nsfs_init()
   → pidfs_init()
   → cpuset_init()
   → mem_cgroup_init()
   → cgroup_init()
   → taskstats_init_early()
   → delayacct_init()
   → acpi_subsystem_init()
   → arch_post_acpi_subsys_init()
   → kcsan_init()

此刻机器状态：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``kcsan_init()`` 已返回，``rest_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task`` / ``swapper/0`` / PID 0；
* interrupts：CPU0 IF=1，``early_boot_irqs_disabled = false``；
* scheduler：runqueue、idle task、tick/time 基础已建立，尚未进行第一次正常 ``schedule()``；
* PID allocator：初始 namespace IDR、范围和 ``struct pid`` cache 已建立；
* fork objects：task、stack、cred、signal/files/fs/mm caches 已建立；
* namespaces：初始 UTS、time 与 network namespace 基础已建立；
* security：key 与 LSM init sequence 已按配置执行，具体 policy 未必加载；
* VFS/page cache：dentry/inode/file/page-cache 基础已建立；
* proc/nsfs/pidfs：filesystem representation 已建立，未断言 procfs 已挂载；
* cpuset/memcg/cgroup：root 与 task-membership/accounting 基础已建立，cgroupfs 未断言已挂载；
* taskstats/delayacct：新任务统计基础已准备；
* ACPI：subsystem enable 已执行，完整 bus/device scan 尚未进行；
* KCSAN：按配置完成初始化；
* AP：尚未收到 INIT/SIPI；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包；
* root filesystem：尚未挂载。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():rest_init()`` 开始，继续 ``rcu_scheduler_starting()``、``user_mode_thread(kernel_init)`` 创建 PID 1、将 PID 1 暂时固定在 CPU0、``kernel_thread(kthreadd)`` 创建 PID 2、``system_state = SYSTEM_SCHEDULING``、``complete(kthreadd_done)``、``schedule_preempt_disabled()`` 与 ``cpu_startup_entry()``。保持边界清晰：对象 cache 与 PID allocator 已建立不等于 PID 1/PID 2 已存在；只有 ``rest_init()`` 才开始创建任务并让 PID 0 第一次进入 scheduler/idle 环境。