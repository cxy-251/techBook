第113章：NVMe 队列、命令与高性能存储
=====================================

核心知识点
----------

NVMe 是 PCIe 原生队列协议
   Host 通过 Submission Queue 发布命令，controller 通过 Completion Queue 返回结果；doorbell、CID、phase 和 queue state 共同构成协议。

块层与协议队列是两层对象
   blk-mq 的 ``blk_mq_hw_ctx`` 和 tag 属于 Linux 块层；NVMe SQ/CQ 与 command identifier 属于协议和驱动层。驱动负责建立映射。

Admin Queue 与 I/O Queue 职责不同
   Admin Queue 执行 Identify、Get Log Page、Set Features 和队列管理；I/O Queue 执行普通 read、write、flush 等数据命令。

队列深度不是设备并行度
   应用 outstanding、blk-mq tag depth、NVMe SQ depth 和控制器内部执行能力是不同层级。过深队列会增加排队和尾延迟。

队列拓扑决定 CPU 成本
   提交 CPU、hctx、NVMe queue、MSI-X vector、completion CPU、buffer NUMA node 和 PCIe 设备位置共同影响局部性。

Doorbell 是显式发布动作
   Host 填写完整 command、推进 SQ tail 并写 doorbell 后，controller 才能消费。批量可摊薄 MMIO 成本，也会增加等待。

Completion 依赖身份复用安全
   Controller 写 CQE 后，驱动通过 CID/tag 找回 request。旧命令完全结束前不得复用身份，否则迟到完成会命中新请求。

Interrupt 与 Polling 是不同完成策略
   Interrupt 由设备通知 CPU；polling 由 CPU 主动检查 CQ。Polling 可降低唤醒成本，但持续消耗 CPU，并要求合适路径支持。

协议状态必须保留
   NVMe status 能区分 invalid field、namespace not ready、media/data integrity、abort 等原因。仅保留 ``EIO`` 会丢失关键证据。

Reset 是控制器级恢复
   Timeout 后驱动可能先 abort，再冻结队列、reset controller、重建 admin/I/O queues 并重扫 namespace。该过程影响大量在途请求。

关键路径
--------

普通 NVMe I/O：

::

   block request
   → blk-mq 选择 hctx
   → 映射到 nvme_queue
   → 分配 tag / CID
   → 构造 nvme_command
   → 写 SQ 并更新 doorbell
   → controller 执行
   → 写 CQE
   → 驱动定位 request
   → 完成块请求

Controller 初始化：

::

   PCI device enable
   → 建立 Admin SQ/CQ
   → Identify controller
   → 读取能力与 queue limits
   → 创建 I/O SQ/CQ
   → 建立 blk-mq queue map
   → 扫描 namespace
   → controller 进入 live

Timeout 与 reset：

::

   request 超时
   → 检查 queue 与 controller state
   → 尝试 Abort
   → 停止或冻结 I/O queues
   → reset controller
   → 重建 Admin 与 I/O queues
   → 重扫 namespace
   → requeue 或失败旧 request

队列拓扑：

::

   应用提交 CPU
   → blk-mq hctx
   → NVMe queue pair
   → MSI-X vector 或 poll queue
   → completion CPU
   → bio completion
   → 唤醒业务任务

概念辨析
--------

Admin Queue 与 I/O Queue
   前者管理 controller 和 namespace；后者承载正常数据访问。

Hctx 与 NVMe Queue Pair
   Hctx 是块层派发上下文；驱动把它连接到协议 SQ/CQ。

Blk-mq Tag 与 NVMe CID
   Tag 标识块层 request；CID 标识协议命令。两者相关但不属于同一命名空间。

Queue Depth 与真实并行
   Depth 只限定允许在途规模，设备固件、介质和控制器资源决定实际并行能力。

Interrupt 与 Polling
   Interrupt 节省空闲 CPU；polling 用持续 CPU 占用换取更少中断与调度延迟。

Reset 与写入回滚
   Reset 重建命令通路，不能撤销可能已经执行的写入。

本章结论
--------

NVMe 把存储访问变成多队列命令协议；性能与可靠性取决于 blk-mq、SQ/CQ、身份映射、CPU/IRQ 局部性和 controller 状态机共同闭合。
