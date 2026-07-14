第一百二十七章：parent 被唤醒后，futex_wait 为什么返回0却不自动重读用户字？
======================================================================================

上一章结束时：

::

   helper FUTEX_WAKE_PRIVATE result = 1
   U                                = 1
   parent state                     = TASK_RUNNING
   parent on_rq                     = 1
   parent on_cpu                    = 0
   H->waiters                       = 0
   H chain                          = no parent q
   q.lock_ptr                       = NULL

helper随后按固定时序在futex之外阻塞。CPU0进入scheduler并选择已经runnable的parent。

本章结束在parent返回CPL 3：原 ``FUTEX_WAIT_PRIVATE`` syscall结果为0，用户字U仍为1；kernel没有在wake后再次读取U，也没有替用户程序完成condition loop或C语言层面的acquire load。

scheduler 怎样恢复原 futex stack
--------------------------------

helper阻塞后，CPU0执行调度：

::

   schedule
   → __schedule
   → context switch helper → parent

parent恢复的不是syscall入口，而是上一章以前保存的kernel stack：

::

   __x64_sys_futex
   → do_futex
   → futex_wait
   → __futex_wait
   → futex_do_wait
   → schedule

context switch返回后，parent从 ``schedule()`` 后一条kernel指令继续。

此时scheduler已经把parent设置为当前task：

::

   current       = parent
   parent on_cpu = 1

``futex_do_wait()`` 随后执行：

.. code-block:: c

   __set_current_state(TASK_RUNNING);

wake路径已经通过 ``try_to_wake_up`` 将state改为 ``TASK_RUNNING``，这里再次无条件建立函数退出所需的running state。它也覆盖timeout、signal或spurious wake等其他返回路径的状态收尾。

futex_unqueue 为什么返回 0
-------------------------

``futex_do_wait()`` 返回到 ``__futex_wait()``，后者调用：

.. code-block:: c

   if (!futex_unqueue(&q))
       return 0;

这里容易把0理解错。

``futex_unqueue(q)`` 的返回语义是：

::

   1 = q仍在bucket中，本线程自己把它移除
   0 = q已经由waker移除

当前 ``q.lock_ptr=NULL``，所以 ``futex_unqueue()`` 走无锁常见路径：

* 不取得H lock；
* 不再次扫描H chain；
* 不重复执行 ``plist_del``；
* 直接返回0。

因此 ``__futex_wait()`` 判断：

::

   q was removed by a waking task
   → wait succeeded
   → return 0

这里的“succeeded”只表示该futex waiter被一个匹配wake操作移除。它不证明任何特定业务condition仍然成立，也不证明只有一个waker或没有其他用户态竞争。

为什么kernel不再次读取 U
-----------------------

parent入队前，kernel确实在H lock内检查过一次：

::

   U == expected 0

wake后， ``__futex_wait()`` 没有第二次 ``get_user(U)``。成功路径只检查q是否已经被waker移除。

这样设计的原因是futex分工：

* 用户内存保存锁、条件变量或状态机的真实状态；
* kernel只在有争用时提供sleep/wake队列；
* kernel不知道U中的1对具体用户协议意味着“锁可用”“事件发生”还是其他状态；
* 一个wake允许是spurious、竞争性或被其他waiter抢先消费条件。

所以正确用户代码必须把futex wait放在condition loop内。例如：

.. code-block:: c

   while (atomic_load_explicit(&U, memory_order_acquire) == 0) {
       long ret = syscall(SYS_futex,
                          &U,
                          FUTEX_WAIT_PRIVATE,
                          0,
                          NULL,
                          NULL,
                          0);

       if (ret == -1 && errno != EAGAIN && errno != EINTR)
           handle_error();
   }

本固定场景到syscall返回立即结束，因此不执行上面新的acquire load；只记录此时U在共享用户内存中已经是1。

返回0是否等于获得了 C/C++ acquire 语义
-------------------------------------

不能把“syscall返回0”直接写成C或C++语言层面的 ``memory_order_acquire`` 操作。

helper执行的是：

.. code-block:: c

   atomic_store_explicit(&U, 1, memory_order_release);

要让parent在语言内存模型中与该release store形成明确的synchronizes-with关系，parent仍应执行读取到1的acquire load：

.. code-block:: c

   atomic_load_explicit(&U, memory_order_acquire);

kernel中的spinlock、waiter barriers、wake_q和scheduler barriers保证kernel queue与task状态不会丢失或乱序；它们不替用户程序生成一个C抽象机可见的atomic acquire operation。

在本单CPU固定顺序中，U的实际内存值已经是1，parent后续普通执行也不会把helper先前的store从现实机器中“撤销”。技术文档仍必须区分：

* hardware/kernel观察到的实际值与调度顺序；
* C/C++程序通过release/acquire建立的正式happens-before关系。

