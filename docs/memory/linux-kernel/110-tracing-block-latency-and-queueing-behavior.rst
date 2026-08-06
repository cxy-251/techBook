第110章：追踪块延迟与排队行为
===============================

本章必须记住
------------

#. 块层延迟分析的目标是把一次 I/O 拆成：上层到达、request 形成、软件队列等待、驱动派发、设备/下层服务、块层完成和任务恢复。
#. “存储慢”不能只看总耗时；同样的应用延迟可以来自 Page Cache miss、文件系统锁、块层排队、设备服务或完成后调度。
#. 本章的块延迟范围主要从请求进入块层到块层收到完成；应用和文件系统阶段必须用其它证据补齐。
#. 调试前先确认真实设备拓扑，包括分区、Device Mapper、RAID、虚拟磁盘和底层物理设备。
#. 对虚拟块设备只追一层会遗漏下层排队；对每层都简单相加又可能把同一次 I/O 重复计数。
#. ``/sys/block/<dev>/queue`` 是 ``request_queue`` 的可观察配置面，属性集合依设备、驱动和版本而异。
#. ``logical_block_size`` 表示设备对上报告的逻辑块大小，``physical_block_size`` 表示物理对齐提示，二者不必相等。
#. ``max_sectors_kb``、``max_segments``、segment boundary 等限制决定块层如何拆分 request。
#. ``scheduler`` 显示当前 elevator；``none`` 不表示驱动和设备内部没有队列。
#. ``rotational`` 帮助判断调度和顺序性假设，但虚拟设备上报值可能不等于真实介质特征。
#. ``nr_requests`` 是软件层请求规模参数，不等于 blk-mq driver tag depth 或设备命令槽数。
#. Discard、write zeroes、zoned、write cache 和 FUA 属性用于解释特殊 I/O 与持久化路径，具体文件名和单位需查当前 sysfs。
#. ``/sys/block/<dev>/stat`` 与 ``/proc/diskstats`` 来自块设备累计统计，适合观察请求数、扇区、耗时和在途量趋势。
#. 这些累计统计是设备级聚合，不能直接归因到某个文件、进程、cgroup 或 request。
#. 读取统计前后取差值才能得到观察窗口；单个累计值不能说明当前是否仍慢。
#. ``iostat`` 基于 diskstats 计算速率、await、队列和利用率等派生指标，字段解释会随版本和扩展模式变化。
#. ``await`` 通常近似请求从块层接纳到完成的平均时间，混合软件排队与设备/下层服务。
#. 平均 await 低不能排除少量极慢请求；必须同时观察延迟分布和 P99/P999。
#. ``%util`` 在传统单队列旋转设备上较直观，在现代多队列设备上不能简单解释为“100% 后绝无额外并行能力”。
#. ``aqu-sz`` 或平均队列长度反映窗口内在途/等待的聚合程度，不说明请求停在哪一层。
#. Device Mapper 上层与下层都可能在 diskstats 中计数；需要沿 major/minor 和拓扑解释。
#. PSI 的 ``io`` 压力表示任务因 I/O 资源停顿的时间比例，不能直接区分文件系统、块层或设备原因。
#. Block tracepoint 是把 ``bio/request`` 状态变化记录为时间戳事件的主要内核证据。
#. 可用事件必须从当前系统 ``/sys/kernel/tracing/available_events`` 和每个事件的 ``format`` 文件确认。
#. 常见事件包括 ``block_bio_queue``、``block_rq_insert``、``block_rq_issue``、``block_rq_complete``、merge、split、requeue 和 remap。
#. 事件名称、字段和触发位置会随内核版本变化，不能把某一版本示例当成永久 ABI。
#. ``block_bio_queue`` 表示 bio 进入块层观察点，不一定已经形成独立 request。
#. ``block_rq_insert`` 表示 request 被插入软件队列/调度阶段，具体路径可能因无 scheduler 或直接派发而缺失或不同。
#. ``block_rq_issue`` 表示 request 被提交到驱动派发路径，不等于介质在该时间点已经开始处理。
#. ``block_rq_complete`` 表示块层收到 request 完成，不等于上层 bio callback、用户 CQE 或业务线程已经完成处理。
#. ``insert → issue`` 可作为软件队列等待的近似区间，可能包含 scheduler、plug、tag 等待、requeue 和 dispatch backlog。
#. ``issue → complete`` 可作为驱动与设备/下层服务的近似区间，可能包含 Device Mapper、控制器队列、重试和 reset。
#. ``bio_queue → insert`` 可帮助观察 bio 到 request 的转换、merge 和早期等待，但并非所有路径都能形成简单一一关系。
#. 这些区间是工程近似，不是协议保证；merge、split、clone、remap 和部分完成会改变事件对应关系。
#. 多个 bio 可以合并成一个 request，一个 bio 可以拆成多个 request，一个虚拟 request 可以映射为多个下层 request。
#. 只按 sector 和长度配对事件会在并发、重用、重试和 Device Mapper 环境中产生错误关联。
#. 强关联可使用 request 指针、tag、BPF map 或专门工具，但必须处理对象复用和生命周期。
#. Block event 中的 ``comm`` 常表示事件执行时的当前任务，不总是最初发起业务 I/O 的进程。
#. Writeback、readahead、journal、reclaim 和异步 completion 会让事件显示内核 worker 或中断上下文。
#. 归因到应用需要结合 inode/file、cgroup、writeback owner、io_uring token 或上层 trace，而不能只读 ``comm``。
#. ``blktrace``/``blkparse`` 能采集和解析块层事件时间线，工具可用性与内核支持依发行版而异。
#. Blktrace 适合分析 queue、merge、issue、complete 和 remap，采集高负载设备时会产生明显数据量和开销。
#. Ftrace/trace-cmd 可以启用 block tracepoint，并与 sched、writeback、filemap 等事件放入同一时间轴。
#. Perf trace/record 可观察 CPU 栈、tracepoint 和调度事件，适合解释块层等待之外的 CPU 开销。
#. eBPF 可以按设备、cgroup、进程、request 或延迟阈值过滤，但程序必须验证结构和 tracepoint 版本。
#. ``bpftrace`` 一行脚本便于临时观察，生产长期工具更应使用 CO-RE、版本检测和丢事件统计。
#. 所有追踪工具都有扰动；事件率极高时，buffer overflow 和丢事件会让时间线不完整。
#. 采集必须记录 trace buffer 大小、丢失计数、CPU 范围、过滤条件和准确时间窗口。
#. 只追 complete 而不追 issue 无法区分旧请求和新请求；只追 issue 而不追 complete 无法判断服务时间和超时。
#. 追踪前应先限定设备 major/minor，防止系统其它磁盘噪声淹没目标。
#. 对分区 trace，应确认事件报告的是分区设备还是整盘 sector，remap 事件可以帮助解释转换。
#. 对 dm-crypt/LVM/RAID，应同时追上层虚拟设备和选定下层，利用 remap/clone 关系避免重复归因。
#. 对 NVMe，还应结合 ``/proc/interrupts``、IRQ affinity、queue 数、控制器错误和 reset 日志。
#. 对 SCSI/SATA，应结合 sense、timeout、error handler、link reset 和设备缓存状态。
#. Queueing delay 高而 service time 正常，常见方向包括：请求突发、队列深度过高、scheduler、tag shortage、plug、后台 writeback 和 cgroup 限流。
#. Service time 高而 queueing delay低，常见方向包括：介质慢、设备 GC、控制器 cache flush、链路错误、重试、reset 或下层网络存储。
#. 两者都高时，设备持续变慢会造成 backlog，后续请求又在软件队列中累积。
#. 两者都低但应用慢时，应向上检查 Page Cache、文件系统锁、CPU copy、io_uring CQ 消费和任务调度。
#. 大量 request insert 后长时间不 issue，应检查 scheduler、hctx dispatch、tag、driver busy 和 queue stopped 状态。
#. Issue 后无 complete，应检查设备超时、驱动日志、控制器状态、reset 和是否漏采完成事件。
#. Complete 已出现而业务仍等待，应检查 bio parent completion、fsync 元数据、CQE、wake-up 和应用锁。
#. 大量 merge 会让 request 数低于 bio 数；merge 少可能来自随机范围、flags 不兼容、queue boundary 或已直接派发。
#. 大量 split 会让下层 request 数高于上层请求，需检查 max sectors、segment、DMA、discard 和 zone 限制。
#. 大量 requeue 表示 request 暂时无法推进，可能由 driver resource、device queue full 或下层 target 造成。
#. Flush/FUA 请求数量和耗时会显著影响同步写尾延迟，应单独按操作类型统计。
#. Discard/trim 可在后台或显式运行，长 discard 会与普通 I/O 竞争；设备是否支持异步和拆分取决于能力。
#. Zoned device 的顺序写和 zone 操作有额外约束，普通随机块延迟模型不能完整覆盖。
#. 观察读写大小分布有助于判断应用小请求、文件系统拆分、merge 效果与设备最佳 I/O 大小是否匹配。
#. 观察 sector 分布有助于判断顺序性、热点和跨设备映射，但 SSD 内部物理布局仍不可由逻辑 sector 推断。
#. I/O scheduler 对 insert→issue 阶段有直接影响，设备 firmware 对 issue→complete 更直接，但两层会通过 backlog 相互作用。
#. Cgroup I/O 限流可以主动延后 request，相关延迟可能发生在块层不同位置，需结合 blk-cgroup trace 和配置。
#. 应用层队列时间不在 block trace 中；io_uring SQ backlog、线程池队列和数据库内部调度必须单独记录。
#. 文件系统提交前时间也不在 request issue 区间中；extent 分配、journal、COW、reclaim 和 dirty throttle 需用对应 tracepoint。
#. 完整端到端读取时间线应连接：应用提交 → VFS/Page Cache → bio → request insert/issue/complete → bio complete → wakeup → 应用运行。
#. 完整同步写时间线还应加入 dirty、writeback、journal commit、flush/FUA 和 fsync 返回。
#. 诊断时先用低成本聚合指标确认问题窗口，再用短时精确 trace 捕获代表样本，避免长期无筛选全量采集。
#. 建立基线时必须固定设备、文件系统、scheduler、queue depth、请求大小、读写比例和后台负载。
#. 优化后要重复同一观测链，确认等待从哪一阶段减少，而不是只看到总吞吐变化。
#. 最稳定分析顺序是：设备拓扑/queue 属性 → diskstats/iostat → block 生命周期 trace → 驱动日志 → 上下层时间线对齐。
#. 稳定模型是“insert→issue 近似软件排队，issue→complete 近似驱动与设备服务”；精确边界依内核、设备栈和事件版本而异。

