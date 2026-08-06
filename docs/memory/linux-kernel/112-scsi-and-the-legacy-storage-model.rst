第112章：SCSI 与传统存储模型
=============================

核心知识点
----------

SCSI 是命令架构而非某种旧接口
   SCSI 用 initiator、target、LUN、命令、状态和 sense data 组织存储访问，可运行在 SAS、Fibre Channel、iSCSI、USB Mass Storage 等多种传输上。

块请求会被转换成协议命令
   块层提供 sector、长度和数据缓冲区；SCSI 层把 ``struct request`` 转换为 ``struct scsi_cmnd`` 与 CDB，再交给 low-level driver。

三个核心对象表达不同层次
   ``Scsi_Host`` 表示主机适配器或软件 initiator，``scsi_device`` 表示某个 target/LUN，``scsi_cmnd`` 表示一次在途协议命令。

Midlayer 统一设备与命令管理
   SCSI midlayer 负责发现、排队、超时、重试、设备状态和错误恢复；low-level driver 负责 HBA、DMA、传输和硬件完成。

Sense data 是结构化故障证据
   Sense key 只给出错误大类，ASC/ASCQ、失败 CDB、LBA、host 状态和恢复动作共同决定错误含义。

队列深度具有多个层级
   块层 tag、SCSI device queue depth、HBA command slots 和阵列内部队列互不等价。任一层资源不足都可能形成等待。

Timeout 不直接等于 I/O 失败
   超时命令可能进入 SCSI EH，依次尝试 abort、device reset、target/bus reset 或 host reset，最后才决定重试或上报错误。

错误恢复会阻塞相关队列
   EH 常在专门线程中串行执行。恢复期间同一 host 或 device 上的其它正常命令也可能停顿，从而放大尾延迟。

Multipath 区分路径与存储对象
   多条 path 可以访问同一 LUN。Path failover 解决传输通道故障，不能修复 LUN 内部介质或数据错误。

最终 errno 会压缩协议细节
   用户态常只看到 ``EIO``，而根因可能是 sense、transport error、queue full、timeout、reset 或 path failure。诊断必须保留完整协议上下文。

关键路径
--------

普通 SCSI I/O：

::

   块层 request
   → SCSI upper layer
   → 构造 scsi_cmnd 与 CDB
   → low-level driver queuecommand
   → HBA / transport
   → target / LUN
   → status 与 sense
   → complete、retry 或 EH

设备发现：

::

   HBA 或软件 initiator probe
   → 创建 Scsi_Host
   → 扫描 target 与 LUN
   → 建立 scsi_device
   → SCSI disk upper layer 绑定
   → 注册块设备
   → 出现 /dev/sdX

错误恢复：

::

   命令 timeout 或失败
   → 解析 result 与 sense
   → 可恢复则 retry / requeue
   → 进入 SCSI EH
   → abort command
   → device / target / host reset
   → 重新验证设备
   → 完成或最终失败

多路径故障：

::

   某 path 报错
   → 传输层与 SCSI 层确认路径状态
   → multipath 标记 path
   → 选择其它可用 path
   → requeue 未完成请求
   → 验证同一 LUN 的服务恢复

概念辨析
--------

SCSI 模型与物理传输
   SCSI 定义命令与错误语义；SAS、FC、iSCSI 等负责传输这些命令。

Block request 与 ``scsi_cmnd``
   Request 是块层执行单位；``scsi_cmnd`` 是发往 target 的协议命令对象。

Sense data 与 errno
   Sense 提供设备级结构化原因；errno 是上层接口的压缩结果。

Timeout 与 Medium Error
   Timeout 表示未按时完成；Medium Error 更直接指向介质访问失败。

Path 与 LUN
   Path 是到存储对象的路线；LUN 是被访问的逻辑存储对象。

Reset 与数据正确性
   Reset 恢复命令通路和队列状态，不能证明在途写是否执行或数据是否完整。

本章结论
--------

Linux SCSI 栈用 Host、Device、Command 与 sense/EH 模型连接块层和多种企业存储传输；可靠诊断必须从协议状态还原重试、恢复与最终错误。
