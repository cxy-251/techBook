第098章：XFS 扩展性、Allocation Group 与大型文件系统
=====================================================

核心知识点
----------

XFS 把扩展性作为核心目标
   大文件、大目录和高并发元数据操作需要避免单一全局分配结构。XFS 通过局部域、索引树和事务日志降低大型文件系统上的共享瓶颈。

Allocation Group 是并行分配域
   文件系统被划分为多个 AG，每个 AG 管理自己的部分空闲空间、inode 和相关元数据。并发操作落在不同 AG 时，可以减少全局锁竞争。

AG 不是用户可见目录
   AG 属于内部物理布局和元数据管理，一个文件的 extent 可以跨越多个 AG，目录树也不会按 AG 划分。

块地址存在多种坐标
   XFS 同时使用文件系统全局块号、AG 编号和 AG 内块号。源码阅读和故障日志必须先确认当前字段所属坐标系。

B+ tree 支撑规模增长
   空闲空间、inode、文件 extent、反向映射和共享 extent 引用可由不同 B+ tree 管理，避免用固定线性结构承载大型元数据集合。

索引树也需要事务保护
   B+ tree 插入、删除、分裂和合并会修改持久化元数据，必须放入 XFS transaction，并满足锁、空间和日志预留要求。

Delayed allocation 改善布局
   Buffered write 先形成脏逻辑范围，真实块选择推迟到 writeback，使 XFS 能基于更完整的范围、AG 状态和对齐条件建立 extent。

Iomap 连接文件偏移与存储映射
   XFS 广泛使用 iomap 把 buffered I/O、direct I/O、Page Cache 和 extent 状态连接起来。公共框架并不消除 XFS 自身的分配和事务规则。

Unwritten extent 分离预留与有效数据
   物理空间可以先预留为 unwritten extent，读取仍返回零；实际写入完成后再转换为 written，避免暴露旧磁盘内容。

元数据日志记录事务变化
   XFS 日志主要保护 inode、目录、B+ tree 和空间管理等元数据。普通文件数据通常仍通过 writeback 或 direct I/O 路径写入设备。

事务需要预先保留推进资源
   操作开始前通常预留日志空间和可能的磁盘空间，避免持锁并修改一半后因资源不足无法完成或回滚。

AIL 连接日志提交与原位写回
   已提交日志但尚未写回 home location 的元数据项目可由 Active Item List 一类结构跟踪，checkpoint 完成后日志空间才能进一步复用。

AG 并行性不能消除所有热点
   同一 inode、同一目录、同一 AG、日志空间和设备队列仍可能成为串行点。低设备吞吐下也可能出现纯元数据锁等待。

恢复保证停留在文件系统层
   日志 replay 让 XFS 元数据结构回到一致状态，不自动保证最后一次普通写或跨文件业务事务已经持久化。

关键路径
--------

延迟分配兑现：

::

   用户写入不同文件
   → Page Cache 形成 dirty ranges
   → XFS 记录 delayed allocation
   → writeback 请求真实块映射
   → 选择候选 allocation group
   → 查询并更新 AG 空闲空间 B+ tree
   → 建立 inode extent 与 rmap/refcount
   → 元数据加入 transaction
   → 日志提交并发出数据 I/O

AG 内空间分配：

::

   输入长度、位置和对齐需求
   → 选择可用 AG
   → 读取 per-AG 状态
   → 查询按位置或长度组织的空闲树
   → 分裂或移除空闲 extent
   → 得到 AG 内块范围
   → 转换为全局块号
   → 更新所有权与文件映射

元数据事务与恢复：

::

   预留日志和空间资源
   → 锁定 inode、目录或 B+ tree 对象
   → 修改并生成 log items
   → commit transaction
   → 日志记录达到稳定顺序
   → AIL/checkpoint 写回 home metadata
   → 崩溃时 replay 已提交记录
   → 恢复可解释的元数据关系

诊断并发延迟：

::

   固定操作、文件和目录范围
   → 判断是否集中于同 inode 或同目录
   → 检查 AG 分布和空间形状
   → 检查 transaction、log force 与 AIL 等待
   → 对齐 writeback 和块设备延迟
   → 用 trace/perf 定位锁与调用栈
   → 区分对象热点、AG 热点、日志或设备瓶颈

概念辨析
--------

* Allocation group 与目录层级：AG 是内部空间管理域；目录是用户命名关系，两者没有固定对应。
* AG 并行与无锁：不同 AG 降低部分竞争，操作仍受 inode、目录、日志和设备同步约束。
* Delalloc 与真实 extent：Delalloc 表示未来分配需求；writeback 后才形成确定物理映射。
* Unwritten 与 written extent：前者已预留空间但读取为零；后者包含已完成写入的有效数据。
* Metadata log 与数据内容：日志保护元数据事务；普通文件数据不因此自动双写进日志。
* 文件系统恢复与业务提交：Log replay 修复 XFS 结构；应用仍需通过 fsync 和事务协议保证业务状态。

本章结论
--------

XFS 以 allocation group、B+ tree、延迟分配和元数据事务把大型文件系统拆成可并行的局部工作，但 inode、目录、日志与设备热点仍需分别证明。
