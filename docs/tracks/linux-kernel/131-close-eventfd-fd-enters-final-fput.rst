第一百三十一章：close(6) 怎样撤销eventfd fd并同步进入最后一次__fput()？
================================================================================

上一章结束时，parent已经从eventfd读出完整counter：

::

   read(6, &value, 8) = 8
   value              = 3
   eventfd count      = 0

fd 6仍然指向同一个eventfd file，parent现在执行：

.. code-block:: c

   close(6);

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper属于同一进程并共享 ``files_struct``；
* parent和helper均为 ``SCHED_NORMAL``；
* fd 6是eventfd file的唯一file reference；
* eventfd ``count=0``，不启用 ``EFD_SEMAPHORE`` 与 ``EFD_NONBLOCK``；
* fd 6设置了close-on-exec bit；
* 没有dup、SCM_RIGHTS、pidfd_getfd或正在进行的fget；
* 没有poll、epoll、io_uring或内核侧 ``eventfd_ctx_fdget`` 引用；
* eventfd wait queue为空；
* helper阻塞在eventfd之外，不持有fd 6的临时file reference；
* 没有POSIX lock、lease、FASYNC、LSM拒绝或flush错误。

本章结束在parent已经从共享fdtable撤销fd 6，并通过 ``fput_close_sync()`` 同步进入最后一次 ``__fput()``；eventfd file与ctx此时尚未释放，下一章从 ``eventfd_release()`` 接续。

close syscall怎样进入内核
-------------------------

native x86-64中， ``close`` 是syscall 3。CPU从CPL 3进入CPL 0：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close(6)

``SYSCALL_DEFINE1(close)`` 首先调用：

.. code-block:: c

   file = file_close_fd(6);

这里的“close fd”只处理fdtable publication。它还没有调用eventfd的 ``release`` callback，也没有释放 ``eventfd_ctx``。

共享fdtable中的fd 6怎样消失
--------------------------

``file_close_fd()`` 读取 ``current->files``，然后获取：

::

   files->file_lock

锁内调用 ``file_close_fd_locked(files, 6)``。固定fd有效，所以得到eventfd file指针 ``F``，并执行：

::

   fdt->fd[6] = NULL
   clear open_fds bit 6
   clear close_on_exec bit 6
   files->next_fd may move back to 6

``file_close_fd_locked()`` 不为 ``F`` 增加新引用。它只是把原本由fdtable持有的file reference转交给当前close路径。

锁释放后，fd 6已经不再是共享 ``files_struct`` 的活动描述符：

* parent不能再通过fd 6解析到 ``F``；
* helper也同时失去fd 6，因为两个线程共享同一个fdtable；
* 后续fd分配可以重新使用数字6；
* 当前close仍可继续操作 ``F``，因为它持有刚从fdtable取出的最后reference。

因此要区分两个边界：

::

   fd 6 no longer published
   ≠
   struct file F already destroyed

前者已经发生，后者还没有发生。

EFD_CLOEXEC在这里发生了什么
--------------------------

创建eventfd时， ``EFD_CLOEXEC`` 只把fd 6对应的close-on-exec bitmap bit设为1。它不写入eventfd counter，也不改变 ``eventfd_ctx``。

本次显式 ``close(6)`` 通过 ``__put_unused_fd()`` 同时清理open与close-on-exec bookkeeping。fd 6已经不存在，因此之后即使进程执行 ``execve``，也没有eventfd需要再由 ``do_close_on_exec()`` 处理。

filp_flush为什么返回0
---------------------

取得 ``F`` 后，close执行：

.. code-block:: c

   retval = filp_flush(F, current->files);

``eventfd_fops`` 没有 ``flush`` callback，因此不会运行eventfd专属flush逻辑。固定场景也没有dnotify或POSIX locks需要清理，结果为：

::

   retval = 0

close syscall仍不能立即返回。fdtable slot虽然已经清空，最后一个file reference还必须下降，并运行完整 ``__fput()`` teardown。

为什么这里使用fput_close_sync
-----------------------------

用户态close路径明确调用：

.. code-block:: c

   fput_close_sync(F);

这与普通 ``fput()`` 的语义边界不同：

