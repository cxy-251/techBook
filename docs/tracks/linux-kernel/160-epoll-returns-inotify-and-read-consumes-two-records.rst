第一百六十章：parent怎样从epoll event读取两条inotify_event记录？
================================================================================

上一章结束时，parent已经被唤醒并恢复原来的 ``epoll_wait`` 内核栈。inotify group ``G`` 的notification queue按FIFO顺序保存：

::

   Ecreate = wd 1, FS_CREATE, name "new.txt"
   Eclose  = wd 1, FS_CLOSE_WRITE|FS_EVENT_ON_CHILD, name "new.txt"

``EP.rdllist`` 中只有一个level-triggered epitem ``I``。本章先让 ``epoll_wait`` 返回一个 ``EPOLLIN`` event，再执行：

.. code-block:: c

   char buf[4096];
   ssize_t n = read(6, buf, sizeof(buf));

本章固定条件：

* parent的用户events array与4096字节read buffer均已映射、可写；
* 不发生copy fault、signal或并发reader；
* queue中恰好只有上一章的两条事件；
* 两条事件的name均为 ``new.txt``，字符串长度7；
* ``sizeof(struct inotify_event)=16``；
* inotify fd保持blocking；
* registration保持level-triggered；
* 本章不执行 ``EPOLL_CTL_DEL``、 ``inotify_rm_watch`` 或close。

本章结束在 ``read`` 返回64，两条event都被消费并释放。watch、inotify fd、epoll fd与registration继续存在；level-triggered epitem因为在 ``epoll_wait`` 交付时queue仍非空而暂留ready list，成为stale-ready item。

parent恢复后怎样清理EP.wq waiter
-------------------------------

parent从：

::

   schedule()

返回到eventpoll wait loop。exclusive栈waiter ``W`` 完成cleanup：

::

   parent state = TASK_RUNNING
   remove W from EP.wq

因此：

::

   EP.wq = empty

``EP.rdllist`` 已包含 ``I``，所以parent不再重新进入睡眠。

epoll为什么还要re-poll inotify fd
--------------------------------

callback只证明“目标file可能ready”。真正向用户交付前， ``ep_send_events`` 在 ``EP.mtx`` 下把ready list移入本地scan batch，并对 ``I`` 调用：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → inotify_poll(F6, no-new-registration poll table)

``inotify_poll`` 在 ``G.notification_lock`` 下检查：

::

   fsnotify_notify_queue_is_empty(G) == false
   G.q_len == 2

因此返回：

::

   EPOLLIN | EPOLLRDNORM

与epitem interest相交后，用户可见revents为 ``EPOLLIN``。

epoll_wait向用户复制什么
------------------------

``epoll_put_uevent`` 写入：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0x494E4F36

registration不是edge-triggered或one-shot，因此成功交付后：

::

   I → EP.rdllist tail

这一步发生时inotify queue仍然包含两条record，所以重新排入ready list是正确的level-trigger行为。

``epoll_wait`` 返回：

::

   RAX = 1

回到CPL 3时，epoll只交付“fd 6可读”。它没有移除任何inotify event，也不知道queue中有一条还是两条record。

inotify read为什么先安装自己的wait entry
---------------------------------------

parent随即执行：

::

   read(6, buf, 4096)

VFS根据 ``F6->f_op->read`` 进入：

::

   inotify_read(F6, buf, 4096, &pos)

``inotify_read`` 建立栈wait entry ``R``：

::

   DEFINE_WAIT_FUNC(R, woken_wake_function)
   add_wait_queue(&G.notification_waitq, &R)

此时wait queue暂时包含：

::

   G.notification_waitq = { epoll callback P, read waiter R }

即使queue已经非空，read仍按统一结构先安装wait entry，再尝试取event。由于可以立即取得event， ``R`` 不会进入 ``wait_woken`` 或 ``schedule``。

第一条record怎样计算为32字节
---------------------------

read在 ``G.notification_lock`` 下调用：

::

   get_one_event(G, count=4096)

queue首部是 ``Ecreate``。内核用户record固定头为：

::

   sizeof(struct inotify_event) = 16

name padding计算：

::

   name_len              = 7
   name + terminating NUL = 8
   roundup(8, 16)         = 16

所以第一条record总长度：

::

   16-byte header + 16-byte name area = 32 bytes

``get_one_event`` 从notification list移除 ``Ecreate``：

::

   G.q_len: 2 → 1

``copy_event_to_user`` 写入：

::

   record 0 offset = 0
   wd               = 1
   mask             = IN_CREATE
   cookie           = 0
   len              = 16
   name bytes       = "new.txt\0"
   remaining padding= zero

``inotify_mask_to_arg`` 只保留inotify userspace bits。 ``FS_CREATE`` 直接映射为 ``IN_CREATE``。

copy成功后， ``fsnotify_destroy_event`` 通过inotify backend释放 ``Ecreate`` allocation。

第二条record为什么也是32字节
---------------------------

read循环继续，remaining count变为：

::

   4096 - 32 = 4064

queue首部现在是 ``Eclose``。它具有相同wd与name长度，因此总record长度也是32字节。

从queue移除后：

::

   G.q_len: 1 → 0
   G.notification_list: empty

用户record为：

::

   record 1 offset = 32
   wd               = 1
   mask             = IN_CLOSE_WRITE
   cookie           = 0
   len              = 16
   name bytes       = "new.txt\0"
   remaining padding= zero

内核event mask曾包含：

::

   FS_CLOSE_WRITE | FS_EVENT_ON_CHILD

