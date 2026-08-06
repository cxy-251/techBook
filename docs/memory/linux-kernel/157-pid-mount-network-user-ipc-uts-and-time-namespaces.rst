第157章：PID、Mount、Network、User、IPC、UTS 与 Time Namespace
==============================================================

本章必须记住
------------

#. 不同 Namespace 类型回答不同问题：PID 隔离编号，Mount 隔离挂载树，Network 隔离网络栈，User 隔离身份映射与 Capability 范围。
#. IPC Namespace 隔离 System V IPC 与 POSIX Message Queue，UTS Namespace 隔离 Hostname/NIS Domain，Time Namespace 隔离部分时间偏移视图。
#. 一个 Task 同时关联多种 Namespace；容器的隔离效果来自这些视图组合，不来自单一“Container Namespace”。
#. 判断容器视图时必须逐类型检查，不能用其中一个 Namespace 推断其它类型。
#. PID Namespace 是层级结构，同一个 ``task_struct`` 在不同 PID Namespace 中可以拥有不同 PID。
#. ``struct pid`` 保存一个执行实体在多层 PID Namespace 中的编号关系；PID 数字不是 Task 的全局永久身份。
#. 祖先 PID Namespace 可以观察后代 Namespace 中的 Task，后代不能反向枚举祖先全部进程。
#. 宿主机看到 PID 48217、容器看到 PID 1，通常仍指向同一个 Task。
#. PID 查找、Signal、Wait 和 ``/proc`` 枚举都必须带上观察者所在 PID Namespace 解释。
#. PID Namespace 中的第一个进程成为该层 PID 1，承担孤儿进程接管和特殊 Signal/退出语义。
#. PID 1 退出通常会触发该 PID Namespace 内其它进程被终止并让该 Namespace 失去正常创建能力，精确行为以目标内核为准。
#. 容器内进程树是否正确还依赖把 ``procfs`` 挂载到匹配的 PID Namespace 视图。
#. 只创建 PID Namespace 但继续使用宿主 ``/proc``，用户态工具仍可能看到错误或泄漏的进程视图。
#. ``/proc/<pid>/status`` 中的 ``NSpid``/``NStgid`` 可提供嵌套 PID 编号证据，具体字段受内核版本影响。
#. ``/proc/<pid>/ns/pid`` 是当前 PID Namespace，``pid_for_children`` 决定之后创建的子进程进入哪层。
#. ``unshare(CLONE_NEWPID)`` 不会把调用进程自身重新编号，必须再创建子进程才能看到新 PID Namespace。
#. Mount Namespace 隔离的是挂载关系和路径视图，不会复制底层 Superblock、Inode、Page Cache 或文件内容。
#. ``struct mnt_namespace`` 表示一棵挂载视图；路径解析还结合 Task 的 Root、CWD 和具体 Mount/Dentry。
#. 不同 Mount Namespace 可以引用同一文件系统和同一 Inode，同时把它们挂到不同路径。
#. 容器 Rootfs 常由 OverlayFS、Bind Mount 或独立文件系统准备，再在新的 Mount Namespace 内切换为 ``/``。
#. ``chroot`` 只改变路径解析根，不等于建立独立 Mount Namespace，也不自动清除旧根引用。
#. ``pivot_root`` 配合卸载旧根能更完整地切换 Mount Tree，但有挂载点和传播属性约束。
#. Mount Propagation 的 ``shared``、``slave``、``private`` 等关系决定挂载事件是否跨 Namespace 传播。
#. 新建 Mount Namespace 通常复制原挂载树关系；如果不处理 Shared Propagation，容器内 Mount 事件仍可能外泄。
#. 排查路径缺失或宿主目录泄漏时，应按 Mount Namespace inode → ``mountinfo`` → Propagation → Bind/Overlay 层 → 权限顺序检查。
#. Network Namespace 为一个独立 ``struct net`` 网络栈视图。
#. 它通常隔离网络设备、地址、路由、端口空间、Netfilter、Conntrack、Network Sysctl、``/proc/net`` 与 Abstract Unix Socket Namespace。
#. 同一个 TCP/UDP 端口可以在两个 Network Namespace 中分别绑定，因为冲突检查发生在各自 ``struct net`` 中。
#. Socket 创建时关联相应 Network Namespace；之后切换 Task 的 Network Namespace，不会迁移已有 Socket。
#. 物理 Netdev 同一时刻通常只属于一个 Network Namespace；Veth、Bridge、VLAN、Tunnel 等虚拟设备按对象规则存在。
#. 新 Network Namespace 通常包含 Loopback 设备对象，但需要显式置 Up 才能正常通信。
#. Veth Pair 是连接两个 Network Namespace 的常见桥梁：一端位于容器，另一端连接宿主 Bridge、Route 或 NAT。
#. Network Namespace 隔离不等于网络可达；仍需检查 Link、Address、Route、Neighbor、Forwarding、Netfilter 和外部路径。
#. 当 Network Namespace 销毁时，虚拟设备可随之删除；物理设备通常按核心规则返回 Initial Network Namespace。
#. ``struct net`` 内部拥有大量 Per-net 子系统状态，Namespace 释放要等待 Socket、Device、Work 和 Per-net 引用收束。
#. User Namespace 隔离 UID/GID 映射与 Capability 作用范围。
#. 容器内 UID 0 可以映射到宿主普通 UID；“容器内 Root”不等于 Initial User Namespace 的全局 Root。
#. ``uid_map``、``gid_map`` 把 Namespace 内 ID 区间映射到父 User Namespace 的 ID 区间。
#. 映射是分段区间，不是把所有 ID 简单加一个固定偏移；精确数量和写入规则以目标内核为准。
#. ``/proc/<pid>/uid_map``、``gid_map`` 和 ``setgroups`` 是观察与建立映射的重要接口。
#. User Namespace 的 Owner、Parent 和 ID Mapping 共同决定 Credential 怎样翻译到宿主视角。
#. ``kuid_t``/``kgid_t`` 是内核内部 ID 表示，向某个 User Namespace 显示时才转换为用户可见 UID/GID。
#. 一个 ID 在目标 User Namespace 中无有效映射时，访问、显示或对象创建会按具体路径失败或使用 Overflow ID。
#. Capability 不是脱离 User Namespace 的全局位图；``ns_capable(user_ns, CAP_*)`` 一类检查同时考虑 Credential 与目标 Namespace。
#. 在子 User Namespace 中拥有全部 Capability，只能对该 Namespace 拥有或允许管理的对象生效。
#. Mount、Device、BPF、模块加载和宿主全局资源常需要 Initial User Namespace 或对象所有者 Namespace 中的能力。
#. User Namespace 是 Rootless Container 的基础，也扩大了可由非特权用户触达的内核接口，部署时需结合系统策略和补丁状态。
#. IPC Namespace 隔离 System V Shared Memory、Semaphore、Message Queue 和 POSIX Message Queue 视图。
#. 相同 IPC Key 或 Queue 名可以在不同 IPC Namespace 中独立存在。
#. IPC Namespace 不隔离普通匿名共享内存、文件映射或 Unix Filesystem Socket；这些由 VFS、Credential 和其它 Namespace 决定。
#. IPC 对象可能持有内存和等待者，Namespace 退出需要按各 IPC 子系统规则唤醒、删除和释放。
#. UTS Namespace 隔离 ``hostname`` 与 NIS Domain Name 视图。
#. ``sethostname()`` 修改当前 UTS Namespace 的字段，不会自动修改 DNS、``/etc/hosts``、TLS 身份或网络可达性。
#. 同一 UTS Namespace 内的进程共享 Hostname；不同 UTS Namespace 可以显示不同名称。
#. UTS Namespace 是标识视图，不是网络隔离机制。
#. Time Namespace 隔离部分时间基准的偏移，主要用于调整 ``CLOCK_MONOTONIC``、``CLOCK_BOOTTIME`` 等视图，支持范围依内核版本。
#. Time Namespace 不允许容器任意改变宿主硬件时钟或全局 Wall Clock。
#. ``/proc/<pid>/timens_offsets`` 一类接口可展示或设置允许的偏移，写入权限与生命周期存在约束。
#. Time Namespace 的偏移主要影响 Namespace 内时间读取和定时语义，不改变 CPU 执行速度。
#. IPC、UTS、Time Namespace 通常通过 ``nsproxy`` 关联；User Namespace 仍主要随 Credential。
#. Cgroup Namespace 虽不在本章标题中，也常与容器组合，它只改变 Cgroup 路径可见根，不改变资源限制本身。
#. 每种 Namespace 都有自己的对象生命周期和退出路径，不能用统一 ``free(namespace)`` 模型解释。
#. 一个 Namespace 的最后成员退出后，打开 fd、Bind Mount、关联内核对象和祖先关系仍可保留它。
#. 组合 Namespace 时顺序很重要：例如 User Namespace 可改变后续创建其它 Namespace 的权限语境，Mount Namespace 要在修改 Rootfs 前建立。
#. ``setns`` 加入多个 Namespace 时，错误顺序可能导致后续步骤权限不足或路径不可见。
#. 容器 Runtime 常通过父子进程同步，在目标进程 ``execve`` 前完成 Namespace、ID Mapping、Rootfs、Network 和 Credential 装配。
#. Namespace 隔离也有显式共享模式：容器可以加入另一个容器或宿主的 Network/PID/IPC Namespace。
#. 共享某类 Namespace 会共享该类对象视图和冲突域，例如共享 Network Namespace 会共享端口空间和路由。
#. Kubernetes Pod 中多个容器常共享 Network Namespace，并可能按配置共享 PID Namespace；它们的 Cgroup 仍可不同。
#. 观察容器进程时，必须从宿主 PID 开始，再读取 ``/proc/<pid>/ns``、``uid_map``、``mountinfo``、Network 和时间接口。
#. ``lsns`` 可聚合同类 Namespace 与成员进程，但不能替代具体 Namespace 内的资源状态检查。
#. ``nsenter`` 只负责进入视图；进入后工具显示的内容仍受 Credential、Capability、LSM 和 Mount 可用性影响。
#. 排查 PID 不一致时应使用 NSpid、宿主/容器 ``/proc`` 和观察者 Namespace，而不是假设进程复制了两份。
#. 排查文件视图异常时应检查 Mount Propagation 与 Rootfs，不要把所有错误归因于 User Namespace 权限。
#. 排查网络异常时应先进入正确 Network Namespace，避免用宿主 ``ip route`` 解释容器内部 Route。
#. 排查“容器内 Root 无权限”时应检查 UID/GID Mapping、目标对象 Owner User Namespace、Capability、LSM 和 Seccomp。
#. 精确 Namespace 类型支持、结构成员、映射上限和权限规则具有内核版本差异。
#. 稳定源码阅读顺序是：Task/Cred 关联 → 具体 Namespace 对象 → 资源查找/编号翻译 → 创建/进入 → 引用与退出。

