第一百五十八章：inotify怎样建立目录watch并让parent阻塞在epoll_wait？
================================================================================

上一批的pidfd与eventpoll对象已经全部释放。本章开始一个独立的运行期实验：parent监视ext4目录 ``/work``，helper随后创建并关闭 ``/work/new.txt``。

用户态先执行：

.. code-block:: c

   int ifd = inotify_init1(IN_CLOEXEC);                  /* fd 6 */
   int wd = inotify_add_watch(ifd, "/work",
                              IN_CREATE | IN_CLOSE_WRITE); /* wd 1 */
   int epfd = epoll_create1(EPOLL_CLOEXEC);              /* fd 7 */

   struct epoll_event ev = {
       .events = EPOLLIN,
       .data.u64 = 0x494E4F36,
   };
   epoll_ctl(epfd, EPOLL_CTL_ADD, ifd, &ev);
   epoll_wait(epfd, events, 1, -1);

本章固定条件：

* 只有CPU0 online；
* parent与helper是同一进程中的两个线程，共享 ``mm_struct`` 与 ``files_struct``；
* 两个线程均为 ``SCHED_NORMAL``；
* fd 0..5已经占用，下一空闲fd依次为6和7；
* ``/work`` 已存在，是当前mount namespace中可读、可写的ext4目录；
* 本进程此前没有inotify instance，当前用户未触及inotify实例、watch或queue上限；
* 不使用 ``IN_NONBLOCK``、 ``IN_ONESHOT``、 ``IN_EXCL_UNLINK``、 ``IN_MASK_ADD`` 或 ``IN_ONLYDIR``；
* watch mask恰好是 ``IN_CREATE|IN_CLOSE_WRITE``；
* epoll registration是level-triggered，只请求 ``EPOLLIN``，不使用 ``EPOLLET``、 ``EPOLLONESHOT`` 或 ``EPOLLEXCLUSIVE``；
* event data固定为 ``0x494E4F36``；
* 初始目录中不存在 ``new.txt``；
* 没有并发watch修改、文件事件、signal、close、poll或allocation failure。

本章结束在parent以 ``TASK_INTERRUPTIBLE`` 阻塞于eventpoll自己的wait queue。inotify group的notification queue仍为空；epoll callback已经挂到inotify group的另一条wait queue上。

inotify_init1怎样建立fsnotify group
----------------------------------

native x86-64入口是：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_inotify_init1(IN_CLOEXEC)
   → do_inotify_init

``IN_CLOEXEC`` 与 ``O_CLOEXEC`` 数值一致。固定没有 ``IN_NONBLOCK``，所以新file保持blocking语义。

``do_inotify_init`` 调用：

::

   inotify_new_group(inotify_max_queued_events)
   → fsnotify_alloc_group(&inotify_fsnotify_ops,
                          FSNOTIFY_GROUP_USER)

新 ``fsnotify_group G`` 的通用部分被初始化为：

::

   G.refcnt             = 1
   G.user_waits         = 0
   G.notification_list  = empty
   G.notification_waitq = empty
   G.notification_lock  = unlocked
   G.mark_mutex         = unlocked
   G.marks_list         = empty
   G.shutdown           = false

``inotify_new_group`` 继续建立inotify私有状态：

* 预分配一个仅供queue overflow使用的 ``IN_Q_OVERFLOW`` event；
* ``G.max_events`` 固定为系统默认16384；
* 保存当前 ``mm`` 对应的memory cgroup；
* 初始化watch descriptor使用的IDR与 ``idr_lock``；
* 增加当前user namespace中的inotify instance ucount。

overflow event只是预备对象。它不在notification list中， ``G.q_len=0``。

fd 6保存的是什么
----------------

随后：

.. code-block:: c

   anon_inode_getfd("inotify", &inotify_fops, G,
                    O_RDONLY | O_CLOEXEC)

建立anon-inode file ``F6`` 并发布fd 6：

::

   F6->private_data = G
   F6->f_op          = &inotify_fops
   F6 flags          = O_RDONLY | O_CLOEXEC

``inotify_fops`` 的关键入口为：

