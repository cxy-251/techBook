第105章：I/O 路径选择与性能权衡
================================

本章必须记住
------------

#. I/O 路径选择不是在 ``read``、``O_DIRECT``、AIO、``io_uring`` 中挑一个“最快 API”，而是组合多个正交维度。
#. 第一维是缓存策略：Buffered I/O 使用 Page Cache，Direct I/O 请求尽量绕过 Page Cache。
#. 第二维是提交模型：同步调用、线程池、legacy AIO、readiness loop 或 ``io_uring`` 决定如何管理未完成工作。
#. 第三维是完成语义：普通 I/O 完成、writeback 完成、``fsync`` 完成和设备稳定持久化必须分开。
#. 第四维是请求形状：顺序或随机、读或写、请求大小、对齐、稀疏范围、文件数量和并发模式。
#. 第五维是资源模型：Page Cache、用户 buffer、页固定、CPU copy、NUMA、本地队列和设备队列。
#. 第六维是目标：平均延迟、P99/P999、吞吐、CPU 效率、内存占用、持久化或实现复杂度。
#. 任何选型都应先描述 workload，而不是先选择接口再寻找理由。
#. 同一个程序的不同阶段可以适合不同路径，例如首次顺序扫描、热点随机查询和后台批量写入。
#. Buffered I/O 适合数据会复用、希望利用内核预读、接受 Page Cache 管理并需要简单一致性的场景。
#. Direct I/O 适合应用已有缓存、数据很少复用、工作集远大于内存、请求可稳定对齐且需要控制缓存污染的场景。
#. Legacy AIO 更适合其支持良好的文件异步路径，不能把它视为所有 fd 和所有 buffered 操作的统一异步接口。
#. ``io_uring`` 适合大量 outstanding work、批量提交、统一 completion、取消、timeout 或固定资源复用的场景。
#. ``io_uring`` 与 Direct I/O 不是互斥选项：前者是提交/完成协议，后者是缓存策略。
#. ``io_uring`` buffered read 仍可命中 Page Cache；``io_uring`` direct read 仍有对齐、pinning 和设备约束。
#. 线程池是通用的异步封装，适合不能原生异步的阻塞操作，代价是线程、调度和用户队列。
#. Readiness loop 适合 socket、pipe 等可非阻塞推进对象，普通磁盘文件通常始终看似 ready，不能由 readiness 直接表达设备完成。
#. 同步 I/O 不等于低性能；当请求足够大、并发由多线程自然提供且实现简单时，它可能是最合理基线。
#. 异步 I/O 不自动降低单个请求的设备服务时间，它主要把多个等待阶段重叠并减少提交固定成本。
#. 吞吐通常由请求大小、队列深度、设备并行度、CPU 和锁竞争共同决定。
#. 单次延迟由用户排队、提交、缓存、文件系统、块层排队、设备服务、完成和调度返回共同组成。
#. 平均延迟低不能代表尾延迟低；回写、回收、compaction、元数据事务和设备 GC 常在尾部暴露。
#. 队列深度过低会让高速设备空闲，过高会增加排队时间、buffer 占用和 P99/P999 延迟。
#. Little's Law 可以帮助理解在途数约等于吞吐乘平均停留时间，但不能替代尾延迟和突发分析。
#. 设备支持大量并行队列不表示单个应用应无条件填满所有队列。
#. 多租户场景中，应用过深队列会挤压其它 cgroup、进程或文件系统事务，破坏公平性。
#. 顺序大 I/O 通常降低每字节 syscall、mapping、bio 和设备命令开销。
#. 请求过大也会延长单次占用、增加取消成本、降低调度灵活性，并放大错误重试范围。
#. 随机小 I/O 需要重点测量固定提交成本、缓存命中、设备 IOPS、队列等待和 CPU 消耗。
#. 热点随机读若能命中 Page Cache，Buffered I/O 往往比 Direct I/O 的真实设备访问更低延迟。
#. 一次性大扫描可能污染 Page Cache，但应先评估预读、访问提示、cgroup/内存压力，再决定是否采用 Direct I/O。
#. Buffered read 的复制成本是 Page Cache 到用户 buffer；如果数据复用，复制成本可能换来大量设备 I/O 避免。
#. Direct I/O 可减少一次 Page Cache copy，却可能增加页固定、对齐处理、请求拆分和应用缓存管理成本。
#. Registered buffers 可减少重复 pin/校验，长期 pinning 仍会约束回收、迁移和 NUMA。
#. Zero-copy 是具体数据路径性质，不能从 ``io_uring``、注册 buffer 或 Direct I/O 名称直接推出。
#. Page Cache 污染要用热点淘汰、refault、真实复用和内存压力证明，不能只因缓存占用高就下结论。
#. Pinning 压力要观察在途 buffer 数、pin 时长、内存回收、迁移失败和 cgroup 约束。
#. Buffered write 可以快速返回并延后支付设备成本，性能评价必须同时看 write 延迟、dirty 积累、throttling 和 fsync 延迟。
#. Direct write 更直接暴露设备和文件系统延迟，但仍可能有块分配、COW、日志、队列和 device cache。
#. 应用若关心崩溃恢复，应单独设计 write、依赖顺序、fsync 和日志协议，不能以“Direct”或“异步完成”替代。
#. 批量提交减少 syscall 和同步成本；批量过大则增加首个请求等待时间和突发 CQ 消费压力。
#. 固定 file/buffer 可以优化高频控制路径，但只在资源集合稳定且注册成本可摊销时有意义。
#. 高频更新注册表或频繁注册/注销可能比普通 fd lookup 和临时 buffer 更贵。
#. SQPOLL/IOPOLL 用 CPU 换取更少 syscall、interrupt 或调度延迟，应同时测 CPU 占用、功耗和同核影响。
#. Polling 适合极低延迟、CPU 可专用的受控环境，不应作为普通服务默认配置。
#. 性能测试必须区分冷缓存、热缓存和受控清缓存；三者回答不同问题。
#. 冷缓存测试主要测后端读入与预读；热缓存测试主要测 Page Cache lookup、copy 和 CPU。
#. 粗暴全局 drop caches 会干扰整机其它 workload，生产诊断应优先使用可控数据集和时间窗口。
#. Benchmark 必须固定文件系统、mount options、文件布局、设备、CPU/NUMA、队列调度器和后台负载。
#. 只报告 MB/s 而不报告请求大小、并发、队列深度和延迟分布，结果不可解释。
#. 只报告 syscall 耗时会遗漏异步排队、设备完成和 CQ 消费时间。
#. 只报告设备延迟会遗漏 Page Cache、文件系统锁、reclaim、writeback 和应用用户队列。
#. ``strace`` 用于确认应用实际使用了哪些 syscall、flags、fd、offset、长度和返回错误。
#. ``strace`` 对高频 I/O 有显著扰动，适合短时、过滤后的路径确认，不适合无条件全量性能测量。
#. ``perf`` 用于定位 CPU 时间、copy、Page Cache、文件系统、锁、worker 和 completion 处理热点。
#. CPU profile 只能说明 CPU 在哪里花时间，不能单独证明请求在块层等待多久。
#. ftrace/tracefs/eBPF 可连接 VFS、filemap、writeback、iomap、``io_uring``、block 和调度事件，事件名具有版本差异。
#. Block trace 用于观察 bio/request 插入、合并、dispatch、完成，从而拆分内核队列与设备服务阶段。
#. ``iostat``、PSI、vmstat、``/proc/meminfo`` 和 cgroup 指标用于补充设备利用率、I/O 压力、回收和 writeback 背景。
#. ``iostat`` 的聚合指标不能直接归因到某个文件、进程或请求，需要与 trace 的时间窗口对齐。
#. ``/proc/<pid>/io`` 展示进程级累计 I/O 视图，字段与 Page Cache/实际存储字节不是一一相等。
#. 观察 Buffered read 要同时看用户读取、Page Cache hit/miss、readahead 和块层读请求。
#. 观察 Buffered write 要同时看应用写入、dirty、writeback、throttling、fsync 和设备写完成。
#. 观察 Direct I/O 要确认 ``O_DIRECT``/request flag、对齐、iomap/direct path、页固定和块层请求。
#. 观察 ``io_uring`` 要同时看 SQ 发布、内核消费、在途数、io-wq、CQE、CQ backlog 和业务消费。
#. 请求没有到块层不一定是故障：Buffered read 可能命中 Page Cache，tmpfs/网络文件系统也可能不走本地块设备。
#. 请求到块层慢不一定是设备慢：可能在文件系统锁、空间分配、journal、reclaim 或 writeback 前等待。
#. Block dispatch 到 completion 慢更接近设备/下层服务时间，但 device mapper、网络块设备和控制器重试仍可能介入。
#. CQE 到达后业务仍慢，问题可能在用户线程调度、完成队列消费、锁或应用状态机。
#. I/O 优化必须逐层验证：改请求大小后看 syscall/块请求，改队列深度后看吞吐/尾延迟，改缓存策略后看复用/回收。
#. 一次只改变一个关键维度，避免同时切换 Direct I/O、``io_uring``、文件系统选项和队列深度导致无法归因。
#. 生产选择应包含故障处理、取消、重试、兼容性和维护成本，不能只看微基准峰值。
#. 较新的 ``io_uring`` opcode 或文件系统 Direct 能力必须提供 feature probe 和降级路径。
#. 最稳定选型顺序是：访问模式 → 缓存收益 → 请求形状 → 持久化要求 → 并发/队列 → 内存成本 → 观测验证。

