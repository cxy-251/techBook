第138章：CPU 热插拔、内存热插拔与设备热插拔
===========================================

核心知识点
----------

Hotplug 是运行时拓扑变化
   CPU、物理内存或设备在系统运行期间进入或退出可用集合，内核必须同时更新对象状态、调度关系、资源依赖和用户可见表示。

三类热插拔共享退出骨架
   共同原则是先阻止新工作，再迁移或排空旧工作，随后撤销可见性，最后等待引用和异步路径结束。

CPU 具有多级存在状态
   ``possible`` 表示理论上可能存在，``present`` 表示当前拓扑中存在，``online`` 表示可参与调度、中断和普通 per-CPU 工作。

CPU Offline 是全系统迁移操作
   下线前要迁移任务、timer、IRQ、workqueue 与队列目标，并执行 cpuhp teardown callback。Pinned task、affinity 和无合法目标都可能阻止下线。

Per-CPU 状态必须跟随 CPU 生命周期
   子系统的 per-CPU 对象、缓存和线程要在上线阶段建立，在下线阶段停止访问并释放或迁移，不能把 online CPU 当成永久集合。

内存加入与 Online 不同
   新物理范围先建立 memory model、direct map、node/zone 和 sysfs 表示，只有 online 后页面才进入普通 page allocator。

Memory Offline 依赖页面可迁移性
   下线目标不是让系统“有足够空闲内存”，而是让指定 PFN 范围中的页全部迁出或释放。长期 pin、HugeTLB、内核对象和设备 DMA 都可能阻止下线。

设备热插拔改变硬件可用性
   总线 add 会创建设备并触发 match/probe；remove 会让硬件立即或逐步消失。软件对象可因 fd、mmap 和引用继续存活，但必须拒绝后续硬件访问。

撤销可见性不等于对象释放
   CPU 从 online mask 移除、memory block offline、``device_del()`` 或 unbind 都只改变某一层状态，残余引用和异步执行仍需分别收束。

热插拔会与 PM 和 I/O 并发
   Runtime PM、system suspend、reset、DMA completion 和用户访问都可能跨越拓扑变化，驱动和子系统必须使用统一 generation 与退出状态。

关键路径
--------

CPU Offline：

::

   请求目标 CPU offline
   → 停止向其分配新工作
   → 迁移任务与可迁移内核线程
   → 迁移 timer、IRQ、workqueue 和设备队列
   → 反向执行 cpuhp teardown callbacks
   → 架构关闭目标 CPU
   → 从 cpu_online_mask 移除

Memory Offline：

::

   选择 memory block
   → 阻止目标范围新分配
   → 隔离 pageblocks
   → 迁移可移动页并回收空闲页
   → 检查 pin、HugeTLB、内核对象与 DMA
   → 目标范围清空
   → 从 page allocator 下线
   → 平台完成物理移除

Device Remove：

::

   总线报告 disconnect/remove
   → 设置 removing/disconnected
   → 撤销新 open、I/O 与上层队列
   → 停止 DMA 和设备 IRQ
   → 等待 request、completion、work、timer、NAPI、RCU
   → device_del / unbind
   → 最后引用归零
   → release 宿主对象

概念辨析
--------

* Present 与 Online：对象存在不表示已进入普通调度、分配或 I/O 可用集合。
* 系统空闲内存与目标内存可移除：总量充足不表示目标 PFN 范围没有不可迁移页。
* Driver Unbind 与 Physical Remove：Unbind 只改变控制关系；物理移除可能立即终止 MMIO、DMA 和协议访问。
* 撤销可见性与释放对象：从索引或 sysfs 消失只阻止新发现；旧引用仍可能保留对象。
* 软件对象寿命与硬件能力：引用可延长软件对象寿命，不能延长已经消失的 CPU、内存或设备能力。

本章结论
--------

热插拔把启动时静态拓扑变成运行时状态机；正确性取决于先停止新工作、迁移或排空旧工作，再改变可用集合，并在最后引用和异步路径结束后完成释放。
