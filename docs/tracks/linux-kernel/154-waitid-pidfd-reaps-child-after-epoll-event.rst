第一百五十四章：waitid(P_PIDFD) 怎样读取退出状态并回收child？
================================================================================

上一章结束时，child已经是zombie，parent已经被pidfd callback唤醒：

::

   child exit_state = EXIT_ZOMBIE
   child exit_code  = 42 << 8
   EP.rdllist       = [I]
   parent           = TASK_RUNNING

parent现在恢复原来的 ``epoll_wait`` 内核栈。本章先完成pidfd event交付，再执行：

.. code-block:: c

   siginfo_t si = {};
   waitid(P_PIDFD, 6, &si, WEXITED, NULL);

本章固定条件：

* parent是child的自然parent；
* 没有其他线程或进程等待同一child；
* 不使用 ``WNOHANG`` 或 ``WNOWAIT``；
* pidfd没有 ``O_NONBLOCK``；
* child没有ptrace关系，没有其他subthread；
* pidfd fd 6与epoll fd 7保持open；
* registration是level-triggered ``EPOLLIN``；
* 本章不执行 ``EPOLL_CTL_DEL`` 或close；
* 用户 ``events`` 与 ``siginfo_t`` buffer均可写，不发生page fault或copy error。

本章结束在child已经被reap，数字PID ``C`` 已从namespace IDR释放，但pidfd file仍通过pidfs inode引用旧 ``struct pid P``。level-triggered epitem仍在ready list，下一次re-poll会观察到 ``EPOLLIN|EPOLLHUP``。

parent恢复后怎样移除W
--------------------

scheduler恢复parent在：

::

   epoll_wait
   → ep_poll
   → schedule return

exclusive stack waiter ``W`` 完成wait-loop清理：

* parent state恢复为 ``TASK_RUNNING``；
* ``W`` 从 ``EP.wq`` 移除；
* ``EP.wq`` 重新为空。

此时 ``EP.rdllist`` 已包含 ``I``，因此epoll不再进入睡眠。

epoll交付前为什么还要调用pidfd_poll
-----------------------------------

``ep_send_events`` 获取 ``EP.mtx``，把ready list splice到本地scan batch，并处理 ``I``。

``ep_item_poll`` 临时pin住pidfd file ``F6``，然后调用：

::

   pidfd_poll(F6, NULL-like poll table)

registration早已建立，本次re-poll不再新增callback。 ``pidfd_poll`` 在RCU下取得：

.. code-block:: c

   task = pid_task(P, PIDTYPE_PID);

child仍是zombie，所以task linkage尚在。接着检查：

::

   task->exit_state != 0
   delay_group_leader(task) == false

child是无subthread group leader，因此返回：

::

   EPOLLIN | EPOLLRDNORM

这一步证明callback标记的candidate现在仍然真实ready。

epoll_wait向用户空间复制什么
----------------------------

用户interest为 ``EPOLLIN``，因此交付：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0x50494436

因为registration是level-triggered且re-poll仍ready， ``I`` 在scan结束时重新加入 ``EP.rdllist``。

最终：

::

   epoll_wait(7, events, 1, -1) = 1

回到CPL 3时：

* child仍是 ``EXIT_ZOMBIE``；
* pidfd readiness没有被epoll消费；
* ``I`` 仍是ready item；
* parent需要显式wait才能回收child。

为什么pidfd event不等于wait完成
------------------------------

pidfd poll通知只表达：

::

   target exited or no longer has a task linkage

它不会：

* 读取child exit_code；
* 修改 ``EXIT_ZOMBIE``；
* 累加parent child resource accounting；
* 调用 ``release_task``；
* 释放数字PID；
* 自动填充 ``siginfo_t``。

pidfd是通知和稳定寻址对象；wait syscall仍负责POSIX child-state消费。

waitid怎样从fd 6取得struct pid
-----------------------------

parent执行：

::

   waitid(P_PIDFD, 6, &si, WEXITED, NULL)

入口：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_waitid
   → kernel_waitid
   → kernel_waitid_prepare

``which=P_PIDFD`` 时， ``upid`` 参数被解释为pidfd number，而不是数字PID：

.. code-block:: c

   P = pidfd_get_pid(6, &f_flags);

``pidfd_get_pid``：

* 通过fdtable临时pin住 ``F6``；
* 验证 ``F6`` 的operations确实是pidfs pidfd operations；
* 从inode ``i_private`` 取得 ``P``；
* 对 ``P`` 增加reference；
* 返回 ``F6->f_flags``。

