项目状态
========

最后更新
--------

2026-07-28。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   audit execution      = paused
   content present      = 001-193
   audit verified       = 001-066
   verified_through     = 066
   blocked batches      = none
   current batch        = none
   next batch           = 067-069
   next batch status    = paused by user

第067—193章已有文件只表示历史正文存在，不表示技术事实已经验证。第193章审查闭合前不得生产
新章；下一批必须从067开始，不得跳过或机械提高游标。用户要求第064—066章完成后暂停审查，
恢复前不得启动第067—069章。

最近完成批次
------------

`064—066审查报告 <audits/linux-kernel/064-066.rst>`_：状态 ``repaired``。

本批完成：

* 第064章按固定源码重建x86延后时间初始化，区分HPET时钟源、HPET旧式时钟事件、PIT和无需
  IRQ0的路径，并保留IRQ登记失败与TSC不可靠分支；
* 第064章补齐 ``sched_clock_init()`` 内部IF变化、延时校准选择顺序，以及启动CPU的FPU、
  最终特性、指令替代、用户地址上限、低端映射和内存加密收尾；
* 第065章区分静态PID 0对象与动态PID分配基础，确认当前x86-64的
  ``thread_stack_cache_init()`` 是弱空入口，并还原 ``fork_init()`` 与
  ``proc_caches_init()`` 的真实对象边界；
* 第066章按构建条件处理名字空间、密钥、安全框架、KGDB/KDB和网络，补齐
  ``vfs_caches_init()`` 内建立的初始挂载树、内部 ``rootfs`` 与三个伪文件系统的不同结果；
* 删除第065、066章各一份同编号重复文件，读者目录现在每个编号只收录一份正文。

第066章结束状态
---------------

::

   当前执行者          = CPU0上的start_kernel()；pidfs_init()已返回
   下一入口            = cpuset_init()
   CPU模式             = x86-64长模式，CPL0
   IF                  = 1
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   应用处理器          = 尚未启动
   中断模式            = 按运行检测选择并完成启动CPU设置
   HPET/PIT            = 按能力、配置和中断模式选择；IRQ0只在需要时尝试登记
   TSC                 = 按能力、频率与同步结果使用或标记不稳定
   调度时钟            = 启动基准已经切换
   延时循环            = CPU0与全局loops_per_jiffy已经写入
   启动CPU             = 最终信息已经复制，指令替代已经执行
   初始PID名字空间     = IDR与动态pid缓存已经建立；PID 1尚未分配
   任务创建基础        = task_struct、凭据、信号、文件和名字空间代理等缓存已经建立
   UTS/时间名字空间    = 分别按构建配置登记或采用空入口
   密钥/安全框架       = 分别按构建与启动选择初始化或采用空入口
   KGDB/KDB            = 按配置完成晚期切换或采用空入口
   初始网络名字空间    = CONFIG_NET启用时已经设置；完整协议与设备尚未初始化
   VFS                 = 文件名、目录项、inode、文件、挂载、块设备和字符设备基础已建立
   初始挂载名字空间    = nullfs与可变rootfs已经挂载并接入init_task
   当前根与工作目录    = 指向可变rootfs
   最终磁盘根          = 尚未挂载
   初始内存盘          = 尚未解包
   页缓存等待/回写     = 基础已经初始化
   procfs              = 按配置登记但尚未挂载
   nsfs/pidfs          = 内部挂载已经建立
   普通工作线程        = 尚未启动
   任务切换            = 尚未发生
   PID1/PID2           = 尚未创建

已验证的第064—066章关系
-----------------------

* ``x86_late_time_init()`` 先选择中断模式，再初始化HPET或PIT，随后完成模式设置并处理TSC；
* ``hpet_enable()`` 返回0可能表示HPET完全不可用，也可能表示时钟源已登记但没有旧式替代
  路由；只有HPET旧式事件或PIT需要IRQ0时才执行 ``setup_default_timer_irq()``；
* IRQ0登记失败只打印信息；越过入口不证明处理动作存在，也不证明硬件时钟事件已经到达；
* ``tsc_init()`` 可能清除能力或标记TSC不稳定；固定QEMU平台未限定CPU模型和加速器，不能预判
  TSC可靠；
* ``sched_clock_init()`` 短暂关闭并重新打开CPU0中断以切换调度时钟基准，正常出口IF仍为1；
* ``calibrate_delay()`` 从六类既有值或校准路径中选择，不必然执行传统收敛循环；
* ``arch_cpu_finalize_init()`` 完成启动CPU收尾，不会启动应用处理器、创建任务或进入空闲循环；
* PID 0使用静态 ``init_struct_pid``； ``pid_idr_init()`` 只建立动态分配能力，PID 1要等
  ``alloc_pid()`` 在任务复制路径中实际执行；
* 当前x86-64的 ``thread_stack_cache_init()`` 是弱空入口；启用虚拟映射栈时，回收状态由
  ``fork_init()`` 按配置登记；
* ``fork_init()`` 建立任务缓存与限制， ``proc_caches_init()`` 建立进程共享对象、VMA和
  ``nsproxy`` 基础；二者都不创建新任务；
* ``proc_caches_init()`` 不是procfs初始化，也不创建已经在更早内存阶段建立的
  ``mm_struct`` 缓存；
* UTS、时间、密钥、安全、KGDB、网络和proc入口均受构建或启动选择控制；
* ``mnt_init()`` 在VFS缓存入口内部建立初始挂载名字空间，以 ``nullfs`` 为名字空间根并在
  上面挂载可变 ``rootfs``；它不是最终ext4磁盘根；
* ``proc_root_init()`` 只按配置登记procfs， ``nsfs_init()`` 与 ``pidfs_init()`` 则建立
  内核内部挂载。

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

第067章从固定Linux源码中的：

.. code-block:: c

   cpuset_init();

开始。随后才是 ``mem_cgroup_init()``、 ``cgroup_init()``、任务统计、延迟记账、ACPI子系统、
KCSAN条件入口和 ``rest_init()``。旧第067—069章尚未按固定源码验证；下一批必须重新确定
``rest_init()``、PID 1/PID 2、应用处理器、工作队列与SMP调度器的真实章节边界。

第067—069章读取清单
-------------------

#. ``AGENTS.md``、 ``project/LINUX_KERNEL_CONTRACT.rst``、本文件和
   ``audits/linux-kernel/064-066.rst``；
#. 第066章末尾、第067—069章全文和第070章开头；
#. 固定 ``init/main.c`` 从 ``cpuset_init()`` 到第069章自然出口的真实调用顺序；
#. CPU集合、内存控制组、控制组核心、任务统计、延迟记账、ACPI子系统、KCSAN、
   ``rest_init()``、 ``kernel_init()``、 ``kthreadd``、应用处理器、工作队列和调度器所需
   源码；
#. 两份manifest游标、条件分支、失败语义、第066章出口和第070章真实入口。

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

* 第067章起历史正文仍有旧版本、旧结构或未经固定源码核验的断言；
* 第001—073章尚未逐章进入主线机器可读章节目录；
* 第067—193章必须继续按编号顺序审查，不能批量机械标记为已验证。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存回溯审查开始前第193章的历史前向终点，
不是当前已验证事实。
