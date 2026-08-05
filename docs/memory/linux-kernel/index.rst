Linux Kernel 必背课本
=====================

本目录与 AIBook 的 ``docs/LinuxK`` 一一对应。AIBook 是完整教材，这里只保留每章中稳定、必须掌握、
可以直接记忆的知识。

Part 1：内核世界观与工程心智模型
---------------------------------

* `第001章：Linux 内核资源管理模型 <001-linux-kernel-resource-management-model.rst>`_；
* `第002章：为什么 Linux 内核源码难读 <002-why-linux-kernel-source-is-difficult.rst>`_；
* `第003章：Linux 内核的核心设计取舍 <003-core-kernel-design-forces.rst>`_；
* `第004章：Linux 内核的四条核心路径 <004-four-great-kernel-paths.rst>`_；
* `第005章：怎样学习 Linux 内核源码 <005-how-to-read-linux-kernel-handbook.rst>`_。

Part 2：源码树与代码导航
------------------------

* `第006章：Linux 内核源码树的结构 <006-shape-of-kernel-source-tree.rst>`_；
* `第007章：怎样在巨大源码库中找到入口 <007-finding-kernel-entry-points.rst>`_；
* `第008章：怎样阅读 Linux 内核数据结构 <008-reading-kernel-data-structures.rst>`_；
* `第009章：怎样结合状态追踪内核调用链 <009-following-call-chains-with-state.rst>`_；
* `第010章：建立个人内核源码阅读工作流 <010-personal-kernel-reading-workflow.rst>`_。

Part 3：内核 C 语法、核心 API 与运行时约束
-----------------------------------------

* `第011章：Linux 内核 C 的运行时约束 <011-kernel-c-runtime-constraints.rst>`_；
* `第012章：Linux 内核核心数据结构 <012-core-kernel-data-structures.rst>`_；
* `第013章：Linux 内核错误处理与返回约定 <013-kernel-error-handling.rst>`_；
* `第014章：Linux 内核日志与诊断语法 <014-kernel-logging-and-diagnostics.rst>`_；
* `第015章：Linux 内核代码风格、评审与可维护性 <015-kernel-coding-style-and-maintainability.rst>`_。

Part 4：Kconfig、Kbuild、模块与内核镜像
--------------------------------------

* `第016章：使用 Kconfig 配置 Linux 内核 <016-kernel-configuration-with-kconfig.rst>`_；
* `第017章：使用 Kbuild 构建 Linux 内核 <017-kernel-build-system-with-kbuild.rst>`_；
* `第018章：Linux 可加载内核模块 <018-loadable-kernel-modules.rst>`_；
* `第019章：Linux 内核镜像、符号与 initramfs <019-kernel-images-symbols-and-initramfs.rst>`_；
* `第020章：建立可复现的 Linux 内核构建 <020-reproducible-kernel-build.rst>`_。

Part 5：启动序列、Initcall 与早期内核初始化
------------------------------------------

* `第021章：从固件到 Bootloader <021-from-firmware-to-bootloader.rst>`_；
* `第022章：内核解压与早期架构初始化 <022-kernel-decompression-and-early-architecture-setup.rst>`_；
* `第023章：内核命令行与早期参数 <023-kernel-command-line-and-early-parameters.rst>`_；
* `第024章：Initcall 层级与子系统初始化 <024-initcall-levels-and-subsystem-initialization.rst>`_；
* `第025章：调试 Linux 早期启动故障 <025-debugging-early-boot-failures.rst>`_。

Part 6：内核对象、生命周期、引用与错误路径
------------------------------------------

* `第026章：内核对象是具有生命周期的 C 结构体 <026-kernel-objects-as-c-structures-with-lifetimes.rst>`_；
* `第027章：引用计数与所有权转移 <027-reference-counting-and-ownership-transfer.rst>`_；
* `第028章：资源申请与释放顺序 <028-resource-acquisition-and-release-ordering.rst>`_；
* `第029章：对象注册、查找与销毁 <029-object-registration-lookup-and-teardown.rst>`_；
* `第030章：失败路径是内核设计的真实检验 <030-failure-paths-as-the-real-test.rst>`_。

Part 7：可观测接口：procfs、sysfs、debugfs、tracefs 与 dmesg
-----------------------------------------------------------

* `第031章：procfs 是进程与内核状态的运行时视图 <031-procfs-runtime-view.rst>`_；
* `第032章：sysfs 是设备与对象模型接口 <032-sysfs-device-and-object-model.rst>`_；
* `第033章：debugfs 是开发者控制的调试面 <033-debugfs-developer-debug-surface.rst>`_；
* `第034章：tracefs 与内核追踪接口 <034-tracefs-kernel-tracing-interface.rst>`_；
* `第035章：dmesg、printk 与运行时证据收集 <035-dmesg-printk-runtime-evidence.rst>`_。

