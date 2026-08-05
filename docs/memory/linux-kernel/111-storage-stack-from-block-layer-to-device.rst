第111章：从块层到设备的存储栈
===============================

本章必须记住
------------

#. Linux 存储栈的稳定模型是分层块翻译：上层表达文件或块语义，下层逐步把请求变成设备协议命令。
#. 一次普通存储路径可以表示为：文件系统/Direct I/O → ``bio`` → 虚拟块层 → ``request`` → blk-mq → 驱动 → 控制器与介质。
#. 每一层都可能改写目标设备和 sector、拆分或复制请求、增加排队、附加持久化标志、重试失败请求或转换完成状态。
#. 分析问题时必须先画出真实设备拓扑，再分析某一层的性能或错误；只看最上层 ``/dev`` 名称通常不够。
#. ``struct bio`` 描述块设备、sector、操作、页片段和完成回调，是层间传递数据移动需求的基础对象。
#. ``struct request`` 是块层调度、tag、blk-mq 和驱动更接近的执行单位，可以承载一个或多个 ``bio``。
#. ``request_queue`` 是一个块设备对上的提交与能力边界，保存设备限制、调度器和 blk-mq 状态。
#. 驱动的 ``queue_rq`` 一类回调把 block request 翻译成 NVMe、SCSI、SATA、virtio 或其它协议命令。
#. 文件系统仍负责解释文件 offset、extent、日志、COW 和元数据顺序；块层不会重新理解这些文件语义。
#. Device Mapper、MD RAID、loop、NBD、zram 等也表现为块设备，但它们的请求会被转换或转发到其它对象。
#. 物理块设备背后有真实控制器和介质；虚拟块设备主要通过映射、加密、复制、缓存或远端传输执行请求。
#. 判断设备类型不能只看名称，应检查 ``slaves``、``holders``、major/minor、驱动和映射表。
#. ``/sys/block/<dev>/slaves/`` 表示该上层设备依赖的下层块设备；``holders/`` 表示持有该设备的上层设备。
#. Device Mapper target 可以把一个上层 ``bio`` 克隆成一个或多个下层 ``bio``，并改写目标设备与 sector。
#. RAID 写可能扩展为多成员数据、镜像或校验请求；一个上层完成要等待所需子请求收束。
#. Loop 设备把块请求转换成普通文件 I/O；NBD 把块请求转换成网络协议；zram 在内存中压缩存储数据。
#. 因此块设备路径不必最终到本机物理盘，也可能终止于文件、网络、内存或虚拟机后端。
#. 存储路径中存在多种不同缓存，必须分别命名和解释。
#. Page Cache 缓存文件数据和元数据对象；普通 buffered write 返回时数据通常仍只在内存脏页中。
#. 块层软件队列缓存的是待执行的 request，而不是另一个独立文件数据副本。
#. 控制器和设备 write-back cache 可以在数据进入非易失介质前报告命令完成。
#. RAID 控制器、SAN、虚拟化后端、dm-cache 和远端服务还可能加入额外缓存层。
#. “请求完成”只能按报告它的层级解释；Page Cache 写入完成、块 request 完成和稳定介质完成是不同承诺。
#. Direct I/O 可绕过普通 Page Cache 数据路径，不能绕过文件系统元数据、块队列、控制器缓存和设备内部缓存。
#. Flush 与 FUA 用于把上层持久化要求表达给下层；所有中间层必须正确传播、转换或模拟该语义。
#. 上层文件系统的崩溃一致性依赖最终设备真实兑现 flush/FUA 和写入顺序。
#. 设备声称支持某项能力不等于所有桥接器、控制器和虚拟化后端都正确实现，可靠性要结合实际栈验证。
#. 存储错误可能来自上层映射、块层资源、驱动、传输链路、控制器、介质或远端服务。
#. ``blk_status_t`` 在块层表达完成状态，上层再把它转换为 errno、folio error、mapping error 或文件系统错误策略。
#. 同一个底层错误可能被重试后隐藏，也可能最终导致 I/O 失败、设备离线、文件系统只读或强制 shutdown。
#. Timeout 表示请求在指定时间内没有到达期望完成点，不自动说明介质永久损坏。
#. Timeout 处理可能依次尝试 abort、queue reset、device reset、bus/controller reset、path failover 或请求重试。
#. Reset 是控制面恢复动作，通常影响多个队列和大量在途请求，而不是只影响触发超时的一个请求。
#. Reset 期间新请求可能被停止、排队、requeue 或失败；应用看到的是整个恢复窗口的尾延迟放大。
#. Retry 会延长请求生命周期并可能改变完成顺序；不能用最终成功掩盖大量重试造成的服务退化。
#. 重试只适用于幂等或协议允许的操作；写请求是否已经部分执行必须由驱动和设备状态判断。
#. 路径切换适用于多路径存储；它改变到同一逻辑设备的传输路径，不等于修复底层数据内容。
#. 多路径层必须区分瞬时路径失败、目标设备失败、队列拥塞和永久不可达。
#. 设备被 offline 或 removed 后，原有 fd、mount 和上层虚拟设备可能仍存在，但后续 I/O 会失败或阻塞在清理路径。
#. 热拔插与设备消失涉及 gendisk、request queue、驱动引用、打开对象和文件系统 teardown，不能只删除 ``/dev`` 节点。
#. 存储完成路径通常是：设备 completion → 驱动定位命令/tag → 完成 request → 完成 bio → 上层回调。
#. Block completion 不表示提交任务已经获得 CPU；还可能等待 softirq、workqueue、任务唤醒和调度。
#. 同一个请求可在一个 CPU 提交、另一个 IRQ CPU 完成，再唤醒第三个 CPU 上的任务。
#. NUMA 拓扑、PCIe root、buffer node、提交 CPU、hctx 和 IRQ affinity 会共同影响尾延迟。
#. 设备性能标签不能替代路径分析；NVMe 设备也可能受 dm-crypt、thin pool、虚拟化和错误恢复限制。
#. 旋转盘更关注寻道、合并和调度；高速 NVMe 更容易暴露队列、tag、IRQ 和 CPU 局部性问题。
#. 虚拟设备的 queue limits 通常是下层能力的组合结果，可能被最弱层限制，也可能因 target 语义进一步收紧。
#. ``max_sectors``、segment、discard、write zeroes、zoned、flush/FUA 等能力必须沿层级确认。
#. 一个上层大请求可能因任一层限制被多次 split，形成明显命令放大和 CPU 开销。
#. 一个上层 flush 可能被传播到多个成员设备，形成同步写尾延迟放大。
#. 一个底层设备故障可能让上层 RAID 降级运行、thin pool 进入只读/错误模式或 dm 设备暂停。
#. Device Mapper suspend 用于切换表或执行管理动作，暂停窗口内 I/O 可能排队，不能误判为介质慢。
#. 文件系统看到 ``EIO`` 时，实际错误可能源于它下方任意层；必须沿设备图向下查日志和状态。
#. ``lsblk`` 适合建立设备树；``dmsetup table/status`` 适合查看 dm target；``mdadm``、LVM 工具和协议工具提供各层状态。
#. ``findmnt`` 与目标进程 ``mountinfo`` 用于把文件路径定位到具体文件系统和可见块设备。
#. ``udevadm``、sysfs 和设备模型能说明当前对象关系，不能单独证明某次请求实际经过的运行分支。
#. ``iostat`` 和 diskstats 提供设备级聚合，分层设备可能在上层和下层重复计数同一逻辑工作。
#. Block trace 的 remap/clone 事件可以帮助连接上层虚拟请求与下层物理请求。
#. 只追最上层设备会把下层服务时间隐藏在虚拟层后；只追最下层设备又会丢失上层业务来源和映射关系。
#. 正确追踪要选定同一时间窗口，同时采集上层提交、映射层 remap、下层 issue/complete 和上层 completion。
#. ``comm`` 可能是 writeback worker、dm worker、中断线程或 kworker，不一定是最初发起 I/O 的应用。
#. 错误日志必须按时间排序，并关联设备号、namespace/LUN、controller、path 和 reset generation。
#. “设备恢复正常”应由新请求成功、队列重新运行、错误计数停止增长和业务恢复共同证明。
#. 可靠性分析的核心不是某个 API，而是每层对地址、顺序、完成、错误和持久化作出的承诺是否一致。
#. 最稳定阅读顺序是：文件系统/上层块设备 → 映射关系 → request queue → blk-mq → 协议驱动 → 控制器/介质 → completion。
#. 精确函数名、target fast path、协议状态机和错误恢复顺序具有版本、驱动和设备差异。

