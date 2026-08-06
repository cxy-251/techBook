第102章：Direct I/O 与绕过 Page Cache
=====================================

核心知识点
----------

Direct I/O 是缓存路径选择
   ``O_DIRECT`` 或请求级 direct 标志表示本次文件数据传输尽量不进入 Page Cache。它不绕过 VFS、文件系统、块层、设备缓存或网络服务器缓存。

Direct 与持久化语义分离
   ``O_DIRECT`` 决定 Page Cache 参与程度；``O_SYNC``、``O_DSYNC``、``fsync`` 和设备 flush 决定完成时需要等待到哪一层。

文件系统仍控制真实路径
   请求仍从 ``file->f_op->read_iter/write_iter`` 进入具体实现。文件 offset 到 extent、块分配、COW、日志和错误处理都没有消失。

对齐是路径合同的一部分
   用户 buffer 地址、I/O 长度和文件 offset 通常都要满足文件系统及设备约束。对齐单位不能固定假设为 512 或 4096 字节。

不满足条件时结果依实现而定
   未对齐、特殊文件类型或不支持的 extent 状态可能返回 ``EINVAL``，也可能由特定文件系统回退到 buffered path。调用者必须验证目标环境。

用户页生命周期跨越请求
   Direct I/O 通常需要引用或固定用户页，使设备在异步完成前可以安全访问。提交后 buffer 不能提前释放、取消映射或复用于冲突操作。

页固定具有内存代价
   大量或长期 pin 会限制回收、迁移、NUMA 放置和 compaction。绕过 Page Cache 不表示内存压力消失。

Direct I/O 不要求物理连续
   用户页可以被组织成多个向量、bio 和 request。DMA 映射、IOMMU、拆分、合并和设备队列仍由内核处理。

文件扩展仍需元数据工作
   写入 hole、EOF 或未写 extent 时，文件系统可能分配空间、补零、更新 inode 大小并提交日志或 COW 元数据。

Direct read 不建立共享文件缓存
   后端数据通常直接进入用户 buffer，不会形成供其它 buffered reader 复用的新 Page Cache 内容。

混用 Buffered 与 Direct 需要一致性协议
   Direct read 前要处理重叠 dirty cache；Direct write 后要避免旧缓存继续服务读取。文件系统提供基础协调，应用仍需定义并发顺序。

关闭 fd 不等于结束在途请求
   异步请求可持有自己的 ``struct file`` 和页面引用。取消、等待 completion 与 buffer 回收必须使用对应异步接口完成。

Direct I/O 的主要收益
   它可减少 Page Cache 污染和一次缓存复制，并让已有应用缓存直接管理数据。收益常出现在大块、对齐、低复用且工作集远大于内存的场景。

Direct I/O 的主要代价
   小随机请求、热点重复读取和不稳定对齐会放大页固定、提交、拆分和设备访问成本，同时失去内核预读与缓存复用。

队列深度决定并行与排队
   深度过低不能展开设备并行，过高会增加在途 buffer、排队时间和尾延迟。应按设备与业务目标设定有界窗口。

关键路径
--------

Direct write：

::

   open 使用 O_DIRECT 或请求设置 direct 标志
   → VFS 取得 struct file
   → 文件系统检查能力和对齐
   → 引用或固定用户页
   → 文件 offset 映射到 extent
   → 必要时分配空间或处理 COW
   → 构造 bio / request
   → 设备执行并完成
   → 解除页面引用
   → 返回同步结果或生成异步 completion

文件扩展写入：

::

   请求覆盖 EOF、hole 或 unwritten extent
   → 序列化映射状态
   → 预留或分配物理空间
   → 提交数据 I/O
   → 更新文件大小和 extent 状态
   → 提交必要元数据事务
   → 按同步标志决定持久化等待边界

混用缓存路径：

::

   确认 Buffered 与 Direct 的重叠范围
   → 阻止新的冲突访问
   → 写回并等待重叠 dirty Page Cache
   → 失效或重新验证旧缓存
   → 执行 Direct I/O
   → 建立完成与可见顺序
   → 重新开放其它访问者

概念辨析
--------

* **Direct I/O 与同步 I/O**：Direct 描述缓存路径；同步描述调用者是否等待请求完成。
* **Direct I/O 与持久化**：设备传输完成不自动等于易失缓存已刷新，也不等于应用事务完成。
* **用户虚拟地址与 DMA 地址**：应用提供虚拟 buffer；内核仍需页固定和设备地址映射。
* **绕过 Page Cache 与绕过所有缓存**：控制器、设备、虚拟块层、服务器和应用缓存仍可存在。
* **提交完成与 buffer 可复用**：异步提交成功只表示请求被接受；completion 才结束内核对 buffer 的使用。
* **缓存污染减少与内存成本减少**：少用 Page Cache 可降低缓存占用，长期 pin 和在途池仍可能占用大量内存。

本章结论
--------

Direct I/O 用严格对齐、用户页生命周期和应用自管缓存换取较少的 Page Cache 参与。它改变的是数据路径，不会消除文件系统事务、设备队列、一致性和持久化责任。
