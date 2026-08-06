第101章：Buffered I/O 与 Page Cache 路径
========================================

本章必须记住
------------

#. Buffered I/O 是普通文件 ``read``、``write``、``pread``、``pwrite`` 的常见默认路径，文件数据先经过 Page Cache。
#. Page Cache 的作用不是简单“缓存磁盘”，而是把文件数据纳入文件偏移索引、预读、脏页、回写、回收和 mmap 共享体系。
#. ``struct file`` 表示打开实例，``struct inode`` 表示文件对象，``struct address_space`` 表示文件内容到 Page Cache 的映射。
#. ``inode->i_mapping`` 通常指向该文件的 ``address_space``；``file->f_mapping`` 让打开实例进入同一映射。
#. ``address_space`` 中的 ``i_pages`` 一类索引结构按文件页索引保存 folio，具体实现细节具有版本差异。
#. 现代内核大量使用 ``struct folio`` 管理一个或多个基础页；稳定语义仍是“某段文件偏移对应的缓存对象”。
#. ``file_operations.read_iter``、``write_iter`` 是 VFS 打开实例级入口，普通文件系统常继续复用 filemap、iomap 或 generic helper。
#. 复用 ``generic_file_*`` 不代表所有文件系统具有相同的块映射、日志、COW、错误和持久化语义。
#. Buffered read 的核心是：文件 offset 转换为 mapping index，再查询对应 folio 是否存在且 ``uptodate``。
#. Folio 存在不等于内容可用；未完成读入、I/O 错误或失效状态仍可能要求等待或重新填充。
#. 缓存命中且内容 ``uptodate`` 时，内核可以直接把数据复制到用户缓冲区，无需本次访问后端设备。
#. 缓存未命中时，内核需要创建或取得 folio，并通过 ``read_folio``、``readahead``、iomap 等路径向后端提交读取。
#. ``uptodate`` 表示该缓存范围可用于满足读取，不表示它刚刚来自物理磁盘。
#. 后端可能是本地块设备、网络文件系统、tmpfs、DAX 之外的普通映射或其它实现，不能把 miss 机械等同于磁盘访问。
#. Readahead 根据顺序访问迹象提前读取相邻范围，因此底层 I/O 量可以大于本次用户 ``read`` 请求。
#. 预读命中能隐藏设备延迟；错误预读会消耗 I/O、内存和回收带宽并污染缓存。
#. Buffered write 的核心是：准备目标 folio、从用户缓冲区复制、更新文件状态、标记 dirty，之后再回写。
#. ``write_begin``/``write_end`` 是传统 buffered write 的重要文件系统回调边界；iomap 路径可能采用另一组 helper。
#. ``write_begin`` 可以处理部分块预读、块分配准备、文件系统事务和 folio 锁定。
#. ``write_end`` 处理本次已复制字节、文件大小、时间戳、解锁和返回值；具体规则由文件系统实现决定。
#. Folio 被修改后进入 dirty 状态，表示内存内容领先于后端稳定状态。
#. Dirty folio 被提交后进入 writeback 状态；dirty、writeback、I/O 完成和稳定持久化是不同阶段。
#. 普通 ``write`` 返回成功通常只说明数据已被内核写路径接受，不自动证明设备已经持久化。
#. ``O_SYNC``、``O_DSYNC``、``fsync`` 和 ``fdatasync`` 用于请求更强完成语义，但实际保证仍取决于文件系统和设备顺序能力。
#. ``fsync`` 不只是等待数据页，它还可能要求必要 inode、目录项、日志或文件系统元数据达到恢复所需状态。
#. 文件系统必须把异步 writeback 错误记录到 mapping 错误状态，并通过后续同步接口或打开实例报告。
#. 初次 ``write`` 成功后出现设备错误，错误可能在后续 ``fsync``、``close`` 或其它同步点才对应用可见。
#. ``close`` 不是所有应用都应依赖的唯一持久化错误检查点；关键数据必须显式检查同步接口结果。
#. Page Cache 与文件 ``mmap`` 通常共享同一文件数据缓存，buffered read/write 和映射访问需要保持一致。
#. 对 ``MAP_SHARED`` 文件映射的写入会使对应缓存范围变脏，并进入文件系统回写语义。
#. ``MAP_PRIVATE`` 写入通常形成匿名 COW 页面，不直接修改共享文件 Page Cache。
#. Page Cache folio 也属于内存回收对象；干净且无关键引用的文件页可以被直接丢弃。
#. Dirty 文件页不能直接丢弃，通常要先写回或保留；这会把内存压力转化为 I/O 和业务延迟。
#. 当后台 writeback 跟不上脏页产生速度时，写入线程可能被 dirty throttling 限速。
#. 当后台 reclaim 不足时，业务线程可能进入 direct reclaim，并在分配、读入或写路径上产生明显卡顿。
#. Page Cache 占用高本身不等于内存泄漏；可回收文件缓存是 Linux 利用空闲内存提高性能的正常行为。
#. 判断缓存是否有价值要看复用率、refault、readahead 命中、设备 I/O 减少和回收成本，而不是只看 ``Cached`` 数值。
#. 一次性大扫描可能挤出真正热点页，形成 cache pollution；可通过请求模式、``posix_fadvise`` 等策略评估，而不是默认改用 Direct I/O。
#. ``POSIX_FADV_SEQUENTIAL``、``RANDOM``、``WILLNEED``、``DONTNEED`` 是访问模式提示，不是强制路径合同。
#. ``DONTNEED`` 不能保证正在使用、dirty 或受其它引用保护的 folio 立即消失。
#. Buffered I/O 包含用户缓冲区与 Page Cache 之间的数据复制，CPU 成本需要与缓存复用收益一起衡量。
#. 小请求会放大 syscall、copy、mapping lookup 和锁成本；顺序大请求通常更容易发挥预读和设备吞吐。
#. 请求变大也会增加单次占用、尾延迟和无效预读，必须按实际访问模式测量。
#. Buffered I/O 可以同步调用，也可以由 ``io_uring`` 等接口异步提交；“是否经过 Page Cache”和“提交完成模型”是两个维度。
#. ``io_uring`` 的 buffered read 命中时仍使用 Page Cache，miss 时仍可能进入文件系统读入和阻塞资源路径。
#. ``RWF_NOWAIT`` 一类语义只能在路径会阻塞时快速返回 ``-EAGAIN``，支持范围依文件系统、操作和版本而定。
#. 不能从 API 名称推断实际设备 I/O；需要把 syscall、Page Cache 状态、文件系统回调和块层事件对齐。
#. 观测读路径时应区分用户请求字节、Page Cache 命中字节、预读字节和真实设备完成字节。
#. 观测写路径时应区分应用写入速率、dirty 产生速率、writeback 提交速率和设备完成速率。
#. Buffered I/O 的尾延迟常来自缓存 miss、文件系统锁、内存分配、direct reclaim、脏页限速、writeback 和同步提交。
#. 正确优化顺序是先确认访问模式与真实瓶颈，再调整请求大小、预读、缓存提示、回写或异步深度。
#. 最稳定的源码阅读顺序是：fd → ``struct file`` → ``read_iter/write_iter`` → ``address_space`` → folio 状态 → 文件系统回调 → writeback/块层。