必背路径
--------

选择缓存策略：

::

   描述工作集大小与重复访问
   → 热点会复用、需要预读或共享 mmap
   → 优先 Buffered I/O
   → 数据基本只读/写一次且应用已有缓存
   → 评估 Direct I/O
   → 检查对齐、pinning、文件系统和设备
   → 用 Page Cache、CPU 和块层证据比较

选择提交模型：

::

   先建立同步 I/O 基线
   → 判断线程等待是否限制吞吐
   → 确定需要的 outstanding depth
   → 少量阻塞工作可用线程池
   → 受支持 Direct 文件 I/O 可评估 legacy AIO
   → 需要批量、统一 completion、取消或多类操作
   → 评估 io_uring
   → 设计有界背压和 teardown

拆分一次 I/O 延迟：

::

   应用任务进入用户队列
   → syscall / SQ 提交
   → Page Cache 或文件系统准备
   → bio/request 进入块层
   → block queue 等待
   → 设备服务
   → completion / CQE
   → 线程被调度并消费结果
   → 业务状态机完成

观测实际路径：

::

   strace 确认 API、flags、offset 和长度
   → perf 确认 CPU 热点
   → ftrace/eBPF 追 VFS、filemap、iomap、io_uring
   → block trace 追 request dispatch/completion
   → iostat/PSI/vmstat 补充系统背景
   → 按同一 request/token 和时间窗口对齐
   → 定位缓存、文件系统、队列、设备或应用层

