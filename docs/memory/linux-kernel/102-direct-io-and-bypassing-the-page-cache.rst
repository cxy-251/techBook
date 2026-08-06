第102章：Direct I/O 与绕过 Page Cache
=====================================

本章必须记住
------------

#. Direct I/O 表达的是“本次文件数据传输尽量绕过 Page Cache”的路径请求，不是“完全绕过所有内核缓存”。
#. 应用通常通过 ``O_DIRECT`` 打开标志或请求级 direct 标志进入该语义，具体能力由文件系统和内核版本决定。
#. ``O_DIRECT`` 属于缓存路径选择；``O_SYNC``、``O_DSYNC``、``fsync`` 属于完成与持久化语义，两者必须分开。
#. Direct write 完成不自动证明设备内部易失缓存已经刷新，也不自动建立应用事务持久化保证。
#. VFS 仍要完成 fd lookup、权限、文件状态、用户缓冲区、offset 和文件系统回调处理，Direct I/O 不是绕过 VFS。
#. 常见路径从 ``file->f_op->read_iter/write_iter`` 进入具体文件系统，再进入 iomap 或文件系统专用 direct I/O 实现。
#. ``IOCB_DIRECT``、``FMODE_CAN_ODIRECT``、``iomap_dio_rw()`` 等名称能帮助定位现代实现，具体组合具有版本差异。
#. 文件系统可以拒绝不支持的 Direct I/O，也可能对某些请求回退到 buffered path；调用者必须检查实际返回结果和运行证据。
#. Direct I/O 的约束通常同时作用于用户 buffer 地址、I/O 长度和文件 offset。
#. 只让长度对齐不够；buffer 地址和 offset 也必须满足目标文件系统与设备路径要求。
#. 对齐单位不能固定假设为 512 或 4096 字节，应从目标文件、文件系统和设备能力确认。
#. 较新的内核和文件系统可以通过 ``statx(..., STATX_DIOALIGN, ...)`` 暴露部分 direct I/O 对齐信息，支持范围具有版本差异。
#. 未满足对齐要求时可能返回 ``EINVAL``，也可能由具体实现回退到 buffered I/O，不能无条件推断。
#. 用户态应使用受控的对齐分配和 buffer pool，并对短 I/O、错误和部分完成进行处理。
#. Direct I/O 通常需要在请求存续期间固定或引用用户页，使底层 I/O 能安全访问这些页面。
#. Buffer 从提交开始到完成可见之前不能被释放、重分配、取消映射或复用于不兼容请求。
#. 异步 Direct I/O 的系统调用提交返回不等于 buffer 可以立即复用，必须等待对应 completion。
#. 长期或大量 page pin 会降低页面迁移、回收和内存管理灵活性，也可能影响 NUMA 与内存压力。
#. 使用私有映射内存作为在途 Direct I/O buffer 时，``fork()`` 语义存在严格限制；工程上应在 fork 前完成 I/O 或使用适合的共享/受控内存模型。
#. Buffer pool 的生命周期必须覆盖 ring、请求、设备完成、取消和进程退出路径。
#. 文件 offset 到后端 extent 的映射仍由文件系统负责，Direct I/O 不消除块分配、COW、日志和元数据操作。
#. 对已分配完整 extent 的覆盖写通常更接近 direct 快路径；洞、未写 extent、文件扩展和 EOF 边界需要额外处理。
#. 文件扩展可能要求分配空间、更新 inode 大小、补零尾部和提交元数据事务。
#. Btrfs 等 COW 文件系统中的 Direct I/O 仍可能分配新 extent、计算 checksum 和更新树结构。
#. 压缩、加密、verity、inline data、reflink、DAX 或特殊设备语义可能限制或改变 Direct I/O 路径。
#. Direct I/O 不意味着物理地址连续；内核可把用户页片段组织成多个 bio/vector 并交给块层。
#. Direct I/O 也不意味着设备执行一次单命令；请求可能因设备限制被拆分、合并或重排。
#. 用户 buffer 地址不是设备 DMA 地址；DMA 映射、IOMMU 和设备队列仍由内核与驱动处理。
#. Direct read 把后端数据送入用户 buffer，通常不建立可供其它 buffered reader 复用的新 Page Cache 内容。
#. Direct write 与已有 Page Cache 范围之间必须保持一致，文件系统通常需要等待、写回或失效重叠缓存。
#. 同一文件混用 buffered write 和 direct read 时，direct read 前必须确保相关 dirty cache 已正确同步，否则可能读取旧后端数据。
#. 同一文件混用 direct write 和 buffered read 时，必须保证旧缓存页被失效或重新验证，否则 buffered reader 可能看到旧数据。
#. 文件系统会实现必要的一致性协议，但应用在并发混用时仍需建立明确的顺序和锁定规则。
#. ``fsync``、``fdatasync``、文件锁或应用协议解决不同问题，不能用其中一个名字替代完整一致性证明。
#. Direct I/O 不自动绕过网络服务器缓存、存储控制器缓存、设备 write cache 或虚拟化层缓存。
#. NFS 客户端的 direct 语义主要约束客户端 Page Cache，端到端缓存与持久化仍由协议和服务器决定。
#. Device mapper、RAID、加密、thin provisioning 和远端块设备仍可在 Direct I/O 下加入映射、缓存和队列。
#. Direct I/O 的主要潜在收益是减少 Page Cache 污染、减少一次用户/内核数据复制，并把缓存策略交给应用。
#. 它适合应用已有稳定缓存、请求大且对齐、工作集远大于内存、数据很少复用或需要控制缓存占用的场景。
#. 数据库、虚拟机镜像和大文件流式处理常评估 Direct I/O，但是否收益必须由实际文件系统、设备和访问模式证明。
#. 热点重复读取若本来能命中 Page Cache，改成 Direct I/O 会把内存命中变成真实设备 I/O，延迟通常更差。
#. 小、随机、未对齐 I/O 会放大固定提交成本、页固定、请求拆分和设备队列开销。
#. Direct I/O 会减少内核预读、缓存复用和写合并收益，应用需要自己管理批量、预取、缓存和回收。
#. 绕过 Page Cache 可能降低 reclaim 压力，也可能通过大量 pinned pages 和高队列深度制造新的内存压力。
#. 队列深度过低无法发挥设备并行；过高会增加排队时间、buffer 占用和尾延迟。
#. Direct I/O 可以同步提交，也可以通过 legacy AIO 或 ``io_uring`` 异步提交；缓存策略与完成模型仍是两个维度。
#. 异步提交只有在底层路径真正支持异步推进时才避免提交线程阻塞；元数据、锁、分配或 fault 仍可能触发同步工作。
#. ``RWF_NOWAIT`` 一类请求可用于拒绝会阻塞的路径，但支持范围和错误行为必须按目标文件系统验证。
#. Direct I/O 返回短读或短写并非总是错误，调用者必须按返回字节数推进 offset 和 buffer。
#. 错误完成可能在部分数据已经传输后发生，应用需要定义可重试边界和幂等策略。
#. 取消请求不自动回滚已经完成的设备写入；取消只改变尚未完成部分和完成通知语义。
#. 不能只用缓存命中率评价 Direct I/O，应同时测 CPU copy、Page Cache 压力、pinning、队列深度、设备吞吐和 P99 延迟。
#. ``strace`` 能证明 ``O_DIRECT``、pread/pwrite 或 ``io_uring`` 接口，不能单独证明所有数据实际绕过缓存。
#. ftrace/perf 可定位 iomap、文件系统和 CPU 成本；块层 trace 可证明真实 bio/request 提交与完成。
#. 诊断 ``EINVAL`` 时应按 buffer 地址、长度、offset、文件类型、文件系统能力和特殊 extent 状态逐项检查。
#. 诊断性能退化时应比较同一数据集的冷缓存与热缓存、同步与异步、不同请求大小和队列深度。
#. 最稳定源码阅读顺序是：打开标志/请求标志 → ``kiocb``/``iov_iter`` → 文件系统 ``read_iter/write_iter`` → direct mapping → page pin → bio/block completion。

