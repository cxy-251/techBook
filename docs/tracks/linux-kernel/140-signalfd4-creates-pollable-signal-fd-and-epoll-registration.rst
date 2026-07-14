第一百四十章：signalfd4() 怎样把阻塞信号变成可poll的fd并挂进epoll？
================================================================================

上一批已经结束旧eventfd/epoll对象的生命周期。本章开始一个独立实验，重新使用fd 6和fd 7。

固定场景
--------

* CPU0是唯一online CPU；
* parent与helper属于同一thread group，共享 ``mm``、 ``files_struct``、 ``signal_struct`` 与 ``sighand_struct``；
* 两个线程均为 ``SCHED_NORMAL``；
* fd 0..5已经占用；
* parent与helper都已把 ``SIGUSR1`` 加入各自blocked mask；
* blocked-mask设置在本章之前完成，本章不展开 ``rt_sigprocmask``；
* ``SIGUSR1`` 当前既不在parent private pending，也不在shared pending；
* parent执行全部创建和注册syscall；
* signalfd使用 ``SFD_CLOEXEC``，不使用 ``SFD_NONBLOCK``；
* epoll使用level-triggered ``EPOLLIN``，不使用 ``EPOLLET``、 ``EPOLLONESHOT``、 ``EPOLLEXCLUSIVE`` 或 ``EPOLLWAKEUP``；
* 注册时 ``event.data.u64=0x51FD6``；
* 没有allocation、copy、permission、quota或fd分配失败。

用户态调用顺序固定为：

.. code-block:: c

   sigset_t mask;
   sigemptyset(&mask);
   sigaddset(&mask, SIGUSR1);

   int sfd = signalfd4(-1, &mask, sizeof(mask), SFD_CLOEXEC); // fd 6
   int epfd = epoll_create1(EPOLL_CLOEXEC);                   // fd 7

   struct epoll_event ev = {
       .events = EPOLLIN,
       .data.u64 = 0x51FD6,
   };
   epoll_ctl(epfd, EPOLL_CTL_ADD, sfd, &ev);

本章结束在fd 6与fd 7均已发布，signalfd callback已经挂到共享 ``sighand->signalfd_wqh``，但没有pending signal，因此epoll ready list为空。

signalfd为什么要求先block信号
----------------------------

signalfd并不会自动修改线程的blocked mask。用户必须先阻塞希望通过fd读取的信号。

本场景中parent与helper都阻塞 ``SIGUSR1``，所以该信号不会按普通异步signal-handler路径进入用户态。后续helper向parent定向发送 ``SIGUSR1`` 时，它可以留在parent的private pending queue中，等待signalfd读取。

这里存在两个不同的mask：

::

   current->blocked       = signal delivery mask
   signalfd_ctx->sigmask  = signalfd selection mask的内部表示

前者决定普通signal delivery是否可运行；后者决定某个signalfd愿意读取哪些pending signal。二者必须由用户程序协调，kernel不会自动保证一致。

signalfd4怎样验证参数
--------------------

native x86-64进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_signalfd4
   → do_signalfd4

固定参数为：

::

   ufd      = -1
   user_mask= { SIGUSR1 }
   sizemask = sizeof(sigset_t)
   flags    = SFD_CLOEXEC

syscall先检查 ``sizemask``，再把用户mask复制到kernel stack。

``do_signalfd4`` 只允许：

::

   SFD_CLOEXEC
   SFD_NONBLOCK

固定没有未知flag。代码还从mask中移除 ``SIGKILL`` 与 ``SIGSTOP``，因为这两个信号不能被block，也不能通过signalfd消费。

为什么ctx中保存的是反转后的mask
------------------------------

``do_signalfd4`` 执行：

.. code-block:: c

   sigdelsetmask(mask, sigmask(SIGKILL) | sigmask(SIGSTOP));
   signotset(mask);

之后才保存：

.. code-block:: c

   ctx->sigmask = *mask;

因此 ``signalfd_ctx`` 中不是直接保存用户集合 ``{SIGUSR1}``，而是保存其内部反转表示。

原因在于 ``next_signal`` 与 ``dequeue_signal`` 接收的是“blocked mask”语义：它们寻找：

::

   pending & ~mask

把用户想接收的集合先反转后传入，就会得到：

::

   pending & user_requested_set

