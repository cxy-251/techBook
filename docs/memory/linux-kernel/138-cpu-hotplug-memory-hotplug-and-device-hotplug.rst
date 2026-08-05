第138章：CPU 热插拔、内存热插拔与设备热插拔
===========================================

本章必须记住
------------

#. Hotplug 是运行时拓扑变化：CPU、物理内存或设备在系统运行期间进入或退出可用集合。
#. 三类热插拔的共同骨架是：发现对象 → 发布表示 → 进入可用集合 → 停止新工作 → 迁移/排空旧工作 → 撤销可见性 → 最后释放。
#. 热插拔问题首先要问“哪个对象从哪个集合进入或退出”，再问“哪些子系统已经依赖它”。
#. CPU、内存和设备各有独立状态机，不能用 device remove 模型直接解释 CPU 或内存下线。
#. CPU 的 possible、present、online 是不同集合。
#. ``possible`` 表示内核为其预留过资源、理论上可能存在；``present`` 表示拓扑中存在；``online`` 表示可参与调度和中断处理。
#. 只有进入 ``cpu_online_mask`` 后，CPU 才能承担普通任务、定时器、中断和多数 per-CPU 工作。
#. CPU hotplug 通过有序状态机执行各子系统 startup/teardown callback，具体状态名具有版本差异。
#. CPU 上线时需要准备 per-CPU 数据、runqueue、timer、RCU、workqueue、IRQ 和架构状态。
#. CPU 下线时先停止新任务定向，再迁移任务、timer、IRQ 与可迁移工作，最后执行低层 teardown。
#. 绑定到特定 CPU 的任务、内核线程、IRQ 或队列可能阻止下线或造成服务退化。
#. CPU affinity 与 cpuset 约束可能让任务没有合法迁移目标。
#. IRQ affinity 在目标 CPU 下线时必须重新选择在线 CPU，否则设备可能失去 completion 路径。
#. 多队列网卡、NVMe 和 blk-mq 设备需要重新平衡 queue、IRQ vector 和 CPU locality。
#. Per-CPU 对象不能在 CPU 下线后仍由普通路径无保护访问。
#. CPU hotplug callback 必须处理重复上线/下线和中途失败回滚，不能只写一次启动逻辑。
#. 内存热插拔分为“加入 Linux 管理”和“online 给 page allocator”两个阶段。
#. Memory block 是常见用户态热插拔粒度，实际粒度由架构、SPARSEMEM 和配置决定。
#. 新增物理地址范围需要建立内存模型 metadata、direct mapping、node/zone 关系和 sysfs 表示。
#. Memory block online 后，其页才进入普通页分配器可用集合。
#. Online 类型可能影响新增内存进入普通 zone、MOVABLE zone 或内核选择的有效 zone。
#. 内存 offline 的核心不是删除 sysfs 文件，而是确保目标范围内所有可迁移页都已迁走或释放。
#. Offline 路径会隔离页块、阻止新分配、迁移可移动页，并检查剩余不可迁移引用。
#. 被长期 pin、HugeTLB、不可迁移 slab、内核对象、页表、设备 DMA 或特殊保留页占用的范围可能无法下线。
#. Memory offline 失败通常不表示总内存不足，而表示目标物理范围内仍有无法迁移对象。
#. NUMA node、zone watermark、cpuset 和 memory policy 会因内存上线下线重新计算或受到影响。
#. 不能只看 ``MemFree`` 判断某个 memory block 是否可移除；必须定位该范围内页面类型和引用。
#. 内存下线成功后仍要等待架构和平台完成物理移除，二者是不同阶段。
#. 设备热插拔把总线事件转换成 ``struct device`` 创建、匹配、probe、remove、uevent 和最终 release。
#. USB、PCIe、Thunderbolt、virtio 等总线的发现机制不同，但 driver core 生命周期骨架相同。
#. 设备 add 后可能立即匹配驱动和进入 probe，因此资源与对象状态必须在发布前准备好。
#. 物理移除事件到来时，驱动应先设置 disconnected/removing，阻止新 open、I/O 和控制操作。
#. ``device_del``、driver unbind 或 bus remove 撤销可见性，不自动结束旧 fd、mmap、DMA、work、timer 和 IRQ。
#. 热拔插后软件对象可因引用继续存活，但硬件访问能力已经消失。
#. 旧 fd 对已断开设备通常应返回 ``-ENODEV``、EOF 或子系统规定的断开结果，不能继续访问寄存器。
#. 设备 remove 必须先停止新请求，再停止硬件队列、DMA 和 IRQ，等待异步路径，最后释放内存。
#. ``synchronize_irq()`` 只等待 handler；NAPI、tasklet、workqueue、timer、RCU、completion 和普通引用仍需分别收束。
#. USB URB、块 request、网络 skb 和字符设备会话拥有不同的取消与完成协议。
#. 取消成功不表示硬件副作用自动回滚，也不表示迟到 completion 不会出现。
#. Generation/tag 可帮助识别旧 completion，但不能阻止旧设备 DMA 覆盖已复用内存。
#. Driver unbind 是软件绑定变化，物理设备可以仍在；物理 remove 则可能使 MMIO 和配置空间立即不可访问。
#. Rebind 前应保证上一驱动已彻底停止设备，避免新驱动继承仍运行的 DMA 或 IRQ 状态。
#. Hotplug 与 Runtime PM 会并发：设备可能在 runtime suspended 时被移除，remove 仍需建立安全停止和最终状态。
#. Hotplug 与 system suspend 会并发：PM core、driver core 和总线必须序列化设备列表和回调状态。
#. CPU hotplug 与 system suspend 也会交叉，例如深度睡眠会暂时下线非启动 CPU。
#. Memory hotplug 与页迁移、compaction、reclaim、NUMA balancing 共享迁移机制，但目标和失败语义不同。
#. CPU hotplug 回调、memory notifier 和 device notifier 都属于变化通知，不自动保证调用者对象生命周期。
#. Notifier callback 不能在不允许的上下文中执行睡眠或长时间阻塞，具体规则取决于 notifier 类型。
#. 用户态常通过 sysfs 请求 CPU/内存 online/offline，写入会实际改变系统拓扑，必须在实验环境操作。
#. ``/sys/devices/system/cpu/{possible,present,online}`` 是 CPU 集合证据。
#. ``/sys/devices/system/memory/memoryX/state``、``valid_zones`` 等是 memory block 证据，字段随版本和配置变化。
#. ``udevadm monitor``、sysfs canonical path 和 ``dmesg`` 可观察设备 add/remove/bind/unbind 时间线。
#. ``/proc/interrupts`` 可观察 CPU 下线前后 IRQ 迁移结果，但计数变化不能说明所有设备队列已重新平衡。
#. ``lscpu``、``numactl``、``lsmem`` 等工具是聚合视图，关键结论仍要回到 sysfs 和内核状态。
#. CPU offline 卡住时，应检查 pinned task、hotplug callback、IRQ、timer、RCU 和架构日志。
#. Memory offline 失败时，应检查目标 PFN 范围、不可迁移页、长期 pin、HugeTLB、内核分配和设备 DMA。
#. Device remove 卡住时，应检查旧 fd、队列、IRQ、DMA、work、timer、runtime PM 和总线 reset。
#. 只在重复插拔后失败通常指向引用、generation、资源重复注册或 teardown 不完整。
#. 只在高负载拔出时失败通常指向在途 I/O、completion、DMA 和上层入口关闭顺序。
#. 只在 CPU/内存拓扑变化后性能下降，需检查 affinity、NUMA locality、queue mapping 和内存策略重建。
#. 精确 sysfs 文件、hotplug state 名称和回调接口具有架构、配置与版本差异。
#. 稳定源码阅读顺序是：事件来源 → 对象状态机 → 可用集合变化 → 工作迁移/排空 → 撤销发布 → 引用归零与最终释放。

