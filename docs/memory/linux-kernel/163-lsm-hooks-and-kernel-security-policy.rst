第163章：LSM Hook 与内核安全策略
================================

核心知识点
----------

LSM 把策略放到真实对象路径
   Linux Security Module Framework 在文件、进程、Socket、IPC、Key、BPF、模块和 Mount 等内核对象的访问点调用安全 Hook，使策略基于主体、目标与操作语义作出决定。

``security_*`` 是统一调用边界
   宿主子系统通过 ``security_inode_*``、``security_file_*``、``security_socket_*`` 等包装入口调用当前安全栈。内核代码不应绕过框架直接依赖某个具体 LSM。

Hook 不等同于系统调用过滤
   同一系统调用可能经过多个 Path、Inode、File 或 Task Hook；同一对象也可能在打开、读写、映射、ioctl 与释放阶段再次检查。Seccomp 则位于系统调用入口，信息边界更早。

策略基于内核对象而非用户字符串
   用户提供路径后，VFS 最终得到 Mount、Dentry、Inode 或 ``struct file``。硬链接、重命名、Bind Mount、OverlayFS 和 fd 传递说明安全结论不能只依赖最初字符串。

DAC 与 Capability 是基础权限层
   对象状态、DAC 与 Capability 通常先建立基础访问结果，LSM 可以继续拒绝。LSM 不能把前层已经拒绝的操作改为允许。

多个 LSM 可以堆叠
   SELinux、AppArmor、Landlock、Yama 等可同时参与 Hook 链。授权类路径中，任一实际参与模块拒绝，最终访问通常失败；修复一个模块后仍可能被另一个模块拦截。

Security Blob 保存模块私有状态
   LSM 可在 Credential、Inode、File、Superblock、Socket、IPC、Key 与 BPF 对象上附着标签、Profile、Ruleset 或缓存状态。Blob 生命周期必须跟随宿主对象的创建、复制、发布和释放。

SELinux 使用标签与对象类别
   其稳定模型是 Subject Context、Target Context、Object Class 与 Requested Permission。文件标签常来自 xattr，AVC 用于缓存访问决策，Audit 中的拒绝记录用于还原策略矩阵。

AppArmor 以 Task Profile 为中心
   AppArmor 主要把当前 Profile、路径或对象和请求操作连接起来。Mount Namespace、路径重命名、Bind Mount 与执行 Profile Transition 都会改变策略解释边界。

Landlock 是进程主动施加的单向约束
   非特权进程可以建立 Ruleset 并限制自己及后代。规则只会继续收紧，已施加的限制不能由普通进程重新放宽。

Hook 位置必须在信息与副作用之间平衡
   Hook 太早可能缺少真实目标对象，太晚则可能已经产生不可回滚副作用。拒绝路径必须在对象发布、资源申请和用户可见状态之间正确回滚。

策略缓存不改变授权语义
   AVC、Profile Cache 与静态分支可降低热路径成本。策略更新时必须使旧缓存失效，并明确运行中 Task、已打开 File 与新对象的生效边界。

LSM 拒绝需要运行证据
   ``EACCES`` 或 ``EPERM`` 不能指出拒绝模块。诊断要确认活跃 LSM、主体 Context/Profile、目标对象 Label、具体 Hook/Operation，并与同一 Audit Event 对齐。

关键路径
--------

文件访问安全链：

::

   open/read/write/mmap
   → VFS 得到 Mount、Dentry、Inode 或 File
   → 检查对象状态、DAC 与 Capability
   → 调用对应 security_path/inode/file Hook
   → 遍历活跃 LSM Hook 链
   → 模块读取 Subject 与 Object Security State
   → 任一拒绝则返回 Errno 并可生成 Audit
   → 全部放行后继续对象操作

Security Blob 生命周期：

::

   创建 Cred/Inode/File/Socket 等宿主对象
   → LSM 分配或初始化 Blob
   → 从 xattr、父对象、Profile 或 Ruleset 建立状态
   → Hook 在访问时读取 Blob
   → 对象复制或发布时转移安全状态
   → 最后引用归零
   → LSM 释放 Blob

Stacking 决策：

::

   基础对象检查通过
   → LSM A 返回允许
   → LSM B 返回允许
   → LSM C 返回拒绝
   → 框架返回拒绝
   → Audit 记录实际拒绝者与对象语义

拒绝诊断：

::

   strace 固定失败系统调用与 Errno
   → 读取 /sys/kernel/security/lsm
   → 记录主体 Credential 与 Context/Profile
   → 解析目标 Mount、Inode、Label 与对象类别
   → 查询同一时间窗口 Audit/Kernel Log
   → 定位具体 Hook、Permission 与策略规则
   → 做最小标签或策略修复

概念辨析
--------

* LSM 与 Seccomp：LSM在对象访问点授权；Seccomp在系统调用入口裁剪接口面。
* Path Hook 与 Inode/File Hook：Path包含当前挂载关系，Inode/File更接近持久对象与打开实例。
* DAC 允许与最终允许：DAC只是基础层，Capability、LSM 与对象状态仍可改变结果。
* Security Blob 与用户 ABI：Blob是内核模块私有状态，不能由普通代码按固定布局解释。
* Permissive 与无策略：Permissive通常记录本应拒绝的决策，策略和标签仍在运行。

本章结论
--------

LSM 的核心是让强制策略跟随真实内核对象与操作语义执行；最终结果由全部活跃安全模块共同决定，诊断必须还原主体、对象、Hook 和策略版本，而不是只看路径字符串或 Errno。