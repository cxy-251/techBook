第127章：块设备驱动模型与请求处理
=================================

本章必须记住
------------

#. 块设备把一段可随机访问的存储空间表达为按 sector 寻址、可排队、可异步完成的线性地址范围。
#. 块驱动接收的不是原始文件语义，而是经过 VFS、文件系统、Page Cache/Direct I/O 和块层转换后的 I/O 工作。
#. 文件 offset、文件系统 block、块层 sector、设备 logical block 和 physical block 是不同层级的单位。
#. 块层常以 512 字节 sector 表达地址和统计；设备 logical/physical block size 可以不同，不能固定假设为 512 或 4096。
#. ``struct gendisk`` 是磁盘级对象，连接容量、名称、分区、设备号、操作表、私有数据和 request queue。
#. ``struct request_queue`` 是块层与驱动之间的能力、排队和提交边界。
#. ``struct bio`` 描述一次块 I/O 的目标、sector、操作、数据页片段和完成关系。
#. ``struct request`` 是 request-based 驱动常见的派发单位，通常由一个或多个兼容 bio 组成。
#. Bio 重点表达“哪些数据范围需要移动”；request 重点表达“驱动当前要执行的调度工作”。
#. 块层可以合并相邻兼容 bio，也可以按 queue limits 拆分过大的 bio/request。
#. 驱动不能假设一个用户请求、一条 bio、一个 request 和一个硬件命令始终一一对应。
#. Queue limits 描述最大请求、最大 segment、对齐、边界、逻辑块、物理块、discard、write zeroes 等能力。
#. Queue limits 必须在磁盘发布前正确设置，否则上层可能生成设备无法执行的请求形状。
#. ``set_capacity()`` 一类接口通常以 512 字节 sector 数设置磁盘容量，具体 helper 以目标内核为准。
#. 容量值、介质存在状态和只读状态是不同属性；设备节点存在不表示介质当前可访问。
#. 块设备操作表 ``struct block_device_operations`` 管理 open/release、ioctl、介质事件等控制面，不承载普通数据 request 的主路径。
#. 现代 request-based 驱动通常通过 blk-mq 的 ``struct blk_mq_ops`` 接收和完成 request。
#. ``queue_rq`` 是驱动接管一个已经分配 tag、选择硬件队列的 request 的核心入口。
#. 驱动在真正把 request 提交给设备前应调用对应 start helper，使超时和统计状态进入运行阶段。
#. ``queue_rq`` 返回成功表示驱动已接管 request；随后必须保证每条路径最终完成或重新排队。
#. 临时资源不足应使用 blk-mq 规定的 resource/backpressure 状态，不应静默丢失 request。
#. 返回资源不足后，驱动必须在资源恢复时重新运行相应硬件队列，否则请求可能永久停滞。
#. Request 的操作类型可能是读、写、flush、discard、write zeroes、zone operation 等，驱动必须按支持能力处理。
#. 不支持的操作应以明确 ``blk_status_t`` 错误完成，不能把未知操作当普通读写。
#. ``rq_for_each_segment`` 等迭代路径得到的是 request 中的数据 segment；segment 仍需按 DMA 和设备描述符限制映射。
#. 一个 segment 的 CPU 页片段不等于一个设备 DMA segment，DMA API/IOMMU 可能合并或重新映射。
#. 驱动必须在设备访问前建立 DMA mapping，在 completion 后按方向解除或同步映射。
#. 设备描述符写完后再发布 owner/valid 位和 doorbell，需要使用适合设备协议的内存屏障。
#. 普通 CPU 内存屏障、MMIO posted write 和设备 DMA 可见性是不同顺序问题，不能用一个宏覆盖全部语义。
#. Request completion 可以发生在 IRQ、poll、softirq、workqueue 或同步模拟后端中，具体上下文决定可执行操作。
#. ``blk_mq_end_request()`` 一类接口把最终状态返回块层；完成后驱动不能继续访问 request 私有数据。
#. 部分完成和分段完成接口具有版本差异；驱动必须准确推进已完成字节并保留未完成部分。
#. ``BLK_STS_OK`` 表示块层请求成功，不自动表示设备易失写缓存已经稳定持久。
#. Flush/FUA 的完成语义必须由驱动和设备真实支持，不能把普通写完成伪装成持久化完成。
#. 硬件错误、超时、介质错误、设备移除和资源不足应映射成不同状态，便于上层决定重试或失败。
#. 错误完成会沿 bio、文件系统、Page Cache、Direct I/O 和用户请求向上传播；驱动不应无界重试永久错误。
#. 超时回调与正常 completion 可能并发，驱动必须用 request 状态、tag 或 generation 防止双完成。
#. Reset 之后旧硬件 completion 可能迟到，必须验证命令 generation，不能命中新队列中复用的 tag。
#. Request tag 是块层队列身份，不必等于设备协议中的 command ID；驱动可建立自己的映射关系。
#. ``gendisk`` 发布前应完成 queue、capacity、fops、private data 和硬件状态初始化。
#. ``add_disk()`` 或相应发布接口成功后，用户空间可以立即扫描分区、读取容量和提交 I/O。
#. 分区是整盘上的子范围，由块层根据分区表维护；驱动通常报告整盘容量和介质状态。
#. `/sys/block/<disk>`、queue 属性、stat 和 `/dev` 节点是 ``gendisk`` 的不同用户可见投影。
#. `/dev` 节点存在只证明设备号和对象被发布，不证明 queue 正常、介质存在或 I/O 能完成。
#. 删除设备时必须先阻止新 I/O，再让上层停止使用，随后冻结/静止 queue、完成或失败在途请求，最后释放资源。
#. Freeze queue 主要阻止新的块层进入并等待活动路径达到指定边界；quiesce 主要停止 dispatch，二者语义不同。
#. 精确 freeze/quiesce helper 和等待行为具有版本差异，不能只按函数名猜 teardown 保证。
#. ``del_gendisk()`` 撤销磁盘用户可见性和分区，不等于所有 open ``block_device`` 引用立即消失。
#. ``put_disk()`` 或最终对象释放必须发生在磁盘对象引用真正结束后，不能在旧 open 或异步路径仍存在时提前释放。
#. Remove 前应停止硬件队列、DMA、IRQ 和 timeout/reset worker，再解除队列与私有对象。
#. 设备突然拔出时，应把磁盘标记为 dead/dying，阻止新请求，并尽快以明确错误完成全部在途请求。
#. 可移动介质设备还需报告介质变化，触发容量、分区和缓存重新验证；具体接口随版本与设备类型变化。
#. 介质变化和设备对象移除不是同一事件：驱动/设备仍存在时，介质本身可以更换。
#. Open block device 可能持有分区、整盘、模块和驱动引用；remove 不能只看驱动私有引用计数。
#. 虚拟块驱动也必须遵守 queue、completion、flush 和 teardown 语义，即使后端不是物理设备。
#. Loop、RAM disk、null_blk、Device Mapper 等路径的后端不同，但向上层都必须提供一致块设备合同。
#. Bio-based 驱动或堆叠 target 可能直接实现 ``submit_bio``，这与 blk-mq request driver 是不同提交边界。
#. Bio 被 remap 到下层设备后，sector 和 ``bi_bdev`` 会改变；诊断时必须记录每一层映射。
#. 驱动吞吐问题应区分上层 bio 生成、scheduler/tag 等待、``queue_rq`` 背压、硬件服务和 completion 回传。
#. `/sys/block/<disk>/stat` 是累计统计，字段反映请求、sector、ticks 和 in-flight 等聚合现象，不能单独还原单次延迟。
#. Block trace/ftrace 能观察 bio/request 插入、issue、requeue、complete，事件名和字段具有版本差异。
#. 调试 I/O 不返回时，应检查 request 是否进入 ``queue_rq``、是否写入硬件、是否收到 completion、是否调用 end_request。
#. 调试双完成时，应对齐 tag 分配、timeout、reset、IRQ 和 completion 代码，而不是只在结束函数前加布尔量。
#. 调试容量或分区错误时，应先确认 sector 单位和 ``set_capacity``，再检查介质读取与分区扫描。
#. 调试设备删除卡死时，应抓取 queue freeze 等待者、open holder、文件系统、在途 request、IRQ 和 reset worker。
#. 稳定源码阅读顺序是：驱动私有对象 → tag set/queue → queue limits → ``gendisk`` → 发布 → ``queue_rq`` → DMA/设备 → completion → remove。
#. 精确磁盘分配 helper、``block_device_operations`` 字段和 blk-mq 回调随版本演进；稳定模型是 ``gendisk`` 发布地址空间，queue 接收规范化请求，驱动最终完成每项工作。

