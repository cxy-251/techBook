第160章：隔离与资源限制问题诊断
==============================

本章必须记住
------------

#. 容器隔离故障必须从一个具体宿主 PID 开始，而不是从镜像名、Pod 名或容器内 PID 猜测。
#. 目标 PID 确定后，诊断必须拆成三条线：Namespace 视图、Cgroup 资源限制、Credential/Capability/Security 权限。
#. Namespace 回答“进程看到什么”；Cgroup 回答“进程组可以使用多少资源”；Credential、Capability、LSM、Seccomp 回答“进程能对对象做什么”。
#. 同一个用户态 ``EPERM``、``EAGAIN``、OOM 或 Timeout 可能来自完全不同的内核层级。
#. 容器内 PID 和宿主 PID 可能不同，必须先从 Runtime、CRI、Cgroup 或 ``NSpid`` 找到宿主 Task。
#. ``/proc/<pid>/status`` 中的 ``NSpid``、UID/GID、Capability 和 ``NoNewPrivs`` 是建立 Task 身份的重要证据。
#. ``/proc/<pid>/ns/*`` 显示目标 Task 的各类 Namespace 成员关系。
#. 同类型 Namespace 的 ``st_dev:st_ino`` 相同表示共享同一活动视图。
#. ``lsns -p <pid>`` 适合聚合目标 Task 的 Namespace；具体资源状态仍要进入对应视图检查。
#. ``nsenter`` 通过 ``setns`` 进入目标 Namespace，适合执行只读诊断命令。
#. 进入 Network Namespace 后观察 ``ip addr``、``ip route``、Socket 和 Netfilter，不能用宿主输出替代。
#. 进入 Mount Namespace 后读取 ``/proc/self/mountinfo``、``findmnt`` 和路径属性，不能只看宿主目录树。
#. PID Namespace 问题要同时检查 ``pid``、``pid_for_children``、匹配的 ``procfs`` Mount 和 Namespace PID 1。
#. 容器内 ``ps`` 为空或看到宿主进程，常见原因是 PID Namespace 与 ``/proc`` Mount 不匹配。
#. 路径在宿主存在但容器内不存在，首先检查 Mount Namespace、Bind/Overlay Mount 和 Rootfs，而不是直接判断文件被删除。
#. 容器内 Mount 影响宿主，首先检查 Shared Mount Propagation 和 Runtime Rootfs 装配顺序。
#. 容器端口监听异常，必须确认目标 Socket 位于哪个 Network Namespace，端口冲突域也在该 Namespace 内。
#. Network Namespace 内接口存在不代表链路可用；继续检查 Link Up、Address、Route、Neighbor、Veth Peer、Host Forwarding 和 Netfilter。
#. Veth 两端属于不同视图，必须分别观察容器端和宿主端 Counter、MTU、Queue 与 Drop。
#. User Namespace 问题要读取 ``uid_map``、``gid_map``、``setgroups`` 和目标对象宿主所有者。
#. 容器内 UID 0 只表示当前 User Namespace 的 Root 身份，不表示拥有 Initial User Namespace 的全局权限。
#. ``CapEff`` 是 Capability 位图的一个集合视图，仍需结合 Bounding、Permitted、Ambient、User Namespace 和目标对象判断。
#. ``capsh``、``getpcaps`` 等用户态工具可辅助解码，内核事实仍由 Credential 与 namespace-aware Capability 检查决定。
#. ``NoNewPrivs: 1`` 表示进程不能通过后续 ``execve`` 获得新的特权，常与 Seccomp 和沙箱配置相关。
#. LSM 拒绝需要查看 Audit/Kernel Log 中的 SELinux、AppArmor 或其它策略记录。
#. Seccomp 拒绝需要确认 Action、Syscall Number、Architecture 和 Filter；它可能返回 Errno、Trap、Kill 或 User Notification。
#. ``strace`` 能显示失败系统调用和 Errno，不能单独指出拒绝来自 DAC、Capability、LSM 还是 Seccomp。
#. Audit 记录若可用，应还原 Subject、Object、Operation、Capability、LSM Context 和 Syscall。
#. ``/proc/<pid>/cgroup`` 是确认目标 Task 真实 Cgroup 归属的首要入口。
#. 在 Cgroup v2 中，从目标节点到 Root 的所有祖先限制都可能生效。
#. 只读取目标目录的 ``memory.max`` 或 ``cpu.max`` 不足以排除父级限制。
#. 诊断 Cgroup 前必须确认系统是 v1、v2 还是混合模式，并定位对应挂载点。
#. Systemd、Kubernetes 和 Runtime 的配置名只是管理层线索，最终值要回读 Cgroupfs。
#. CPU 吞吐低首先区分 CPU Saturation、CPU Quota Throttling、Cpuset 限制、CPU Affinity 和调度优先级。
#. ``cpu.stat`` 中 ``nr_throttled``、``throttled_usec`` 等字段增长是 CPU Quota 生效的重要证据，精确字段依版本。
#. ``cpu.max`` 为 ``max`` 不表示没有父级 Quota；必须逐级向上读取。
#. ``cpu.weight`` 只影响竞争中的相对份额，不能据此直接计算固定 CPU 百分比。
#. ``cpuset.cpus.effective`` 显示任务真实可运行 CPU，配置值可能因父级和 Online CPU 被收窄。
#. 单核热、其余 CPU 空闲时，应同时检查 Cpuset、Task Affinity、IRQ/NAPI Affinity、单线程业务和锁竞争。
#. 容器 OOM 必须区分 Memcg OOM、全局 OOM、用户态分配失败和进程自身地址空间限制。
#. ``memory.current`` 是 Cgroup 计费，不等于单进程 RSS。
#. ``memory.events`` 中 ``high``、``max``、``oom``、``oom_kill`` 的增长可定位 Memory Controller 事件，字段依内核版本。
#. Memcg OOM 发生时宿主仍可能有空闲内存，因为失败边界是 Cgroup 的 ``memory.max``。
#. ``memory.high`` 可造成分配路径回收和明显延迟，即使没有 OOM Kill。
#. ``memory.swap.current``、``memory.swap.max``、PSI 与 Reclaim 证据用于判断 Swap 和内存压力。
#. 应用报告 OOM 不一定有 Kernel OOM Kill；Allocator、Language Runtime、RLIMIT 或地址空间碎片也可能主动失败。
#. PIDs Limit 命中时 ``fork``/``clone`` 常返回 ``EAGAIN``，应读取 ``pids.current``、``pids.max``、``pids.events``。
#. Thread 计入 PIDs Controller，低 ``pids.max`` 可让多线程服务在进程数看似很少时仍创建失败。
#. 全局 PID 耗尽、``RLIMIT_NPROC``、Memory Failure 和 PIDs Controller 都可能导致 Fork 失败，必须分层验证。
#. I/O 吞吐低首先检查 ``io.max``、``io.stat``、``io.pressure`` 和目标块设备 Major:Minor。
#. 容器文件位于 OverlayFS 时，最终 I/O 可能落到宿主 Upper/Lower/Backing Device，不能按容器路径名推断限速设备。
#. Page Cache 命中、Dirty Page 积累和 Writeback 会让应用系统调用时间与块设备 I/O 时间错开。
#. I/O PSI 表示任务因 I/O 等待而失去进展，不等于设备硬件一定慢。
#. 网络吞吐限制通常不直接来自 Cgroup v2 内建 Net Controller；可能来自 TC/BPF、Netns、CPU Quota、Socket Buffer 或虚拟网络路径。
#. 容器内 DNS 故障要区分 ``/etc/resolv.conf`` Mount、Network Namespace Route、DNS Server 可达、UDP/TCP 端口和策略限制。
#. 设备访问失败要检查设备节点 Major/Minor、Mount Namespace、Cgroup Device Policy、Capability、LSM 和驱动状态。
#. ``/dev`` 中看到节点不证明底层设备存在，也不证明权限检查允许打开。
#. Mount 失败要同时检查 Mount Namespace、User Namespace、``CAP_SYS_ADMIN`` 范围、Filesystem 支持、LSM 和 Seccomp。
#. BPF、Perf、Module、Raw Socket 等接口的权限可能依 Capability、User Namespace、Lockdown、LSM 和 Sysctl 共同决定。
#. Container Runtime 启动失败应定位到 Namespace、ID Mapping、Mount、Cgroup、Credential、Seccomp 或 ``execve`` 的第一个失败阶段。
#. Runtime 日志中的最终错误字符串可能压缩了内核原始 Errno，必要时结合 Audit、Trace 和最小复现实验。
#. ``dmesg`` 可能受权限限制，容器内不可见不表示宿主 Kernel Log 没有记录。
#. Namespace 泄漏诊断要查成员 Task、Namespace fd、Bind Mount、Runtime Shim 和相关内核对象引用。
#. Cgroup 删除失败常因仍有成员、子 Cgroup、打开 fd 或异步清理；不要直接强制删除目录掩盖成员关系。
#. 容器退出后 Veth、Mount 或 Cgroup 残留，通常是 Runtime/Network Plugin/GC 的用户态清理链未闭合。
#. Reset、Restart 和 Delete 必须可重复，首次成功、第二次失败常指向残留 fd、Mount、Cgroup 或 Namespace 引用。
#. 诊断命令必须尽量只读；写 Cgroup、进入 Namespace 后修改网络或 Mount 会改变故障现场。
#. 需要修改时先保存原配置，并一次改变一个变量。
#. 时间线非常重要：Counter 当前值无法证明问题发生时增长，应采集前后差值和时间戳。
#. Cgroup Counter、Network Counter 和 Namespace inode 的生命周期不同，Runtime 重建后需记录 Generation。
#. 对比正常与异常容器时，要保证镜像、Kernel、Runtime、Cgroup 父级、Namespace 共享模式和流量条件一致。
#. 诊断应优先寻找“第一个不符合预期的内核边界”，而不是收集大量没有因果关系的命令输出。
#. 稳定排障顺序是：固定 Task → 验证视图 → 验证资源位置 → 验证身份权限 → 对齐第一个失败系统调用 → 检查清理生命周期。
#. 精确 Procfs 字段、Cgroup 文件、Capability 名称、LSM 日志和 Runtime 路径具有版本与发行版差异。
#. 稳定源码阅读顺序是：``/proc`` Task Evidence → Namespace/Cgroup Objects → Resource/Permission Check → Error Return → Audit/Event → Teardown。

