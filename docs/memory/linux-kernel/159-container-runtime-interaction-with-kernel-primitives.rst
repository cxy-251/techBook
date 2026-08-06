第159章：Container Runtime 与内核原语的交互
==========================================

核心知识点
----------

内核没有单一 Container 对象
   容器是 Runtime 将 Task、Namespace、Mount、Cgroup、Credential、Capability、LSM、Seccomp 与文件描述符按顺序装配出的运行环境。

OCI 配置只是用户态意图
   内核真正接收的是 ``clone3``、``unshare``、``setns``、Mount、Cgroupfs、Credential 和 ``seccomp`` 等操作。配置是否生效必须回到真实对象关系验证。

Runtime 依赖父子进程协作
   宿主侧父进程负责 Cgroup、UID/GID Mapping、网络和监督，容器 Init 在目标 Namespace 内完成 Rootfs、Credential 与 ``execve``。两者通过 Pipe、Socketpair 或 Pidfd 建立阶段同步。

环境装配必须遵守依赖顺序
   先建立 Namespace 和资源归属，再准备 Rootfs 与网络，随后收紧 Credential、Capability、LSM 和 Seccomp，最后执行目标程序。过早降权会阻断后续初始化。

Rootfs 是 Mount Tree，不只是目录
   Runtime 需要在独立 Mount Namespace 中处理传播属性、Bind/Overlay 关系、特殊文件系统和旧根引用。``chroot`` 只改变路径根，不能替代完整挂载树隔离。

Cgroup 归属应早于业务初始化
   CPU、内存、I/O 和 PIDs 策略只有在目标 Task 进入对应 Cgroup 后才生效。若在 ``execve`` 后迁移，程序早期分配和线程创建会落在错误计费边界。

User Namespace 与 Credential 分阶段建立
   宿主侧写入 ``uid_map``、``gid_map`` 后，容器内 UID/GID 才有明确父级映射。Runtime 随后设置 Groups、Capability 各集合、Securebits 与 ``no_new_privs``。

LSM、Seccomp 与设备访问是独立安全层
   LSM 决定对象级策略，Seccomp 限制系统调用入口，Capability 表达特权范围，设备访问还涉及节点、Major/Minor、Cgroup/BPF Policy 和驱动权限。任一层都不能替代其它层。

继承 fd 会穿过 Rootfs 与 Namespace 边界
   文件描述符直接引用内核对象，切换根目录或 Namespace 不会自动使其失效。Runtime 必须关闭非预期 fd，并防止旧 Root、设备或宿主资源通过句柄泄漏。

容器退出与资源删除是不同阶段
   业务 Task 退出后，Shim、Cgroup、Mount、Veth、Namespace fd 和 Runtime State 仍可能存在。可靠 Runtime 必须为每个创建阶段提供逆序回滚和可重复删除。

关键路径
--------

容器创建：

::

   解析 OCI 配置
   → 准备 Bundle 与 Rootfs
   → 创建 Runtime Parent 和 Container Init
   → 创建或加入 Namespace
   → 建立 UID/GID Mapping 与 Cgroup 归属
   → 装配 Mount Tree 和网络
   → 设置 Credential、LSM、no_new_privs、Seccomp
   → 关闭内部 fd
   → execve 目标程序

Rootfs 切换：

::

   创建 Mount Namespace
   → 设置 Root Propagation
   → 将 Rootfs 变成独立 Mount Point
   → 挂载 procfs、sysfs、devpts、tmpfs 等
   → pivot_root 到新根
   → 卸载旧根
   → 清理 CWD、Root fd 与继承引用

权限收紧：

::

   完成 Mount、Network、Device 初始化
   → 设置 UID/GID 与 Supplementary Groups
   → 计算 Capability 集合
   → 应用 LSM Label/Profile
   → 设置 no_new_privs
   → 安装 Seccomp Filter
   → 进入用户程序

失败回滚：

::

   记录最后成功阶段
   → 终止未完成的 Init Task
   → 撤销 Veth、Mount 与外部连接
   → 迁移/结束 Cgroup 成员并删除子树
   → 关闭 Namespace、Pidfd、Console fd
   → 删除 Runtime State
   → 验证再次创建与删除可重复

概念辨析
--------

* OCI 配置与内核状态：前者表达期望；系统调用结果、Procfs、Cgroupfs 和对象关系才证明实际状态。
* Image 与 Container：Image 提供文件系统内容；Container 是运行 Task 与内核资源组合。
* ``chroot`` 与 Mount Namespace：``chroot`` 只改变路径根；Mount Namespace 与 ``pivot_root`` 管完整挂载视图和旧根收束。
* Capability 与 Seccomp：Capability 控制特权操作范围；Seccomp 控制允许进入哪些系统调用。
* 进程退出与容器删除：进程结束不自动清理 Cgroup、Mount、网络和 Runtime 持有的外部对象。

本章结论
--------

Container Runtime 的本质是把高层配置翻译为有序、可验证、可回滚的内核对象装配。先建立视图和资源边界，再收紧权限，最后执行程序并保证退出路径完整闭合。
