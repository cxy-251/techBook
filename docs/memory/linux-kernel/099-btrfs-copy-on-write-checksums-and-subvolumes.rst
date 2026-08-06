第099章：Btrfs COW、校验和与子卷
================================

核心知识点
----------

Btrfs 应按版本化状态树理解
   文件数据 extent、元数据 B-tree、tree root、事务和引用关系共同表达一个可提交的文件系统状态，而不是一组彼此独立的原地更新块。

普通更新采用 Copy-on-Write
   新数据或元数据先写入新的物理位置，上层引用随后切换到新版本。旧 extent 只要仍被快照、reflink 或其它 root 引用，就不能释放。

COW 同时作用于数据和元数据
   修改少量文件内容可能产生新 data extent、file extent item、checksum item 以及多层 B-tree 节点更新，因此小随机写也可能形成明显写放大。

Extent 引用定义共享关系
   Extent tree、backref 和 refcount 记录物理范围被哪些文件、树根或快照引用。文件逻辑大小不能直接推导其独占物理占用。

Subvolume 是独立 tree root
   子卷拥有自己的目录树和 inode 编号空间，但仍共享同一 Btrfs 文件系统、事务、设备集合和空间池。

Snapshot 复制根关系而非数据
   快照初始共享大量元数据和数据 extent，因此创建快速；源和快照后续分歧时才逐步产生新的 COW 空间。

快照删除不等于立即释放空间
   只有某个 extent 的所有 root、reflink 和快照引用都消失后，它才可回收。目录项删除与真实空间回收可能存在明显时间差。

事务提交切换稳定根
   多个修改通常聚合进一个 Btrfs transaction。提交过程写出新 tree blocks、extent 引用和 checksum，再让 superblock 指向新的已提交 roots。

Tree log 优化部分 ``fsync``
   某些文件同步可通过 tree log 记录必要变化，避免每次提交完整全局事务。其恢复仍需正确处理文件、目录项和 rename 依赖。

校验和负责发现内容不一致
   数据 checksum 通常保存在 checksum tree，元数据块携带自描述校验字段。读回内容不匹配时，内核能够检测损坏。

检测不等于修复
   自动修复要求存在另一份可读取且校验正确的副本。所有副本都坏、误删除或应用写入错误时，checksum 无法恢复原始业务数据。

Scrub 验证已分配内容
   Scrub 主动读取数据和元数据并校验，在有冗余时尝试修复。它不是离线结构检查，也不能替代独立备份。

Profile 决定逻辑块到设备布局
   Data、metadata 和 system block group 可以使用不同 RAID profile。多设备文件系统不能按单一传统 RAID 名称推断所有数据的容错能力。

Btrfs 空间不是单一数字
   Chunk、block group、profile、metadata reserve、global reserve、快照共享和 qgroup 都影响可分配性。设备仍有未用字节时也可能出现 ``ENOSPC``。

关键路径
--------

普通 COW 写入：

::

   用户修改文件逻辑范围
   → Page Cache 形成 dirty data
   → 分配新的 data extent
   → 计算并记录 checksum
   → 更新 file extent item
   → COW 修改 filesystem tree 节点
   → 更新 extent refs 与 backrefs
   → transaction commit 写出新 roots
   → 旧 extent 按剩余引用继续保留或释放

创建与分裂快照：

::

   选择源 subvolume root
   → 创建新的 snapshot root
   → 初始共享 tree nodes 与 data extents
   → 源或快照继续读取共享内容
   → 任一方写入共享范围
   → 分配新 extent 并切换该方引用
   → 最后共享引用消失后回收旧 extent

校验与冗余修复：

::

   逻辑范围映射到目标 extent
   → 从某个设备副本读取数据
   → 计算 checksum
   → 与记录值比较
   → 匹配则返回内容
   → 不匹配时读取其它 mirror
   → 找到好副本时返回并可修复坏副本
   → 无有效副本时报告 I/O 或 checksum 错误

诊断 ``ENOSPC``：

::

   保存失败操作与内核日志
   → 区分 data、metadata 和 system 空间
   → 查看 chunk/profile 与设备未分配空间
   → 检查 metadata/global reserve
   → 检查快照、reflink 与共享 extent
   → 检查 qgroup 和 transaction 状态
   → 判断容量、profile 或分配域限制
   → 保留工作空间后再删除、扩容或受控 balance

概念辨析
--------

* COW 与原地覆盖：普通 Btrfs 写新位置并切换引用；NODATACOW 等特殊路径会改变该模型。
* Subvolume 与独立文件系统：子卷有独立 root 和目录层级，但共享同一存储池、事务与设备。
* Snapshot 与备份：快照通常与源处于相同设备和故障域；备份要求独立副本和恢复验证。
* Checksum 检测与自动修复：校验和能发现不一致；修复还依赖可验证的冗余副本。
* 逻辑大小与物理占用：压缩、快照和 reflink 会让多个对象共享 extent，二者不能直接换算。
* 设备空闲与可分配空间：剩余设备字节不保证当前 profile、chunk 和 metadata 域能够满足新的 COW 更新。

本章结论
--------

Btrfs 用 COW 状态树、extent 引用和校验和统一组织写入、快照与完整性；空间、恢复和性能必须按事务根、共享关系与设备 profile 联合分析。
