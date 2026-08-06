第179章：I/O 延迟、排队、Writeback 与存储瓶颈
=============================================

核心知识点
----------

I/O 延迟必须分段测量
   应用等待包含用户态队列、文件系统锁、Page Cache、Dirty Throttling、块层排队、设备服务、完成回调和调度唤醒。设备统计只覆盖其中一部分。

Buffered Write 会推迟成本
   ``write()`` 返回通常只表示数据进入 Page Cache。真正的设备写入可由后台回写、脏页阈值、过期时间或 ``fsync()`` 触发，因此前台快速返回不等于持久化完成。

Dirty 与 Writeback 表达不同状态
   Dirty Page 尚待写出，Writeback Page 正在提交。脏页持续增长说明产生速度超过回写能力，周期性堆积并伴随长尾常指向回写突发或前台节流。

Dirty 参数只改变成本暴露位置
   增大阈值可延后前台停顿，却会增加后续 Burst、内存占用和 ``fsync`` 长尾；降低阈值会更早回写，也可能增加设备争用。它们不能提高设备真实服务率。

块层存在多级队列
   ``bio`` 描述块范围，``request`` 是调度与驱动执行单位；blk-mq 还包含软件上下文、Hardware Context、Tag、驱动 Ring 和设备内部 Queue。

Queue Depth 不等于有效并行度
   增加在途请求可能提高吞吐，也会增加排队、内存、Timeout 和 Recovery 成本。最佳深度取决于设备、驱动、Firmware、访问模式和延迟目标。

Issue 与 Complete 划分设备阶段
   Request 形成后仍可能等待 Merge、Scheduler、Tag 或 Budget。Issue/Dispatch 更接近设备接管边界，Complete 表示块层收到完成，不表示应用线程已经恢复运行。

平均设备指标会掩盖长尾
   ``await``、平均 Queue 和 ``%util`` 无法解释少量 Flush、GC、Reset、Timeout、Error Recovery 或单 Hardware Queue 热点。需要阶段 Histogram 和错误时间线。

设备栈必须逐层识别
   Filesystem、DM、LVM、RAID、Crypt、Thin、Multipath、Network Block 与虚拟化都会重映射请求和统计边界。顶层设备名不一定是实际瓶颈位置。

Cgroup 和用户态也能形成队列
   ``io.max``、``io.weight``、用户线程池、io_uring SQ/CQ 和应用内部队列都可能在设备有余量时限制工作负载，不能把全部等待归因于磁盘。

关键路径
--------

Buffered Write：

::

   Application write
   → VFS / Filesystem
   → 数据进入 Page Cache
   → 页面标记 Dirty
   → write 可能返回
   → 阈值、过期或 fsync 触发 Writeback
   → Filesystem 生成 Bio
   → Block Layer 形成 Request
   → blk-mq Dispatch
   → Device Completion
   → 页面恢复 Clean / fsync 返回

块层阶段：

::

   Bio Submit
   → Request Allocation / Merge
   → Software Queue
   → Scheduler / Tag / Budget
   → Hardware Context Dispatch
   → Driver Ring / Device Queue
   → Device Service
   → Interrupt 或 Poll Completion
   → 上层回调与 Task Wakeup

长尾定位：

::

   固定慢 Syscall 或请求
   → 对齐应用延迟分布
   → 观察 Dirty、Writeback 与 I/O PSI
   → 记录 Submit / Issue / Complete
   → 计算 Queue Time 与 Service Time
   → 检查 Per-queue、Cgroup 和设备栈
   → 检查 Flush、Reset、Timeout 与 Firmware
   → 找到最早出现长尾的阶段

概念辨析
--------

* 应用等待与设备服务：前者覆盖完整请求，后者只覆盖块层和硬件的一段。
* ``write()`` 返回与持久化完成：进入 Page Cache 不等于介质完成。
* Dirty 与 Writeback：待写页面和正在写出的页面不同。
* ``bio`` 与 ``request``：数据范围描述和块层调度执行单位不同。
* Software Queue 与 Device Queue：内核排队和 Firmware/Hardware 排队不同。
* Queue Depth 与设备并行度：在途数量不等于硬件有效处理能力。
* ``await`` 与端到端延迟：块设备平均值不覆盖文件系统、节流和调度唤醒。
* Timeout 与修复：延长等待不会让丢失的 Completion 自动出现。

本章结论
--------

存储性能调查必须量化请求何时进入缓存、何时被回写、何时在块层排队、何时由设备服务，以及完成后何时真正唤醒应用。