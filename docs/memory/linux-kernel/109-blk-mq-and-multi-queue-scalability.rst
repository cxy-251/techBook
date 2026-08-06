第109章：blk-mq 与多队列扩展性
===============================

核心知识点
----------

blk-mq 把多 CPU 提交映射到有限硬件派发队列
   它用于降低传统单共享队列在高速 SSD、NVMe 和多核系统上的锁竞争与 cacheline bouncing。

``struct blk_mq_ctx`` 贴近提交 CPU
   Software context 承接本 CPU 形成的 request，并为 merge、scheduler 与本地提交提供入口。它的目标是减少跨 CPU 共享状态。

``struct blk_mq_hw_ctx`` 贴近驱动派发
   Hardware context 保存 dispatch、CPU mask、tag、NUMA 与驱动私有状态。它是 Linux 块层对象，不必与控制器真实硬件队列一一对应。

``struct blk_mq_tag_set`` 描述驱动能力
   驱动通过它声明硬件队列数量、queue depth、保留 tag、NUMA 信息和 ``blk_mq_ops`` 回调，再由块层建立 request queue 与 hctx 映射。

CPU 到 hctx 的映射决定竞争位置
   多个 CPU 可以共享一个 hctx；硬件队列少于 CPU 数时，这种汇聚会让 tag、dispatch 与驱动队列成为共享热点。

Tag 是在途 request 的稀缺资源
   Request 获得 driver tag 后才能交给驱动。Tag exhaustion 会造成软件排队或 requeue，不等于介质本身变慢。

Scheduler tag 与 driver tag 属于不同阶段
   Scheduler 可用自己的 tag 管理等待 request；driver tag 标识已经具备驱动派发资格的 request。两者不能用同一个深度指标解释。

``queue_rq`` 是驱动接收边界
   驱动接受 request 后把它转换为 DMA 与协议命令；资源不足时可返回暂时忙状态，让块层延后或重新派发，而不是立即上报永久 I/O 错误。

Completion 可以回到不同 CPU
   中断亲和性、polling 与驱动设计决定完成 CPU。提交 CPU、buffer NUMA node、设备 NUMA node、hctx 与 IRQ CPU 的错位会增加远程缓存和唤醒成本。

更多队列不自动带来更高性能
   队列过少会形成共享竞争，过多会增加内存、tag 与控制器管理成本。有效数量必须匹配设备真实并行度、CPU 拓扑和 workload 深度。

blk-mq 只解决块层并发组织
   Page Cache、文件系统锁、COW、journal、reclaim 和 writeback 发生在更上层；request 已 issue 后的设备慢、重试和 reset 发生在更下层。

关键路径
--------

blk-mq 提交
~~~~~~~~~~~

::

   CPU 提交 bio
   → 形成 struct request
   → 当前 CPU 对应 blk_mq_ctx
   → scheduler / merge 或直接路径
   → queue map 选择 blk_mq_hw_ctx
   → 分配 driver tag
   → 驱动 queue_rq
   → 控制器硬件队列

驱动暂时繁忙
~~~~~~~~~~~~

::

   queue_rq 尝试提交
   → 驱动或设备资源不足
   → 返回 resource 状态
   → request 保留在 dispatch / requeue 路径
   → 延后运行 hctx
   → 资源恢复后重新派发

Completion
~~~~~~~~~~

::

   设备完成命令
   → 中断或 polling 找到协议命令
   → 驱动映射回 request/tag
   → blk_mq_end_request
   → 完成 request 中 bio
   → 调用上层回调
   → 归还 tag 与 request

概念辨析
--------

``blk_mq_ctx`` 与 ``blk_mq_hw_ctx``
   前者贴近提交 CPU 的软件上下文；后者贴近驱动的派发上下文。

Hctx 与真实硬件队列
   Hctx 是块层抽象；驱动可以把一个或多个 hctx 映射到控制器队列，不能仅按名称推断拓扑。

Tag depth 与应用队列深度
   Tag 表示块层/驱动可接收的在途 request；应用还可在用户队列、io_uring SQ 或文件系统上层积压请求。

Driver busy 与设备服务慢
   Driver busy 表示请求尚未被接受；issue 后长期未 complete 才更接近设备、下层映射或错误恢复问题。

提交 CPU 与完成 CPU
   两者可以不同，性能分析必须同时检查 IRQ affinity、hctx cpumask、应用 affinity 与 NUMA 拓扑。

本章结论
--------

blk-mq 把多 CPU 的软件提交映射到有限的驱动派发队列，并用 tag 管理在途 request；扩展性取决于队列映射、资源深度和完成亲和性是否匹配真实设备。