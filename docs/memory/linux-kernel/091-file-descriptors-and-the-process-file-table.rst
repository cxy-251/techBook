第091章：文件描述符与进程文件表
================================

核心知识点
----------

fd 是进程局部索引
   文件描述符是 ``files_struct`` 中的非负整数索引。相同数字出现在不同进程中，不表示它们引用同一个内核对象。

进程文件表保存打开关系
   ``task_struct->files`` 指向 ``struct files_struct``，其 ``fdtable`` 保存 ``struct file *`` 槽位、已打开位图、close-on-exec 位图和容量状态。

``struct file`` 才是打开实例
   它保存 ``f_pos``、``f_flags``、``f_mode``、``f_op``、``f_path`` 和 ``private_data`` 等状态，对应一次 open file description。

fd 查找必须取得稳定引用
   并发 close、表扩容和共享文件表会改变槽位。内核通过 ``fdget()``、``fget()``、RCU 和引用计数等机制把瞬时槽位转换为可安全使用的 ``struct file``。

分配编号与安装对象是两个阶段
   ``alloc_fd()`` 一类路径预留空闲编号，``fd_install()`` 才把已构造的 ``struct file`` 发布到槽位。错误回滚必须区分对象是否已经安装。

两次 open 与 dup 语义不同
   同一路径两次 open 通常产生两个 ``struct file``，文件偏移彼此独立；``dup()`` 创建新 fd 表项并共享原 ``struct file``，因此共享偏移和打开状态标志。

fd 标志与打开状态分属不同层
   ``FD_CLOEXEC`` 属于 fd 表项；``O_APPEND``、``O_NONBLOCK`` 等 open file status flags 位于共享的 ``struct file``。同一打开实例的多个 fd 可以具有不同的 CLOEXEC 状态。

fork 与线程共享层次不同
   普通 fork 复制 fd 表容器，同时增加底层 ``struct file`` 引用；``CLONE_FILES`` 让线程直接共享同一个 ``files_struct``，一个线程关闭槽位会立即改变其它线程看到的表。

close 先撤销句柄可见性
   ``close(fd)`` 先从表中移除槽位，使编号可以立刻复用，再释放该表项持有的 file 引用。旧 fd 数字从此不再代表原对象。

最后引用才触发最终释放
   其它 fd、进程、mmap、epoll、io_uring 或内核异步路径都可能继续持有引用。最后一次 ``fput()`` 才进入 ``file->release`` 和底层对象清理。

fd 复用形成 ABA 风险
   一个线程关闭 fd 7 后，另一次 open 可能再次返回 7。数字相同只表示槽位相同，不能证明打开实例身份相同。

CLOEXEC 应在创建时原子建立
   ``O_CLOEXEC``、``SOCK_CLOEXEC`` 和 ``pipe2(O_CLOEXEC)`` 可避免“先创建、再设置 FD_CLOEXEC”期间被并发 fork/exec 继承的窗口。

fd 资源限制分为进程级与系统级
   当前进程达到 ``RLIMIT_NOFILE`` 常返回 ``EMFILE``；系统范围的打开文件资源不足可能返回 ``ENFILE``。二者的修复方向不同。

fd 不只表示磁盘文件
   Socket、pipe、eventfd、timerfd、epoll 和 ``anon_inode`` 都通过 ``struct file`` 接入 fd table，再由各自 ``f_op`` 实现操作。

关键路径
--------

打开并发布 fd：

::

   创建或取得 struct file
   → 在当前 files_struct 中预留空闲编号
   → 设置 fd flags 与 close-on-exec
   → fd_install 发布 struct file
   → 返回 fd 给用户态

从 fd 执行操作：

::

   系统调用收到 fd
   → current->files 定位 fdtable
   → 校验槽位并取得稳定 file 引用
   → 检查 f_mode 和操作支持
   → 通过 file->f_op 分发
   → 释放本次临时引用

``dup`` 与 fork 共享：

::

   原 fd 指向 struct file X
   → 新表项增加 X 的引用
   → 多个 fd 或父子进程共享 X
   → 顺序 I/O 共同推进 f_pos
   → 每次 close 只减少一个引用

关闭与最终释放：

::

   close(fd)
   → 从 fdtable 移除槽位
   → 编号立即可复用
   → 释放表项持有的 file 引用
   → 最后引用归零
   → 调用 release 并清理底层资源

概念辨析
--------

* fd 与 ``struct file``：fd 是进程表中的索引；``struct file`` 保存打开实例状态。
* 两次 open 与一次 dup：前者通常创建独立打开实例；后者共享同一个打开实例。
* fd flags 与 file status flags：``FD_CLOEXEC`` 属于表项；偏移和打开状态标志属于共享 file。
* fork 复制与 ``CLONE_FILES``：fork 复制表容器并共享 file；线程可直接共享整张表。
* close 与对象销毁：close 撤销一个句柄引用；底层对象在最后引用结束后才释放。
* fd 数值与对象身份：关闭后的整数可被新对象复用，数字相等不能作为身份凭据。

本章结论
--------

文件描述符只是进程文件表中的句柄索引。真正的访问状态、共享语义和生命周期位于 ``struct file`` 及其引用关系中。