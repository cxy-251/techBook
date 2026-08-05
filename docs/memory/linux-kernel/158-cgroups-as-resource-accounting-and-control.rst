第158章：Cgroup 作为资源统计与控制机制
=====================================

本章必须记住
------------

#. Cgroup 的本质是把 Task 组织成层级化进程组，并让不同 Controller 对这些进程组实施资源统计、分配、保护和限制。
#. Namespace 改变进程看到的资源视图；Cgroup 改变进程组如何消耗 CPU、内存、I/O、PID 和 NUMA 资源。
#. Cgroup Core 管理层级、成员关系和对象生命周期；CPU、Memory、I/O、PIDs、Cpuset 等 Controller 定义具体资源语义。
#. 在 Cgroup v2 中，系统使用统一层级，常挂载于 ``/sys/fs/cgroup``。
#. ``cgroup.procs`` 表示某个 Cgroup 的进程成员集合；写入 PID 会把对应进程迁移到该 Cgroup。
#. 新进程通常继承父进程创建时所在的 Cgroup。
#. 迁移一个进程不会自动迁移其已经存在的所有子孙进程；Runtime 必须在正确时点放置目标进程。
#. ``/proc/<pid>/cgroup`` 是判断目标进程真实 Cgroup 归属的首要入口。
#. Cgroup v2 常显示为 ``0::/path``，该路径是相对于统一 Cgroupfs 根的成员位置。
#. 目录名来自用户态管理策略，例如 Systemd Slice、Scope、Service、Pod 或 Container ID；真正限制要读取 Controller 文件。
#. ``struct cgroup`` 表示层级中的一个节点。
#. ``struct cgroup_subsys_state`` 表示某个 Controller 在一个 Cgroup 节点上的状态。
#. ``struct css_set`` 关联 Task 当前使用的一组 Controller/Cgroup 状态。
#. Task 成员关系与每个 Controller 的状态是不同对象，不能把目录节点本身等同于某个资源限制实现。
#. Cgroup v2 的 Controller 可用性由 ``cgroup.controllers`` 暴露。
#. 父节点通过 ``cgroup.subtree_control`` 把 Controller 向直接子 Cgroup 分发。
#. 子目录缺少 ``memory.max``、``cpu.max`` 等文件时，应先检查父级是否提供并启用了相应 Controller。
#. Controller 的限制具有层级性，父级限制会约束整个子树。
#. 子 Cgroup 的 ``memory.max=max`` 不表示完全无限制，父级可能有更低上限。
#. ``cpu.weight`` 表示同一竞争层级中的相对 CPU 权重，不是固定 CPU 百分比保证。
#. 只有发生 CPU 竞争时，相对权重才影响公平调度份额；系统空闲时一个低权重组仍可使用更多 CPU。
#. ``cpu.max`` 通常用 ``quota period`` 表达 CPU 带宽上限。
#. CPU Quota 用尽后，该 Cgroup 可在当前周期内被 Throttle，直到新周期补充可用时间。
#. ``cpu.stat`` 中的使用量、Throttle 次数和 Throttled 时间是判断 CPU 限额影响的重要证据。
#. CPU Throttling 与 CPU 饱和不同：前者是策略限额，后者是运行队列中任务真实竞争。
#. Cpuset Controller 限定 Task 可运行 CPU 和可分配内存节点。
#. ``cpuset.cpus``/``cpuset.mems`` 表示配置集合，``*.effective`` 表示结合父级和 Online 状态后的真实有效集合。
#. Cpuset 为空、与父级不兼容或 CPU/Memory Node Offline 会导致配置失败或运行位置异常。
#. Memory Controller 统计并限制 Cgroup 关联的匿名内存、Page Cache、内核内存及其它受支持对象，精确计费随版本演进。
#. ``memory.current`` 表示当前计费使用量；它不是进程 RSS 简单求和。
#. ``memory.max`` 是硬上限，接近上限时内核会尝试在该 Memcg 范围内回收。
#. 无法回收到限制以内时可触发 Cgroup 范围的 OOM，而宿主机仍可能有空闲内存。
#. ``memory.high`` 是节流和回收压力边界，超过后任务可被迫在分配路径承担回收成本，不等同于立即 OOM。
#. ``memory.low``/``memory.min`` 提供不同强度的内存保护语义，只有在层级和资源竞争中解释才有意义。
#. ``memory.events``/``memory.events.local`` 提供 High、Max、OOM、OOM Kill 等事件证据，具体字段依内核版本。
#. ``memory.oom.group`` 可影响 Cgroup OOM 时按组处理的策略，不能假设每次只杀一个任意进程。
#. Memcg OOM 与全局 OOM 必须分开：前者由该层级内存限制触发，后者由系统总体可用内存耗尽触发。
#. Swap 计费和限制通常通过 ``memory.swap.*`` 一类接口表达，是否可用依内核与系统配置。
#. I/O Controller 按块设备及 Cgroup 追踪和控制 I/O。
#. ``io.stat`` 提供设备级读写字节、I/O 次数和其它统计。
#. ``io.max`` 可按 Major:Minor 设备设置带宽或 IOPS 上限。
#. I/O 限制作用于真实块层路径；Page Cache 命中或尚未发生 Writeback 的写入不会立即表现为设备 I/O。
#. Buffered Write 的任务 Cgroup 与后续 Writeback I/O 归属有专门机制，不能只按执行 Flusher 线程归因。
#. Device Mapper、RAID、Loop 和容器 OverlayFS 会让上层文件路径与最终块设备不同，I/O 限速应针对真实生效设备验证。
#. ``io.pressure`` 属于 PSI 证据，表示任务因 I/O 资源等待而失去运行进展，不等同于某个设备吞吐值。
#. PIDs Controller 限制 Cgroup 及其子树可创建的 Task 数量。
#. ``pids.current`` 是当前计数，``pids.max`` 是限制，``pids.events`` 可显示 Max 命中。
#. 超过 ``pids.max`` 时 ``fork``/``clone`` 常返回 ``EAGAIN``，这和全局 PID 空间耗尽是不同原因。
#. Thread 也会消耗 PIDs Controller 的 Task 计数，不能只按进程组数量估算。
#. Cgroup Freeze 可暂停一组任务，具体接口和状态机需按目标内核确认；Freeze 不等于销毁任务或释放资源。
#. Cgroup Events、Pressure、Stat 文件是资源控制的证据面，不只是配置展示。
#. Cgroup v1 允许多棵独立 Hierarchy，不同 Controller 可使用不同进程划分。
#. Cgroup v2 强调统一层级、统一成员关系和更一致的 Controller 协作语义。
#. v1 与 v2 文件名、层级、迁移和 Controller 行为不能混用。
#. 混合模式系统可能同时挂载 v1 与 v2，排查时必须先确认目标进程在哪个 Hierarchy 和 Controller 上。
#. 只看到 ``/sys/fs/cgroup`` 并不能证明所有 Controller 都运行在 v2，应查看挂载和 ``/proc/<pid>/cgroup``。
#. Cgroup Namespace 只改变进程看到的 Cgroupfs 路径根，不能改变目标进程真实 Cgroup 归属。
#. 容器内显示为 ``/`` 的 Cgroup 路径，宿主视角可能位于很深的 Systemd/Kubernetes 层级。
#. Cgroup 的限制应在目标程序早期资源使用之前设置和生效。
#. Runtime 若在目标程序 ``execve`` 后才迁移，初始化阶段可能已经分配内存、创建线程或产生 I/O，形成统计与限制窗口。
#. ``clone3(CLONE_INTO_CGROUP)`` 可在支持的内核中让新 Task 直接进入目标 Cgroup，具体使用与权限具有版本边界。
#. Controller 配置文件写入是内核 UAPI，用户态 Runtime/Systemd 只是管理者。
#. 写入成功只表示内核接受了策略，不证明业务目标已实现；必须观察统计、事件和实际延迟/吞吐。
#. ``cpu.max``、``memory.max``、``io.max`` 等限制之间会相互作用，例如内存压力可增加 I/O，CPU Throttle 可延迟内存回收和网络处理。
#. Cgroup 层级越深，诊断越需要从目标节点一路向上检查父级限制。
#. 资源有效边界通常是当前节点与所有祖先约束共同作用的结果。
#. Delegation 允许受信任子管理者在一棵子树内创建和管理 Cgroup，但必须遵守权限、No-internal-process 等 v2 规则。
#. Cgroup v2 的 Domain/Threaded 模式会改变 Task 和 Controller 的组织方式，精确规则属于版本敏感细节。
#. 内部节点是否允许持有进程与 Controller 类型有关，不能根据普通目录经验随意迁移。
#. 删除 Cgroup 前必须先迁移或结束成员，并处理子 Cgroup 和 Controller 引用。
#. 删除目录不等于资源统计对象立即释放；Per-CPU 数据、RCU 和在途资源记账可能延迟最终销毁。
#. 已打开的 Cgroup fd 可引用 Cgroup 对象，现代 API 也可通过 fd 执行安全的层级操作。
#. Cgroup ID、目录 inode 和路径都不是跨销毁、跨启动永久业务身份，管理面应维护自己的 Generation/Container ID。
#. 排查资源限制时第一步固定宿主机 PID，再读取 ``/proc/<pid>/cgroup``。
#. 第二步确认 Cgroup v1/v2 模式和对应挂载点。
#. 第三步沿目标路径到 Root 读取相关 Controller 文件与事件。
#. 第四步把现象映射到资源语义：CPU Throttle、Memcg OOM、PIDs Max、I/O Delay 或 Cpuset Locality。
#. 第五步对齐故障时间线，确认事件计数在问题窗口真实增长。
#. 只看编排 YAML、Docker 参数或 Systemd Unit 不足以证明内核实际状态，必须读取 Cgroupfs。
#. 只看单个进程 RSS、CPU 百分比或 I/O 统计也不足以证明组级限制。
#. ``systemd-cgls``、``systemd-cgtop`` 等工具提供管理视图，内核事实仍由 ``/proc`` 与 Cgroupfs 文件支撑。
#. 修改 Cgroup 限制会直接改变正在运行工作负载，应先保存旧值并在受控环境一次改变一个变量。
#. 精确 Controller 文件、计费范围、统计字段和 v1/v2 兼容性具有版本差异。
#. 稳定源码阅读顺序是：Task Membership → Cgroup Core → Controller State → Resource Charge/Check → Event/Stat → Migration/Release。

