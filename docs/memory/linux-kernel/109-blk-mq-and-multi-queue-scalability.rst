第109章：blk-mq 与多队列扩展性
===============================

本章必须记住
------------

#. blk-mq 是现代 Linux 块层的多队列排队机制，用于把多 CPU 提交与设备并行硬件队列连接起来。
#. 它解决的核心问题是传统单共享队列在高速 SSD、NVMe 和多核系统上的锁竞争与 cacheline bouncing。
#. 设备越快，软件排队、共享锁、tag 分配和 completion 回流在总延迟中的占比越容易上升。
#. ``struct blk_mq_ctx`` 表示贴近 CPU 的软件提交上下文，通常承接本 CPU 发起的 request 和调度器输入。
#. ``struct blk_mq_hw_ctx`` 表示贴近驱动的硬件队列上下文，保存 dispatch、CPU mask、tag、NUMA 和驱动私有状态。
#. ``struct blk_mq_tag_set`` 描述驱动向块层提供的硬件队列数量、queue depth、保留 tag、NUMA 和操作回调。
#. ``struct blk_mq_ops`` 把通用块层连接到驱动的 request 初始化、映射、``queue_rq``、timeout 和 polling 等动作。
#. 稳定主线是：提交 CPU → ``blk_mq_ctx`` → 映射到 ``blk_mq_hw_ctx`` → 分配 tag → 驱动 ``queue_rq`` → completion。
#. Software queue 的目标是降低提交路径跨 CPU 争用，并为 merge 与 scheduler 提供软件暂存位置。
#. Hardware context 是 Linux 块层中的驱动派发上下文，不等于设备控制器中真实硬件队列对象本身。
#. 一个 ``blk_mq_hw_ctx`` 可以映射到一个设备硬件提交队列，也可能因驱动设计映射到其它组合，不能只按名称推断。
#. 无 scheduler、无需 merge 且资源充足时，请求可以较快进入 hardware context 和驱动。
#. 存在 scheduler、plug、tag 不足或驱动资源不足时，request 会停留在软件队列或 hardware context 的 dispatch 列表。
#. ``dispatch`` 列表保存块层已经准备但暂时未能交给驱动的 request，不是设备内部命令队列。
#. 驱动 ``queue_rq`` 成功接收 request 后，块层认为请求已进入驱动/设备执行阶段。
#. 驱动暂时缺少资源时可以返回资源状态，让块层停止或延后该 hardware queue 并在稍后重试。
#. 暂时资源不足不等于 I/O 永久失败，也不应立即向文件系统报告硬错误。
#. Driver busy、tag shortage、device queue full 和 scheduler wait 属于不同等待原因，需要分别观测。
#. CPU 到 hardware queue 的映射由 ``struct blk_mq_queue_map`` 一类对象表达，稳定含义是 CPU ID 映射到 hctx 索引。
#. 多个 CPU 可以共享一个 ``blk_mq_hw_ctx``；硬件队列少于 CPU 数时这是正常映射。
#. 设备硬件队列多于有效 CPU 或 workload 并行度时，更多队列也不会自动产生更多吞吐。
#. ``nr_hw_queues`` 是驱动声明的块层硬件队列数量，不能直接等同于 NVMe 控制器所有可创建队列上限。
#. ``queue_depth`` 表示每个队列可用 tag/在途 request 规模的重要能力，实际可用量还受 reserved tags 和其它限制影响。
#. Tag 是 blk-mq 标识在途 request 和驱动命令槽关系的资源；没有 tag 时 request 不能正常派发。
#. Tag exhaustion 会表现为软件排队、requeue 或提交延迟，不一定表示设备介质本身变慢。
#. Reserved tags 用于关键或恢复路径，普通 I/O 不能无条件占用。
#. Scheduler 可以使用独立 ``sched_tags`` 管理软件调度 request；driver tags 与 scheduler tags 属于不同阶段。
#. Request tag 不等于设备协议 command ID；NVMe CID、SCSI tag 等由驱动和协议继续解释。
#. Tag 回收必须发生在 request 不再被驱动和完成路径访问之后，过早复用会把迟到 completion 关联到错误请求。
#. Completion 的稳定主线是：设备/驱动报告完成 → 找到 request/tag → 更新状态与完成字节 → ``blk_mq_end_request`` → 完成 bio → 归还 tag。
#. Request 可以乱序完成；提交顺序、issue 顺序和 completion 顺序不保证一致。
#. 完成 CPU 不保证等于提交 CPU；中断亲和性、polling、softirq 和驱动设计决定 completion 在哪里执行。
#. Completion 在错误 CPU 上集中会产生远程 cacheline、NUMA 和调度开销，即使设备本身仍有余量。
#. IRQ affinity、hardware queue CPU mask 和应用 CPU affinity 应联合检查，避免提交、设备队列和完成跨 NUMA 反复迁移。
#. NUMA 系统上，设备 PCIe root、内存 buffer、提交 CPU、hctx 和中断 CPU 的位置共同影响延迟。
#. “本地 CPU 提交”不自动表示 buffer 内存、设备和 completion 也都位于本地 NUMA node。
#. ``blk_mq_tag_set.numa_node`` 一类信息是分配与映射提示，不能替代真实拓扑和运行时证据。
#. blk-mq 可以定义 DEFAULT、READ、POLL 等不同 queue map 类型，支持范围由驱动和内核版本决定。
#. Read queue map 可让读请求使用不同硬件队列集合；poll map 用于轮询完成路径，不能推广到所有设备。
#. Polling 通过主动检查完成减少中断和调度开销，代价是占用 CPU，并要求底层设备与请求路径支持。
#. Polling request 与普通中断完成 request 的 hctx、CPU 和完成路径可能不同。
#. NVMe 协议天然具有多 submission/completion queues，但 Linux blk-mq 仍需完成 CPU 映射、tag、request 和驱动回调管理。
#. SATA/SCSI、virtio-blk、loop、nbd 和 Device Mapper 也可以使用 blk-mq，但其下层并行能力和瓶颈完全不同。
#. Device Mapper 上层 queue 可以映射到多个下层 queue；上层 hctx 数量不能直接代表最终物理设备并行度。
#. 多路径设备还可能按路径选择和故障切换重映射请求，观察时需区分虚拟 queue 与底层 queue。
#. Software queue 数量增多减少某些共享状态，不表示完全无锁；scheduler、hctx、tag 和统计仍可能成为共享热点。
#. 多个提交 CPU 映射到同一 hctx 时，hctx dispatch、tag 和驱动队列仍会产生竞争。
#. 当 hardware queue 数过少，多个 CPU 汇聚会增加锁和 cacheline 压力；过多则会增加内存、管理和设备上下文成本。
#. 队列映射的目标是匹配设备能力和 CPU 拓扑，不是让 hardware queue 数机械等于 CPU 数。
#. 应用队列深度、blk-mq tag 深度、驱动 queue depth 和设备内部 command depth 是不同层级。
#. 应用在途请求过少时，tag 可能大量空闲且设备利用不足；过多时会在应用、软件队列或设备内部累积等待。
#. blk-mq 只能组织块层请求，不能消除上层 Page Cache、文件系统事务、COW、reclaim 和 writeback 延迟。
#. 请求到达 ``blk_mq_submit_bio`` 一类入口之前已经慢，瓶颈通常在更上层；不能用 hctx 调优解决文件系统锁。
#. Request 已 issue 后很慢，更应检查驱动、设备、下层映射、超时和错误恢复。
#. Requeue 次数高可能表示驱动资源不足、设备 queue full、zone/ordering 限制或下层 target 阻塞。
#. Requeue 会增加软件停留和尾延迟，也可能改变后续 issue 顺序。
#. Timeout 处理可能调用驱动 timeout 回调，执行 abort、reset、requeue 或失败；具体恢复语义由协议和驱动决定。
#. 控制器 reset 会影响多个 hardware queues 和大量在途 request，不能只按单请求慢解释。
#. ``/sys/block/<dev>/mq/`` 在部分系统中暴露 hardware context、CPU 映射和队列信息，具体目录结构依版本而异。
#. ``/sys/block/<dev>/queue/nr_requests`` 不是 blk-mq 所有 tag 的完整视图，也不是设备协议 queue depth。
#. ``/proc/interrupts`` 可观察存储中断分布，需结合 MSI-X vector、driver queue 和 CPU affinity 解释。
#. ``lspci -vv``、sysfs NUMA node 和 IRQ affinity 可帮助建立设备拓扑，但虚拟机环境中的信息可能由 hypervisor 抽象。
#. Block tracepoint 可观察 insert、issue、requeue、complete 等阶段，精确事件集合以当前 tracefs 为准。
#. ``block_rq_issue`` 说明 request 已进入驱动派发观察点，不一定等同于设备已经开始介质访问。
#. ``block_rq_complete`` 说明块层收到完成，不自动表示应用线程已经运行并消费结果。
#. Perf 可定位 blk-mq 提交、tag、scheduler、completion 和驱动 CPU 热点；单独 CPU profile 不能测设备等待时间。
#. eBPF/ftrace 可按 request 指针或 tag 关联生命周期，必须处理 request 复用、merge、split 和 remap。
#. 调试吞吐不足时，应检查 CPU 是否集中提交、hctx 映射、tag 利用、request size、requeue 和设备利用率。
#. 调试尾延迟时，应检查 software wait、tag wait、driver busy、device service、IRQ/complete CPU 和调度返回。
#. 调试单核 CPU 高时，应确认多个 hctx 或 completion 是否集中到一个 CPU，以及 scheduler/softirq 是否成为热点。
#. 调试跨 NUMA 延迟时，应同时记录应用 CPU、buffer node、hctx CPU mask、IRQ CPU 和设备 NUMA node。
#. 优化 IRQ affinity 不能脱离应用 affinity；把 completion 移到另一个 CPU 可能降低中断热点，却增加远程唤醒和数据访问。
#. 优化 queue count 也不能脱离设备 firmware 和虚拟化限制；驱动创建更多 queue 可能不会得到真实并行收益。
#. 最稳定源码阅读顺序是：``blk_mq_tag_set`` → queue map → ``blk_mq_ctx`` → ``blk_mq_hw_ctx`` → tag → ``queue_rq`` → completion。
#. 稳定模型是“blk-mq 把多 CPU 的软件提交映射到有限硬件派发队列”；精确字段和 fast path 属于版本敏感实现。

