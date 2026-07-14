第一百三十二章：eventfd_release() 怎样发送EPOLLHUP并释放eventfd_ctx？
================================================================================

上一章结束时，fd 6已经从共享fdtable撤销，parent正在同步执行eventfd file ``F`` 的最后一次 ``__fput()``：

::

   fdtable[6]      = NULL
   file F          = final __fput in progress
   eventfd ctx E   = active
   E->kref         = 1
   E->count        = 0
   E->wqh          = empty

``__fput()`` 现在调用：

.. code-block:: c

   eventfd_release(inode, F);

本章固定条件继续保持：

* 没有poll或epoll registration；
* 没有阻塞reader、writer或其他wait queue entry；
* 没有额外 ``eventfd_ctx_fdget``、 ``eventfd_ctx_fileget`` 或内核持有的ctx reference；
* ``E->id`` 是创建时由 ``eventfd_ida`` 分配的有效非负id；
* ctx kref只剩eventfd file持有的初始reference；
* no PREEMPT_RT特殊语义、signal、CPU migration或allocation failure。

本章结束在 ``eventfd_ctx`` 已经释放，而 ``struct file F``、pseudo dentry与anon-inode mount path仍由 ``__fput()`` 做最后收尾。

eventfd_release只接收两个对象
-----------------------------

``eventfd_release`` 的入口非常短：

.. code-block:: c

   static int eventfd_release(struct inode *inode, struct file *file)
   {
       struct eventfd_ctx *ctx = file->private_data;

       wake_up_poll(&ctx->wqh, EPOLLHUP);
       eventfd_ctx_put(ctx);
       return 0;
   }

``inode`` 在此函数中没有被使用。真正需要释放的eventfd私有对象由：

::

   F->private_data = E

取得。

这也说明eventfd的counter、flags、id与wait queue都不存放在shared anonymous inode中；它们属于每个eventfd file独立持有的 ``eventfd_ctx``。

EPOLLHUP是怎样编码进wake key的
------------------------------

第一步执行：

.. code-block:: c

   wake_up_poll(&E->wqh, EPOLLHUP);

宏展开为：

::

   __wake_up(&E->wqh,
             TASK_NORMAL,
             1,
             poll_to_key(EPOLLHUP))

``poll_to_key`` 把poll event mask编码成 ``void *`` wake key。若wait queue上存在poll/epoll callback，它可以通过 ``key_to_poll`` 读取 ``EPOLLHUP``，从而知道底层eventfd file正在消失。

这里传入 ``TASK_NORMAL``，可匹配普通interruptible与uninterruptible waiter； ``nr_exclusive=1`` 表示最多消费一个exclusive waiter，同时仍可经过前面的non-exclusive entries。

本固定场景wait queue为空，所以不会真正唤醒task，也不会执行epoll callback。

空wait queue仍然经过哪条锁路径
-----------------------------

``wake_up_poll`` 不是一个“如果为空就完全跳过”的宏。它进入：

::

   __wake_up
   → __wake_up_common_lock
   → spin_lock_irqsave(E->wqh.lock)
   → __wake_up_common

``__wake_up_common`` 检查queue head，发现第一个entry就是head本身，于是直接返回。随后释放 ``E->wqh.lock`` 并恢复IRQ状态。

固定结果：

::

   wake key       = EPOLLHUP
   queue scan     = empty
   tasks awakened = 0
   E->wqh          remains empty

``EPOLLHUP`` 在这里表示release通知的事件类型，不表示系统中一定存在一个epoll instance，也不保证有用户线程观察到它。

为什么不是wake_up_pollfree
--------------------------

``wake_up_pollfree`` 用于wait queue lifetime可能独立于被poll的 ``struct file``，需要通知epoll“这个wait queue本身即将消失”，并要求RCU-delayed free。

eventfd的 ``wqh`` 直接嵌在 ``eventfd_ctx`` 中，而ctx由eventfd file及显式ctx references控制。file teardown已经先执行 ``eventpoll_release(F)``，再进入 ``eventfd_release``。因此eventfd使用普通：

::

   wake_up_poll(..., EPOLLHUP)

而不是 ``wake_up_pollfree``。

当前场景没有epoll link，这个区别不产生可见callback，但它明确了两种API的lifetime约束不同。

ctx kref为什么从1直接到0
-----------------------

HUP wake完成后执行：

.. code-block:: c

   eventfd_ctx_put(E);

它只是：

.. code-block:: c

   kref_put(&E->kref, eventfd_free);

创建eventfd时， ``kref_init`` 把reference count设为1。这个初始reference由file/ctx ownership链持有。

能够增加ctx kref的典型入口包括：

* ``eventfd_ctx_fdget``；
* ``eventfd_ctx_fileget``；
* 某些内核子系统显式保存eventfd ctx。

固定场景排除了这些引用，因此：

::

   E->kref: 1 → 0

``kref_put`` 同步调用release function：

