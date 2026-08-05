第061章：内核并发中的上下文、生命周期与顺序
==========================================

本章必须记住
------------

#. 内核并发正确性必须同时回答三个问题：代码运行在什么上下文、对象由谁保证存活、其它 CPU 按什么顺序看到状态变化。
#. 并发来源不仅是多个线程，还包括多 CPU、内核抢占、硬中断、softirq、timer、workqueue、IRQ thread 和 RCU 回调。
#. 两个 CPU 可以真正同时访问同一对象；只关闭本 CPU 的抢占或中断，不能阻止其它 CPU 修改全局数据。
#. 硬中断可以插入当前 CPU 上的进程或内核路径；若中断和进程路径共享对象，锁协议必须同时处理同 CPU 插入与跨 CPU 并行。
#. ``spin_lock_irqsave()`` 用锁处理跨 CPU 互斥，同时关闭本 CPU IRQ，避免同一 CPU 的中断路径重入同一临界区。
#. ``spin_lock_bh()`` 用锁处理跨 CPU 互斥，同时禁止本 CPU 的 bottom half，适合进程路径与 softirq 共享数据的场景。
#. 关闭本 CPU IRQ、bottom half 或抢占属于局部执行约束，不是完整的多 CPU 数据保护。
#. Workqueue 和 threaded IRQ 通常运行在线程上下文，可以睡眠；硬中断和普通 softirq 路径不能睡眠。
#. 能否睡眠决定可用同步原语：可睡眠上下文可以使用 mutex、rwsem 和等待机制；不可睡眠上下文通常使用 spinlock、atomic、per-CPU 或 RCU 读侧协议。
#. “当前函数在进程上下文”仍不等于一定可以睡眠；持有 spinlock、关闭 IRQ、提高 ``preempt_count`` 后仍属于不可睡眠区间。
#. 同一个对象可能同时被注册表、文件句柄、IRQ、timer、work、RCU 读者和设备回调持有。
#. 从全局表删除对象只会阻止新的查找者看到它，不会自动让旧读者、异步回调和已有引用立即消失。
#. 对象生命周期通常包含分配、初始化、发布、运行、停止新入口、等待旧使用者、注销和最终释放。
#. 引用计数表达长期持有关系；成功 get 后对象必须保持存活，匹配的 put 归还持有权。
#. RCU 适合保护短期查找和延迟回收；对象指针离开 RCU 读侧临界区后继续使用，通常需要提升为普通引用。
#. Timer、workqueue 和 IRQ 回调都可能在调用者返回后继续访问对象，因此 teardown 必须同步取消或等待这些异步路径。
#. 关闭用户入口或删除 sysfs/debugfs 文件不能代替停止 timer、work、IRQ、DMA 和其它对象使用者。
#. 锁解决互斥访问，引用计数解决对象存活，RCU 解决可见性与延迟回收，内存屏障解决跨 CPU 观察顺序。
#. 一把锁不能自动保护没有遵守该锁协议的访问；无锁读取同一字段已经离开锁的证明范围。
#. 原子操作只保证特定变量的不可分割访问，不自动保证相邻普通字段已经按预期对其它 CPU 可见。
#. 发布对象时，必须先完成对象初始化，再通过带发布顺序的指针或状态操作使其它 CPU 看见它。
#. 观察者看到“ready”状态后读取对象内容，需要与发布侧形成 acquire/release、锁、RCU 或其它明确同步关系。
#. ``READ_ONCE()`` 和 ``WRITE_ONCE()`` 约束单次编译器访问形态，不等于完整跨 CPU 同步。
#. 并发 bug 经常只在极少数交错中出现：CPU 速度差、抢占、IRQ 插入、错误回滚和对象销毁会扩大这些窗口。
#. 正常压力测试没有复现不能证明并发设计正确；必须用状态机、锁序、引用关系和内存模型进行证明。
#. Lockdep 检查锁类、上下文和依赖顺序；KCSAN 检查数据竞争；KASAN 检查越界与 use-after-free；refcount 和 RCU 调试检查生命周期协议。
#. 工具报警是某次错误交错的证据，修复时仍要找出违反的上下文、生命周期或顺序规则。
#. PREEMPT_RT 会改变部分锁和 IRQ 的运行语义，分析并发代码时必须记录目标内核配置和执行上下文。
#. 可靠源码阅读顺序是：列出所有访问者，标记上下文，画对象生命周期，再写出锁、引用和发布顺序。

必背路径
--------

分析一个共享对象：

::

   找到对象定义与创建者
   → 列出进程、IRQ、softirq、timer、work 和 RCU 访问者
   → 标记每条路径是否可睡眠、是否可抢占、是否跨 CPU
   → 确定哪些字段由哪种锁或原子协议保护
   → 确定每个指针由引用、RCU 或注册关系保证存活
   → 确定对象发布与状态读取的内存顺序
   → 检查停止入口、同步回调和最终释放顺序

对象安全删除：

::

   把对象标记为 dying
   → 从全局查找结构摘除
   → 阻止新请求、IRQ 或异步工作进入
   → 同步 timer、work、IRQ、DMA 和回调
   → 等待 RCU 旧读者
   → 等待长期引用归还
   → 释放底层资源
   → 最后释放对象内存

发布共享对象：

::

   分配对象
   → 初始化所有读者可见字段
   → 建立引用和状态
   → 使用 release、锁或 RCU 发布指针
   → 读者使用匹配的 acquire、锁或 RCU 读取
   → 只有成功取得生命周期保证后才继续使用

验证罕见交错：

::

   写出两个或多个执行流的时间线
   → 在每个锁、引用、发布和删除点暂停
   → 尝试插入 IRQ、抢占、另一个 CPU 和错误返回
   → 检查是否出现未初始化读取、重复释放或悬空指针
   → 使用 lockdep、KCSAN、KASAN 和 fault injection 验证

必须区分
--------

局部执行控制与跨 CPU 同步
   关抢占、关 IRQ 和关 bottom half只影响本 CPU；跨 CPU 共享数据仍需要锁、原子或其它协议。

互斥与生命周期
   锁防止临界区并发修改；引用、RCU 和同步取消保证对象在访问期间仍然存在。

原子性与内存顺序
   原子性保护一个内存位置的更新；顺序约束多个内存位置在其它 CPU 上的观察关系。

删除与释放
   删除使新查找者看不到对象；释放必须等所有旧使用者和异步路径结束。

可抢占与可睡眠
   可抢占表示调度器可能切换 task；可睡眠表示当前路径允许主动阻塞等待，二者不能混为一谈。

一句话结论
----------

内核并发不是“加一把锁”即可解决的问题；任何共享对象都必须同时闭合上下文、生命周期和内存顺序三条证明链。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 13，Concurrency, Locking, Atomics, Memory Barriers, and RCU；
* AIBook 章节：Chapter 61，Kernel Concurrency Context Lifetime and Ordering；
* 源文件：``docs/LinuxK/Part_13_Concurrency_Locking_Atomics_Memory_Barriers_and_RCU/Chapter_061_Kernel_Concurrency_Context_Lifetime_and_Ordering.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_13_Concurrency_Locking_Atomics_Memory_Barriers_and_RCU/Chapter_061_Kernel_Concurrency_Context_Lifetime_and_Ordering.md>`_。