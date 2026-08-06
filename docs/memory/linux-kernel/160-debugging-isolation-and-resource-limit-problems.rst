第160章：隔离与资源限制问题诊断
==============================

核心知识点
----------

诊断入口必须是真实宿主 Task
   容器名、Pod 名和容器内 PID 都是管理视图。排障必须先定位宿主 ``task_struct`` 对应的 PID，否则 Namespace、Cgroup、Credential 和时间线都会指向错误对象。

问题要拆成三条证据链
   Namespace 解释进程看见什么，Cgroup 解释进程组可使用多少资源，Credential、Capability、LSM 与 Seccomp 解释进程能对对象做什么。同一 Errno 可能来自不同链路。

Namespace 证据围绕成员关系与内部状态
   ``/proc/<pid>/ns`` 证明目标 Task 属于哪些活动视图；进入目标 Mount、Network 或 PID 视图后，才能解释其中的路径、路由、Socket 与进程树。

Cgroup 证据必须沿祖先层级检查
   ``/proc/<pid>/cgroup`` 给出成员位置，真正有效边界是当前节点与全部祖先 Controller 的共同结果。单独读取容器目录的 ``max`` 不能排除父级限制。

第一个失败系统调用是权限诊断锚点
   ``strace`` 或审计证据应先确定具体 Syscall 与 Errno，再依次检查 UID/GID Mapping、对象权限、Capability 范围、LSM 和 Seccomp。最终用户态错误文本通常不足以区分拒绝层。

CPU 低吞吐存在多种机制
   CPU Saturation、``cpu.max`` Throttling、Cpuset 收窄、Task Affinity、IRQ/NAPI 局部性和锁竞争表现相似。``cpu.stat``、有效 CPU 集合和 Runqueue 证据必须联合解释。

内存失败要区分计费边界
   Memcg OOM 可在宿主仍有空闲内存时发生；``memory.high`` 可造成回收延迟而不 Kill；语言运行时、RLIMIT 与地址空间问题也可返回分配失败。事件计数决定失败属于哪一层。

Fork 与 I/O 失败也有独立控制面
   ``pids.max`` 命中、全局 PID 耗尽、``RLIMIT_NPROC`` 和内存不足都可能产生 ``EAGAIN``。I/O 慢则要把 ``io.max``、真实块设备、Page Cache、Writeback 和 PSI 放到同一时间线。

容器内 Root 不是权限结论
   UID 0 还要结合 User Namespace Mapping、Capability 各集合、``no_new_privs``、LSM、Seccomp 与目标对象所有者。设备节点存在也不证明设备可打开。

残留资源说明退出链未闭合
   容器退出后仍存在 Namespace、Cgroup、Mount 或 Veth，通常源于 Runtime、Shim 或网络插件保留引用。首次删除成功、第二次失败常指向残留 fd、传播关系或异步清理。

关键路径
--------

目标 Task 基线：

::

   从 Runtime / CRI 定位宿主 PID
   → 读取 status 中的 NSpid、Uid/Gid、Capability、NoNewPrivs
   → 读取 Namespace 成员关系
   → 读取 Cgroup 成员路径
   → 固定同一故障时间窗口与对象 generation

三线诊断：

::

   Namespace 线：确认视图与内部对象
   → Cgroup 线：确认成员位置、祖先限制与事件
   → Permission 线：确认 Syscall、Credential、Capability、LSM、Seccomp
   → 找到最先偏离预期的内核边界

资源限制定位：

::

   CPU：throttle / cpuset / affinity / runqueue
   → Memory：high / max / OOM / swap / reclaim
   → PIDs：current / max / fork 失败
   → I/O：io.max / io.stat / writeback / PSI
   → 对齐事件增量与应用错误

残留对象收束：

::

   确认业务 Task 已退出
   → 查 Shim、Helper 与打开 fd
   → 查 Namespace Bind Mount 和成员
   → 查 Cgroup 子树与异步引用
   → 查 Mount、Veth、Socket 和 Network Namespace
   → 按创建依赖逆序释放
   → 验证创建、重启、删除可重复

概念辨析
--------

* 容器内 PID 与宿主 PID：同一 Task 在不同 PID Namespace 中编号不同，宿主 PID 才是跨子系统诊断锚点。
* Memcg OOM 与全局 OOM：前者由组级硬限制触发；后者来自系统整体内存压力。
* CPU Throttle 与 CPU 饱和：Throttle 是策略禁止继续运行；饱和是可运行任务真实竞争 CPU。
* 容器内 Root 与宿主权限：UID 0 仍受 User Namespace、Capability、LSM、Seccomp 和对象所有者约束。
* 配置声明与内核事实：YAML、OCI、Systemd 只是意图；Procfs、Cgroupfs、Audit 与运行对象状态才是证据。

本章结论
--------

隔离与资源问题必须围绕真实 Task，把视图、资源和权限三条证据链放在同一时间线上。最先出现不符合预期状态的内核边界，才是根因位置。