必背路径
--------

分层写入：

::

   文件系统 writeback / Direct I/O
   → 构造上层 bio
   → 目标为 dm/RAID 等虚拟设备
   → 查映射表并 clone/split/remap
   → 下层 request_queue
   → blk-mq request 与 tag
   → 协议驱动 queue_rq
   → 控制器和设备
   → completion 逐层返回

建立设备拓扑：

::

   从文件路径确定 mount
   → 找到上层块设备 major/minor
   → lsblk 查看父子关系
   → sysfs slaves/holders 验证依赖
   → dmsetup/LVM/MD 工具展开映射
   → 找到最终 NVMe/SCSI/远端/文件后端
   → 记录每一层 queue 和缓存能力

Timeout 与恢复：

::

   request 长时间未完成
   → blk-mq/协议 timeout 回调
   → 判断命令和设备状态
   → 尝试 abort 或重试
   → 必要时停止 queue
   → reset path/controller/device
   → 重新建立队列或切换路径
   → 重放/失败在途请求
   → 向上层报告最终状态

检查持久化承诺：

::

   应用请求 fsync/事务提交
   → 文件系统产生数据、元数据和顺序要求
   → 块层附加 PREFLUSH/FUA/FLUSH
   → 每个 dm/RAID/cache 层传播或模拟
   → 驱动翻译成协议命令
   → 最终设备确认稳定状态
   → 完成逐层返回
   → 应用才能建立崩溃恢复假设

