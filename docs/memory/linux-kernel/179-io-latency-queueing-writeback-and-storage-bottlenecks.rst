第179章：I/O 延迟、排队、Writeback 与存储瓶颈
=============================================

本章必须记住
------------

#. 存储性能调查必须把应用等待、文件系统、Page Cache、Writeback、块层排队、设备服务和完成通知分开。
#. 应用看到的 I/O 延迟通常大于块设备 Request 的统计延迟，因为上层锁、分配、节流和调度等待不在设备统计中。
#. Buffered ``write()`` 返回通常只证明数据进入 Page Cache，不证明设备已经完成写入。
#. ``fsync()`` 可能承担此前多个 ``write()`` 累积的脏数据、元数据、Journal 和 Flush 成本。
#. Direct I/O、Buffered I/O、DAX、Network Filesystem 和 Device Mapper 的路径与完成语义不同，不能混用统计口径。
#. 块设备统计是累计 Counter，必须取两个时间点差值才能得到当前窗口 Rate。
#. ``/proc/diskstats`` 和 ``/sys/block/<dev>/stat`` 描述块设备层事件，不是应用请求的端到端追踪。
#. ``iostat`` 等工具通常基于这些 Counter 计算速率、平均队列和平均等待。
#. ``await`` 通常包含块层排队和服务时间，不包含请求进入块层之前的完整应用等待。
#. ``aqu-sz`` 是平均排队/在途规模线索，不能单独说明每个请求的尾延迟。
#. ``%util`` 对串行设备较容易解释，对 NVMe、RAID、DM、虚拟盘和多队列设备不能机械等同于性能上限。
#. 高 Util、低 Queue 和低 Latency 可能是健康的并行设备正常工作状态。
#. 低 Util 也不排除单 Queue、Flush、Throttle、Lock 或上层串行化瓶颈。
#. 设备吞吐没有升高而应用延迟升高时，应优先检查文件系统锁、Dirty Throttling、Cgroup、调度和上层队列。
#. ``write()`` 很快而后台设备持续写出，说明成本被 Page Cache 延迟暴露。
#. Page 从 Clean 变为 Dirty 后，稍后由 Writeback 选择、提交并在 Completion 后恢复干净状态。
#. Background Threshold 到达时后台 Flusher 开始写出；更高阈值可让前台写入者被节流。
#. Dirty Throttling 把设备跟不上写入速度的成本反馈到产生脏页的 Task。
#. ``Dirty`` 表示待写脏页规模，``Writeback`` 表示正在写出的页面规模；二者是快照，不是延迟。
#. Dirty 持续增长且设备吞吐接近能力上限，说明产生速度大于设备吸收速度。
#. Dirty 周期性堆高并伴随写入 ``p99`` 尖峰，常指向 Writeback Burst 或阈值触发。
#. ``balance_dirty_pages`` 一类路径体现前台 Dirty 控制；``fs/fs-writeback.c`` 一类路径组织 Inode 与 Worker 回写。
#. Dirty 参数改变成本积累位置，不会提高底层设备的真实服务能力。
#. 增大 Dirty Limit 可让前台短期更快，也会增加后续 Burst、数据风险和 ``fsync`` 尾延迟。
#. 降低 Dirty Limit 可更早回写，也可能增加写入频率、设备争用和前台节流。
#. Flush 周期、脏页过期和阈值必须结合内存容量、设备能力和业务持久化语义测量。
#. 文件系统 Journal、Metadata、Data 和 Barrier/Flush 顺序会影响 ``fsync`` 延迟。
#. ``fsync()`` 成功语义依文件系统、设备缓存、Flush/FUA 支持和错误传播，不能只看平均设备延迟。
#. 写缓存开启可降低表面延迟，也可能改变掉电一致性边界。
#. Flush/FUA 频繁时，吞吐不高也可能出现显著同步延迟。
#. 进入块层后，``bio`` 描述数据范围，``request`` 是调度和驱动执行单位。
#. blk-mq 把上层提交连接到软件上下文队列、Hardware Context 和设备驱动 Queue。
#. 一个设备可有多个 Hardware Queue；整机平均值会隐藏单队列热点。
#. Queue Depth 表示可并行或在途请求数量，不等于设备真实有效并行度。
#. 增加 Queue Depth 可能提高吞吐，也会增加等待、内存、超时和恢复复杂度。
#. Queue 太浅会让设备缺少并行工作，Queue 太深会让尾延迟和取消成本升高。
#. Request Merge 可减少提交开销和提高顺序性，也可能让单个 Request 更大、完成粒度更粗。
#. NVMe 通常依赖多队列并行；SATA、虚拟盘、网络盘和 RAID 的最佳 Queue 形态不同。
#. Software Queue、Hardware Dispatch Queue、Driver Ring 和设备内部 Queue 是不同层级。
#. Block Scheduler 只控制其中一部分软件调度行为，不等于控制设备内部 Firmware 排队。
#. ``none``、``mq-deadline``、BFQ 等调度器具有不同目标，不能脱离设备和业务直接评判。
#. Latency-sensitive 与 Throughput-oriented 工作负载可能需要不同调度策略。
#. blk-mq Tag 耗尽、Budget 不足或 Driver 返回 Resource 会导致请求在软件层重新等待。
#. Request 已形成不表示已经提交到硬件；Issue/Dispatch Event 才接近设备接管边界。
#. Completion Event 表示块层收到完成，不自动等于用户线程已经被调度并返回。
#. I/O Trace 应至少区分 Submit、Insert/Merge、Issue/Dispatch、Complete 和 Wakeup。
#. 单个平均 ``await`` 无法分辨延迟发生在 Queue 还是设备服务，应使用阶段事件或 Histogram。
#. ``block_rq_issue`` 到 ``block_rq_complete`` 可近似某段设备在途时间，精确字段和语义依版本。
#. 从应用 Syscall 到 Block Issue 的时间包含 Page Cache、Filesystem、Lock、Allocation、Throttle 等上层成本。
#. Block Complete 到应用恢复还包含 Completion Callback、Wakeup 和 Scheduler Latency。
#. Tail Latency 必须用分布观察；平均服务时间稳定时，少量 Flush、Reset、GC 或 Error Recovery 仍可产生长尾。
#. SSD Firmware Garbage Collection、Thermal Throttle、Media Error 和内部 Queue 不一定被内核直接细分暴露。
#. NVMe SMART/Health、Error Log、Reset 和 Timeout 日志是设备侧重要证据。
#. 设备 Reset、Timeout 和 Retry 会把单次故障放大为秒级尾延迟。
#. 增大 Timeout 只会延后失败，不会修复设备不完成 Request。
#. RAID Rebuild、Scrub、Snapshot、Thin Provisioning、Encryption 和 Compression 会在块设备下方或上方增加成本。
#. Device Mapper 需要按真实栈逐层识别，顶层 ``dm-*`` 统计不总能直接定位底层瓶颈。
#. LVM、MD、DM-crypt、Thin、Multipath、Network Block 和虚拟化都可能改变 Queue 与完成语义。
#. Cgroup I/O Controller 可在设备仍有余量时限制目标工作负载。
#. 调查容器 I/O 必须检查目标 Cgroup 的 ``io.stat``、``io.max``、``io.weight`` 和真实 Major:Minor。
#. Application Queue、Thread Pool 和 Async Runtime 也会在进入内核前排队。
#. io_uring SQ/CQ、AIO Context 和用户态 Batch 是独立队列，不能用块层 Queue 代替解释。
#. 同步 I/O 的线程数增加可提高并行度，也会增加 Context Switch、Memory、Lock 和设备 Queueing。
#. Async I/O 提交成功不表示 Request 已完成；Completion Queue 才是所有权返回边界。
#. Read-ahead 可减少顺序读取 Fault/I/O 次数，也可能污染 Page Cache 和挤压别的工作集。
#. Direct I/O 可避免 Page Cache 双重缓存，也会暴露 Alignment、设备延迟和应用 Buffer 生命周期要求。
#. Buffer Alignment、Block Size、Request Size 和 Access Pattern 会影响 Merge、Queue 和设备效率。
#. 小随机 I/O、顺序大块 I/O、Flush-heavy 和 Mixed Read/Write 负载不能用同一吞吐指标比较。
#. 设备带宽、IOPS 和 Latency 是不同能力维度。
#. 高带宽不表示小 I/O IOPS 高，高 IOPS 不表示 Flush 延迟低。
#. Little's Law 可帮助连接平均在途量、吞吐和平均延迟，但不替代尾部分布和 Burst 分析。
#. I/O PSI 表示任务因 I/O 等待失去进展的时间，不等于设备 Utilization。
#. I/O PSI 上升而设备统计平稳，可能来自 Cgroup、Network FS、上层锁或设备栈映射错误。
#. 应用 ``p99``、Syscall Histogram、Block Histogram、Device Counter 和 Error Log 必须放在同一时间轴。
#. 修改 I/O Scheduler、Queue Depth、Read-ahead 或 Dirty 参数前必须保存原值和回滚路径。
#. 一次只改一个关键变量，并同时验证吞吐、``p99``、Queue、PSI、内存和错误恢复。
#. 设备参数收益可能依 Firmware、Kernel、Driver、Filesystem 和 Workload 版本变化。
#. 稳定调查顺序是：应用调用 → Page Cache/Filesystem → Dirty/Writeback → Bio/Request → blk-mq Queue → Driver/Device → Completion/Wakeup。