必背路径
--------

PID 编号翻译：

::

   task_struct
   → struct pid
   → 在每一层 pid_namespace 中保存编号
   → 宿主观察得到 Host PID
   → 容器观察得到 Namespace PID
   → Signal/Wait/Proc 按调用者视图解析

容器 Mount 视图：

::

   创建 Mount Namespace
   → 调整 Root Propagation
   → 准备 Overlay/Bind Rootfs
   → 挂载 /proc、/sys、/dev 等
   → pivot_root 或等价 Root 切换
   → 卸载旧根
   → execve 目标程序

容器网络：

::

   创建 Network Namespace
   → 创建 Veth Pair
   → 一端移动到目标 Netns
   → 启用 lo 与容器接口
   → 配置地址和路由
   → 宿主端连接 Bridge/Route/NAT
   → 分别验证容器与宿主 Netfilter

User Namespace 映射：

::

   创建 User Namespace
   → 进程取得该 Namespace 内的新 Credential 语境
   → 写 uid_map / gid_map
   → Namespace UID/GID 映射到父级 ID
   → Capability 只在相应 User Namespace 范围内生效
   → 对目标对象执行 namespace-aware 权限检查

组合隔离：

::

   PID Namespace 提供进程编号视图
   + Mount Namespace 提供 Rootfs 与挂载树
   + Network Namespace 提供独立网络栈
   + User Namespace 提供 ID/Capability 范围
   + IPC/UTS/Time 提供对应资源视图
   → 形成容器进程环境

必须区分
--------

* ``task_struct`` 与 PID 数字：Task 是执行实体；PID 是该实体在特定 PID Namespace 中的名字。
* Mount Namespace 与文件副本：Mount Namespace 隔离路径关系，底层 Inode、Superblock 和 Page Cache 可以共享。
* Network Namespace 与网络可达：独立网络栈只建立隔离边界，通信仍需要设备、地址、路由和过滤配置。
* 容器内 UID 0 与宿主 Root：子 User Namespace 的 Root 权力受 ID Mapping、Capability 范围和目标对象所有者限制。
* UTS Hostname 与网络身份：Hostname 是 UTS 视图字段，不自动决定 DNS、IP 地址或外部认证身份。

一句话结论
----------

每种 Namespace 都只隔离一种全局资源视图；容器隔离来自多张视图按正确顺序组合，而不是复制一台独立内核机器。
