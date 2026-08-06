第114章：Device Mapper、LVM、RAID 与分层块设备
==============================================

本章必须记住
------------

#. Device Mapper 是 Linux 内核中的虚拟块设备框架，接收上层块 I/O，并按映射表交给一个或多个 target 处理。
#. 映射表决定虚拟 sector 范围由哪个 target 负责；target 决定怎样改写、复制、缓存、加密或转发请求。
#. 一个 dm 设备对上表现为普通块设备，对下持有一个或多个底层块设备。
#. 文件系统通常不知道 dm 设备下方的具体组合，只看到它报告的容量、queue limits 和块语义。
#. ``drivers/md/dm.c``、``dm-table.c`` 和 ``struct target_type`` 是理解 device mapper 的常见源码入口。
#. Target 通过 ``map``、constructor、destructor、status、message 等回调实现自己的映射和管理语义。
#. ``linear`` target 只改写目标设备和 sector 偏移，不提供冗余、不改变数据内容。
#. 多段 linear 映射可以把多个底层区间拼接成一个更大的虚拟设备。
#. ``striped`` target 按 chunk 把相邻逻辑范围轮转到多个成员设备，提高并行吞吐但不提供冗余。
#. 条带中任一成员永久丢失，会让虚拟地址空间的一部分数据不可恢复，除非上层另有冗余。
#. Mirror/RAID1 把同一逻辑数据写入多个副本，写完成通常需要满足 target 的副本完成策略。
#. RAID5/6 一类校验布局需要数据与 parity 更新，可能产生 read-modify-write、full-stripe write 和写放大。
#. RAID10 组合镜像与条带，读写并行、故障域和重建成本取决于布局。
#. Linux MD 与 dm-raid 都能提供 RAID 能力，但对象、管理工具和实现路径不同。
#. Device Mapper snapshot 使用 COW 设备保存 origin 被覆盖前的旧 chunk。
#. Snapshot 创建快，只建立映射关系；后续 origin 首次写入某 chunk 时才产生 COW 复制和元数据更新。
#. Snapshot COW 空间耗尽会使快照失效或进入错误状态，不能只看 origin 剩余空间。
#. Snapshot merge 会把快照差异重新应用到 origin，过程中性能和故障恢复语义需要单独管理。
#. Thin provisioning 把逻辑容量与实际物理分配分开，thin device 在写入时从 pool 分配块。
#. Thin pool 同时依赖 data device 和 metadata device；任一空间耗尽都可能导致 pool 降级、只读或错误模式。
#. Thin device 显示的逻辑剩余空间不能证明 thin pool data/metadata 仍有足够实际空间。
#. Thin snapshot 共享底层块，创建成本低；后续写入增加分配、元数据和共享引用成本。
#. Cache target 在快速 cache device 与 origin 之间维护热点数据和元数据。
#. Writethrough、writeback、passthrough 等模式具有不同完成和持久化承诺，必须按实际模式解释。
#. Writeback cache 中脏数据可能尚未到 origin，cache device 或 metadata 故障会影响数据恢复。
#. ``dm-crypt`` 在写入前加密、读取后解密，改变数据内容并增加 CPU、workqueue 和请求拆分成本。
#. Crypt target 不提供完整性或冗余，除非与 dm-integrity、verity、RAID 等其它机制组合。
#. 加密 sector size、IV 规则和 discard 配置会影响性能、兼容性和信息泄露边界。
#. ``dm-verity`` 提供只读数据完整性验证，通过哈希树检测数据块篡改或损坏。
#. Verity 能检测不一致，不提供通用可写更新或自动冗余修复。
#. ``dm-integrity`` 可提供块级完整性标签与写入日志，通常与 crypt 或 RAID 组合使用。
#. Device Mapper target 可以按 sector 范围修改地址，也可以克隆一个 bio 为多个下层请求。
#. 一个 target 可以同步完成请求，也可以把请求交给 workqueue、内部元数据 I/O 或下层设备异步完成。
#. 上层 bio 完成必须等待 target 规定的所有必要下层工作结束。
#. Target 只完成数据路径还不够，flush、FUA、discard、write zeroes、zoned 和 polling 语义也必须正确处理。
#. 某个 target 不支持某操作时，可能拒绝、模拟、拆分或屏蔽能力；上层 queue limits 必须反映组合结果。
#. 分层设备的最大 I/O 大小通常受所有下层最严格限制影响。
#. Alignment、discard granularity、optimal I/O size 和 zone 约束也会在多层组合中传播。
#. 一个大 bio 经过多层反复 split 会形成命令放大和额外 CPU/内存开销。
#. 上层 merge 不保证下层仍连续，target 重映射可能把一个连续范围拆到不同设备。
#. LVM 是用户空间管理层，维护 PV、VG、LV、segment 和元数据，并用 device mapper 表实现运行时逻辑卷。
#. PV 是 LVM 使用的底层块设备，VG 汇集可分配 extent，LV 从 VG 中取得逻辑 extent。
#. Physical extent 和 logical extent 是 LVM 元数据单位，不等于文件系统 extent 或块层 sector。
#. LVM 普通 linear LV 最终表现为若干 dm-linear segment。
#. LVM striped、raid、thin、snapshot、cache、crypt 组合最终由相应 dm target 和管理元数据实现。
#. 扩展 LV 只增加块设备容量；文件系统是否同时扩展需要单独执行或由工具显式协调。
#. 缩小 LV 风险更高，必须先确保上层文件系统和数据布局已经安全收缩。
#. LVM 元数据损坏会影响映射恢复；应保留 metadata backup、archive 和可验证的设备清单。
#. Device Mapper table 切换通常通过 suspend、加载新表、resume 完成。
#. Suspend 期间新 I/O 可能被暂存或阻塞，管理操作会造成业务延迟尖峰。
#. Table reload 是控制面变化，不应与普通数据路径映射混为同一操作。
#. ``dmsetup table`` 展示当前映射规则，``dmsetup status`` 展示 target 运行状态。
#. ``dmsetup table`` 对 crypt 等 target 可能涉及敏感信息，生产采集不得暴露密钥。
#. ``lsblk``、``pvs/vgs/lvs``、``mdadm`` 和 sysfs slaves/holders 用于建立完整设备图。
#. LVM 名称、``/dev/mapper`` 名称和实际 ``dm-N`` 设备号属于不同命名层。
#. RAID 降级表示冗余减少但设备可能仍可服务；必须立即判断剩余故障容忍度和重建风险。
#. Rebuild/resync 会占用成员设备带宽和队列，显著影响前台 I/O 尾延迟。
#. Rebuild 不是普通顺序复制，它还受 bitmap、校验、坏块、成员性能和负载影响。
#. RAID 写成功语义取决于布局和 target 策略，不能只看到某一个成员完成就认为上层写已完成。
#. Write hole 指数据与 parity 更新在崩溃时不一致的风险，日志、PPL、BBU 或全条带策略用于降低风险。
#. 硬件 RAID、MD RAID 和 dm-raid 的缓存、错误和重建语义不同，不能只按“RAID5”名称类比。
#. 分层错误会向上传播，也可能被冗余层吸收或转换。
#. 某个 mirror member 出错时，上层请求可能从另一个副本成功完成，同时记录成员降级。
#. 最终成功不表示底层健康；降级、校验错误和重试计数仍是关键可靠性证据。
#. Thin pool metadata 错误、snapshot overflow、cache metadata 故障和 crypt key 错误属于 target 自身故障，不是底层盘坏的同义词。
#. 所有成员设备正常也不能排除 target 元数据或映射表错误。
#. Flush 在 RAID、cache 和多成员 target 中可能需要传播到多个设备，成本高于单盘 flush。
#. 任一层错误屏蔽或错误实现 flush/FUA 都会破坏上层文件系统持久化保证。
#. 分层缓存会把“完成”分成 cache 完成、origin 完成、成员完成和最终稳定完成多个层级。
#. 上层 iostat 看到的是虚拟设备请求，下层设备也会记录对应子请求，不能简单相加。
#. 一个上层写可因 mirror/parity/cache/metadata 变成多个下层写，形成 I/O 放大。
#. 一个上层读可命中 dm-cache 而不访问 origin，也可因校验或重建访问多个成员。
#. Block remap tracepoint 能帮助连接上层 dm sector 与下层设备 sector。
#. Clone、split 和多成员请求会破坏一对一关联，复杂分析应按 bio/request identity 与层级建图。
#. 性能分析必须分别测 target CPU、target 内部等待、下层 queue wait 和设备 service time。
#. dm-crypt CPU 高应检查算法、加速、sector size、workqueue 与 NUMA，而不是只调块层 scheduler。
#. Thin 随机写延迟高应检查 metadata I/O、pool 空间、discard 和 snapshot 共享，而不是只看底层 await。
#. RAID 尾延迟高应检查成员长尾、校验路径、重建和 write intent 元数据。
#. Cache 命中率高也不自动表示持久化安全，writeback 脏块和 metadata 状态仍需单独验证。
#. 设备图发生变化后，应重新确认 mount 实际指向的 dm generation 和 table，而不是依赖旧名称。
#. 删除 dm/LV 前必须先卸载文件系统、停止上层引用、等待 I/O 和解除 holders。
#. 强制 remove 会把管理问题转换为上层 I/O 错误和潜在数据损坏。
#. 正确设计分层设备时，每新增一层都要明确地址、缓存、冗余、错误、flush、discard 和恢复语义。
#. 最稳定源码阅读顺序是：上层 dm device → table range → target ``map`` → clone/remap → 下层 queue → target completion/status。
#. 精确 target 参数、状态格式、RAID 算法和管理命令属于版本与工具敏感细节。

