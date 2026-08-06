第098章：XFS 扩展性、Allocation Group 与大型文件系统
=====================================================

本章必须记住
------------

#. XFS 的核心目标之一是让大文件、大目录和高并发元数据操作在大型文件系统上保持可扩展。
#. XFS 通过 allocation group（AG）把空间与 inode 管理拆成多个相对独立的局部元数据域。
#. AG 不是目录、挂载点或用户可见子文件系统；它是 XFS 内部的分配和元数据并行边界。
#. 一个文件可以拥有跨多个 AG 的 extent，一个目录也可以包含 inode 位于不同 AG 的对象。
#. ``struct xfs_perag`` 一类对象保存每 AG 的内存状态，具体字段和生命周期随版本演进。
#. XFS 同时使用文件系统全局块号、AG 编号和 AG 内块号；阅读分配路径必须确认当前坐标系。
#. 多个并发操作落在不同 AG 时，可以修改不同的空闲空间和 inode 元数据结构，降低全局锁竞争。
#. AG 不能消除所有竞争；同一 inode、同一目录、同一 AG 和日志资源仍可能形成串行点。
#. 高并发性能问题必须区分 inode 锁、目录锁、AG 元数据、日志空间和块设备延迟。
#. AG 数量和大小主要在 mkfs 时确定，会影响并行性、元数据开销和未来扩展行为。
#. 过少 AG 可能扩大局部竞争范围；过多 AG 会增加固定元数据和管理成本。
#. XFS 大量使用 B+ tree 管理随文件系统规模增长的元数据，而不是依赖单一全局线性表。
#. 空闲空间通常由按起始位置和按长度等不同索引组织，帮助查找位置合适或大小合适的 extent。
#. Inode 分配状态、文件 extent、反向映射和空闲空间等可由不同 B+ tree 管理，具体特性取决于格式版本。
#. B+ tree 的查找、插入、分裂和合并都属于持久化元数据修改，必须进入事务和日志保护。
#. 文件 extent 描述文件逻辑范围到物理块范围的映射；AG free-space tree 描述某个局部域还有哪些空闲范围。
#. Reverse mapping（rmap）记录物理范围由哪些所有者引用，为在线检查、重建和空间管理提供反向证据。
#. Refcount tree 可支持共享 extent/reflink 的引用关系，不能只按单一 inode 独占块模型分析现代 XFS。
#. XFS delayed allocation 先记录文件逻辑范围和内存脏状态，把真实块分配推迟到 writeback。
#. 延迟分配让 XFS 根据更完整的写入范围、设备几何和局部性选择较好的 extent。
#. ``write()`` 返回成功时，延迟分配范围可能尚未取得真实磁盘块，后续 writeback 仍可能失败。
#. Iomap 是现代 XFS 连接文件偏移、Page Cache、direct I/O 和 extent 映射的重要通用接口，具体函数拆分具有版本差异。
#. 写回阶段会把 delalloc extent 转换为真实 extent，更新 AG 空间树和 inode 映射。
#. XFS 使用 write-ahead metadata log 保护元数据事务，日志记录的是可恢复的元数据变化而非普通应用事务。
#. XFS transaction 把一次操作涉及的 inode、btree、目录和空间修改组织成受日志保护的更新集合。
#. 事务开始前通常需要预留日志空间和可能的磁盘资源，避免持锁后才发现无法推进。
#. 事务提交使日志层获得元数据变化；真实 home location 的写回可以在后续进行。
#. 崩溃恢复扫描日志并重放已提交、可解释的元数据操作，使文件系统回到结构一致状态。
#. 日志恢复不自动保证应用最后一次普通 write 的数据已经稳定持久化。
#. XFS 日志强调元数据一致性；文件数据持久化仍依赖 writeback、fsync、设备 flush 和应用顺序。
#. XFS 常通过 log item 表示不同元数据对象如何格式化进入日志和在恢复时重放。
#. Active Item List（AIL）一类结构跟踪已提交到日志但 home metadata 尚未完成持久化的项目，具体实现具有版本差异。
#. Log force 用于推进日志到稳定边界，fsync 等路径可能要求强制特定序列提交。
#. Journal/log 与文件数据内容仍是不同层；不能把“XFS 有日志”理解成所有文件数据都双写日志。
#. XFS 的 metadata updates 常使用 intent/done 类机制表示可能跨多个内部步骤完成的操作，具体类型以目标版本为准。
#. Rename、extent freeing、reflink 和目录操作可能涉及多对象事务，必须按资源预留和锁顺序执行。
#. XFS inode number 通常编码 AG 相关位置关系，但用户态不应依赖内部编码作为稳定 ABI。
#. 大目录使用索引化结构减少线性查找成本，但同一热目录仍可能因目录 inode 和日志修改形成瓶颈。
#. 大文件性能来自 extent、delalloc、并行 AG 和索引结构共同作用，不是单纯支持更大文件长度。
#. XFS 动态预分配和 speculative preallocation 可以改善顺序增长布局，也可能让 ``du``、``df`` 和实际写入需求看起来不同。
#. EOF 之后的预分配空间不一定等于用户可读文件数据，truncate、close、回收和 mount 选项会影响保留方式。
#. ``fallocate``、reflink、hole punching 和 unwritten extent 会改变 extent 状态，不能把所有已分配块视为已有有效数据。
#. Unwritten extent 预留物理空间但读取保持零值语义，写入完成后再转换为 written 状态。
#. Direct I/O、DAX、buffered I/O 和 reflink 文件可能进入不同映射与一致性路径。
#. XFS 支持在线 grow，但不能无条件在线 shrink；功能边界必须按当前内核和工具版本确认。
#. 文件系统 grow 会增加新的空间和 AG 或扩展布局，具体策略取决于原始格式和设备。
#. XFS metadata checksum、UUID、owner、generation/LSN 等字段帮助检测错误块和旧元数据，不能代替备份。
#. XFS 遇到严重元数据错误时可能触发 shutdown，后续修改返回 I/O 错误以防止扩大损坏。
#. Forced shutdown 后文件系统通常需要卸载、检查设备与日志，并按官方工具流程修复，不能继续当作正常只读缓存使用。
#. ``xfs_repair`` 是离线修复工具；在日志未正常清理时必须理解其对日志和最近元数据状态的处理边界。
#. ``xfs_scrub``/在线检查能力依赖内核、工具和特性配置，不能假设所有部署都可用相同修复功能。
#. ``df`` 可用空间、AG 空闲 extent、inode 预留和日志空间是不同资源域，单一百分比不能解释全部 ENOSPC。
#. XFS 的 ENOSPC 可能来自数据空间、元数据空间、特定 AG 形状、配额或 delayed allocation 后续兑现失败。
#. Project quota 是 XFS 常用资源控制机制之一，需与用户/组配额和全局空间分开判断。
#. 性能诊断应观察 workload 分布、目录热点、inode 锁、AG 竞争、log force、writeback、设备延迟和 CPU 利用。
#. 只看设备吞吐无法证明瓶颈在磁盘；元数据锁和日志串行点可能在低吞吐时制造高延迟。
#. 只看 CPU 高也无法证明 B+ tree 是根因；必须通过 trace、perf 和 XFS stats 对齐具体操作。
#. 最稳定源码阅读顺序是：VFS 入口 → XFS iomap/delalloc → 选择 AG → 更新 B+ tree/extent → transaction → metadata log → recovery/checkpoint。

