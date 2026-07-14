第一百五十二章：pidfd_open() 怎样建立pidfs file并让epoll_wait监视child？
================================================================================

上一批已经完成timerfd与eventpoll的最终释放。现在开始一个独立的pidfd实验。

本章开始前，parent已经通过普通 ``fork()`` 创建一个单线程child。fork本身沿用第九十二至九十四章已经核对的控制流，本章不重复展开copy_process与COW建立过程。

固定条件：

* CPU0是唯一online CPU；
* parent与child是两个不同TGID的单线程进程；
* 两者均为 ``SCHED_NORMAL``；
* parent当前运行在CPU0，child已经 ``TASK_RUNNING`` 并位于CPU0 runqueue，但尚未得到CPU；
* child是parent的直接自然子进程， ``exit_signal=SIGCHLD``；
* child PID在parent当前pid namespace中为 ``C``；
* child尚未退出， ``exit_state=0``；
* parent与child拥有不同的 ``files_struct``；
* parent fd 0..5已占用，next free fd为6；
* child只继承fork时已有的fd 0..5，不会看到稍后创建的fd 6/7；
* parent对 ``SIGCHLD`` 使用默认disposition，没有显式 ``SIG_IGN``，没有 ``SA_NOCLDWAIT``；
* 没有ptrace、subreaper、pid namespace迁移、exec、signal race或并发wait；
* parent执行 ``pidfd_open(C, 0)``，不使用 ``PIDFD_NONBLOCK`` 或 ``PIDFD_THREAD``；
* 随后创建level-triggered epoll，只监听 ``EPOLLIN``，event data固定为 ``0x50494436``；
* 所有fd、pidfs、epoll与slab分配均成功。

本章结束在parent阻塞于 ``epoll_wait(7, events, 1, -1)``，child被scheduler选中准备执行 ``_exit(42)``。

pidfd_open怎样找到原来的struct pid
----------------------------------

parent在CPL 3执行：

.. code-block:: c

   int pfd = pidfd_open(C, 0);

x86-64 syscall入口为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_pidfd_open(C, 0)

``pidfd_open`` 首先验证：

* flags只允许 ``PIDFD_NONBLOCK`` 与 ``PIDFD_THREAD``；
* ``C > 0``。

本场景flags为0，PID有效。随后：

.. code-block:: c

   p = find_get_pid(C);

``find_get_pid`` 在RCU read-side临界区中通过parent当前pid namespace查找数字 ``C``，并对对应 ``struct pid`` 对象 ``P`` 增加reference。

这里获得的不是child ``task_struct`` reference。pidfd的核心identity是：

::

   userspace numeric PID C
   → current pid namespace lookup
   → stable struct pid P

数字PID未来可以复用；持有 ``P`` reference不会错误指向未来复用同一数字的新进程。

pidfd_prepare怎样确认child仍可被打开
------------------------------------

``pidfd_create(P, 0)`` 调用：

.. code-block:: c

   pidfd_prepare(P, 0, &pidfd_file)

由于没有 ``PIDFD_STALE``， ``pidfd_prepare`` 获取：

::

   P->wait_pidfd.lock

在这把waitqueue spinlock下检查：

* ``P`` 仍有 ``PIDTYPE_PID`` task linkage；
* 未请求 ``PIDFD_THREAD`` 时， ``P`` 还必须有 ``PIDTYPE_TGID`` linkage。

child是尚未退出的单线程group leader，因此两项均成立。锁在scope结束时释放。

这把锁的重要作用不只是保护wait queue链表。它还与task linkage消失的reap路径形成同步边界，避免在“已经彻底回收的PID”上新建一个无法提供完整退出信息的pidfd。

fd 6怎样被预留
--------------

检查完成后， ``pidfd_prepare`` 执行：

.. code-block:: c

   CLASS(get_unused_fd, pidfd)(O_CLOEXEC);

parent的fd 0..5已占用，所以预留：

::

   pidfd number = 6

此时fdtable slot 6处于reserved、尚未published状态。close-on-exec bitmap已按 ``O_CLOEXEC`` 准备，但其他线程还不能通过fd 6取得file。

pidfd默认总是close-on-exec。用户传入flags=0只表示没有NONBLOCK/THREAD语义，不会关闭 ``O_CLOEXEC``。