必背路径
--------

Buffered Write：

::

   Application write
   → VFS / Filesystem
   → Copy Data into Page Cache
   → Mark Page Dirty
   → write 可能返回
   → Dirty Threshold / Expiration / fsync 触发 Writeback
   → Filesystem 生成 Bio
   → Block Layer 形成 Request
   → blk-mq Dispatch
   → Device Completion
   → 清理 Writeback/Dirty 状态
   → fsync 或等待者返回

块层阶段延迟：

::

   Bio Submit
   → Request Allocation / Merge
   → Software Queue
   → Scheduler / Tag / Budget
   → Hardware Context Dispatch
   → Driver Ring / Device Queue
   → Device Service
   → Interrupt / Poll Completion
   → blk_mq_end_request
   → 上层 Completion 与 Task Wakeup

I/O 长尾诊断：

::

   固定慢 Syscall 或业务请求
   → 采集 Application Latency Histogram
   → 对齐 Dirty、Writeback 和 I/O PSI
   → 记录 Block Submit/Issue/Complete
   → 计算 Queue Time 与 Service Time 分布
   → 检查 Per-queue、Cgroup 与 Device Stack
   → 检查 Flush、Reset、Timeout、Firmware 与 Error
   → 找到最早出现长尾的阶段

安全调优：