* 普通 ``fput`` 在最后引用下降时，可以把 ``__fput`` 延后到task_work或delayed work；
* ``fput_close_sync`` 使用 ``file_ref_put_close`` 的close优化，并在最后引用成立时直接调用 ``__fput(F)``；
* close syscall不会先返回用户态，再异步执行eventfd release。

固定条件规定fdtable reference是唯一reference，所以：

::

   F file reference: 1 → final put
   → __fput(F) runs synchronously on parent

当前执行者仍是parent，CPU仍是CPU0，CPU mode仍为CPL 0。

__fput在release之前先做什么
--------------------------

``__fput(F)`` 先保存：

::

   dentry = F->f_path.dentry
   mnt    = F->f_path.mnt
   inode  = F->f_inode
   mode   = F->f_mode

然后依次经过通用清理入口：

::

   fsnotify_close(F)
   eventpoll_release(F)
   locks_remove_file(F)
   security_file_release(F)
   optional fasync teardown

固定eventfd pseudo file带有 ``FMODE_NONOTIFY``，没有外部fsnotify事件。没有epoll registration，因此 ``eventpoll_release(F)`` 没有需要拆除的eventpoll link；没有file lock或FASYNC状态，其余路径也不产生对象变化。

顺序仍然很重要。 ``eventpoll_release`` 位于file-specific ``release`` 之前，保证真实存在的epoll关系会先从eventpoll侧拆除，再允许底层file private state消失。本固定场景没有epoll关系，所以它只是通过该控制边界。

控制权怎样到达eventfd_release
-----------------------------

通用清理完成后， ``__fput`` 检查：

.. code-block:: c

   if (F->f_op->release)
       F->f_op->release(inode, F);

``F->f_op`` 是 ``eventfd_fops``，其 ``release`` 成员指向：

::

   eventfd_release

进入下一章前，对象状态是：

::

   shared fdtable slot 6 = NULL
   eventfd file F         = still executing final __fput
   eventfd ctx E kref     = 1
   E count                = 0
   E wait queue           = empty
   pseudo dentry/path     = still held by F

fd publication已经结束；file、ctx与path teardown尚未完成。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 0；
* syscall：``close(6)`` 正在执行；
* shared fd 6：已从fdtable撤销；
* fd 6 open bit：cleared；
* fd 6 close-on-exec bit：cleared；
* helper对fd 6的可见性：同样closed；
* eventfd file ``F``：最后一次 ``__fput`` 正在执行；
* ``F`` 的最后file reference：已由 ``fput_close_sync`` 消耗；
* ``filp_flush`` result：0；
* eventfd ctx ``E``：仍active；
* ``E->kref``：1；
* ``E->count``：0；
* ``E->wqh``：empty、unlocked；
* pseudo dentry与anon-inode path：仍由 ``F`` 的 ``f_path`` 持有；
* task_work/delayed_fput：未使用；
* next control entry：``eventfd_release(inode, F)``。

关键边界
--------

#. fdtable slot撤销与file object释放是两个不同边界。
#. 共享 ``files_struct`` 使helper与parent同时失去fd 6。
#. ``file_close_fd`` 不增加file reference，而是把fdtable reference交给close路径。
#. close-on-exec bit随fd bookkeeping一起清理，不会单独保留。
#. eventfd没有 ``flush`` callback，固定 ``filp_flush`` 返回0。
#. ``fput_close_sync`` 让最后 ``__fput`` 在close syscall返回前同步运行。
#. ``eventpoll_release`` 早于file-specific ``release``；本场景因无epoll link而无对象变化。
#. 进入 ``eventfd_release`` 时，fd已不可解析，但eventfd ctx和pseudo path仍存在。

下一任务
--------

下一章从 ``eventfd_release()`` 开始，追踪：

::

   wake_up_poll(E->wqh, EPOLLHUP)
   → empty wait-queue scan
   → eventfd_ctx_put(E)
   → kref 1 → 0
   → ida_free(eventfd id)
   → kfree(E)

资料
----

* `Linux 7.2-rc1 fs/open.c：close syscall、filp_flush与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file.c：file_close_fd与fdtable撤销 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/file_table.c：同步__fput与release调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/eventfd.c：eventfd file_operations <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