必背路径
--------

CPU Offline：

::

   用户/平台请求 CPU offline
   → 标记目标 CPU 不再接收新工作
   → 迁移普通任务和可迁移内核线程
   → 迁移 timer、IRQ 和队列目标
   → 按 cpuhp 反向执行 teardown callbacks
   → 架构关闭目标 CPU
   → 清除 cpu_online_mask

Memory Offline：

::

   选择 memory block
   → 阻止目标范围新分配
   → 隔离 pageblocks
   → 扫描并迁移可移动页
   → 回收空闲页和可释放对象
   → 检查不可迁移页/长期 pin
   → 全部清空后从 page allocator 下线
   → 平台执行物理移除

Device Remove：

::

   总线检测 disconnect/remove
   → 设置 removing/disconnected
   → 撤销用户入口和上层队列
   → 取消新请求
   → 停止 DMA 与设备 IRQ
   → 等待 completion、worker、timer、NAPI、RCU
   → 释放总线和硬件资源
   → device_del / put_device
   → 最后引用归零后 release

热插拔故障定位：

::

   确认 CPU / memory / device 对象
   → 确认当前 possible/present/online 或 bind 状态
   → 找出仍依赖该对象的任务、页、IRQ、请求
   → 对齐 hotplug callback 与日志
   → 判断失败在迁移、排空、解绑还是最终 release
   → 复测重复插拔和高负载场景

必须区分
--------

Present 与 Online
   对象存在不表示已进入普通调度、分配或 I/O 可用集合。

撤销可见性与释放对象
   从 sysfs/driver core 移除只阻止新查找；旧引用可能继续存活。

Software Object Lifetime 与 Hardware Availability
   对象可被引用保留；物理设备、CPU 或内存能力可能已经消失。

Memory Free 与 Memory Removable
   系统有空闲内存不表示目标物理范围内没有不可迁移页。

Driver Unbind 与 Physical Remove
   Unbind 改变驱动控制关系；physical remove 可能立即终止硬件访问。

一句话结论
----------

热插拔把启动时的静态拓扑变成运行时状态机，正确退出取决于先撤销新工作、迁移或排空旧工作，再从可用集合移除并等待最后引用释放。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 28，Power Management, Hotplug, Firmware Loading, and Runtime PM；
* AIBook 章节：Chapter 138，CPU Hotplug, Memory Hotplug, and Device Hotplug；
* 源文件：``docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_138_CPU_Hotplug_Memory_Hotplug_and_Device_Hotplug.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_138_CPU_Hotplug_Memory_Hotplug_and_Device_Hotplug.md>`_。