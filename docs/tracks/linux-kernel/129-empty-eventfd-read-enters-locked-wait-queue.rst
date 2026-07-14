第一百二十九章：eventfd read() 怎样在counter为0时进入locked wait queue？
====================================================================

上一章结束时，parent已经得到blocking eventfd fd 6：

::

   fd 6          = O_RDWR | close-on-exec
   ctx->count    = 0
   semaphore     = disabled
   wait queue    = empty

parent现在执行：

.. code-block:: c

   uint64_t value = 0;
   read(6, &value, sizeof(value));

固定条件：

* ``sizeof(value)==8``；
* fd 6仍打开，helper没有close它；
* counter在parent进入kernel时仍为0；
* file没有 ``O_NONBLOCK``；
* kiocb没有 ``IOCB_NOWAIT``；
* 没有pending signal；
* parent与helper都是CPU0上的 ``SCHED_NORMAL`` task；
* 调度顺序固定为parent阻塞后helper运行；
* 没有poll、epoll或其他eventfd waiter。

本章结束在parent以非exclusive wait entry挂入 ``ctx->wqh``，状态为 ``TASK_INTERRUPTIBLE``，已经从CPU0调度出去；helper成为当前执行者。

read怎样进入eventfd_read
-----------------------

native x86-64路径是：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_read(6, &value, 8)
   → ksys_read
   → vfs_read
   → new_sync_read
   → eventfd_read

VFS从共享fdtable解析fd 6，取得使用 ``eventfd_fops`` 的file。 ``new_sync_read`` 建立同步kiocb与目标 ``iov_iter``，再调用 ``.read_iter``。

``eventfd_read`` 首先验证目标buffer至少能容纳一个 ``__u64``：

.. code-block:: c

   if (iov_iter_count(to) < sizeof(ucnt))
       return -EINVAL;

本场景长度正好8，因此继续。

为什么counter与等待条件使用同一把锁
---------------------------------

``eventfd_read`` 执行：

.. code-block:: c

   spin_lock_irq(&ctx->wqh.lock);

这把锁同时保护：

* ``ctx->count``；
* ``ctx->wqh.head``；
* read与write之间的条件检查和wait publication顺序。

CPU0进入critical section时本地中断被关闭。固定观察结果：

::

   ctx->count == 0

read不能立即完成。

为什么本次不会返回EAGAIN
-----------------------

count为0时，代码先检查：

.. code-block:: c

   file->f_flags & O_NONBLOCK
   iocb->ki_flags & IOCB_NOWAIT

本场景两者都为false，所以不会返回 ``-EAGAIN``。read进入：

::

   wait_event_interruptible_locked_irq(ctx->wqh, ctx->count)

这个宏要求调用者已经持有 ``wqh.lock`` 且本地中断关闭；睡眠时宏会释放锁并重新打开中断，恢复后再以相同方式取得锁。

wait entry是否exclusive
----------------------

``wait_event_interruptible_locked_irq`` 使用：

::

   DEFINE_WAIT(__wait)
   exclusive = 0

因此parent的wait entry：

* ``private`` 指向parent task；
* wake function是 ``default_wake_function``；
* 不设置 ``WQ_FLAG_EXCLUSIVE``；
* entry对象位于parent当前kernel stack上。

非exclusive意味着一次针对该queue的普通wake扫描可以唤醒所有匹配的non-exclusive waiter。本固定场景只有parent一个waiter。

do_wait_intr_irq怎样发布waiter
-----------------------------

locked wait macro调用 ``do_wait_intr_irq``。在 ``ctx->wqh.lock`` 仍持有且IRQ关闭时，它执行：

::

   if wait entry not yet linked:
       add entry to tail of ctx->wqh

   set_current_state(TASK_INTERRUPTIBLE)
   check signal_pending(current)

固定场景没有signal，所以继续。

这里的顺序非常关键：

#. 先在queue中发布wait entry；
#. 再把parent状态设为可中断睡眠；
#. 条件检查、入队与状态变化都由同一个waitqueue lock串行化；
#. writer要修改counter并wake，也必须取得同一把lock。