Part 8：用户态—内核态边界与系统调用路径
--------------------------------------

* `第036章：用户代码怎样进入内核 <036-user-code-entry-into-kernel.rst>`_；
* `第037章：系统调用表、入口代码与 ABI 稳定性 <037-syscall-tables-entry-and-abi-stability.rst>`_；
* `第038章：跨越用户态与内核态边界复制数据 <038-copying-data-across-user-kernel-boundary.rst>`_；
* `第039章：文件描述符、句柄与内核对象 <039-file-descriptors-handles-and-kernel-objects.rst>`_；
* `第040章：失败、errno 与边界诊断 <040-failure-errno-and-boundary-diagnostics.rst>`_。

Part 9：进程、线程、task_struct 与执行上下文
--------------------------------------------

* `第041章：task_struct 是 Linux 内核的任务对象 <041-task-struct-as-kernel-process-object.rst>`_；
* `第042章：fork、clone 与 exec 的进程创建语义 <042-process-creation-fork-clone-exec.rst>`_；
* `第043章：线程、线程组与共享资源 <043-threads-thread-groups-shared-resources.rst>`_；
* `第044章：进程状态、睡眠、唤醒与信号 <044-process-states-sleep-wakeup-signals.rst>`_；
* `第045章：进程、中断与内核线程执行上下文 <045-execution-contexts-process-interrupt-kernel-thread.rst>`_。

Part 10：调度器架构、CFS、实时调度与 CPU 时间
---------------------------------------------

* `第046章：调度类与调度框架 <046-scheduler-classes-and-framework.rst>`_；
* `第047章：CFS、vruntime、权重与公平性 <047-cfs-vruntime-weights-and-fairness.rst>`_；
* `第048章：实时调度类与延迟保证 <048-real-time-scheduling-and-latency.rst>`_；
* `第049章：CPU 亲和性、负载均衡与多核调度 <049-cpu-affinity-load-balancing-and-multicore.rst>`_；
* `第050章：诊断调度延迟与饥饿 <050-diagnosing-scheduling-latency-and-starvation.rst>`_。

Part 11：上下文切换、抢占、定时器与时间维护
------------------------------------------

* `第051章：上下文切换保存状态与恢复路径 <051-context-switch-saved-state-and-resume.rst>`_；
* `第052章：内核抢占模型与自愿抢占 <052-kernel-preemption-models-and-voluntary-preemption.rst>`_；
* `第053章：定时器基础设施与高精度定时器 <053-timer-infrastructure-and-high-resolution-timers.rst>`_；
* `第054章：时间维护、jiffies、Clocksource 与 Clockevents <054-timekeeping-jiffies-clocksource-and-clockevents.rst>`_；
* `第055章：抢占与定时器路径中的延迟来源 <055-latency-sources-in-preemption-and-timer-paths.rst>`_。

Part 12：中断、异常、Softirq、Tasklet 与 Workqueue
--------------------------------------------------

* `第056章：CPU 异常与硬件中断入口 <056-cpu-exceptions-and-hardware-interrupt-entry.rst>`_；
* `第057章：中断控制器、IRQ Domain 与 IRQ 描述符 <057-interrupt-controllers-irq-domains-and-descriptors.rst>`_；
* `第058章：上半部、下半部与延迟执行 <058-top-halves-bottom-halves-and-deferred-execution.rst>`_；
* `第059章：Softirq、Tasklet、Workqueue 与 Threaded IRQ <059-softirq-tasklet-workqueue-and-threaded-irqs.rst>`_；
* `第060章：中断风暴、延迟与调试策略 <060-interrupt-storms-latency-and-debugging.rst>`_。

Part 13：并发、锁、原子操作、内存屏障与 RCU
------------------------------------------

* `第061章：内核并发中的上下文、生命周期与顺序 <061-kernel-concurrency-context-lifetime-and-ordering.rst>`_；
* `第062章：Spinlock、Mutex、Semaphore 与读写锁 <062-spinlocks-mutexes-semaphores-and-rw-locks.rst>`_；
* `第063章：原子操作与内存顺序 <063-atomic-operations-and-memory-ordering.rst>`_；
* `第064章：内存屏障与 CPU 重排 <064-memory-barriers-and-cpu-reordering.rst>`_；
* `第065章：RCU Read-Copy-Update 同步模型 <065-rcu-read-copy-update.rst>`_。

Part 14：虚拟内存、地址空间与页表
--------------------------------

* `第066章：虚拟地址空间与 mm_struct <066-virtual-address-spaces-and-mm-struct.rst>`_；
* `第067章：页表、页表遍历与 TLB <067-page-tables-page-table-walks-and-tlbs.rst>`_；
* `第068章：用户地址空间与内核地址空间 <068-user-address-space-vs-kernel-address-space.rst>`_；
* `第069章：VMA、mmap 与地址空间布局 <069-vma-mmap-and-address-space-layout.rst>`_；
* `第070章：页表调试与地址转换证据 <070-page-table-debugging-and-address-translation-evidence.rst>`_。