为什么pidfd不再是普通anon_inode file
-----------------------------------

``pidfd_prepare`` 继续调用：

.. code-block:: c

   pidfs_alloc_file(P, O_RDWR)

当前内核使用专门的 ``pidfs`` pseudo filesystem，而不是让所有pidfd共享一个anonymous inode。

``pidfs_alloc_file`` 通过：

::

   path_from_stashed(&P->stashed, pidfs_mnt, get_pid(P), &path)

取得或创建与 ``P`` 对应的stashed pidfs path。首次创建时：

* ``pidfs_register_pid`` 为 ``P->attr`` 分配 ``pidfs_attr``；
* 创建pidfs dentry与inode；
* inode ``i_private=P``；
* inode operations设为 ``pidfs_inode_operations``；
* file operations设为 ``pidfs_file_operations``；
* inode number来自 ``P->ino``；
* dentry保存到 ``P->stashed``，之后同一 ``struct pid`` 的pidfd可复用该path。

pidfs inode持有一个 ``struct pid`` reference。关闭pidfd file时，inode eviction最终通过 ``pidfs_evict_inode`` 对它执行 ``put_pid``。

因此对象关系为：

::

   fd 6
   → struct file F6
   → pidfs dentry/inode N
   → N->i_private = struct pid P
   → P identifies child independently of numeric PID reuse

``dentry_open`` 以 ``O_RDWR`` 创建 ``F6``。pidfd虽然没有普通read/write数据流，本内核仍把pidfd file mode建立为read/write file；真正可用的核心操作包括poll与ioctl。

fd_install怎样发布pidfd
----------------------

``pidfd_prepare`` 把 ``F6`` 返回给 ``pidfd_create``，后者执行：

.. code-block:: c

   fd_install(6, F6);

从这一刻开始，parent fdtable中的fd 6正式published。 ``pidfd_open`` 释放自己查找时临时持有的 ``P`` reference，并返回：

::

   RAX = 6

返回CPL 3后：

* parent可通过fd 6稳定引用child的 ``struct pid``；
* child的files_struct是在fork时复制的，不包含后来发布的fd 6；
* fd 6设置close-on-exec；
* ``F6->f_op=&pidfs_file_operations``；
* ``P->wait_pidfd`` 当前为空；
* ``P->attr`` 已存在，用于未来保存退出信息。

epoll fd 7怎样建立
------------------

parent随后执行：

.. code-block:: c

   int epfd = epoll_create1(EPOLL_CLOEXEC);

沿前面epoll章节已核对的路径，内核分配：

* eventpoll file ``F7``；
* eventpoll object ``EP``；
* close-on-exec fd 7。

初始状态：

::

   EP.refcount = 1
   EP.rbr      = empty
   EP.rdllist  = empty
   EP.wq       = empty

pidfd_poll怎样把callback挂到P->wait_pidfd
---------------------------------------

parent注册：

.. code-block:: c

   struct epoll_event ev = {
       .events = EPOLLIN,
       .data.u64 = 0x50494436,
   };

   epoll_ctl(7, EPOLL_CTL_ADD, 6, &ev);

``ep_insert`` 建立epitem ``I``，key为：

::

   (F6, fd 6)

并把兴趣mask扩展为用户请求的 ``EPOLLIN`` 加上始终隐含的 ``EPOLLERR|EPOLLHUP``。

registration过程调用 ``pidfd_poll(F6, pts)``。该函数首先执行：

.. code-block:: c

   poll_wait(F6, &P->wait_pidfd, pts);

由epoll提供的poll table callback分配 ``eppoll_entry PWE``，其wait entry ``CB``：

* 挂入 ``P->wait_pidfd``；
* flags为non-exclusive；
* callback function为 ``ep_poll_callback``；
* ``CB`` 反向指向epitem ``I``。

为了避免和 ``struct pid P`` 混淆，本章后续将这个poll callback entry记为 ``CB``。

初次poll为什么不ready
--------------------

安装callback后， ``pidfd_poll`` 在RCU下读取：

.. code-block:: c

   task = pid_task(P, PIDTYPE_PID);

child仍存在，且：

::

   child->exit_state = 0

