第081章：Page Cache 是文件 I/O 的中心
=====================================

本章必须记住
------------

#. 普通文件的 buffered I/O 通常先与内存中的 Page Cache 交互，存储设备主要出现在缓存填充、回写和同步阶段。
#. Page Cache 缓存的是“某个文件映射在某个偏移范围的数据”，不是某个文件描述符私有的数据副本。
#. 同一个 inode 被多个进程或多个 ``struct file`` 打开时，通常共享同一个 ``struct address_space`` 和 Page Cache 内容。
#. ``struct file->f_mapping`` 通常指向 inode 的 ``struct address_space``，它连接文件对象、缓存索引和文件系统回调。
#. ``address_space->i_pages`` 保存文件偏移索引到 folio 的映射，现代内核常使用 XArray 组织该索引。
#. ``struct folio`` 是现代内存管理中常见的缓存单位，可以表示一个或多个连续基础页。
#. 文件偏移通过页大小或 folio 索引定位缓存对象；对象索引和物理页框位置是不同维度。
#. Page Cache 中存在 folio 不代表其中数据一定可读，还必须判断 ``uptodate``、错误和锁定状态。
#. ``uptodate`` 表示内存中的文件数据已经有效，可以作为该文件范围的当前读结果。
#. ``dirty`` 表示内存中的文件数据比后端存储更新，后续必须写回才能完成持久化。
#. ``writeback`` 表示该 folio 的脏数据正在被提交到文件系统或后端设备。
#. Clean file folio 通常可以在内存压力下丢弃，因为后端文件仍保留可重新读取的数据。
#. Dirty folio 不能直接丢弃；必须先完成或安排回写，并处理写回错误。
#. Folio 在 writeback 期间仍可能被新的写入重新标记为 dirty，因此 writeback 完成不保证对象从此保持 clean。
#. Buffered read 先按文件偏移查找 Page Cache，命中且 uptodate 时可以直接从内存复制给用户。
#. 缓存未命中或 folio 未 uptodate 时，内核通过文件系统 ``read_folio``、readahead 等路径填充数据。
#. 第一次顺序读取可能触发 readahead，把后续范围提前放进 Page Cache；后续 read 可以命中预读数据。
#. Readahead 是推测性优化，读入的数据可能从未被应用使用，并可能在压力下被快速回收。
#. Buffered write 通常先把用户数据复制进 Page Cache，再把对应 folio 标记为 dirty。
#. 普通 ``write()`` 返回成功通常表示数据已进入内核文件写入路径，不等于已经到达持久介质。
#. 后续读取同一文件范围通常会看到 Page Cache 中的新数据，即使后端设备仍保存旧内容。
#. ``fsync()``、``fdatasync()``、挂载模式和文件系统日志规则决定更强的同步与持久化边界。
#. ``fsync()`` 不只是启动写回，还需要等待相关数据和必要元数据达到文件系统承诺的稳定状态。
#. 文件系统是否需要发送设备 flush、提交日志或更新元数据，取决于具体文件系统和块设备语义。
#. ``fdatasync()`` 主要要求数据及读取该数据所必需的元数据同步，和 ``fsync()`` 的元数据范围不同。
#. Buffered I/O 与内存映射 I/O 可以共享同一 Page Cache folio，因此 ``read``、``write`` 和 ``mmap`` 可能观察同一文件缓存对象。
#. ``MAP_SHARED`` 文件映射中的写入会修改共享文件页并形成 dirty 状态，最终需要 writeback。
#. ``MAP_PRIVATE`` 写入通常经过 COW 形成匿名私有页，不把修改写回原文件。
#. 文件截断、打洞和失效操作必须从 Page Cache 中删除或调整对应偏移范围，并与并发 I/O、映射和 writeback 协调。
#. Truncate 后仍使用旧映射或旧 folio 指针会形成对象生命周期和页缓存一致性问题。
#. Page Cache folio 可能同时被页表映射、I/O、回写、readahead、回收和文件系统路径引用。
#. 从缓存索引找到 folio 后，调用者必须使用锁、引用和状态检查保证它在操作期间仍有效。
#. Page Cache 的锁定用于保护 folio 状态和 I/O 协议，不等于长期独占整个文件范围。
#. 文件数据锁、inode 锁、Page Cache 锁和页表锁保护不同层次，不能互相替代。
#. ``O_DIRECT`` 表达绕过普通 buffered data path 的意图，但仍需与现有 Page Cache、映射和文件大小保持一致。
#. Direct I/O 是否完全绕过缓存、是否回退 buffered I/O、怎样失效缓存，由文件系统、对齐和接口语义决定。
#. 同一文件范围混用 buffered I/O、direct I/O 和 writable mmap 时，必须遵守文件系统提供的一致性协议。
#. DAX、设备文件、网络文件系统和特殊 ``file_operations`` 可能不走普通 Page Cache 主路径，分析前必须确认文件类型和操作表。
#. Page Cache 占用内存不等于内存泄漏；clean file cache 是 Linux 利用空闲内存提高 I/O 命中率的正常机制。
#. ``MemAvailable`` 比单独的 ``MemFree`` 更接近系统可承受新分配的估计，因为它考虑部分可回收缓存。
#. Page Cache 命中降低设备读取，但仍有内存复制、页表、cache miss 和锁竞争成本。
#. 大量随机访问会降低缓存命中和 readahead 效果，并增加缺页和设备 I/O。
#. 大量顺序访问可能把工作集外的缓存挤出，应用和内核可通过访问提示影响 readahead 与回收策略。
#. ``drop_caches`` 只用于受控诊断，不是修复常态内存压力或应用缓存策略的手段。
#. Page Cache 写入错误可能异步发生，内核需要把错误记录在 mapping 或文件状态中，并在后续同步接口上报告。
#. 一次 ``write`` 成功和后续 ``fsync`` 失败可以同时成立，因为设备或文件系统错误可能在延迟回写阶段出现。
#. 调试普通文件 I/O 时，应先确认是 buffered、direct、DAX 还是 mmap 路径，再判断缓存命中、folio 状态和后端 I/O。
#. 运行证据应结合 ``/proc/meminfo``、fault/I/O 统计、tracepoint、块层延迟和文件系统日志，不能只看应用调用耗时。
#. 最稳定的文件 I/O 分析顺序是：文件描述符 → ``struct file`` → ``address_space`` → folio → 文件系统回调 → 块层或后端。

