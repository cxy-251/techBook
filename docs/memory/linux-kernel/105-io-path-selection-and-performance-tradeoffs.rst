第105章：I/O 路径选择与性能权衡
================================

核心知识点
----------

I/O 选型由多个正交维度组成
   缓存策略、提交模型、完成语义、请求形状、资源占用和性能目标必须分别判断，不能把某个 API 当作统一最快答案。

缓存策略决定 Page Cache 参与程度
   Buffered I/O 使用 Page Cache、预读、回写和回收；Direct I/O 请求尽量绕过 Page Cache，并把更多缓存责任交给应用。

提交模型决定如何管理等待
   同步调用、线程池、readiness loop、legacy AIO 和 ``io_uring`` 的主要区别是请求如何提交、并行、完成和收束。

完成语义独立于提交接口
   普通 I/O 完成、dirty writeback 完成、``fsync`` 成功和设备稳定持久化是不同边界。异步或 Direct 都不能替代持久化协议。

请求形状决定底层成本
   顺序或随机、读或写、请求大小、对齐、文件数量、稀疏范围和并发关系会改变缓存命中、映射、bio 数量和设备并行度。

工作集复用决定缓存收益
   热点会重复访问、多个进程共享文件页或内核预读有效时，Buffered I/O 往往能避免大量真实设备访问。

应用已有缓存时可评估 Direct I/O
   数据低复用、工作集远大于内存、请求可稳定对齐且 Page Cache 污染已被证实时，Direct I/O 可能降低复制与回收压力。

同步 I/O 是必要基线
   当请求足够大、并发由多线程自然提供且实现复杂度敏感时，同步路径可能已经满足目标。异步接口不自动降低单次设备服务时间。

异步模型管理在途工作
   ``io_uring``、AIO 或线程池主要通过重叠等待、批量提交和统一 completion 提高利用率。它们都需要有界队列、背压和 teardown。

Readiness 更适合可非阻塞推进对象
   Socket、pipe 等对象可由 ``epoll`` 表达当前可操作状态；普通磁盘文件通常不能靠 readiness 表示某个设备请求已经完成。

队列深度在吞吐与延迟间权衡
   深度过低无法展开设备并行，过高会增加用户队列、内核队列、buffer 占用和 P99/P999。设备支持高深度不表示应用应填满它。

请求大小具有双向影响
   大请求降低每字节 syscall、映射和命令开销，也延长单次占用、取消粒度和错误重试范围。小随机 I/O 更依赖缓存与固定成本控制。

复制与页固定是不同成本
   Buffered I/O 通常有 Page Cache 到用户 buffer 的复制；Direct I/O 减少该复制，却增加对齐、pinning、应用缓存和生命周期管理成本。

Registered resources 只在稳定复用时收益
   Fixed file 和 registered buffer 可减少高频查找与固定成本。频繁注册、更新或长期 pin 可能抵消收益。

Polling 用专用 CPU 换较低唤醒开销
   SQPOLL、IOPOLL 或用户 busy polling 适合受控低延迟环境。必须同时评估 CPU、功耗和同核任务干扰。

Buffered write 会延迟支付成本
   前台 write 很快不代表设备轻松。Dirty 积累、throttling、writeback 和 fsync 尾延迟必须和应用写入速率一起测量。

性能测试必须固定实验边界
   文件系统、挂载选项、设备、文件布局、CPU/NUMA、请求大小、并发和后台负载都要保持一致。冷缓存与热缓存应分别报告。

吞吐不能替代延迟分布
   只报告 MB/s 无法解释排队和尾部停顿。至少同时记录平均延迟、P99/P999、CPU、内存、错误和在途深度。

观测需要跨层对齐
   ``strace`` 确认 API 与参数，``perf`` 定位 CPU，tracefs/eBPF 连接 VFS、filemap、iomap 和 ``io_uring``，块层事件拆分排队与设备服务。

一次只改变一个关键变量
   同时切换 Direct、``io_uring``、文件系统选项和队列深度会失去归因能力。每次改动都要用同一工作负载重新验证。

关键路径
--------

选择缓存策略：

::

   描述工作集大小和复用距离
   → 检查 Page Cache 命中、预读和共享收益
   → 热点复用明显时优先 Buffered I/O
   → 低复用且缓存污染已证实时评估 Direct I/O
   → 检查对齐、pinning 和应用缓存能力
   → 用 CPU、内存、块层和尾延迟对照验证

选择提交模型：

::

   建立同步路径基线
   → 判断等待是否限制吞吐
   → 估算所需 outstanding depth
   → 少量通用阻塞任务使用线程池
   → 特定受支持文件路径评估 legacy AIO
   → 需要批量、统一 completion、取消和多类操作时评估 io_uring
   → 设计背压与 teardown

拆分一次请求延迟：

::

   应用排队
   → syscall 或 SQ 提交
   → Page Cache / 文件系统准备
   → bio / request 进入块层
   → 内核队列等待
   → 设备服务
   → completion / CQE
   → 用户线程被调度
   → 业务状态机完成

验证实际路径：

::

   strace 确认 syscall、flag、offset 和长度
   → perf 定位 copy、锁和 worker CPU
   → tracefs/eBPF 追 VFS、filemap、iomap、io_uring
   → 块层 trace 追 dispatch 与 completion
   → vmstat、PSI、iostat 补充系统压力
   → 按同一时间窗口和请求身份对齐

概念辨析
--------

* **缓存策略与提交模型**：Buffered/Direct 决定数据缓存路径；同步、AIO、线程池和 ``io_uring`` 决定未完成工作的管理方式。
* **吞吐与单次延迟**：增加并发可提高设备利用率，也会增加排队；二者不能从同一个平均值推导。
* **冷缓存与热缓存**：前者主要测后端读入，后者主要测缓存查找、复制和 CPU。
* **Page Cache 污染与高缓存占用**：污染需要证明热点被淘汰和 refault 增加，而不是看到 ``Cached`` 较高。
* **Direct I/O 与 zero-copy**：Direct 减少 Page Cache 参与，不保证完整路径没有复制或地址转换。
* **异步完成与稳定持久化**：CQE 或 AIO completion 报告请求结果；崩溃恢复边界仍由同步和文件系统协议决定。

本章结论
--------

I/O 性能问题通常来自访问模式、缓存策略、请求形状、在途深度和设备能力不匹配。正确选型应从工作负载出发，逐层测量缓存、文件系统、队列、设备和完成消费，而不是从接口名称推断性能。
