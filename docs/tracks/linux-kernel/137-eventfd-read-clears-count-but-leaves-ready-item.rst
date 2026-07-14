第一百三十七章：eventfd read() 怎样清零counter却暂时留下ready epitem？
================================================================================

上一章结束时，level-triggered epoll已经向parent交付过一次 ``EPOLLIN``，但用户程序尚未读取eventfd：

::

   fd 6                  = eventfd file F6
   eventfd ctx E.count   = 5
   fd 7                  = eventpoll file F7
   eventpoll EP.rbr      = contains epitem I
   eventpoll EP.rdllist  = contains I
   eventfd E.wqh         = contains callback entry P
   I interest            = EPOLLIN | EPOLLERR | EPOLLHUP
   I data                = 0xEFD6

parent现在执行：

.. code-block:: c

   uint64_t value;
   read(6, &value, sizeof(value));

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper共享同一 ``mm`` 与 ``files_struct``；
* parent和helper都是 ``SCHED_NORMAL``；
* eventfd为blocking、non-semaphore模式；
* ``E->count=5``；
* 用户buffer有效、可写且覆盖8字节；
* 没有signal、copy fault、fd race或额外reader；
* epoll registration保持level-triggered；
* 没有 ``EPOLLET``、 ``EPOLLONESHOT``、 ``EPOLLEXCLUSIVE`` 或 ``EPOLLWAKEUP``；
* helper继续阻塞在eventfd之外；
* 本章不调用 ``epoll_wait``、 ``epoll_ctl`` 或close。

本章结束在 ``read`` 返回8、用户buffer得到5、 ``E->count`` 归零；epitem ``I`` 仍暂时留在 ``EP->rdllist``，等待下一次event delivery重新poll目标file并判断它已经不再满足 ``EPOLLIN``。

read怎样找到eventfd file
-----------------------

x86-64 syscall入口沿既有VFS路径进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_read
   → ksys_read
   → fdget_pos(6)
   → vfs_read
   → new_sync_read
   → eventfd_read

fd 6仍指向 ``F6``， ``F6->private_data`` 指向 ``E``。本次 ``fdget_pos`` 持有一个临时file reference，防止read执行期间另一个共享fdtable线程使 ``F6`` 进入最终 ``__fput``。

eventfd为什么不进入等待
-----------------------

``eventfd_read`` 先检查iov长度至少为8，然后执行：

.. code-block:: c

   spin_lock_irq(&E->wqh.lock);

CPU0本地IRQ在临界区内关闭。此时：

::

   E->count = 5

因此条件 ``!E->count`` 为false，read不会进入：

::

   wait_event_interruptible_locked_irq(...)

parent始终保持current，不改变task state，不调用scheduler，也不加入eventfd wait queue。

non-semaphore read怎样消费全部counter
------------------------------------

锁内调用：

.. code-block:: c

   eventfd_ctx_do_read(E, &ucnt);

该helper要求 ``E->wqh.lock`` 已持有。由于未设置 ``EFD_SEMAPHORE``：

::

   ucnt     = E->count = 5
   E->count = E->count - ucnt = 0

因此一次read取得整个counter，而不是只减1。

这一步只修改eventfd状态。它还没有改变epoll的RB tree、ready list或registration对象。

为什么read发送EPOLLOUT wake
---------------------------

counter从5降到0后，eventfd拥有更多可写空间。 ``eventfd_read`` 设置：

::

   current->in_eventfd = 1

随后检查 ``waitqueue_active(&E->wqh)``。queue中仍有 ``epoll_ctl(ADD)`` 建立的callback entry ``P``，因此执行：

.. code-block:: c

   wake_up_locked_poll(&E->wqh, EPOLLOUT);

注意这里发送的是 ``EPOLLOUT``，不是 ``EPOLLIN``：

* read让counter变小；
* eventfd变得可继续写入；
* 对关心可写性的poll observer而言，这是 ``EPOLLOUT`` 状态。

``E->wqh.lock`` 已由eventfd_read持有，所以使用locked wake变体，不重复获取同一个waitqueue lock。

callback为什么忽略这次wake
---------------------------

``P->wait.func`` 是 ``ep_poll_callback``。wake core调用它时：

::

   key       = poll_to_key(EPOLLOUT)
   pollflags = EPOLLOUT
   epi       = I
   ep        = EP

callback取得：

::

   spin_lock_irqsave(&EP->lock, flags)

然后检查incoming poll bits是否与interest相交：

.. code-block:: c

   if (pollflags && !(pollflags & I->event.events))
       goto out_unlock;

``I->event.events`` 在ADD时被内核补入 ``EPOLLERR|EPOLLHUP``，但不包含 ``EPOLLOUT``：

::

   EPOLLOUT & (EPOLLIN | EPOLLERR | EPOLLHUP) = 0

因此callback直接释放 ``EP->lock``，不会：

