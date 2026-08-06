第127章：块设备驱动模型与请求处理
=================================

核心知识点
----------

块设备发布线性扇区地址空间
   块设备向上层提供可随机访问、可排队、可异步完成的存储范围。文件名、文件 offset 和文件系统元数据已经在更上层被转换。

地址单位必须分层理解
   文件 offset、文件系统 block、块层 sector、设备 logical block 和 physical block 属于不同语义层。Linux 块地址常以 512 字节 sector 计数，设备实际对齐要求可更大。

``gendisk`` 表示用户可见磁盘
   ``struct gendisk`` 连接容量、设备号、分区、控制操作、私有数据和 request queue，是磁盘地址空间及其用户态投影的核心对象。

Request queue 表达提交合同
   ``struct request_queue`` 保存 queue limits、排队策略、blk-mq 映射和驱动入口。限制必须在磁盘发布前设置正确，否则上层会生成设备无法执行的请求形状。

``bio`` 与 ``request`` 分工不同
   ``bio`` 描述目标设备、sector、操作和页片段；``request`` 是调度、tag 和驱动派发单位。合并、拆分和映射使它们与应用请求不存在固定一一关系。

控制面与数据面分离
   ``block_device_operations`` 主要处理 open、release、ioctl 和介质事件；普通数据 I/O 通常经 blk-mq 的 ``queue_rq`` 进入驱动。

``queue_rq`` 建立完成责任
   驱动返回接管成功后，必须保证 request 最终恰好完成一次，或按块层协议重新排队。资源不足不能被当作永久错误，也不能静默丢弃请求。

DMA 描述符需要独立顺序协议
   Request segment 还要经过 DMA API 映射成设备可见地址。描述符内容、owner 位、doorbell 和 MMIO posted write 的顺序必须按设备协议建立。

完成路径终结对象所有权
   IRQ、poll 或 worker 根据 command/tag 找回 request，解除 DMA 映射并调用完成接口。完成后驱动不能继续访问 request 或其私有上下文。

错误、超时与 Reset 必须防止双完成
   正常 completion、timeout 和 reset 可能并发。驱动应以状态机和 generation 验证旧命令，防止迟到 completion 命中新一轮复用的 tag。

普通完成不等于持久化
   ``BLK_STS_OK`` 只表示当前块操作满足其完成合同。稳定介质语义还依赖正确处理 flush、FUA 和设备易失写缓存。

磁盘发布与对象释放分离
   ``add_disk()`` 后用户空间可立即扫描和提交 I/O；``del_gendisk()`` 撤销可见性，但旧 open、分区和内部引用仍可延长对象寿命。

关键路径
--------

块设备注册：

::

   初始化硬件与驱动私有状态
   → 建立 blk-mq tag set 和 request_queue
   → 设置容量单位、queue limits 与超时
   → 初始化 gendisk、fops 和 private_data
   → set_capacity 设置 sector 数
   → add_disk 发布磁盘
   → sysfs、uevent、设备节点和分区扫描生效

Request 执行：

::

   上层生成 bio
   → 块层 merge/split 并形成 request
   → blk-mq 选择 hctx 和 tag
   → queue_rq 检查设备与 ring 资源
   → DMA map request segments
   → 填写设备描述符并发布 doorbell
   → 设备执行
   → IRQ/poll 找回 request
   → unmap DMA 并完成 request/bio

安全移除：

::

   标记磁盘 dying 并阻止新业务
   → del_gendisk 撤销用户可见地址空间
   → freeze 或 quiesce 对应队列阶段
   → 停止硬件新提交和 DMA
   → 完成或失败全部在途 request
   → 停止 IRQ、timeout、reset 和 worker
   → 释放 queue、tag set 与硬件资源
   → 等待 open 引用结束
   → put_disk 并释放私有对象

概念辨析
--------

``gendisk`` 与 ``request_queue``
   Gendisk 表示磁盘身份、容量和分区；queue 表示请求能力、排队和驱动提交边界。

``bio`` 与 ``request``
   Bio 描述数据移动需求；request 是块层调度和驱动执行单位。

Sector 与设备块大小
   Sector 是块层地址单位；logical/physical block size 是设备可访问与对齐能力。

Queue Freeze 与 Quiesce
   Freeze 阻止新的块层进入并等待活动路径；quiesce 主要停止 request 向驱动派发。

Request 完成与稳定持久化
   普通完成表示命令结束；掉电后仍存在还需 flush/FUA 与真实设备缓存合同。

``del_gendisk`` 与对象释放
   Del 撤销磁盘可见性；对象存储要等旧打开和全部内部引用结束后释放。

本章结论
--------

块驱动通过 ``gendisk`` 发布扇区地址空间，通过 request queue 接收规范化的 ``bio/request``，并必须在资源不足、错误、超时、reset 和移除竞态中让每个已接管请求恰好结束一次。
