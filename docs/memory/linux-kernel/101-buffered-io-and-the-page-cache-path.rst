第101章：Buffered I/O 与 Page Cache 路径
========================================

核心知识点
----------

Buffered I/O 以 Page Cache 为数据中心
   普通文件 ``read``、``write``、``pread`` 和 ``pwrite`` 通常先访问内存中的文件缓存。Page Cache 同时服务系统调用、文件映射、预读、回写和回收。

``address_space`` 表示文件内容映射
   ``struct file`` 表示打开实例，``struct inode`` 表示文件系统对象，``inode->i_mapping`` 与 ``file->f_mapping`` 把文件偏移连接到 ``struct address_space``。

Folio 承载缓存范围
   ``address_space`` 按文件页索引保存 folio。一个 folio 可覆盖一个或多个基础页，稳定语义是“某段文件偏移当前对应的内存对象”。

读路径先判断缓存状态
   文件 offset 被换算为 mapping index。目标 folio 存在且 ``uptodate`` 时可直接复制到用户缓冲区；不存在或内容无效时才进入文件系统读入路径。

Cache miss 通过文件系统填充
   ``read_folio``、``readahead`` 或 iomap 等接口把文件偏移映射到后端。I/O 完成后 folio 变为可读状态，等待者才继续执行。

Readahead 预取相邻范围
   顺序访问迹象会触发超出当前请求范围的预读。命中能隐藏后端延迟，错误预读会占用 I/O、内存和回收带宽。

写路径先修改内存副本
   Buffered write 准备目标 folio、复制用户数据、更新文件大小或时间戳，并把 folio 标记为 dirty。真实后端写入通常发生在之后。

Dirty 与 writeback 是不同阶段
   Dirty 表示内存内容领先于后端；writeback 表示正在提交后端。两者都不等于已经达到稳定介质。

``write`` 返回不表示持久化
   普通写成功通常只证明数据已被写路径接受。稳定性还取决于 writeback、文件系统事务、``fsync``/``fdatasync`` 和设备 flush 顺序。

同步点负责收束延迟错误
   异步回写错误可能在初次写之后出现。文件系统通过 mapping 错误状态等机制，在后续同步接口或打开实例上报告失败。

文件映射共享同一缓存
   普通 buffered I/O 与文件 ``mmap`` 通常访问相同 Page Cache。``MAP_SHARED`` 写入形成共享 dirty 文件页；``MAP_PRIVATE`` 写入通常转为匿名 COW 页。

Page Cache 也是回收对象
   干净且无关键引用的文件页可直接丢弃；dirty 页需要先写回。内存压力因此可能转化为 direct reclaim、写回等待和业务尾延迟。

缓存占用不等于泄漏
   Linux 主动使用空闲内存缓存文件数据。异常判断应依据复用率、refault、回收效率和业务损害，而不是只看 ``Cached`` 数值。

缓存污染来自错误工作集
   一次性大扫描可能淘汰真正热点页。应先分析访问范围、复用距离、预读和 refault，再决定使用访问提示或更换 I/O 路径。

Buffered 与异步是正交维度
   是否经过 Page Cache 属于缓存策略；同步调用、线程池、AIO 或 ``io_uring`` 属于提交与完成模型。异步 buffered I/O 仍然使用 Page Cache。

关键路径
--------

Buffered read 命中：

::

   read / pread
   → fd table 取得 struct file
   → file->f_op->read_iter
   → 文件 offset 转换为 mapping index
   → address_space 查找 folio
   → folio 存在且 uptodate
   → 复制到用户缓冲区
   → 返回字节数

Buffered read 未命中：

::

   目标 folio 不存在或不可用
   → 创建并加入 Page Cache
   → read_folio / readahead / iomap
   → 文件系统映射到后端
   → 提交并等待 I/O
   → folio 标记 uptodate
   → 唤醒等待者
   → 复制数据并返回

Buffered write 与持久化：

::

   write / pwrite
   → 准备并锁定目标 folio
   → 从用户缓冲区复制数据
   → 更新 inode 状态
   → 标记 folio dirty
   → write 返回
   → 后台、阈值、回收或 fsync 触发 writeback
   → 文件系统提交数据和必要元数据
   → 设备完成与 flush
   → fsync 返回最终结果

概念辨析
--------

* **Page Cache 命中与后端持久化**：命中只说明内存中存在可读内容；不能证明后端包含最新版本。
* **Dirty 与 writeback**：Dirty 表示尚待写出；writeback 表示正在写出，稳定完成还在后面。
* **用户请求与预读 I/O**：应用只请求一个范围，内核可能读取更大的相邻范围。
* **缓存占用与内存泄漏**：可回收文件缓存属于正常工作集；泄漏需要证明对象无法按预期释放。
* **Buffered/Direct 与同步/异步**：前者决定 Page Cache 参与程度，后者决定提交线程和完成通知方式。
* **``write`` 与 ``fsync``**：Write 接受数据修改；fsync 收束数据、元数据、回写错误和设备顺序要求。

本章结论
--------

Buffered I/O 通过 ``address_space`` 和 folio 把文件数据纳入缓存、预读、脏页、回写与回收体系。分析性能和正确性时，必须把缓存命中、写入接受、后台写回和稳定持久化分阶段判断。