必背路径
--------

块设备注册：

::

   初始化驱动私有对象和硬件
   → 建立 blk-mq tag set / request_queue
   → 设置 queue limits、timeout 和 DMA 约束
   → 分配并初始化 gendisk
   → 设置名称、major/minor、fops、private_data
   → set_capacity 设置 sector 容量
   → add_disk 发布磁盘
   → 创建 sysfs、uevent、/dev 与分区扫描入口

Request 派发：

::

   文件系统/Direct I/O 生成 bio
   → 块层 merge/split
   → bio 进入 request
   → blk-mq 选择 hctx 和 tag
   → 调用 queue_rq
   → 驱动检查设备与 ring 资源
   → start request
   → DMA map 数据段
   → 填写硬件描述符并 doorbell
   → 返回接管成功

Request 完成：

::

   设备产生 IRQ 或 poll completion
   → 读取完成队列和状态
   → 根据 command/tag 找回 request
   → 验证 generation，防止迟到完成
   → 解除 DMA mapping
   → 更新已完成范围和错误
   → blk_mq_end_request
   → 块层完成 bio
   → 唤醒文件系统、Page Cache 或用户请求

安全移除：

::

   标记磁盘 dying 并阻止新业务
   → 注销文件系统/上层使用或等待卸载
   → del_gendisk 撤销用户可见磁盘
   → freeze/quiesce queue
   → 停止硬件新提交
   → 完成或失败全部在途 request
   → 停止 IRQ、timeout、reset 和 worker
   → 释放 DMA、queue、tag set
   → 等待 open 引用结束
   → put_disk 和释放私有对象

