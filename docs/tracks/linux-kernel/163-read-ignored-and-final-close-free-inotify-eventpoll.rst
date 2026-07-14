第一百六十三章：读取IN_IGNORED后，close怎样释放inotify group与eventpoll？
================================================================================

上一章结束时，watch wd 1的逻辑生命周期已经结束，但最后一条用户通知仍在queue中：

::

   G.q_len             = 1
   G.notification_list = { Eignored }
   Eignored            = wd1, IN_IGNORED, cookie0, no name
   EP.rdllist          = { I }

parent依次执行：

.. code-block:: c

   int n = epoll_wait(7, events3, 1, 0);
   ssize_t r = read(6, buf, 4096);
   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL);
   close(6);
   close(7);

本章固定条件：

* callback ``P`` 仍挂在 ``G.notification_waitq``；
* registration ``I`` 为level-triggered ``EPOLLIN``，data为 ``0x494E4F36``；
* queue中只有一条 ``IN_IGNORED`` record；
* wd 1已经从IDR删除，mark ``M`` 不再attached或alive；
* mark reaper work可能尚未运行；
* helper阻塞在inotify之外；
* 不发生新filesystem event、signal、copy fault、close race或allocation failure；
* ``/work/new.txt`` 继续存在；
* fd 6和fd 7都是最后的file references。

本章结束在fd 6/7均关闭： ``IN_IGNORED`` 已交付并消费，epoll callback和registration已删除，fsnotify group已完成同步销毁，inotify file与eventpoll file均退出活动对象图。

epoll_wait怎样确认IN_IGNORED可读
--------------------------------

parent先执行零超时 ``epoll_wait``。 ``I`` 已经在ready list中，所以eventpoll进入delivery scan：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → inotify_poll(F6)

``inotify_poll`` 在 ``G.notification_lock`` 下观察：

::

   G.q_len == 1
   notification list not empty

因此返回：

::

   EPOLLIN | EPOLLRDNORM

与registration interest相交后，用户收到：

::

   events3[0].events   = EPOLLIN
   events3[0].data.u64 = 0x494E4F36

返回值：

::

   epoll_wait(...) = 1

因为queue在交付时仍非空，level-triggered ``I`` 再次被放回 ``EP.rdllist``。

为什么IN_IGNORED record只有16字节
--------------------------------

parent随后调用：

::

   read(6, buf, 4096)

``inotify_read`` 临时把栈waiter ``R`` 加入：

::

   G.notification_waitq = { P, R }

queue已经非空，所以 ``R`` 不会睡眠。

``get_one_event`` 看到 ``Eignored``。该event没有name：

::

   event.name_len = 0
   round_event_name_len = 0

用户record总长度只包含固定header：

::

   sizeof(struct inotify_event) = 16

``copy_event_to_user`` 写入：

::

   offset = 0
   wd     = 1
   mask   = IN_IGNORED
   cookie = 0
   len    = 0

这里的wd来自上一章入队时保存的event字段；mark自身的 ``wd`` 已经是 ``-1``。

queue怎样回到empty
------------------

在 ``G.notification_lock`` 下：

::

   remove Eignored from queue
   G.q_len: 1 → 0

copy成功后， ``fsnotify_destroy_event`` 通过inotify backend释放event allocation。

下一轮读取发现queue为空。因为已经复制16字节：

::

   start != buf

所以blocking read立即退出，不进入睡眠。最后移除waiter ``R``：

::

   G.notification_waitq = { P }

返回：

::

   read(6, buf, 4096) = 16

此时 ``I`` 又成为stale-ready item，因为read不会主动修改eventpoll ready list。

EPOLL_CTL_DEL怎样删除最后的registration
--------------------------------------

parent执行：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)

控制流取得eventpoll ``EP`` 与target file ``F6``，在 ``EP.mtx`` 下找到 ``I``。

``ep_remove`` 首先注销poll wait entry：

::

   ep_unregister_pollwait(I)
   → remove callback P from G.notification_waitq
   → free P synchronously

然后清理target file反向关系，并把 ``I`` 从两处移除：

::

   erase I from EP.rbr
   remove I from EP.rdllist

registration曾为eventpoll持有额外reference，所以：

::

   EP.refcount: 2 → 1

