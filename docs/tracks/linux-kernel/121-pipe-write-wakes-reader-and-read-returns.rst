第一百二十一章：pipe write() 怎样唤醒reader并让 read() 返回5？
================================================================

上一章结束时：

.. code-block:: text

   current          = helper on CPU0
   parent state     = TASK_INTERRUPTIBLE
   parent on_rq     = 0
   parent wait      = exclusive entry on pipe->rd_wait
   pipe head/tail   = 0/0
   pipe occupancy   = 0

helper与parent共享fd table。helper现在调用：

.. code-block:: c

   write(7, "hello", 5);

固定条件：

* pipe read end与write end都保持open；
* fd 7没有 ``O_NONBLOCK`` 或 ``O_DIRECT``；
* pipe ring完全为空，16个slot均可用；
* ``tmp_page[0]`` 与 ``tmp_page[1]`` 都为NULL；
* anonymous page allocation成功；
* userspace source与parent destination buffer都可访问；
* 没有signal、copy fault或scheduler异常；
* helper的write返回后会阻塞在与pipe无关的同步点，使scheduler选择已被唤醒的parent。

本章闭环到parent把5 bytes复制进userspace ``buf``，``read()`` 返回5；pipe重新为空，但刚使用的anonymous page被保留在 ``pipe->tmp_page[0]`` 中。

helper write 怎样进入 anon_pipe_write
------------------------------------

控制流是：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_write
   → ksys_write(7, "hello", 5)
   → vfs_write
   → new_sync_write
   → write_file->f_op->write_iter
   → anon_pipe_write

write-side file同样是stream，``file_ppos()`` 返回NULL，不存在普通文件position更新。

``anon_pipe_write()`` 得到：

.. code-block:: text

   total_len = 5
   ret       = 0
   pipe      = write_file->private_data

5 bytes小于等于PAGE_SIZE，因此 ``anon_pipe_get_page_prealloc()`` 不在pipe mutex外预分配page；它只对multi-page write执行preallocation。

为什么这次write不会阻塞
-----------------------

helper取得：

.. code-block:: c

   mutex_lock(&pipe->mutex);

然后确认：

.. code-block:: text

   readers       = 1
   head          = 0
   tail          = 0
   was_empty     = true
   occupancy     = 0
   max_usage     = 16

仍有reader endpoint，所以不会产生 ``SIGPIPE`` 或 ``-EPIPE``。ring没有full，helper可以立即生产一个slot。

因为pipe为空，没有上一个 ``PIPE_BUF_FLAG_CAN_MERGE`` buffer可供追加，write进入新buffer路径。

anonymous page 怎样变成 pipe_buffer
-----------------------------------

``anon_pipe_get_page()`` 的选择顺序是：

.. code-block:: text

   prealloc page
   → pipe->tmp_page[] cached page
   → alloc_page(GFP_HIGHUSER | __GFP_ACCOUNT)

固定前两者都为空，因此分配一个新的anonymous page ``Q``。

接着：

.. code-block:: text

   copy_page_from_iter(Q, offset=0, max=PAGE_SIZE, from)

虽然copy helper允许最多复制PAGE_SIZE，source iterator只有5 bytes，所以实际：

.. code-block:: text

   Q[0..4] = "hello"
   copied   = 5
   source iterator remaining = 0

copy完成后，producer index先推进：

.. code-block:: text

   pipe->head = 1

slot 0被初始化为：

.. code-block:: text

   pipe->bufs[0].page   = Q
   pipe->bufs[0].ops    = anon_pipe_buf_ops
   pipe->bufs[0].offset = 0
   pipe->bufs[0].len    = 5
   pipe->bufs[0].flags  = PIPE_BUF_FLAG_CAN_MERGE

现在：

.. code-block:: text

   head       = 1
   tail       = 0
   occupancy  = 1

5-byte write小于 ``PIPE_BUF``，并且固定allocation/copy均成功，因此本次数据作为一个完整buffer提交，没有partial write。

writer 怎样唤醒exclusive reader
-------------------------------

helper离开critical section：

.. code-block:: c

   mutex_unlock(&pipe->mutex);

进入write时pipe是empty，所以 ``was_empty=true``。函数执行：

.. code-block:: text

   wake_up_interruptible_sync_poll(
       &pipe->rd_wait,
       EPOLLIN | EPOLLRDNORM
   )

wake路径在 ``rd_wait.lock`` 保护下遍历wait queue，命中parent的exclusive wait entry。默认wake function最终进入 ``try_to_wake_up(parent, TASK_INTERRUPTIBLE, WF_SYNC)``：

.. code-block:: text

   parent state   → TASK_RUNNING
   parent on_rq   → 1
   parent queued  → CPU0 runqueue

``WF_SYNC`` 是调度提示，表达writer刚产生reader需要的数据；它不是直接把CPU控制权交给parent，也不是在helper kernel stack上执行parent的read代码。