因此不会出现“writer已经把count改为3并检查到queue为空，parent随后才入队”的丢失唤醒窗口。

锁与IRQ怎样在schedule前恢复
--------------------------

``do_wait_intr_irq`` 接着执行：

.. code-block:: c

   spin_unlock_irq(&ctx->wqh.lock);
   schedule();

``spin_unlock_irq`` 同时完成：

* 释放 ``ctx->wqh.lock``；
* 重新允许CPU0本地中断。

此时状态是：

::

   parent state      = TASK_INTERRUPTIBLE
   parent wait entry = linked in ctx->wqh
   ctx->count        = 0
   wqh.lock          = unlocked
   local IRQ         = enabled

只有到 ``schedule()`` 真正完成context switch，parent才离开CPU。task state设为 ``TASK_INTERRUPTIBLE`` 本身不等于已经阻塞。

scheduler怎样切换到helper
-------------------------

``schedule`` 进入 ``__schedule``。parent不是 ``TASK_RUNNING``，因此不继续作为可运行任务留在runqueue上。

固定调度条件下：

::

   parent → dequeue / sleep
   CPU0 next task → helper

context switch保存parent的kernel stack位置。parent以后被唤醒时，不会重新从syscall入口开始，也不会重新创建eventfd file；它会从 ``schedule()`` 返回点继续执行locked wait宏。

parent睡眠期间哪些对象继续存在
-----------------------------

parent不占用CPU后，以下对象仍保持活动：

* 共享fdtable中的fd 6；
* eventfd ``struct file``；
* ``eventfd_ctx`` E；
* ``ctx->count=0``；
* parent栈上的wait entry；
* wait entry对parent task的指向；
* parent完整kernel stack与syscall上下文。

ctx不会因为parent睡眠而释放。fd 6仍由共享fdtable持有，helper也可通过同一fd访问它。

为什么还没有复制用户buffer
--------------------------

``eventfd_read`` 只有在counter大于0后才会调用：

::

   eventfd_ctx_do_read(ctx, &ucnt)
   copy_to_iter(&ucnt, 8, to)

当前尚未到达这两个步骤。因此：

::

   userspace value remains 0
   ctx->count remains 0
   read result not available

read也没有file-position更新。eventfd是counter对象，不使用普通文件offset推进语义。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_INTERRUPTIBLE``；
* parent ``on_rq=0``、``on_cpu=0``；
* parent syscall：阻塞在 ``read(6, &value, 8)``；
* parent kernel stack：停在 ``do_wait_intr_irq → schedule`` 恢复点；
* fd 6：仍open并由两个线程共享；
* ctx E ``count``：0；
* ctx E wait queue：包含parent的一个non-exclusive entry；
* wait entry storage：parent kernel stack；
* ``ctx->wqh.lock``：unlocked；
* CPU0 local IRQ：enabled；
* parent userspace ``value``：仍为0；
* read copyout：尚未发生；
* signal pending：none；
* filesystem与block I/O：none；
* next entry：helper ``write(6, &three, 8)``。

关键边界
--------

#. eventfd read要求buffer至少8字节；本场景正好读取一个 ``u64``。
#. counter检查与wait-entry publication由同一个 ``wqh.lock`` 串行化。
#. locked wait宏在睡眠前释放waitqueue spinlock并重新打开本地IRQ。
#. 本次wait entry是non-exclusive，不是pipe blocking read使用的exclusive waiter。
#. ``TASK_INTERRUPTIBLE`` 允许signal中断；固定场景没有signal。
#. task state变化不等于context switch， ``schedule`` 才让parent真正离开CPU。
#. sleeping task以后恢复原kernel stack，不重新进入read syscall入口。

下一入口
--------

helper现在执行：

.. code-block:: c

   uint64_t three = 3;
   write(6, &three, sizeof(three));

下一章从helper取得同一个eventfd file开始，追踪counter从0增加到3、waitqueue wakeup，以及parent最终读出3。

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：eventfd_read与locked wait路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 include/linux/wait.h：wait_event_interruptible_locked_irq展开 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/wait.h>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：do_wait_intr_irq与waitqueue wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：schedule与task切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
