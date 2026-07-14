第一百二十六章：FUTEX_WAKE_PRIVATE 怎样移除waiter并把parent放回runqueue？
================================================================================

上一章结束时，parent已经真正离开CPU0：

::

   parent state       = TASK_INTERRUPTIBLE | TASK_FREEZABLE
   parent on_rq       = 0
   parent on_cpu      = 0
   U                  = 0
   H->waiters         = 1
   H chain            = contains parent q
   q.lock_ptr         = &H->lock

CPU0当前执行helper。helper与parent属于同一thread group并共享同一个 ``mm_struct``，所以二者对 ``&U`` 构造出的private futex key完全相同。

helper先在用户态修改条件：

.. code-block:: c

   atomic_store_explicit(&U, 1, memory_order_release);

随后调用：

.. code-block:: c

   syscall(SYS_futex,
           &U,
           FUTEX_WAKE_PRIVATE,
           1,
           NULL,
           NULL,
           0);

固定条件：

* store在wake syscall之前完成；
* ``U`` 的page仍resident、writable且映射不变；
* 该key只有parent一个waiter；
* wake count固定为1；
* 没有PI、requeue、robust unlock、bitset过滤或signal；
* helper完成wake syscall后仍短暂运行，随后才在futex之外主动阻塞；
* 所有key lookup、spinlock与scheduler操作成功。

本章结束在helper从 ``FUTEX_WAKE_PRIVATE`` 得到返回值1；parent已经从H中移除并成为CPU0 runqueue上的 ``TASK_RUNNING`` task，但尚未恢复其旧kernel stack。

为什么必须先写 U 再调用 wake
---------------------------

futex把“条件值”保存在用户内存，kernel只管理睡眠队列。普通 ``FUTEX_WAKE`` 不会替用户程序修改U。

正确顺序是：

::

   publish protected state/data
   → store U = 1
   → FUTEX_WAKE_PRIVATE

本固定程序使用release atomic store。它保证同一helper线程中排在该store之前的用户态写，不会被语言实现移动到store之后。

在x86-64上，这个32-bit aligned release store通常不需要额外的硬件release指令，仍可表现为普通原子store；这里的关键不是具体汇编形式，而是用户程序先改变condition，再请求kernel唤醒。

如果把wake放在store之前，parent可能被唤醒后再次观察到旧条件并重新等待，甚至与错误的用户态协议组合成lost wakeup。kernel的futex barrier解决“waiter入队与waker检查queue”的竞态，不替用户程序建立错误顺序下的condition protocol。

WAKE syscall 怎样进入 futex_wake
--------------------------------

helper从CPL 3进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_futex
   → do_futex

operation为：

::

   FUTEX_WAKE | FUTEX_PRIVATE_FLAG

``futex_to_flags()`` 得到：

::

   FLAGS_SIZE_32
   FLAGS_SHARED clear

``do_futex()`` 将普通WAKE转换为全bitset匹配：

::

   bitset = FUTEX_BITSET_MATCH_ANY
   nr_wake = 1

随后进入：

::

   futex_wake(&U, flags, pop=NULL,
              nr_wake=1,
              bitset=FUTEX_BITSET_MATCH_ANY)

本场景没有 ``FUTEX_ROBUST_UNLOCK``，所以 ``futex_robust_unlock()`` 不触碰用户字。U保持helper刚写入的1。

helper为什么会找到同一个 key K
-----------------------------

``get_futex_key(&U, flags, &key, FUTEX_READ)`` 再次检查：

* 地址是4-byte aligned；
* 地址处于用户地址范围；
* operation是process-private。

helper与parent共享 ``current->mm``，并使用相同virtual address，所以构造出的key仍为：

::

   K = (shared mm,
        page-aligned virtual base containing U,
        byte offset of U)

``futex_hash(K)`` 因此选择与parent相同的private bucket H。若两个线程不共享mm，即使virtual address数字相同，private key也不会匹配。

无waiter快速路径怎样避免拿spinlock
--------------------------------

``futex_wake()`` 在真正获取H lock之前调用：

::

   futex_hb_waiters_pending(H)

该检查包含full memory barrier，并读取 ``H->waiters``。

当前固定状态：

::

   H->waiters = 1

所以不能走“没有waiter，直接返回0”的快速路径，helper必须取得：

::

   spin_lock(&H->lock)

waiter侧在入队前先增加 ``H->waiters`` 并执行barrier；waker侧先完成U的用户态store，再通过这里的barrier检查waiter count。二者共同保证waker不能同时漏掉condition变化和即将/已经入队的waiter。

注意：H的 ``waiters`` 是bucket级计数。值大于0只说明这个bucket可能存在waiter，不保证每个waiter都匹配K，因此仍要扫描chain并比较完整key。

H chain 怎样精确匹配 parent
---------------------------

持有H lock后， ``futex_wake()`` 遍历priority list：

::

   plist_for_each_entry_safe(q, next, &H->chain, list)

对每个entry执行：

::

   futex_match(&q->key, &K)
   q->bitset & FUTEX_BITSET_MATCH_ANY

固定chain只有parent q：

::

   q.key       == K
   q.bitset    == MATCH_ANY
   q.pi_state  == NULL
   q.rt_waiter == NULL

因此它是普通non-PI futex waiter，进入regular wake handler：

