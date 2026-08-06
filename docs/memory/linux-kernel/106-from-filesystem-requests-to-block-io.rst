第106章：从文件系统请求到块 I/O
================================

本章必须记住
------------

#. 通用块层位于文件系统、Direct I/O、Swap、Device Mapper 与块设备驱动之间，统一组织面向块设备的数据移动工作。
#. 用户态文件 I/O 首先表达文件名、fd、文件 offset 和字节长度；进入块层前，具体文件系统必须先完成文件范围到后端块范围的映射。
#. 块层主要处理目标块设备、起始 sector、长度、内存页片段、操作类型和请求标志，不再解释目录名和文件业务含义。
#. 文件语义转换为块设备语义的稳定主线是：文件 offset → 文件系统逻辑范围 → extent/block mapping → 块设备 sector → ``bio``。
#. ``struct file`` 和 ``struct inode`` 仍携带打开实例和文件对象语义；``struct bio`` 已主要携带块设备数据移动语义。
#. ``struct block_device`` 表示某个块设备或分区的内核对象，连接设备号、磁盘对象、分区范围和请求队列。
#. ``struct request_queue`` 是该块设备的通用提交边界，集中保存队列限制、调度状态、blk-mq 映射和驱动接口。
#. ``submit_bio()`` 是大量上层块 I/O 提交会经过的公共入口之一，具体调用层次和 helper 随版本变化。
#. 并非所有文件操作都会进入本地块层；tmpfs、procfs、网络文件系统和特殊设备可能在其它路径完成。
#. 文件 offset 的单位是字节，表达文件内部位置，与文件在后端的物理布局没有固定一一对应关系。
#. 文件系统逻辑块或 extent 是文件系统用于组织文件数据和元数据的映射单位，大小与布局由具体文件系统决定。
#. Linux 块层的 ``sector_t`` 地址长期以 512 字节 sector 为计数单位；设备报告的 logical block size 可以大于 512 字节。
#. “块层 sector 以 512 字节计数”不表示设备能接受任意 512 字节 I/O；请求仍须满足 logical/physical block、对齐和队列限制。
#. 块层看到的 sector 通常仍是该 Linux 块设备抽象下的逻辑地址，不是 SSD 闪存页或磁盘介质的最终物理位置。
#. 分区、LVM、dm-crypt、RAID、thin provisioning、虚拟磁盘和控制器固件都可能继续重映射块层 sector。
#. 相邻文件 offset 不保证后端 sector 相邻；碎片、洞、COW、压缩、快照和多设备布局都会改变映射。
#. 文件洞的读可以直接返回零而不提交设备读；向洞写入通常要求先分配空间并更新元数据。
#. Buffered write 通常先修改 Page Cache 并标记 dirty，真正块 I/O 在 writeback、fsync、内存压力或文件系统策略触发后产生。
#. Buffered read miss 需要文件系统把目标文件范围映射到后端，提交读 ``bio``，完成后再把 folio 标记为可用。
#. Direct I/O 不经过普通 Page Cache 数据缓存，但仍须由文件系统完成 offset 映射、空间分配、COW、日志和块层提交。
#. 文件系统元数据更新也会产生块 I/O；创建、truncate、rename、extent tree、位图和日志提交可能生成独立请求。
#. 同一应用写操作可能对应数据 ``bio``、元数据 ``bio``、journal ``bio``、flush 和 FUA 等多类设备工作。
#. 因此看到多个块写请求时，不能只按用户写入字节数解释，还要识别数据、元数据和持久化顺序。
#. Swap I/O 也使用块层，但其上层语义是匿名页换入换出，不是普通文件读写。
#. Device Mapper target 可以克隆或重映射 ``bio``，改变目标设备、sector、加密或冗余关系，同时保留上层完成链。
#. 分层块设备会让一次上层 ``bio`` 变成多个下层 ``bio``；完成通常要等所有必要子请求收束后再返回上层。
#. 块层可以合并相邻兼容 I/O，也可以按设备限制拆分过大的 I/O；上层请求数量不等于设备命令数量。
#. 最大 sectors、segment 数、segment boundary、DMA 对齐、discard、zone 和 atomic write 等限制会影响拆分。
#. 块层合并和拆分只改变设备工作形状，不重新解释文件内容的业务意义。
#. 请求进入块层后仍保留操作语义，如 READ、WRITE、FLUSH、DISCARD、WRITE_ZEROES 或 ZONE_APPEND；可用操作取决于设备与版本。
#. ``REQ_PREFLUSH``、``REQ_FUA`` 等标志表达持久化排序要求，具体下传与实现由文件系统、块层、驱动和设备共同决定。
#. Flush 用于要求先前易失写缓存达到相应稳定点；FUA 用于要求相关写以强制单元访问语义完成，支持能力必须从设备确认。
#. ``write()`` 返回、writeback 完成、块请求完成和设备稳定持久化不是同一个时间点。
#. 文件系统必须把数据与元数据顺序要求转换成块操作和标志；块层不会自动理解应用事务。
#. 块请求完成通常通过 ``bio`` 或 ``request`` 的完成路径把状态逐层传回文件系统、Page Cache、Direct I/O 或 Swap 调用者。
#. 设备错误在块层常使用 ``blk_status_t`` 表达，再由上层转换为 errno、mapping error 或页面状态。
#. 一个下层错误可能导致部分 ``bio`` 失败、文件系统强制 shutdown、只读重挂载或后续 fsync 报错，具体策略由上层决定。
#. 请求成功完成只表示该块操作满足当前完成语义，不证明应用数据结构、文件系统事务或跨设备事务整体成功。
#. 块设备是按 sector/逻辑块随机访问的抽象；真实设备可以是旋转磁盘、SSD、NVMe、远端设备或虚拟映射。
#. 对旋转介质，顺序性与寻道影响显著；对高速多队列设备，软件队列、tag 和 CPU 亲和性更容易成为瓶颈。
#. 块层的统一抽象允许上层不直接依赖 NVMe/SCSI 命令格式，但设备特性仍通过 queue limits 和驱动能力向上传播。
#. ``/sys/block/<dev>/queue`` 暴露队列能力和策略，具体文件集合依设备、配置和内核版本而异。
#. ``logical_block_size``、``physical_block_size``、``max_sectors_kb``、``max_segments`` 和 discard 属性可帮助解释请求形状。
#. 从文件路径定位到块设备时，应结合 mountinfo、文件系统、设备号和可能的 Device Mapper 层，而不是只看文件名。
#. ``findmnt``、``lsblk``、``/sys/dev/block`` 和 ``/proc/<pid>/mountinfo`` 分别提供挂载、设备拓扑和命名空间证据。
#. 同一容器路径可能映射到宿主机不同 mount 与块设备，必须从目标进程的 mount namespace 取证。
#. ``strace`` 能看到文件 syscall、offset、长度和返回值，不能直接证明映射到了哪些 sector。
#. 文件系统 tracepoint、iomap/extent 证据可连接文件 offset 与后端范围；块 tracepoint可观察后续 ``bio/request`` 生命周期。
#. 请求没有进入本地块层不表示 I/O 没发生，可能命中 Page Cache、走网络文件系统、DAX、tmpfs 或设备专用路径。
#. 块层出现大量 I/O 不表示应用主动发起同等数量请求，可能来自 readahead、writeback、journal、reclaim 或 filesystem scrub。
#. 调试时应先确定 I/O 类型：Buffered read miss、Buffered writeback、Direct I/O、metadata、Swap 还是 Device Mapper 子请求。
#. 然后沿对象转换追踪：``file/inode`` → ``address_space/iomap`` → ``block_device`` → ``bio`` → ``request_queue`` → 驱动。
#. 最稳定源码阅读顺序是：VFS 操作 → 文件系统映射 → ``submit_bio`` → 队列限制/拆分 → request/blk-mq → 驱动完成。
#. 稳定模型是“文件系统解释文件，块层组织设备工作”；精确函数名、tracepoint 和队列实现属于版本敏感细节。