所以既不满足“task linkage已不存在”，也不满足“task已经退出且group leader无需延迟”。返回poll mask为0。

因此ADD完成后：

::

   EP.rbr contains I
   EP.rdllist empty
   P->wait_pidfd contains CB
   EP.refcount: 1 → 2

epitem持有一个eventpoll reference。此时registration存在，但没有ready event。

parent怎样阻塞在eventpoll自己的wait queue
-----------------------------------------

parent执行：

.. code-block:: c

   epoll_wait(7, events, 1, -1);

初次检查 ``EP.rdllist`` 为空。 ``ep_poll`` 创建parent内核栈wait entry ``W``：

* ``W.private=parent``；
* ``W`` 以exclusive waiter加入 ``EP.wq``；
* parent state设为 ``TASK_INTERRUPTIBLE``。

必须区分两条wait queue：

::

   P->wait_pidfd : contains non-exclusive epoll callback CB
   EP.wq         : contains exclusive sleeping task waiter W

``CB`` 用来把pidfd readiness转换成eventpoll ready item； ``W`` 用来真正唤醒阻塞在 ``epoll_wait`` 的parent。

parent调用 ``schedule()`` 后：

::

   parent TASK_INTERRUPTIBLE
   parent on_rq = 0
   parent on_cpu = 0

固定scheduler顺序选择已经在CPU0 runqueue中的child。CPU切换到child原来的fork返回栈，child进入CPL 3并准备执行 ``_exit(42)``。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：child；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* child scheduling class：``SCHED_NORMAL``；
* child state：``TASK_RUNNING``、 ``on_rq=1``、 ``on_cpu=1``；
* parent state：``TASK_INTERRUPTIBLE``、 ``on_rq=0``、 ``on_cpu=0``；
* parent stack：停在 ``epoll_wait → ep_poll → schedule``；
* child PID： ``C``；
* child ``exit_state``：0；
* child task/group：single-threaded、group leader；
* child parent：当前parent；
* parent fd 6：open pidfd ``F6``，close-on-exec、blocking；
* child fdtable：不包含fd 6/7；
* pidfs inode ``N``：active， ``N->i_private=P``；
* ``struct pid P``：active，task linkage仍存在；
* ``P->attr``：allocated，exit bit未设置；
* ``P->wait_pidfd``：包含callback ``CB``；
* parent fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：empty；
* ``EP.wq``：包含exclusive waiter ``W``；
* event data： ``0x50494436``；
* next control entry：child ``_exit(42)`` syscall。

关键边界
--------

#. pidfd固定的是 ``struct pid`` identity，不是可复用的数字PID本身。
#. ``find_get_pid`` 增加pid reference，不增加child task_struct reference。
#. ``pidfd_prepare`` 在 ``wait_pidfd.lock`` 下确认task linkage仍存在。
#. pidfd fd number总是以close-on-exec方式预留。
#. 当前pidfd由pidfs dentry/inode承载，不是共享singleton anon inode。
#. pidfs inode ``i_private`` 指向 ``struct pid`` 并持有pid reference。
#. child在fork后拥有独立files_struct，因此看不到parent稍后创建的fd 6/7。
#. ``pidfd_poll`` 把epoll callback挂到 ``P->wait_pidfd``。
#. target wait queue上的callback ``CB`` 与 ``EP.wq`` 上的task waiter ``W`` 属于两条不同queue。
#. child仍live且 ``exit_state=0`` 时，初次pidfd poll返回0。
#. level-triggered registration存在不等于当前ready。
#. parent阻塞后，固定scheduler顺序才让child运行。

下一任务
--------

下一章从child执行 ``_exit(42)`` 开始，追踪：

::

   do_exit
   → exit_notify
   → child EXIT_ZOMBIE
   → do_notify_parent
   → do_notify_pidfd
   → wake P->wait_pidfd with EPOLLIN|EPOLLRDNORM key
   → ep_poll_callback queues I
   → wake parent W on EP.wq

资料
----

* `Linux 7.2-rc1 kernel/pid.c：pidfd_open与pidfd_create <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c>`_
* `Linux 7.2-rc1 kernel/fork.c：pidfd_prepare与fd预留 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 fs/pidfs.c：pidfs path、inode、file与pidfd_poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：epoll callback registration与wait <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