必背路径
--------

Buffered read 命中：

::

   用户 read
   → fd 找到 struct file
   → file->f_mapping 找到 address_space
   → 文件偏移换算为缓存索引
   → 在 i_pages 查找 folio
   → folio 已 uptodate
   → 从内存复制给用户
   → 更新文件位置与访问状态

Buffered read 未命中：

::

   查找对应 folio 失败或未 uptodate
   → 分配或取得缓存 folio
   → 触发 readahead / read_folio
   → 文件系统生成后端读取
   → I/O 完成并标记 folio uptodate
   → 返回读路径
   → 复制数据给用户

Buffered write：

::

   用户 write
   → 定位或建立 Page Cache folio
   → 文件系统准备写入范围
   → 复制用户数据到 folio
   → 更新文件大小和必要元数据
   → 标记 folio dirty
   → write 返回
   → 后续 writeback 提交后端存储

文件同步：

::

   用户调用 fsync / fdatasync
   → 找到目标文件和脏范围
   → 启动或等待数据 writeback
   → 文件系统提交必要元数据或日志
   → 处理块设备 flush 与错误
   → 达到文件系统承诺的同步边界
   → 返回成功或错误

分析文件缓存问题：

::

   确认文件类型和 I/O 模式
   → 确认地址范围与文件偏移
   → 查 Page Cache 是否命中
   → 判断 uptodate / dirty / writeback
   → 检查 readahead、回写和回收
   → 检查文件系统与块层延迟
   → 将应用耗时放回完整时间线

必须区分
--------

文件描述符与 Page Cache
   文件描述符属于进程句柄表；Page Cache 以 inode 的 ``address_space`` 为中心，可被多个打开实例共享。

``uptodate`` 与 ``dirty``
   前者说明内存数据可用于读取；后者说明内存数据尚未完全同步到后端。

``dirty`` 与 ``writeback``
   Dirty 表示等待提交；writeback 表示正在提交，两者可在并发写入中再次变化。

Buffered write 成功与持久化成功
   ``write`` 通常只完成缓存写入语义；持久化需要同步接口和文件系统、设备共同完成。

Clean cache 与空闲内存
   Clean cache 正在使用物理页，但在需要时通常可以丢弃并重新读取。

Buffered I/O 与 Direct I/O
   前者以 Page Cache 为中心；后者尝试直接进入后端 I/O，但仍需处理缓存一致性和文件系统边界。

一句话结论
----------

普通文件 I/O 的中心是 inode 的 ``address_space`` 与 Page Cache：读先查缓存，写先形成脏缓存，后端设备成本在未命中、回写和同步阶段支付。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 17，Page Cache, Writeback, Reclaim, Compaction, and OOM；
* AIBook 章节：Chapter 81，Page Cache as the Center of File IO；
* 源文件：``docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_081_Page_Cache_as_the_Center_of_File_IO.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_081_Page_Cache_as_the_Center_of_File_IO.md>`_。