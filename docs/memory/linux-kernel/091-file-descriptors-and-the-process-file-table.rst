第091章：文件描述符与进程文件表
================================

本章必须记住
------------

#. 文件描述符 fd 是用户态看到的非负整数句柄，本质上是当前任务文件描述符表中的索引。
#. fd 数字只在对应 ``files_struct`` 中有意义；两个进程都拥有 fd 3，不代表它们指向同一对象。
#. ``task_struct->files`` 连接任务与 ``struct files_struct``，后者表示该任务可见的文件描述符集合。
#. ``struct fdtable`` 保存 ``struct file *`` 数组、open 位图、close-on-exec 位图和容量等状态。
#. fd 表项保存的是到 ``struct file`` 的引用关系，不保存文件内容、inode 元数据或路径解析过程。
#. ``alloc_fd()`` 一类路径负责找到空闲编号，``fd_install()`` 把已经建立的 ``struct file`` 安装进对应槽位。
#. fd 分配通常选择当前可用的较小编号，因此关闭后的编号可能很快被重新使用。
#. 日志里只有“fd=7”不足以证明对象身份，还必须同时记录 PID、时间、创建方式和关闭路径。
#. ``read(fd, ...)``、``write(fd, ...)`` 等调用先从当前 ``files_struct`` 查找 ``struct file``，再进入 VFS 或对象操作表。
#. fd 槽位为空、越界或已关闭时，通常返回 ``EBADF``。
#. fd lookup 必须与并发 close、表扩容和共享 fd 表协调，不能把槽位中的裸指针当成无生命周期对象。
#. 内核通常通过 RCU、引用计数和 ``fdget``/``fget`` 一类 helper 安全取得 ``struct file``。
#. ``struct file`` 表示一次打开实例，也对应 POSIX 语境中的 open file description。
#. ``struct file`` 常保存 ``f_pos``、``f_flags``、``f_mode``、``f_op``、``f_path`` 和 ``private_data`` 等打开状态。
#. 文件偏移 ``f_pos`` 属于打开实例，不属于 fd 数字，也不属于 inode 本身。
#. 同一路径调用两次 ``open()``，通常创建两个不同的 ``struct file``，各自拥有独立文件偏移。
#. 对一个 fd 调用 ``dup()``，新旧两个 fd 表项通常指向同一个 ``struct file``。
#. 通过 ``dup`` 得到的 fd 共享文件偏移和 open file status flags。
#. fd 表项级别的 ``FD_CLOEXEC`` 不属于共享 ``struct file``，不同 fd 可以拥有不同 close-on-exec 状态。
#. ``dup2()``/``dup3()`` 的替换语义必须按原子 fd 表操作理解，不能用普通 ``close()+dup()`` 无条件模拟。
#. ``fork()`` 通常复制父进程 fd 表关系，使父子对应 fd 指向同一批 ``struct file``。
#. fork 后父子若共享同一个打开实例，对任一方的普通顺序读写都可能推进共享 ``f_pos``。
#. 使用 ``clone(CLONE_FILES)`` 创建的线程直接共享同一个 ``files_struct``，一个线程关闭 fd 会影响其它线程。
#. 普通 fork 后父子拥有不同 fd 表容器，但表项中的 ``struct file`` 引用仍可共享。
#. ``execve()`` 会替换地址空间，不会默认关闭全部 fd；只有设置 ``FD_CLOEXEC`` 的表项会在成功 exec 时关闭。
#. 创建 fd 时应优先使用 ``O_CLOEXEC``、``SOCK_CLOEXEC``、``pipe2(O_CLOEXEC)`` 等原子接口，避免多线程竞态泄漏。
#. 先创建 fd 再单独调用 ``fcntl(F_SETFD, FD_CLOEXEC)``，中间窗口可能被另一线程的 ``fork+exec`` 继承。
#. ``close(fd)`` 首先移除当前 fd 表项，让该编号可被复用。
#. close 一个 fd 不等于底层 ``struct file``、inode、socket 或挂载对象立即销毁。
#. 只有最后一个 ``struct file`` 引用释放时，VFS 才进入 ``fput``、``release`` 和最终对象清理路径。
#. 其它 fd、其它进程、内核异步工作、epoll、io_uring 或文件映射都可能继续持有相关引用。
#. close 返回后，当前线程不得再使用旧 fd；即使底层释放稍后完成，旧编号也已经失去原身份。
#. 多线程中一个线程 close fd，另一个线程稍后使用同一数字，可能得到 ``EBADF``，也可能命中新打开对象。
#. 这类 fd reuse 是典型 ABA 风险：整数值相同，不代表打开实例相同。
#. 不能通过在业务结构中只保存 fd 数字来证明对象长期身份；还需明确同步、所有权和关闭协议。
#. 阻塞 I/O 与并发 close 的具体结果依赖内核取得 ``struct file`` 引用的时机，不能简单假设 close 会立即取消另一线程已开始的 I/O。
#. 取消异步 I/O、poll、epoll 或 io_uring 请求应使用对应子系统的取消与收束协议，不应只依赖 close。
#. ``/proc/<pid>/fd`` 展示该进程当前 fd 表项，符号链接目标可能是路径、``socket:[id]``、``pipe:[id]`` 或 ``anon_inode``。
#. ``/proc/<pid>/fdinfo/<fd>`` 可补充位置、标志、mount ID 以及部分子系统特有信息。
#. ``/proc/<pid>/fd`` 只能证明当前可见表项，不能证明底层对象没有其它内核引用。
#. 打开但已 unlink 的文件可能显示 ``(deleted)``，文件内容仍由打开实例和 inode 引用保持可访问。
#. fd 泄漏会增加进程 open fd 数量，也可能保持 inode、dentry、mount、socket、pipe 和设备资源长期存活。
#. ``RLIMIT_NOFILE`` 限制单进程可分配的 fd 数量，耗尽时常见 ``EMFILE``。
#. 系统级打开文件资源不足可能表现为 ``ENFILE``，其语义不同于当前进程达到 fd 上限。
#. 诊断 ``EMFILE`` 时应先统计 fd 数和创建速率，再按类型、调用栈、生命周期和 exec 继承定位泄漏。
#. ``close_range()`` 可批量关闭或设置 close-on-exec，但使用前必须确认线程共享 fd 表和保留范围语义。
#. stdin/stdout/stderr 只是约定占用 0、1、2；它们仍是普通 fd 表项，可以被关闭和复用。
#. 关闭标准 fd 后未显式重建，后续 ``open`` 可能得到 0、1 或 2，引发权限或日志方向错误。
#. Socket、pipe、eventfd、timerfd、signalfd、epoll fd 同样通过 ``struct file`` 接入 fd table，不一定对应普通 inode 路径。
#. ``struct file->f_op`` 决定当前打开对象支持的读写、poll、ioctl、mmap、release 等操作。
#. fd 是“访问某个内核打开关系的句柄”，不是磁盘文件的同义词。
#. 文件锁的归属语义可能与进程、fd 或 open file description 相关，必须按具体锁 API 区分。
#. 通过 SCM_RIGHTS 传递 fd 时，接收进程得到新的 fd 表项，背后引用同一个打开实例或对象关系。
#. fd 跨进程传递改变的是句柄所在表，不自动复制底层文件内容或独立文件偏移。
#. 正确 fd 生命周期必须定义创建、发布、共享、继承、取消、关闭和错误回滚的唯一责任方。
#. 错误路径中 fd 已安装与未安装必须区分：未安装 ``struct file`` 应直接 ``fput``，已安装后应按 fd 关闭路径回滚。
#. 不能同时对同一引用既 ``fput`` 又 ``close_fd``，否则可能形成双重释放。
#. 最稳定的 fd 分析顺序是：PID/task → ``files_struct`` → fd 槽位 → ``struct file`` → 操作表与底层对象 → 最后引用释放。