fd 6不是nonblocking，所以wait options不会被隐式增加 ``WNOHANG``。

wait_opts怎样锁定目标
--------------------

``kernel_waitid_prepare`` 建立：

::

   wo.wo_type  = PIDTYPE_PID
   wo.wo_pid   = P
   wo.wo_flags = WEXITED
   wo.wo_info  = kernel waitid_info buffer

``do_wait`` 仍会把一个临时 ``child_wait`` entry加入：

::

   parent->signal->wait_chldexit

这是通用wait框架要求。child已经是zombie，第一次扫描即可完成，因此parent不会再次 ``schedule()``。

P_PIDFD为什么没有绕过parent关系
------------------------------

``__do_wait`` 对 ``PIDTYPE_PID`` 使用优化路径：

::

   do_wait_pid
   → pid_task(P, PIDTYPE_TGID)

它定位到zombie child后，还要执行：

::

   is_effectively_child(parent, child)

本场景parent就是child的 ``real_parent``，检查通过。

若任意进程仅通过SCM_RIGHTS收到一个陌生child的pidfd，它可以poll该pidfd，却不能因此调用 ``waitid(P_PIDFD)`` 回收不属于自己的进程。pidfd提供identity，不授予parent/reaper权限。

wait_task_zombie怎样独占reap权
-----------------------------

``wait_consider_task`` 看到：

::

   child->exit_state = EXIT_ZOMBIE
   WEXITED set
   no delayed group leader

进入 ``wait_task_zombie``。它使用原子状态转换：

.. code-block:: c

   cmpxchg(&child->exit_state,
           EXIT_ZOMBIE,
           EXIT_DEAD)

固定没有其他waiter，所以转换成功：

::

   EXIT_ZOMBIE → EXIT_DEAD

从这一刻开始，parent独占该child的reap工作。其他并发waiter即使存在也不能再次消费退出状态。

退出状态怎样变成waitid_info
---------------------------

``wait_task_zombie`` 读取：

::

   status = child->exit_code = 42 << 8
   pid    = C
   uid    = child uid mapped into parent user namespace

正常退出满足：

::

   (status & 0x7f) == 0

因此填入kernel waitid_info：

::

   cause  = CLD_EXITED
   status = 42
   pid    = C
   uid    = child uid

同时，child累计的CPU时间、fault、context switch与I/O accounting被合并进parent的 ``signal_struct`` child accounting字段。

release_task怎样结束child task生命周期
--------------------------------------

状态已经变为 ``EXIT_DEAD``，所以 ``wait_task_zombie`` 调用：

::

   release_task(child)

``release_task`` 首先调用：

.. code-block:: c

   pidfs_exit(child);

由于pidfd曾经创建， ``P->attr`` 已分配。 ``pidfs_exit`` 保存：

::

   P->attr->exit_code = 42 << 8
   PIDFS_ATTR_BIT_EXIT = set

该metadata属于 ``struct pid P``，允许pidfd在task被reap后仍查询退出信息。

随后 ``release_task`` 在tasklist lock下执行 ``__exit_signal``：

* 从parent children list移除child；
* 解除PIDTYPE_PID/TGID/PGID/SID task linkages；
* 更新process/thread accounting；
* 释放signal/sighand等最终task资源。

之后 ``free_pids`` 对child原来的pid objects执行 ``free_pid``。

数字PID与struct pid为什么在这里分离
----------------------------------

``free_pid(P)`` 会：

* 从pid namespace IDR移除数字 ``C``；
* 允许未来进程重新使用数字 ``C``；
* 从pidfs inode-number hashtable移除相应可新开入口；
* 通过RCU延迟下降task侧pid reference。

然而 ``P`` 不会立即释放，因为pidfs inode ``N`` 仍由open pidfd file ``F6`` 的path持有，并且inode本身持有一个 ``P`` reference。

因此最终形成：

::

   numeric PID C        = released and reusable
   child task_struct    = logically reaped
   old struct pid P     = still alive because pidfd is open
   pidfd identity       = still refers to old child, never future PID C user

这正是pidfd解决PID reuse race的核心。

waitid怎样返回用户空间
----------------------

``wait_task_zombie`` 返回正的child PID给kernel wait框架。 ``kernel_waitid`` 把它视为成功；syscall wrapper把返回值转换成POSIX waitid语义：

::

   waitid return/RAX = 0

并复制：

