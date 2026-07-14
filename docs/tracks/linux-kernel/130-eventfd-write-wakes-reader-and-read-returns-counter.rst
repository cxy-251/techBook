第一百三十章：eventfd write() 怎样唤醒reader并让read()返回counter？
================================================================

上一章结束时，parent已经阻塞在eventfd read中：

::

   ctx->count        = 0
   parent state      = TASK_INTERRUPTIBLE
   parent wait entry = linked in ctx->wqh
   wait entry        = non-exclusive
   CPU0 current      = helper

helper现在执行：

.. code-block:: c

   uint64_t three = 3;
   write(6, &three, sizeof(three));

固定条件：

* fd 6仍指向同一个blocking eventfd file；
* ``three`` 是有效、可读的8字节userspace对象；
* 输入值3不等于 ``ULLONG_MAX``；
* counter当前为0，不存在overflow；
* parent是唯一waiter；
* 没有signal、copy fault或调度异常；
* helper write返回后在eventfd之外阻塞，使parent最终被scheduler选中。

本章结束在helper write返回8、parent read返回8，parent用户buffer得到64位值3，eventfd counter重新变为0；fd 6与ctx仍保持打开。

write怎样进入eventfd_write
-------------------------

native x86-64路径是：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_write(6, &three, 8)
   → ksys_write
   → vfs_write
   → eventfd_write

``eventfd_fops`` 使用普通 ``.write`` callback。 ``eventfd_write`` 首先检查：

.. code-block:: c

   count == sizeof(__u64)

固定长度8合法。随后：

.. code-block:: c

   copy_from_user(&ucnt, buf, 8)

得到：

::

   ucnt = 3

eventfd拒绝用户写入 ``ULLONG_MAX``，因为该值保留给counter overflow状态；3合法。

counter怎样从0增加到3
--------------------

helper取得：

.. code-block:: c

   spin_lock_irq(&ctx->wqh.lock);

CPU0本地中断关闭。锁内同时观察：

::

   ctx->count = 0
   parent wait entry is active

写入允许条件是：

.. code-block:: c

   ULLONG_MAX - ctx->count > ucnt

固定数值代入：

::

   ULLONG_MAX - 0 > 3

条件为true，所以write不需要等待counter空间，结果预设为8，然后执行：

::

   ctx->count: 0 → 3

这一步发生在waitqueue lock内，先于reader wakeup。

为什么先改counter再wake
----------------------

read等待条件就是：

.. code-block:: c

   ctx->count != 0

writer必须先发布 ``count=3``，再调用wake。因为waiter检查条件、writer修改条件和waitqueue扫描都由同一把 ``wqh.lock`` 保护，parent被唤醒后重新取得锁时必然能观察到此次counter更新。

这套顺序保障的是内核eventfd状态机；userspace不需要另建一个与counter分离的condition变量。

wake_up_locked_poll做了什么
--------------------------

counter增加后， ``waitqueue_active`` 为true，helper执行：

::

   wake_up_locked_poll(&ctx->wqh, EPOLLIN)

此时 ``ctx->wqh.lock`` 仍由helper持有。

wake scan找到parent的non-exclusive entry，并通过 ``default_wake_function`` 进入task wakeup路径：

::

   try_to_wake_up(parent, TASK_NORMAL, ...)
   → parent state: TASK_INTERRUPTIBLE → TASK_RUNNING
   → enqueue parent on CPU0 runqueue

wake的语义是让parent变为runnable：

* 不会在helper持锁时直接切换到parent；
* 不会替parent执行 ``eventfd_ctx_do_read``；
* 不会立即把3复制进parent userspace；
* 不保证helper的write syscall尚未返回时parent已经运行。

固定单CPU顺序中，helper继续执行当前kernel stack。

helper怎样返回8
---------------

wake scan完成后，helper清除 ``current->in_eventfd`` 标记，释放 ``wqh.lock`` 并重新打开本地IRQ。

``eventfd_write`` 返回：

::

   sizeof(__u64) = 8

因此：

::

   __x64_sys_write returns 8
   → helper CPL 3, RAX=8

固定程序随后让helper在eventfd之外阻塞。scheduler选择已经runnable的parent。

parent从哪里恢复
---------------

context switch恢复parent原来的kernel stack。执行从：

::

   do_wait_intr_irq
   → schedule() returns

继续。 ``do_wait_intr_irq`` 立即重新执行：

