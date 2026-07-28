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
   audit execution      = active
   content present      = 001-193
   audit verified       = 001-063
   verified_through     = 063
   blocked batches      = none
   current batch        = none
   next batch           = 064-066
   next batch status    = pending

第064—193章已有文件只表示历史正文存在，不表示技术事实已经验证。第193章审查闭合前不得生产
新章；下一批必须从064开始，不得跳过或机械提高游标。

最近完成批次
------------

`061—063审查报告 <audits/linux-kernel/061-063.rst>`_：状态 ``repaired``。

本批完成：

* 第061章按Linux 7.2-rc1重新建立VDSO数据页、持久时钟、启动偏移、
  ``clocksource_jiffies``、核心计时器同步发布和x86延后函数边界；
* 第062章区分随机数生成器的条件状态、KFENCE、栈保护、性能事件与传统性能分析构建分支，并
  纠正所有可能CPU队列头和仅CPU0发送端资源之间的差异；
* 第062章确认 ``early_boot_irqs_disabled`` 与RFLAGS.IF依次变化，并保留FRED或IDT入口、最终
  中断模式和具体中断源之间的边界；
* 第063章把 ``kmem_cache_init_late()`` 限定为SLUB清理工作队列与可选随机状态，纠正
  ``lockdep_init()`` 的报告语义；
* 第063章补齐 ``panic_later``、初始内存盘低端禁用、逐CPU页面集、当前启动任务临时NUMA交错
  策略，以及ACPICA禁用、失败关闭和正常初始化三类结果。

第063章结束状态
---------------

::

   当前执行者          = CPU0上的start_kernel()；acpi_early_init()已返回
   下一入口            = if (late_time_init) late_time_init()
   CPU模式             = x86-64长模式，CPL0
   IF                  = 1
   启动期IRQ软件标志   = early_boot_irqs_disabled为假
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   应用处理器          = 尚未执行
   VDSO数据            = 正式数据页已经分配；用户VMA尚不存在
   通用计时            = 核心timekeeper已发布；当前时钟源为clocksource_jiffies
   x86硬件时间         = late_time_init已登记但尚未调用
   周期时钟滴答        = 尚未由最终硬件时钟事件驱动
   随机数              = random_init()已执行；可用状态取决于较早熵累计
   KFENCE              = 按配置、采样间隔和池初始化结果处理
   栈保护              = 按配置为init_task与CPU0设置，或为空入口
   性能事件/传统分析   = 分别按配置、参数和分配结果处理
   跨CPU函数调用       = 所有可能CPU队列头已初始化；CPU0发送端资源只保证已尝试申请
   SLUB                = slub_flushwq已尝试申请；失败只警告
   控制台              = 默认行规程和控制台初始化区间已执行；具体终端登记取决于配置与结果
   锁检查              = lockdep报告与锁接口自检按配置和调试状态处理
   初始内存盘          = 起始地址按低端检查保留或清零；归档尚未解包
   逐CPU页面集         = 已填充内存区覆盖所有可能CPU的正式页面集已经建立
   NUMA策略            = 启用且设置成功时，init_task暂时采用启动期交错策略
   ACPI                = 保持禁用、失败后关闭，或已建立早期ACPICA基础
   普通AML/ACPI设备    = 尚不能执行 / 尚未扫描
   普通工作线程        = 尚未启动
   任务切换            = 尚未发生
   PID1/PID2           = 尚未创建
   根文件系统          = 尚未挂载

已验证的第061—063章关系
-----------------------

* ``vdso_setup_data_pages()`` 只准备内核侧正式页面，不创建用户VDSO或VVAR映射；
* x86墙上时间经 ``x86_platform.get_wallclock`` 读取，启动偏移的通用值来自
  ``local_clock()``，二者不能合并为一次硬件读取；
* x86没有覆盖启动默认时钟源，当前使用 ``clocksource_jiffies``；没有最终硬件时钟事件时不能
  声称周期性 ``jiffies`` 增长已经开始；
* ``time_init()`` 只把 ``late_time_init`` 指向 ``x86_late_time_init``，不执行HPET、PIT、
  TSC或最终中断模式初始化；
* ``random_init()`` 已执行不等于随机数生成器在所有运行条件下都已达到可用阈值；
* KFENCE延迟工作已经排队时，普通工作线程仍未开始；栈保护和性能事件都可能是空入口；
* ``call_function_init()`` 为所有可能CPU初始化队列头，只为CPU0尝试申请发送端数据，并忽略
  该申请函数的错误值；
* ``local_irq_enable()`` 允许普通可屏蔽中断进入，不会主动制造中断、登记处理动作或触发调度；
* ``kmem_cache_init_late()`` 不重建SLUB，只申请清理工作队列并初始化可选伪随机状态；
* ``lockdep_init()`` 在启用时报告静态容量，不在此首次创建锁依赖图；
* 初始内存盘低端检查可以把 ``initrd_start`` 清零，运行期地址未固定，不能把保留写成必然；
* 正式逐CPU页面集不改变页面所属内存区；NUMA初始化可能改变当前 ``init_task`` 的后续分配策略；
* ``acpi_early_init()`` 正常返回也不允许普通AML执行；初始化失败会关闭ACPI后继续启动。

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

第064章从固定Linux源码中的：

.. code-block:: c

   if (late_time_init)
       late_time_init();

开始。x86当前函数指针指向 ``x86_late_time_init()``，随后才进入 ``sched_clock_init()``、
``calibrate_delay()`` 和 ``arch_cpu_finalize_init()``。旧第064—066章标题、两个第065章文件和
两个第066章文件均未按固定源码验证；下一批必须从真实调用边界确定保留文件，不能从旧文件名
反推事实或跳过重复项。

第064—066章读取清单
-------------------

#. ``AGENTS.md``、 ``project/LINUX_KERNEL_CONTRACT.rst``、本文件和
   ``audits/linux-kernel/061-063.rst``；
#. 第063章末尾、第064章全文、两个第065章文件、两个第066章文件和第067章开头；
#. 固定 ``init/main.c`` 从 ``late_time_init`` 条件调用到第066章自然出口的真实顺序；
#. x86中断模式、HPET/PIT、TSC、调度时钟、延时校准、启动CPU最终处理、PID分配器、匿名VMA、
   线程栈、凭据、 ``fork_init()``、名字空间、安全框架和VFS缓存所需源码；
#. 重复文件的读者入口与链接情况；只在完成逐个源码核验后决定保留哪一份；
#. 两份manifest游标、条件分支、失败语义和第067章真实入口。

权威源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

本批开始时，四个工作树的远程仓库均符合合同；Linux存在指向 ``gregkh/linux`` 的远程仓库；
四者工作树干净、完整、不是浅克隆且未启用稀疏检出。不得使用其他源码副本取证，也不得自动
下载、拉取或补齐源码。

已知债务
--------

* 第064章起历史正文仍有旧版本、旧结构或未经固定源码核验的断言；
* 第065、066章各有两个正文文件，必须在下一批逐一核验并解决重复项；
* 第001—073章尚未逐章进入主线机器可读章节目录；
* 第064—193章必须继续按编号顺序审查，不能批量机械标记为已验证。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存回溯审查开始前第193章的历史前向终点，
不是当前已验证事实。