* ``poll = inotify_poll``；
* ``read = inotify_read``；
* ``release = inotify_release``；
* ``fasync = fsnotify_fasync``。

因此fd 6是读取notification records的只读fd。它不代表被监视的目录file，也不持有 ``/work`` 的open file description。

inotify_add_watch怎样解析/work
------------------------------

parent随后执行：

::

   inotify_add_watch(6, "/work", IN_CREATE | IN_CLOSE_WRITE)

syscall首先通过fdtable临时pin住 ``F6``，验证：

::

   F6->f_op == &inotify_fops

然后 ``inotify_find_inode`` 使用 ``user_path_at`` 解析 ``/work``。未设置 ``IN_DONT_FOLLOW``，所以lookup允许跟随最终symlink；固定路径直接指向ext4目录inode ``D``。

watch要求对目标inode拥有 ``MAY_READ`` 权限，并经过 ``security_path_notify`` 检查。固定全部通过。

目录watch的内部mask为什么比用户mask更大
---------------------------------------

``inotify_update_watch(G, D, arg)`` 在 ``G.mark_mutex`` 下先查找已有mark。固定是新group，未找到已有mark，于是进入 ``inotify_new_watch``。

分配 ``inotify_inode_mark M`` 后：

.. code-block:: c

   fsnotify_init_mark(&M.fsn_mark, G);
   M.fsn_mark.mask = inotify_arg_to_mask(D, arg);

用户请求只有：

::

   IN_CREATE | IN_CLOSE_WRITE

由于 ``D`` 是目录， ``inotify_arg_to_mask`` 还自动加入：

::

   FS_UNMOUNT
   FS_EVENT_ON_CHILD

因此内部mark mask是：

::

   FS_CREATE
   | FS_CLOSE_WRITE
   | FS_UNMOUNT
   | FS_EVENT_ON_CHILD

``FS_EVENT_ON_CHILD`` 不是用户可读取的一条独立事件。它告诉fsnotify：该目录mark关心子dentry上的文件事件，并需要把子文件名带给watcher。

wd为什么固定为1
---------------

新mark先进入group的IDR：

.. code-block:: c

   idr_alloc_cyclic(idr, M, 1, 0, GFP_NOWAIT)

IDR从1开始分配，当前group此前没有watch，因此：

::

   M.wd = 1

进入IDR会为mark增加一份reference。随后增加当前用户的inotify watch ucount，再调用：

::

   fsnotify_add_inode_mark_locked(&M.fsn_mark, D, 0)

这一步把mark连接到：

* fsnotify group ``G`` 的mark集合；
* ext4目录inode ``D`` 的fsnotify connector；
* inode聚合的 ``i_fsnotify_mask``。

由于目录现在监视child event，fsnotify还会维护child dentry上的 ``DCACHE_FSNOTIFY_PARENT_WATCHED`` 快速判断状态。以后 ``new.txt`` 的close事件可以快速知道父目录需要通知。

``inotify_add_watch`` 返回：

::

   RAX = wd = 1

path lookup期间取得的临时path reference随后释放；真正pin住目录inode的是fsnotify mark及其connector关系。

epoll怎样挂到inotify wait queue
-------------------------------

``epoll_create1(EPOLL_CLOEXEC)`` 建立eventpoll ``EP``、anon-inode file ``F7``，并发布fd 7。初始：

::

   EP.refcount = 1
   EP.rbr      = empty
   EP.rdllist  = empty
   EP.wq       = empty

``epoll_ctl(7, EPOLL_CTL_ADD, 6, &ev)`` 分配epitem ``I``。epoll会自动把 ``EPOLLERR|EPOLLHUP`` 加入interest，实际event mask为：

::

   EPOLLIN | EPOLLERR | EPOLLHUP

registration key仍然是：

::

   watched file = F6
   source fd     = 6
   data          = 0x494E4F36

``ep_insert`` 调用目标file的poll入口：

::

   inotify_poll(F6, epoll poll table)

``inotify_poll`` 先执行：

.. code-block:: c

   poll_wait(F6, &G.notification_waitq, wait);

这让epoll在 ``G.notification_waitq`` 上安装non-exclusive callback entry ``P``：

::

   P.func = ep_poll_callback
   P.private/base → I

