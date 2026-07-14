第一百五十三章：child _exit(42) 怎样通过pid->wait_pidfd唤醒epoll_wait？
================================================================================

上一章结束时，parent阻塞在eventpoll自己的wait queue，child被调度到CPU0：

::

   P->wait_pidfd contains callback CB
   EP.wq         contains parent waiter W
   EP.rdllist    = empty
   child exit_state = 0

child现在执行：

.. code-block:: c

   _exit(42);

本章固定条件继续保持：

* child是单线程group leader；
* parent是child的自然parent；
* parent没有显式忽略SIGCHLD，也没有设置 ``SA_NOCLDWAIT``；
* 没有ptrace、其他waiter、并发epoll_ctl、pidfd close或exec；
* ``CB`` 是 ``P->wait_pidfd`` 上唯一epoll callback；
* ``W`` 是 ``EP.wq`` 上唯一sleeping waiter；
* CPU0是唯一online CPU；
* child退出过程中没有coredump、fatal signal或资源清理错误。

本章结束在child已经成为 ``EXIT_ZOMBIE``，pidfd callback已把epitem加入ready list并使parent runnable；child随后进入最终dead scheduling path，scheduler将恢复parent的 ``epoll_wait`` 内核栈。

_exit怎样进入do_exit
-------------------

x86-64 syscall入口：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_exit(42)
   → do_exit(42 << 8)

内核保存的正常退出编码不是裸整数42，而是wait status格式：

::

   child->exit_code = 42 << 8

这样后续wait路径能够区分正常退出、signal终止与core dump。

child先释放哪些运行资源
-----------------------

``do_exit`` 将child标记为退出中，并沿已经在第一百零一章展开过的路径释放运行期资源，包括：

* mm与用户地址空间；
* files/fs namespace引用；
* namespaces、sem、shm与thread state；
* accounting、perf、cgroup与task work状态。

这些步骤不会释放 ``struct pid P``，也不会让pidfd file ``F6`` 失效。pidfd持有的是独立pid object reference，其目的正是跨越task退出与数字PID回收边界。

本章聚焦退出通知阶段：

::

   do_exit
   → exit_notify(child, group_dead=1)

exit_notify何时设置EXIT_ZOMBIE
------------------------------

``exit_notify`` 获取：

::

   write_lock_irq(&tasklist_lock)

完成必要的reparent检查后，执行：

.. code-block:: c

   child->exit_state = EXIT_ZOMBIE;

从这一点开始，child已经是可等待的zombie：

* task_struct仍存在；
* PIDTYPE_PID与PIDTYPE_TGID linkage仍存在；
* exit_code仍可读取；
* parent尚未执行wait，因此child还没有被reap。

pidfd readiness的第一条判断正是task存在且 ``exit_state != 0``。因此通知发生时，后续re-poll已经能够观察到 ``EPOLLIN``。

do_notify_parent怎样先通知pidfd
------------------------------

child是无ptrace的单线程group leader， ``exit_notify`` 调用：

::

   do_notify_parent(child, SIGCHLD)

``do_notify_parent`` 开始阶段先执行：

.. code-block:: c

   do_notify_pidfd(child);

这发生在构造并发送parent的SIGCHLD通知之前。pidfd wake与传统child-wait signal是两条不同通知通道：

::

   pidfd channel  → P->wait_pidfd
   wait/SIGCHLD   → parent signal state + wait_chldexit

parent当前睡在 ``EP.wq``，并不睡在 ``wait_chldexit``。真正把它从epoll_wait中唤醒的是pidfd channel。

do_notify_pidfd发送什么wake key
------------------------------

``do_notify_pidfd`` 取得：

.. code-block:: c

   struct pid *P = task_pid(child);

并验证 ``child->exit_state != 0``。随后调用：

.. code-block:: c

   __wake_up(&P->wait_pidfd,
             TASK_NORMAL,
             0,
             poll_to_key(EPOLLIN | EPOLLRDNORM));

这里：

* wake key包含 ``EPOLLIN|EPOLLRDNORM``；
* ``nr_exclusive=0``，表示扫描所有匹配entry；
* ``CB`` 是non-exclusive callback，因此会被调用；
* 当前没有直接睡在 ``P->wait_pidfd`` 上的普通task waiter。

wait queue lock把exit wake与未来的 ``EPOLL_CTL_DEL`` callback removal串行化。

ep_poll_callback怎样把I加入ready list
-----------------------------------

``CB`` 的function是 ``ep_poll_callback``。callback从wake key得到：

::

   pollflags = EPOLLIN | EPOLLRDNORM

registration interest包含 ``EPOLLIN``，所以mask相交。callback获取 ``EP->lock`` 的IRQ-safe spinlock，检查：

* ``I`` 尚未在ready list；
* EP当前不处于scan overflow阶段；
* registration未被oneshot disable。

于是：

::

   list_add_tail(&I->rdllink, &EP->rdllist)

状态转换：

::

   EP.rdllist: empty → [I]

