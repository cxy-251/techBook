第108章：Request Queue 与 I/O Scheduler
======================================

本章必须记住
------------

#. ``struct request_queue`` 是一个块设备对上承接 ``bio/request``、对下连接 blk-mq 与驱动的提交边界。
#. Request queue 集中保存设备限制、队列能力、调度器、merge 策略、tag set、硬件队列映射和 sysfs 属性。
#. 上层提交到同一块设备的 Page Cache writeback、Direct I/O、Swap 和 Device Mapper 请求会在该队列边界汇合。
#. ``bio`` 进入块层后可被合并或转换成 ``struct request``；I/O scheduler 主要对等待派发的 request 进行排序和节奏控制。
#. 调度器工作在驱动/设备接收请求之前，无法重新排序已经进入设备内部队列的命令。
#. 现代 Linux 块层以 blk-mq 为主；request queue、software context、hardware context 和 elevator 共同构成派发路径。
#. 无调度器且无需 merge 时，请求可能走较短的直接派发路径；存在 scheduler、plug 或资源不足时会进入软件等待阶段。
#. ``q->elevator`` 一类关系表示当前 request queue 是否挂接 I/O scheduler，精确字段与初始化流程具有版本差异。
#. ``/sys/block/<dev>/queue/scheduler`` 通常显示可选调度器，并用方括号标出当前项；实际可选项取决于配置、设备和内核版本。
#. ``none`` 表示不使用通用 elevator 排序，不表示块层、驱动和设备内部完全没有排队、merge 或调度。
#. ``mq-deadline`` 侧重限制请求饥饿和控制读写 deadline，同时保留一定 sector 顺序与批量能力。
#. BFQ 侧重按进程或 cgroup 分配预算和服务，常用于交互、公平性与带宽控制目标，支持与适用范围依配置。
#. Kyber 通过分域 token 和延迟反馈控制读写派发，是否可用和具体实现具有版本边界。
#. 调度器名称不是性能结论；同一调度器在 HDD、SATA SSD、NVMe、虚拟设备和 Device Mapper 上作用不同。
#. 旋转设备的机械寻道使 sector 顺序、merge 和请求重排通常更重要。
#. 高速 NVMe 已有多硬件队列和控制器内部并行，主机侧过度重排可能增加 CPU 和排队延迟。
#. 虚拟设备的 scheduler 可能作用在上层虚拟 queue；下层真实设备仍有自己的 scheduler、队列和硬件行为。
#. Device Mapper 栈中每一层的 request/bio 模型不同，不能只查看最上层设备的 ``scheduler`` 推断完整路径。
#. Request merge 的直接目标是把相邻、兼容的 I/O 组成更少、更大的驱动 request。
#. Front merge 把新 I/O 接到已有 request 前端，back merge 接到尾部；实现细节以目标内核为准。
#. Merge 要求目标队列、方向、sector 连续性和请求标志兼容，并满足 queue limits。
#. Flush、FUA、discard、integrity、crypto、zone、atomic write 等语义可以阻止普通 merge。
#. Request 已经 issue 到硬件队列后，主机 scheduler 通常不再有机会把它与后续请求合并。
#. Merge 减少 request、tag、驱动调用和设备命令数量，但会增大单个 request 的长度和占用时间。
#. 大请求可以提高顺序吞吐，也可能让小延迟敏感请求等待更久；merge 数量不是越多越好。
#. I/O scheduler 的主要目标通常包括吞吐、平均延迟、尾延迟、公平性、避免饥饿和设备利用率。
#. 这些目标彼此冲突：保持后台大写顺序性可能提高吞吐，却推高交互小读的尾延迟。
#. Deadline 不是实时完成保证，它只控制软件队列中的派发等待，不控制设备固件、错误恢复和完成调度。
#. Fairness 也不等于每个请求轮流派发；调度器可能按进程、cgroup、预算、时间或 I/O 类别分配服务。
#. 调度器看到的是块 request，不知道完整文件名和业务优先级，除非上层通过 cgroup、ioprio 或其它元数据传递策略。
#. ``ioprio_set``、I/O cgroup 与 scheduler 的作用取决于调度器是否支持相应语义，不能假设所有设备都执行同样的优先级。
#. blk-cgroup 可以统计和控制不同 cgroup 的块 I/O，但控制器、调度器、Device Mapper 与文件系统回写归属会影响结果。
#. Buffered writeback 由内核 worker 提交时，任务归属和 I/O 控制需要依赖 writeback/cgroup 关联机制，不能只看 worker 名称。
#. Plug 机制可暂时收集当前上下文产生的一组 request，以增加 merge 机会并批量提交。
#. ``blk_start_plug``/``blk_finish_plug`` 一类 helper 的稳定作用是建立短期批量窗口，精确触发和 flush 细节具有版本差异。
#. Plug 时间过长会推迟 request issue；正常实现会在调度、等待或显式 finish 时冲刷。
#. 队列的 ``nr_requests`` 等属性控制软件层可容纳的请求规模，不等于设备硬件 queue depth。
#. Queue depth、tag 数和 ``nr_requests`` 分别作用于不同资源层，必须结合 blk-mq 与驱动能力判断。
#. Queue limits 描述最大 sectors、segment 数、边界、discard、write zeroes、zone 和对齐能力。
#. 上层构造的 bio/request 超出 limits 时，块层必须 split；scheduler 不能绕过设备硬限制。
#. ``max_sectors_kb`` 限制单 request 大小不等于应用 syscall 大小；一个大 syscall 可以拆为多个 request。
#. ``nomerges`` 等属性可限制 merge 行为，具体取值与作用范围应查当前内核文档和 sysfs。
#. ``read_ahead_kb`` 属于块设备预读参数，但文件系统、Page Cache readahead 和应用访问模式共同决定实际读形状。
#. ``rotational`` 是设备向块层暴露的属性，虚拟或错误上报的设备可能需要人工验证其真实性。
#. Scheduler 切换会改变后续请求派发策略，不会重写已经完成或已进入设备内部的命令。
#. 在线切换 scheduler 可能造成瞬时队列重建或行为变化，应在受控环境并保留前后性能证据。
#. 不能只用吞吐选择 scheduler；生产系统还应比较 P50/P99、CPU、公平性、写回、设备利用率和错误恢复。
#. 对低队列深度同步读，软件 scheduler 可能显著影响延迟；对深队列 NVMe，设备内部排队可能掩盖主机策略。
#. 当设备内部已有大量命令时，即使 scheduler 立即优先派发一个小读，该读仍会在设备队列中等待。
#. 因此低延迟还要求限制在途深度、合理完成亲和性和设备服务时间，而不只是选择一个 scheduler。
#. ``iostat`` 的 await 等聚合指标通常包含软件队列和设备服务的组合时间，不能直接归因给 scheduler。
#. ``block_rq_insert`` 到 ``block_rq_issue`` 可近似观察 request 软件等待，但 merge、plug、requeue 和事件版本会影响解释。
#. ``block_rq_issue`` 到 ``block_rq_complete`` 更接近驱动与设备阶段，但下层虚拟设备、重试和 remap 仍可能包含其中。
#. 调试 scheduler 时应同时记录当前 scheduler、设备类型、队列深度、请求大小、读写比例和 cgroup/ioprio。
#. 大量 merge 失败时，应检查请求是否真正 sector 相邻、操作/flags 是否兼容、是否跨硬件 queue 或超过 limits。
#. 小读饥饿时，应检查软件队列等待、后台写深度、scheduler deadline、公平策略和设备内部 backlog。
#. 吞吐低时，应检查请求过小、队列深度不足、频繁 flush、merge 受限、CPU 派发瓶颈和设备能力。
#. Scheduler CPU 高时，应检查请求率、红黑树/预算管理、跨 CPU queue、锁竞争和是否需要该复杂策略。
#. ``none`` 性能好不表示 scheduler 无用，可能只是设备和 workload 更适合把排序交给控制器。
#. ``mq-deadline``、BFQ、Kyber 的默认参数和支持状态会随内核演进，必背内容应保留目标而非固定具体数值。
#. 最稳定源码阅读顺序是：``request_queue`` → queue limits → bio/request merge → elevator insert/dispatch → blk_mq_hw_ctx → driver ``queue_rq``。
#. 稳定模型是“scheduler 控制 request 何时以何种顺序到达驱动”；精确调度器算法和 sysfs 参数属于版本敏感实现。

