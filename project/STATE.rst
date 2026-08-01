项目状态
========

最后更新
--------

2026-08-01。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   audit execution      = paused
   content present      = 001-193
   audit verified       = 001-069
   verified_through     = 069
   blocked batches      = none
   current batch        = none
   next batch           = 070-072
   next batch status    = paused by user

第070—193章已有文件只表示历史正文存在，不表示技术事实已经验证。第193章审查闭合前不得生产
新章；下一批必须从070开始，不得跳过或机械提高游标。用户要求第067—069章完成后暂停审查，
恢复前不得启动第070—072章。

最近完成批次
------------

`067—069审查报告 <audits/linux-kernel/067-069.rst>`_：状态 ``repaired``。

本批完成：

* 第067章按固定源码重建cpuset、内存控制组、控制组核心、任务统计与延迟记账，区分共享设施、
  根对象、文件系统登记、实际挂载和启动参数控制的启用状态；
* 第067章确认当前ACPI入口只尝试切换模式，没有提前建立FACS、事件、SCI或全局锁处理器，并按
  CPU能力和构建选择收束x86修正与KCSAN边界；
* 第068章按完成量和调度约束重建PID 0、PID 1、PID 2的交接，保留两次任务创建结果未检查和
  首次调度顺序不固定的源码事实；
* 第068章确认PID 0永久进入CPU0空闲循环，PID 1只有越过 ``kthreadd_done`` 才接续
  ``kernel_init_freeable()``，PID 2首次运行时刻不由 ``rest_init()`` 固定；
* 第069章分开处理器准备、实际唤醒、逐CPU上线与SMP调度域发布，保留构建、APIC模式、
  ``setup_max_cpus``、平台方法和逐CPU错误对在线集合的控制；
* 第069章按三阶段工作队列、早期初始化调用、异步执行、并行数据路径和页分配晚期收尾的真实
  顺序重写，下一入口精确停在 ``do_basic_setup()``。

第069章结束状态
---------------

::

   当前执行者          = PID 1；page_alloc_init_late()已返回
   下一入口            = do_basic_setup()
   CPU模式             = x86-64长模式，CPL0
   system_state        = SYSTEM_SCHEDULING
   PID 0               = CPU0空闲任务
   PID 1               = kernel_init；允许在非隔离housekeeping CPU运行
   PID 2               = kthreadd；已能处理内核线程创建请求
   CPU在线集合         = 按SMP配置、APIC模式、setup_max_cpus与逐CPU启动结果确定
   应用处理器          = 按SMP构建与目标限额尝试上线；成功者进入各自空闲循环
   RCU                 = 已越过调度器启动阶段；完整运行期切换仍由后续初始化调用完成
   SMP调度器           = 按实际cpu_active_mask建立并发布
   工作队列            = 首批执行者在线，无绑定池已按最终拓扑重新连接
   early_initcall      = SMP前链接区间已经执行
   锁死检测            = 按配置、housekeeping集合和探测结果设置
   async               = 专用无绑定工作队列已经建立
   padata              = 已建立，或在登记/分配失败后警告并撤销
   延后页元数据        = 启用时已经全部初始化并关闭按需分支
   memblock私有元数据  = 已丢弃
   初始根              = 仍为可变rootfs
   最终磁盘根          = 尚未挂载
   初始内存盘          = 尚未解包
   用户空间init       = 尚未装入

已验证的第067—069章关系
------------------------

* ``cpuset_init()`` 建立顶层约束掩码，不建立SMP调度域；
* ``mem_cgroup_init()`` 建立共享设施，根内存控制组由随后 ``cgroup_init()`` 连接；
* ``cgroup_init()`` 建立默认根并登记文件系统，不等于cgroupfs已经挂载；
* ``taskstats_init_early()`` 没有登记Generic Netlink族， ``delayacct_init()`` 也不保证采集
  已启用；
* ``acpi_subsystem_init()`` 本次只允许切换ACPI模式，FACS、事件、SCI与全局锁处理器仍留给
  后续入口；
* ``rcu_scheduler_starting()`` 进入 ``RCU_SCHEDULER_INIT``，不是完整运行期RCU；
* 持续启动路径中的两次任务复制依次得到PID 1和PID 2，但 ``rest_init()`` 没有检查负返回值；
* PID 1在SMP调度域建立前只能在CPU0运行， ``kthreadd_done`` 保证它继续前能看到PID 2已经
  发布；
* 第一次显式调度不规定PID 1和PID 2谁先运行；PID 0随后永久成为CPU0空闲任务；
* ``smp_prepare_cpus()`` 只准备处理器启动条件，应用处理器由 ``smp_init()`` 实际尝试唤醒；
* 应用处理器在线结果受构建、APIC模式、 ``setup_max_cpus``、平台方法和逐CPU错误控制；
* ``workqueue_init()`` 为更早建立的池创建首批执行者， ``workqueue_init_topology()`` 再按
  最终在线CPU重连无绑定池；
* ``do_pre_smp_initcalls()`` 只执行 ``early_initcall()`` 链接区间，不进入0到7级完整初始化
  调用；
* ``sched_init_smp()`` 按实际活动CPU建立调度域并解除PID 1临时亲和限制，不保证发生迁移；
* ``padata_init()`` 失败只警告并撤销， ``async_init()`` 与关键工作线程失败则停止当前路径；
* 延后页元数据初始化依赖每个节点的 ``kthread_run()`` 成功，源码没有检查各次返回值；
* ``page_alloc_init_late()`` 完成页元数据和 ``memblock`` 晚期收尾，不挂载最终根，也不解包
  初始内存盘。

固定平台约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

最终 ``.config``、内建命令行、启动配置、CPU模型与特性、加速器、SMP/NUMA、内存容量、完整设备
参数、运行期地址和初始内存盘内容未固定。正文必须保留这些输入控制的构建、失败和运行分支。

下一入口
--------

第070章从固定Linux源码中的：

.. code-block:: c

   do_basic_setup();

开始。该函数依次进入 ``cpuset_init_smp()``、 ``ksysfs_init()``、 ``driver_init()``、
``init_irq_proc()``、构造函数和完整初始化调用。旧第070—072章尚未按固定源码验证；下一批
必须重新确定设备模型、各初始化调用级别和初始内存盘等待的真实章节边界。

第070—072章读取清单
--------------------

#. ``AGENTS.md``、 ``project/LINUX_KERNEL_CONTRACT.rst``、本文件和
   ``audits/linux-kernel/067-069.rst``；
#. 第069章末尾、第070—072章全文和第073章开头；
#. 固定 ``init/main.c`` 从 ``do_basic_setup()`` 到第072章自然出口的真实调用顺序；
#. cpuset SMP阶段、内核对象文件系统、设备模型、中断proc入口、构造函数、0到7级初始化调用、
   初始内存盘同步和根文件系统准备所需源码；
#. 两份manifest游标、条件分支、失败语义、第069章出口和第073章真实入口。

权威源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

本批开始时，四个工作树的远程仓库均符合合同；Linux存在指向 ``gregkh/linux`` 的远程仓库；
四者工作树干净、不是浅克隆且未启用稀疏检出。不得使用其他源码副本取证，也不得自动
下载、拉取或补齐源码。

已知债务
--------

* 第070章起历史正文仍有旧版本、旧结构或未经固定源码核验的断言；
* 第001—073章尚未逐章进入主线机器可读章节目录；
* 第070—193章必须继续按编号顺序审查，不能批量机械标记为已验证。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存回溯审查开始前第193章的历史前向终点，
不是当前已验证事实。