::

   eventfd_free
   → container_of(kref, eventfd_ctx, kref)
   → eventfd_free_ctx(E)

这里没有task_work，也没有RCU callback。

eventfd id怎样归还IDA
--------------------

``eventfd_free_ctx`` 先检查：

.. code-block:: c

   if (E->id >= 0)
       ida_free(&eventfd_ida, E->id);

本场景的id由 ``ida_alloc`` 成功分配，所以有效。 ``ida_free`` 归还的是eventfd内部调试/识别id，不是用户看到的fd 6：

::

   userspace fd number = 6
   eventfd internal id = E->id

fd 6早在上一章已由fdtable回收；本步骤归还另一套独立的IDA编号空间。

归还后，未来创建的eventfd可能复用这个internal id。现有用户态没有API继续通过已关闭的fd读取旧id。

kfree之后哪些字段不能再访问
----------------------------

最后执行：

.. code-block:: c

   kfree(E);

由此同时结束以下对象的存储期：

* ``E->count``；
* ``E->flags``；
* ``E->id``；
* ``E->kref``；
* 内嵌 ``E->wqh.lock``；
* 内嵌 ``E->wqh.head``。

从这一点起，不能再查询“eventfd counter是不是0”或“wait queue是不是empty”。这些字段曾经的最后值可以写入状态记录，但其承载memory已经释放。

``F->private_data`` 仍保存旧地址值，但它已经是不可解引用的stale pointer。 ``__fput`` 后续路径不会再次调用eventfd fops或访问 ``private_data``，所以固定控制流安全。

release返回值为什么不决定close结果
----------------------------------

``eventfd_release`` 返回0。然而 ``__fput`` 的调用方式是：

.. code-block:: c

   if (file->f_op->release)
       file->f_op->release(inode, file);

``release`` 的int返回值没有被接收。Linux最后一次 ``fput`` 不能把release错误传播回已经清空fdtable slot的close语义。

本场景中close最终返回0的直接来源仍是上一章得到的：

::

   filp_flush result = 0

即使某种file operation的release callback返回非零值，通用 ``__fput`` 也不会用它覆盖close retval。

release结束时的对象图
---------------------

``eventfd_release`` 返回给 ``__fput`` 时：

::

   fd 6                 = absent
   eventfd ctx E        = freed
   E internal id        = returned to eventfd_ida
   eventfd wait queue   = no longer exists
   eventfd file F       = still in __fput
   F pseudo dentry      = still referenced by f_path
   anon_inode_mnt ref   = still held by F path

这体现了另一个lifetime分层：

::

   private device/context state may die
   before
   generic struct file/path state

下一章继续完成后半段。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 0；
* syscall：``close(6)`` 仍在执行；
* shared fd 6：closed；
* eventfd file ``F``：final ``__fput`` 仍在执行；
* ``eventfd_release``：已返回0；
* ``EPOLLHUP`` wake：已执行；
* actual poll/epoll callbacks：0；
* tasks awakened by HUP：0；
* eventfd ctx ``E``：freed；
* ``E->kref`` 最后转换：1→0；
* eventfd internal id：已归还 ``eventfd_ida``；
* ``E->count`` 与 ``E->wqh``：对象已不存在；
* pseudo dentry：仍由 ``F->f_path`` 持有；
* shared singleton anon inode：仍active；
* per-file anon-inode mount reference：仍active；
* next control entry： ``__fput`` 中 ``fops_put``、 ``dput``、 ``mntput`` 与 ``file_free``。

关键边界
--------

#. ``EPOLLHUP`` 是wake key，不代表一定有epoll observer。
#. ``wake_up_poll`` 在固定空queue上获取waitqueue lock，但唤醒0个task。
#. eventfd release使用 ``wake_up_poll``，不是 ``wake_up_pollfree``。
#. file teardown先执行 ``eventpoll_release``，再运行eventfd-specific release。
#. ctx kref与file refcount是两套不同引用计数。
#. 没有额外ctx reference时， ``eventfd_ctx_put`` 让kref从1直接到0。
#. internal eventfd id与userspace fd number属于不同编号空间。
#. ``kfree(E)`` 之后不能再访问counter、flags、id或wait queue。
#. ``release`` 返回值被 ``__fput`` 忽略；close result仍来自 ``filp_flush``。
#. ctx释放早于generic file/path teardown。

下一任务
--------

下一章继续 ``__fput(F)``：

::

   fops_put
   → file_f_owner_release
   → put_file_access
   → dput([eventfd] pseudo dentry)
   → mntput(per-file anon_inodefs mount ref)
   → file_free(F)
   → fput_close_sync returns
   → close(6) returns 0 to CPL 3

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：eventfd_release、ctx kref与free路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 include/linux/wait.h：wake_up_poll与poll wake key <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/wait.h>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：__wake_up_common与empty queue scan <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 fs/file_table.c：eventpoll_release早于file-specific release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
