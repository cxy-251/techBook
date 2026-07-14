第一百四十五章：close() 怎样释放signalfd与eventpoll，却保留共享sighand wait queue？
================================================================================

上一章结束时，epoll registration已经完全删除：

::

   fd 6                    = open signalfd file F6
   fd 7                    = open eventpoll file F7
   F6->f_ep                = NULL
   shared signalfd_wqh     = active, empty
   EP->rbr                 = empty
   EP->rdllist             = empty
   EP->refcount            = 1
   callback P              = freed
   epitem I                = logical-dead, kfree_rcu pending/completed

parent现在依次执行：

.. code-block:: c

   close(6);
   close(7);

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper属于同一TGID，共享 ``files_struct``、 ``signal_struct`` 与 ``sighand_struct``；
* fd 6与fd 7均没有dup、SCM_RIGHTS、pidfd_getfd、io_uring或in-flight ``fget`` reference；
* fd 6的signalfd ctx ``S`` 是唯一private-data allocation；
* fd 7的eventpoll ``EP`` 只有eventpoll file持有的基础reference；
* ``EP`` 的rbtree、ready list、poll wait list与task wait queue均为空；
* shared ``sighand->signalfd_wqh`` 为空，但 ``sighand_struct`` 仍由parent/helper持有；
* parent/helper blocked mask仍包含 ``SIGUSR1``；
* private/shared pending queue均不含 ``SIGUSR1``；
* 没有并发signal、poll、epoll、close、exec或thread exit；
* 没有VFS、security、dcache、mount或allocator failure。

本章结束在fd 6/7均已关闭；signalfd file、ctx与eventpoll file均释放，eventpoll ``EP`` 退出活动对象图并通过 ``kfree_rcu`` 回收；共享 ``sighand_struct`` 及其 ``signalfd_wqh`` 继续存在。

close(6)怎样先撤销fd publication
------------------------------

parent从CPL 3进入：

::

   __x64_sys_close(6)
   → file_close_fd(6)

``file_close_fd`` 在共享 ``files->file_lock`` 下：

::

   fdt->fd[6] = NULL
   clear open_fds bit 6
   clear close_on_exec bit 6
   update next_fd reuse hint

parent与helper共享 ``files_struct``，因此锁释放后两个线程都不能再通过fd 6找到 ``F6``。当前close路径持有从fdtable转交出来的最后file reference。

``signalfd_fops`` 没有 ``flush`` callback，固定 ``filp_flush(F6)`` 返回0。随后：

::

   fput_close_sync(F6)
   → final file reference
   → synchronous __fput(F6)

整个signalfd teardown在 ``close(6)`` 返回用户态之前完成，不经过task_work或delayed fput。

为什么eventpoll_release走fast path
--------------------------------

通用 ``__fput`` 在file-specific ``release`` 之前调用：

::

   eventpoll_release(F6)

上一章删除最后watcher时已经：

::

   WRITE_ONCE(F6->f_ep, NULL)

因此target-file侧的eventpoll release检查直接发现没有反向registration，不需要：

* 搜索eventpoll实例；
* 获取旧 ``EP->mtx``；
* 删除epitem；
* 操作共享signalfd wait queue。

这说明显式 ``EPOLL_CTL_DEL`` 已把registration teardown与file close teardown彻底分离。

signalfd_release真正释放什么
----------------------------

``__fput`` 随后调用：

.. code-block:: c

   signalfd_release(inode, F6);

固定源码只有：

.. code-block:: c

   kfree(F6->private_data);
   return 0;

因此本步骤只结束 ``struct signalfd_ctx S`` 的生命周期。 ``S`` 中唯一业务字段是signalfd内部mask：

::

   S->sigmask

它不保存pending signal，不拥有task reference，也不包含wait queue head。

``kfree(S)`` 之后不能再读取该mask； ``F6->private_data`` 成为不可解引用的stale value，后续通用 ``__fput`` 不再使用它。

为什么close signalfd不调用wake_up_pollfree
-----------------------------------------

signalfd poll registration使用：

::

   current->sighand->signalfd_wqh

这个wait queue嵌在共享 ``sighand_struct`` 中，不嵌在 ``S`` 或 ``F6`` 中。关闭某一个signalfd file不会结束queue head的lifetime。

因此 ``signalfd_release`` 不调用：

::

   wake_up_pollfree

真正的：

.. code-block:: c

   signalfd_cleanup(sighand)
   → wake_up_pollfree(&sighand->signalfd_wqh)