所以不能直接把 ``ctx->sigmask`` 按用户可见sigset打印或解释。 ``signalfd_show_fdinfo`` 在展示时也会再次 ``signotset``，恢复用户视角。

signalfd_ctx与file怎样建立
-------------------------

``ufd=-1`` 表示创建新对象。kernel分配：

::

   struct signalfd_ctx S

其中只有一个主要字段：

::

   S->sigmask = inverted internal mask selecting SIGUSR1

随后调用：

::

   anon_inode_getfile_fmode(
       "[signalfd]",
       &signalfd_fops,
       S,
       O_RDWR,
       FMODE_NOWAIT)

得到anonymous-inode file ``F6``：

* ``F6->private_data=S``；
* ``F6->f_op=&signalfd_fops``；
* ``F6`` 支持 ``poll`` 与 ``read_iter``；
* file本身为blocking，因为没有 ``SFD_NONBLOCK``；
* ``FMODE_NOWAIT`` 表示VFS允许IOCB_NOWAIT语义，不等于该fd默认nonblocking；
* ``SFD_CLOEXEC`` 只设置fdtable close-on-exec bit。

fd分配选择第一个空slot 6，发布后：

::

   fdtable[6] = F6
   open_fds[6] = 1
   close_on_exec[6] = 1

parent与helper共享 ``files_struct``，所以两者都能解析fd 6。不过能从该fd读到哪些private pending signal，仍取决于执行read的current task，而不是fd由哪个线程创建。

epoll_create1怎样建立fd 7
-------------------------

parent随后调用：

::

   epoll_create1(EPOLL_CLOEXEC)

进入：

::

   __x64_sys_epoll_create1
   → do_epoll_create
   → ep_alloc

kernel分配 ``struct eventpoll EP`` 并初始化：

::

   EP->mtx
   EP->lock
   EP->wq
   EP->poll_wait
   EP->rbr      = empty RB tree
   EP->rdllist  = empty
   EP->ovflist  = EP_UNACTIVE_PTR
   EP->refcount = 1

然后建立 ``[eventpoll]`` anonymous-inode file ``F7``：

::

   F7->private_data = EP
   F7->f_op          = eventpoll_fops

下一个空slot是7：

::

   fdtable[7] = F7
   close_on_exec[7] = 1

此时signalfd与epoll只是两个独立fd，还没有watch relationship。

epoll_ctl怎样建立epitem
-----------------------

parent执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_ADD, 6, &ev);

kernel分别解析：

::

   epfd 7 → eventpoll file F7 → eventpoll EP
   fd   6 → signalfd file F6 → signalfd_ctx S

目标 ``F6`` 有 ``poll`` operation，所以可以被epoll监视。

用户传入 ``EPOLLIN``。kernel自动加入：

::

   EPOLLERR | EPOLLHUP

最终epitem ``I`` 保存：

::

   I->ffd.file    = F6
   I->ffd.fd      = 6
   I->event.events= EPOLLIN | EPOLLERR | EPOLLHUP
   I->event.data  = 0x51FD6
   I->ep          = EP

key同时包含 ``struct file *`` 与整数fd。fd数字被复用后，新file不会与旧registration混淆。

``ep_register_epitem`` 把 ``I``：

* 挂到 ``F6->f_ep`` reverse hlist；
* 插入 ``EP->rbr`` interest RB tree；
* 为item lifetime增加一个eventpoll reference。

因此：

::

   EP->refcount: 1 → 2

一个reference来自eventpoll file，另一个来自epitem relationship。

callback挂在哪条wait queue
--------------------------

``ep_insert`` 初始化poll table：

::

   poll_table callback = ep_ptable_queue_proc
   poll key            = I->event.events

然后调用：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → signalfd_poll(F6, poll_table)

``signalfd_poll`` 首先执行：

.. code-block:: c

   poll_wait(F6, &current->sighand->signalfd_wqh, wait);

这里的 ``current`` 是执行 ``epoll_ctl`` 的parent。parent与helper共享 ``sighand_struct``，所以目标wait queue是进程共享的：

::

   parent->sighand->signalfd_wqh
   == helper->sighand->signalfd_wqh

``ep_ptable_queue_proc`` 分配 ``struct eppoll_entry P``：

::

   P->base      = I
   P->whead     = &sighand->signalfd_wqh
   P->wait.func = ep_poll_callback