Part 15：物理内存、Zone、NUMA 与页分配器
---------------------------------------

* `第071章：物理页、struct page 与内存模型 <071-physical-pages-struct-page-and-memory-models.rst>`_；
* `第072章：Zone、水位线与分配约束 <072-zones-watermarks-and-allocation-constraints.rst>`_；
* `第073章：Buddy 分配器与页分配路径 <073-buddy-allocator-and-page-allocation-paths.rst>`_；
* `第074章：NUMA 节点、局部性与内存策略 <074-numa-nodes-locality-and-memory-policy.rst>`_；
* `第075章：诊断物理内存碎片与压力 <075-diagnosing-physical-memory-fragmentation-and-pressure.rst>`_。

Part 16：内核内存分配、Slab、SLUB、Vmalloc 与 Per-CPU 内存
----------------------------------------------------------

* `第076章：内核分配器家族与分配上下文 <076-kernel-allocator-families-and-allocation-context.rst>`_；
* `第077章：kmalloc、kfree 与分配标志 <077-kmalloc-kfree-and-allocation-flags.rst>`_；
* `第078章：Slab 与 SLUB 对象缓存 <078-slab-and-slub-object-caches.rst>`_；
* `第079章：vmalloc 与非连续内核虚拟内存 <079-vmalloc-and-non-contiguous-kernel-virtual-memory.rst>`_；
* `第080章：Per-CPU 内存与可扩展分配模式 <080-per-cpu-memory-and-scalable-allocation-patterns.rst>`_。

Part 17：Page Cache、Writeback、Reclaim、Compaction 与 OOM
---------------------------------------------------------

* `第081章：Page Cache 是文件 I/O 的中心 <081-page-cache-as-the-center-of-file-io.rst>`_；
* `第082章：脏页、回写与 Flusher 线程 <082-dirty-pages-writeback-and-flusher-threads.rst>`_；
* `第083章：内存回收、LRU 列表与 kswapd <083-memory-reclaim-lru-lists-and-kswapd.rst>`_；
* `第084章：内存压缩、碎片与大页压力 <084-compaction-fragmentation-and-huge-page-pressure.rst>`_；
* `第085章：OOM Killer、内存死亡与生存诊断 <085-oom-killer-memory-death-and-survival-diagnostics.rst>`_。

Part 18：内存映射、缺页、写时复制与大页
--------------------------------------

* `第086章：缺页异常入口与故障分类 <086-page-fault-entry-and-fault-classification.rst>`_；
* `第087章：匿名内存与文件后备映射 <087-anonymous-memory-and-file-backed-mapping.rst>`_；
* `第088章：fork 之后的写时复制 <088-copy-on-write-after-fork.rst>`_；
* `第089章：透明大页与 HugeTLB <089-transparent-huge-pages-and-hugetlb.rst>`_；
* `第090章：诊断 Major Fault、Minor Fault 与内存异常 <090-debugging-major-faults-minor-faults-and-memory-surprises.rst>`_。

Part 19：文件描述符、VFS、Inode、Dentry 与 Superblock
----------------------------------------------------

* `第091章：文件描述符与进程文件表 <091-file-descriptors-and-the-process-file-table.rst>`_；
* `第092章：VFS 作为文件系统抽象层 <092-vfs-as-the-filesystem-abstraction-layer.rst>`_；
* `第093章：inode、dentry、file 与 super_block <093-inode-dentry-file-and-super-block.rst>`_；
* `第094章：路径查找、挂载与命名空间感知解析 <094-path-lookup-mounts-and-namespace-aware-resolution.rst>`_；
* `第095章：VFS 故障模式与文件系统级证据 <095-vfs-failure-modes-and-filesystem-level-evidence.rst>`_。

Part 20：ext4、XFS、Btrfs 与伪文件系统实现
-----------------------------------------

* `第096章：真实文件系统如何接入 VFS <096-how-real-filesystems-plug-into-vfs.rst>`_；
* `第097章：ext4 日志、Extent 与元数据一致性 <097-ext4-journaling-extents-and-metadata-consistency.rst>`_；
* `第098章：XFS 扩展性、Allocation Group 与大型文件系统 <098-xfs-scalability-allocation-groups-and-large-filesystems.rst>`_；
* `第099章：Btrfs COW、校验和与子卷 <099-btrfs-copy-on-write-checksums-and-subvolumes.rst>`_；
* `第100章：伪文件系统作为内核接口 <100-pseudo-filesystems-as-kernel-interfaces.rst>`_。

