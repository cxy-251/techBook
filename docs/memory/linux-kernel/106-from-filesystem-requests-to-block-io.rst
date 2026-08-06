第106章：从文件系统请求到块 I/O
================================

核心知识点
----------

块层承接已经完成文件语义翻译的工作
   文件系统解释路径、inode、文件偏移和 extent；块层接收目标块设备、sector、长度、内存片段与操作标志。块层不会重新解释目录名或文件业务含义。

文件偏移与设备 sector 属于不同坐标系
   文件偏移按字节描述文件内部位置，文件系统通过 extent、块映射或 COW 结构把它转换成块设备逻辑范围。块层 ``sector_t`` 通常以 512 字节为计数单位，但请求仍必须满足设备逻辑块、物理块和对齐限制。

``struct block_device`` 表示块设备视图
   它连接设备号、分区范围、磁盘对象和 ``struct request_queue``。该视图仍可能是 LVM、dm-crypt、RAID 或其它虚拟设备，而非最终物理介质。

``submit_bio()`` 是通用提交边界之一
   上层用 ``struct bio`` 描述块设备、sector、操作和数据页片段，再交给块层检查队列限制、执行拆分、合并、重映射与派发。

Buffered I/O 延迟生成块请求
   Buffered write 通常先修改 Page Cache 并标记 dirty，writeback、``fsync`` 或内存压力才触发块写；Buffered read 只有 Page Cache 未命中时才需要后端读入。

Direct I/O 仍需要文件系统映射
   Direct I/O 绕过普通文件数据缓存，不绕过 extent 查找、空间分配、COW、日志、块层限制和设备完成协议。

一次文件操作可以产生多类块工作
   用户数据、inode、extent、位图、journal、flush 和 FUA 可能形成独立请求。块请求字节数和数量不能直接等同于应用系统调用的字节数和次数。

分层设备会继续重映射请求
   Device Mapper、RAID 和虚拟块设备可 clone、split 或改写 ``bio`` 的目标设备与 sector。一个上层请求可能变成多个下层请求，完成必须按父子依赖聚合。

块完成不是业务持久化完成
   ``write()`` 返回、writeback 完成、块 request 完成、设备稳定写入和应用事务提交是不同边界。文件系统必须把顺序要求转换为 flush、FUA、日志与同步协议。

并非所有文件访问都会进入本地块层
   Tmpfs、procfs、网络文件系统、DAX、Page Cache 命中和特殊设备可能绕开本地块设备 request 路径。没有 block trace 不能直接推断没有 I/O 行为。

关键路径
--------

Buffered write 转换路径
~~~~~~~~~~~~~~~~~~~~~~~~

::

   write 修改 Page Cache
   → folio 标记 dirty
   → writeback 选择文件范围
   → 文件系统查找或分配 extent
   → 构造 write bio
   → submit_bio
   → request_queue / blk-mq
   → 驱动与设备
   → completion 回传 folio 和文件系统

Buffered read miss 路径
~~~~~~~~~~~~~~~~~~~~~~~

::

   read 查 Page Cache 未命中
   → 文件系统把文件 offset 映射到后端范围
   → 洞范围直接生成零值
   → 普通范围构造 read bio
   → 块层派发并等待完成
   → folio 标记 uptodate 或 error
   → 返回用户数据

分层块设备路径
~~~~~~~~~~~~~~

::

   上层 bio 指向虚拟块设备
   → target 查映射表
   → clone / split bio
   → 改写下层 block_device 与 sector
   → 提交子 bio
   → 聚合子请求状态
   → 完成原 bio

概念辨析
--------

文件偏移与设备 sector
   前者是文件内部字节位置；后者是某个块设备视图中的逻辑地址。两者由具体文件系统映射连接。

文件系统块与设备逻辑块
   文件系统块或 extent 服务文件布局；设备逻辑块规定设备可接受的寻址与对齐边界。

``bio`` 与设备命令
   ``bio`` 描述块数据移动需求；经过 merge、split、scheduler、blk-mq 和驱动后，才形成协议或控制器命令。

数据 I/O 与元数据 I/O
   同一系统调用可同时引起数据、日志、extent、inode 和持久化控制请求，不能只统计一种操作。

块完成与持久化
   Request completion 只满足当前块操作的完成合同；稳定介质、文件系统恢复与应用事务需要更高层协议证明。

本章结论
--------

文件系统负责把文件语义翻译成块设备范围，通用块层再把 ``bio`` 塑形成可排队、可重映射、可由驱动执行的设备工作。