* 把 ``I`` 新增到ready list；
* 操作 ``EP->ovflist``；
* 唤醒 ``EP->wq`` 上的task；
* 唤醒 ``EP->poll_wait`` observer；
* 修改 ``I->event`` 或 ``I->data``。

由于 ``P`` 是non-exclusive wait entry，callback最终返回值对exclusive wake quota没有实际作用；queue entry本身继续挂在 ``E->wqh`` 上，供未来 ``EPOLLIN`` 或HUP等匹配事件再次调用。

为什么已有ready item没有立即删除
-------------------------------

关键点是： ``I`` 在read开始前已经位于 ``EP->rdllist``。本次 ``EPOLLOUT`` callback只处理“这次incoming wake是否值得把item标ready”，它不负责重新验证ready list中已有item的当前状态。

因此read完成后出现：

::

   target readiness for EPOLLIN = false
   I membership in EP.rdllist   = still true

这不是event丢失，也不是永久错误。epoll ready list是一条“需要重新检查”的候选队列。真正向用户交付前， ``ep_send_events`` 必须再次调用：

::

   ep_item_poll(I)
   → eventfd_poll(F6)

只有重新poll后，epoll才知道 ``E->count=0`` 已使 ``EPOLLIN`` 消失，并把候选item从ready list移除。

level-triggered为什么会产生这个状态
-----------------------------------

上一章交付事件时， ``ep_deliver_event`` 发现：

::

   !(I->event.events & EPOLLET)

于是按level-triggered规则把 ``I`` 重新放回 ``EP->rdllist``。epoll没有替用户读取eventfd，也不能假设用户在 ``epoll_wait`` 返回后立即完成read。

用户read发生在另一个syscall中，eventfd只通过poll wake告知状态变化。由于变化方向是 ``EPOLLOUT``，且当前interest不包含它，已有ready candidate不会在read syscall中被同步摘除。

read怎样返回用户态
------------------

wake完成后：

::

   current->in_eventfd = 0
   spin_unlock_irq(&E->wqh.lock)

本地IRQ恢复。然后：

.. code-block:: c

   copy_to_iter(&ucnt, 8, to)

固定用户buffer有效，所以复制：

::

   value = 5

``eventfd_read`` 返回8，表示传输字节数。VFS释放临时fd/file reference，syscall exit返回CPL 3：

::

   RAX = 8

parent没有读取epoll event buffer，也没有消耗或修改 ``events[0]`` 中上一章留下的用户态数据。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent latest syscall：``read(6, &value, 8)``；
* parent read result/RAX：8；
* userspace ``value``：5；
* helper：阻塞在eventfd之外；
* shared fd 6：open、blocking、close-on-exec；
* eventfd file ``F6``：active；
* eventfd ctx ``E``：active；
* ``E->count``：0；
* ``E->wqh.lock``：unlocked；
* ``E->wqh``：仍含callback entry ``P``；
* latest eventfd wake key：``EPOLLOUT``；
* actual parent/task wake from该key：0；
* shared fd 7：open、close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：仍含epitem ``I``；
* ``EP->rdllist``：仍含 ``I``；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：empty；
* ``I->event.events``：``EPOLLIN|EPOLLERR|EPOLLHUP``；
* ``I->pwqlist``：仍含 ``P``；
* target current ``EPOLLIN`` readiness：false；
* filesystem/block I/O：none；
* next control entry：parent执行零超时 ``epoll_wait(7, events2, 1, 0)``。

关键边界
--------

#. non-semaphore eventfd read一次取得整个counter并清零。
#. counter非零时，eventfd read不建立wait entry、不改变task state。
#. eventfd read使可写空间增加，因此发送 ``EPOLLOUT`` wake key。
#. epoll callback interest不包含 ``EPOLLOUT``，所以不修改ready state或唤醒parent。
#. callback entry ``P`` 仍保留在eventfd wait queue上。
#. epoll ready list保存的是待重新验证的candidate，不是永远有效的readiness事实。
#. level-triggered delivery会在目标仍ready时把item重新排入ready list。
#. 用户在另一个syscall中清除readiness后，已有ready item可暂时保留。
#. stale-ready item由下一次event delivery中的 ``f_op->poll`` recheck清理。
#. read返回8表示字节数，用户buffer中的5才是counter值。

下一任务
--------

下一章执行：

::

   epoll_wait(7, events2, 1, 0)
   → initial ready candidate I exists
   → ep_start_scan moves I to local scan batch
   → eventfd_poll sees count=0 and reports EPOLLOUT only
   → interest intersection is zero
   → I is not delivered and not requeued
   → EP.rdllist becomes empty
   → zero-time epoll_wait returns 0

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：eventfd_read、eventfd_ctx_do_read与EPOLLOUT wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll_callback的event-mask过滤 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/read_write.c：read VFS入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