定位 EIO：

::

   保存应用 errno 与文件系统日志
   → 定位上层块设备
   → 展开映射和成员设备
   → 检查 block error/remap/requeue
   → 检查协议状态和 sense/NVMe status
   → 检查 timeout/reset/path failover
   → 判断瞬时恢复或永久故障
   → 验证数据与文件系统一致性

必须区分
--------

物理块设备与虚拟块设备
   前者由控制器和介质执行；后者把请求映射、转换或转发到其它对象。

Page Cache 与设备写缓存
   前者位于内核文件路径；后者位于控制器或设备内部，持久化语义不同。

Block completion 与稳定持久化
   Request 完成符合当前命令语义；只有正确的 flush/FUA 与设备兑现才能支持断电后仍存在。

Timeout 与永久介质错误
   Timeout 是未按时完成的状态；原因可以是拥塞、路径、固件、reset 或介质故障。

Retry 与新请求
   Retry 延续原请求的完成责任；新请求拥有新的身份、顺序和生命周期。

上层设备统计与下层设备统计
   分层设备可能重复表示同一逻辑 I/O 的不同阶段，不能直接相加解释业务字节。

一句话结论
----------

Linux 存储栈是一组分层块翻译和承诺，只有地址映射、错误恢复、完成与持久化语义沿所有虚拟层传到最终设备，上层文件系统的可靠性才成立。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 23，Storage Devices, NVMe, SCSI, Device Mapper, and Filesystem Reliability；
* AIBook 章节：Chapter 111，Storage Stack from Block Layer to Device；
* 源文件：``docs/LinuxK/Part_23_Storage_Devices_NVMe_SCSI_Device_Mapper_and_Filesystem_Reliability/Chapter_111_Storage_Stack_from_Block_Layer_to_Device.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_23_Storage_Devices_NVMe_SCSI_Device_Mapper_and_Filesystem_Reliability/Chapter_111_Storage_Stack_from_Block_Layer_to_Device.md>`_。