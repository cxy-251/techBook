项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109
   LK-UNLINK-110..LK-UNLINK-112
   LK-SLEEP-113..LK-SLEEP-115
   LK-SIGNAL-116..LK-SIGNAL-118
   LK-PIPE-119..LK-PIPE-121
   LK-PIPECLOSE-122..LK-PIPECLOSE-124
   LK-FUTEX-125..LK-FUTEX-127

最新三章：

#. ``LK-FUTEX-125``：FUTEX_WAIT_PRIVATE 怎样建立private key并把parent排入hash bucket？
#. ``LK-FUTEX-126``：FUTEX_WAKE_PRIVATE 怎样移除waiter并把parent放回runqueue？
#. ``LK-FUTEX-127``：parent 被唤醒后，futex_wait 为什么返回0却不自动重读用户字？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault；
#. child static ELF ``execve()``；
#. child ``_exit(42)`` 与 parent ``wait4()`` 回收；
#. ext4 ``openat(O_CREAT|O_EXCL)``；
#. 新文件首次delalloc buffered write与显式 ``fsync``；
#. open-unlinked ext4文件的final close与inode/extent回收；
#. monotonic ``clock_nanosleep`` 自然到期、hrtimer/APIC/scheduler唤醒；
#. ``SIGUSR1`` 中断relative nanosleep、remaining copyout、rt signal frame与 ``rt_sigreturn``；
#. anonymous pipe创建、空pipe阻塞read、writer插入buffer与reader wakeup；
#. pipe write-end close、EOF read与final pipe object teardown；
#. private futex wait、release store、wake、scheduler恢复与return semantics。

本批固定场景
------------

::

   runtime relation    = independent scenario
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   mm relation         = shared through CLONE_VM
   scheduling          = both SCHED_NORMAL
   user word           = 4-byte aligned _Atomic uint32_t U
   mapping             = resident writable private anonymous page
   initial U           = 0
   wait call           = futex(&U, FUTEX_WAIT_PRIVATE, 0, NULL, NULL, 0)
   wake store          = atomic_store_explicit(&U, 1, memory_order_release)
   wake call           = futex(&U, FUTEX_WAKE_PRIVATE, 1, NULL, NULL, 0)
   kernel config       = FUTEX=y, FUTEX_PRIVATE_HASH=y, BASE_SMALL=n
   private hash        = default 16 buckets for one online CPU
   key waiters         = exactly one parent waiter
   timeout             = none
   signal/freezer      = none
   scheduler order     = parent blocks; helper stores+wakes; helper blocks; parent resumes
   failure policy      = no alignment, address, page, hash, copy or scheduler failure

完整控制流
----------

::

   parent futex(FUTEX_WAIT_PRIVATE, expected=0)
   → __x64_sys_futex
   → do_futex
   → futex_wait
   → no timeout / no hrtimer
   → __futex_wait
   → futex_wait_setup
   → get_futex_key private path
   → key K = shared mm + page-aligned virtual base + byte offset
   → no VMA lookup, page pin, inode or physical-page key
   → futex_hash selects private bucket H
   → H->waiters 0 -> 1 before taking H->lock
   → read U under H lock with pagefault disabled
   → U == expected == 0
   → parent state = TASK_INTERRUPTIBLE | TASK_FREEZABLE
   → add stack futex_q to H plist
   → release H lock
   → futex_do_wait
   → schedule / __schedule
   → parent leaves CPU0 and helper runs

   helper atomic_store_release(U, 1)
   → U becomes 1 before wake syscall
   → helper futex(FUTEX_WAKE_PRIVATE, 1)
   → do_futex / futex_wake
   → reconstruct same private key K
   → select same bucket H
   → futex_hb_waiters_pending sees 1
   → lock H
   → match q key and MATCH_ANY bitset
   → futex_wake_mark
   → plist_del(q)
   → H->waiters 1 -> 0
   → smp_store_release(q.lock_ptr, NULL)
   → add parent to wake_q
   → unlock H
   → wake_up_q / try_to_wake_up
   → parent TASK_RUNNING and queued on CPU0
   → helper returns CPL3 with RAX=1
   → helper blocks outside futex

   scheduler restores parent original futex_do_wait stack
   → schedule returns
   → __set_current_state(TASK_RUNNING)
   → futex_unqueue sees q.lock_ptr == NULL
   → futex_unqueue returns 0: waker already removed q
   → __futex_wait returns 0
   → futex_wait returns 0 without rereading U
   → parent returns CPL3 with RAX=0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：private futex wait/wake complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* parent wait result/RAX：0；
* helper wake result：1；
* helper：阻塞在futex之外；
* userspace word ``U``：1；
* U mapping：仍resident、writable、private anonymous；
* post-wake kernel re-read of U：未发生；
* post-return user acquire load：尚未执行；
* private key K：同一mm和address可再次构造；
* per-mm private futex hash：仍存在，16 buckets；
* selected bucket H ``waiters``：0；
* H chain：没有本次q；
* H spinlock：unlocked；
* parent栈上 ``futex_q``：生命周期结束；
* timeout/hrtimer：none；
* restart block：未使用；
* signal pending：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. ``FUTEX_PRIVATE_FLAG`` 让key使用mm与virtual address，不使用physical page identity。
#. private key路径不查VMA、不pin page，也不引用inode。
#. bucket可能容纳不同key，wake必须比较完整key与bitset。
#. waiter先增加bucket waiter count，再获取spinlock并读取U。
#. kernel必须在bucket lock内验证U仍等于expected，避免检查/入队窗口丢wake。
#. 值不匹配会返回 ``-EWOULDBLOCK``，不会睡眠。
#. parent先设置interruptible state，再把栈上q发布到bucket chain。
#. task state设置不等于已经阻塞；context switch才让parent离开CPU。
#. 普通futex wake不修改U，U=1来自helper用户态release store。
#. waker先从plist移除q，再以release store把 ``q.lock_ptr`` 设为NULL。
#. task通过wake_q在bucket lock释放后唤醒。
#. wake只让parent runnable，不保证立即handoff。
#. helper WAKE返回1表示唤醒一个waiter；parent WAIT返回0表示本q由waker移除。
#. wait返回0后kernel不会重新读取U，也不保证业务condition仍成立。
#. 用户程序必须在condition loop中重新检查U并处理spurious/competitive wake。
#. kernel queue barriers不替代C/C++ release/acquire协议；parent应通过acquire load读取1。
#. ``futex_q`` 是一次wait调用的栈上对象，syscall返回后结束生命周期。
#. private hash bucket属于mm，单次wait结束不会销毁它。

下一任务
--------

当前没有已选定场景。优先候选是 ``eventfd`` counter阻塞read与writer wakeup：

::

   eventfd2(0, EFD_CLOEXEC)
   → create anon_inode file and eventfd_ctx
   → parent read(eventfd, &value, 8) with counter=0
   → parent enters eventfd wait queue and schedules out
   → helper write(eventfd, value=3)
   → counter 0 -> 3 and wake reader
   → parent consumes counter and returns 8 with value=3

开始前必须固定fd编号、counter/semaphore mode、blocking flags、wait queue、scheduler顺序、signal状态与file references。