必背路径
--------

Buffered write 进入块层：

::

   write 修改 Page Cache
   → folio 标记 dirty
   → writeback 选择文件范围
   → 文件系统把 offset 映射到 extent/block
   → 构造写 bio
   → submit_bio
   → request_queue / blk-mq
   → 块驱动与设备
   → completion 返回文件系统和 folio

Buffered read miss：

::

   read 查找 Page Cache 未命中
   → 建立并锁定目标 folio
   → 文件系统查找 extent/block mapping
   → 洞则填零
   → 有后端块则构造读 bio
   → 设备完成
   → folio 标记 uptodate 或 error
   → 唤醒等待者并复制给用户

Direct I/O：

::

   用户提交对齐 buffer 与文件 offset
   → VFS 构造 kiocb / iov_iter
   → 文件系统检查 Direct 能力
   → pin 用户页
   → 映射文件 extent
   → 构造一个或多个 bio
   → 块层拆分/合并并提交
   → completion
   → 解除 pin 并返回 CQE/系统调用结果

分层块设备：

::

   上层 bio 指向 dm/LVM/RAID 设备
   → target 解释映射表
   → clone 或拆分 bio
   → 改写下层 block_device 与 sector
   → 提交一个或多个子 bio
   → 汇总子请求状态
   → 完成原上层 bio

定位文件到块请求：

::

   确认目标进程 mount namespace
   → 路径解析到 mount 与 filesystem
   → 找到后端 block device / device mapper 栈
   → 识别文件 offset 与 I/O 类型
   → 文件系统 mapping/extent 证据
   → block bio/request trace
   → 驱动和设备完成证据

必须区分
--------

* 文件 offset 与块设备 sector：前者表示文件内部字节位置；后者表示某块设备抽象中的逻辑扇区范围。
* 文件系统逻辑块与设备 logical block：文件系统用自己的块/extent 管理文件；设备报告可寻址和对齐的逻辑块能力。
* Buffered write 返回与块 I/O 提交：Buffered write 常先修改内存；块提交可以在稍后的 writeback 或同步点发生。
* 数据 I/O 与元数据 I/O：同一文件操作可能同时产生文件数据、inode、extent、journal 和 flush 请求。
* 上层 ``bio`` 与下层设备命令：Bio 是块层数据移动描述；它还可能被映射、拆分、合并后才形成驱动命令。
* 块请求完成与业务持久化：Request completion满足当前块操作语义；应用事务和文件系统恢复保证仍需上层协议证明。

一句话结论
----------

文件系统先把文件范围翻译成块设备 sector 和数据页片段，通用块层再以 ``bio``、队列和 request 把这些结果组织成驱动能够执行的设备工作。
