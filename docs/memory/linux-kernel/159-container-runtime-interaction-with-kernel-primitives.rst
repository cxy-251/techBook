第159章：Container Runtime 与内核原语的交互
==========================================

本章必须记住
------------

#. Linux 内核没有一个名为“Container”的单一对象；容器是 Runtime 把 Task、Namespace、Mount、Cgroup、Credential、Capability、LSM 和 Seccomp 按顺序装配出的进程环境。
#. OCI 配置是用户态声明；内核真正接收的是 ``clone/clone3``、``unshare``、``setns``、``mount``、``pivot_root``、Cgroupfs 写入、Credential 变更和 ``seccomp`` 等操作。
#. Runtime 的核心职责不是简单执行命令，而是把高层配置转换成有依赖、有同步点、有回滚边界的系统调用序列。
#. 容器创建必须先明确哪些 Namespace 新建、哪些加入既有对象、哪些资源和设备共享。
#. ``clone3()``/``clone()`` 可在创建容器 Init Task 时建立部分 Namespace；其它视图可由子进程执行 ``unshare`` 或 ``setns`` 完成。
#. Runtime 常使用父进程与容器 Init 子进程协作，因为部分配置只能在宿主视角完成，部分操作必须在目标 Namespace 内完成。
#. 父子进程之间通常通过 Pipe、Socketpair、Pidfd 或专用协议交换状态，确保每个阶段按顺序继续。
#. 创建 Task 成功不表示容器已经可运行；Rootfs、Cgroup、Credential、Network、Seccomp 和文件描述符清理可能尚未完成。
#. 目标程序的 ``execve`` 是环境装配完成后的边界，不是容器创建的起点。
#. Namespace 决定进程看到什么，Mount/Rootfs 决定路径解析，Cgroup 决定资源边界，Credential/Capability/LSM 决定对象访问，Seccomp 决定可发起的系统调用面。
#. 会影响后续配置能力的限制通常靠后安装；例如过早丢弃 Capability 或安装 Seccomp 可能让 Runtime 无法完成 Mount、UID Mapping 或设备设置。
#. 会影响目标程序早期资源使用的 Cgroup 归属应在 ``execve`` 前完成。
#. 容器配置成功写入 Cgroup 文件，但目标 PID 未进入对应 Cgroup，资源策略仍不会作用到该进程。
#. 在支持的内核中，``clone3(CLONE_INTO_CGROUP)`` 可减少“先创建后迁移”的窗口，具体 Runtime 使用和权限具有版本边界。
#. Mount Namespace 必须在修改容器挂载树前建立，否则 Mount 操作可能污染宿主视图。
#. 新 Mount Namespace 通常继承一份挂载关系，Runtime 还要处理 Root Propagation，避免 Shared Mount 事件向宿主传播。
#. 容器 Rootfs 内容可以来自 OverlayFS、Snapshotter、Bind Mount 或独立文件系统；Low-level Runtime 通常接收一个已准备好的 Root Path。
#. Rootfs 目录必须成为满足要求的 Mount Point，才能可靠执行 ``pivot_root`` 或等价根切换。
#. ``pivot_root`` 把当前 Mount Namespace 的根切换到新 Root，并临时保留旧 Root 供后续卸载。
#. ``chroot`` 只改变路径查找根，不能替代完整 Mount Namespace、Propagation 处理和旧根清理。
#. 安全 Rootfs 主线通常是：建立 Mount Namespace → 设为 Private/Slave → Bind Rootfs 为 Mount Point → 挂载特殊 FS → 切换根 → 卸载旧根。
#. ``/proc`` 应与目标 PID Namespace 对齐重新挂载，否则容器内进程工具可能看到错误进程视图。
#. ``/sys``、``/dev``、``devpts``、``tmpfs``、``/dev/shm`` 等需要按容器 ABI、权限和安全策略单独装配。
#. Bind Mount 不复制文件，容器与宿主可能访问同一个底层 Inode；Read-only、Recursive Read-only 和 Propagation 要分别配置。
#. OverlayFS Rootfs 的 Lower、Upper、Work 与 Merged 视图属于文件系统层；Mount Namespace 决定目标进程看到哪一个 Merged Path。
#. Rootfs 切换后仍需检查 CWD、Root fd、继承 fd 和旧 Mount 引用，避免宿主路径通过已有句柄泄漏。
#. Runtime 应按配置关闭或重映射不需要的文件描述符，只保留 Stdin/Stdout/Stderr、Console、Notify 或显式 Preserve fd。
#. 文件描述符是对内核对象的引用；Rootfs 与 Namespace 隔离不会自动使继承 fd 失效。
#. PID Namespace 的 Init 进程必须承担 Reaping 和 Signal 转发职责，普通业务进程直接作为 PID 1 时可能不能正确回收孤儿进程。
#. Runtime/Shim 常保留宿主侧监督进程，用于等待容器 Init、转发 Signal、收集退出状态和处理 I/O。
#. Network Namespace 创建只是得到独立网络栈；地址、Route、Veth、Loopback、DNS 文件和过滤规则通常由 Runtime 或上层网络插件配置。
#. Veth 一端移动进容器 Net Namespace 后，容器内和宿主端必须分别配置 Link、MTU、Queue 和 Route。
#. Network 配置可以在目标进程执行前由父进程操作目标 Namespace，也可以通过 Helper/Hook 完成，具体 Runtime 实现不同。
#. User Namespace 需要先创建对象，再由有权限的宿主侧进程写入 ``uid_map``、``gid_map``，随后容器内 Credential 才有明确宿主映射。
#. ``setgroups`` 限制、Subuid/Subgid 分配和 ID Mapping 写入顺序具有严格规则。
#. Rootless Runtime 依赖 User Namespace、FUSE/Idmapped Mount、Slirp/Pasta 等替代路径时，功能和性能边界与特权容器不同。
#. Idmapped Mount 可以改变 Mount 视图中的 ID 解释，不等同于修改文件 Inode 的真实所有者，支持范围具有版本边界。
#. Runtime 最终要设置 UID、GID、Supplementary Groups、Capability 集合、Securebits 和 ``no_new_privs``。
#. Capability 的 Permitted、Effective、Inheritable、Bounding、Ambient 集合在 ``execve`` 时按规则重新计算，不能只看一个 Effective 位图。
#. ``no_new_privs`` 建立后，后续 ``execve`` 不能通过 Setuid/File Capability 获得新的权限。
#. Runtime 常先完成需要特权的初始化，再 Drop Bounding/Effective Capability，最后执行目标程序。
#. Capability Drop 不等于所有权限消失；文件所有权、User Namespace 范围、Device fd 和 LSM 标签仍可能允许操作。
#. LSM 标签或 Profile 由 SELinux、AppArmor、Smack 等机制应用，精确配置入口取决于系统和 Runtime。
#. Seccomp Filter 限制系统调用入口，不负责文件对象级权限，也不替代 LSM 或 Capability。
#. 安装 Seccomp 前需要确保 Runtime 不再需要被禁止的系统调用。
#. ``no_new_privs`` 常作为非特权安装 Seccomp Filter 的前提之一，具体权限规则以目标内核为准。
#. Seccomp Filter 在目标程序执行后继续继承，并可按 Thread/TSYNC 等规则应用，精确行为具有版本边界。
#. Seccomp 拒绝可能表现为 ``EPERM``、指定 Errno、Signal、Kill、Trap、Log 或 User Notification，不能统一解释成“权限不足”。
#. Device Access 由 Device Node、Mount、Cgroup Device Policy（v1 或 BPF-based v2 管理）、Capability、LSM 和驱动权限共同决定。
#. 只在容器内创建 ``/dev`` 节点不表示设备可访问；需要正确 Major/Minor、底层设备、策略和权限。
#. Cgroup v2 的资源限制通常由 Systemd、Containerd、CRI-O、Docker 或 Runtime 通过 Cgroupfs/Systemd API 设置。
#. Runtime 配置中的 CPU 数字、Memory Limit 或 PIDs Limit 必须回读 Cgroupfs 才能证明实际生效。
#. 容器进程应在目标程序初始化之前进入正确 Cgroup，避免早期内存、线程和 I/O 不受限制。
#. Cgroup 层级中的父级限制仍会约束容器，即使容器自身文件显示 ``max``。
#. OCI Hook 是用户态扩展点，不是内核对象；不同 Hook 执行在不同 Namespace、生命周期阶段和权限语境。
#. Hook 失败是否阻止容器创建、是否需要回滚，取决于 OCI 阶段和 Runtime 策略。
#. Prestart/CreateRuntime/CreateContainer/StartContainer/Poststop 等 Hook 名称和阶段以 OCI 规范版本为准。
#. Runtime 必须为每个成功阶段建立逆序回滚：Cgroup、Mount、Veth、Namespace fd、Console、Pidfd 和临时文件都需释放。
#. 创建失败不应留下孤立 Veth、残留 Cgroup、挂载点、Pinned Namespace 或仍运行的 Init Task。
#. Kill 一个容器主进程不一定自动清理其 Cgroup 和外部资源；Shim/Daemon/GC 负责用户态生命周期收束。
#. 容器退出与删除是不同阶段：退出表示目标 Task 停止，删除才撤销 Bundle、Cgroup、Mount、Network 和 Runtime State。
#. Pause 常通过 Cgroup Freezer 或 Signal/Runtime 协议实现，不等于进程退出或资源释放。
#. Checkpoint/Restore 会保存和重建 Task、Memory、fd、Namespace 与网络状态，属于更复杂的版本敏感路径。
#. OCI Runtime Spec 描述配置和生命周期合同；runc、crun 等是不同实现，函数名和内部进程结构不能作为稳定内核接口。
#. Container Manager、CRI、Runtime、Shim、Low-level OCI Runtime 和 Kernel 是不同层级。
#. Kubernetes Pod Sandbox/CRI 配置最终仍要拆成 Namespace、Cgroup、Mount、Network 和 Security 原语。
#. Image 不等于运行容器；Image 提供 Rootfs 内容和元数据，Runtime 创建真实 Task 与内核对象关系。
#. Container ID 不是内核 Task、Cgroup 或 Namespace 的永久 ID，管理面必须维护映射。
#. 排查“容器未启动”时应定位失败发生在 Task 创建、Namespace、Rootfs、Cgroup、Credential、Seccomp 还是 Exec 阶段。
#. 排查“容器启动但隔离异常”时应从目标宿主 PID 回读 ``/proc/<pid>/ns``、``mountinfo``、``uid_map`` 和 Cgroup 路径。
#. 排查“限制未生效”时不能只看 OCI 配置，要检查目标 PID 成员关系和所有祖先 Cgroup 限制。
#. 排查“容器内 Root 仍无权限”时应检查 User Namespace Mapping、Capability 集合、``no_new_privs``、LSM、Seccomp 和目标对象所有者。
#. 排查“重启后路径泄漏”时应检查 Mount Propagation、旧 Root fd、Bind Mount 和 Runtime GC。
#. Runtime 日志应与内核 Audit、Dmesg、Cgroup Events、Seccomp 和 LSM 拒绝证据对齐。
#. 安全创建顺序不是绝对固定函数表，但稳定依赖是：先建立视图和资源归属，再收紧权限，最后 ``execve``。
#. 精确 OCI 字段、Runtime 实现、Cgroup 模式和系统调用支持具有版本差异。
#. 稳定源码阅读顺序是：OCI Config → Runtime Parent/Init 协议 → Task/Namespace → Rootfs → Cgroup → Cred/LSM/Seccomp → Exec → Teardown。