必背路径
--------

进程归属：

::

   Task 创建
   → 继承父 Task 的 css_set / Cgroup 成员关系
   → Runtime 可迁移到目标 Cgroup
   → /proc/<pid>/cgroup 暴露实际路径
   → 各 Controller 按该层级计费和限制

Controller 分发：

::

   父 Cgroup 读取 cgroup.controllers
   → 在 cgroup.subtree_control 启用 +cpu/+memory/+io 等
   → 直接子 Cgroup 获得对应控制文件
   → 写入策略值
   → 内核资源路径执行统计、限制或保护

Memory Limit：

::

   Cgroup 内任务分配内存
   → Memory Controller Charge
   → memory.current 增长
   → 超过 memory.high 时节流/回收
   → 接近 memory.max 时强制回收
   → 无法满足限制
   → Memcg OOM / OOM Kill Event

CPU Quota：

::

   任务在 CPU 上运行
   → 记入 Cgroup CPU Runtime
   → 当前 Period 的 Quota 用尽
   → 任务组被 Throttle
   → 新 Period 补充 Runtime
   → cpu.stat 记录 Throttle 证据

分层诊断：

::

   固定 PID
   → 读取 /proc/PID/cgroup
   → 定位 /sys/fs/cgroup 路径
   → 从当前节点逐级向父节点检查限制
   → 读取 Events/Stat/Pressure
   → 对齐应用错误和故障时间
   → 确定最先触发的 Controller

