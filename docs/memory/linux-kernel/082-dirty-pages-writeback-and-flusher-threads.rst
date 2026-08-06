第082章：脏页、回写与 Flusher 线程
=================================

核心知识点
----------

Dirty folio 是延迟的存储写入
   Buffered write 先修改 Page Cache，再把 folio 标记为 dirty。内存中的文件内容已经更新，后端存储仍可能保留旧版本。

写入成本只是被推迟
   前台 ``write()`` 快速返回后，设备 I/O、文件系统排序、日志提交和错误处理会在后台回写、显式同步、写入限速或内存回收阶段发生。

Writeback 按文件和后端组织
   ``address_space`` 管理文件缓存，inode 归属文件对象，``bdi_writeback`` 把脏 inode、写回队列、带宽估计和后端设备联系起来。

Flusher worker 执行批量提交
   Writeback worker 在可睡眠上下文中选择待写 inode，进入 ``writepages``、``write_folio`` 等文件系统路径，再把 I/O 交给块层或其它后端。

文件系统决定实际落盘语义
   通用 writeback 负责调度和限速，延迟分配、块映射、日志、校验、压缩及远端提交由具体文件系统实现。

回写有四类触发源
   脏数据年龄和周期检查、后台脏页阈值、``fsync`` 等显式同步，以及内存回收压力都可以启动 writeback。

后台阈值与写入者阈值不同
   ``dirty_background_*`` 促使 flusher 更积极工作；``dirty_*`` 的更高边界会让产生脏页的任务进入 ``balance_dirty_pages()`` 一类限速路径。

Writer throttling 是流量控制
   限速把脏页生成速率压到接近后端消化能力，防止内存被无界脏数据占满。设备或文件系统变慢时，限速会表现为前台写入延迟尖峰。

Dirty 与 writeback 可以并存变化
   Folio 进入 writeback 后，新的写入仍可能再次把它标记为 dirty。一次 I/O 完成只提交了被选中的版本，不保证对象永久保持 clean。

同步模式决定是否等待
   后台写回以推进队列和降低脏页量为目标；``WB_SYNC_ALL`` 一类同步路径还要求等待相关写入完成并检查错误。

持久化跨越多个层次
   数据写入设备队列不等于进入稳定介质。文件系统日志、块设备 flush、FUA 和硬件缓存语义共同决定 ``fsync()`` 的承诺。

延迟错误必须向上报告
   原始 ``write()`` 成功后，异步 I/O 仍可能失败。Mapping 或文件状态会记录错误，并由后续 ``fsync()`` 等同步接口返回。

脏页会降低回收效率
   Clean file folio 可以直接丢弃；dirty folio 必须先写回或等待写回。Direct reclaim 遇到脏页时，分配任务可能间接承担存储延迟。

写回域可以局部拥塞
   多设备、cgroup writeback、网络文件系统和远端存储会形成各自的脏页预算与瓶颈。整机 Dirty 总量不能说明压力具体发生在哪个域。

关键路径
--------

Buffered write 到后台回写：

::

   用户 write 修改 Page Cache
   → folio 标记 dirty
   → inode 进入 writeback 脏队列
   → 周期、阈值或压力触发 worker
   → 按 bdi_writeback 和 superblock 选择 inode
   → 文件系统生成 I/O
   → 后端完成写入
   → 清除 writeback 或因新修改重新 dirty

写入者限速：

::

   任务持续生成 dirty folio
   → 统计当前 writeback 域脏页量
   → 超过后台阈值时唤醒 flusher
   → 接近写入者阈值
   → balance_dirty_pages 计算允许速率
   → 当前任务等待或减速
   → 脏页下降后继续

显式同步：

::

   fsync / fdatasync
   → 确定目标文件和范围
   → 启动尚未提交的 writeback
   → 等待相关 I/O 完成
   → 提交必要元数据或日志
   → 执行设备稳定存储协议
   → 检查并返回延迟错误

回收脏文件页：

::

   Reclaim 扫描到 dirty folio
   → 判断当前 GFP 和上下文是否允许写回
   → 启动、等待或跳过该 folio
   → 写回完成后变为 clean
   → 从 Page Cache 移除
   → 释放物理页

概念辨析
--------

* Dirty 与 writeback：Dirty 表示待提交修改；writeback 表示正在提交，期间仍可能产生新 dirty 状态。
* 后台回写与写入者限速：前者由 worker 消化脏页；后者把后端压力反馈给产生脏数据的任务。
* ``write`` 成功与 ``fsync`` 成功：前者通常只完成缓存语义；后者还要等待提交、稳定存储和错误传播。
* I/O 完成与持久化完成：请求完成需要结合文件系统日志和设备缓存协议才能形成稳定存储结论。
* 全局脏页与局部写回域：整机统计是汇总值；实际拥塞可能只发生在某个 BDI、文件系统或 memcg。
* 调高阈值与提高吞吐：阈值只改变缓冲规模和成本支付时机，不能提高后端持续写入能力。

本章结论
--------

Writeback 把 Page Cache 中的脏数据按文件和后端设备组织起来，flusher 负责提交，脏页阈值则把后端消化能力反向约束到写入者。