必背路径
--------

目标 Task 基线：

::

   从 Runtime/CRI 找到宿主 PID
   → 读取 /proc/PID/status
   → 记录 NSpid、Uid/Gid、CapEff、NoNewPrivs
   → 读取 /proc/PID/ns/*
   → 读取 /proc/PID/cgroup
   → 固定同一故障时间窗口

Namespace 诊断：

::

   比较目标 PID 与宿主/正常进程的 Namespace inode
   → 确认异常属于 PID/Mount/Net/User/IPC/UTS/Time 哪类视图
   → nsenter 进入目标视图执行只读检查
   → 读取 mountinfo、ip route、socket、uid_map 等
   → 检查跨 Namespace 连接和引用

Cgroup 诊断：

::

   /proc/PID/cgroup 定位目标节点
   → 确认 v1/v2 与挂载点
   → 从目标目录逐级向 Root 读取 Controller 文件
   → 检查 cpu.stat / memory.events / pids.events / io.stat / PSI
   → 对齐应用错误发生时间
   → 找到第一个命中的限制

权限拒绝诊断：

::

   strace 定位失败 Syscall 与 Errno
   → 检查 UID/GID Mapping
   → 检查 Capability 集合及 User Namespace 范围
   → 检查 Mount/Device 对象权限
   → 检查 LSM Audit
   → 检查 Seccomp Action
   → 确认哪一层首先拒绝

容器残留诊断：

::

   确认业务 Task 已退出
   → 查 Runtime Shim/Helper
   → 查 Namespace fd 与 Bind Mount
   → 查 Cgroup 成员和子树
   → 查残留 Mount、Veth、Netns 与 Socket
   → 按逆序释放外部引用
   → 验证再次创建/删除可重复

必须区分
--------

容器内 PID 与宿主 PID
   同一 Task 在不同 PID Namespace 中有不同编号，诊断入口必须使用正确宿主 Task。

Memcg OOM 与全局 OOM
   Memcg OOM 由组级限制触发，宿主仍可能有可用内存；全局 OOM 来自系统整体压力。

CPU Throttle 与 CPU 饱和
   Throttle 是 Quota 策略阻止运行；饱和是可运行任务竞争 CPU。

容器内 Root 与宿主权限
   UID 0 的权力受 User Namespace Mapping、Capability 范围、LSM 和 Seccomp 限制。

配置声明与内核事实
   YAML/OCI/Systemd 表达意图；Procfs、Cgroupfs、Audit 和对象状态证明实际生效。

一句话结论
----------

容器排障必须围绕真实 Task 把视图、资源和权限三条证据链闭合，最先偏离预期的内核边界才是根因位置。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 32，Namespaces, Cgroups, Resource Control, and Container Internals；
* AIBook 章节：Chapter 160，Debugging Isolation and Resource Limit Problems；
* 源文件：``docs/LinuxK/Part_32_Namespaces_Cgroups_Resource_Control_and_Container_Internals/Chapter_160_Debugging_Isolation_and_Resource_Limit_Problems.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_32_Namespaces_Cgroups_Resource_Control_and_Container_Internals/Chapter_160_Debugging_Isolation_and_Resource_Limit_Problems.md>`_。