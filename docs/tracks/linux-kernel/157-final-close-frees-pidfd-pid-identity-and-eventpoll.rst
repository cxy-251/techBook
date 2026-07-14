第一百五十七章：close()怎样释放pidfs inode、旧struct pid与eventpoll？
================================================================================

上一章结束时，registration已经删除：

::

   fd 6          = open pidfd F6
   fd 7          = open eventpoll F7
   F6->f_ep      = NULL
   P->wait_pidfd = empty
   EP.rbr        = empty
   EP.rdllist    = empty
   EP.refcount   = 1

child task已经被reap，数字PID ``C`` 已经可复用。旧identity仍由pidfs path保持：

::

   F6 → dentry D → inode N → old struct pid P

parent依次执行：

.. code-block:: c

   close(6);
   close(7);

本章固定条件：

* CPU0是唯一online CPU；
* parent是当前执行者；
* fd 6/7是各自file的最后userspace fd reference；
* 没有dup、SCM_RIGHTS、proc fd pin、open_by_handle或其他pidfd file；
* 没有额外 ``pidfd_get_pid`` / ``get_pid`` reference；
* ``P->attr`` 没有xattr；
* ``free_pid(P)`` 先前已经从namespace IDR和pidfs ino hashtable移除 ``P``，并通过RCU安排 ``delayed_put_pid``；
* 本章允许所需RCU grace period在最终状态前完成；
* pidfd没有 ``PIDFD_AUTOKILL``；
* 不发生close、VFS、dcache、mount或allocator failure。

本章结束时，fd 6/7、pidfd file、pidfs dentry/inode、旧 ``struct pid``、exit metadata、eventpoll file和eventpoll对象均已退出活动对象图。全局pidfs mount与全局anon_inodefs仍继续存在。

close(6)怎样撤销fd publication
------------------------------

入口：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close
   → file_close_fd(6)

``file_close_fd`` 在parent的 ``files_struct->file_lock`` 下：

* 把fdtable slot 6设为NULL；
* 清除open-fd bit 6；
* 清除close-on-exec bit 6；
* 更新 ``next_fd``。

解锁之后，任何新的fd lookup都无法取得 ``F6``。close路径自身仍持有从fdtable取出的file reference，因此对象 teardown可以继续。

``filp_flush(F6)`` 没有pidfs-specific flush callback，固定返回0。随后：

::

   fput_close_sync(F6)
   → final file reference
   → synchronous __fput(F6)

为什么eventpoll_release走fast path
--------------------------------

``__fput`` 在file-specific ``release`` 之前首先调用：

::

   eventpoll_release(F6)

上一章最后一个watcher已经删除，并在 ``F6->f_lock`` 下发布：

::

   F6->f_ep = NULL

因此eventpoll watched-file cleanup直接走fast path：

* 不扫描eventpoll reverse links；
* 不获取 ``EP.mtx``；
* 不再次处理callback或epitem。

这说明显式 ``EPOLL_CTL_DEL`` 已经把registration生命周期完整结束。

pidfs_file_release为什么不发送SIGKILL
------------------------------------

接下来 ``__fput`` 调用：

::

   pidfs_file_release(N, F6)

该callback只在file flags包含 ``PIDFD_AUTOKILL`` 时尝试向仍活着的thread group发送 ``SIGKILL``。

本场景来自：

::

   pidfd_open(C, 0)

所以：

::

   F6->f_flags & PIDFD_AUTOKILL == 0

``pidfs_file_release`` 立即返回0。child早已被reap，也不存在可发送signal的task。

真正的P reference为什么不在release callback中下降
------------------------------------------------

pidfd file没有把 ``P`` 放在 ``file->private_data``。identity关系存放在：

::

   N->i_private = P

inode在创建时接管 ``path_from_stashed(..., get_pid(P), ...)`` 传入的pid reference。file-specific release只处理行为语义；inode eviction才归还该reference。

因此 teardown继续沿generic VFS path前进。

dput怎样清除P->stashed
----------------------

``__fput`` 在fops、owner和access bookkeeping之后调用：

::

   dput(D)

pidfs superblock设置了：

::

   DCACHE_DONTCACHE

固定没有其他file、handle或dentry reference，所以 ``D`` 不会留在dcache中供未来复用。dentry prune路径调用：