必背路径
--------

Request queue 派发：

::

   上层提交 bio
   → 检查 queue limits
   → 尝试与已有 request merge
   → 分配/形成 struct request
   → 无 scheduler 且资源允许时直接派发
   → 否则进入软件队列/elevator
   → scheduler 选择下一 request
   → blk_mq_hw_ctx
   → 驱动 queue_rq

相邻请求合并：

::

   新 bio/request 到达
   → 查找 front/back merge 候选
   → 检查同设备、同操作和 sector 连续
   → 检查 flags、segment 与 queue limits
   → 更新已有 request 范围和 bio 链
   → 减少待派发 request 数
   → 后续由 scheduler 或 blk-mq 派发

小读与大写竞争：

::

   交互小读进入软件队列
   → 后台大写已形成批量 request
   → scheduler 比较 deadline/预算/类别
   → 选择是否打断写批量先派发读
   → request 进入硬件队列
   → 仍受设备 backlog 和服务时间影响
   → completion 返回应用

选择 scheduler：

::

   确认真实块设备和 Device Mapper 层
   → 查看 rotational、hardware queues 和当前 scheduler
   → 描述读写比例、请求大小、同步性与租户
   → 建立 none/mq-deadline/BFQ/Kyber 对照
   → 同时测吞吐、P99、CPU、公平性和队列深度
   → 选择满足业务目标的策略
   → 保留版本、参数和回退方案

