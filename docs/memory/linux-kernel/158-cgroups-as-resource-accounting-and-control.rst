第158章：Cgroup 作为资源统计与控制机制
=====================================

核心知识点
----------

Cgroup 是层级化 Task 资源分组
   Cgroup Core 维护层级、成员关系和生命周期，各 Controller 再对 CPU、内存、I/O、PID 与 NUMA 资源执行统计、分配、保护或限制。

Cgroup v2 使用统一成员树
   统一层级让同一 Task 组合接受多个 Controller 的约束。``struct cgroup`` 表示树节点，``css_set`` 关联 Task 的控制状态组合，``cgroup_subsys_state`` 表示单个 Controller 在节点上的状态。

成员关系决定资源计费位置
   Task 通常继承父 Task 的 Cgroup，迁移通过 ``cgroup.procs`` 或创建时放置完成。配置目录存在不表示目标进程已经进入，真实归属应由 ``/proc/<pid>/cgroup`` 确认。

Controller 必须由父级向子树分发
   ``cgroup.controllers`` 表示父节点可用 Controller，``cgroup.subtree_control`` 决定哪些能力交给直接子节点。控制文件缺失往往是层级启用问题，不是 Controller 不存在。

有效限制来自当前节点与全部祖先
   子节点写 ``max`` 只表示本节点不再收紧，祖先仍可施加更严格边界。任何资源问题都必须沿 Cgroup 树向上检查，而不能只读取容器目录。

CPU Controller 区分份额与上限
   ``cpu.weight`` 只在竞争时决定相对份额；``cpu.max`` 用周期和配额形成硬带宽边界。配额耗尽导致 Throttle，与普通 Runqueue 饱和是不同现象。

Cpuset 决定合法执行与分配位置
   ``cpuset.cpus``、``cpuset.mems`` 给出配置集合，``*.effective`` 才反映父级、Online CPU 和 NUMA 状态共同作用后的有效范围。

Memory Controller 同时统计多类内存
   ``memory.current`` 不等于进程 RSS 求和；匿名页、Page Cache、内核内存及其它受支持对象都可能计费。``memory.high`` 主要施加回收与节流压力，``memory.max`` 是硬上限并可能触发 Memcg OOM。

I/O 与 PIDs Controller 具有独立失败语义
   ``io.max``、``io.stat`` 面向真实块设备路径；Page Cache 会让系统调用与设备 I/O 时间错开。``pids.max`` 限制 Task 数量，线程同样计数，命中后 ``fork/clone`` 常返回 ``EAGAIN``。

事件与 Pressure 是运行证据
   ``cpu.stat``、``memory.events``、``pids.events``、``io.stat`` 与 PSI 描述限制是否真实触发。配置值只表达策略，事件增量和业务时间线才能证明因果。

关键路径
--------

Task 成员关系：

::

   创建 Task
   → 继承父 Task 的 css_set
   → Runtime 在 execve 前放入目标 Cgroup
   → 各 Controller 以该成员关系计费
   → /proc/<pid>/cgroup 暴露实际路径

Controller 分发与生效：

::

   父节点提供 Controller
   → subtree_control 向子树启用
   → 子节点创建 Controller 状态
   → 写入 weight / max / cpuset 等策略
   → 资源热路径执行 charge、检查或调度
   → stat / events / pressure 记录结果

层级资源诊断：

::

   固定目标宿主 PID
   → 取得真实 Cgroup 路径
   → 确认 v1 / v2 与挂载层级
   → 从目标节点逐级检查祖先约束
   → 对齐 Controller 事件与故障窗口
   → 找到第一个实际命中的边界

概念辨析
--------

* Namespace 与 Cgroup：Namespace 改变资源视图；Cgroup 改变进程组怎样消耗和竞争资源。
* ``cpu.weight`` 与 ``cpu.max``：Weight 是竞争时相对份额；Max 是周期性 CPU 带宽上限。
* ``memory.high`` 与 ``memory.max``：High 施加回收和节流压力；Max 是可触发 Memcg OOM 的硬边界。
* 进程 RSS 与 ``memory.current``：RSS 是进程视角的部分内存，Memory Controller 还统计缓存和内核对象等范围。
* 当前节点无限与实际无限：当前节点的 ``max`` 仍受全部祖先的更严格限制。

本章结论
--------

Cgroup 用统一成员树把 Task 交给各资源 Controller。真实资源边界由成员位置、Controller 状态和所有祖先约束共同形成，不能从单个容器参数或单个目录值推断。
