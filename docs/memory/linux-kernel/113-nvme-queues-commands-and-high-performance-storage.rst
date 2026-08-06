第113章：NVMe 队列、命令与高性能存储
=====================================

本章必须记住
------------

#. NVMe 是面向 PCIe 的队列协议，核心对象是 submission queue、completion queue、doorbell、command identifier 和 controller state。
#. NVMe 性能来自协议队列、blk-mq 映射、CPU 局部性、中断或 polling，以及控制器内部并行共同成立。
#. 仅凭“设备是 NVMe”不能推出低延迟；队列数量、深度、映射、IRQ、固件和恢复状态都可能成为瓶颈。
#. 一次普通数据路径是：block request → blk-mq hctx → NVMe queue → submission queue → doorbell → controller → completion queue → request completion。
#. NVMe queue pair 由一条 SQ 和一条 CQ 组成，host 提交命令，controller 写回完成项。
#. Submission queue 和 completion queue 通常位于 host 可 DMA 的内存中；doorbell 位于控制器寄存器空间。
#. Host 填写完整 command 后推进 SQ tail 并写 doorbell，controller 才能消费新命令。
#. Controller 写入 CQE 后更新 phase/status，host 根据 CQ head 与 phase 判断新完成。
#. SQ/CQ 中的 head、tail 和 phase 组成环形队列协议，不能只按数组索引静态理解。
#. Command identifier 用于把 completion 映射回在途命令，驱动通常进一步映射到 blk-mq request/tag。
#. NVMe CID 不等于 blk-mq tag，但驱动通常利用二者关系快速定位 request。
#. Tag 或 CID 在旧命令完全结束前不能复用，否则迟到 completion 会命中错误请求。
#. ``struct nvme_queue`` 一类对象保存 SQ、CQ、doorbell、queue depth、qid、vector 和队列游标。
#. ``nvme_queue_rq()``、``nvme_pci_complete_rq()`` 等是 PCIe host driver 常见源码锚点，精确函数拆分具有版本差异。
#. ``blk_mq_ops`` 把块层的 queue_rq、complete、map_queues、poll 等动作连接到 NVMe 驱动。
#. Admin queue 和 I/O queue 必须区分。
#. Admin queue 用于 Identify、Get Log Page、Set Features、创建/删除 I/O queue、namespace 管理等控制命令。
#. I/O queue 用于普通 read、write、flush、discard/DSM 等数据路径命令。
#. Controller 初始化通常先建立 admin queue，再 Identify controller/namespace，最后创建 I/O queues。
#. Admin queue 不可用时，普通 I/O queue 往往也无法建立或恢复。
#. Admin command 慢可能阻塞 reset、namespace scan、queue 创建和健康日志读取，不等于普通数据介质慢。
#. ``struct nvme_dev`` 一类对象通常同时保存 admin tagset、I/O tagset、queue 数量、depth 和 interrupt vectors。
#. I/O queue 数量受 controller capability、CPU 数量、MSI-X vector、驱动参数和内存资源共同限制。
#. ``nr_hw_queues`` 是 Linux blk-mq 可见队列数量，不必等于控制器理论最大队列数量。
#. Queue depth 表示一个队列能容纳的并发命令规模之一，实际可用量还受 reserved tag 和驱动限制。
#. 队列深度过低会限制并行，过高会增加设备内部排队、buffer 占用和 P99/P999 延迟。
#. 高吞吐 workload 需要足够在途命令，低延迟 workload 更关注控制队列长度和 completion 局部性。
#. 应用队列深度、blk-mq tag depth、NVMe SQ depth 和控制器内部执行并行度是不同层级。
#. 设备支持深队列不表示应用应无条件填满；过量在途请求只会把等待转移到更深层。
#. blk-mq queue map 决定提交 CPU 使用哪个 hctx，NVMe driver 再把 hctx 映射到某个 queue pair。
#. 多个 CPU 可以共享同一 NVMe queue，也可以按 CPU、NUMA 或 queue type 分配不同队列。
#. READ、DEFAULT、POLL 等 queue map 类型的支持取决于驱动和内核版本。
#. CPU 提交本地性、PCIe 设备 NUMA node、buffer node 和 IRQ CPU 应联合分析。
#. 提交 CPU 与 completion CPU 不一致会产生远程 cacheline、远程唤醒和 NUMA 开销。
#. MSI-X 允许不同 queue 使用不同 interrupt vector，是高并行 completion 的重要基础。
#. IRQ vector 数不足会让多个 queue 共享 vector，可能形成 completion 热点。
#. irqbalance、CPU hotplug、isolcpus 和手工 affinity 会改变实际中断分布。
#. ``/proc/interrupts`` 只显示 vector/IRQ 计数，还需结合 queue id、hctx 和驱动映射解释。
#. Polling 让 CPU 主动检查 CQ，降低 IRQ 和调度唤醒成本，但持续消耗 CPU。
#. IOPOLL 通常要求适合的 NVMe queue 和 Direct I/O 路径，不能机械用于任意 buffered I/O。
#. Poll queue 没有普通中断完成路径，其 CPU 映射与普通 I/O queue 可能不同。
#. Polling 适合 CPU 可专用、延迟目标极严的受控场景，不应作为普通系统默认优化。
#. Doorbell 写是 host 通知 controller 队列推进的 MMIO 操作；频繁小批量 doorbell 会增加 PCIe 与 CPU 开销。
#. 批量提交可以摊薄 doorbell 和队列同步成本，也可能增加首个请求等待时间。
#. Controller 通过 DMA 读取 command 和写 completion，IOMMU、PCIe 链路和 DMA 映射仍影响路径。
#. NVMe read/write command 表达 namespace identifier、LBA、长度和控制字段；块层 sector 必须转换为 namespace LBA。
#. Namespace 是 controller 暴露的逻辑存储空间，不等于一块独立物理 NAND 介质。
#. 一个 controller 可以暴露多个 namespace；一个 namespace 也可能通过 NVMe multipath 由多个 path 访问。
#. Namespace 容量、LBA format、metadata 和 protection information 会影响命令构造。
#. Flush 命令用于让 controller 对应 namespace 的易失写缓存达到持久化边界，具体范围按规范与设备实现解释。
#. FUA 可在支持时附加到写命令，要求该写在完成前达到非易失状态。
#. NVMe completion status 是协议级结果，不应只压缩成 ``EIO`` 后丢失详细状态。
#. 状态字段可区分 invalid field、LBA range、namespace not ready、media/data integrity、abort 等类别。
#. 同一个状态在不同命令类型和 controller state 下意义不同，必须结合 opcode、qid、cid、nsid 和日志。
#. Command timeout 表示 host 未在期限内收到期望 completion，不自动等于命令从未执行。
#. Timeout 后驱动可能先尝试 Abort admin command，再进入 controller reset。
#. Abort 成功表示目标命令被终止或进入相应状态，不自动回滚已完成写入。
#. Controller reset 会停止或冻结 I/O queue、重新初始化 controller、重建 queue 并重新扫描 namespace。
#. Reset 影响整个 controller 上的多个 namespace 和大量在途 request，不是单命令局部动作。
#. Reset 期间请求可能 requeue、失败或等待恢复；最终语义取决于 request 状态和驱动策略。
#. Controller state 常见有 live、resetting、connecting、deleting、dead 等概念，具体枚举随版本变化。
#. Live 表示可正常提交，resetting 表示恢复中，dead 表示无法继续正常 I/O。
#. Namespace 消失、容量变化或 ANA 状态变化可能触发重扫、path 切换或设备不可用。
#. NVMe multipath 中 namespace head 与 path/controller 对象必须区分。
#. ANA optimized、non-optimized、inaccessible 等状态影响 path 选择，不等于介质数据内容状态。
#. PCIe AER、link retrain、IOMMU fault、controller fatal status 和 firmware bug 都可能表现为 NVMe timeout/reset。
#. 设备内部 garbage collection、thermal throttling、wear leveling 和 background media scan 会影响 service time。
#. 温度、power state、APST 和 PCIe ASPM 可能降低功耗，同时增加唤醒延迟或抖动。
#. 低延迟场景应把 power state 与 queue/IRQ 一起测量，不能只关闭一个节能选项后下结论。
#. ``nvme list``、``nvme id-ctrl``、``id-ns``、``smart-log`` 和 ``error-log`` 用于建立 controller/namespace 状态。
#. 管理命令会占用 admin queue；高频采集健康日志也可能干扰控制面。
#. ``/sys/class/nvme/``、``/sys/block/nvme*/mq/`` 和 PCI sysfs 可观察队列、NUMA 和设备关系，文件集合依版本而异。
#. ``iostat`` 显示 namespace 块设备聚合，不能解释具体 SQ/CQ、doorbell、IRQ 或 reset。
#. Block trace 可分解 insert/issue/complete，NVMe trace/log 补充 command、qid、cid 和 status。
#. ``block_rq_issue`` 不等于 doorbell 已写，更不等于 controller 已开始介质操作。
#. ``block_rq_complete`` 表示驱动向块层完成 request，不等于应用线程已经被调度并消费结果。
#. 大量 issue 后 service time 增长应检查 controller queueing、介质、thermal、retry 和 reset。
#. 大量 request 在 issue 前等待应检查 blk-mq tag、scheduler、hctx 和应用队列深度。
#. 单个 CPU completion 热点应检查 MSI-X、queue mapping、IRQ affinity 和 poll 配置。
#. Reset storm 应检查首个 timeout 根因，而不是只统计 reset 次数；后续 reset 往往是恢复链的放大结果。
#. 设备恢复后要验证 controller live、queue 重建、namespace 可见、错误停止增长和业务 I/O 正常。
#. NVMe 的高性能本质是队列拓扑工程：命令必须以合适深度从合适 CPU 到合适 queue，并在合适 CPU 完成。
#. 最稳定源码阅读顺序是：blk-mq request/tag → queue map → ``nvme_queue`` → command/SQ/doorbell → CQE/status → completion/reset。
#. 精确 opcode、status、queue field、module parameter 和 reset 函数属于规范、版本与驱动敏感细节。