::

   保存 Filesystem、Scheduler、Queue、Dirty 与 Device 配置
   → 选择一个明确假设
   → 修改一个 Queue/Writeback/Scheduler 变量
   → 保持 I/O Pattern 和并发一致
   → 比较 Throughput、p99、Queue、PSI 与 Error
   → 验证 Flush/Recovery 和数据一致性
   → 回滚或固化

必须区分
--------

* 应用等待与设备服务：前者覆盖完整调用，后者只覆盖块层/设备的一部分。
* ``write()`` 返回与持久化完成：进入 Page Cache 不等于介质完成。
* Buffered I/O 与 Direct I/O：缓存、对齐、完成和延迟暴露方式不同。
* Dirty 与 Writeback：待写页面和正在写出的页面不同。
* Bio 与 Request：数据描述和块层执行/调度单位不同。
* Queue Depth 与设备并行度：在途数量不等于硬件有效吞吐能力。
* Software Queue 与 Device Queue：内核排队和 Firmware/Hardware 排队不同。
* ``await`` 与端到端延迟：设备统计不覆盖全部上层和唤醒成本。
* Utilization 与 Saturation：设备忙不等于所有请求已排队到极限。
* Timeout 与修复：延长等待不会让丢失 Completion 自动出现。

一句话结论
----------

存储性能调查必须把“应用何时开始等待、成本何时进入 Writeback、Request 何时排队、设备何时服务、Completion 何时唤醒”逐段量化。
