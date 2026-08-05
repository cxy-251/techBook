第082章：脏页、回写与 Flusher 线程
=================================

本章必须记住
------------

#. Buffered write 通常先修改 Page Cache 并把 folio 标记为 dirty，把实际存储 I/O 延后到 writeback 阶段。
#. Dirty folio 表示内存中的文件数据领先于后端存储，系统必须保留它直到成功写回或明确报告错误。
#. 写入者快速返回的代价没有消失，而是转移到后台回写、写入限速、显式同步、回收或设备拥塞阶段。
#. Folio 被标记 dirty 时，相关 inode 会进入 writeback 管理范围，使内核能按文件和后端设备组织写出。
#. 通用 writeback 以 ``struct address_space``、inode、superblock 和 ``bdi_writeback`` 等对象组织待写数据。
#. BDI 表示 backing device information，把 Page Cache 脏数据与后端设备能力、带宽估计和回写队列关联起来。
#. Cgroup writeback 可以进一步把脏页和 I/O 归属到 memory cgroup、I/O cgroup 等控制域，具体支持取决于文件系统。
#. ``bdi_writeback`` 中的 dirty、I/O、more-I/O 等队列用于区分等待写回、正在处理和仍需继续处理的 inode。
#. Writeback worker 通常在可睡眠的内核线程或 workqueue 上下文执行，能够进入文件系统和块层路径。
#. Flusher worker 负责把批量脏 inode 转换成文件系统 ``writepages``、``write_folio`` 等操作。
#. 文件系统决定延迟分配、块映射、日志、校验、压缩和实际 I/O 提交方式，通用 writeback 不能代替具体文件系统语义。
#. Writeback 有四类主要触发源：周期和脏页年龄、脏页阈值、显式同步、内存回收压力。
#. ``dirty_writeback_centisecs`` 控制周期性回写检查间隔，``dirty_expire_centisecs`` 控制脏数据达到多大年龄后适合周期写出。
#. ``dirty_background_ratio`` 或 ``dirty_background_bytes`` 控制后台回写开始积极工作的脏内存水平。
#. ``dirty_ratio`` 或 ``dirty_bytes`` 控制写入者被迫限速或参与平衡的更高脏内存水平。
#. Ratio 与 bytes 配置表达同类阈值的两种形式，目标系统实际生效值必须从当前 sysctl 读取。
#. 阈值根据可用于脏页计算的内存和当前写回域变化，不应把 ratio 简单乘以整机物理内存得到绝对结论。
#. ``balance_dirty_pages()`` 一类路径把脏页压力反馈给产生脏数据的任务，使写入速度逐步接近后端消化能力。
#. Writer throttling 不是错误；它是防止内存被无限脏页占满并让回写失控的流量控制机制。
#. 当后端设备变慢、队列拥塞或文件系统写回受阻时，写入者限速时间会增加并形成延迟尖峰。
#. ``Dirty`` 表示尚未进入或完成写回的脏内存，``Writeback`` 表示当前正在回写的内存。
#. Dirty 持续增长且 Writeback 很低，可能表示回写未及时启动、文件系统受阻或统计归属需要进一步确认。
#. Dirty 与 Writeback 都高且设备利用率饱和，通常表示后端消化速度低于脏数据生成速度。
#. 写回开始时，folio 会进入 writeback 状态；I/O 完成后清除 writeback，并根据并发写入情况保持 clean 或重新 dirty。
#. Writeback 期间新的写入可能再次修改同一 folio，因此一次 I/O 完成不代表所有后续修改都已持久化。
#. 文件系统必须使用锁、folio 状态和 writeback 序列协调并发修改、写出和截断。
#. 后台回写通常不要求等待全部写出完成，只以降低脏页压力和推进队列为目标。
#. ``WB_SYNC_NONE`` 一类模式强调异步推进；``WB_SYNC_ALL`` 一类模式用于需要等待完成的同步路径。
#. ``fsync()`` 和 ``fdatasync()`` 会触发或等待目标文件数据写回，并按各自语义处理必要元数据。
#. ``sync()`` 面向更广范围的文件系统脏数据，不应被用作单个事务持久化协议的替代品。
#. 写回完成和数据到达设备易失缓存不是完全相同的层次；稳定存储语义还可能需要 cache flush、FUA 或文件系统日志提交。
#. 文件系统和块设备必须正确传播 flush 与完成语义，应用才能依赖 ``fsync`` 的持久化承诺。
#. 异步 writeback 错误可能在原始 ``write`` 返回后发生，内核会把错误记录并在后续 ``fsync``、``close`` 或其它接口上报告。
#. 应用必须检查 ``fsync`` 等同步接口返回值，不能因为早先 ``write`` 成功就忽略延迟 I/O 错误。
#. Dirty file folio 比 clean file folio 更难回收，因为它需要先写回或等待写回。
#. Direct reclaim 遇到大量脏页时，内存分配者可能间接等待存储 I/O，导致与写调用无关的线程出现延迟。
#. 回收路径不应任意承担所有文件系统写回；具体何时启动、等待或跳过受 GFP、上下文和 writeback 规则限制。
#. ``GFP_NOFS``、``GFP_NOIO`` 会限制回收递归进入文件系统或 I/O，可能降低回收脏页的能力。
#. Memcg 达到限制时，局部脏页和 writeback 压力可以在整机内存仍充足时使 cgroup 内任务被限速。
#. Backing device 的带宽估计用于分配脏页预算和写入者限速，设备性能变化会影响平衡点。
#. 多设备系统中，应按 BDI、文件系统、块设备和 cgroup 分开观察，不能只看整机 Dirty 总量。
#. 网络文件系统、FUSE、设备映射和远端存储的 writeback 延迟来源可能不在本地块设备。
#. 文件系统冻结、只读切换、设备错误和 journal abort 会改变 writeback 能否前进及错误传播方式。
#. 回写线程 CPU 使用率低不代表没有拥塞，它可能正在等待块 I/O、文件系统锁或远端响应。
#. 高 ``writeback`` 时间不一定表示设备吞吐高，也可能表示 I/O 长时间未完成。
#. ``/proc/meminfo`` 提供 Dirty、Writeback；``/proc/vmstat`` 提供 dirty、writeback 和限速相关累计计数。
#. 累计计数必须在固定时间窗口计算增量，并与设备吞吐、I/O 延迟和应用写速率对齐。
#. Tracepoint 可以观察 dirty、writeback、writeback queue 和块 I/O 时间线，具体事件名称取决于内核版本和配置。
#. 调试延迟尖峰时，应同时记录写入者被限速时间、flusher 活动、文件系统 writeback、块层排队和设备完成时间。
#. 调整 dirty ratio 只能改变成本何时支付和缓冲规模，不能提高后端设备的真实持续写入能力。
#. 提高阈值可能延长前台快速写入阶段，也会增加之后集中回写、崩溃时未持久化数据和回收延迟风险。
#. 降低阈值可能让回写更平滑，也会更早限制突发写入，并增加持续后台 I/O。
#. 正确修复应先确认瓶颈属于脏页预算、文件系统、块层、设备、cgroup 还是应用同步策略。

