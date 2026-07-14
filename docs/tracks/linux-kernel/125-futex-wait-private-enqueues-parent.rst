第一百二十五章：FUTEX_WAIT_PRIVATE 怎样建立private key并把parent排入hash bucket？
====================================================================================

上一批已经结束anonymous pipe的完整生命周期。本章选择一个独立的运行期场景，进入Linux线程同步最常见的慢路径：private futex wait。

固定用户程序包含同一进程内的两个线程：

::

   parent thread
   helper thread

二者通过 ``CLONE_VM | CLONE_THREAD`` 共享同一个 ``mm_struct``。固定只有CPU0 online，两个线程均为 ``SCHED_NORMAL``。

共享用户字记为 ``U``：

.. code-block:: c

   _Atomic uint32_t U = 0;

固定条件：

* ``U`` 具有4-byte自然对齐；
* ``U`` 位于可读写的private anonymous mapping；
* 该用户页已经resident，页表与PTE均存在；
* parent与helper看到同一个虚拟地址和同一个 ``mm``；
* 不发生 ``munmap``、``mprotect``、COW、userfaultfd或地址复用；
* ``CONFIG_FUTEX=y``、``CONFIG_FUTEX_PRIVATE_HASH=y``、``CONFIG_BASE_SMALL=n``；
* helper创建时已经为该 ``mm`` 建立默认private futex hash；单CPU场景下固定为16个bucket；
* ``U`` 对应的key上只有parent一个waiter；
* 没有timeout、signal、freezer、spurious wakeup或fault injection；
* 所有用户访问、hash allocation与scheduler操作均成功。

parent执行：

.. code-block:: c

   syscall(SYS_futex,
           &U,
           FUTEX_WAIT_PRIVATE,
           0,
           NULL,
           NULL,
           0);

本章结束在parent已经以 ``TASK_INTERRUPTIBLE | TASK_FREEZABLE`` 状态排入private futex hash bucket，并从CPU0调度出去；helper成为当前执行者。

FUTEX_WAIT_PRIVATE 怎样变成 futex_wait
--------------------------------------

native x86-64 syscall路径进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_futex
   → do_futex

用户传入的operation等价于：

::

   FUTEX_WAIT | FUTEX_PRIVATE_FLAG

``futex_to_flags()`` 首先建立内部flags：

::

   size          = FLAGS_SIZE_32
   FLAGS_SHARED  = clear
   timeout       = NULL
   command       = FUTEX_WAIT

``FUTEX_PRIVATE_FLAG`` 的含义不是“该page一定是anonymous page”，而是这个同步对象只在当前 ``mm`` 内匹配。当前映射确实是private anonymous mapping，但private key路径甚至不需要解析VMA或查找底层folio。

``do_futex()`` 对 ``FUTEX_WAIT`` 设置：

::

   bitset = FUTEX_BITSET_MATCH_ANY

随后调用：

::

   futex_wait(&U, FLAGS_SIZE_32, expected=0,
              abs_time=NULL,
              FUTEX_BITSET_MATCH_ANY)

因为timeout pointer为NULL， ``futex_setup_timer()`` 返回NULL：

* 不建立hrtimer；
* 不计算deadline；
* 不存在timeout callback；
* 后续阻塞只能由wake、signal或spurious scheduler event结束。

固定场景排除signal与spurious wake，因此自然结束条件只有helper的 ``FUTEX_WAKE_PRIVATE``。

private futex key 怎样建立
-------------------------

``__futex_wait()`` 在parent内核栈上建立：

::

   struct futex_q q = futex_q_init

并进入：

::

   futex_wait_setup(&U, expected=0, flags, &q, NULL, current)

``get_futex_key()`` 先检查32-bit futex的自然对齐：

::

   sizeof futex word = 4
   address(U) % 4    = 0

随后保存页内offset，并得到页对齐virtual base：

::

   key.offset          = address(U) % PAGE_SIZE
   key.private.address = address(U) - key.offset
   key.private.mm      = current->mm
   key.node            = FUTEX_NO_NODE

所以本场景的private key可以准确写成：

::

   K = (parent/helper shared mm,
        page-aligned virtual base containing U,
        byte offset of U inside that page)

这里没有：

