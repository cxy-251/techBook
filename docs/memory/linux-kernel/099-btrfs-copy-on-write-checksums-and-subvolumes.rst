第099章：Btrfs COW、校验和与子卷
================================

本章必须记住
------------

#. Btrfs 应按“版本化状态树”理解：数据 extent、元数据 B-tree、tree root、事务和引用关系共同表达文件系统状态。
#. 普通 COW 更新先写入新的物理位置，再把上层元数据引用切换到新版本。
#. Btrfs 的 COW 同时可以作用于文件数据 extent 和元数据 B-tree 节点。
#. 旧 extent 只要仍被快照、reflink 或其它 tree 引用，就不能释放。
#. Extent tree、backref 和 refcount 关系用于说明某段物理空间被哪些对象共享。
#. 文件长度不等于独占物理占用；多个文件或快照可以共享同一 extent。
#. 覆盖少量逻辑数据可能引起新 data extent、file extent item、checksum 和多层 tree node 更新。
#. COW 让快照和 reflink 低成本建立共享，也可能增加随机写碎片、元数据开销和写放大。
#. Btrfs 使用通用 B-tree key space 组织 inode item、目录项、file extent、checksum 和 root 等对象。
#. Key 通常由 objectid、type 和 offset 组成，具体对象语义由 item type 决定。
#. 一个 subvolume 对应一个独立 filesystem tree root，拥有自己的目录层级和 inode number namespace。
#. Subvolume 不是独立块设备或独立存储池；多个 subvolume 共享同一个 Btrfs 文件系统空间与设备集合。
#. Snapshot 是基于已有 subvolume root 创建的新 root 关系，初始共享大量数据和元数据 extent。
#. Snapshot 创建快不等于未来空间成本为零；源和快照继续分歧时会产生新 extent 和元数据。
#. 删除快照只释放不再被任何 root 或 reflink 引用的 extent，空间回收可能明显滞后于目录删除。
#. Read-only snapshot 可以作为 send 的稳定父/源状态，但不能代替离线或异地备份。
#. Btrfs send 根据两个 subvolume/snapshot 状态生成逻辑变更流，receive 在目标文件系统重建对象关系。
#. Send stream 是文件系统级逻辑操作序列，不是原始块设备镜像。
#. Incremental send 依赖发送端和接收端对 parent 状态具有一致理解，错误 parent 会导致失败或错误恢复计划。
#. COW 提交不是每个 write 单独产生一个全局稳定版本；多个修改通常聚合进 Btrfs transaction。
#. Transaction commit 把一组新 tree blocks、extent 引用、checksum 和 root 更新推进到可恢复边界。
#. Superblock 保存可定位当前已提交 tree roots 的关键指针与 generation 信息，具体格式有多个镜像位置。
#. 崩溃恢复依赖最后完整提交的事务和可验证树结构，不保证应用所有未 fsync 修改都可见。
#. Tree log 可以加速部分 fsync 持久化，避免每次都提交整个全局 transaction；具体适用和恢复路径具有版本差异。
#. ``fsync()`` 的 Btrfs 语义必须结合 tree log、transaction commit、rename 和目录项依赖理解。
#. Btrfs 默认对数据和元数据使用 checksum，但具体算法在创建文件系统时确定。
#. 数据 checksum 通常存放在独立 checksum tree，元数据 block 在 header 中包含 checksum 等自描述字段。
#. 读取时 checksum mismatch 说明内容与记录摘要不符，能够检测损坏，不自动保证可修复。
#. 只有存在可用冗余副本并且能通过校验验证时，Btrfs 才可能从另一副本修复坏块。
#. RAID1/10、DUP 等 profile 表达块组副本布局；不同 profile 的容错能力不能只按传统 RAID 名称机械推断。
#. Scrub 主动读取已分配数据和元数据、验证 checksum，并在有冗余时尝试修复。
#. Scrub 不等于离线结构检查，也不能恢复所有副本都损坏、误删除或应用写入错误。
#. Checksum 验证“读回内容是否等于文件系统记录的内容”，不能判断应用写入的业务数据是否正确。
#. NODATACOW 会改变普通数据 COW 路径，常同时影响 data checksum、压缩、快照共享和恢复特征。
#. NODATASUM 表示数据不使用普通 checksum 语义；必须在使用前理解其完整性代价。
#. 不能把“Btrfs 是 COW 文件系统”绝对化到所有 inode、direct I/O、swapfile 和特殊 extent 路径。
#. Compression 在写入时把逻辑范围压缩成较少物理数据，读出时解压，实际收益取决于数据可压缩性和 CPU 成本。
#. 压缩会让逻辑大小、已分配物理大小、extent 边界和实际 I/O 量之间关系更复杂。
#. 不同压缩算法和级别具有版本、CPU、兼容性和 workload 边界，必须从实际挂载/文件属性确认。
#. Btrfs 的 chunk/block group 将逻辑地址映射到一个或多个设备上的物理范围，profile 决定副本或条带布局。
#. 一个多设备 Btrfs 文件系统不等于所有数据都按同一种 profile 分布；data、metadata、system 可以使用不同 profile。
#. ``df`` 的通用 VFS 可用空间视图不能完整解释 Btrfs chunk 分配、profile、未分配设备空间和 metadata reserve。
#. Btrfs 出现 ENOSPC 时，设备仍可能显示未用字节，但当前 data/metadata chunk、profile 或 reserve 无法满足请求。
#. Metadata ENOSPC 与 data ENOSPC 必须分开分析；COW 更新即使只改小文件也可能需要额外 metadata 空间。
#. Global reserve 用于帮助关键元数据路径推进，不是普通应用可自由使用的剩余空间。
#. Balance 重新分配 chunk 中的数据以改变使用率或 profile，不是通用“整理碎片”或无风险日常命令。
#. Balance 需要额外工作空间，文件系统非常满时可能反而更难执行。
#. Device add/remove/replace 会改变 chunk 布局和副本位置，操作期间必须同时考虑故障域和剩余容量。
#. Reflink 让两个文件共享 extent；任一文件后续写入共享范围时才通过 COW 分裂。
#. Deduplication 若由用户态或其它机制建立共享 extent，也会改变物理占用与后续写放大。
#. ``du``、``df``、exclusive/shared qgroup 数值回答的问题不同，不能互相替代。
#. Qgroup 试图统计 subvolume 的 referenced/exclusive 空间，快照和共享关系多时更新成本和解释都更复杂。
#. 配额启用、rescan 和关系更新会增加元数据工作，生产环境应评估实际版本行为。
#. Btrfs metadata 自描述字段、checksum、owner 和 generation 帮助识别错误块和旧版本节点。
#. Tree checker 报错说明读取到的结构不能满足当前格式约束，常需结合设备错误、内存、内核日志和离线工具判断。
#. Read-only mount 可以阻止继续修改，但不等于损坏已经修复或所有数据都可安全读取。
#. ``btrfs check --repair`` 具有高风险，不能作为看到错误后的默认第一步；必须按官方建议、版本和备份状态执行。
#. Scrub、device stats、filesystem usage、subvolume list 和 kernel log 提供不同证据层。
#. 诊断空间问题应先看 filesystem usage 与 device usage，再看 data/metadata/system profile、reserve、qgroup 和快照共享。
#. 诊断 checksum 错误应记录 logical address、device、mirror、文件路径映射、scrub 状态和是否有可用好副本。
#. 诊断写放大应观察 COW、压缩、快照/reflink 数量、随机写模式、transaction commit 和底层设备延迟。
#. Btrfs 不能替代备份；快照与源数据通常共享同一设备和故障域。
#. 最稳定阅读顺序是：VFS 写入 → data extent → file extent item → checksum → COW tree nodes → extent refs → transaction commit → root/snapshot/send。

