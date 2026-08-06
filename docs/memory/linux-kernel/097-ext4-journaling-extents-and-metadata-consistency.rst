第097章：ext4 日志、Extent 与元数据一致性
=========================================

本章必须记住
------------

#. ext4 延续传统 Unix 文件系统的 inode、block group 和就地更新模型，并用 extent、延迟分配和 JBD2 日志增强可扩展性与恢复能力。
#. ext4 不是通用 Copy-on-Write 文件系统；普通更新最终会写回对象的既定磁盘位置。
#. 文件逻辑偏移到磁盘块的映射、空间分配局部性、日志事务，是理解 ext4 写入的三条主线。
#. Extent 用“逻辑起点、物理起点、连续长度”描述一段连续映射，减少大文件所需映射元数据。
#. Inode 内可以保存 extent tree 根；映射复杂时再使用额外 extent tree 节点。
#. Extent 是映射表示，block group 是空间管理域，两者不能混为同一对象。
#. Block group 通常包含块位图、inode 位图、inode table、group descriptor 和数据块等布局元素。
#. 分配器尽量把 inode、目录和文件数据放在有利于局部性与连续性的 group 中，但不保证永远连续。
#. Delayed allocation 先在 Page Cache 中记录脏范围，把真实物理块分配推迟到 writeback 或同步路径。
#. 延迟分配让分配器看到更大的待写范围，通常有利于连续 extent 和减少碎片。
#. ``write()`` 返回成功时，delayed allocation 范围可能尚未获得最终物理块。
#. 未来 writeback 仍可能遇到空间不足、配额、I/O 或文件系统错误。
#. Extent 状态可以包含未初始化/preallocated 语义，读取和写入路径必须按具体状态解释。
#. Fallocate 可以预留空间或改变文件范围，但不同 mode 对文件长度、数据内容和 extent 状态的影响不同。
#. JBD2 是 ext4 使用的通用块级日志层，主要为元数据修改建立事务和崩溃恢复边界。
#. Ext4 负责识别要修改的 inode、bitmap、extent、目录块等元数据；JBD2 负责事务、日志写入、commit 和 replay。
#. Journal handle 把当前元数据修改绑定到一个事务，并通过 credit 估计限制允许修改的元数据块数量。
#. Credit 不足时必须扩展、重启或拆分事务，不能无条件继续修改未纳入日志保护的元数据。
#. 元数据缓冲区进入事务后，需要按 JBD2 协议获得写权限、标记脏状态并最终进入 commit。
#. Write-ahead logging 要求相关日志记录先达到所需持久化顺序，再允许 checkpoint 把元数据更新到 home location。
#. Commit record 是事务已完成的关键恢复标志；未完整提交的事务不应作为完整事务重放。
#. Crash recovery 重放完整已提交事务，目标是让文件系统结构恢复到可解释的一致状态。
#. Journal replay 不保证恢复应用最后一次用户态写入的全部数据内容。
#. Ext4 常见 data mode 包括 ordered、writeback 和 journal，具体默认值与能力以目标内核和挂载实例为准。
#. ``data=ordered`` 通常只日志元数据，并要求相关新数据在提交暴露元数据前按协议写出。
#. Ordered mode 主要防止恢复后新元数据指向未经本次写入初始化的旧磁盘内容，不等于每次 write 都已持久化。
#. ``data=writeback`` 对数据与元数据提交顺序约束更弱，性能和恢复后文件内容语义不同。
#. ``data=journal`` 把普通文件数据也纳入日志，提供更强数据事务顺序，但增加写放大并改变部分 I/O 能力。
#. 日志模式只是一层保证；barrier、flush、FUA、设备缓存和控制器行为仍决定写入顺序是否真实落到介质。
#. 禁用或破坏写屏障可能让文件系统认为 commit 已持久，而设备仍可能在掉电时丢失关键顺序。
#. ``fsync()`` 应把目标文件相关数据和必要元数据推进到文件系统定义的稳定边界。
#. 新建文件、rename、目录项和 inode 元数据之间的 fsync 需求必须按应用持久化协议设计。
#. 只 fsync 文件不总能替代对父目录持久化目录项变化的需求，精确语义取决于操作和文件系统保证。
#. ``fdatasync()`` 侧重数据和影响数据读取的必要元数据，仍不是无条件只写数据块。
#. Close 不等同于 fsync；close 也不能自动把所有异步 writeback 错误转成成功持久化。
#. Writeback error 可能在后续 fsync、close 或其它同步接口上报告，应用必须处理延迟错误。
#. Metadata checksum 用于检测 ext4 部分元数据结构损坏，不能代替数据备份或端到端应用校验。
#. Journal checksum 帮助验证日志块和事务，具体算法与格式由 feature bits 决定。
#. Orphan 处理用于在 unlink/truncate 与崩溃之间维护需要继续清理的 inode 状态，具体实现会随 ext4 演进。
#. Unlink 只解除目录项和链接计数关系；已打开文件仍可继续通过 ``struct file`` 访问，最后引用结束后才最终释放空间。
#. Truncate 需要同时更新文件大小、extent、块引用、Page Cache 和日志事务。
#. Rename 的原子命名语义不自动保证应用数据内容已经持久化；部署协议仍需明确同步顺序。
#. Ext4 的 multiblock allocator、预分配和 locality group 等优化帮助连续分配，具体内部对象具有版本差异。
#. Fragmentation 可能来自长期小随机写、交错文件增长、快满文件系统、预留失配和空间回收模式。
#. 文件看起来连续不证明块设备物理介质连续；extent 只描述文件系统逻辑块到设备块的映射。
#. SSD、thin provisioning、RAID 和虚拟块设备还会在 ext4 之下重新映射地址。
#. ``df`` 统计可用块不等于某次分配一定成功，还需考虑保留块、配额、inode、journal 和具体分配约束。
#. ``ENOSPC`` 可能在 writeback 才出现，因为 delayed allocation 把真实分配推迟了。
#. ``tune2fs``、``dumpe2fs``、``debugfs`` 等工具读取或修改 ext4 元数据时必须区分在线/离线安全边界。
#. ``e2fsck`` 通常面向未挂载或只读受控场景；不能把在线强制 fsck 当作普通运行时诊断。
#. 文件系统发生严重错误时可按挂载策略继续、remount-ro 或 panic，具体由 errors 选项和实现决定。
#. Remount read-only 是阻止进一步修改的保护动作，不表示已有数据损坏已经自动修复。
#. Ext4 故障诊断应保存 mount options、feature bits、journal 状态、I/O error、设备 cache/flush 和应用同步调用。
#. 最稳定写入阅读顺序是：Page Cache 脏范围 → delayed allocation/块映射 → extent 更新 → JBD2 事务 → data mode 顺序 → writeback/commit → fsync 与设备持久化。

