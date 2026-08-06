第115章：可靠性、Flush、FUA、Barrier 与崩溃一致性
==================================================

本章必须记住
------------

#. 崩溃一致性讨论的是系统在任意断电、内核崩溃或控制器 reset 点之后，哪些已承诺状态仍可恢复。
#. 应用系统调用返回、文件系统事务提交、块 request 完成和设备稳定介质完成是不同层级的完成事件。
#. 可靠性必须围绕“哪一层已经作出什么承诺”分析，不能只看到 ``write()`` 或 request 成功就推断数据安全。
#. Buffered ``write()`` 成功通常表示数据已进入 Page Cache 或文件系统写路径，不代表已经提交给设备。
#. Writeback 完成表示相关 dirty 数据已完成下层 I/O 语义，仍需确认设备缓存与持久化控制。
#. 设备 write-back cache 可以在数据仍位于易失缓存时向 host 报告写完成。
#. 无掉电保护的易失写缓存制造了“命令完成”和“断电后仍存在”之间的 durability gap。
#. Page Cache 与设备 write cache 必须区分；前者位于主机内存，后者位于设备、控制器或虚拟后端。
#. RAID 控制器、SAN、虚拟机后端、dm-cache 和远端服务都可能额外加入缓存层。
#. 电池/电容保护缓存可以缩小掉电风险，但仍需验证健康状态、写策略和故障切换语义。
#. ``REQ_PREFLUSH`` 表达在当前操作前先刷新此前已接受的易失写入。
#. ``REQ_FUA`` 表达当前写在报告完成前达到相应非易失状态。
#. Flush 主要约束此前写入，FUA 主要约束当前写入，两者可组合形成顺序边界。
#. 空 payload 的 flush 请求只执行缓存刷新；带 payload 的请求也可以附加 preflush/FUA 语义。
#. 设备原生支持 FUA 时可以直接翻译为协议标志；不支持时块层或驱动可能用 write+flush 序列模拟。
#. FUA 模拟会改变命令数量、延迟和影响范围，但上层依赖的语义目标不应改变。
#. ``REQ_OP_FLUSH``、``REQ_PREFLUSH``、``REQ_FUA`` 是块层语义，最终还要由驱动和设备正确实现。
#. Queue 声明 write cache/FUA 能力是上层构造请求的依据，错误声明会破坏性能或可靠性。
#. Flush 成功必须沿所有中间层传到真正持有易失数据的设备或后端。
#. 一个中间层不能简单吞掉 flush，除非它能以自身非易失机制提供等价承诺。
#. Device Mapper、RAID、cache 和虚拟化层必须传播、拆分、汇总或模拟 flush/FUA。
#. 多成员 RAID 的 flush 可能需要发送到所有相关成员，并等待它们完成。
#. Mirror 中只刷新一个副本不足以普遍支持上层已完成写的冗余持久化承诺。
#. Stripe/RAID5/6 中数据、校验和元数据的顺序必须一起满足布局恢复要求。
#. dm-cache writeback 模式中，数据先稳定在 cache 层还是 origin 层，取决于 target 模式和持久化设计。
#. Thin pool 的 data 和 metadata transaction 都可能参与同一次逻辑写的恢复边界。
#. dm-crypt 改变数据内容但仍必须保持下层 flush/FUA 与写入顺序。
#. Loop/NBD/虚拟磁盘的 flush 必须进一步转换为宿主文件系统、网络服务或 hypervisor 的持久化操作。
#. 如果后端忽略 flush，上层 guest 文件系统即使正确发送 barrier 也无法获得真实持久化保证。
#. “Barrier”是历史和泛化术语，现代 Linux 常通过 flush/FUA、请求依赖和文件系统事务表达顺序。
#. Barrier 的核心不是阻止 CPU 重排，而是建立存储命令之间的持久化顺序。
#. 存储 barrier 与内存 barrier 是完全不同的机制，不能因名称相似而混用。
#. I/O scheduler 和设备可以重排普通请求，只要不违反 flush/FUA 等显式顺序约束。
#. 普通写完成顺序可以与提交顺序不同；应用可靠性必须依赖同步接口和文件系统协议，而不是观察偶然顺序。
#. 文件系统日志把多个更新组织为 transaction，并用 commit record 建立可重放边界。
#. 日志 commit record 持久化前，受它确认的数据和描述信息必须按文件系统要求先达到稳定状态。
#. 如果 commit block 先稳定、相关日志内容仍在易失缓存，恢复可能误判一个不完整事务为已提交。
#. Ext4 JBD2、XFS log、Btrfs transaction 等实现细节不同，但都需要定义可恢复状态边界和存储顺序。
#. Journaling 主要保护文件系统元数据一致性，不自动保证应用多文件业务事务原子性。
#. ``data=ordered`` 一类模式建立数据与元数据提交顺序，不表示每次 ``write`` 都同步持久。
#. Data journaling、metadata journaling 和 COW tree commit 对数据写放大与恢复语义不同。
#. 文件系统日志成功提交不等于应用目录项操作必然已经持久，应用仍要按接口规则同步文件和目录。
#. ``fsync(fd)`` 的目标是同步该文件的数据和必要元数据，并报告延迟 writeback 错误。
#. ``fdatasync`` 可以减少部分非必要元数据同步，具体保证必须按 POSIX/Linux 接口语义理解。
#. ``syncfs`` 针对某个文件系统实例推进同步，不替代应用级依赖顺序设计。
#. ``sync`` 触发全局写回，不应作为关键业务事务完成的唯一确认接口。
#. ``close()`` 不应被当作可靠持久化提交操作；关键路径必须显式调用并检查同步接口。
#. 原子 ``rename()`` 保证命名空间操作的运行时原子可见性，不自动证明崩溃后新目录项一定存在。
#. 可靠替换文件的常见协议是：写临时文件 → ``fsync(tmp)`` → ``rename`` → ``fsync(directory)``。
#. 该协议的精确要求仍取决于文件系统、是否新建文件、目录结构和平台保证。
#. 只 ``fsync(tmp)`` 不能普遍保证 rename 后的目录项在崩溃后存在。
#. 只 ``fsync(directory)`` 也不能替代临时文件内容先持久化。
#. 跨文件系统 rename 不具备普通原子 rename 语义，通常退化为复制与删除。
#. 多文件业务更新需要 WAL、数据库事务、版本号或其它应用协议，不能靠多个独立 fsync 自动组成原子事务。
#. Write-ahead logging 要求日志记录先稳定，再让受保护的数据更新对恢复逻辑生效。
#. WAL 的“先”必须是持久化顺序，不只是用户态调用顺序或 CPU 执行顺序。
#. 数据库 group commit 通过合并多个事务的 flush 降低成本，同时增加一部分等待和批量故障范围。
#. Fsync 延迟包含 Page Cache writeback、文件系统事务、块层 flush/FUA 和设备缓存行为。
#. Fsync 慢不能直接归因于设备 flush；也可能在 dirty throttle、journal lock、COW、metadata 或 RAID 成员等待。
#. 普通 write 快而 fsync 慢通常说明成本被延后支付，不表示总 I/O 成本消失。
#. Flush 请求会形成队列顺序点，频繁小事务可能显著降低吞吐。
#. 批量事务可以减少 flush 次数，但必须满足业务允许的 durability latency。
#. 设备带 PLP 时 flush 仍可能用于建立顺序；PLP 不意味着上层可以删除所有同步协议。
#. Write cache 被禁用可能减少 durability gap，也可能大幅降低性能，且仍需文件系统顺序保证。
#. 设备报告 write cache disabled 应结合控制器、桥接层和虚拟化后端确认。
#. USB-SATA 桥、廉价 RAID 卡和部分虚拟磁盘可能错误报告或忽略 flush/FUA。
#. 可靠性要求高的系统应通过硬件认证、断电测试和故障注入验证实际承诺。
#. 断电测试必须保护测试数据和设备，不能在生产数据上直接执行。
#. Crash consistency 测试应覆盖应用进程崩溃、内核 panic、虚拟机断电、控制器 reset 和真实掉电等不同故障点。
#. 仅 ``kill -9`` 应用不能模拟设备缓存丢失或内核未写回数据的完整掉电场景。
#. 文件系统恢复成功只说明结构可挂载，不证明应用最后一个事务符合预期。
#. 恢复后要验证文件内容、目录项、版本号、日志状态和业务不变量。
#. Writeback 错误可能在最初写入之后通过 ``fsync`` 报告，应用必须保存并处理同步返回值。
#. 多个打开实例对同一 mapping 的 writeback error 报告有游标语义，精确实现具有版本差异。
#. 底层介质错误、path failover 或 reset 后最终 flush 失败时，上层同步接口必须返回错误，而不是伪造成功。
#. Retry 可能延迟 flush，但不能降低其最终完成语义；无法兑现时应失败。
#. Timeout 后命令是否已经执行可能不明确，应用重试非幂等写入必须使用事务 ID 或日志避免重复副作用。
#. NVMe reset、SCSI EH 和 multipath failover 期间的在途写可能处于已执行、未完成或未知状态。
#. 文件系统与块层负责尽量收束请求状态，应用仍应依赖可恢复事务协议处理系统级不确定性。
#. RAID 降级时仍可能成功 fsync，但冗余水平已经下降，应把可靠性状态纳入业务告警。
#. Battery-backed controller 电池失效后可能从 writeback 自动切为 writethrough，造成 fsync 延迟突增。
#. Thin pool、cache metadata 或阵列 NVRAM 状态变化都可能改变持久化成本与保证。
#. ``/sys/block/<dev>/queue/write_cache`` 等属性可提供线索，格式和真实性取决于驱动与设备。
#. ``hdparm``、``nvme-cli``、``smartctl`` 和阵列工具看到的是不同控制层，不可互相替代。
#. Block trace 应单独统计 FLUSH、FUA 写、普通写和 completion 延迟。
#. 大量 preflush/FUA 是事务密集型 workload 的正常结果，也可能说明应用同步粒度过细。
#. Flush 在上层出现而下层没有对应动作时，应检查 target 是否安全吸收、设备是否无易失缓存，或语义是否丢失。
#. 分层追踪要处理一个上层 flush 展开为多个下层 flush 的一对多关系。
#. ``block_rq_complete`` 只说明该层 request 完成，不能独自证明应用 ``fsync`` 已返回。
#. 完整 fsync 时间线应连接：应用调用 → 文件系统 writeback/log → flush/FUA → 所有下层 completion → 任务唤醒 → fsync 返回。
#. 可靠性审计必须记录文件系统类型、mount options、块设备栈、cache 模式、RAID 状态和设备能力。
#. 变更任一层配置后都应重新验证顺序和故障恢复，不能沿用旧测试结论。
#. 最稳定源码阅读顺序是：应用同步接口 → 文件系统事务/日志 → bio flags → ``blk-flush`` → dm/RAID 传播 → 协议命令 → 设备承诺。
#. 精确日志格式、flush sequence 实现、FUA 模拟和设备协议字段属于版本与硬件敏感细节。

