第085章：OOM Killer、内存死亡与生存诊断
=======================================

核心知识点
----------

OOM 是分配路径的最后裁决
   当前请求经过回收、写回、换出、压缩和重试后仍无法恢复推进能力，内核才进入 OOM 决策。它不是所有分配失败的统一结果。

OOM 发生在具体约束域
   整机仍有空闲页时，memcg、cpuset、NUMA policy、node、zone 或 GFP 限制内仍可能耗尽。诊断第一步必须确定裁决范围。

触发请求由 ``gfp_mask`` 和 ``order`` 描述
   这些字段说明内核当时要申请什么页面、允许执行哪些恢复动作，不描述最终 victim 的内存布局。

许多失败不会进入 OOM
   NOWAIT、ATOMIC、NORETRY、高阶形状请求或调用者允许降级的分配，可以直接返回失败。高阶失败也可能只是连续形状不足。

``oom_control`` 汇总裁决上下文
   分配慢路径把 nodemask、memcg、order、GFP 和约束类型组织成 OOM 输入，再进入 global、memcg、cpuset 或 policy 范围的处理。

Global OOM 与 memcg OOM 候选范围不同
   Global OOM 在当前系统分配域内选择任务；memcg OOM 只处理触发硬限制的 cgroup，即使整机容量仍然充足。

``memory.high`` 与 ``memory.max`` 语义不同
   ``memory.high`` 主要引发回收和限速；``memory.max`` 是硬限制。``memory.events`` 用于记录 high、max、oom 和 oom_kill 等事件。

Victim 选择偏向可释放价值
   ``oom_badness`` 主要依据候选任务的匿名驻留、swap、页表等可释放内存，并叠加 ``oom_score_adj``。分数高表示更适合牺牲，不表示它必然是压力根因。

``oom_score_adj`` 只改变牺牲顺序
   值越高越容易被选择，``-1000`` 提供普通 OOM 保护。它不会增加容量、改善回收，也不能修复泄漏。

Trigger task 与 victim 可以不同
   Trigger task 发起了无法满足的分配；victim 是内核认为杀掉后更可能恢复资源的候选。两者不能按因果关系直接等同。

发送 ``SIGKILL`` 不等于内存已释放
   Victim 仍需退出线程、拆除 ``mm_struct``、页表和映射。卡在不可中断 I/O、锁或驱动路径时，恢复会延迟。

OOM reaper 加速地址空间回收
   Reaper 尝试提前解除 victim 的部分匿名映射，使其它分配者尽快获得页面。长期 pin、DMA、内核对象和共享资源仍依赖完整退出路径。

日志字段必须按内存类型解释
   ``total-vm`` 是虚拟地址空间规模；``anon-rss``、``file-rss``、``shmem-rss``、页表和 swap 更接近实际压力。RSS 仍可能包含共享页。

OOM 是压力时间线的终点
   Task dump 只是裁决瞬间快照。真正根因可能来自持续匿名增长、脏页堵塞、不可回收 slab、长期 pin、cgroup 限制或回收效率下降。

回收无进展是核心证据
   ``pgscan`` 高而 ``pgsteal`` 低、``allocstall`` 和 PSI memory 上升、Dirty/Writeback 堵塞或 swap 不可用，都能解释为什么系统走到最终裁决。

杀掉进程只恢复推进能力
   Victim 退出后服务若按同样模式重新增长，系统会进入重复 OOM。正确修复应针对预算、泄漏、并发、回写、pin 或工作集本身。

关键路径
--------

OOM 触发：

::

   分配请求携带 GFP、order 和约束域
   → 快速路径找不到页
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
   → 估算可释放地址空间内存
   → 应用 oom_score_adj
   → 选择最高分有效候选
   → 标记 OOM victim
   → 发送 SIGKILL
   → 启动退出与 OOM reaper

Memcg OOM：

::

   识别 oom_memcg 路径
   → 检查 memory.current / max / high
   → 检查 memory.swap.current / max
   → 检查 memory.events 与 memory.stat
   → 分解 anon / file / shmem / slab / pgtables
   → 检查 memory.oom.group 与任务保护
   → 修正限制或增长根因

OOM 后恢复：

::

   Victim 收到 SIGKILL
   → 停止正常业务推进
   → OOM reaper 尝试解除部分映射
   → 线程退出并关闭资源
   → mm_struct、页表和映射释放
   → 页面返回 allocator
   → 水位恢复
   → 检查是否发生重复 OOM

概念辨析
--------

* 分配失败与 OOM：许多请求允许直接失败或回退；只有进入最终内存死亡策略时才是 OOM。
* Global OOM 与 memcg OOM：前者在系统分配域裁决；后者由 cgroup 硬限制触发并只在该域选择 victim。
* Trigger task 与 victim：前者发起失败请求；后者是被选择用于释放资源的任务。
* 虚拟内存与驻留内存：``total-vm`` 是地址空间规模；RSS、swap、页表和内核对象更接近实际压力。
* 发送 ``SIGKILL`` 与完成释放：信号只启动死亡过程，真正回收需要 reaper、退出和引用清理。
* Victim 优先级与压力修复：``oom_score_adj`` 只改变谁被杀，不改变容量和回收效率。

本章结论
--------

OOM killer 是当前约束域无法通过回收继续推进时的生存裁决；诊断必须先确定 OOM 域和触发分配，再解释回收为何失败、victim 为何被选中以及内存为何持续增长。