必背路径
--------

打开并安装 fd：

::

   用户调用 open / socket / pipe
   → 内核创建或取得 struct file
   → 在当前 files_struct 中分配空闲 fd
   → 设置 fd flags 与 close-on-exec
   → fd_install 把 struct file 放入槽位
   → 返回 fd 数字给用户态

从 fd 执行 I/O：

::

   用户调用 read(fd)
   → current->files
   → fdtable[fd]
   → 安全取得 struct file 引用
   → 检查 f_mode 与状态
   → 通过 file->f_op 分发
   → 更新打开实例状态
   → 释放本次临时引用

``dup`` 共享打开实例：

::

   已有 fd 3 指向 struct file X
   → 为新 fd 4 分配表项
   → 增加 X 的引用
   → fd 3 与 fd 4 都指向 X
   → 任一 fd 的顺序 I/O 可推进共享 f_pos
   → 关闭一个 fd 只减少一个表项引用

Close 生命周期：

::

   close(fd)
   → 从 fdtable 原子移除表项
   → fd 数字立即可复用
   → 释放该表项持有的 file 引用
   → 最后引用归零时执行 file->release
   → 释放路径、inode、socket 或私有资源引用
   → 最终回收 struct file

诊断 fd 泄漏：

::

   观察 EMFILE 或 fd 数持续增长
   → 读取 /proc/<pid>/fd 与 fdinfo
   → 按普通文件、socket、pipe、anon_inode 分类
   → 对齐创建 syscall 与关闭 syscall
   → 检查 fork/exec 与 CLOEXEC
   → 检查异步子系统和共享 files_struct
   → 修正所有权并验证 fd 数回落

必须区分
--------

fd 数字与打开对象
   fd 是当前进程表中的索引；``struct file`` 才保存打开实例状态。

fd 表项与 ``struct file``
   表项保存指针和 ``FD_CLOEXEC``；``struct file`` 保存偏移、状态标志和操作表。

两次 ``open`` 与一次 ``dup``
   两次 open 通常产生独立打开实例；dup 产生新表项并共享同一个打开实例。

Fork 表复制与线程表共享
   fork 通常复制表容器并共享 file 引用；``CLONE_FILES`` 让线程直接共享同一张表。

Close fd 与对象销毁
   close 只移除一个表项引用；最后引用归零后底层打开对象才进入最终释放。

fd 数值复用与对象身份
   旧 fd 被关闭后同一整数可指向新对象，不能用数字相等证明身份未变。

一句话结论
----------

文件描述符只是当前任务 fd 表中的整数索引，真正的打开状态和生命周期位于共享或独立的 ``struct file`` 对象及其引用关系中。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 19，File Descriptors, VFS, Inode, Dentry, and Superblock；
* AIBook 章节：Chapter 91，File Descriptors and the Process File Table；
* 源文件：``docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_091_File_Descriptors_and_the_Process_File_Table.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_091_File_Descriptors_and_the_Process_File_Table.md>`_。