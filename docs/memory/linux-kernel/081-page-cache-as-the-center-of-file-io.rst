第081章：Page Cache 是文件 I/O 的中心
=====================================

核心知识点
----------

Page Cache 按文件偏移缓存数据
   普通文件的 buffered I/O 通常先访问内存中的文件缓存。缓存对象属于 inode 的 ``struct address_space``，不是某个文件描述符私有的数据副本。

``address_space`` 连接文件与缓存页
   ``struct file->f_mapping`` 通常指向 inode 的 ``address_space``。其中的 ``i_pages`` 使用索引结构把文件偏移关联到 folio，文件系统则通过 ``address_space_operations`` 提供填充和写回能力。

Folio 是缓存与回收的管理单位
   ``struct folio`` 可以表示一个或多个连续基础页。文件索引描述它对应哪个文件范围，PFN 描述它位于哪些物理页框，两者不能混为一谈。

缓存状态决定后续动作
   ``uptodate`` 表示内存内容可用于读取；``dirty`` 表示内存内容领先于后端；``writeback`` 表示脏内容正在提交。Clean folio 通常可以直接服务读取，也更容易在压力下丢弃。

Buffered read 先查缓存
   命中且 uptodate 时，读路径只需从 folio 复制数据。未命中或内容无效时，文件系统通过 ``read_folio``、readahead 等路径从后端填充缓存。

Readahead 是推测性填充
   顺序访问会促使内核提前读取后续范围，以减少未来缓存缺失。预读数据可能未被使用，并可在内存压力下被回收。

Buffered write 先形成脏缓存
   写路径定位或建立 folio，把用户数据复制到缓存并标记 dirty。普通 ``write()`` 成功通常只说明数据已进入内核缓存语义，不表示已经持久化。

同步接口建立更强边界
   ``fsync()``、``fdatasync()`` 需要启动或等待相关 writeback，并按文件系统语义提交必要元数据、日志和设备缓存。延迟 I/O 错误可以在这些接口上返回。

Buffered I/O 与 mmap 共享文件缓存
   ``MAP_SHARED`` 文件映射修改共享 folio并形成 dirty 状态；``MAP_PRIVATE`` 写入通常通过 COW 转成匿名私有页，不写回原文件。

文件范围变化必须同步缓存状态
   Truncate、hole punching 和失效操作需要调整 Page Cache、页表映射与 writeback。已经取得的 folio 指针仍需要锁和引用保证存活。

Direct I/O 是另一套数据路径
   ``O_DIRECT`` 尝试绕过普通 buffered data path，但仍必须与 Page Cache、文件大小和映射保持一致。是否回退以及如何失效缓存由文件系统决定。

Page Cache 占用不等于泄漏
   Clean file cache 是可复用的性能资源。只有缓存持续 refault、脏页无法写回或对象无法回收时，才说明缓存行为正在伤害系统。

关键路径
--------

Buffered read 命中：

::

   fd 定位 struct file
   → f_mapping 定位 address_space
   → 文件偏移转换为缓存索引
   → i_pages 找到 folio
   → 检查 folio uptodate
   → 从内存复制数据
   → 更新文件位置

Buffered read 未命中：

::

   缓存中没有可用 folio
   → 分配或取得缓存 folio
   → read_folio / readahead 提交后端读取
   → I/O 完成并设置 uptodate
   → 返回通用读路径
   → 复制给用户

Buffered write 与回写：

::

   定位文件范围对应 folio
   → 准备写入并复制用户数据
   → 更新文件大小和必要元数据
   → 标记 folio dirty
   → write 返回
   → 后续 writeback 提交文件系统与设备

文件同步：

::

   fsync / fdatasync
   → 找到目标脏范围
   → 启动并等待数据 writeback
   → 提交必要元数据或日志
   → 执行设备稳定存储协议
   → 返回成功或延迟错误

概念辨析
--------

* 文件描述符与 Page Cache：文件描述符是进程句柄；Page Cache 由 inode 的 ``address_space`` 管理，可被多个打开实例共享。
* ``uptodate`` 与 ``dirty``：前者表示内容可读；后者表示内容尚未完全同步到后端。
* ``dirty`` 与 ``writeback``：Dirty 等待提交；writeback 正在提交，并可能因并发写入再次变脏。
* 写入成功与持久化成功：``write`` 通常完成缓存写入；持久化需要同步接口、文件系统和设备共同保证。
* Buffered I/O 与 Direct I/O：前者以 Page Cache 为中心；后者尝试直接进入后端，但仍受缓存一致性协议约束。
* Clean cache 与空闲内存：Clean cache 占用物理页，却通常可以按需丢弃并从文件重新构造。

本章结论
--------

普通文件 I/O 以 ``address_space`` 和 Page Cache 为中心：读先复用缓存，写先形成脏缓存，存储设备成本主要在缓存填充、回写和同步阶段支付。