``I`` 的逻辑生命周期立即结束，storage通过 ``kfree_rcu`` 在RCU grace period后回收。

syscall返回：

::

   epoll_ctl(...) = 0

此时：

::

   G.notification_waitq = empty
   EP.rbr                = empty
   EP.rdllist            = empty

close inotify fd怎样销毁group
----------------------------

parent执行：

::

   close(6)

fd 6先从共享fdtable撤销，随后 ``fput_close_sync`` 在当前syscall中同步运行最后一次 ``__fput(F6)``。

因为 ``EPOLL_CTL_DEL`` 已经清除了target file的epoll反向链， ``eventpoll_release(F6)`` 走无registration路径。

file-specific release进入：

::

   inotify_release
   → fsnotify_destroy_group(G)

``fsnotify_destroy_group`` 的第一步是：

::

   G.shutdown = true

从此 ``fsnotify_add_event`` 不再接受新event。

为什么group close要等待mark reaper
---------------------------------

``fsnotify_destroy_group`` 随后清除group中仍存在的marks。本场景的 ``M`` 已在 ``inotify_rm_watch`` 时移出 ``G.marks_list``，所以没有active mark需要再次detach。

它检查 ``G.user_waits`` 为0，然后调用：

::

   fsnotify_wait_marks_destroyed()
   → flush_delayed_work(&reaper_work)

若上一章排队的mark reaper尚未执行，这里会同步运行并等待：

::

   synchronize_srcu(fsnotify_mark_srcu)
   → inotify_free_mark(M)
   → kmem_cache_free(M)
   → fsnotify_put_group(G)

因此 ``close(6)`` 返回前，mark ``M`` 的storage一定已经完成释放。

inode connector的storage由独立 ``connector_reaper_work`` 处理。它已经从 ``/work`` inode解绑，逻辑生命周期结束；其 ``kfree`` 可能在close返回前或之后完成，不影响任何用户可访问对象。

group queue与overflow event怎样收尾
----------------------------------

mark全部完成销毁后，group teardown可靠地清空notification queue：

::

   fsnotify_flush_notify(G)

本场景queue已经被read清空，因此没有普通event需要释放。

每个inotify group还预先分配一个overflow event。它没有排队，但group销毁仍显式通过backend释放：

::

   inotify_free_event(G, G.overflow_event)

最后下降file持有的group reference：

::

   fsnotify_put_group(G)

reference到0后：

::

   inotify_free_group_priv(G)
   → verify/destroy empty watch IDR
   → decrement UCOUNT_INOTIFY_INSTANCES
   → mem_cgroup_put
   → destroy mark_mutex
   → kfree(G)

所以 ``G`` 在 ``inotify_release`` 返回前已经结束storage生命周期。

inotify file和anon-inode path怎样释放
------------------------------------

``inotify_release`` 返回0后， ``__fput`` 继续：

::

   fops_put
   → owner/access cleanup
   → dput per-file [inotify] pseudo dentry
   → mntput per-file anon_inodefs mount reference
   → file_free(F6)

全局anon_inodefs mount和singleton anon inode继续存在。

最终：

::

   close(6) = 0

fd 6、inotify file、group、overflow event和mark均不可再访问。

close eventpoll fd怎样结束EP
---------------------------

parent最后执行：

::

   close(7)

fd 7从fdtable撤销。eventpoll当前为空：

::

   EP.rbr     = empty
   EP.rdllist = empty
   EP.refcount= 1

``eventpoll_release_file`` / ``ep_clear_and_put`` 不需要删除registration。最后reference下降：

::

   EP.refcount: 1 → 0
   → ep_free(EP)
   → kfree_rcu(EP)

eventpoll的pseudo dentry、per-file anon_inodefs mount reference与 ``struct file F7`` 随 ``__fput`` 释放。

返回：

::

   close(7) = 0

close返回不要求epitem或eventpoll的RCU callback已经实际执行；它只保证这些对象已经退出所有用户可达结构。

完整收尾顺序
------------

本批三个章节的控制流可以压缩为：

