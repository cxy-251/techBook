第一百二十章：空管道 read() 怎样进入 exclusive wait queue 并阻塞？
=================================================================

上一章结束时，parent与helper共享fd table：fd 6是anonymous pipe的read end，fd 7是write end。pipe状态是：

.. code-block:: text

   head       = 0
   tail       = 0
   occupancy  = 0
   readers    = 1
   writers    = 1

固定调度条件：

* parent当前运行在CPU0；
* helper也在CPU0 runqueue上runnable；
* parent在helper获得CPU之前执行 ``read(6, buf, 5)``；
* fd 6没有 ``O_NONBLOCK``；
* ``buf`` 可写，长度为5；
* 没有pending signal、freezer或spurious wakeup；
* helper将在parent真正阻塞后被scheduler选中。

本章结束在parent已经加入 ``pipe->rd_wait``、从CPU0 runqueue移除并停在原 ``read()`` kernel stack中，helper成为CPU0当前执行者。

read syscall 怎样找到 anon_pipe_read
------------------------------------

parent调用：

.. code-block:: c

   char buf[5];
   ssize_t n = read(6, buf, sizeof(buf));

控制流进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_read
   → ksys_read(6, buf, 5)

``ksys_read()`` 从共享fd table取得fd 6对应的read-side ``struct file``。``stream_open()`` 已经设置 ``FMODE_STREAM``，因此：

.. code-block:: text

   file_ppos(read_file) = NULL

pipe read不读取或更新普通文件的 ``f_pos``。

VFS继续执行：

.. code-block:: text

   vfs_read
   → new_sync_read
   → read_file->f_op->read_iter
   → anon_pipe_read

``anon_pipe_read()`` 得到：

.. code-block:: text

   total_len = 5
   pipe      = read_file->private_data
   ret       = 0

空pipe为什么不能立即返回0
-------------------------

函数先取得：

.. code-block:: c

   mutex_lock(&pipe->mutex);

随后读取ring index：

.. code-block:: text

   head = 0
   tail = 0

``pipe_empty(head, tail)`` 为true，因此没有 ``pipe_buffer`` 可复制。

接着检查：

.. code-block:: text

   pipe->writers = 1

存在writer endpoint时，空pipe不代表EOF。read只有在 ``head == tail`` 且 ``writers == 0`` 时才返回0。固定场景仍有fd 7，所以parent必须等待数据。

由于fd 6没有 ``O_NONBLOCK``，也没有 ``IOCB_NOWAIT``，不会返回 ``-EAGAIN``。当前 ``ret=0``，也没有partial data可以先返回。

为什么必须先释放 pipe mutex
--------------------------

阻塞前，``anon_pipe_read()`` 执行：

.. code-block:: c

   mutex_unlock(&pipe->mutex);

reader不能在睡眠期间持有 ``pipe->mutex``。否则helper进入 ``anon_pipe_write()`` 时无法取得mutex，也就不能插入数据并满足reader的等待条件。

此刻pipe仍为空；parent尚未睡眠，但已经不持有pipe mutex。

exclusive wait entry 怎样建立
-----------------------------

随后进入：

.. code-block:: c

   wait_event_interruptible_exclusive(
       pipe->rd_wait,
       pipe_readable(pipe)
   );

``pipe_readable()`` 的条件是：

.. code-block:: text

   head != tail || writers == 0

固定状态仍是 ``head=tail=0`` 且 ``writers=1``，条件为false。

wait macro在parent当前kernel stack上建立一个 ``wait_queue_entry``，并设置：

.. code-block:: text

   entry.private = current parent
   entry.func    = autoremove_wake_function
   entry.flags  |= WQ_FLAG_EXCLUSIVE

``WQ_FLAG_EXCLUSIVE`` 表示一次普通wake operation在遇到成功唤醒的exclusive waiter后可以停止继续唤醒后续exclusive waiter。当前场景只有一个reader，但这个标志仍真实存在。

``prepare_to_wait_event()`` 在 ``rd_wait.lock`` 保护下把entry链接进reader wait queue，并设置：

.. code-block:: text

   parent state = TASK_INTERRUPTIBLE

设置state后再次检查condition，仍然没有数据，也没有signal，于是macro执行 ``schedule()``。

scheduler 怎样把 parent 切换出去
-------------------------------

控制流进入：

.. code-block:: text

   schedule
   → __schedule_loop(SM_NONE)
   → __schedule

scheduler看到parent的state不是 ``TASK_RUNNING``，因此把parent从CPU0 runqueue dequeue：

.. code-block:: text

   parent.on_rq = 0

helper已经runnable，``pick_next_task()`` 选择helper。``context_switch()`` 完成后：

.. code-block:: text

   rq->curr       = helper
   parent.on_cpu  = 0
   helper.on_cpu  = 1

parent的kernel stack没有消失。以下对象都保留在它的stack与task state中：

* 未完成的 ``read()`` syscall调用链；
* ``anon_pipe_read()`` 局部变量；
* ``wait_event_interruptible_exclusive`` 的wait entry；
* 返回到 ``schedule()`` 后继续执行的位置。

helper现在可以取得 ``pipe->mutex``，因为parent在加入wait queue之前已经释放它。

当前精确状态
------------

* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3，helper userspace即将调用write；
* parent state：``TASK_INTERRUPTIBLE``；
* parent ``on_rq=0``、``on_cpu=0``；
* parent kernel stack：停在wait macro内部的 ``schedule()``；
* parent wait entry：已链接到 ``pipe->rd_wait``；
* wait entry flag：``WQ_FLAG_EXCLUSIVE``；
* pipe mutex：unlocked；
* ``head=0``、``tail=0``、occupancy=0；
* ``writers=1``，因此不是EOF；
* copied bytes：0；
* parent user buffer：尚未修改；
* read result：尚未产生；
* signal：无；
* next entry：helper调用 ``write(7, "hello", 5)``。

关键边界
--------

#. 空pipe加上仍存在的writer意味着blocking wait，不是EOF。
#. 空pipe且没有writer才使read返回0。
#. ``O_CLOEXEC`` 不会让read变成nonblocking。
#. reader必须在sleep前释放 ``pipe->mutex``，writer才能改变condition。
#. wait entry位于sleeping task自己的kernel stack，task睡眠期间仍有效。
#. ``TASK_INTERRUPTIBLE`` 允许signal打断；本场景固定没有signal。
#. exclusive wait控制wake-one语义，不表示pipe只能有一个reader。
#. parent不是从read入口重新开始；被唤醒后会恢复原kernel stack并继续wait macro。

资料
----

* `Linux 7.2-rc1 fs/read_write.c：read syscall、ksys_read与VFS read_iter dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 fs/pipe.c：anon_pipe_read、pipe_readable与reader等待路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
* `Linux 7.2-rc1 include/linux/wait.h：wait_event_interruptible_exclusive展开与WQ_FLAG_EXCLUSIVE <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/wait.h>`_
* `Linux 7.2-rc1 kernel/sched/core.c：schedule与blocking task dequeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
