第157章：PID、Mount、Network、User、IPC、UTS 与 Time Namespace
==============================================================

核心知识点
----------

PID Namespace 提供分层编号
   同一个 ``task_struct`` 可通过 ``struct pid`` 在多层 ``pid_namespace`` 中拥有不同 PID。祖先视图可以观察后代 Task，后代不能反向枚举祖先全部进程。

PID 1 具有 Namespace 级特殊职责
   每层 PID Namespace 的首个进程承担孤儿进程接管和信号语义。该进程退出会破坏该层进程树的正常生命周期，因此容器 Init 必须正确 Reap 和转发信号。

PID 视图依赖匹配的 procfs
   PID Namespace 只改变编号关系；用户态进程列表还取决于当前 Mount Namespace 中挂载的 procfs。复用宿主 ``/proc`` 会让工具显示错误视图。

Mount Namespace 隔离挂载树
   ``mnt_namespace`` 管理 Mount 关系和传播边界，不复制 Superblock、Inode 或 Page Cache。不同视图可以把同一文件系统挂到不同路径，也可共享同一底层文件内容。

Mount Propagation 决定事件是否外泄
   ``shared``、``slave``、``private`` 等属性控制挂载变化在 Namespace 之间怎样传播。新建 Mount Namespace 后若未处理传播关系，容器内 Mount 事件仍可能影响宿主或其它视图。

Network Namespace 是独立网络栈实例
   ``struct net`` 组织设备、地址、路由、端口空间、Netfilter、Conntrack 和网络 Sysctl。已有 Socket 绑定创建时的 Network Namespace，Task 后续 ``setns`` 不会迁移这些 Socket。

User Namespace 定义身份映射与能力范围
   ``uid_map``、``gid_map`` 把子 Namespace 的 ID 区间映射到父级；``kuid_t``、``kgid_t`` 在内核中保存可转换身份。容器内 UID 0 不等于宿主 Initial User Namespace 的 Root。

Capability 必须结合目标对象所有者解释
   ``ns_capable()`` 一类检查同时考虑调用 Credential 所在 User Namespace 与目标对象由哪个 User Namespace 管理。子层全部 Capability 只在相应范围内有效。

IPC、UTS 与 Time 隔离不同资源
   IPC Namespace 管 System V IPC 与 POSIX Message Queue；UTS Namespace 管 Hostname 和 NIS Domain；Time Namespace 管部分单调时钟和启动时间偏移。它们不替代文件、网络或调度隔离。

容器环境来自多种视图的有序组合
   PID、Mount、Network、User、IPC、UTS、Time 等对象彼此独立。Runtime 需要按权限和依赖顺序组合它们，并可显式选择共享某一种视图。

关键路径
--------

PID 编号解析：

::

   task_struct
   → struct pid 保存多层 upid
   → 观察者所在 pid_namespace 选择对应编号
   → Signal / Wait / Proc 按该编号查找
   → 同一 Task 在宿主与容器显示不同 PID

容器 Rootfs 视图：

::

   创建 Mount Namespace
   → 调整 Root Propagation
   → 准备 Overlay / Bind Rootfs
   → 挂载匹配的 procfs、sysfs、devtmpfs/tmpfs
   → pivot_root 或等价根切换
   → 卸载旧根并清理旧引用

容器网络与身份：

::

   创建 Network 与 User Namespace
   → 宿主侧写入 UID/GID Mapping
   → 创建并移动 Veth 端点
   → 配置 lo、地址、路由与过滤
   → 以映射后的 Credential 进入目标环境
   → 资源访问执行 namespace-aware 权限检查

概念辨析
--------

* ``task_struct`` 与 PID 数字：Task 是执行实体；PID 是该实体在特定 PID Namespace 中的名字。
* Mount Namespace 与文件副本：Mount 隔离路径关系，底层文件系统对象和缓存可以共享。
* Network Namespace 与网络可达：独立网络栈只建立冲突域，通信仍需设备、地址、路由和策略。
* 容器内 Root 与宿主 Root：子 User Namespace 的 UID 0 受 ID Mapping、Capability 范围和目标对象所有者约束。
* UTS Hostname 与网络身份：Hostname 是标识字段，不决定 DNS、IP 地址或外部认证身份。

本章结论
--------

每种 Namespace 只隔离一种资源视图。容器不是一台复制出来的内核机器，而是多种编号、挂载、网络、身份与时间视图按依赖关系组合后的 Task 环境。
