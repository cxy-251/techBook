第一百五十一章：close() 怎样释放timerfd与eventpoll并结束两套RCU生命周期？
================================================================================

上一章结束时，registration已经删除：

::

   T->wqh       = empty
   F6->f_ep     = NULL
   EP->rbr      = empty
   EP->rdllist  = empty
   EP->refcount = 1

parent现在依次执行：

.. code-block:: c

   close(6);
   close(7);

本章固定条件：

* fd 6是timerfd file ``F6`` 的唯一file reference；
* fd 7是eventpoll file ``F7`` 的唯一file reference；
* timerfd ctx ``T`` 没有额外内核引用；
* ``T`` 使用 ``CLOCK_MONOTONIC``，从未加入clock-change cancel list；
* embedded hrtimer已经到期并处于inactive、not queued状态；
* ``T->ticks=0``、 ``T->expired=0``、 ``T->tintv=0``；
* ``T->wqh`` 为空；
* eventpoll ``EP`` 没有epitem、ready item、poll waiter或nested epoll relation；
* 没有并发timer callback、fget、epoll_ctl、poll、close或RCU reader需要显式等待；
* VFS、dcache、mount和allocator路径均正常完成。

本章结束在parent返回CPL 3：fd 6/7都已关闭，timerfd ctx、eventpoll object与两份anon-inode file均退出活动对象图。 ``T``、先前的epitem ``I`` 和 ``EP`` 的storage由各自 ``kfree_rcu`` callback在grace period后回收。

close(6)先怎样撤销timerfd fd
----------------------------

native x86-64路径为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close(6)
   → file_close_fd(6)

在共享 ``files_struct->file_lock`` 下，内核：

::

   fdt->fd[6] = NULL
   clear open_fds bit 6
   clear close_on_exec bit 6
   update next_fd if needed

parent与helper共享同一个fdtable，因此fd 6对两个线程同时消失。后续fd分配可以复用数字6。

close路径持有从fdtable取出的最后file reference ``F6``，所以fd slot撤销后仍能同步完成：

::

   filp_flush(F6)
   → fput_close_sync(F6)
   → final __fput(F6)

``timerfd_fops`` 没有 ``flush`` callback，固定 ``filp_flush`` 返回0。

为什么eventpoll_release走fast path
---------------------------------

``__fput(F6)`` 在file-specific ``timerfd_release`` 之前调用通用：

::

   eventpoll_release(F6)

上一章删除最后watcher时已经在 ``F6->f_lock`` 下发布：

::

   F6->f_ep = NULL

因此eventpoll release不需要扫描任何watching eventpoll，也不会再次访问已经逻辑删除的 ``I``。这是显式 ``EPOLL_CTL_DEL`` 带来的close fast path。

timerfd_release怎样处理cancel list
---------------------------------

``__fput`` 随后调用：

::

   timerfd_release(inode, F6)

第一步是：

.. code-block:: c

   timerfd_remove_cancel(T);

只有以下组合才把ctx加入全局 ``cancel_list``：

* clock为 ``CLOCK_REALTIME`` 或 ``CLOCK_REALTIME_ALARM``；
* settime带 ``TFD_TIMER_ABSTIME``；
* 同时带 ``TFD_TIMER_CANCEL_ON_SET``。

本场景使用相对 ``CLOCK_MONOTONIC`` one-shot，所以：

::

   T->might_cancel = false

``timerfd_remove_cancel`` 不获取全局cancel-list mutation路径，也不删除任何RCU list node。

inactive hrtimer为什么cancel返回0
-------------------------------

``T`` 不是alarmtimer ctx，因此release调用：

.. code-block:: c

   hrtimer_cancel(&T->t.tmr);

上一批中一次性timer已经经历：

::

   queued
   → callback running
   → timerfd_tmrproc returns HRTIMER_NORESTART
   → inactive

之后没有再次settime，所以 ``hrtimer_active`` 为false。 ``hrtimer_try_to_cancel`` 的lockless fast path直接返回0； ``hrtimer_cancel`` 不等待callback，也不从CPU timerqueue删除节点。

固定结果：

::

   hrtimer_cancel result = 0
   T->t.tmr remains inactive

release为何使用kfree_rcu(T)
---------------------------

最后执行：

.. code-block:: c

   kfree_rcu(T, rcu);

