第045章：进程、中断与内核线程执行上下文
=======================================

本章必须记住
------------

#. 执行上下文决定一段内核代码能否睡眠、能否访问用户指针、能用哪类锁、能采用哪种内存分配标志。
#. 判断内核 API 是否可用时，必须先问代码运行在哪种上下文，再看局部锁、中断和抢占状态。
#. 进程上下文表示内核代码正在代表某个 task 执行，并具有普通调度语义。
#. 系统调用、page fault、普通文件回调、线程型 workqueue 和内核线程通常运行在进程上下文。
#. ``current`` 始终指向当前 CPU 上的 task，但该 task 可能是用户进程、kworker 或内核线程。
#. 只有当前路径确实代表用户进程时，``current->mm``、用户指针和调用者凭证才具有普通用户请求语义。
#. 进程上下文通常允许睡眠，但持有 spinlock、关闭中断、关闭 bottom half 或处于其它 atomic 状态时仍不能睡眠。
#. ``copy_from_user()``、``copy_to_user()``、``mutex_lock()`` 和 ``GFP_KERNEL`` 都可能睡眠，必须用于允许睡眠的路径。
#. 硬中断上下文由硬件事件触发，不代表被打断的用户 task 处理请求。
#. 硬中断中 ``current`` 只是碰巧被打断的 task，不能据此访问它的用户地址空间或把事件归因给它。
#. 硬中断处理函数不能调用 ``schedule()``、阻塞 mutex、普通用户访问或可能睡眠的分配路径。
#. 硬中断应尽快确认并应答硬件、保存最小状态、唤醒等待者或安排延迟处理。
#. 硬中断需要临时分配时通常使用不睡眠的策略，例如 ``GFP_ATOMIC``，并必须处理失败。
#. 更稳健的驱动会在进程上下文预分配 ring、descriptor 和事件对象，减少 IRQ 中动态分配。
#. softirq 是异步 atomic 上下文，常用于网络、定时器、RCU 等高频延迟处理。
#. softirq 可能在硬中断返回、系统调用返回或 ``ksoftirqd`` 相关路径中执行；只要处于 softirq context，就不能睡眠。
#. ``ksoftirqd`` 是内核线程，但它执行 softirq 工作时仍遵守 softirq 的非睡眠语义。
#. tasklet 建立在 softirq 机制之上，也属于不能睡眠的延迟执行上下文。
#. 线程型 workqueue 的 work function 由 kworker task 执行，属于进程上下文，通常允许睡眠。
#. workqueue 回调没有原用户调用者的用户地址空间语义；把用户指针保存到 work item 后异步访问通常是错误设计。
#. 用户数据需要异步处理时，应在原系统调用上下文先复制成内核对象，再把内核对象交给 workqueue。
#. 排队动作与执行动作可能位于不同上下文：IRQ 中 ``queue_work()``，实际 work function 在 kworker 中运行。
#. 内核线程是由内核创建并在调度器中独立运行的 task，通常没有普通用户地址空间。
#. 内核线程的 ``current->mm`` 通常为空；``active_mm`` 用于 CPU 地址空间运行需要，不等于内核线程拥有可访问的用户进程内存。
#. 借用 ``active_mm`` 是地址空间切换优化，不会赋予内核线程普通用户指针语义。
#. 内核线程可以睡眠、使用 mutex 和 ``GFP_KERNEL``，但仍需遵守持锁、抢占和停止协议。
#. ``kthread_should_stop()`` 与 ``kthread_stop()`` 构成常见停止协议；线程函数要周期性检查停止条件并可被唤醒。
#. workqueue 适合离散任务和统一 worker 管理；专用 kthread 适合长期循环、专用状态机或明确调度控制。
#. NAPI 把网卡硬中断转换成受预算约束的轮询处理，执行语义通常落在 softirq 路径。
#. ``in_hardirq()``、``in_softirq()``、``in_interrupt()`` 等谓词提供运行时线索，但最终仍要由注册入口和调用链确认上下文。
#. ``might_sleep()``、lockdep 和 atomic-sleep warning 可帮助发现禁止睡眠上下文中调用睡眠 API 的错误。
#. 同一函数可能从不同入口被调用；只有所有调用上下文都允许时，函数内部才能无条件睡眠。
#. 需要跨上下文共享数据时，必须同时设计同步、生命周期、内存分配和取消/拆除路径。

必背路径
--------

设备事件的典型上下文迁移：

::

   硬件产生 IRQ
   → 硬中断 handler 读取并确认最小状态
   → 使用 spinlock 或原子操作保存事件
   → 安排 softirq、NAPI 或 queue_work
   → 硬中断快速返回
   → softirq 处理低延迟批量工作
   或 kworker 处理可睡眠、较复杂工作
   → 更新对象状态并唤醒等待用户 task

用户请求转异步工作：

::

   用户 task 进入 read、write 或 ioctl
   → 在进程上下文 copy_from_user
   → 验证并建立内核请求对象
   → 增加目标设备与请求引用
   → queue_work
   → 系统调用返回或等待完成
   → kworker 使用内核对象执行工作
   → 完成后唤醒等待者或记录结果
   → 归还引用并释放请求

判断能否睡眠：

::

   确认入口是系统调用、IRQ、softirq、workqueue 还是 kthread
   → 检查 in_interrupt 与抢占状态
   → 检查是否持有 spinlock 或关闭 IRQ/BH
   → 检查 API 是否可能 fault、回收内存或阻塞
   → 仅在全部条件允许时使用睡眠 API
   → 否则改用非阻塞操作或迁移到线程上下文

停止专用内核线程：

::

   设置对象进入 stopping 状态
   → 阻止新任务进入
   → 调用 kthread_stop 或设置停止条件
   → 唤醒可能正在睡眠的线程
   → 线程检测 kthread_should_stop
   → 退出循环并释放线程私有资源
   → 等待线程函数返回
   → 最后释放共享对象

必须区分
--------

* 进程上下文与用户进程上下文：kworker 和内核线程也属于进程上下文并可睡眠，但不代表普通用户地址空间。
* 硬中断与 softirq：两者都不能睡眠；硬中断直接响应硬件，softirq 负责延后的高频 atomic 工作。
* softirq 在线程名下运行与可睡眠：即使由 ``ksoftirqd`` task 执行，softirq 回调本身仍按 softirq 规则运行。
* workqueue 与 softirq：线程型 workqueue 通常可睡眠；softirq 不能使用阻塞 API。
* ``current`` 存在与用户指针有效：每种上下文都有 current；只有代表相应用户 task 的路径才具有用户地址空间语义。
* ``mm`` 与 ``active_mm``：``mm`` 表示 task 拥有的用户地址空间；``active_mm`` 可能只是内核线程运行时借用的地址空间。
* 排队上下文与执行上下文：在 IRQ 中排入 workqueue，不表示 work function 也运行在 IRQ 中。

一句话结论
----------

内核代码是否合法首先由执行上下文决定：硬中断和 softirq 必须非阻塞，线程型 workqueue 与内核线程通常可睡眠，而用户指针只能在代表相应用户 task 的受控路径中访问。
