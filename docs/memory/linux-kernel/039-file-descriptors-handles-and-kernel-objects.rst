第039章：文件描述符、句柄与内核对象
==================================

核心知识点
----------

fd 是进程文件表中的索引
   文件描述符是当前文件描述符表中的非负整数，不是文件本身，也不是内核对象地址。相同 fd 数值在不同进程中可以指向完全不同的对象。

``files_struct`` 保存进程的 fd 语境
   当前任务通过 ``current->files`` 找到 ``files_struct``，再由 ``fdtable`` 把整数 fd 映射到 ``struct file``。位图同时记录已占用槽位和 close-on-exec 状态。

``struct file`` 表示一次打开关系
   ``struct file`` 保存访问模式、状态标志、文件位置、路径关系、操作表和私有数据。它是一次 open file description 的内核对象，不等于磁盘文件内容。

``struct inode`` 表示文件系统对象身份
   多个 ``struct file`` 可以指向同一个 inode，但各自拥有不同的打开标志和文件偏移。重新 ``open`` 通常产生新的 ``struct file``。

``file_operations`` 决定对象行为
   fdtable 先把整数变成 ``struct file``，``file->f_op`` 再把 ``read``、``write``、``poll``、``ioctl``、``mmap`` 和 ``release`` 分发到对象专属实现。

fd 可以统一表示多种对象
   普通文件、目录、socket、pipe、设备、eventfd、timerfd、signalfd 和 epoll 都能通过 fd 暴露。相同系统调用的实际语义由 ``struct file`` 和操作表决定。

查找 fd 必须保护对象生命周期
   ``fdget()``、``fdput()`` 等 helper 把 fd 查找和临时引用规则封装在一起。取得裸 ``struct file *`` 后长期保存，而没有明确引用，会产生并发关闭后的悬空访问。

fd 发布需要原子完成表项安装
   创建句柄时通常先准备对象和 ``struct file``，再分配空 fd 槽位、设置表项属性并安装映射。任一步失败都要回滚槽位和对象引用。

``dup`` 复制 fd，不复制打开对象
   ``dup``、``dup2`` 和 ``dup3`` 创建新的 fd 数值，但通常仍指向同一个 ``struct file``，因此共享文件偏移和部分打开状态。

``fork`` 与 ``CLONE_FILES`` 共享层次不同
   普通 ``fork`` 复制文件表语境，但父子表项继续引用相同的 ``struct file``；使用 ``CLONE_FILES`` 的任务直接共享同一个 ``files_struct``。

``close`` 只释放当前表项引用
   ``close(fd)`` 先从当前 fd 表移除映射，fd 数值随后可以立即复用。只有所有 fd 和内核引用都消失后，``struct file`` 才进入最终 ``release`` 路径。

Close-on-exec 必须原子设置
   ``FD_CLOEXEC`` 是 fd 表项属性；``O_CLOEXEC`` 在创建 fd 时原子设置它，避免多线程中先创建 fd、后调用 ``fcntl`` 所产生的继承竞态。

关键路径
--------

从 fd 到实际操作：

::

   系统调用收到整数 fd
   → current->files 找到 files_struct
   → fdtable 检查索引和槽位
   → fdget 取得受保护的 struct file
   → 检查访问模式和对象状态
   → 读取 file->f_op
   → 调用对象专属回调
   → fdput 归还临时持有

创建并返回 fd：

::

   创建底层内核对象
   → 构造 struct file 和操作表
   → 分配空 fd 槽位
   → 设置 O_CLOEXEC 等属性
   → 安装 struct file 到 fdtable
   → 返回整数 fd
   → 失败时回滚槽位与引用

关闭路径：

::

   close(fd)
   → 从当前 fdtable 移除表项
   → fd 数值可以被复用
   → 减少 struct file 引用
   → 其它 dup、进程或内核引用继续持有
   → 最后引用消失
   → 执行 release 并销毁私有状态

``dup``、``fork`` 与 ``exec``：

::

   dup 新增 fd 指向同一 struct file
   → fork 复制表项引用或共享 files_struct
   → 共享者继续持有打开对象
   → exec 关闭标记 FD_CLOEXEC 的表项
   → 其余表项进入新程序映像

概念辨析
--------

fd 与 ``struct file``
   fd 是用户态整数索引；``struct file`` 是内核中的打开对象。

``struct file`` 与 ``struct inode``
   ``file`` 表示一次打开关系；``inode`` 表示文件系统对象身份和元数据。

文件表共享与打开对象共享
   两个任务可以拥有不同 ``files_struct``，其中的表项仍然指向同一个 ``struct file``。

``dup`` 与重新 ``open``
   ``dup`` 共享原打开对象和偏移；重新 ``open`` 通常创建独立的打开对象。

``close`` 与对象销毁
   ``close`` 只释放当前 fd 表项的引用；对象是否销毁取决于全部引用是否归零。

fd 数值与对象身份
   fd 关闭后可以立即复用，因此整数再次相同不代表仍是原来的对象。

``FD_CLOEXEC`` 与 ``O_CLOEXEC``
   ``FD_CLOEXEC`` 描述表项状态；``O_CLOEXEC`` 在创建时原子建立该状态，避免并发继承窗口。

本章结论
--------

fd 只是进程文件表中的句柄；``struct file`` 承载打开状态，``file_operations`` 决定行为，而 ``dup``、``fork``、``exec`` 和 ``close`` 改变的是表项与对象引用关系。