第107章：bio、Request 与块 I/O 数据模型
=======================================

核心知识点
----------

``struct bio`` 描述块数据移动需求
   它保存目标 ``block_device``、操作与标志、sector 范围、内存页片段、状态和完成回调。它不是文件对象，也不是最终硬件命令。

``bio_vec`` 描述内存片段
   ``bv_page``、``bv_offset`` 和 ``bv_len`` 表示页及页内范围。一个 ``bio`` 可以引用多个非连续页片段，因此用户缓冲区或 Page Cache 数据不要求物理连续。

``bvec_iter`` 保存当前进度
   ``bi_sector``、``bi_size``、片段索引和片段内偏移随部分完成、拆分与迭代推进。代码应使用内核 helper 遍历，不能自行假设数组边界。

Bio 生命周期跨越异步提交
   ``submit_bio()`` 后，上层不能随意修改关键字段或释放页面。``bi_private`` 和 ``bi_end_io`` 把完成事件连接回提交者，完成路径负责释放页面引用、用户 pin 和上层状态。

``bio_put()`` 只释放 bio 容器
   数据页、文件对象、私有上下文和父请求拥有各自的生命周期。归还 bio 存储不等于所有关联资源都已结束。

Merge 减少请求数量
   同设备、同方向、sector 连续且标志兼容的 bio 可以合并到一个 request。合并仍受 segment、边界、加密、完整性、zone 和设备限制约束。

Split 适配设备能力
   超过最大 sectors、segment 数或边界限制的 bio 会被切成多个子范围。子 bio 可以共享原始 biovec，父操作只有在全部必要子请求收束后才完成。

Clone 支撑块设备分层
   Device Mapper、RAID 和加密层可 clone bio，共享原数据描述并改写目标设备、sector、标志和完成回调。Clone 不是数据页深复制。

``struct request`` 是队列执行单位
   一个 request 可以包含一个或多个 bio，并进一步携带队列、tag、超时、派发状态和驱动私有信息。Scheduler、blk-mq 和驱动主要围绕 request 工作。

Request 仍不是协议命令
   驱动在 ``queue_rq`` 等路径中把 request 转换为 DMA 描述和 NVMe、SCSI 或其它设备命令。驱动还可能重试、部分完成或重新排队。

完成按层次回传
   设备先完成命令，驱动结束 request，块层推进其中 bio 的 iterator 与状态，再调用各自 ``bi_end_io``。提交、request 完成和 bio 上层完成不能混为同一时刻。

关键路径
--------

Bio 构造与提交
~~~~~~~~~~~~~~

::

   确定 block_device、sector 与操作
   → 分配 bio
   → 添加 page / offset / length 片段
   → 设置 bi_opf、bi_private、bi_end_io
   → submit_bio
   → queue limits 检查
   → merge / split / remap
   → 形成 request

Bio split
~~~~~~~~~

::

   bio 超过设备限制
   → 计算可接受子范围
   → 创建共享 biovec 的 split bio
   → 为子范围设置独立 iterator
   → 推进原 bio 剩余范围
   → 分别提交
   → 聚合完成与错误

Request 完成
~~~~~~~~~~~~

::

   request 分配 tag
   → 驱动 queue_rq
   → 建立 DMA 与设备命令
   → 硬件报告完成
   → 块层更新 request 状态与进度
   → 完成其中 bio
   → 调用 bi_end_io
   → 归还 tag、request 与上层资源

概念辨析
--------

``bio`` 与 ``request``
   Bio 表达数据从哪些页移动到哪个块范围；request 表达这些 bio 如何进入软件队列、tag、驱动和硬件执行。

``bio_vec`` 与 DMA segment
   Bio_vec 是内核页片段；IOMMU、DMA mapping 和控制器限制会再次合并或拆分，二者数量不必相等。

Split 与 Clone
   Split 把一个地址范围切成多个子范围；clone 创建共享数据描述的新映射视图，常用于下层设备重映射。

Request tag 与设备命令 ID
   Tag 标识 blk-mq 中的在途 request；协议驱动还可使用自己的 CID、tag 或槽位编号。

Request 完成与 Bio 完成
   驱动结束的是 request；块层随后完成其中一个或多个 bio，并触发上层回调。

本章结论
--------

``bio`` 描述块范围与内存片段之间的数据移动，块层通过 merge、split 和 clone 把它组织成 ``request``，再由驱动转换为真正的设备工作。