* ``get_user_pages_fast``；
* folio pin；
* inode sequence number；
* filesystem mapping；
* physical address参与key。

private futex依赖同一 ``mm`` 中稳定的virtual address。相同数值的另一个用户字，只要virtual address不同，就得到不同key；另一个进程即使使用相同virtual address，只要 ``mm`` 不同，也得到不同key。

key 怎样选择 hash bucket H
-------------------------

固定kernel启用了 ``CONFIG_FUTEX_PRIVATE_HASH``。helper线程创建时， ``copy_process()`` 已通过 ``futex_hash_allocate_default()`` 为共享 ``mm`` 分配默认private hash。

该默认大小按下面的规则计算：

::

   threads = min(thread-count, online-CPU-count)
   buckets = clamp(roundup_pow_of_two(4 * threads), 16, global-hash-size)

本场景只有CPU0 online，因此 ``threads=1``，最终：

::

   private hash buckets = 16

``futex_hash(K)`` 对key执行hash并选择其中一个bucket。具体下标依赖virtual address与hash结果，本书不虚构数值，把选中的对象记为：

::

   H = struct futex_hash_bucket for K

H内部包含：

::

   atomic_t waiters
   spinlock_t lock
   plist_head chain

不同futex key可能hash到同一个H。因此bucket chain中的每个 ``futex_q`` 仍必须保存完整key，wake路径不能只凭bucket相同就唤醒。

为什么先增加 waiters 再取得spinlock
----------------------------------

``futex_q_lock(q, H)`` 的第一步不是spin lock，而是：

::

   H->waiters: 0 → 1
   smp_mb__after_atomic()

然后才执行：

::

   q.lock_ptr = &H->lock
   spin_lock(&H->lock)

这个顺序服务于wait/wake的核心不丢唤醒协议。

waker允许先检查 ``H->waiters``，在0时跳过bucket lock。waiter因此必须先公布“有一个潜在waiter”，再锁bucket并读取用户字。与waker侧的full memory barrier配合后，不允许同时发生：

::

   waiter没有看到U已经改变
   AND
   waker没有看到waiter即将入队

本固定时序没有并发交叉：parent完整入队后helper才执行store与wake。这里仍保留这些barrier，因为它们是futex正确性的通用基础，不是单CPU场景特例代码。

为什么必须在bucket lock内再次读取 U
----------------------------------

parent进入syscall前知道 ``U==0``，这个用户态观察不能直接作为阻塞依据。helper可能在syscall入口与真正入队之间修改U。

因此取得H的spinlock后， ``futex_wait_setup()`` 使用pagefault-disabled读取：

::

   futex_get_value_locked(&uval, &U)

固定用户页resident且可读，所以：

::

   uval = 0
   expected = 0
   uval == expected

如果此处读到1，wait路径会撤销 ``H->waiters`` 计数、释放锁并返回 ``-EWOULDBLOCK``，绝不会睡眠。本场景读到0，所以可以建立“检查与入队之间不可被同key wake穿过”的控制边界。

parent 怎样进入 futex queue
---------------------------

值匹配后， ``futex_wait_setup()`` 在仍持有H lock时执行：

::

   set_current_state(TASK_INTERRUPTIBLE | TASK_FREEZABLE)
   futex_queue(&q, H, current)

``set_current_state()`` 必须先于公开q。这样helper即使在q刚进入chain后立即wake，也能看到parent处于可唤醒状态。

``__futex_queue()`` 完成：

::

   initialize q.list priority
   plist_add(&q.list, &H->chain)
   q.task = parent

parent是普通 ``SCHED_NORMAL`` task，因此它在futex priority list中使用non-RT级别；同级waiter按FIFO关系排列。固定key只有这一个waiter。

随后 ``futex_queue()`` 释放H lock。此刻的对象状态是：

::

   H->waiters       = 1
   H->chain         = contains q
   q.key            = K
   q.task           = parent
   q.lock_ptr       = &H->lock
   q.bitset         = FUTEX_BITSET_MATCH_ANY
   parent state     = TASK_INTERRUPTIBLE | TASK_FREEZABLE

private-hash临时引用随hash helper作用域结束而下降；q通过key与 ``lock_ptr`` 描述自己的queue位置，不长期持有一个额外的用户page pin。

