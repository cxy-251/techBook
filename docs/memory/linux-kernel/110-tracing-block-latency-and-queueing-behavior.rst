第110章：追踪块延迟与排队行为
===============================

核心知识点
----------

块延迟必须拆成阶段
   一次 I/O 至少包含上层提交、bio/request 形成、软件排队、驱动派发、设备或下层服务、块层完成、上层回调与任务重新运行。

先确认真实设备拓扑
   分区、Device Mapper、RAID、虚拟磁盘和物理设备可能形成多层队列。只追最上层会遗漏下层等待，简单累加各层又可能重复计算同一次 I/O。

``/sys/block/<dev>/queue`` 描述队列能力
   Logical/physical block size、最大 sectors、segment、scheduler、rotational、discard、write cache 与 FUA 等属性用于解释请求形状和持久化能力。

Diskstats 提供设备级聚合
   ``/proc/diskstats``、``/sys/block/<dev>/stat`` 和 ``iostat`` 适合确认时间窗口中的吞吐、在途量和平均等待，但不能直接归因到某个文件、进程或 request。

Block tracepoint 描述 request 生命周期
   常见事件覆盖 bio queue、request insert、issue、complete、merge、split、requeue 与 remap。事件和字段必须以当前 tracefs 的 ``format`` 为准。

``insert → issue`` 近似软件排队
   该区间可能包含 scheduler、plug、tag 等待、hctx dispatch 和 requeue。它适合定位主机软件层 backlog，但不是严格协议边界。

``issue → complete`` 近似服务阶段
   该区间包含驱动、Device Mapper 下层、控制器、介质、重试与 reset。Issue 只表示交给驱动观察点，不保证介质此刻开始访问。

Bio 与 request 不是一一对应
   Merge、split、clone、remap 和部分完成会改变数量与范围。只按 sector 和长度配对事件，在高并发与虚拟设备环境中容易误关联。

事件中的 ``comm`` 不等于业务发起者
   Writeback、readahead、journal、io_uring、softirq 和中断完成会让当前任务显示为内核 worker 或完成上下文。归因需要结合 cgroup、inode、token 或上层 trace。

高 queueing 与高 service 指向不同问题
   Queueing 高而 service 正常，优先检查突发深度、scheduler、tag、cgroup 和 writeback；service 高则检查设备 GC、flush、错误重试、reset 与远端存储。

块完成后仍可能存在尾延迟
   ``block_rq_complete`` 不代表 bio 父链、fsync、CQE、任务唤醒和业务锁已经结束。应用慢而块阶段正常时，应继续向上追踪。

关键路径
--------

块层最小时间线
~~~~~~~~~~~~~~~~

::

   上层提交 bio
   → block_bio_queue
   → merge / split / request 分配
   → block_rq_insert
   → scheduler / plug / tag / dispatch 等待
   → block_rq_issue
   → 驱动、下层与设备服务
   → block_rq_complete
   → bio completion

Queueing delay 诊断
~~~~~~~~~~~~~~~~~~~

::

   request 已 insert
   → issue 明显延后
   → 检查 scheduler 与 plug
   → 检查 tag 和 hctx dispatch
   → 检查 cgroup throttle
   → 检查请求突发与后台 writeback
   → 调整在途深度并复测尾延迟

Service time 诊断
~~~~~~~~~~~~~~~~~

::

   request 已 issue
   → complete 明显延后
   → 检查 remap 与下层设备
   → 检查 timeout / retry / reset
   → 检查 flush、discard 与设备 GC
   → 检查 IRQ 和 completion 分布
   → 验证硬件或远端服务状态

概念辨析
--------

``await`` 与设备服务时间
   ``iostat`` 的 await 通常混合软件等待和服务阶段；只有 request 生命周期 trace 才能进一步拆分。

``block_rq_issue`` 与设备开始执行
   Issue 表示请求进入驱动派发观察点；控制器内部仍可能继续排队。

``block_rq_complete`` 与应用完成
   Complete 表示块层收到 request 结果；上层回调、任务调度和业务处理可能继续等待。

Queueing delay 与 Service time
   前者主要发生在 request 交给驱动之前；后者主要发生在 issue 之后。设备持续变慢还会反向造成软件 backlog。

聚合指标与单请求证据
   Diskstats/iostat 用于发现问题窗口；tracepoint、blktrace、ftrace 或 eBPF 用于还原代表性请求时间线。

本章结论
--------

块 I/O 诊断的核心是把 ``insert→issue`` 与 ``issue→complete`` 分开，并在真实设备拓扑中继续连接上层文件系统和下层驱动证据。