``inotify_mask_to_arg`` 不输出内部 ``FS_EVENT_ON_CHILD``，所以用户只看到 ``IN_CLOSE_WRITE``。

为什么read不会继续阻塞
---------------------

第二条copy后，read再次检查queue。现在：

::

   fsnotify_peek_first_event(G) = NULL

代码先准备 ``-EAGAIN`` 或 ``-ERESTARTSYS`` 作为“没有已复制数据时”的候选结果，但随后发现：

::

   start != buf

说明本次调用已经成功复制64字节，于是直接退出循环，不进入 ``wait_woken``。

最后：

::

   remove_wait_queue(&G.notification_waitq, &R)
   return buf - start

返回值为：

::

   read(6, buf, 4096) = 64

read返回后 ``G.notification_waitq`` 再次只剩epoll callback ``P``。

用户怎样遍历两条record
----------------------

用户buffer布局是：

::

   offset 0
   ├─ struct inotify_event, 16 bytes
   └─ padded name area,      16 bytes

   offset 32
   ├─ struct inotify_event, 16 bytes
   └─ padded name area,      16 bytes

遍历步长不能写成固定32，而应使用协议定义：

.. code-block:: c

   for (char *p = buf; p < buf + n; ) {
       struct inotify_event *e = (struct inotify_event *)p;
       p += sizeof(*e) + e->len;
   }

本场景两条record碰巧都是32字节，因为两个name相同且padding后 ``len=16``。

为什么epitem现在是stale-ready
-----------------------------

``epoll_wait`` 交付时，queue仍非空，所以level-triggered ``I`` 被重新放入 ``EP.rdllist``。随后 ``read`` 把queue清空，却没有直接操作eventpoll ready list。

inotify在“最后一条event被read移除”时不会发出一个not-ready callback。epoll采用下一次scan时re-poll目标file的方式验证状态。

因此本章结束时：

::

   G.queue    = empty
   I          = still linked on EP.rdllist
   inotify_poll(F6) if called now = 0

下一次零超时 ``epoll_wait`` 会取出 ``I``、重新调用 ``inotify_poll``，看到queue为空，然后不向用户复制event并把 ``I`` 留在ready list之外。

read是否删除watch
-----------------

读取notification record不会改变watch关系：

* ``M`` 仍连接 ``G`` 与 ``/work`` inode ``D``；
* ``M.wd`` 仍为1；
* IDR仍包含 ``1 → M``；
* 用户watch ucount保持不变；
* 后续匹配事件仍会继续进入 ``G``。

只有 ``inotify_rm_watch``、watched inode teardown、one-shot触发或inotify group销毁才会拆除mark。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在inotify之外；
* ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x494E4F36``；
* ``read(6)`` result：64；
* record 0：wd1、 ``IN_CREATE``、cookie0、len16、name ``new.txt``；
* record 1：wd1、 ``IN_CLOSE_WRITE``、cookie0、len16、name ``new.txt``；
* inotify fd 6：open、blocking、close-on-exec；
* fsnotify group ``G``：active；
* ``G.q_len``：0；
* ``G.notification_list``：empty；
* overflow event：not queued；
* directory mark ``M``：active，wd1；
* ``G.notification_waitq``：只包含epoll callback ``P``；
* eventpoll fd 7：open；
* ``EP.refcount``：2；
* ``EP.rbr``：包含 ``I``；
* ``EP.rdllist``：包含stale-ready ``I``；
* ``EP.wq``：empty；
* ``/work/new.txt``：存在；
* fd 8：closed；
* storage durability：未由 ``IN_CLOSE_WRITE`` 保证；
* next runtime scenario：unselected。

关键边界
--------

#. epoll callback只生成fd-level readiness，不按inotify record数量交付多个epoll slots。
#. epoll交付前必须re-poll目标file确认queue仍非空。
#. level-triggered交付时仍ready的item会重新进入ready list。
#. inotify read使用FIFO顺序移除notification records。
#. 用户record长度是 ``sizeof(struct inotify_event)+event.len``。
#. ``event.len`` 是包含NUL与padding的name区域长度，不是 ``strlen(name)``。
#. 两条 ``new.txt`` record各为32字节，本次read总计返回64。
#. 内部 ``FS_EVENT_ON_CHILD`` 不会出现在用户mask中。
#. blocking read在已经复制至少一条event后遇到empty queue会直接返回，不继续睡眠。
#. read临时wait entry与epoll callback可同时位于 ``G.notification_waitq``。
#. 消费最后一条notification不会主动从epoll ready list移除item。
#. 读取event不会删除watch或释放mark。
#. ``IN_CLOSE_WRITE`` 表示write-mode file close，不代表数据已持久化。

下一任务
--------

优先接续inotify cleanup：

::

   epoll_wait(7, events2, 1, 0)
   → inotify_poll sees empty queue
   → remove stale-ready I and return 0
   → epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove P and I
   → inotify_rm_watch(6, 1)
   → queue IN_IGNORED
   → read and consume IN_IGNORED
   → close(6), close(7)

开始前必须决定是否显式观察 ``IN_IGNORED``，以及mark销毁worker、group teardown与eventpoll teardown的精确顺序。

资料
----

* `Linux 7.2-rc1 inotify_user.c：poll、read、record padding与queue消费 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_user.c>`_
* `Linux 7.2-rc1 notification.c：FIFO peek/remove与q_len维护 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/notification.c>`_
* `Linux 7.2-rc1 eventpoll.c：ready scan、re-poll与level-triggered requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