必背路径
--------

普通 NVMe I/O：

::

   bio/request 进入 blk-mq
   → queue map 选择 hctx
   → hctx 对应 nvme_queue
   → 分配 request tag / command identifier
   → 构造 nvme_command
   → 写入 submission queue
   → 更新 SQ tail 并写 doorbell
   → controller 执行命令
   → 写 completion queue entry
   → 驱动按 CID/tag 找到 request
   → 完成块请求

Controller 初始化：

::

   PCI device enable 与 BAR 映射
   → 建立 admin SQ/CQ
   → Identify controller
   → 读取能力与 queue limit
   → 创建 I/O completion/submission queues
   → 建立 blk-mq queue map
   → 扫描 namespace
   → controller 进入 live

Timeout 与 reset：

::

   request 超时未完成
   → 检查 controller/queue 状态
   → 尝试 Abort 命令
   → 停止或冻结 I/O queues
   → controller reset
   → 重建 admin 和 I/O queues
   → 重新扫描 namespace
   → requeue 或失败旧 request
   → 恢复正常提交

检查队列拓扑：

::

   确认 controller 与 namespace
   → 查看 nr_hw_queues 和 queue depth
   → 查看 CPU-to-hctx map
   → 对齐 NVMe queue 与 MSI-X vector
   → 查看 /proc/interrupts 分布
   → 对齐应用 CPU 与 buffer NUMA node
   → 检查 polling/power state
   → 复测吞吐和 P99

诊断 service time：

::

   block_rq_issue 时间
   → NVMe queue/doorbell 提交
   → controller queue 等待
   → 介质与固件执行
   → CQE 到达
   → block_rq_complete
   → 关联 qid/cid/status/temperature/reset
   → 判断队列、设备或恢复问题

必须区分
--------

* Admin queue 与 I/O queue：前者管理 controller 和 namespace；后者执行正常数据读写。
* blk-mq hctx 与 NVMe queue pair：Hctx 是块层派发对象；驱动把它映射到协议 SQ/CQ。
* Blk-mq tag 与 NVMe CID：二者处于不同层级，但驱动利用映射把 completion 找回 request。
* Queue depth 与设备并行度：深度是允许在途命令规模；控制器实际并行还受固件和介质限制。
* Interrupt completion 与 Polling：前者由设备通知 CPU；后者由 CPU 主动检查 CQ，资源成本不同。
* Reset 恢复与写入回滚：Reset 重建控制器命令通路，不能自动撤销可能已执行的数据写入。

一句话结论
----------

NVMe 把存储访问变成多队列命令协议，性能与可靠性取决于 blk-mq、SQ/CQ、tag、CPU/IRQ 局部性和 controller 状态机共同闭合。