必须区分
--------

Namespace 与 Cgroup
   Namespace 管视图和命名；Cgroup 管进程组资源统计、分配和限制。

``cpu.weight`` 与 ``cpu.max``
   Weight 是竞争时相对份额；Max 是周期性硬带宽上限。

``memory.high`` 与 ``memory.max``
   High 主要施加回收和节流压力；Max 是硬上限并可能触发 Memcg OOM。

进程 RSS 与 ``memory.current``
   RSS 是进程视角的一部分内存；Memory Controller 还计费共享、缓存和内核对象等范围。

子节点显示无限与实际无限
   当前节点的 ``max`` 仍受祖先 Cgroup 更严格边界约束。

一句话结论
----------

Cgroup 用统一成员树把 Task 交给资源 Controller：真实限制来自目标节点和全部祖先的共同状态，而不是容器配置中的一个孤立数字。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 32，Namespaces, Cgroups, Resource Control, and Container Internals；
* AIBook 章节：Chapter 158，Cgroups as Resource Accounting and Control；
* 源文件：``docs/LinuxK/Part_32_Namespaces_Cgroups_Resource_Control_and_Container_Internals/Chapter_158_Cgroups_as_Resource_Accounting_and_Control.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_32_Namespaces_Cgroups_Resource_Control_and_Container_Internals/Chapter_158_Cgroups_as_Resource_Accounting_and_Control.md>`_。