发生在 ``sighand_struct`` teardown路径。当前parent与helper仍存活并共享sighand，所以该路径不会运行。

固定结果：

::

   signalfd ctx S          = freed
   shared signalfd_wqh     = remains active and empty
   shared sighand_struct   = remains active

这也是本批最重要的对象归属边界。

F6的pseudo path怎样结束
----------------------

``signalfd_release`` 返回后， ``__fput(F6)`` 继续：

::

   fops_put
   → file owner/access cleanup
   → dput([signalfd] pseudo dentry)
   → mntput(per-file anon_inode_mnt reference)
   → file_free(F6)

普通signalfd复用全局singleton ``anon_inode_inode``。因此：

* per-file ``[signalfd]`` pseudo dentry结束；
* 本file的singleton inode reference下降；
* 全局 ``anon_inode_inode`` 继续存在；
* 全局 ``anon_inode_mnt`` 继续mounted；
* 没有磁盘filesystem或block I/O。

``fput_close_sync`` 返回后， ``close(6)`` 使用先前的 ``filp_flush`` result 0返回：

::

   close(6) = 0

此时fd 7与eventpoll ``EP`` 仍然active。

close(7)怎样进入eventpoll release
--------------------------------

parent随后执行：

::

   __x64_sys_close(7)
   → file_close_fd(7)
   → shared fdtable[7] = NULL
   → clear open/cloexec bookkeeping
   → filp_flush(F7) = 0
   → fput_close_sync(F7)
   → synchronous __fput(F7)

``F7->f_op`` 是 ``eventpoll_fops``，其release callback为：

::

   ep_eventpoll_release
   → ep_clear_and_put(EP)

``EP`` 当前只有file基础reference：

::

   EP->refcount = 1

所有epitem reference已在上一章由DEL归还。

ep_clear_and_put为什么仍做两遍空drain
------------------------------------

``ep_clear_and_put`` 首先检查：

::

   EP->poll_wait

固定没有其他file或epoll在poll这个epoll fd，queue为空，所以不执行 ``ep_poll_safewake``。

随后：

::

   mutex_lock(EP->mtx)
   → ep_drain_pollwaits(EP)
   → ep_drain_tree(EP)
   → mutex_unlock(EP->mtx)

虽然 ``EP->rbr`` 已空，两遍结构仍按固定顺序执行：

#. 第一遍原本用于从所有watched wait queue解除callbacks；
#. 第二遍原本用于删除所有epitems、reverse links与ready membership。

本场景两遍都没有迭代对象。保持这套顺序让eventpoll close与“用户没有显式DEL”的复杂场景使用同一个可靠teardown框架。

EP refcount怎样归零
------------------

空tree drain完成后：

::

   ep_put(EP)
   → EP->refcount: 1 → 0
   → returns true

于是立即调用：

::

   ep_free(EP)

``ep_free`` 完成：

* 恢复可能暂停的NAPI IRQ状态；
* ``mutex_destroy(&EP->mtx)``；
* ``free_uid(EP->user)``；
* 注销eventpoll wakeup source；
* ``kfree_rcu(EP, rcu)``。

从 ``kfree_rcu`` 排队开始， ``EP`` 已退出合法访问生命周期。其物理storage可能晚于 ``close(7)`` 返回才真正归还slab allocator。

为什么eventpoll file还能在EP logical-dead后继续收尾
--------------------------------------------------

``ep_eventpoll_release`` 返回后， ``__fput(F7)`` 不再访问 ``F7->private_data``。通用路径继续释放：

::

   [eventpoll] pseudo dentry
   per-file anon_inode_mnt reference
   struct file F7

因此生命周期顺序是：

::

   eventpoll private object EP logical lifetime
   → generic eventpoll file/path lifetime
   → close syscall frame

最后：

::

   close(7) = 0
   parent returns to CPL 3

blocked SIGUSR1 mask为什么仍然存在
--------------------------------

本章只关闭两个fd，没有调用 ``rt_sigprocmask`` 或pthread mask API。因此：

* parent blocked mask仍包含 ``SIGUSR1``；
* helper blocked mask仍包含 ``SIGUSR1``；
* parent private pending不含 ``SIGUSR1``；
* shared pending不含 ``SIGUSR1``。

关闭最后一个signalfd并不会自动解除signal block。若之后再次向parent发送 ``SIGUSR1``，它仍会进入pending状态，直到用户显式解除阻塞或使用其他同步signal消费接口。

