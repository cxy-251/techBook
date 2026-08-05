第085章：OOM Killer、内存死亡与生存诊断
=======================================

本章必须记住
------------

#. OOM 是当前内存分配约束域内，回收、写回、换出、压缩和重试仍无法恢复推进能力后的最后裁决。
#. OOM 不要求整机所有空闲内存归零；当前 memcg、cpuset、NUMA policy、node、zone 或 GFP 约束内耗尽即可触发局部裁决。
#. 一次分配失败不一定进入 OOM；高阶、NOWAIT、ATOMIC、NORETRY 或调用者允许失败的请求经常直接返回失败或降级。
#. OOM 日志中的 ``gfp_mask`` 和 ``order`` 描述触发分配请求，不描述被杀进程的内存布局。
#. 诊断第一步是确定 OOM 域：global、memcg、cpuset、mempolicy 或特定节点约束。
#. ``constraint=``、``nodemask=``、``cpuset=``、``mems_allowed=`` 和 ``oom_memcg=`` 是识别 OOM 域的重要日志字段。
#. Global OOM 在当前全局分配约束内选择候选；memcg OOM 只在触发限制的 cgroup 范围内处理。
#. 整机仍有大量可用内存时，达到 ``memory.max`` 的 cgroup 仍可发生 memcg OOM。
#. ``memory.high`` 主要触发回收和任务限速，不是硬 OOM 上限；``memory.max`` 是无法持续超出的硬限制。
#. Cgroup v2 的 ``memory.events`` 可记录 high、max、oom、oom_kill、oom_group_kill 等事件。
#. ``memory.events.local`` 只报告当前 cgroup 本身的事件，不汇总子树，适合区分压力来源层级。
#. ``memory.current`` 表示当前 cgroup 内存用量，必须结合 ``memory.stat`` 判断匿名页、文件页、slab、页表和 swap 构成。
#. ``memory.swap.max`` 会限制 cgroup 可使用的 swap，匿名页较高而 swap 受限时更容易进入 memcg OOM。
#. ``memory.oom.group=1`` 请求把 cgroup 作为一个工作负载整体处理，避免只杀部分进程留下损坏服务。
#. ``oom_score_adj=-1000`` 的任务受到 OOM 保护，组杀规则也必须尊重相应保护语义。
#. OOM killer 选择 victim 前，先过滤不符合当前 OOM 域、不可杀或没有可释放用户地址空间的任务。
#. 内核线程、全局 init 和部分特殊状态任务通常不会成为普通 OOM victim。
#. ``oom_badness`` 主要根据候选任务可释放的地址空间内存、swap、页表等估计分数，并叠加 ``oom_score_adj``。
#. ``/proc/<pid>/oom_score_adj`` 范围通常为 -1000 到 +1000，越大越容易被选中，-1000 表示禁止普通 OOM 选择。
#. ``/proc/<pid>/oom_score`` 是当前条件下的动态倾向值，不能单独解释为固定百分比概率。
#. 高内存任务更可能被杀，是因为杀掉它可能释放更多资源，不表示它一定是最初的内存增长根因。
#. Victim 与 trigger task 可以不是同一进程；触发分配者只是把系统推进到裁决点。
#. ``oom_kill_allocating_task`` 可以改变是否优先杀触发者，必须读取目标系统实际 sysctl。
#. ``panic_on_oom`` 可以把部分 OOM 转换为 kernel panic，适合特定高可用或转储策略，错误设置会扩大故障范围。
#. ``oom_dump_tasks`` 控制是否打印任务内存表，关闭它会减少诊断证据但不改变压力本身。
#. 内核选中 victim 后通常发送 ``SIGKILL`` 并设置 OOM victim 状态，使其退出路径获得必要前进机会。
#. 被杀进程不会在信号发送瞬间释放全部内存；它仍需退出线程、拆除 ``mm_struct``、页表和映射。
#. OOM reaper 会尝试提前解除 victim 的部分匿名用户映射，减少其它分配者等待内存归还的时间。
#. OOM reaper 不能回收所有对象；长期 pin、DMA、内核对象、共享资源和不可解除映射仍依赖真正退出路径。
#. Victim 可能卡在不可中断 I/O、内核锁或驱动路径中，使 OOM 后内存恢复迟缓。
#. 多个任务共享同一 ``mm_struct`` 时，victim 选择、线程组退出和地址空间释放具有共享生命周期语义。
#. ``Killed process`` 日志中的 total-vm 是虚拟地址空间规模，不等于实际驻留物理内存。
#. ``anon-rss``、``file-rss``、``shmem-rss``、页表和 swap 条目比 total-vm 更接近可释放内存构成。
#. RSS 仍不等于进程独占内存；共享文件页和共享匿名页可能同时计入多个进程视图。
#. PSS、smaps、memcg 统计和对象归属可以补充共享内存解释，但 OOM 现场日志不一定包含它们。
#. OOM task dump 是裁决时的瞬时快照，真正根因可能在数秒或数分钟前的持续增长、突发分配或回收失效。
#. 应保留 OOM 前后的监控时间线，而不是只分析最后一条 ``Killed process``。
#. Global OOM 需要结合 ``MemFree``、``MemAvailable``、AnonPages、Dirty、Writeback、Slab、Unevictable 和 Swap。
#. Memcg OOM 需要优先读取目标 cgroup 的 current、max、high、swap、events 和 stat，整机指标只是背景。
#. ``order=0`` OOM 表示普通基础页都无法在当前约束内恢复，通常比单次高阶形状失败更严重。
#. 高阶请求触发的日志仍需先判断调用者是否允许 fallback，不能把连续形状失败直接归为 OOM 容量问题。
#. Dirty 与 Writeback 很高时，存储回写滞后可能阻止文件页及时变成可回收 clean cache。
#. 匿名页高且 swap 不可用时，reclaim 候选会显著减少，OOM 风险上升。
#. Unevictable、长期 pin、不可回收 slab 和内核泄漏会减少用户进程退出之外的恢复空间。
#. Slab 高时必须区分 ``SReclaimable`` 与 ``SUnreclaim``，并继续定位具体 cache 和对象生命周期。
#. 页表内存、内核栈和 socket buffer 等内核内存也可能形成压力，不能只按进程 RSS 排查。
#. Tmpfs、shmem 和 shared memory 可能表现为匿名或共享内存压力，并受 memcg 和 swap 规则影响。
#. Page Cache 高且 clean 时通常有回收空间；Page Cache 高但 dirty/writeback 堵塞时恢复成本由 I/O 决定。
#. ``pgscan`` 高而 ``pgsteal`` 低说明回收扫描效率差，可能来自工作集活跃、dirty、pin 或不可回收比例高。
#. ``allocstall`` 与 PSI memory 上升表示业务任务已经因 direct reclaim 和内存压力停顿。
#. OOM 日志应与 ``/proc/vmstat``、PSI、块 I/O、swap、memcg events 和应用分配曲线按时间对齐。
#. Killed victim 恢复了系统推进能力，不代表压力根因已经修复；工作负载可能重新增长并形成 OOM 循环。
#. 自动重启 victim 在未修改限制或内存行为时，可能形成重复 OOM、服务抖动和日志风暴。
#. 调高 ``memory.max`` 只是扩大预算，不能修复无界缓存、泄漏、错误并发或工作集估计。
#. 降低 ``oom_score_adj`` 只改变谁被牺牲，不会增加内存或改善回收。
#. 把所有关键进程设为 -1000 可能让内核找不到合适 victim，增加长时间停顿或 panic 风险。
#. 启用 swap 可以增加匿名页回收选择，但会引入 I/O 延迟，不能替代容量规划和内存上限。
#. ``vm.overcommit_memory``、commit limit 与运行时 OOM 有关，但虚拟内存承诺和实际物理压力不是同一指标。
#. Strict overcommit 可以更早拒绝部分虚拟内存申请，仍不能覆盖所有内核分配、共享页和实际工作集行为。
#. OOM 期间不要首先清理日志或重启整机；应先保存完整 kernel log、cgroup 状态、任务表和时间线证据。
#. 正确修复方向可能是限制无界增长、修复泄漏、增加容量、调整 cgroup 预算、降低并发、改善回写或解除长期 pin。
#. 最稳定诊断顺序是：确定 OOM 域 → 还原触发分配 → 判断回收为何无进展 → 阅读候选与 victim → 追查 OOM 前内存增长。