callback只建立ready candidate。它不会在child退出上下文中再次调用 ``pidfd_poll``，也不会复制event到parent用户空间。

callback怎样唤醒EP.wq上的parent
------------------------------

加入ready list后，callback发现 ``EP.wq`` 有active waiter，执行eventpoll wake：

::

   wake_up(&EP->wq)

exclusive waiter ``W`` 的default wake function进入scheduler wakeup路径：

::

   parent TASK_INTERRUPTIBLE → TASK_RUNNING
   parent on_rq: 0 → 1

parent被放回CPU0 runqueue。当前CPU仍执行child的exit path；wake不会强制立即切换到parent。

这再次体现两级转换：

::

   child exit
   → wake pidfd wait queue callback CB
   → CB marks epitem I ready
   → wake eventpoll task waiter W
   → parent becomes runnable

传统SIGCHLD为什么没有自动reap child
---------------------------------

pidfd wake完成后， ``do_notify_parent`` 构造SIGCHLD siginfo：

::

   si_code   = CLD_EXITED
   si_status = 42
   si_pid    = C

parent没有显式把SIGCHLD disposition设置为 ``SIG_IGN``，也没有 ``SA_NOCLDWAIT``，所以：

::

   autoreap = false

SIGCHLD的默认动作不会执行用户handler，也不会把本次 ``epoll_wait`` 变成signal-handler控制流。child仍保留为zombie，等待parent显式调用wait。

``do_notify_parent`` 还会wake ``parent->signal->wait_chldexit``，但本场景该queue上没有waitid/wait4 waiter，因此该wake不改变task状态。

exit_notify怎样留下zombie
------------------------

``do_notify_parent`` 返回false后：

* ``exit_notify`` 不把child改为 ``EXIT_DEAD``；
* 不把child加入立即release列表；
* child保持 ``EXIT_ZOMBIE``；
* tasklist lock最终释放。

随后 ``do_exit`` 完成剩余accounting与connector通知，进入不可返回的dead task路径。child调用scheduler后不再运行用户代码。

固定scheduler顺序选择已经runnable的parent。CPU0切换回parent原来的内核栈，恢复点仍位于：

::

   epoll_wait
   → ep_poll
   → schedule return

本章结束时尚未向parent用户空间复制epoll event；该动作属于下一章。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current transition：scheduler正在从dead child切回parent；
* CPU：CPU0；
* child userspace：不会再次执行；
* child exit code： ``42 << 8``；
* child exit state： ``EXIT_ZOMBIE``；
* child task_struct：仍存在并保留pid linkages；
* child PID： ``C`` 仍占用且尚不可复用；
* parent state： ``TASK_RUNNING``、 ``on_rq=1``；
* parent waiter ``W``：已由eventpoll wake命中，恢复后将从 ``EP.wq`` 移除；
* pidfd file ``F6``：open；
* pidfs inode ``N``：active；
* ``struct pid P``：active，仍指向zombie child；
* ``P->wait_pidfd``：仍包含callback ``CB``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：包含ready ``I``；
* eventpoll user event：尚未copy；
* pidfd wake key： ``EPOLLIN|EPOLLRDNORM``；
* next control entry：parent恢复 ``epoll_wait`` 并由 ``pidfd_poll`` re-poll zombie child。

关键边界
--------

#. child先进入 ``EXIT_ZOMBIE``，随后才发送pidfd wake。
#. pidfd readiness不是“task_struct已释放”，而是“目标已经退出并可观察”。
#. ``do_notify_pidfd`` 使用 ``P->wait_pidfd``，传统wait使用 ``wait_chldexit``。
#. parent睡在 ``EP.wq``，不是直接睡在pidfd wait queue。
#. pidfd callback先加入ready item，再唤醒eventpoll waiter。
#. wake使parent runnable，不会强制child立刻交出CPU。
#. callback接收 ``EPOLLIN|EPOLLRDNORM`` key，但用户只请求EPOLLIN。
#. callback只建立candidate，最终交付仍需要parent上下文中的re-poll。
#. 默认SIGCHLD disposition不等于显式SIG_IGN；本场景不会autoreap。
#. child仍为zombie，因此waitid仍可读取并消费退出状态。
#. pidfd file与pidfs inode跨越child exit继续存在。

下一任务
--------

下一章恢复parent：

::

   ep_send_events
   → pidfd_poll sees EXIT_ZOMBIE
   → copy {EPOLLIN, data=0x50494436}
   → epoll_wait returns 1
   → waitid(P_PIDFD, 6, &si, WEXITED, NULL)
   → EXIT_ZOMBIE → EXIT_DEAD
   → release_task
   → pidfs_exit stores exit metadata
   → detach/free numeric PID while pidfd keeps struct pid alive

资料
----

* `Linux 7.2-rc1 kernel/exit.c：exit_notify、EXIT_ZOMBIE与release边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/exit.c>`_
* `Linux 7.2-rc1 kernel/signal.c：do_notify_pidfd与do_notify_parent <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll_callback与eventpoll wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/pidfs.c：pidfd_poll与wait_pidfd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c>`_
