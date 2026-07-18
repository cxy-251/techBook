项目状态
========

最后更新
--------

2026-07-18。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-057
   verified_through     = 057
   blocked batches      = none
   next batch           = 058-060
   next batch status    = paused-by-user

058—193中文件存在不等于技术已验证；当前pending范围是058—193。第193章审查闭合前不生产新章。
用户要求在完成055—057后暂停长期任务；恢复前不得自动开始058。恢复时仍从本文件指定的058—060
接续，不重做已验证批次。

最近完成批次
------------

`055—057审查报告 <audits/linux-kernel/055-057.rst>`_：状态 ``repaired``。

本批修复了：

* early RNG只混入arch command line，不把bootconfig extras或CRNG ready写成必然结果；
* printk per-CPU readiness、dynamic ring already-ready/迁移/失败保留static paths按源码固定；
* VFS early hash、later inode/dentry SLUB caches与filesystem mount分开；
* x86 trap foundation不再混同device IRQ initialization；
* 7.2-rc1 ``mm_core_init`` 的KHO、memblock→buddy、SLUB、vmalloc与espfix/PTI/execmem尾部恢复；
* Maple node cache、text-poke专用mm/PTE与actual text patch拆开；
* ftrace records/infrastructure/recording及其failure/stub paths拆开；
* scheduler class/root objects、possible-CPU runqueue与CPU0 ``init_task`` idle publication按锁和字段固定；
* ``sched_init`` 后的IRQ sanity repair纳入057出口，使下一入口IF确定为0。

当前符号
--------

::

   Z   = original boot_params physical address; copied and no longer reserved
   R/N = GRUB original initramfs physical address / true size
   E   = PAGE_ALIGN(R + N), the originally reserved initrd end
   B   = logical initrd_end after an optional valid bootconfig trailer is cut
   L   = build LOAD_PHYSICAL_ADDR
   O   = actual physical kernel output base / formal phys_base
   V   = relocation virtual position value

actual initrd relocation、SMP/UP、per-CPU allocator、NUMA、hypervisor、KASLR、MM debug、ftrace/tracing、
preemption mode与CPU/node counts受未固定build/runtime inputs影响。STATE只保存源码边界，不制造数值。

第057章结束状态
---------------

::

   current executor          = CPU0 start_kernel(), sched_init and IRQ sanity repair returned
   next call                 = radix_tree_init()
   CPU mode                  = x86-64 long mode, CPL0
   IF                        = 0, fixed again by post-sched sanity repair if needed
   current task              = init_task / swapper/0 / PID 0
   CPU online/active         = CPU0 only
   AP execution              = none
   possible CPU runqueues    = core/class/conditional fields initialized and attached to default root domain
   other CPU rq online       = 0 at initialization; containers do not mean CPUs are running
   CPU0 rq curr/idle         = init_task / init_task
   init_task scheduler state = TASK_RUNNING, on_rq queued, on_cpu 1, idle_sched_class
   init_task CPU affinity    = CPU0-only per-CPU kthread identity
   init_mm                   = current holds lazy-TLB reference; no user mm
   scheduler_running         = 1
   scheduler tick/domains    = not started / full SMP topology not established
   task switches             = none in this batch
   PID1/PID2                 = not created
   ordinary free RAM         = owned by buddy; reserved memblock ranges remain reserved
   after_bootmem             = 1
   totalram_pages            = actual pages released to buddy included
   slab                      = bootstrap/kmalloc foundation available; late init pending
   vmalloc                   = vmap-area cache/nodes/free space published
   maple node cache          = available
   text poke                 = dedicated mm/address/page-table backing; no resident text alias
   dynamic ftrace            = enabled infrastructure, disabled on failure, or build stub
   early tracing             = buffers/events initialized or degraded according to build/allocation
   console/initramfs/root    = not initialized / not unpacked / not mounted

已验证的055—057关系
-----------------

* early RNG argument不含later bootconfig extras；mix不等于credit或CRNG ready；
* log ring迁移failure可继续使用static ring，且不注册console；
* VFS hash backing、SLUB object caches与mount是不同阶段；
* trap runtime foundation不打开IF或初始化device IRQ；
* zonelists/pagesets存在不等于buddy已有普通RAM，handoff点是 ``memblock_free_all``；
* buddy收到memblock ``memory - reserved``，不是全部E820 RAM；
* KHO在handoff前处理， ``mem_init``、SLUB bootstrap、vmalloc area publication按序发生；
* ``mm_core_init`` 真实出口在espfix、PTI、KMSAN/MM cache与execmem之后；
* Maple cache不创建VMA，text-poke PTE backing不等于RWX text mapping；
* ftrace locations、enabled infrastructure与actual recording不可合并；
* possible CPU runqueue ready不等于CPU online或已有idle task；
* ``__sched_fork`` 不创建child， ``init_task`` 是PID 0 boot idle而不是PID 1；
* ``init_idle`` 发布CPU0 rq current/idle但不调度、不进入idle loop；
* ``scheduler_running=1`` 不代表tick、full SMP topology或AP ready；
* 057 return后的sanity repair保证058入口IF=0。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、RAM容量、QEMU CPU/accelerator/SMP/NUMA/完整device CLI、
runtime addresses、builtin command line、initramfs内容/bootconfig与microcode blob未提供，不得从commit
制造。

下一入口
--------

任务当前按用户指令暂停。恢复后，第058章从fixed ``init/main.c``：

.. code-block:: c

   radix_tree_init();

开始，随后依次进入housekeeping、 ``workqueue_init_early``、 ``rcu_init``、 ``kvfree_rcu_init``、
``trace_init`` 等启动阶段。第058正文尚未验证；上面的函数名只固定下一批读取边界，不预先声明结果。

058—060恢复读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``055-057`` 报告；
#. 第057章末尾、058—060全文、061开头；
#. fixed ``start_kernel`` 从 ``radix_tree_init`` 到060自然出口的真实顺序；
#. radix/XArray、housekeeping、early workqueue、RCU、kvfree-RCU与trace full-init actual helpers；
#. 059/060所涉IRQ/time/timer入口按fixed源码重新划分，不继承历史标题；
#. 两份manifest游标；旧058—060的版本标签、对象状态与相邻交接全部重核。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

均为clean、完整、非shallow、无active sparse checkout。 ``/Volumes/LinuxKernel/linux`` 不作为fixed
evidence；项目 ``.sources/`` 不承担缓存。

已知债务
--------

* 第058章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 058—193必须在用户恢复目标后继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