``anon_pipe_write()`` 返回5。helper通过syscall exit回到CPL 3，随后按固定调度在一个与pipe无关的同步点阻塞。CPU0 scheduler选择已经runnable的parent。

parent 怎样从原 wait macro 继续
-------------------------------

context switch恢复的是parent原来的kernel stack。它从上一章 ``schedule()`` 的返回点继续，不是重新执行read syscall入口。

wait macro再次检查：

.. code-block:: text

   pipe_readable(pipe)
   → head=1, tail=0
   → true

``finish_wait()`` 把parent的wait entry从 ``pipe->rd_wait`` 移除，并确保task state为 ``TASK_RUNNING``。

``anon_pipe_read()`` 设置：

.. code-block:: text

   wake_next_reader = true

随后重新取得 ``pipe->mutex``，回到read loop。

5 bytes 怎样进入 parent user buffer
----------------------------------

reader现在看到slot 0：

.. code-block:: text

   buf->offset = 0
   buf->len    = 5
   total_len   = 5

``pipe_buf_confirm()`` 对anonymous pipe buffer不需要等待storage I/O。随后：

.. code-block:: text

   copy_page_to_iter(Q, 0, 5, destination)

固定copy成功：

.. code-block:: text

   parent buf[0..4] = "hello"
   ret              = 5
   pipe buffer offset = 5
   pipe buffer len    = 0

buffer被完全消费，``pipe_update_tail()`` 执行release并推进consumer index。

为什么page没有立即释放给buddy
-----------------------------

slot使用 ``anon_pipe_buf_ops``，其release路径是：

.. code-block:: text

   pipe_buf_release
   → anon_pipe_buf_release
   → anon_pipe_put_page(pipe, Q)

固定 ``page_count(Q)==1``，且 ``tmp_page[0]`` 为空，所以page被pipe本身缓存：

.. code-block:: text

   pipe->tmp_page[0] = Q

它没有立即 ``put_page()`` 回到buddy allocator。下一次需要新anonymous pipe buffer时，``anon_pipe_get_page()`` 可以直接复用这个hot page。

consumer index随后推进：

.. code-block:: text

   tail = 1

最终：

.. code-block:: text

   head       = 1
   tail       = 1
   occupancy  = 0

旧slot中的字段即使仍保留stale数值，也已经位于 ``[tail, head)`` 之外，不再代表有效pipe data；ring以后wrap时会覆盖它。

read 怎样返回用户态
-------------------

requested length已经完全满足，read loop退出。pipe重新为空，因此 ``wake_next_reader`` 被清除。这个pipe在read开始时并不full，所以不需要唤醒等待空间的writer。

``anon_pipe_read()`` 返回5，VFS更新read accounting，syscall exit让parent回到CPL 3：

.. code-block:: text

   n      = 5
   buf    = {'h','e','l','l','o'}
   RAX    = 5

fd 6/7继续open，pipe对象与pseudo inode都继续存在。

当前精确状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* read result/RAX：5；
* parent user buffer：``"hello"``；
* helper write result：5，随后阻塞在pipe之外；
* fd 6/7：仍发布且close-on-exec；
* ``pipe->readers=1``、``pipe->writers=1``、``pipe->files=2``；
* ``head=1``、``tail=1``、occupancy=0；
* active ``pipe_buffer``：0；
* page ``Q``：不再承载可读数据，缓存于 ``tmp_page[0]``；
* ``tmp_page[1]``：NULL；
* reader wait entry：已移除；
* reader/writer wait queues：无本次waiter；
* signal/SIGPIPE：未发生；
* file position：stream，无有效 ``f_pos`` 变化；
* next runtime scenario：unselected。

关键边界
--------

#. write先修改pipe ring，再执行reader wakeup，等待condition才会变为true。
#. wakeup把reader变成runnable，不直接执行reader代码。
#. ``WF_SYNC`` 是调度提示，不是强制同步context switch。
#. sleeping reader恢复原kernel stack，从wait macro后继续。
#. pipe data驻留在anonymous page，不进入page cache、filesystem或block layer。
#. 小write在成功路径中形成一个 ``PIPE_BUF_FLAG_CAN_MERGE`` buffer。
#. reader完全消费buffer后推进tail，使pipe再次empty。
#. anonymous pipe release可把page留在 ``tmp_page[]``，避免下一次write重新分配。
#. pipe empty不等于pipe对象被释放；fd 6/7仍持有两个file reference。

资料
----

* `Linux 7.2-rc1 fs/pipe.c：anon_pipe_write、reader wakeup、anon_pipe_read与page复用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
* `Linux 7.2-rc1 include/linux/pipe_fs_i.h：pipe_buffer、head/tail与ring occupancy <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pipe_fs_i.h>`_
* `Linux 7.2-rc1 include/linux/wait.h：sync poll wakeup与exclusive waiter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/wait.h>`_
* `Linux 7.2-rc1 kernel/sched/core.c：try_to_wake_up、enqueue与context switch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 fs/read_write.c：write/read syscall dispatch与stream position处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