设置task state为什么还不等于已经阻塞
-----------------------------------

``futex_wait_setup()`` 返回后，parent继续执行 ``futex_do_wait(&q, NULL)``。

它先检查q是否仍在plist中：

::

   !plist_node_empty(&q.list) == true

如果helper恰好已经移除q，parent会跳过 ``schedule()``。固定时序中helper尚未运行，所以q仍在H chain，parent调用：

::

   schedule()
   → __schedule()

scheduler观察到parent不是 ``TASK_RUNNING``：

* parent从CPU0 runqueue离开；
* parent保存的kernel stack停在 ``futex_do_wait()`` 内部的 ``schedule()``；
* q仍位于parent这次syscall的kernel stack上；
* H chain仍指向q；
* scheduler选择已经runnable的helper。

CPU0切换到helper后，parent才真正处于阻塞状态。设置 ``TASK_INTERRUPTIBLE`` 本身只声明睡眠意图，context switch才结束parent对CPU的占用。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper；
* CPU：CPU0；
* CPU mode：helper即将返回/运行于x86-64 CPL 3；
* parent scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_INTERRUPTIBLE | TASK_FREEZABLE``；
* parent ``on_rq``：0；
* parent ``on_cpu``：0；
* parent kernel stack：暂停在 ``futex_do_wait() → schedule()``；
* userspace word ``U``：0；
* userspace mapping：private anonymous、resident、writable；
* futex operation：32-bit ``FUTEX_WAIT_PRIVATE``；
* timeout object：不存在；
* private key K：shared ``mm`` + page-aligned virtual base + page offset；
* private futex hash：16 buckets；
* selected bucket：H；
* ``H->waiters``：1；
* H chain：包含parent的q；
* q storage：parent当前syscall的kernel stack；
* q bitset：``FUTEX_BITSET_MATCH_ANY``；
* q ``lock_ptr``：指向 ``H->lock``；
* H spinlock：unlocked；
* signal pending：none；
* next entry：helper对U执行release store，然后进入 ``FUTEX_WAKE_PRIVATE``。

关键边界
--------

#. private futex key使用 ``mm`` 与virtual address，不使用physical page identity。
#. private key路径只做alignment与 ``access_ok`` 检查，不需要VMA查找或page pin。
#. bucket可以容纳多个不同key，wake必须再次比较完整key。
#. ``H->waiters`` 在获取bucket lock前增加，以配合waker的无waiter快速路径。
#. 用户态进入syscall前读到0不够；kernel必须在H lock内再次检查U。
#. 值不匹配会返回 ``-EWOULDBLOCK``，不会入队或睡眠。
#. parent先设置interruptible state，再把q发布到bucket chain。
#. q位于parent kernel stack；wait期间该kernel stack必须保持存在。
#. ``TASK_INTERRUPTIBLE`` 不是“已经睡着”，真正阻塞发生在 ``schedule()`` context switch。
#. futex wait不建立普通 ``wait_queue_entry``，而使用hash bucket中的 ``futex_q`` plist。

下一章
------

helper将在用户态先执行：

.. code-block:: c

   atomic_store_explicit(&U, 1, memory_order_release);

随后执行：

.. code-block:: c

   syscall(SYS_futex, &U, FUTEX_WAKE_PRIVATE, 1, NULL, NULL, 0);

下一章追踪H bucket lookup、q移除、 ``wake_q`` 与parent重新进入CPU0 runqueue。

资料
----

* `Linux 7.2-rc1 kernel/futex/syscalls.c：futex syscall与WAIT/WAKE dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/syscalls.c>`_
* `Linux 7.2-rc1 kernel/futex/waitwake.c：wait setup、queue与sleep <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/waitwake.c>`_
* `Linux 7.2-rc1 kernel/futex/core.c：private key、hash与futex_q操作 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/core.c>`_
* `Linux 7.2-rc1 kernel/futex/futex.h：bucket、futex_q与waiter barriers <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/futex/futex.h>`_
* `Linux 7.2-rc1 kernel/fork.c：创建thread时分配default private futex hash <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 init/Kconfig：FUTEX_PRIVATE_HASH默认配置 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/Kconfig>`_