随后在 ``G.notification_lock`` 下检查queue。当前 ``G.notification_list`` 为空，所以返回0。

registration完成后：

::

   EP.refcount = 2
   EP.rbr      = { I }
   EP.rdllist  = empty
   G.notification_waitq = { P }

额外的eventpoll reference属于epitem ``I`` 的生命周期。

parent阻塞在哪一条wait queue
----------------------------

parent调用：

::

   epoll_wait(7, events, 1, -1)

首次ready-list检查为空，于是epoll建立栈上task waiter ``W``，把它加入：

::

   EP.wq

``W`` 是exclusive wait entry，private指向parent task。parent状态转换为：

::

   TASK_RUNNING
   → TASK_INTERRUPTIBLE

然后释放相关锁并调用 ``schedule()``。

必须区分两条wait queue：

::

   G.notification_waitq = { epoll callback P }
   EP.wq                 = { sleeping parent waiter W }

文件事件先唤醒 ``G.notification_waitq`` 上的callback；callback再把 ``I`` 放入ready list并唤醒 ``EP.wq`` 上的parent。

scheduler选择helper
-------------------

单CPU0上parent离开runqueue：

::

   parent on_rq  1 → 0
   parent on_cpu 1 → 0

helper是固定场景中唯一runnable task，scheduler切换到helper。helper返回CPL 3，准备执行下一章的 ``openat``、 ``write`` 与 ``close``。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_INTERRUPTIBLE``；
* parent ``on_rq=0``、 ``on_cpu=0``；
* parent kernel stack：暂停在 ``epoll_wait → ep_poll → schedule``；
* helper state：``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* fd 6：open blocking inotify file ``F6``，close-on-exec；
* fsnotify group ``G``：active， ``refcnt=1``；
* ``G.q_len``：0；
* ``G.notification_list``：empty；
* ``G.max_events``：16384；
* watch descriptor：1；
* directory mark ``M``：active on ext4 ``/work`` inode ``D``；
* ``M.mask``：``FS_CREATE|FS_CLOSE_WRITE|FS_UNMOUNT|FS_EVENT_ON_CHILD``；
* ``G.notification_waitq``：包含non-exclusive callback ``P``；
* fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP.refcount``：2；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：empty；
* ``EP.wq``：包含parent exclusive waiter ``W``；
* filesystem/block I/O：本章没有数据I/O；
* next control entry：helper ``openat("/work/new.txt", O_CREAT|O_WRONLY|O_TRUNC, 0644)``。

关键边界
--------

#. inotify fd保存 ``fsnotify_group``，不是被watch目录的open file。
#. blocking与close-on-exec是独立属性；本fd blocking且设置close-on-exec。
#. overflow event预分配不等于queue中已有overflow notification。
#. directory watch会自动增加 ``FS_EVENT_ON_CHILD`` 与 ``FS_UNMOUNT``。
#. wd属于每个inotify group自己的IDR；新group首个wd固定为1。
#. mark同时连接group与watched inode，并pin住对应watch关系。
#. epoll callback位于 ``G.notification_waitq``，parent task waiter位于 ``EP.wq``。
#. 初始queue为空使 ``inotify_poll`` 返回0，epitem不进入ready list。
#. epitem增加eventpoll reference，使 ``EP.refcount`` 从1变为2。
#. parent真正阻塞于eventpoll wait queue，不直接阻塞于inotify notification queue。

下一任务
--------

下一章由helper执行：

::

   openat(..., "/work/new.txt", O_CREAT|O_WRONLY|O_TRUNC, 0644)
   → fsnotify_create queues IN_CREATE
   → write(fd 8, "data", 4)
   → close(fd 8)
   → fsnotify_close queues IN_CLOSE_WRITE
   → first queue wake runs epoll callback
   → parent becomes runnable

资料
----

* `Linux 7.2-rc1 inotify_user.c：group、watch、poll与syscall入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_user.c>`_
* `Linux 7.2-rc1 group.c：fsnotify_group与notification wait queue初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/group.c>`_
* `Linux 7.2-rc1 eventpoll.c：epitem、callback注册与epoll_wait阻塞 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