必背路径
--------

块层最小时间线：

::

   上层提交 bio
   → block_bio_queue
   → bio merge/split 与 request 分配
   → block_rq_insert
   → scheduler / plug / tag / dispatch 等待
   → block_rq_issue
   → 驱动、下层设备与介质服务
   → block_rq_complete
   → bio completion

定位高延迟：

::

   确认真实设备拓扑
   → 读取 queue 属性和 scheduler
   → 取 diskstats/iostat 时间窗口
   → 判断 backlog、吞吐和平均 await
   → 启用目标设备 block tracepoint
   → 分解 insert-to-issue 与 issue-to-complete
   → 检查 merge/split/requeue/remap
   → 向上或向下继续追踪

Queueing delay 高：

::

   request 已 insert
   → issue 明显延后
   → 检查 scheduler 和 plug
   → 检查 tag/hctx dispatch
   → 检查 cgroup throttle
   → 检查后台 writeback 与请求突发
   → 降低或重塑在途深度
   → 复测 P99

Service time 高：

::

   request 已 issue
   → complete 明显延后
   → 检查下层 remap
   → 检查控制器和设备日志
   → 检查 timeout/retry/reset
   → 检查 flush、discard 与设备 GC
   → 检查 IRQ/completion 分布
   → 验证硬件或远端服务