.. code-block:: c

   spin_lock_irq(&ctx->wqh.lock);

因此恢复后的parent再次持有waitqueue lock，本地IRQ关闭。

locked wait宏重新检查：

::

   ctx->count == 3

条件为true，循环结束。宏执行：

::

   __remove_wait_queue(&ctx->wqh, &parent_wait)
   __set_current_state(TASK_RUNNING)

parent的wait entry从queue中移除。该entry位于parent kernel stack上，read返回后结束生命周期。

普通counter模式怎样读取3
----------------------

``eventfd_read`` 继续调用：

::

   eventfd_ctx_do_read(ctx, &ucnt)

函数在 ``wqh.lock`` 持有时执行。因为没有 ``EFD_SEMAPHORE``：

.. code-block:: c

   ucnt = ctx->count;
   ctx->count -= ucnt;

固定状态变化：

::

   ucnt        = 3
   ctx->count: 3 → 0

所以普通eventfd read的语义是一次取走整个counter。

若设置了 ``EFD_SEMAPHORE``，本次只会返回1并把counter从3减到2；本场景明确关闭该模式。

为什么read清零后可能wake writer
------------------------------

counter下降为空间后，read检查waitqueue是否还有waiter，并可执行：

::

   wake_up_locked_poll(&ctx->wqh, EPOLLOUT)

这用于唤醒因为counter接近上限而阻塞的writer或通知poll waiter“现在可写”。固定场景没有其他waiter，所以没有实际task被唤醒。

parent随后释放 ``wqh.lock`` 并重新打开本地IRQ。

3怎样复制到用户态
-----------------

锁外执行：

.. code-block:: c

   copy_to_iter(&ucnt, sizeof(ucnt), to)

固定copy成功，parent的8字节 ``value`` 变成：

::

   value = 3

copyout放在spinlock之外，避免在持有eventfd内部锁时执行可能复杂的用户内存访问。

``eventfd_read`` 最终返回8，而不是返回counter值3：

::

   read return value = bytes transferred = 8
   userspace output  = counter value 3

这两个数不能混淆。

parent怎样回到CPL3
-----------------

返回路径是：

::

   eventfd_read returns 8
   → new_sync_read
   → vfs_read
   → ksys_read
   → __x64_sys_read returns 8
   → exit_to_user_mode
   → parent CPL 3, RAX=8

此时fd 6仍在共享fdtable中。read消费counter不会自动close eventfd，也不会释放ctx。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* parent read result/RAX：8；
* parent userspace ``value``：3；
* helper write result：8；
* helper：阻塞在eventfd之外；
* shared fd 6：open、close-on-exec；
* eventfd file：仍active；
* ctx E ``count``：0；
* semaphore mode：disabled；
* ctx E wait queue：没有本次waiter；
* ``ctx->wqh.lock``：unlocked；
* parent栈上wait entry：生命周期结束；
* read/write file position：无普通offset推进语义；
* anon-inode file与ctx：仍可由fd 6访问；
* filesystem与block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd write必须正好提供8字节，并且不能写入 ``ULLONG_MAX``。
#. writer在 ``wqh.lock`` 内先增加counter，再执行reader wakeup。
#. wake只让parent runnable，不直接执行read后半段。
#. parent恢复原kernel stack，并重新取得同一waitqueue lock后检查counter。
#. 非semaphore模式read一次取得整个counter，并把count清零。
#. read返回值8表示传输了8字节；counter值3写入用户buffer。
#. counter消费不会关闭fd，也不会销毁eventfd ctx。
#. eventfd全部操作停留在内存对象与scheduler路径，不产生磁盘I/O。

下一任务
--------

当前eventfd场景已经闭环。优先候选是继续追踪fd关闭与anon-inode ctx最终释放：

::

   parent close(6)
   → remove shared fd publication
   → synchronous final __fput
   → eventfd_release
   → EPOLLHUP wake
   → eventfd_ctx_put
   → kref reaches zero
   → free eventfd id and ctx
   → release anon-inode file/path

也可以切换到timerfd或epoll，以eventfd作为ready source继续追踪poll callback与ready list。

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：eventfd_write、eventfd_read与counter语义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 include/linux/wait.h：locked waitqueue宏与non-exclusive entry <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/wait.h>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：waitqueue扫描与do_wait_intr_irq恢复 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：try_to_wake_up、enqueue与scheduler恢复 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