必背路径
--------

并发文件增长：

::

   多个进程写入不同文件
   → VFS 进入 XFS write path
   → Page Cache 形成 dirty ranges
   → XFS 建立 delayed allocation
   → writeback 触发真实空间选择
   → 选择目标 allocation group
   → 更新 AG free-space B+ tree
   → 建立 inode extent mapping
   → 元数据变化进入 XFS transaction
   → 日志提交并发出数据 I/O

AG 内空间分配：

::

   得到目标长度和对齐需求
   → 选择候选 AG
   → 读取 per-AG 状态
   → 查询按位置/长度组织的 free-space trees
   → 分裂或删除空闲 extent
   → 返回 AG 内块范围
   → 转换为文件系统全局块号
   → 更新 inode mapping 与 rmap/refcount

元数据事务：

::

   预估操作所需日志和空间
   → 分配 transaction
   → 锁定并加入 inode / btree buffers
   → 修改目录、extent、space 或 inode 元数据
   → 创建对应 log items
   → commit transaction
   → 日志记录达到稳定顺序
   → AIL/checkpoint 后续写回 home locations

崩溃恢复：

::

   挂载发现日志需要恢复
   → 扫描有效 log records
   → 验证元数据标识和校验
   → 重放已提交事务和 intent/done 状态
   → 恢复 inode、btree 和空间关系
   → 完成必要清理
   → 建立可挂载的一致元数据视图

诊断 XFS 高并发延迟：

::

   固定文件、目录和时间窗口
   → 区分同 inode / 同目录 / 不同文件
   → 查看 AG 分布与空间状态
   → 观察 log force、AIL 与 transaction 等待
   → 观察 writeback 和 block latency
   → 用 trace/perf 确认锁与调用栈
   → 判断目录热点、AG 热点、日志或设备瓶颈

必须区分
--------

* Allocation group 与目录树：AG 是内部元数据分配域；用户目录结构可以跨多个 AG。
* AG 并行性与无锁：不同 AG 可降低竞争；同 inode、同目录、同 AG 和日志仍需要同步。
* Delayed allocation 与已分配 extent：Delalloc 只记录未来需求；真实物理范围在后续 writeback 才确定。
* Metadata log 与数据日志：XFS 日志主要记录元数据事务；普通文件数据通常走自己的 writeback 路径。
* B+ tree 索引与数据内容：Tree 管理空间、inode 和 extent 元数据；文件实际数据仍位于对应 data extents。
* 文件系统可恢复与应用事务完整：Log recovery 修复 XFS 元数据状态；多文件业务提交仍需要应用级协议。

一句话结论
----------

XFS 通过 allocation group、B+ tree、延迟分配和元数据日志把大型文件系统操作拆成可并行的局部事务，但热点 inode、日志和设备仍需单独诊断。
