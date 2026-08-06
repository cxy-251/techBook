第112章：SCSI 与传统存储模型
=============================

本章必须记住
------------

#. SCSI 在 Linux 中首先是一套命令型存储架构，不等于某一种旧线缆或某一类老硬盘。
#. SCSI 模型把存储访问组织为 initiator 向 target 的某个 LUN 发送命令，设备返回状态和 sense data。
#. 同一抽象可承载 SAS、Fibre Channel、iSCSI、USB Mass Storage，以及部分经 libata 接入的 ATA 设备。
#. 块层表达 sector 范围和数据移动；SCSI 层把 block request 翻译成协议命令与 CDB。
#. ``struct scsi_cmnd`` 是一次 Linux SCSI 命令对象，连接 CDB、数据缓冲区、超时、重试、状态和 sense buffer。
#. Block request 表达上层块 I/O；``scsi_cmnd`` 表达实际提交给 SCSI target 的协议命令。
#. CDB 是 SCSI Command Descriptor Block，包含操作码、LBA、传输长度和控制字段。
#. SCSI 命令完成后返回 status；失败时 sense key、ASC、ASCQ 提供结构化故障原因。
#. Sense data 是错误恢复策略的输入，不只是打印给人的日志文本。
#. 常见 sense key 只能表示错误大类；最终判断必须结合 ASC/ASCQ、命令类型和设备状态。
#. Unit Attention 常表示设备状态发生变化，不自动等于永久介质损坏。
#. Not Ready 可能来自设备初始化、路径不可用、介质缺失或控制器恢复中。
#. Medium Error 更接近介质读取或写入失败，仍需结合 LBA、重试和阵列冗余判断影响范围。
#. Illegal Request 常表示命令、字段或能力不被目标接受，不应直接解释为硬件坏盘。
#. Aborted Command、Hardware Error、Data Protect 等各自对应不同恢复与上报方向。
#. Linux SCSI 栈可分为块层、SCSI upper layer、midlayer 和 low-level driver。
#. SCSI disk 驱动把磁盘类 ``scsi_device`` 暴露为 ``/dev/sdX`` 块设备。
#. Midlayer 负责命令生命周期、通用设备状态、队列控制、设备发现和错误恢复。
#. Low-level driver 负责具体 HBA、DMA、传输协议、硬件队列和完成中断。
#. ``struct Scsi_Host`` 表示一个主机适配器或软件 initiator 实例。
#. ``struct scsi_device`` 表示 host 上发现的某个 target/LUN 设备。
#. ``struct scsi_host_template`` 是 low-level driver 向 midlayer 提供的操作与能力表。
#. ``queuecommand`` 是普通命令提交的重要回调；精确签名和调度方式具有版本差异。
#. ``eh_abort_handler``、device reset、target/bus reset、host reset 等回调属于错误恢复控制面。
#. 驱动 probe 后通常先注册 ``Scsi_Host``，再扫描 target/LUN，最后由 upper layer 创建块设备。
#. ``scsi_host_alloc()``、``scsi_add_host()`` 和 ``scsi_scan_host()`` 是理解发现路径的常见源码锚点。
#. Host、SCSI device 和 block disk 是同一存储路径在不同子系统中的对象投影。
#. ``/sys/class/scsi_host/hostN`` 展示 host 视角，``/sys/class/scsi_device/H:C:T:L`` 展示 SCSI 地址视角。
#. ``/sys/block/sdX`` 展示最终块设备视角，不能用一个对象替代全部层级。
#. H:C:T:L 中的 host、channel、target、LUN 是 Linux SCSI 地址，不应机械推断物理机箱位置。
#. 企业阵列可通过多个 target port 暴露同一 LUN，从而形成多路径。
#. Tagged queueing 允许一个设备同时处理多条命令；queue depth 决定并发命令上限之一。
#. Block layer queue depth、SCSI device queue depth、HBA command slots 和阵列内部队列是不同层级。
#. Host busy、device busy、target busy 和 block tag shortage 不能混为一种排队问题。
#. 设备返回 QUEUE FULL 或 TASK SET FULL 时，midlayer/驱动可能动态收缩 queue depth。
#. 队列深度过低会浪费阵列并行能力，过高会放大排队与尾延迟。
#. 一次命令超时不自动立即失败给上层，可能先进入 SCSI EH。
#. 普通完成路径通常由 low-level driver 调用完成接口，把 ``scsi_cmnd`` 状态交回 midlayer。
#. Midlayer 根据 result、host byte、status byte 和 sense 判断成功、重试、requeue 或 EH。
#. SCSI EH 通常在专门错误处理线程中串行恢复相关 host/device 的命令。
#. EH 期间设备或 host 的正常命令队列可能被阻塞，导致多个无关 I/O 同时出现长尾延迟。
#. 恢复动作通常从较小范围开始：命令 abort → device/target reset → bus reset → host reset。
#. 具体层级、跳过条件和驱动实现取决于传输类型和内核版本。
#. Reset 会影响多个在途命令，并可能导致设备重新发现、容量重读和 Unit Attention。
#. Reset 成功只表示控制通路恢复，不自动证明所有原数据完整或性能恢复。
#. 命令重试可能让最终 I/O 成功，但日志中的 retry、reset 增长仍是退化证据。
#. 不可重试错误最终会转换为 block error，可能上报 ``EIO``、文件系统错误或设备离线。
#. SCSI 设备 offline 表示 midlayer 不再正常向其提交命令；对应 ``sdX`` 节点仍可能短暂存在。
#. 删除设备前必须收束打开引用、块队列和上层文件系统，不能只操作 sysfs delete。
#. Request Sense 与自动 sense 返回是协议与驱动细节；稳定结论是 sense buffer承载失败分类。
#. Sense 日志必须同时记录失败 CDB、LBA、sense key、ASC/ASCQ、host、target、LUN 和恢复动作。
#. 只截取 ``I/O error, dev sdX`` 会丢失最有价值的 SCSI 错误上下文。
#. Multipath 把多个传输路径组合成同一逻辑设备，通常由 device mapper multipath 等层提供上层块设备。
#. Path 是到 target/LUN 的传输通道；LUN 是逻辑存储对象；两者不能混为同一设备。
#. 单路径失败时，多路径层可以将新 I/O 切换到其它健康路径。
#. Path failover 不自动修复目标 LUN 内的数据错误；介质错误可能在所有路径上同样出现。
#. 多路径策略可能按 round-robin、service time、queue length 等方式选路，具体策略依配置。
#. Queue-if-no-path 会在所有路径不可用时排队 I/O，可能造成应用长期挂起，必须明确恢复策略。
#. Fail-if-no-path 会更快向上报错，避免无限等待，但要求应用和文件系统能够处理错误。
#. Fibre Channel、iSCSI、SAS 等传输各有链路登录、session、target port 和重连状态。
#. iSCSI 慢可能来自网络、session 重连、target、阵列后端或 SCSI queue，不能只看块设备 await。
#. SAN 阵列缓存、控制器故障切换和 ALUA 状态会影响路径优先级与命令延迟。
#. ALUA 的 optimized/non-optimized path 表示访问状态差异，不等于路径是否物理可达。
#. ``lsscsi``、sysfs、multipath 工具和内核日志用于建立 host-target-LUN-path 关系。
#. ``sg_inq``、``sg_logs`` 等工具可读取设备协议信息，使用时应避免对生产设备发送破坏性命令。
#. ``smartctl`` 经 SCSI/SAT 时看到的是桥接后的健康信息，字段能力取决于设备和传输。
#. ``iostat`` 聚合到块设备，无法解释 sense、path failover 和 EH 内部状态。
#. Block trace 能观察 request issue/complete/requeue；SCSI trace 和日志用于补充 command 与 sense。
#. ``comm`` 可能显示 EH thread、kworker 或中断上下文，不代表最初发起 I/O 的进程。
#. 诊断慢 I/O 时应先区分 block queue wait、SCSI command service、EH recovery 和 multipath queueing。
#. 诊断设备消失时应按 PCI/HBA → Scsi_Host → target/session → LUN → sdX → multipath/dm 的顺序检查。
#. 诊断介质错误时应保存受影响 LBA、重试结果、阵列冗余状态和文件系统对应范围。
#. SCSI 的持久价值来自稳定的命令、对象、状态和错误模型，而不是某种特定物理接口。
#. 最稳定源码阅读顺序是：``Scsi_Host`` → ``scsi_device`` → block request → ``scsi_cmnd`` → ``queuecommand`` → completion/EH。
#. 精确 result 位编码、sense helper、EH 状态机和传输实现属于版本与驱动敏感细节。