Part 21：Page Cache I/O、Direct I/O、异步 I/O 与 io_uring
--------------------------------------------------------

* `第101章：Buffered I/O 与 Page Cache 路径 <101-buffered-io-and-the-page-cache-path.rst>`_；
* `第102章：Direct I/O 与绕过 Page Cache <102-direct-io-and-bypassing-the-page-cache.rst>`_；
* `第103章：异步 I/O 与完成模型 <103-asynchronous-io-and-completion-models.rst>`_；
* `第104章：io_uring 作为现代 Linux I/O 接口 <104-io-uring-as-a-modern-linux-io-interface.rst>`_；
* `第105章：I/O 路径选择与性能权衡 <105-io-path-selection-and-performance-tradeoffs.rst>`_。

Part 22：块层、Bio、Request Queue、I/O Scheduler 与 Multi-Queue
---------------------------------------------------------------

* `第106章：从文件系统请求到块 I/O <106-from-filesystem-requests-to-block-io.rst>`_；
* `第107章：bio、Request 与块 I/O 数据模型 <107-bio-request-and-the-block-io-data-model.rst>`_；
* `第108章：Request Queue 与 I/O Scheduler <108-request-queues-and-io-schedulers.rst>`_；
* `第109章：blk-mq 与多队列扩展性 <109-blk-mq-and-multi-queue-scalability.rst>`_；
* `第110章：追踪块延迟与排队行为 <110-tracing-block-latency-and-queueing-behavior.rst>`_。

Part 23：存储设备、NVMe、SCSI、Device Mapper 与文件系统可靠性
-------------------------------------------------------------

* `第111章：从块层到设备的存储栈 <111-storage-stack-from-block-layer-to-device.rst>`_；
* `第112章：SCSI 与传统存储模型 <112-scsi-and-the-legacy-storage-model.rst>`_；
* `第113章：NVMe 队列、命令与高性能存储 <113-nvme-queues-commands-and-high-performance-storage.rst>`_；
* `第114章：Device Mapper、LVM、RAID 与分层块设备 <114-device-mapper-lvm-raid-and-layered-block-devices.rst>`_；
* `第115章：可靠性、Flush、FUA、Barrier 与崩溃一致性 <115-reliability-flush-fua-barriers-and-crash-consistency.rst>`_。

Part 24：设备模型、Kobject、Sysfs、Driver Core 与设备生命周期
-------------------------------------------------------------

* `第116章：Linux 设备模型作为内核对象层级 <116-linux-device-model-as-a-kernel-object-hierarchy.rst>`_；
* `第117章：kobject、kset、ktype 与引用生命周期 <117-kobject-kset-ktype-and-reference-lifetime.rst>`_；
* `第118章：Device、Driver、Bus 与 Class 关系 <118-device-driver-bus-and-class-relationships.rst>`_；
* `第119章：Sysfs 中的内核设备表示 <119-sysfs-representation-of-kernel-devices.rst>`_；
* `第120章：设备生命周期故障与 Driver Core 诊断 <120-device-lifetime-bugs-and-driver-core-diagnostics.rst>`_。

Part 25：Platform、PCI、USB、I2C、SPI、ACPI 与 Device Tree 总线框架
-----------------------------------------------------------------

* `第121章：总线框架作为驱动匹配与资源模型 <121-bus-frameworks-as-driver-matching-and-resource-models.rst>`_；
* `第122章：Platform 设备与板级硬件描述 <122-platform-devices-and-board-level-description.rst>`_；
* `第123章：PCI 枚举、BAR、MSI 与配置空间 <123-pci-enumeration-bars-msi-and-configuration-space.rst>`_；
* `第124章：USB、I2C 与 SPI 设备模型 <124-usb-i2c-and-spi-device-models.rst>`_；
* `第125章：ACPI 与 Device Tree 作为硬件描述机制 <125-acpi-and-device-tree-as-hardware-description-mechanisms.rst>`_。

Part 26：字符设备、块设备、网络设备与 Misc 驱动
------------------------------------------------

* `第126章：字符设备注册与 file_operations <126-character-device-registration-and-file-operations.rst>`_；
* `第127章：块设备驱动模型与请求处理 <127-block-device-driver-model-and-request-handling.rst>`_；
* `第128章：网络设备注册与 net_device 操作 <128-network-device-registration-and-net-device-operations.rst>`_；
* `第129章：Misc 驱动与简单内核接口 <129-misc-drivers-and-simple-kernel-interfaces.rst>`_；
* `第130章：选择正确的驱动抽象 <130-choosing-the-correct-driver-abstraction.rst>`_。

阅读方式
--------

按编号直接阅读和记忆即可。正文不设置问题、练习和互动环节。需要完整推导、源码例子或实验时，
使用每章末尾的 AIBook 来源链接。
