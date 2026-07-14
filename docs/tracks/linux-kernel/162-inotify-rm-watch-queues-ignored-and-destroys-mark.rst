第一百六十二章：inotify_rm_watch怎样先排入IN_IGNORED再销毁mark？
================================================================================

上一章结束时，inotify notification queue和eventpoll ready list都为空：

::

   G.q_len       = 0
   EP.rdllist    = empty
   wd 1 / mark M = active

parent现在显式删除watch：

.. code-block:: c

   int ret = inotify_rm_watch(6, 1);

本章固定条件：

* fd 6仍指向inotify file ``F6``，private data为group ``G``；
* wd 1在 ``G.inotify_data.idr`` 中唯一映射到inode mark ``M``；
* ``M`` 是 ``/work`` inode上的唯一fsnotify mark；
* callback ``P`` 仍挂在 ``G.notification_waitq``；
* eventpoll ``EP`` 的registration ``I`` 仍在RB tree中，ready list为空；
* 没有并发event producer、watch remover、group close或inode eviction；
* 不发生allocation failure、queue overflow或signal；
* mark destroy worker尚未运行；
* parent当前不阻塞在 ``epoll_wait``。

本章结束在 ``inotify_rm_watch`` 返回0：wd 1已无效， ``IN_IGNORED`` record已经入队，callback把 ``I`` 放回ready list；mark和connector已经退出活动对象图，其storage进入SRCU安全的延迟销毁路径。

syscall怎样找到wd 1对应的mark
-----------------------------

parent从CPL 3进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_inotify_rm_watch(6, 1)

入口先取得fd 6对应的file reference，并验证：

::

   F6->f_op == &inotify_fops

然后得到：

::

   G = F6->private_data

``inotify_idr_find(G, 1)`` 获取：

::

   G.inotify_data.idr_lock

在IDR中找到 ``M``，并临时增加mark reference。锁释放后，当前syscall持有的这个reference保证后续destroy期间 ``M`` 不会提前释放。

mark在删除前有哪些reference
---------------------------

watch创建完成后， ``M`` 的稳定reference主要来自：

* group的 ``marks_list`` / attached关系；
* inotify IDR中的wd映射。

本次 ``inotify_idr_find`` 又取得一个临时reference。

对象关系可以写成：

::

   G marks_list ──> M
   G idr[1]     ──> M
   /work connector obj_list contains M
   current rm_watch syscall holds temporary M ref

``fsnotify_destroy_mark`` 会先让mark退出group，再让backend处理“mark正在失效”的通知，最后由当前syscall释放临时reference并触发真正的connector detach。

fsnotify_detach_mark先改变什么
----------------------------

``inotify_rm_watch`` 调用：

.. code-block:: c

   fsnotify_destroy_mark(&M->fsn_mark, G);

它先获取：

::

   G.mark_mutex

``fsnotify_detach_mark`` 再获取 ``M.lock``，确认mark仍具有：

::

   FSNOTIFY_MARK_FLAG_ATTACHED

随后：

::

   clear ATTACHED
   remove M from G.marks_list
   drop the group-list mark reference

此时 ``M`` 已不能作为group中的active watch被新event traversal选中，但它仍暂时存在于inode connector的object list中，因为IDR和当前syscall仍持有reference。

锁顺序保持为：

::

   G.mark_mutex
   → M.lock
   → connector lock only when final reference detaches object side

本阶段结束后释放 ``G.mark_mutex``。

为什么IN_IGNORED必须在wd失效前入队
---------------------------------

随后 ``fsnotify_free_mark`` 清除：

::

   FSNOTIFY_MARK_FLAG_ALIVE

并调用inotify backend的 ``freeing_mark`` callback：

::

   inotify_freeing_mark
   → inotify_ignored_and_remove_idr

该函数的固定顺序是：

#. 先用mark当前wd排入 ``FS_IN_IGNORED`` event；
#. 再从IDR删除wd；
#. 最后下降watch ucount。