必背路径
--------

Device Mapper 提交：

::

   上层 bio 到达 dm 虚拟设备
   → 按虚拟 sector 查 dm table
   → 找到 target 实例
   → target map 检查操作与状态
   → 改写/clone/split bio
   → 提交一个或多个下层 block_device
   → 汇总子请求状态
   → 完成原上层 bio

LVM 到运行时设备：

::

   PV 提供 physical extents
   → VG 汇集空间
   → LV 分配 logical extents
   → LVM 元数据描述 segment
   → 用户空间生成 dm table
   → 内核创建 dm 设备
   → 文件系统挂载该虚拟块设备

Thin 写入：

::

   Thin device 收到未映射逻辑块写入
   → 查询 pool metadata
   → 从 data pool 分配物理块
   → 更新逻辑到物理映射
   → 提交数据 I/O
   → 持久化 metadata transaction
   → 完成上层请求

RAID 降级与重建：

::

   成员设备报告错误
   → RAID 标记成员 faulty/failed
   → 从剩余成员继续服务
   → 上层设备进入 degraded
   → 添加/选择替代成员
   → resync/rebuild 数据与校验
   → 监控坏块和前台延迟
   → 验证冗余恢复

展开性能放大：

::

   记录上层 dm 请求
   → 追踪 remap/clone/split
   → 统计每个 target 的子请求数
   → 对齐 metadata/cache/parity I/O
   → 追踪每个下层设备 queue/service
   → 区分 CPU、映射和介质成本
   → 调整布局或策略后复测

必须区分
--------

* Device Mapper 与 LVM：DM 是内核映射框架；LVM 是用户空间策略和元数据管理层。
* 映射表与 Target：Table 选择某段虚拟 sector 的处理者；target 定义实际转换语义。
* Thin 逻辑容量与 Pool 实际容量：Thin device 可显示很大逻辑空间；真正可写性取决于 data 和 metadata pool。
* Snapshot 与备份：Snapshot 共享故障域和底层数据，只提供时间点映射，不等于独立备份。
* RAID 冗余与数据备份：RAID 提高在线容错和可用性，不能替代离线、异地或版本化备份。
* 上层请求与下层工作量：一个逻辑 I/O 可被缓存、镜像、校验和元数据机制放大为多个子请求。

一句话结论
----------

Device Mapper 通过 target 把块设备能力组合成新的虚拟设备，LVM 与 RAID 提供策略、空间和冗余，但每增加一层都会同时增加地址、缓存、持久化、性能和故障传播复杂度。