必背路径
--------

普通 SCSI I/O：

::

   文件系统/块层形成 request
   → SCSI disk 与 midlayer 准备 scsi_cmnd
   → 构造 CDB、SG 和超时信息
   → low-level driver queuecommand
   → HBA/传输发送给 target/LUN
   → 设备返回 status/sense
   → midlayer 判断 disposition
   → 完成 block request 或进入重试/EH

设备发现：

::

   HBA/软件 initiator 驱动 probe
   → scsi_host_alloc
   → scsi_add_host
   → 扫描 target 和 LUN
   → 创建 scsi_device
   → SCSI disk upper layer 绑定
   → 注册 gendisk
   → 出现 /dev/sdX

错误恢复：

::

   命令失败或 timeout
   → 解析 result 与 sense
   → 可立即重试则 requeue/retry
   → 需要恢复则冻结相关命令
   → abort command
   → device/target/bus/host reset
   → 重新验证设备状态
   → 重试或最终失败
   → 解冻 queue 并完成上层请求

多路径故障：

::

   某条 path I/O 失败
   → SCSI/传输层报告 path error
   → multipath 标记路径状态
   → 选择其它 active path
   → requeue 未完成 I/O
   → 新路径提交同一 LUN
   → 验证业务恢复和旧路径状态

分析 sense：

::

   保存完整内核日志
   → 确认 host:channel:target:lun 和 sdX
   → 识别失败 CDB 与 LBA
   → 读取 sense key
   → 读取 ASC/ASCQ
   → 检查 retry/reset/offline
   → 对照传输和阵列状态
   → 判断瞬时、路径、介质或能力错误

必须区分
--------

* SCSI 协议模型与物理接口：SCSI 是命令、目标、LUN 和错误模型，可运行在多种传输之上。
* Block request 与 ``scsi_cmnd``：前者表达块层工作；后者表达发送给 SCSI target 的协议命令。
* Sense data 与 errno：Sense 是设备级结构化原因；errno 是上层最终看到的压缩错误结果。
* Timeout 与 Medium Error：Timeout 表示未按时完成；Medium Error 更明确指向介质访问失败。
* Path 与 LUN：Path 是到存储对象的传输路线；LUN 是被访问的逻辑对象。
* Reset 恢复与数据正确：Reset 恢复命令通路；数据是否完整仍需由命令状态、阵列和文件系统验证。

一句话结论
----------

Linux SCSI 栈用 ``Scsi_Host``、``scsi_device``、``scsi_cmnd`` 和 sense/EH 模型，把统一块请求连接到多种企业存储传输，并以结构化状态决定重试、重置、切换路径或失败。