必背路径
--------

追加写入：

::

   用户 write 文件尾部
   → Page Cache 接收并标记 dirty
   → inode 记录逻辑范围增长
   → delayed allocation 暂不确定物理块
   → writeback 或 fsync 触发真实分配
   → multiblock allocator 选择 block group 与连续空间
   → 建立或扩展 extent
   → inode、bitmap、group 元数据进入 JBD2 事务
   → 提交日志并写出数据与元数据

JBD2 元数据事务：

::

   ext4 开始元数据修改
   → 取得 journal handle 与 credits
   → 对目标 metadata buffer 取得写权限
   → 修改 inode / bitmap / extent / directory block
   → 标记 journal dirty metadata
   → transaction 进入 commit
   → 日志描述、数据块和 commit record 按协议写出
   → 后续 checkpoint 更新 home location

崩溃恢复：

::

   系统在事务期间崩溃
   → 重新挂载读取 journal
   → 扫描日志序列和校验
   → 找到完整 commit 的事务
   → 重放其元数据更新
   → 忽略不完整事务
   → 清理 orphan 等待处理状态
   → 文件系统恢复到结构一致状态

应用持久化：

::

   写临时文件
   → fsync / fdatasync 临时文件
   → rename 切换目录项
   → 必要时 fsync 父目录
   → 检查每一步返回值
   → 依赖文件系统日志与设备 flush 顺序
   → 崩溃后验证应用协议所需状态

诊断延迟分配 ENOSPC：

::

   write 先返回成功
   → 后续 writeback / fsync 报错
   → 检查 df、inode、quota 和 reserved blocks
   → 检查 delayed allocation 与预分配
   → 检查 ext4/jbd2 内核日志
   → 检查块设备 I/O 错误
   → 修正空间预算与错误处理

必须区分
--------

* Extent 与 Block group：Extent 描述文件映射；block group 是空间、位图和 inode 管理的局部域。
* Delayed allocation 与空间保证：延迟分配改善布局，但 write 成功时不保证未来一定能取得物理块。
* Journal 一致性与数据持久化：JBD2 主要保护元数据事务；数据内容保证还取决于 data mode、同步调用和设备顺序。
* Ordered mode 与同步写：Ordered 约束数据和元数据提交顺序，不表示每次 write 返回时数据已落盘。
* Rename 原子性与崩溃持久性：Rename 提供运行时命名切换原子性；掉电后的目录项和文件数据仍需同步协议保证。
* 文件系统恢复与应用事务恢复：Journal replay 让 ext4 结构可解释；应用跨文件业务状态仍需自己的事务或恢复机制。

一句话结论
----------

Ext4 用 extent 与延迟分配改善空间映射，用 JBD2 保护元数据事务，但应用数据持久化仍必须结合 data mode、fsync 顺序和真实设备写入保证。