::

   futex_wake_mark(&wake_q, q)

为什么先从bucket移除，再真正wake task
------------------------------------

``futex_wake_mark()`` 先取得parent task reference，然后在仍持有H lock时执行：

::

   __futex_wake_mark(q)
   → __futex_unqueue(q)

``__futex_unqueue()`` 完成：

::

   plist_del(&q->list, &H->chain)
   H->waiters: 1 → 0

到这里q已经不再属于bucket chain。

接着：

.. code-block:: c

   smp_store_release(&q->lock_ptr, NULL);

顺序必须是：

::

   plist_del visible
   → q.lock_ptr = NULL visible

parent恢复后可以无锁读取 ``q.lock_ptr``。一旦看到NULL，就知道waker已经完成q的bucket移除，不需要再次取得H lock或访问已被waker结束的queue关系。

waker不能在设置 ``q->lock_ptr=NULL`` 后继续任意访问q，因为q位于parent kernel stack；parent一旦恢复，可能很快退出syscall并结束q lifetime。

真正的task wake因此通过单独的 ``wake_q`` 延后：

::

   wake_q_add_safe(&wake_q, parent)

H lock释放后，kernel才调用：

::

   wake_up_q(&wake_q)

这样把“修改futex hash data structure”与“scheduler wakeup”分开，避免在H spinlock内执行完整的task wake path。

wake_up_q 怎样让parent重新runnable
---------------------------------

``wake_up_q()`` 对parent进入scheduler wake路径，核心效果等价于：

::

   try_to_wake_up(parent, TASK_NORMAL, wake_flags)

parent当前state包含 ``TASK_INTERRUPTIBLE``，满足wake mask。scheduler在CPU0 runqueue lock保护下完成：

::

   parent state: TASK_INTERRUPTIBLE|TASK_FREEZABLE → TASK_RUNNING
   parent on_rq: 0 → 1
   parent queued on CPU0 runqueue

parent的kernel stack没有被重新创建，也没有重新进入futex syscall。它仍保留在：

::

   futex_do_wait()
   → schedule()

之后CPU0真正选择parent时，将从这个原调用点继续。

wake只使task runnable，不承诺helper在 ``wake_up_q`` 内立即把CPU直接交给parent。固定时序中helper先完成syscall返回，然后在futex之外阻塞，scheduler才选择parent。

helper为什么得到返回值 1
------------------------

每成功匹配并标记一个waiter， ``futex_wake()`` 增加return count：

::

   ret: 0 → 1

固定 ``nr_wake=1``，因此找到parent后立即停止扫描。H lock释放、 ``wake_up_q`` 完成后：

::

   futex_wake returns 1
   → do_futex returns 1
   → __x64_sys_futex returns 1
   → helper CPL 3, RAX=1

这个1表示“kernel成功标记并唤醒了一个匹配waiter”，不是U的新值，也不是被唤醒线程的TID。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* helper wake result/RAX：1；
* helper scheduling class：``SCHED_NORMAL``；
* userspace word ``U``：1；
* U store：release atomic store已完成；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1；
* parent ``on_cpu``：0；
* parent kernel stack：仍暂停在 ``futex_do_wait() → schedule()``；
* private key：K；
* selected bucket：H；
* ``H->waiters``：0；
* H chain：不再包含parent q；
* q list：empty/dequeued；
* q ``lock_ptr``：NULL；
* q task pointer：旧字段仍可能保存parent，但queue ownership已经结束；
* H spinlock：unlocked；
* wake_q：已经drained；
* timeout：none；
* pending signal：none；
* next entry：helper在futex之外阻塞，CPU0 scheduler恢复parent原kernel stack。

关键边界
--------

#. 普通futex wake不修改用户字；U=1来自helper的用户态atomic store。
#. condition store必须在wake syscall之前完成。
#. private WAKE与WAIT必须使用相同mm和virtual address才能得到同一key。
#. ``H->waiters`` 只支持快速判断，真正wake仍要匹配完整key和bitset。
#. q必须先从plist删除，再以release store把 ``lock_ptr`` 设为NULL。
#. 设置 ``q->lock_ptr=NULL`` 后，waker不能继续依赖q lifetime。
#. task先加入 ``wake_q``，bucket lock释放后才执行scheduler wakeup。
#. wakeup只把parent放回runqueue，不恢复其用户态或直接运行其handler。
#. ``FUTEX_WAKE_PRIVATE`` 返回1表示唤醒一个waiter，不表示U值等于1。
#. kernel的wait/wake barriers防止queue竞态，不替代用户态atomic memory-order协议。

下一章
------

helper接下来在futex之外阻塞。CPU0 scheduler将恢复parent原 ``schedule()`` 返回点。下一章解释parent为什么从 ``futex_wait`` 得到0，以及kernel为什么不会在wake成功后再次读取U。

资料
----

* `Linux 7.2-rc1 kernel/futex/syscalls.c：FUTEX_WAKE dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/syscalls.c>`_
* `Linux 7.2-rc1 kernel/futex/waitwake.c：futex_wake、wake mark与wake_q <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/waitwake.c>`_
* `Linux 7.2-rc1 kernel/futex/core.c：private key、hash、queue与unqueue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/core.c>`_
* `Linux 7.2-rc1 kernel/futex/futex.h：waiter count barriers与futex_q结构 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/futex.h>`_