必背路径
--------

blk-mq 提交：

::

   CPU 上层提交 bio
   → 形成/取得 struct request
   → 当前 CPU 对应 blk_mq_ctx
   → scheduler/merge 或直接路径
   → queue map 选择 blk_mq_hw_ctx
   → 分配 driver tag
   → 驱动 queue_rq
   → 设备 submission queue

驱动暂时忙：

::

   queue_rq 尝试提交
   → 驱动/设备资源不足
   → 返回 resource 状态
   → request 留在 dispatch/requeue 路径
   → 停止或延后运行 hctx
   → 资源恢复后重新 run queue
   → 再次调用 queue_rq

Completion：

::

   设备完成命令
   → 中断或 polling 找到 command/tag
   → 驱动映射回 struct request
   → 更新 blk_status 与完成范围
   → blk_mq_end_request
   → 完成 request 中 bio
   → 调用上层 bi_end_io
   → 归还 tag 和 request

检查队列映射：

::

   确认设备和 driver nr_hw_queues
   → 读取 CPU 到 hctx map
   → 查看每个 hctx cpumask 与 NUMA
   → 对齐应用提交 CPU
   → 对齐 IRQ/completion CPU
   → 检查 tag depth 与利用率
   → 判断是否存在集中或跨 NUMA

诊断 blk-mq 尾延迟：

