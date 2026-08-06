第039章：文件描述符、句柄与内核对象
==================================

本章必须记住
------------

#. 文件描述符 ``fd`` 是当前进程文件描述符表中的非负整数索引，不是文件本身，也不是内核对象地址。
#. 相同 fd 数值在不同进程中可以指向完全不同的对象，因为每个进程或共享任务组使用自己的 ``files_struct`` 语境。
#. ``0``、``1``、``2`` 只是惯例上的标准输入、标准输出和标准错误；它们仍然是普通 fd 表项，可以被关闭和重新分配。
#. fd 可以表示普通文件、目录、socket、pipe、字符设备、eventfd、timerfd、signalfd 和 epoll 等对象。
#. 用户态统一使用 ``read``、``write``、``poll``、``ioctl`` 和 ``close``，内核通过 fd 后面的对象恢复具体语义。
#. 当前任务通过 ``current->files`` 找到 ``files_struct``，再通过 ``fdtable`` 按 fd 索引找到 ``struct file``。
#. ``fdtable`` 中的 ``fd`` 指针数组保存 fd 到 ``struct file`` 的映射，``open_fds`` 位图记录已占用槽位。
#. ``close_on_exec`` 位图记录哪些 fd 在成功 ``exec`` 新程序映像时自动关闭。
#. fd 查找必须同时检查索引范围、槽位是否打开以及 ``struct file`` 在操作期间是否仍然存活。
#. 内核常使用 ``fdget``、``fdput`` 或相关 helper 包装 fd 查找与临时引用规则，不能长期保存一个未持有引用的裸 ``struct file *``。
#. ``struct file`` 表示一次打开的文件对象，也称 open file description 的内核载体之一；它不是磁盘文件内容。
#. ``struct file`` 保存访问模式、状态标志、当前位置、路径或 inode 关系、``private_data``、操作表和引用状态。
#. ``struct inode`` 表示文件系统对象的元数据身份；多个 ``struct file`` 可以指向同一个 inode，但拥有不同打开标志和文件偏移。
#. ``file->f_op`` 指向 ``struct file_operations``，决定该打开对象实际支持哪些操作。
#. fd 到行为的分发有两层：fdtable 把整数变成 ``struct file``，``f_op`` 再把通用系统调用分发到对象专属实现。
#. 同一个 ``read(fd, ...)`` 可以进入普通文件、pipe、socket、procfs、设备或 eventfd 的不同实现。
#. ``read_iter``、``write_iter``、``poll``、``unlocked_ioctl``、``mmap`` 和 ``release`` 等回调是否存在，决定对象支持哪些行为。
#. ``private_data`` 常把 ``struct file`` 连接到驱动、socket 或匿名 inode 的私有状态，具体类型由创建该 file 的代码决定。
#. 打开或创建对象时，内核通常先分配空 fd 槽位，再创建或取得 ``struct file``，最后用 ``fd_install`` 一类路径安装表项。
#. fd 分配、对象创建和表项安装之间任一步失败，都必须回滚已占用槽位和对象引用。
#. ``dup``、``dup2`` 和 ``dup3`` 创建新的 fd 数值，但新旧 fd 通常指向同一个 ``struct file``。
#. 指向同一 ``struct file`` 的 fd 通常共享文件偏移和部分打开状态；其中一个 fd 改变偏移会影响其它共享者。
#. 普通 ``fork`` 会得到新的 fd 表语境，但父子表项仍引用相同的 ``struct file``；使用 ``CLONE_FILES`` 的任务直接共享 ``files_struct``。
#. ``close(fd)`` 首先从当前 fd 表移除表项并释放该引用；只有最后一个引用消失时，``struct file`` 才进入最终释放和 ``release`` 路径。
#. fd 数值可以在关闭后立即复用，因此长期异步逻辑不能只保存整数 fd 并假设它仍指向原对象。
#. ``FD_CLOEXEC`` 是 fd 表项属性；``O_CLOEXEC`` 在创建 fd 时原子设置该属性，能避免多线程 ``fork`` 与 ``exec`` 之间的泄漏竞态。
#. 先创建 fd、再单独调用 ``fcntl(F_SETFD, FD_CLOEXEC)`` 存在窗口，另一个线程可能在窗口中执行 fork/exec。
#. fd 泄漏会让对象、挂载、socket、pipe 或设备引用跨过预期生命周期，表现为资源不能释放或子进程继承意外权限。
#. ``/proc/<pid>/fd`` 可以观察进程当前 fd 链接，``/proc/<pid>/fdinfo`` 可以补充 flags、位置和对象特定信息。
#. fd 链接文本只是用户态可读表示；实际类型和行为仍要追踪 ``struct file``、``f_op`` 与私有对象。

必背路径
--------

从 fd 到实际操作：

::

   系统调用收到整数 fd
   → current 找到当前任务
   → current->files 找到 files_struct
   → fdtable 检查索引和 open_fds
   → 取得并保护 struct file
   → 检查访问模式和对象状态
   → 读取 file->f_op
   → 调用 read_iter、poll、ioctl 或其它对象回调
   → fdput 归还临时引用

创建并发布一个 fd：

::

   创建或取得内核对象
   → 构造 struct file 并安装 f_op
   → 分配空 fd 槽位
   → 设置 O_CLOEXEC 等表项属性
   → fd_install 把 struct file 放入表项
   → 把整数 fd 返回用户态
   → 失败时释放槽位和 file 引用

关闭对象：

::

   close(fd)
   → 从当前 fdtable 移除表项
   → fd 数值可以被后续分配复用
   → 减少 struct file 引用
   → 仍有 dup、fork 或内核引用则继续存活
   → 最后一个引用释放
   → 调用对象 release 并销毁私有状态

``fork``、``dup`` 与 ``exec``：

::

   dup 创建新 fd 指向同一 struct file
   → fork 复制表项引用或按 CLONE_FILES 共享文件表
   → 所有引用共享打开对象状态
   → exec 关闭标记 FD_CLOEXEC 的表项
   → 未标记表项进入新程序映像

必须区分
--------

* fd 与 ``struct file``：fd 是进程表中的整数索引；``struct file`` 是内核中的打开对象。
* ``struct file`` 与 ``struct inode``：``file`` 表示一次打开关系；``inode`` 表示文件系统对象身份和元数据。
* fd 表共享与 file 对象共享：任务可以拥有不同 ``files_struct``，其中的表项仍可指向同一个 ``struct file``。
* ``dup`` 与重新打开：``dup`` 共享同一个打开对象和偏移；重新 ``open`` 通常创建新的 ``struct file``。
* ``close`` 与对象立即销毁：``close`` 只释放当前 fd 引用；其它 fd、进程或内核引用仍可让对象存活。
* fd 数值与对象身份：fd 关闭后可立即复用，整数相同不代表对象相同。
* ``FD_CLOEXEC`` 与 ``O_CLOEXEC``：前者是表项状态；后者要求创建时原子设置，避免多线程继承竞态。

一句话结论
----------

fd 是用户态索引，``struct file`` 是内核打开对象，``file_operations`` 决定实际行为；dup、fork、exec 和 close 只是在改变对象引用与 fd 表边界。