端到端对齐：

::

   应用记录 request/token 和提交时间
   → VFS/filemap/iomap trace
   → bio/request block trace
   → driver/device completion
   → sched_wakeup
   → sched_switch 到业务线程
   → CQE/syscall 返回
   → 分别计算各阶段延迟

必须区分
--------

* 软件排队与设备服务：Insert 到 issue 近似软件等待；issue 到 complete 近似驱动、下层和设备服务。
* 设备统计与单请求 trace：Diskstats/iostat 是设备级聚合；tracepoint 才能观察具体请求时间线。
* ``comm`` 与原始 I/O 所有者：事件当前任务可能是 writeback worker、中断或 kworker，不一定是业务进程。
* 上层虚拟设备与下层物理设备：Device Mapper 会 remap/clone 请求，两个层级的统计不能简单相加。
* 块完成与应用完成：Block complete 后还可能等待 bio 聚合、文件系统、CQE、唤醒和业务调度。
* 平均延迟与尾延迟：Await 等平均值会隐藏少数极慢请求，必须保留延迟分布和错误时间线。

一句话结论
----------

块延迟必须沿 bio/request 生命周期拆成软件排队和驱动—设备服务，再与文件系统、完成回调和任务调度证据对齐，才能判断真正等待发生在哪一层。