::

   epoll_wait(..., 0)
   → stale I re-poll sees q_len=0
   → remove I from ready list
   → return 0

   inotify_rm_watch(6, 1)
   → detach M from group
   → queue wd1 IN_IGNORED before IDR removal
   → callback requeues I
   → remove wd1 from IDR
   → detach M from /work connector
   → schedule SRCU-safe mark/connector destruction
   → return 0

   epoll_wait(..., 0)
   → deliver EPOLLIN
   → return 1

   read(6)
   → copy 16-byte wd1 IN_IGNORED record
   → q_len 1 → 0
   → return 16

   EPOLL_CTL_DEL
   → free callback P
   → remove I from RB tree and ready list
   → EP.refcount 2 → 1

   close(6)
   → destroy group G
   → flush mark reaper and complete SRCU-safe M free
   → free overflow event and empty IDR
   → free G, F6 and pseudo path

   close(7)
   → EP.refcount 1 → 0
   → RCU-free EP
   → free F7 and pseudo path

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：inotify watch removal and final teardown complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* ``IN_IGNORED`` delivery ``epoll_wait`` result：1；
* delivered event：``EPOLLIN``、data ``0x494E4F36``；
* ``read(6)`` result：16；
* user record：wd1、``IN_IGNORED``、cookie0、len0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* ``close(7)`` result/RAX：0；
* fd 6/7：closed and unallocated；
* wd 1：invalid and absent from IDR；
* mark ``M``：freed；
* ``/work`` fsnotify connector：detached，storage freed or pending connector work completion；
* fsnotify group ``G``：freed；
* notification queue：destroyed after empty flush；
* overflow event：freed；
* inotify file ``F6``：freed；
* callback ``P``：freed synchronously by DEL；
* epitem ``I``：logical lifetime ended，storage through RCU；
* eventpoll ``EP``：logical lifetime ended，storage through RCU；
* eventpoll file ``F7``：freed；
* global anon_inodefs：active；
* ``/work/new.txt``：still exists；
* filesystem/block I/O caused by this cleanup：none；
* next runtime scenario：unselected。

关键边界
--------

#. ``IN_IGNORED`` readiness必须先经epoll re-poll确认，再向用户交付。
#. no-name ``IN_IGNORED`` record只有16字节固定header。
#. event中的wd是入队快照，独立于已失效mark的 ``wd=-1``。
#. read清空queue后，level-triggered epitem再次成为stale-ready。
#. DEL同步移除callback，同时从RB tree和ready list删除epitem。
#. callback同步free，epitem通过RCU延迟free。
#. inotify close将group置为shutdown，阻止后续event入队。
#. ``fsnotify_wait_marks_destroyed`` 使group close等待mark SRCU reaper完成。
#. mark storage在close(6)返回前已经释放；connector storage由独立worker收尾。
#. group final free会销毁空IDR、下降instance ucount并释放overflow event。
#. inotify与eventpoll都是anon-inode files；全局anon_inodefs不因最后fd关闭而卸载。
#. close返回不要求epitem/eventpoll的RCU storage回收已经完成。
#. watch removal和group close不会删除 ``/work/new.txt``。

下一任务
--------

当前没有已选定场景。优先候选是Unix domain socket与epoll：

::

   socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)
   → fd 6/7 share a connected unix socket pair
   epoll_create1(EPOLL_CLOEXEC) → fd 8
   epoll_ctl ADD fd 6 EPOLLIN|EPOLLRDHUP
   → parent blocks in epoll_wait
   → helper write(fd 7, "hello", 5)
   → unix stream receive queue wakes epoll
   → parent reads 5 bytes
   → helper shutdown(fd 7, SHUT_WR)
   → parent observes EPOLLRDHUP and read EOF

开始前必须固定socket state、sk_receive_queue、ownership、memory accounting、waitqueue callback、shutdown flags与scheduler顺序。

资料
----

* `Linux 7.2-rc1 fs/notify/inotify/inotify_user.c：inotify_read、release与group teardown入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_user.c>`_
* `Linux 7.2-rc1 fs/notify/group.c：fsnotify_destroy_group与group final free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/group.c>`_
* `Linux 7.2-rc1 fs/notify/mark.c：mark reaper与SRCU等待 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/mark.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：registration删除与eventpoll final free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/anon_inodes.c：anon-inode file/path lifetime <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/anon_inodes.c>`_