诊断挂起请求：

::

   记录 disk、sector、op、request/tag
   → 确认 bio/request 是否创建
   → 确认是否等待 scheduler/tag
   → 确认 queue_rq 是否被调用
   → 确认硬件 descriptor/doorbell
   → 确认 IRQ/poll 是否收到 completion
   → 确认 end_request 是否执行
   → 检查 timeout/reset 是否与正常完成竞争

必须区分
--------

* ``gendisk`` 与 ``request_queue``：Gendisk 表示用户可见磁盘地址空间；queue 表示能力、排队和提交路径。
* ``bio`` 与 ``request``：Bio 描述块数据范围和完成关系；request 是驱动调度与硬件执行单位。
* Sector 与设备块大小：块层地址常以 512 字节 sector 表达；logical/physical block size 是设备能力属性。
* Queue Freeze 与 Quiesce：Freeze 阻止新的块层进入并等待活动路径；quiesce 主要停止向驱动派发。
* Request 完成与数据持久化：普通成功表示 I/O 命令完成；稳定介质保证还依赖 flush/FUA 和设备缓存语义。
* ``del_gendisk`` 与对象释放：Del 撤销用户可见磁盘；旧打开、分区和内部引用仍可能延长对象寿命。

一句话结论
----------

块驱动通过 ``gendisk`` 发布扇区地址空间，通过 request queue 接收块层重塑后的 bio/request，并必须让每个已接管请求在错误、超时、reset 和移除竞态下恰好完成一次。