::

   pidfs_dentry_operations.d_prune
   → stashed_dentry_prune(D)

``D->d_fsdata`` 保存 ``&P->stashed``。prune使用条件cmpxchg：

.. code-block:: c

   cmpxchg(&P->stashed, D, NULL);

本场景仍是同一个stashed dentry，因此成功：

::

   P->stashed: D → NULL

这一步必须发生在最终 ``put_pid(P)`` 之前； ``pidfs_free_pid`` 会检查任何stashed dentry都已经清除。

inode eviction怎样归还pid reference
-----------------------------------

``D`` 失去最后reference后，pidfs inode ``N`` 也失去活动dentry引用。pidfs使用：

::

   drop_inode = inode_just_drop
   evict_inode = pidfs_evict_inode

``pidfs_evict_inode`` 执行：

.. code-block:: c

   clear_inode(N);
   put_pid(P);

这次 ``put_pid`` 归还pidfs inode持有的identity reference。

为什么P可能还要等待一个RCU callback
-----------------------------------

上一章回收child时：

::

   release_task
   → free_pid(P)

``free_pid`` 已经完成：

* 从pid namespace IDR删除数字PID ``C``；
* 从pidfs inode-number rhashtable移除 ``P``；
* 调用 ``call_rcu(&P->rcu, delayed_put_pid)``。

那个RCU callback代表task/PID-linkage一侧最后的延迟reference drop。close fd 6时可能出现两种时间顺序：

::

   delayed_put_pid first → inode eviction performs final put_pid

或：

::

   inode eviction first  → delayed_put_pid performs final put_pid

两条顺序都受同一refcount保护，不产生语义差异。本章固定在最终状态前RCU grace period已经完成，所以两次drop最终都已发生。

final put_pid怎样释放exit metadata与P
-----------------------------------

最后一次 ``put_pid(P)`` 看到refcount归零，执行：

::

   pidfs_free_pid(P)
   → free struct pidfs_attr
   → free struct pid P
   → put pid namespace reference

``pidfs_free_pid`` 首先验证：

::

   P->stashed == NULL

然后读取 ``P->attr``。本场景：

* attr不是NULL；
* attr不是 ``PIDFS_PID_DEAD`` error marker；
* xattr list为空。

因此直接：

.. code-block:: c

   kfree(P->attr);

其中保存的：

::

   PIDFS_ATTR_BIT_EXIT
   exit_code = 42 << 8

随attr一起结束生命周期。随后 ``P`` 从pid namespace的pid cache释放。

从这一刻起：

* old pidfd identity不再存在；
* ``P->wait_pidfd`` storage也随 ``P`` 消失；
* 未来数字PID ``C`` 的新进程只会拥有新的 ``struct pid``。

pidfs mount为什么继续存在
-------------------------

``__fput(F6)`` 在 ``dput(D)`` 后执行：

::

   mntput(F6->f_path.mnt)

这只归还该file path持有的pidfs mount reference。 ``pidfs_init`` 在boot时通过 ``kern_mount`` 建立全局 ``pidfs_mnt``，全局reference仍存在，因此不会卸载pidfs。

最后：

::

   file_free(F6)
   close(6) returns 0

回到用户态的短暂状态是：

::

   fd 6 = closed
   fd 7 = still open
   EP   = active but empty

close(7)怎样结束eventpoll
-------------------------

parent接着执行 ``close(7)``。fdtable撤销fd 7及其close-on-exec bit， ``filp_flush(F7)`` 返回0， ``fput_close_sync`` 同步进入final ``__fput(F7)``。

file-specific callback：

::

   ep_eventpoll_release(F7)
   → ep_clear_and_put(EP)

上一章已经执行显式DEL，所以：

::

   EP.rbr     = empty
   EP.rdllist = empty
   EP.wq      = empty
   EP.poll_wait = empty

``ep_clear_and_put`` 仍保持固定两遍结构：

#. 获取 ``EP.mtx``；
#. ``ep_drain_pollwaits`` 扫描空rbtree；
#. ``ep_drain_tree`` 再次扫描空rbtree；
#. 释放 ``EP.mtx``。

随后：

::

   ep_put(EP): refcount 1 → 0
   → ep_free(EP)

``ep_free`` 销毁mutex/user/wakeup-source bookkeeping，并执行：