::

   上层提交时间
   → request insert
   → tag 获得时间
   → queue_rq / issue
   → requeue 或 driver busy
   → device complete
   → bio complete
   → 任务 wakeup-to-run
   → 按阶段定位等待来源

必须区分
--------

``blk_mq_ctx`` 与 ``blk_mq_hw_ctx``
   前者贴近提交 CPU 的软件上下文；后者贴近驱动的硬件派发上下文。

Hardware context 与设备硬件队列
   Hctx 是 Linux 块层对象；驱动再把它映射到控制器真实队列。

Scheduler tag 与 Driver tag
   前者服务软件调度阶段；后者标识可交给驱动的在途 request。

Tag depth 与应用队列深度
   Tag 是块层/驱动资源；应用还可以在更上层积压尚未进入块层的请求。

提交 CPU 与完成 CPU
   Request 可在一个 CPU 提交，在另一个中断或 polling CPU 完成。

更多队列与更高性能
   多队列降低共享争用，收益仍取决于设备能力、映射、NUMA、请求形状和完成路径。

一句话结论
----------

blk-mq 通过 CPU 本地软件上下文、硬件派发上下文和 tag，把多核提交映射到设备并行队列；性能取决于映射、资源深度与完成回流是否匹配真实拓扑。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 22，Block Layer, Bio, Request Queues, Schedulers, and Multi-Queue；
* AIBook 章节：Chapter 109，blk-mq and Multi-Queue Scalability；
* 源文件：``docs/LinuxK/Part_22_Block_Layer_Bio_Request_Queues_Schedulers_and_Multi_Queue/Chapter_109_blk-mq_and_Multi-Queue_Scalability.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_22_Block_Layer_Bio_Request_Queues_Schedulers_and_Multi_Queue/Chapter_109_blk-mq_and_Multi-Queue_Scalability.md>`_。