从调用这一刻起，timerfd ctx退出合法活动对象图：

* ``T->t.tmr`` 不得再次arm；
* ``T->ticks`` 与 ``T->expired`` 不得访问；
* ``T->wqh`` 不得再注册或执行callback；
* ``F6->private_data`` 成为不可解引用的旧地址。

memory不会要求在 ``timerfd_release`` 返回前立即归还slab。RCU callback会在所有先前RCU read-side临界区完成后执行实际free。

本场景已先显式DEL并清空wait queue， ``kfree_rcu`` 不替代callback removal；它处理的是剩余通用RCU lifetime约束。

F6的通用file/path怎样结束
-------------------------

``timerfd_release`` 返回后， ``__fput`` 继续：

::

   fops_put
   → file_f_owner_release
   → put_file_access
   → dput([timerfd] pseudo dentry)
   → mntput(per-file anon_inode_mnt reference)
   → file_free(F6)

普通timerfd复用singleton ``anon_inode_inode``。本次只结束：

* ``[timerfd]`` per-file pseudo dentry；
* 该file持有的mount reference；
* ``struct file F6``。

全局 ``anon_inode_inode`` 与 ``anon_inode_mnt`` 继续存在。

``fput_close_sync`` 返回后，第一条close syscall使用 ``filp_flush`` 的0结果返回CPL 3：

::

   close(6) = 0

close(7)怎样进入eventpoll release
--------------------------------

parent随后执行 ``close(7)``。fdtable阶段同样完成：

::

   fdt->fd[7] = NULL
   clear open_fds bit 7
   clear close_on_exec bit 7

``F7`` 是唯一file reference，close再次通过：

::

   filp_flush(F7) = 0
   → fput_close_sync(F7)
   → final __fput(F7)
   → ep_eventpoll_release(inode, F7)

``F7->private_data`` 指向 ``EP``。

空eventpoll为何仍执行两遍drain
------------------------------

``ep_eventpoll_release`` 进入：

::

   ep_clear_and_put(EP)

尽管 ``EP->rbr`` 已空，通用teardown仍保持固定结构：

#. 处理/唤醒可能存在的eventpoll poll waiters；本场景 ``EP->poll_wait`` 与 ``EP->wq`` 均为空；
#. 获取 ``EP->mtx``；
#. 第一遍 ``ep_drain_pollwaits`` 遍历rbtree并注销所有target callbacks；本场景遍历0项；
#. 第二遍 ``ep_drain_tree`` 删除所有epitems；本场景遍历0项；
#. 释放 ``EP->mtx``；
#. 下降eventpoll reference。

两遍结构不能因为本场景为空就改写成“直接free”。它保证非空情况下所有callback先失效，随后才允许epitem storage退出。

EP.refcount怎样从1归零
----------------------

上一章DEL已经释放epitem持有的reference：

::

   EP->refcount: 2 → 1

剩余1由eventpoll file ``F7`` 持有。 ``ep_clear_and_put`` 最后调用：

::

   ep_put(EP)

结果：

::

   EP->refcount: 1 → 0

rbtree为空，满足最后reference的完整性检查，于是调用：

::

   ep_free(EP)

``ep_free`` 完成：

* NAPI busy-poll状态收尾；
* ``EP->mtx`` 销毁；
* user accounting reference释放；
* eventpoll wakeup source注销；
* ``kfree_rcu(EP, rcu)`` 排队。

从 ``ep_free`` 返回起， ``EP`` 的逻辑生命周期结束。实际storage同样在RCU grace period后回收。

F7与eventpoll path怎样释放
-------------------------

``ep_eventpoll_release`` 返回后，通用 ``__fput(F7)`` 继续：

::

   dput([eventpoll] pseudo dentry)
   → mntput(per-file anon_inode_mnt reference)
   → file_free(F7)

最后：

::

   fput_close_sync(F7) returns
   → close(7) returns 0
   → parent resumes CPL 3

固定没有signal、reschedule或user-return work，最终：

::

   RAX = 0
   RIP = instruction after close(7)

三种RCU对象应怎样区分
--------------------

本实验中出现三次RCU-delayed storage回收：

#. 第150章 ``kfree_rcu(I)``：保护epitem的RCU观察者；
#. 本章 ``kfree_rcu(T)``：结束timerfd ctx storage；
#. 本章 ``kfree_rcu(EP)``：保护eventpoll topology的RCU观察者。

