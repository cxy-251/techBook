第107章：bio、Request 与块 I/O 数据模型
=======================================

本章必须记住
------------

#. ``struct bio`` 是块层表达一次数据移动需求的基础对象；它描述目标块设备、操作、sector 范围、内存片段和完成回调。
#. ``bio`` 不是文件对象，也不是最终硬件命令；它位于文件系统映射结果与驱动 request 之间。
#. ``bi_bdev`` 指向目标 ``struct block_device``，说明请求当前面向哪个块设备或分区。
#. ``bi_opf`` 保存操作类型和请求标志；READ、WRITE、FLUSH、DISCARD 等语义通过 helper 和位字段解释。
#. ``bi_iter`` 保存当前剩余 I/O 的 sector、字节数和内存片段游标，是部分完成、拆分和迭代的中心。
#. ``bi_io_vec`` 指向 ``struct bio_vec`` 数组，``bio_vec`` 用页、页内偏移和长度描述内存来源或目的地。
#. ``bi_end_io`` 是完成回调，``bi_private`` 保存提交者上下文；两者决定完成后由谁继续收束生命周期。
#. ``bi_status`` 保存块层完成状态，上层通常再把它转换为 errno、folio error、Direct I/O 结果或文件系统状态。
#. ``bio`` 的 sector 地址以块层 sector 语义表达，不能和文件 offset 或设备内部物理地址混淆。
#. 一个 ``bio`` 可以包含多个 ``bio_vec``，因此内存可以由多个页片段组成，不要求整个 buffer 物理连续。
#. ``struct bio_vec`` 的稳定语义是 ``bv_page``、``bv_offset``、``bv_len``；精确布局与 helper 随版本变化。
#. ``bio_vec`` 描述的是页片段，不记录该页来自哪个文件、进程、Page Cache、Swap 或用户 pin。
#. 上层对象身份通过 ``bi_private``、回调、request 关联或其它私有结构维护，不能从 ``bio_vec`` 推断。
#. 现代 biovec 迭代模型把可变进度集中在 ``struct bvec_iter``，原始片段集合可保持稳定。
#. ``bi_iter.bi_sector`` 随进度推进，``bi_iter.bi_size`` 表示剩余字节，片段索引和片段内完成量也随迭代变化。
#. 处理当前片段应使用 ``bio_for_each_segment``、``bio_iter_iovec`` 等 helper，而不是自行假设数组和页边界。
#. 一个 ``bio_vec`` 可能覆盖超过一个基础页或由 compound page/folio 支撑，具体 helper 语义应按目标版本确认。
#. Bio 中的页片段最终还要转换为设备可 DMA 的 scatter-gather 段；bio_vec 数量不等于硬件 DMA segment 数量。
#. 相邻物理片段可能在 DMA 映射后合并，边界、IOMMU、最大 segment 和控制器限制也可能再次拆分。
#. ``bio`` 提交前由上层构造和拥有；提交后，调用者必须遵守异步生命周期，不能随意修改其关键字段或释放页。
#. 完成回调可能在中断、softirq、轮询或其它不可睡眠上下文执行，具体路径由驱动和配置决定。
#. ``bi_end_io`` 中不能无条件执行可睡眠工作；复杂清理通常要转交 workqueue 或其它进程上下文。
#. 完成回调必须正确归还 bio 引用、页面引用、用户 pin、计数器和上层请求状态，遗漏会形成泄漏或永久等待。
#. ``bio_put()`` 只归还 bio 对象本身，不自动结束其中页、文件、请求和业务上下文的所有权。
#. Bio 可以从 bioset、mempool 或普通分配路径取得，关键 I/O 路径常使用预分配池保证回收/提交前进。
#. 内存压力路径不能依赖可能递归进入同一 I/O 栈的普通分配，GFP 与 bioset 选择是死锁设计的一部分。
#. Bio merge 用于把相邻、同设备、同操作且标志兼容的数据移动需求组织成更大 request。
#. 合并条件还受 queue limits、segment、integrity、crypto、zone、atomic write 和调度状态约束。
#. 合并可以发生为 front merge、back merge 或其它实现形式，具体函数和策略具有版本差异。
#. 合并减少软件 request、tag 和设备命令数量，不保证任何设备和 workload 都更快。
#. 对高速多队列设备，过度合并可能降低并行度或增加单请求延迟；收益必须结合实际队列和请求大小测量。
#. Bio split 用于把超过设备最大 sectors、segment、boundary 或特殊操作限制的大 I/O 切成多个可接受子范围。
#. ``bio_split()`` 一类路径常让分裂对象共享原始 biovec 集合，并通过不同 iterator 表达子区间。
#. Split 后原 bio 与新 bio 的完成关系必须正确链接，只有所有必要子请求结束，上层原操作才算完成。
#. 子请求部分失败时，上层应保留首个或合并后的错误语义，不能因其它子请求成功而静默丢失错误。
#. Bio clone 创建共享底层数据描述的另一个 bio 视图，常用于 Device Mapper、RAID、加密和重映射层。
#. Clone 通常共享或引用原 biovec，不等于深复制数据页；原始页和上下文必须活到所有 clone 完成。
#. Clone 可以改写 ``bi_bdev``、sector、操作标志和完成回调，把同一数据映射到下层设备。
#. 一个上层 bio 可以因 mirror/stripe 变成多个下层 clone；上层完成取决于冗余策略和所有子请求结果。
#. ``bio_chain()``、剩余计数或 target 私有聚合结构用于表达父子完成依赖，具体实现因层级而异。
#. Bio remap 只改变块地址层关系，不自动改变上层文件系统对数据和持久化的合同。
#. ``struct request`` 是更接近 request queue、调度器、blk-mq、tag 和驱动执行的对象。
#. 一个 request 可以包含一个或多个 bio；``bio`` 链保留数据移动片段与上层完成关系。
#. ``request`` 通常保存队列、操作、sector 范围、状态、tag、超时、启动/完成信息和驱动私有数据。
#. Request 是调度器、硬件队列和驱动更直接处理的单位，但仍不等于 NVMe/SCSI 的最终协议命令对象。
#. 驱动在 ``queue_rq`` 等回调中把 request 转换为控制器命令、DMA 描述和硬件队列项。
#. 一个 request 可能被驱动进一步拆分、映射或重试；一个设备命令也可能只完成 request 的部分进度。
#. Bio 与 request 的完成层次必须分开：驱动先结束 request，再由块层推进其中 bio 并调用各自完成回调。
#. Request tag 用于在 blk-mq 队列中标识在途 request；设备协议还可能有自己的 command ID，二者不能机械等同。
#. Request 超时表示在指定时间内没有按预期完成，超时处理可能 abort、reset、requeue 或最终失败。
#. Requeue 表示 request 暂时不能由驱动接受，重新进入派发路径；它不是新的文件系统操作。
#. 驱动返回资源不足状态时，块层可停止/延后硬件队列并重试，具体状态码和行为随驱动接口而定。
#. Request completion 可以从目标 CPU、中断 CPU 或 polling CPU 回流，完成 CPU 不保证等于提交 CPU。
#. 部分完成会推进 bio/request iterator，剩余范围继续处理；调用者不能假设完成事件总覆盖原始全部长度。
#. Flush、discard、zone append 等非普通读写操作可能没有常规数据页片段，不能按 READ/WRITE bio_vec 模型硬套。
#. Zone append 的最终写入位置可能由设备决定并在完成中返回，具体接口和支持范围具有版本差异。
#. Integrity、inline crypto 和 cgroup 信息可以附着于 bio/request，说明相同数据移动还受校验、加密和服务控制约束。
#. Bio/request 的复制、clone 和 split 必须正确传播这些扩展上下文，遗漏会造成数据损坏或策略绕过。
#. 观察 ``bio`` 数量不能直接推断 request 数量，因为 merge/split/remap 会改变一一关系。
#. 观察 request 数量也不能直接推断硬件命令数量，因为驱动和设备内部还可能合并、拆分、重试和并行执行。
#. Block tracepoint 中的 bio、request、merge、remap 和 complete 事件应组合解释，不能只匹配相同 sector 的一对事件。
#. Device Mapper 场景中应追踪 major/minor 和 remap，避免把上层虚拟设备与下层物理设备事件重复计为独立业务 I/O。
#. 调试卡住的 bio 时，应找提交者、``bi_private``、``bi_end_io``、剩余计数、下层 clone 和最终 request 状态。
#. 调试数据损坏时，应同时检查 sector/长度、biovec offset、split 边界、DMA mapping、clone remap 和完成顺序。
#. 调试 UAF 时，应检查 bio 完成是否迟于上层对象销毁、页面是否过早 unpin、clone 是否仍共享原内存。
#. 最稳定源码阅读顺序是：bio 构造 → biovec/iterator → submit → merge/split/remap → request → driver queue → request/bio completion。
#. 稳定模型是“bio 描述数据移动，request 描述队列执行”；精确字段、helper 和 tracepoint 属于版本敏感实现。