因此 ``inotify_handle_inode_event`` 读取wd时仍得到：

::

   wd = 1

若顺序反过来， ``i_mark->wd`` 会先变成 ``-1``，backend将拒绝构造用户event。当前实现明确保证用户能收到最后一条带原watch descriptor的 ``IN_IGNORED`` record。

IN_IGNORED record怎样构造
-------------------------

调用参数没有inode name：

::

   mask   = FS_IN_IGNORED
   name   = NULL
   cookie = 0

backend分配 ``inotify_event_info``，保存：

::

   event.mask        = FS_IN_IGNORED
   event.wd          = 1
   event.sync_cookie = 0
   event.name_len    = 0

因为queue开始时为空，不存在merge对象。即使队尾已经是 ``IN_IGNORED``，inotify的merge比较也会对带 ``FS_IN_IGNORED`` 的旧event返回false，避免丢失watch失效通知。

fsnotify_add_event怎样重新激活epitem
----------------------------------

``fsnotify_add_event`` 在：

::

   G.notification_lock

保护下执行：

::

   G.q_len: 0 → 1
   append Eignored to G.notification_list tail

锁释放后调用：

::

   wake_up(&G.notification_waitq)

wait queue中只有epoll callback ``P``。本次parent没有阻塞在 ``EP.wq``，所以不存在需要唤醒的task waiter； ``P`` 仍会执行并把registration标为candidate-ready：

::

   I → EP.rdllist

最终：

::

   G.notification_list = { Eignored }
   EP.rdllist           = { I }
   EP.wq                = empty

callback只负责重新建立ready membership。下一章交付前仍会通过 ``inotify_poll`` 确认queue确实非空。

wd怎样从IDR消失
---------------

record入队后， ``inotify_remove_from_idr`` 获取：

::

   G.inotify_data.idr_lock

它再次确认 ``idr[1]`` 仍指向同一个 ``M``，然后：

::

   idr_remove(1)
   drop IDR-held mark reference
   M.wd = -1

锁释放前，wd 1已经不可再被新的 ``inotify_rm_watch`` 或fdinfo lookup解析。

随后下降：

::

   UCOUNT_INOTIFY_WATCHES

用户queue中已经存在的 ``Eignored`` 保存的是独立字段 ``event.wd=1``，所以mark中的 ``M.wd=-1`` 不会改写已排队record。

最后一个mark reference怎样触发connector detach
---------------------------------------------

``fsnotify_destroy_mark`` 返回后，syscall释放最初由 ``inotify_idr_find`` 取得的临时reference。

固定场景中，这使mark refcount到达0。 ``fsnotify_put_mark`` 在 ``M.connector.lock`` 下：

::

   remove M from connector obj_list

因为 ``M`` 是 ``/work`` inode上的唯一mark，connector list变空，于是：

::

   /work inode i_fsnotify_mask = 0
   detach connector from /work inode
   clear connector object pointer
   connector type → DETACHED

该connector曾为non-evictable inotify mark持有inode reference，所以detach还在spinlock外执行对应 ``iput``，归还watch对 ``/work`` inode的pin。

``/work`` inode本身仍可能因directory path、dcache或filesystem引用继续存在；这里只结束fsnotify watch对它的引用。

为什么mark不会立即kmem_cache_free
--------------------------------

当mark最后reference下降时，代码不能立刻释放storage，因为其他CPU理论上可能仍在 ``fsnotify_mark_srcu`` read-side traversal中看到旧指针。

因此：

::

   add M to global destroy_list
   queue delayed reaper_work after 1 jiffy

worker执行：

::

   fsnotify_mark_destroy_workfn
   → move destroy_list to private list
   → synchronize_srcu(fsnotify_mark_srcu)
   → inotify_free_mark(M)
   → kmem_cache_free(M)
   → fsnotify_put_group(G)

connector storage走另一条workqueue：