它们可以在不同grace period callback中完成。项目状态不应声称三块memory在 ``close(7)`` 返回前必然已经实际释放。

能够确定的是：

::

   I, T, EP logical lifetime = ended
   no active fd/reference can legally access them
   storage free = pending or completed after RCU grace period

完整控制流
----------

::

   parent close(6)
   → remove fd 6 and cloexec bit
   → fput_close_sync(F6)
   → eventpoll_release sees F6->f_ep=NULL
   → timerfd_release
   → timerfd_remove_cancel no-op
   → hrtimer_cancel(inactive) returns 0
   → kfree_rcu(T)
   → release [timerfd] pseudo path
   → file_free(F6)
   → close(6) returns 0

   parent close(7)
   → remove fd 7 and cloexec bit
   → fput_close_sync(F7)
   → ep_eventpoll_release
   → empty pollwait drain
   → empty epitem drain
   → EP refcount 1 → 0
   → ep_free / kfree_rcu(EP)
   → release [eventpoll] pseudo path
   → file_free(F7)
   → close(7) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：timerfd + eventpoll lifecycle complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* zero-time ``epoll_wait`` result：0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* ``close(7)`` result/RAX：0；
* shared fd 6：closed and unallocated；
* shared fd 7：closed and unallocated；
* timerfd file ``F6``：freed；
* timerfd ctx ``T``：logical lifetime ended；
* ``T`` storage：queued/freed through ``kfree_rcu`` grace period；
* embedded hrtimer：inactive before ctx teardown；
* callback ``P``：freed synchronously during DEL；
* epitem ``I``：logical lifetime ended；
* ``I`` storage：queued/freed through ``kfree_rcu`` grace period；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended；
* ``EP`` storage：queued/freed through ``kfree_rcu`` grace period；
* ``[timerfd]`` / ``[eventpoll]`` per-file pseudo paths：released；
* singleton ``anon_inode_inode``：active；
* global ``anon_inode_mnt``：mounted；
* helper：阻塞在旧timerfd/eventpoll之外；
* parent/helper blocked mask：仍包含之前实验留下的 ``SIGUSR1``；
* private/shared pending ``SIGUSR1``：none；
* shared ``files_struct``：active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. fdtable撤销、file teardown、ctx logical death与RCU storage free是不同边界。
#. 显式DEL让timerfd close的 ``eventpoll_release`` 走 ``f_ep=NULL`` fast path。
#. CLOCK_MONOTONIC relative timerfd不加入clock-change cancel list。
#. 已到期one-shot hrtimer为inactive，release中的 ``hrtimer_cancel`` 返回0。
#. timerfd release使用 ``kfree_rcu(T)``，不会同步等待实际slab free。
#. callback必须在ctx wait queue消失之前删除；本场景已由DEL完成。
#. per-file pseudo dentry释放不销毁全局singleton anon inode。
#. 空eventpoll close仍保持pollwait-first、tree-second的两遍drain结构。
#. file持有eventpoll最后reference，close使refcount从1归零。
#. ``ep_free`` 结束EP逻辑生命周期，并通过 ``kfree_rcu`` 延迟storage回收。
#. ``I``、 ``T`` 与 ``EP`` 的RCU callback互相独立。
#. close返回0时三者均不可再访问，即使实际memory free尚未发生。
#. 整个场景不产生磁盘filesystem、journal、writeback或block I/O。

下一任务
--------

当前没有已选定场景。优先候选是pidfd与epoll组合：

::

   clone/fork child
   → pidfd_open(child_pid, 0) publishes fd 6
   → epoll_create1(EPOLL_CLOEXEC) publishes fd 7
   → epoll_ctl ADD pidfd EPOLLIN
   → parent blocks in epoll_wait
   → child exits and becomes waitable
   → pidfd poll callback queues epitem and wakes parent
   → epoll_wait returns one event
   → waitid(P_PIDFD, fd 6, ...) consumes exit status

开始前必须固定clone flags、child exit status、pidfd type、wait semantics、zombie/reap时点、poll mask、epoll callback与scheduler顺序。

资料
----

* `Linux 7.2-rc1 fs/timerfd.c：timerfd_release、hrtimer_cancel与kfree_rcu <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_clear_and_put、ep_put与ep_free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/open.c：close与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput通用file/path teardown <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