安全性能实验：

::

   固定设备、文件系统、mount、CPU 和数据集
   → 分别测冷缓存与热缓存
   → 固定请求大小和读写比例
   → 逐级增加并发/队列深度
   → 同时记录吞吐、平均和尾延迟、CPU、内存
   → 每次只改变一个路径维度
   → 重复验证并保留错误率与降级结果

必须区分
--------

缓存策略与提交接口
   Buffered/Direct 决定 Page Cache；同步/AIO/``io_uring`` 决定请求和完成管理。

吞吐与单次延迟
   更多在途请求可提高设备利用率，也会增加排队和尾延迟。

复制减少与总成本减少
   少一次 copy 可能换来 pinning、对齐、缓存自管和更多设备 I/O。

Page Cache 占用与缓存污染
   占用是缓存工作状态；污染需要证明无复用数据挤出热点并造成额外成本。

I/O 完成与持久化完成
   请求完成表示接口操作结束；崩溃恢复保证还取决于 fsync、文件系统和设备顺序。

工具现象与根因
   Syscall、CPU、块层和设备工具观察不同阶段，必须按同一时间线交叉验证。

一句话结论
----------

I/O 性能优化本质上是让缓存策略、请求形状、完成模型、队列深度、内存成本和设备能力匹配，并用分层证据证明真实请求走了预期路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 21，Page Cache IO, Direct IO, Async IO, and io_uring；
* AIBook 章节：Chapter 105，IO Path Selection and Performance Tradeoffs；
* 源文件：``docs/LinuxK/Part_21_Page_Cache_IO_Direct_IO_Async_IO_and_io_uring/Chapter_105_IO_Path_Selection_and_Performance_Tradeoffs.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_21_Page_Cache_IO_Direct_IO_Async_IO_and_io_uring/Chapter_105_IO_Path_Selection_and_Performance_Tradeoffs.md>`_。