诊断软件排队：

::

   记录 block_rq_insert
   → 记录 block_rq_issue
   → 计算近似软件等待
   → 对齐 scheduler、plug、merge、requeue 和 tag 状态
   → 检查后台来源与 cgroup/ioprio
   → 再与 issue-to-complete 服务时间比较

必须区分
--------

Request queue 与设备内部队列
   Request queue 是 Linux 块层提交边界；控制器和介质还会在设备内部继续排队。

Scheduler 与 Queue Limits
   Scheduler 调整顺序和节奏；limits 是不能违反的设备能力边界。

Merge 与调度
   Merge 改变 request 形状和数量；调度决定等待 request 的派发顺序。

``none`` 与没有排队
   None 关闭通用 elevator，blk-mq、驱动和设备内部仍然存在队列和资源控制。

Deadline 与完成期限
   Deadline 限制软件队列饥饿，不保证设备在确定时间内完成请求。

软件队列容量与硬件 queue depth
   ``nr_requests``、blk-mq tags 和设备命令槽属于不同层级的容量。

一句话结论
----------

Request queue 汇集块设备工作，I/O scheduler 在驱动接收前控制 request 的 merge、等待与派发顺序，并在吞吐、延迟和公平性之间取舍。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 22，Block Layer, Bio, Request Queues, Schedulers, and Multi-Queue；
* AIBook 章节：Chapter 108，Request Queues and IO Schedulers；
* 源文件：``docs/LinuxK/Part_22_Block_Layer_Bio_Request_Queues_Schedulers_and_Multi_Queue/Chapter_108_Request_Queues_and_IO_Schedulers.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_22_Block_Layer_Bio_Request_Queues_Schedulers_and_Multi_Queue/Chapter_108_Request_Queues_and_IO_Schedulers.md>`_。