必背路径
--------

容器创建主线：

::

   读取 OCI Config
   → 准备 Bundle / Rootfs
   → 创建 Runtime Parent 与 Container Init Task
   → 创建或加入 Namespace
   → 配置 User ID Mapping
   → 进入目标 Cgroup 并写资源限制
   → 准备 Mount Tree 与 Rootfs
   → 配置 Network、Hostname 和 IPC
   → 设置 Credential、Capability 与 LSM
   → 安装 no_new_privs / Seccomp
   → 关闭内部 fd
   → execve 目标程序

Rootfs 装配：

::

   创建 Mount Namespace
   → 将 Root Propagation 设为 Private/Slave
   → Bind Mount Rootfs 使其成为 Mount Point
   → 挂载 /proc、/sys、/dev、devpts、tmpfs
   → 应用 Read-only 和 Masked Path
   → pivot_root 到新根
   → 卸载旧根并清理 fd/CWD

Cgroup 放置：

::

   创建目标 Cgroup
   → 父级启用所需 Controller
   → 写 cpu/memory/io/pids/cpuset 策略
   → 创建时直接加入或写 cgroup.procs
   → 确认目标 PID 实际成员关系
   → execve 前开始统计和限制

权限收紧：

::

   完成需要特权的 Mount/Network/Device 初始化
   → 设置 UID/GID 与 Supplementary Groups
   → 设置 Capability Bounding/Permitted/Effective/Ambient
   → 应用 LSM Label/Profile
   → 设置 no_new_privs
   → 安装 Seccomp Filter
   → execve 用户程序

失败回滚：

::

   记录最后成功阶段
   → 终止未完成的 Init Task
   → Detach Network / 删除 Veth
   → 卸载临时 Mount 与 Rootfs
   → 移除 Cgroup 和成员
   → 关闭 Namespace/Pidfd/Console fd
   → 删除 Runtime State
   → 验证无孤立资源

必须区分
--------

* OCI 配置与内核状态：配置是用户态意图；只有系统调用、Cgroupfs 和对象关系能证明实际生效。
* Image 与 Container：Image 提供文件系统内容；Container 是运行时装配后的 Task 与内核资源关系。
* ``chroot`` 与 Mount Namespace/``pivot_root``：Chroot 只改变路径根；完整容器 Rootfs 还需要独立挂载树、传播控制和旧根清理。
* Capability 与 Seccomp：Capability 控制特权操作授权；Seccomp 限制系统调用入口，两者作用层不同。
* 容器退出与删除：退出只表示 Task 停止；删除还要清理 Cgroup、Mount、Network、Namespace 引用和 Runtime State。

一句话结论
----------

Container Runtime 的真实工作是把 OCI 意图翻译成有序的内核对象装配：先建立视图和资源边界，再收紧权限，最后执行用户程序并保证失败可逆。