必背路径
--------

普通 COW 写入：

::

   用户写入文件逻辑范围
   → Page Cache 形成 dirty data
   → Btrfs 分配新 data extent
   → 计算并记录 data checksum
   → 更新 file extent item
   → COW 修改 filesystem tree leaf/node
   → 更新 extent refs 与 backrefs
   → transaction commit 切换到新 root
   → 旧 extent 由旧快照或其它引用继续持有

创建快照：

::

   选择源 subvolume
   → 建立新的 subvolume root
   → 初始共享源 tree 与 data extents
   → 快照创建快速完成
   → 源或快照后续写入触发 COW 分裂
   → extent 引用计数增加或减少
   → 最后引用消失时空间才能释放

Checksum 读取与修复：

::

   文件逻辑范围映射到 data extent
   → 从设备读取目标副本
   → 计算 checksum
   → 与 checksum tree 中记录比较
   → 匹配则返回数据
   → 不匹配时尝试其它 mirror
   → 找到好副本则返回并可能修复坏副本
   → 全部副本失败则报告 I/O / checksum error

Send/Receive：

::

   准备只读源 snapshot
   → 可选指定共同 parent snapshot
   → send 遍历两个状态树差异
   → 生成创建、写入、rename、clone 等逻辑命令流
   → 传输到目标
   → receive 重建 subvolume 状态
   → 验证目标快照、parent 链和业务完整性

诊断 Btrfs ENOSPC：

::

   保存失败操作和 kernel log
   → 查看 filesystem usage
   → 区分 data / metadata / system
   → 查看各 profile 与设备未分配空间
   → 检查 global reserve 和 qgroup
   → 检查快照、reflink 与共享 extent
   → 判断 chunk 分配、profile 约束或真实容量不足
   → 保留工作空间后再选择删除、扩容或受控 balance

必须区分
--------

COW 更新与原地覆盖
   普通 Btrfs 路径写新 extent 并切换引用；NODATACOW 等特殊路径会改变该模型。

快照与备份
   快照保留文件系统内部旧 root，通常仍处于相同设备和故障域；备份需要独立副本与恢复验证。

Checksum 检测与自动修复
   校验和能发现内容不匹配；修复还要求存在可验证的冗余好副本。

Subvolume 与独立文件系统
   Subvolume 有独立 tree root 和目录层级，但共享同一个 Btrfs 存储池、事务和设备集合。

逻辑大小与物理占用
   压缩、快照和 reflink 使一个文件的逻辑长度不能直接推导独占磁盘空间。

设备空闲与可分配空间
   未分配设备字节不保证当前 profile 和 metadata/data 域能立即满足 COW 请求。

一句话结论
----------

Btrfs 用 COW 状态树、extent 引用和校验和统一管理写入、快照与完整性，因此空间、性能和恢复都必须按共享关系、事务根和设备 profile 联合判断。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 20，Filesystem Implementations ext4, XFS, Btrfs, and Pseudo Filesystems；
* AIBook 章节：Chapter 99，Btrfs Copy-on-Write, Checksums, and Subvolumes；
* 源文件：``docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_099_Btrfs_Copy_on_Write_Checksums_and_Subvolumes.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_099_Btrfs_Copy_on_Write_Checksums_and_Subvolumes.md>`_。