这条边界必须与“signalfd已经关闭”分开理解：

::

   signalfd file lifetime ended
   ≠
   thread signal mask restored

完整释放顺序
------------

本批三章可以压缩为：

::

   epoll_wait(timeout=0)
   → stale I candidate re-polled
   → no pending SIGUSR1
   → I leaves EP.rdllist
   → return 0

   epoll_ctl(DEL)
   → remove P from shared signalfd_wqh
   → free P synchronously
   → clear F6->f_ep
   → erase I from EP.rbr
   → kfree_rcu(I)
   → EP refcount 2 → 1

   close(6)
   → final __fput(F6)
   → eventpoll fast path
   → signalfd_release kfree(S)
   → free signalfd pseudo path/file
   → return 0

   close(7)
   → final __fput(F7)
   → ep_eventpoll_release
   → empty two-pass drain
   → EP refcount 1 → 0
   → ep_free / kfree_rcu(EP)
   → free eventpoll pseudo path/file
   → return 0

共享sighand与它的signalfd wait queue不在这条file释放链中结束。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：signalfd + eventpoll lifecycle complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``close(7)``；
* last result/RAX：0；
* zero-time ``epoll_wait`` result：0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* fd 6：closed and unallocated；
* fd 7：closed and unallocated；
* signalfd file ``F6``：freed；
* signalfd ctx ``S``：freed synchronously；
* callback ``P``：freed synchronously during DEL；
* epitem ``I``：logical lifetime ended，storage由 ``kfree_rcu`` 回收；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended，storage由 ``kfree_rcu`` 回收；
* shared ``sighand_struct``：active；
* shared ``sighand->signalfd_wqh``：active、empty；
* parent/helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending：无 ``SIGUSR1``；
* shared pending：无 ``SIGUSR1``；
* singleton ``anon_inode_inode``：active；
* global ``anon_inode_mnt``：mounted；
* helper：阻塞在旧signalfd/eventpoll之外；
* shared ``files_struct``：active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. signalfd ctx与shared sighand wait queue属于不同对象。
#. ``signalfd_release`` 只释放private ctx，不销毁 ``signalfd_wqh``。
#. ``signalfd_cleanup/wake_up_pollfree`` 属于sighand teardown，不属于file close。
#. 显式DEL使target file close的eventpoll release走 ``f_ep=NULL`` fast path。
#. ``fput_close_sync`` 保证两个file的final ``__fput`` 均在close返回前执行。
#. eventpoll close即使tree为空，也保持pollwait-first、tree-second两遍drain结构。
#. eventpoll file基础reference让 ``EP->refcount`` 在close前保持1。
#. ``ep_put`` 归零后 ``ep_free`` 结束EP逻辑生命周期。
#. ``kfree_rcu(I/EP)`` 允许物理memory回收晚于syscall返回。
#. per-filepseudo dentry与mount references结束，全局anon_inodefs继续存在。
#. 关闭signalfd不会解除 ``SIGUSR1`` block，也不会恢复旧signal mask。
#. fd数字只是可复用fdtable slot，不是signalfd或eventpoll对象identity。
#. 整个释放链没有磁盘filesystem、journal或block I/O。

下一任务
--------

当前没有已选定场景。优先候选是 ``timerfd_create`` 与epoll组合：

::

   timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC) → fd 6
   timerfd_settime(one-shot relative 20ms)
   epoll_create1(EPOLL_CLOEXEC) → fd 7
   epoll_ctl ADD timerfd EPOLLIN
   parent epoll_wait blocks
   → local APIC timer interrupt
   → hrtimer callback increments expirations
   → timerfd poll callback queues epitem and wakes parent
   → epoll_wait returns EPOLLIN
   → read(fd 6, &expirations, 8) returns one expiration

开始前必须固定absolute/relative mode、clockid、cancel-on-set、interval、hrtimer base、expiration count、callback与scheduler顺序。

资料
----

* `Linux 7.2-rc1 fs/signalfd.c：signalfd_release只释放private ctx <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/signalfd.c>`_
* `Linux 7.2-rc1 include/linux/signalfd.h：signalfd_notify与共享sighand wait queue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/signalfd.h>`_
* `Linux 7.2-rc1 fs/eventpoll.c：empty tree close、ep_put与ep_free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/file_table.c：final __fput通用path/file teardown <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/anon_inodes.c：singleton anon inode与per-file pseudo path <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/anon_inodes.c>`_