::

   connector_destroy_list
   → connector_reaper_work
   → synchronize_srcu
   → kfree(connector)

``inotify_rm_watch`` 不等待这两个worker完成。它只保证wd、group membership和object attachment已经失效。

syscall返回时哪些对象已经失效
-----------------------------

当前syscall返回：

::

   inotify_rm_watch(6, 1) = 0

此时：

* wd 1已从IDR删除；
* ``M`` 不再attached或alive；
* ``M`` 不再属于 ``G.marks_list``；
* ``M`` 不再挂在 ``/work`` inode connector中；
* ``/work`` 的fsnotify mask不再包含该watch；
* ``IN_IGNORED`` record已可靠排队；
* mark/connector storage可能仍等待SRCU grace period。

因此“rm_watch返回”表示watch的逻辑生命周期已经结束，不表示所有相关allocation都已经物理释放。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：inotify explicit watch removal complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* latest syscall：``inotify_rm_watch(6, 1)``；
* latest result/RAX：0；
* fd 6：open inotify file ``F6``；
* group ``G``：active；
* ``G.q_len``：1；
* queue record：wd1、``IN_IGNORED``、cookie0、len0；
* ``G.inotify_data.idr``：no entry for wd 1；
* inotify watch ucount：decremented；
* mark ``M``：not alive、not attached、logical lifetime ended；
* ``M.wd``：-1；
* ``M`` storage：queued or completed for SRCU-delayed destruction；
* ``/work`` inode connector：detached；
* connector storage：queued or completed for SRCU-delayed destruction；
* ``G.notification_waitq``：contains callback ``P``；
* fd 7：open eventpoll file ``F7``；
* ``EP.rbr``：contains ``I``；
* ``EP.rdllist``：contains candidate-ready ``I``；
* ``EP.wq``：empty；
* ``/work/new.txt``：exists；
* next control entry：zero-time ``epoll_wait`` delivering ``IN_IGNORED`` readiness。

关键边界
--------

#. rm_watch先取得mark临时reference，再开始detach，防止并发释放。
#. ``fsnotify_detach_mark`` 先清ATTACHED并移出group list。
#. ``fsnotify_free_mark`` 通过backend callback产生watch失效通知。
#. ``IN_IGNORED`` 在IDR removal之前入队，所以用户record仍携带原wd 1。
#. 已入队event保存独立wd字段，不受随后 ``M.wd=-1`` 影响。
#. queue从空变非空时callback会重新把epitem加入ready list。
#. parent当前未睡眠，因此callback只改变ready状态，不发生task wakeup。
#. IDR reference、group-list reference和syscall临时reference依次下降。
#. 最后mark reference下降时才从inode connector object list摘除。
#. watch结束会归还fsnotify对 ``/work`` inode的pin，但不会删除目录。
#. mark与connector storage需要SRCU grace period，rm_watch不等待物理free。
#. watch逻辑生命周期结束与 ``IN_IGNORED`` 用户record消费是两个不同边界。

下一任务
--------

下一章完成：

::

   epoll_wait(7, events3, 1, 0)
   → re-poll q_len=1
   → deliver EPOLLIN
   → read(6) copies 16-byte wd1 IN_IGNORED record
   → EPOLL_CTL_DEL removes P and I
   → close(6) destroys fsnotify group and synchronizes mark destruction
   → close(7) releases eventpoll

资料
----

* `Linux 7.2-rc1 fs/notify/inotify/inotify_user.c：inotify_rm_watch与IDR removal <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_user.c>`_
* `Linux 7.2-rc1 fs/notify/inotify/inotify_fsnotify.c：IN_IGNORED构造与mark backend callbacks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_fsnotify.c>`_
* `Linux 7.2-rc1 fs/notify/mark.c：detach、reference、SRCU reaper与connector销毁 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/mark.c>`_
* `Linux 7.2-rc1 fs/notify/notification.c：queue insertion与wait queue wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/notification.c>`_
