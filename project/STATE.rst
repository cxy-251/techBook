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
   audit verified       = 001-060
   verified_through     = 060
   blocked batches      = none
   current batch        = none
   next batch           = 061-063
   next batch status    = pending

第061—193章已有文件只表示历史正文存在，不表示技术事实已经验证。第193章审查闭合前不得生产
新章；下一批必须从061开始，不得跳过或机械提高游标。

最近完成批次
------------

`058—060审查报告 <audits/linux-kernel/058-060.rst>`_：状态 ``repaired``。

本批完成：

* 统一权威源码规则，只允许使用大小写敏感卷上的四个固定工作树；禁止使用 ``.sources/`` 和
  其他副本，也禁止自动下载或拉取源码；
* 新增逐章独立写作和完整中文叙述规则，并重新检查第055—060章正文；
* 纠正第055章 ``hashdist`` 对目录项与索引节点哈希表的共同推迟条件；
* 纠正第056章无效函数追踪位置的逐项跳过语义，并补明本章进入
  ``ftrace_update_code()``；
* 补齐第057章CPU0运行队列在线、默认根域在线掩码和引用计数；
* 按Linux 7.2-rc1重写第058章的工作队列、RCU和追踪事件边界，第059章的IRQ描述符以及FRED或
  IDT分支，第060章的时钟滴答、定时器、SRCU、高精度定时器和软中断边界。

第060章结束状态
---------------

::

   当前执行者          = CPU0上的start_kernel()；softirq_init()已返回
   下一函数            = vdso_setup_data_pages()
   CPU模式             = x86-64长模式，CPL0
   IF                  = 0
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   应用处理器          = 尚未执行
   调度器              = 核心已公布；CPU0 rq的curr和idle均为init_task
   任务切换            = 尚未发生
   普通工作线程        = 尚未启动
   RCU                 = 所选实现已经初始化；后续线程尚不存在
   通用IRQ             = 稀疏分支或静态数组分支已初始化描述符状态
   x86 IRQ             = VECTOR域、向量矩阵和CPU0 IRQ栈已经建立
   CPU入口             = 按构建和CPU选择FRED分支或只读IDT分支
   IF启用              = 尚未执行
   时钟滴答            = 已尝试申请广播掩码；尚未选择时钟事件设备
   低精度定时器        = 所有可能CPU的定时器基已经初始化
   高精度定时器        = CPU0的基已在线；其他CPU尚未由本函数准备
   SRCU                = 所选实现已经初始化；排队工作尚未执行
   软中断              = 定时器、高精度定时器、条件RCU和小任务动作已登记
   ksoftirqd           = 尚未创建
   通用计时            = 尚未初始化
   jiffies周期增长     = 本批尚未启动
   控制台/初始内存盘/根 = 尚未初始化 / 尚未解包 / 尚未挂载
   PID1/PID2           = 尚未创建

已验证的第058—060章关系
-----------------------

* 基数树节点缓存与Maple Tree节点缓存是不同对象；前者不会向页缓存加入文件页；
* ``housekeeping.flags`` 是否为零不能只由GRUB命令行决定，内建命令行与 ``bootconfig`` 仍是
  未固定输入；
* ``workqueue_init_early()`` 允许创建和排队普通工作，不表示工作线程已经执行；
* Tree RCU、Tiny RCU、批量 ``kvfree_rcu`` 和强制用户上下文追踪都受构建配置控制；
* ``trace_init()`` 登记追踪事件并处理可选实例，不重复第056章的早期缓冲区分配；
* 稀疏IRQ使用Maple Tree，非稀疏IRQ使用静态描述符数组；二者不能合并；
* FRED有效时跳过 ``idt_setup_apic_and_irq_gates()``，IDT只读映射不是所有CPU的必然路径；
* 早期传统PIC状态、向量保留和CPU入口完成，不等于q35最终IOAPIC路由已经建立；
* ``tick_init()`` 只处理广播掩码和全动态时钟滴答条件，不会注册硬件时钟事件设备；
* 普通定时器本批覆盖所有可能CPU，高精度定时器本次只准备CPU0；
* 软中断动作登记不等于待处理位已经设置，也不等于 ``ksoftirqd`` 已经创建；
* 第060章结束时IF位仍为0，通用计时状态和x86硬件时间初始化尚未执行。

固定平台约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

最终 ``.config``、内建命令行、 ``bootconfig``、CPU模型与特性、加速器、SMP/NUMA、内存容量、
完整设备参数、运行期地址和初始化内存盘内容未固定。正文必须保留这些输入控制的构建与运行分支。

下一入口
--------

第061章从固定Linux源码中的：

.. code-block:: c

   vdso_setup_data_pages();

开始，随后进入 ``timekeeping_init()`` 和x86 ``time_init()``。旧第061—063章标题和边界尚未按
固定源码验证，下一批必须重新确定三章的自然出口，不能从旧标题反推调用范围。

第061—063章读取清单
-------------------

#. ``AGENTS.md``、 ``project/LINUX_KERNEL_CONTRACT.rst``、本文件和
   ``audits/linux-kernel/058-060.rst``；
#. 第060章末尾、第061—063章全文和第064章开头；
#. 固定 ``init/main.c`` 从 ``vdso_setup_data_pages()`` 到第063章自然出口的真实顺序；
#. VDSO数据页、通用计时、x86 ``time_init()``、随机数最终初始化、KFENCE、栈保护值、性能事件、
   性能分析、跨CPU函数调用、中断开启、SLUB后半段、控制台与第063章涉及的后续源码；
#. 两份manifest游标；旧版本标签、条件分支、失败语义和第064章入口全部重新核对。

权威源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

四个工作树的remote均与固定仓库一致；Linux存在指向 ``gregkh/linux`` 的remote；四者工作树干净、
完整、非浅克隆且未启用稀疏检出。不得使用 ``/Volumes/LinuxKernel/linux``、项目 ``.sources/``
或其他副本取证，不得自动下载、拉取或补齐源码。

已知债务
--------

* 第061章起历史正文仍有旧版本、旧结构或未经固定源码核验的断言；
* 第065、066章各有重复正文文件；
* 第001—073章尚未逐章进入主线机器可读章节目录；
* 第061—193章必须继续按编号顺序审查，不能批量机械标记为已验证。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存回溯审查开始前第193章的历史前向终点，
不是当前已验证事实。