必背路径
--------

普通写与持久化差距：

::

   应用 write
   → Page Cache dirty
   → 文件系统 writeback
   → 块层普通 write request
   → 设备易失写缓存接收
   → 命令可能先报告完成
   → 后续才写入非易失介质
   → 无 flush/FUA 时掉电可能丢失

Flush + FUA：

::

   文件系统需要持久化顺序点
   → 设置 REQ_PREFLUSH
   → 刷新此前易失写入
   → 提交当前关键写
   → 设置 REQ_FUA
   → 当前写稳定后才完成
   → 完成逐层返回
   → 上层事务可建立 commit 边界

日志事务提交：

::

   收集 transaction 更新
   → 写 descriptor/data/metadata
   → 等待受保护内容达到要求状态
   → preflush 必要旧写
   → 写 commit record 并使用 FUA/flush
   → commit 完成
   → 后续 checkpoint 到 home location
   → 崩溃恢复只重放完整事务

可靠替换文件：

::

   创建同目录临时文件
   → 写入完整新内容
   → fsync 临时文件并检查错误
   → rename 覆盖正式文件
   → fsync 父目录并检查错误
   → 记录业务版本/事务状态
   → 崩溃后验证内容和目录项

分层持久化审计：

::

   确认文件系统同步语义
   → 检查 dm/LVM/RAID/cache 层
   → 检查每层 flush/FUA 传播
   → 检查控制器与设备 write cache
   → 检查 PLP/BBU 健康状态
   → 追踪 FLUSH/FUA completion
   → 执行受控 crash/power-fail 测试
   → 验证恢复后的业务不变量

必须区分
--------

* ``write`` 成功与持久化成功：Write 可只修改内存或易失缓存；持久化需要同步协议和最终设备承诺。
* Page Cache 与设备 Write Cache：前者由内核管理文件缓存；后者可在块命令完成后仍保存易失数据。
* Flush 与 FUA：Flush 约束此前写；FUA 约束当前写在完成前稳定。
* 存储 Barrier 与内存 Barrier：前者建立 I/O 持久化顺序；后者约束 CPU 和内存访问可见顺序。
* 日志一致性与应用事务：文件系统日志保护文件系统恢复；应用多对象原子性仍需业务事务协议。
* 原子 Rename 与目录项持久化：Rename 在运行时原子切换名字；崩溃后存在性通常还需要同步父目录。

一句话结论
----------

崩溃一致性要求应用、文件系统、块层、虚拟设备和最终硬件对完成与持久化作出同一条可传递承诺，Flush/FUA 只是把这条承诺明确送到设备的关键控制点。