必背路径
--------

Direct write：

::

   open 设置 O_DIRECT 或请求设置 direct 标志
   → VFS 取得 struct file
   → 构造 kiocb 与 iov_iter
   → 文件系统检查 direct 能力
   → 检查 buffer、长度和 offset 对齐
   → 固定/引用用户页
   → 映射文件 offset 到 extent
   → 构造并提交 bio / 块请求
   → 设备完成
   → 解除页固定并写入完成结果
   → 调用者才可复用 buffer

文件扩展的 Direct write：

::

   请求覆盖文件尾部或 hole
   → 文件系统序列化 extent 状态
   → 分配或准备新空间
   → 处理未写 extent / 补零 / COW
   → 提交数据 I/O
   → 更新 inode 大小和必要元数据
   → 提交文件系统事务
   → 按同步语义决定是否等待持久化

混用 Buffered 与 Direct：

::

   确认两个路径是否访问重叠范围
   → 阻止并发产生新的冲突访问
   → 写回并等待重叠 dirty Page Cache
   → 失效或重新验证旧缓存范围
   → 执行 Direct I/O
   → 完成后建立应用可见顺序
   → 再允许 buffered reader/writer 进入

检查对齐失败：

::

   保存 errno、文件和请求参数
   → 查询 STATX_DIOALIGN（若支持）
   → 检查 buffer 地址
   → 检查 I/O 长度
   → 检查文件 offset
   → 检查文件系统、mount 与文件属性
   → 检查 EOF、hole、COW、压缩和加密边界
   → 调整请求或明确改走 buffered path

判断是否适合 Direct I/O：

::

   描述数据复用率和工作集大小
   → 确认应用是否已有缓存
   → 确认请求能稳定大块对齐
   → 测量 Page Cache 污染与 copy CPU
   → 测量 pinning、队列和设备延迟
   → 与 buffered I/O 做同条件对照
   → 只在真实瓶颈改善时采用

必须区分
--------

* Direct I/O 与同步持久化：Direct 决定 Page Cache 参与程度；sync/fsync 决定完成时需要等待哪些数据、元数据和设备顺序。
* 用户虚拟地址与 DMA 地址：应用提供虚拟 buffer；内核仍需固定页面并建立设备可访问映射。
* 对齐请求与路径保证：满足对齐只是必要条件之一；文件系统状态和特殊功能仍可拒绝或改变路径。
* 绕过 Page Cache 与绕过所有缓存：Direct 不消除控制器、设备、服务器、虚拟块层和应用自己的缓存。
* 提交完成与 I/O 完成：异步提交返回只表示请求被接受；收到 completion 后才能结束 buffer 生命周期。
* 缓存污染减少与内存压力消失：少用 Page Cache 可减少缓存占用；大量页固定和在途 buffer 仍会占用并限制内存管理。

一句话结论
----------

Direct I/O 用对齐、页固定和应用自管缓存换取较少的 Page Cache 参与，但一致性、异步完成、持久化和设备队列后果都必须由应用与文件系统共同承担。