必背路径
--------

OOM 触发：

::

   分配请求携带 GFP、order 和约束域
   → 快速路径找不到空闲页
   → direct reclaim / kswapd / writeback / swap
   → 高阶请求必要时 compaction
   → 多轮重试仍无有效进展
   → 建立 oom_control
   → 识别 global / memcg / cpuset / policy 域
   → 进入 OOM 裁决

Victim 选择：

::

   枚举当前 OOM 域内任务
   → 排除不可杀和受保护任务
   → 计算可释放内存基准
   → 应用 oom_score_adj
   → 选择分数最高的有效候选
   → 标记 OOM victim
   → 发送 SIGKILL
   → 启动退出与 OOM reaper

Memcg OOM 诊断：

::

   从日志取得 oom_memcg 路径
   → 读取 memory.current / max / high
   → 读取 memory.swap.current / max
   → 读取 memory.events 和 memory.stat
   → 判断 anon / file / slab / shmem / pgtables 构成
   → 检查 memory.oom.group 和 oom_score_adj
   → 对齐容器或服务时间线
   → 修正限制或内存增长根因

Global OOM 诊断：

::

   保存完整 OOM header 和 task dump
   → 解码 gfp_mask、order、nodemask 和 cpuset
   → 检查 zone 水位与 buddy 状态
   → 检查 anon、file、dirty、slab、unevictable、swap
   → 检查 pgscan / pgsteal / allocstall / PSI
   → 判断回收、写回、swap 或 pin 为何无进展
   → 追踪压力增长对象和生命周期