.. code-block:: c

   kfree_rcu(EP, rcu);

因此 ``EP`` 的logical lifetime在close路径中结束，storage在RCU grace period后释放。

I与EP的RCU释放是否依赖P
----------------------

上一章已经对 ``I`` 执行 ``kfree_rcu``；本章对 ``EP`` 执行另一个 ``kfree_rcu``； ``P`` 还有来自 ``free_pid`` 的 ``delayed_put_pid``。

三条RCU callback：

::

   I storage free
   EP storage free
   delayed_put_pid(P)

彼此没有对象所有权依赖。每条都只在自己的pre-RCU logical unlink完成后回收storage。具体callback执行顺序不改变最终状态。

``__fput(F7)`` 最后释放 ``[eventpoll]`` per-file pseudo dentry和anon_inodefs mount reference，再执行 ``file_free(F7)``。全局singleton ``anon_inode_inode`` 与 ``anon_inode_mnt`` 继续存在。

两个close怎样返回
-----------------

两个file-specific ``release`` callback都返回0，close syscall的结果来自各自 ``filp_flush``，固定都是0：

::

   close(6) = 0
   close(7) = 0

parent最终回到CPU0、CPL 3，RAX为最后一次 ``close(7)`` 的0。

最终精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：pidfd/eventpoll lifecycle complete；
* current executor：parent；
* CPU：CPU0，CPL 3；
* parent：``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``close(7)``；
* last result/RAX：0；
* ``close(6)`` result：0；
* fd 6：closed and unallocated；
* fd 7：closed and unallocated；
* pidfd file ``F6``：freed；
* pidfs dentry ``D``：pruned/freed；
* ``P->stashed``：在 ``P`` 释放前已清零；
* pidfs inode ``N``：evicted/freed；
* old ``struct pid P``：logical lifetime ended，storage在最终pid ref drop后释放；
* ``P->attr`` exit metadata：freed；
* numeric PID ``C``：可复用，本章没有创建新owner；
* callback ``CB``：上一章已同步释放；
* epitem ``I``：logical lifetime ended，storage经RCU释放；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended，storage经RCU释放；
* global ``pidfs_mnt``：mounted；
* global anon_inodefs mount/singleton inode：active；
* child task：不存在；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. pidfd file release与pid identity reference drop不是同一步。
#. 未设置 ``PIDFD_AUTOKILL`` 时close不会发送SIGKILL。
#. identity reference由pidfs inode持有，并在inode eviction中归还。
#. stashed dentry必须在 ``struct pid`` 最终释放前从 ``P->stashed`` 清除。
#. ``DCACHE_DONTCACHE`` 使无引用pidfs dentry不长期留在dcache。
#. 数字PID早在 ``free_pid`` 时已可复用，pidfd close结束的是旧identity storage。
#. inode ref drop与 ``delayed_put_pid`` 的先后可交换，refcount保证只有一次final free。
#. ``pidfs_free_pid`` 最终释放exit metadata和 ``struct pid``。
#. pidfs使用独立pseudo filesystem，不是eventfd使用的singleton anon inode path。
#. 全局pidfs mount不会因最后一个pidfd close而卸载。
#. 显式DEL使pidfd close的eventpoll cleanup走 ``F6->f_ep=NULL`` fast path。
#. empty eventpoll close仍执行pollwait-first、tree-second drain框架。
#. ``I``、 ``EP`` 和 ``P`` 的RCU回收互相独立。
#. close返回0不要求所有RCU callback在返回指令之前执行；对象已经不可由用户访问。
#. 整个场景不产生磁盘I/O、journal或writeback。

固定源码依据
------------

* `fs/file_table.c：__fput通用释放顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c#L486-L532>`_
* `fs/pidfs.c：pidfs_file_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c#L660-L683>`_
* `fs/pidfs.c：pidfs_evict_inode与d_prune <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c#L790-L818>`_
* `fs/libfs.c：path_from_stashed与stashed_dentry_prune <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/libfs.c#L2170-L2250>`_
* `kernel/pid.c：put_pid、free_pid与delayed_put_pid <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/pid.c#L90-L147>`_
* `fs/pidfs.c：pidfs_free_pid <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c#L176-L200>`_
* `fs/eventpoll.c：ep_clear_and_put与ep_eventpoll_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L1190-L1255>`_