必背路径
--------

Buffered read 命中：

::

   read / pread
   → fd lookup 得到 struct file
   → file->f_op->read_iter
   → 文件 offset 转换为 mapping index
   → 在 address_space 中查找 folio
   → folio 存在且 uptodate
   → 把数据复制到用户缓冲区
   → 更新打开实例位置或返回指定 offset 结果

Buffered read 未命中：

::

   查找目标 folio 未命中或未 uptodate
   → 分配/取得 folio并建立 Page Cache 索引
   → read_folio / readahead / iomap
   → 文件系统把文件范围映射到后端
   → 提交块层或其它后端 I/O
   → I/O 完成并设置 uptodate
   → 唤醒等待者
   → 复制到用户缓冲区

Buffered write：

::

   write / pwrite
   → file->f_op->write_iter
   → 定位目标文件范围
   → write_begin 或 iomap 准备 folio
   → 从用户缓冲区复制数据
   → write_end 更新大小和状态
   → 标记 folio dirty
   → write 返回
   → 后台/阈值/同步/压力触发 writeback
   → 文件系统提交后端 I/O

``fsync`` 收束：

::

   应用调用 fsync
   → 发起并等待相关 dirty data writeback
   → 提交必要文件系统元数据或日志
   → 检查 mapping writeback error
   → 向设备发出所需 flush / ordering
   → 返回成功或错误
   → 应用只在成功后建立对应持久化假设

诊断缓存污染：

::

   记录访问范围与复用距离
   → 观察 Page Cache 增长和 refault
   → 对齐 readahead 与真实消费范围
   → 观察热点页是否被淘汰
   → 检查 reclaim / major fault / 设备 I/O
   → 调整请求大小或访问提示
   → 再评估 buffered 与 direct 路径

必须区分
--------

* Page Cache 命中与后端持久化：命中说明内存中有可读数据；不能证明后端已经包含最新内容。
* ``write`` 返回与数据落盘：Write 通常完成内存缓存修改；持久化需要 writeback、文件系统提交和设备顺序保证。
* Dirty 与 Writeback：Dirty 表示需要写出；writeback 表示正在执行写出，二者都不自动表示稳定完成。
* 用户请求与 Readahead I/O：应用请求一个范围，内核可以提前读取更大相邻范围。
* 缓存占用与内存泄漏：可回收文件缓存是正常内存用途；泄漏需要证明对象无法按预期回收且持续造成损害。
* 缓存策略与异步接口：Buffered/Direct 决定是否使用 Page Cache；同步、AIO、``io_uring`` 决定提交和完成模型。

一句话结论
----------

Buffered I/O 以 ``address_space`` 和 folio 把文件数据纳入 Page Cache、预读、脏页、回写与回收体系，读取命中、写入返回和持久化完成必须分阶段判断。