futex_wait 怎样一路返回 syscall
-------------------------------

``__futex_wait()`` 返回0后，进入：

::

   futex_wait()

本次没有timeout：

::

   to == NULL

所以没有：

* ``hrtimer_cancel``；
* ``destroy_hrtimer_on_stack``；
* restart-block setup；
* remaining-time copyout。

``futex_wait()`` 直接返回0：

::

   futex_wait returns 0
   → do_futex returns 0
   → __x64_sys_futex returns 0

x86-64 syscall退出路径恢复用户寄存器并返回：

::

   exit_to_user_mode
   → SYSRET/IRET return path
   → parent CPL 3
   → RAX = 0

parent的user RIP位于原futex syscall之后。栈上的 ``struct futex_q q`` 随 ``__futex_wait()`` stack frame结束而结束生命周期；waker此前在设置 ``q.lock_ptr=NULL`` 后不再访问q，正是为了允许这个安全释放边界。

bucket H 的最终状态
------------------

固定key只有一个waiter，因此wake完成后：

::

   H->waiters = 0
   H chain     = no entry for K
   H lock      = unlocked

H本身不会随一次wait结束而释放。它属于该 ``mm`` 的16-bucket private futex hash，会继续服务后续private futex操作，直到mm销毁或private hash被合法替换。

相同地，U也不是kernel object：

* kernel没有为U分配永久锁对象；
* U所在anonymous page仍属于用户 ``mm``；
* futex syscall返回后，U继续是普通atomic user word；
* 只有等待期间的栈上q被创建并销毁。

为什么 wake 返回1而 wait 返回0
-----------------------------

两边返回值表达不同问题：

::

   helper FUTEX_WAKE_PRIVATE returns 1
       = one matching waiter was marked and woken

   parent FUTEX_WAIT_PRIVATE returns 0
       = this waiter was removed by a wake operation

它们都不是U的值。U当前为1来自用户态store。

若helper调用wake时没有waiter，helper会返回0；若parent入队前发现U已经不等于expected，parent会返回 ``-EWOULDBLOCK``/用户态 ``EAGAIN``。这两个快速路径也要求用户程序围绕真实condition循环，而不是把单次futex返回当成锁状态。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：private futex wait/wake complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1；
* parent ``on_cpu``：1；
* parent futex result/RAX：0；
* helper wake result：1；
* helper：阻塞在futex之外；
* userspace word ``U``：1；
* post-wake kernel re-read of U：未发生；
* post-return user acquire load：尚未执行；
* private key K：仍可由同一mm与address重新构造；
* private hash：仍存在，16 buckets；
* bucket H ``waiters``：0；
* bucket H chain：没有本次q；
* bucket H lock：unlocked；
* parent栈上 ``futex_q``：生命周期结束；
* timeout/hrtimer：none；
* restart block：未使用；
* pending signal：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. scheduler恢复parent原 ``schedule()`` 调用点，不重新进入futex syscall。
#. ``futex_unqueue`` 返回0表示q已被waker移除，因此wait成功返回0。
#. wake成功后kernel不会再次读取用户字U。
#. futex wait返回0不等于业务condition必然仍满足。
#. 用户程序必须在loop中重新读取condition并处理spurious/competitive wake。
#. helper wake返回1与parent wait返回0表达不同计数/状态，均不是U值。
#. kernel queue barriers不替代C/C++ release/acquire同步协议。
#. 要与helper release store建立语言层面的同步，parent应在用户态执行acquire load并读到1。
#. q是一次wait调用的栈上对象，wait返回后不再存在。
#. private hash bucket属于mm，单个wait结束不会销毁bucket。
#. futex没有为每个用户地址建立永久kernel lock object。

下一任务
--------

当前没有已选定场景。优先候选是 ``eventfd`` counter的阻塞读取与writer唤醒：

::

   eventfd2(0, EFD_CLOEXEC)
   → create anon_inode file and eventfd_ctx
   → parent read(eventfd, &value, 8) with counter=0
   → parent enters eventfd wait queue and schedules out
   → helper write(eventfd, value=3)
   → counter 0 -> 3 and wake reader
   → parent consumes counter and returns 8 with value=3

开始前必须固定fd编号、counter mode、blocking flags、wait queue、scheduler顺序、signal状态与file reference关系。

资料
----

* `Linux 7.2-rc1 kernel/futex/syscalls.c：futex syscall返回链 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/syscalls.c>`_
* `Linux 7.2-rc1 kernel/futex/waitwake.c：futex_do_wait、futex_unqueue判断与wait返回 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/waitwake.c>`_
* `Linux 7.2-rc1 kernel/futex/core.c：futex_unqueue与private hash lifetime <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/core.c>`_
* `Linux 7.2-rc1 kernel/futex/futex.h：futex_q与bucket结构 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/futex.h>`_