必背路径
--------

Buffered write 到后台回写：

::

   用户 write
   → 修改 Page Cache folio
   → 标记 folio dirty
   → inode 进入 writeback 脏队列
   → 周期或 background 阈值触发 worker
   → 按 BDI、superblock、inode 选择写回范围
   → 文件系统生成 I/O
   → 块层和设备完成写入
   → 清除 writeback 或根据新修改重新 dirty

写入者限速：

::

   任务持续产生 dirty folio
   → 统计当前 writeback 域脏页量
   → 超过 background 阈值时唤醒 flusher
   → 接近或超过 writer 阈值
   → balance_dirty_pages 计算允许速率
   → 当前任务睡眠或降低生成速度
   → 脏页下降后继续写入

显式同步：

::

   用户调用 fsync / fdatasync
   → 标记目标文件和范围需要同步
   → 启动未提交 dirty folio 的 writeback
   → 等待相关 writeback 完成
   → 提交必要文件系统元数据或日志
   → 执行需要的设备 flush
   → 检查延迟 writeback 错误
   → 返回结果

回收遇到脏页：

::

   分配路径需要回收物理页
   → 扫描到 dirty file folio
   → 判断当前上下文是否允许写回或等待
   → 启动、等待或跳过 writeback
   → I/O 完成后 folio 变 clean
   → 从 Page Cache 移除
   → 释放物理页

诊断写入延迟：

::

   记录应用 write / fsync 延迟
   → 采样 Dirty 与 Writeback 增量
   → 观察 balance_dirty_pages 和 flusher 活动
   → 按 BDI / cgroup 确认脏页归属
   → 对齐文件系统 writeback trace
   → 对齐块层队列与设备完成延迟
   → 判断成本在哪一层积压

必须区分
--------

Dirty 与 Writeback
   Dirty 表示等待提交的修改；writeback 表示正在向后端提交，folio 仍可能被再次写脏。

后台回写与写入者限速
   前者由 worker 消化脏页；后者把压力反馈给产生脏数据的任务。

``write`` 成功与 ``fsync`` 成功
   前者通常完成缓存写入；后者还要等待数据、必要元数据和延迟错误处理。

Writeback 完成与稳定介质
   I/O 完成需要结合文件系统日志、设备缓存 flush 和硬件语义才能形成持久化结论。

全局脏页与局部写回域
   整机 Dirty 是汇总值；实际限速可能发生在某个 BDI、memcg 或文件系统域内。

调高阈值与提高吞吐
   阈值改变缓冲和延迟分布，不会突破后端持续写入能力。

一句话结论
----------

Writeback 把 buffered write 形成的脏内存按后端设备和文件组织起来，后台线程负责提交，脏页阈值则把设备消化能力反向施加给写入者。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 17，Page Cache, Writeback, Reclaim, Compaction, and OOM；
* AIBook 章节：Chapter 82，Dirty Pages, Writeback, and Flusher Threads；
* 源文件：``docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_082_Dirty_Pages_Writeback_and_Flusher_Threads.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_082_Dirty_Pages_Writeback_and_Flusher_Threads.md>`_。