OOM 后恢复：

::

   Victim 收到 SIGKILL
   → 阻止其继续正常业务分配
   → OOM reaper 尝试解除部分匿名映射
   → 线程退出并关闭资源
   → mm_struct、页表和映射释放
   → 页返回 allocator
   → 等待水位恢复
   → 检查是否发生重复 OOM

必须区分
--------

分配失败与 OOM
   很多请求可以直接失败或回退；只有当前策略进入最终内存死亡裁决时才是 OOM。

Global OOM 与 Memcg OOM
   前者在系统分配域内裁决；后者由 cgroup 硬限制触发并只在该域内选择 victim。

Trigger task 与 Victim
   Trigger 发起无法满足的分配；victim 是内核认为杀掉后更适合恢复资源的候选。

虚拟内存与驻留内存
   total-vm 是地址空间规模；RSS、swap、页表和内核对象更接近实际压力构成。

发送 ``SIGKILL`` 与内存已经释放
   信号只启动死亡过程；真正释放需要 OOM reaper 和完整退出、引用清理。

改变 victim 优先级与修复压力
   ``oom_score_adj`` 只影响牺牲对象，不改变容量、回收效率或工作负载增长。

一句话结论
----------

OOM killer 是当前约束域无法通过回收继续推进时的生存裁决；诊断必须先确定 OOM 域和触发分配，再解释回收失败、victim 选择及内存为何持续增长。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 17，Page Cache, Writeback, Reclaim, Compaction, and OOM；
* AIBook 章节：Chapter 85，OOM Killer, Memory Death, and Survival Diagnostics；
* 源文件：``docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_085_OOM_Killer_Memory_Death_and_Survival_Diagnostics.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_085_OOM_Killer_Memory_Death_and_Survival_Diagnostics.md>`_。