::

   si.si_signo = SIGCHLD
   si.si_code  = CLD_EXITED
   si.si_pid   = C
   si.si_uid   = child uid
   si.si_status= 42

临时 ``child_wait`` entry从 ``wait_chldexit`` 移除， ``kernel_waitid_prepare`` 持有的 ``P`` reference也通过 ``put_pid`` 归还。

reap之后pidfd为什么仍然ready
----------------------------

child task linkage已经消失。若现在调用 ``pidfd_poll``：

.. code-block:: c

   task = pid_task(P, PIDTYPE_PID);  /* NULL */

它将返回：

::

   EPOLLIN | EPOLLRDNORM | EPOLLHUP

``EPOLLHUP`` 表示pidfd引用的task已经被彻底reap。

本场景的level-triggered ``I`` 在epoll event交付时已经重新放回 ``EP.rdllist``，所以不需要新的wake来重新排队。下一次 ``epoll_wait`` 会re-poll并交付至少 ``EPOLLIN|EPOLLHUP``；由于HUP总是报告，即使用户interest只写EPOLLIN也能观察到它。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：pidfd exit notification and P_PIDFD reap complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* ``epoll_wait`` result：1；
* ``events[0].events``： ``EPOLLIN``；
* ``events[0].data.u64``： ``0x50494436``；
* ``waitid(P_PIDFD)`` result/RAX：0；
* ``si_signo``： ``SIGCHLD``；
* ``si_code``： ``CLD_EXITED``；
* ``si_pid``： ``C``；
* ``si_status``：42；
* child exit state： ``EXIT_DEAD``，task已被reap；
* child task_struct：退出活动process图，storage可能等待RCU/refcount最终释放；
* numeric PID ``C``：已从namespace IDR移除，可被未来process复用；
* parent fd 6：仍open的pidfd ``F6``；
* pidfs inode ``N``：active，仍引用旧 ``struct pid P``；
* ``P->attr``：exit bit已设置，保存 ``42 << 8``；
* ``P`` task linkage：none；
* ``P->wait_pidfd``：仍包含callback ``CB``；
* parent fd 7：仍open的eventpoll ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：仍包含level-triggered ``I``；
* next pidfd poll mask： ``EPOLLIN|EPOLLRDNORM|EPOLLHUP``；
* ``EP.wq``：empty；
* child fdtable/mm/signal/task resources：已结束生命周期；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. epoll event交付不会消费pidfd退出状态。
#. pidfd re-poll在zombie阶段返回 ``EPOLLIN|EPOLLRDNORM``。
#. ``waitid(P_PIDFD)`` 的upid参数是fd number，不是numeric PID。
#. pidfd定位目标后仍执行自然parent/ptrace child权限检查。
#. pidfd identity不会赋予reap任意进程的权限。
#. ``cmpxchg(EXIT_ZOMBIE, EXIT_DEAD)`` 让一个waiter独占reap。
#. waitid正常退出结果通过 ``CLD_EXITED`` 与status 42表达。
#. waitid syscall成功返回0，而不是返回child PID。
#. ``pidfs_exit`` 在task linkage拆除前保存exit metadata。
#. numeric PID从namespace IDR移除后即可复用。
#. open pidfd通过pidfs inode继续保持旧 ``struct pid`` alive。
#. 旧pidfd不会因数字PID复用而指向新process。
#. reap后pidfd poll增加 ``EPOLLHUP``。
#. level-triggeredepitem仍在ready list，下一次wait会继续观察HUP。
#. 本批不删除registration，也不关闭fd 6/7。

下一任务
--------

当前pidfd仍永久ready。优先接续：

::

   epoll_wait(7, events2, 1, 0)
   → pidfd_poll sees no task linkage
   → return EPOLLIN|EPOLLHUP
   → copy one post-reap event

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove callback CB from P->wait_pidfd
   → erase epitem I

   close(6)
   → release pidfs file/path/inode
   → pidfs_evict_inode put_pid(P)
   → old struct pid may finally be freed

   close(7)
   → empty eventpoll teardown

资料
----

* `Linux 7.2-rc1 fs/pidfs.c：pidfd_poll、pidfs_exit与pidfs inode lifetime <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c>`_
* `Linux 7.2-rc1 kernel/exit.c：P_PIDFD wait、wait_task_zombie与release_task <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/exit.c>`_
* `Linux 7.2-rc1 kernel/pid.c：pidfd_get_pid与struct pid reference <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：level-triggered delivery与ready-list requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