必背路径
--------

构造并提交 bio：

::

   上层确定 block_device、sector 和操作
   → 分配 bio
   → 添加 page/offset/length bio_vec
   → 设置 bi_opf
   → 设置 bi_private 与 bi_end_io
   → submit_bio
   → 块层检查限制、合并或拆分
   → 形成 request 并派发驱动

Bio split：

::

   原 bio 超过 queue limits
   → 计算可接受前段范围
   → 创建共享 biovec 的 split bio
   → 设置独立 bvec_iter 子区间
   → 推进原 bio 到剩余范围
   → 分别提交子请求
   → 汇总完成与错误
   → 最后完成原上层操作

Device Mapper clone：

::

   上层 bio 到达虚拟块设备
   → target 查映射表
   → clone bio 并引用原数据页
   → 改写下层 bi_bdev 与 sector
   → 可拆成多个 mirror/stripe 子 bio
   → 下层 request 完成
   → 聚合状态
   → 调用原 bio 完成回调

Request 派发：

::

   一个或多个兼容 bio
   → 形成 struct request
   → 进入 request_queue / scheduler
   → 映射到 blk_mq_hw_ctx
   → 分配 tag
   → 驱动 queue_rq
   → 建立 DMA 和设备命令
   → 硬件完成
   → blk_mq_end_request
   → 完成 request 中的 bio

完成回收：

::

   驱动报告状态和已完成范围
   → 块层推进 request/bio iterator
   → 若仍有剩余则继续或失败
   → 设置 bi_status
   → 调用 bi_end_io
   → 上层释放页面、pin 和私有上下文
   → bio_put / request tag 回收

必须区分
--------

* ``bio`` 与 ``request``：Bio 描述面向块设备的数据移动；request 是队列、调度器、tag 和驱动处理的执行单位。
* ``bio_vec`` 与 DMA segment：Bio_vec 是页片段描述；DMA 映射后片段数量和边界还可变化。
* Split 与 Clone：Split 把一个范围切成子区间；clone 创建共享数据描述的另一个映射视图。
* Bio completion 与 Request completion：驱动通常结束 request；块层再推进并完成其中一个或多个 bio。
* Request tag 与设备命令 ID：Tag 标识 blk-mq 在途 request；协议控制器可能使用另一套命令标识。
* 完成对象与资源所有权：``bio_put`` 归还 bio 存储；页、用户 pin、文件和上层对象仍需按各自协议释放。

一句话结论
----------

``bio`` 用 block device、sector 和 biovec 描述数据怎样移动，块层通过 merge、split、clone 把它塑形成 ``request``，再交给驱动和硬件队列执行。