因为没有 ``EPOLLEXCLUSIVE``， ``P`` 通过 ``add_wait_queue`` 作为non-exclusive callback entry加入wait queue。

这不是一个正在睡眠的task waiter。 ``P`` 的作用是：当signal产生路径wake这条queue时，把控制权转入epoll callback。

注册时怎样判断readiness
----------------------

callback挂好后， ``signalfd_poll`` 获取：

::

   current->sighand->siglock

然后检查parent的：

::

   current->pending
   current->signal->shared_pending

检查只针对 ``S->sigmask`` 选中的 ``SIGUSR1``。

固定场景没有pending signal，因此返回0：

::

   signalfd_poll readiness = 0

所以 ``I`` 只进入interest tree，不进入ready list：

::

   EP->rbr     contains I
   EP->rdllist empty

``epoll_ctl`` 最终返回0。

为什么shared fd不等于shared private pending
-----------------------------------------

parent与helper共享fd 6、signalfd ctx和sighand wait queue，但每个thread仍有自己的：

::

   task_struct->pending

``signalfd_poll`` 与 ``signalfd_read`` 都使用执行syscall的 ``current``。所以：

* parent定向pending signal可由parent通过fd 6读取；
* helper使用同一个fd 6执行read时，不会读取parent的private pending queue；
* process-directed signal位于 ``signal->shared_pending``，可被合适thread读取。

本实验后续使用 ``tgkill`` 定向发送给parent，并由parent执行 ``epoll_wait`` 与 ``read``，避免跨thread private-pending歧义。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent/helper scheduling：``SCHED_NORMAL``；
* parent blocked mask：包含 ``SIGUSR1``；
* helper blocked mask：包含 ``SIGUSR1``；
* parent private pending：不含 ``SIGUSR1``；
* shared pending：不含 ``SIGUSR1``；
* shared fd 6：open signalfd file ``F6``，blocking、close-on-exec；
* signalfd ctx ``S``：active，内部mask选择 ``SIGUSR1``；
* shared fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：包含epitem ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``I->event.events``：``EPOLLIN|EPOLLERR|EPOLLHUP``；
* ``I->event.data``：``0x51FD6``；
* callback entry ``P``：non-exclusive，挂在 ``sighand->signalfd_wqh``；
* ``EP->wq``：没有task waiter；
* filesystem/block I/O：none；
* next entry：parent执行 ``epoll_wait(7, events, 1, -1)``。

关键边界
--------

#. signalfd不会自动阻塞signal；blocked mask必须由用户程序先建立。
#. ``signalfd_ctx->sigmask`` 保存内部反转表示，不是用户mask的直接副本。
#. ``SIGKILL`` 与 ``SIGSTOP`` 会从signalfd选择集中移除。
#. ``SFD_CLOEXEC`` 属于fdtable，不属于signalfd ctx。
#. ``FMODE_NOWAIT`` 不等于默认 ``O_NONBLOCK``。
#. signalfd file和eventpoll file是两个独立anonymous-inode file。
#. epoll interest key由 ``(file pointer, fd number)`` 共同组成。
#. kernel自动把 ``EPOLLERR|EPOLLHUP`` 加入stored interest。
#. epitem relationship把 ``EP->refcount`` 从1增加到2。
#. callback ``P`` 挂在共享sighand的 ``signalfd_wqh``，不是 ``EP->wq``。
#. ``P`` 是readiness callback，不是阻塞task。
#. registration时没有pending ``SIGUSR1``，所以ready list保持为空。
#. shared fd与shared sighand不意味着thread-private pending queue也共享。

下一任务
--------

下一章从parent阻塞开始：

::

   parent epoll_wait(7, events, 1, -1)
   → parent waits on EP->wq
   → helper tgkill(tgid, parent_tid, SIGUSR1)
   → signal enters parent private pending
   → signalfd_notify wakes shared signalfd queue
   → P invokes ep_poll_callback
   → I enters EP->rdllist
   → parent becomes runnable

资料
----

* `Linux 7.2-rc1 fs/signalfd.c：signalfd4、poll与ctx mask <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/signalfd.c>`_
* `Linux 7.2-rc1 include/uapi/linux/signalfd.h：flags与128-byte signalfd_siginfo <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/uapi/linux/signalfd.h>`_
* `Linux 7.2-rc1 fs/eventpoll.c：epoll create、ADD与poll callback安装 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
