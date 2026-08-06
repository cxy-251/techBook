第161章：Credentials、UID/GID 与权限检查
========================================

本章必须记住
------------

#. Linux 权限判断的稳定起点是：哪一组 Credentials 正在对哪个内核对象执行什么动作。
#. 用户态看到 UID、GID、路径、``EACCES`` 或 ``EPERM``；内核实际读取的是主体 ``struct cred``、目标对象状态、访问掩码和安全 Hook。
#. ``struct cred`` 是任务安全身份的核心引用计数对象，集中保存 UID/GID、补充组、Capability、User Namespace、Keyring 和 LSM 私有状态。
#. ``task_struct`` 通常同时持有 ``real_cred`` 与 ``cred``。
#. ``real_cred`` 表示 Task 作为被观察或被访问对象时的客观身份。
#. ``cred`` 表示 Task 作为当前动作发起者时的主观身份。
#. 两个指针通常相同，但内核可以通过受控的 Credential Override 临时改变主观身份。
#. 读权限源码时必须先判断当前 Task 是主体还是目标对象，不能机械读取同一个 Credential 指针。
#. ``current_cred()``、``current_uid()``、``current_euid()`` 等 Helper 用于取得当前主体身份，精确接口随版本演进。
#. Credential 是不可原地随意修改的共享对象；修改通常采用 Prepare → Modify Private Copy → Commit 的 Copy-and-replace 模型。
#. ``prepare_creds()`` 创建可修改的新 Credential 副本并取得内部对象引用。
#. 修改者只能在新 Credential 尚未发布时改变其字段。
#. ``commit_creds()`` 把新 Credential 发布给当前 Task，并按引用与 RCU 规则撤销旧对象。
#. 失败路径必须调用 ``abort_creds()`` 或对应清理，避免引用泄漏。
#. 读者不能缓存裸 ``current->cred`` 指针并跨越可能切换 Credential 的边界；需要长期持有时应使用正式引用接口。
#. ``get_cred()``/``put_cred()`` 管理 Credential 引用；精确封装应以目标内核版本为准。
#. Credential 最终释放还可能递归释放 ``group_info``、User、User Namespace、Keyring 和 LSM Security Blob。
#. Credential 发布常由 RCU 保护并发读取；RCU 只保护读侧观察窗口，不替代显式长期引用。
#. Real UID/GID 表示 Task 的基本归属身份，位于 ``uid``/``gid`` 一类字段。
#. Effective UID/GID 表示当前权限生效身份，位于 ``euid``/``egid`` 一类字段。
#. Saved UID/GID 保存受控身份切换可恢复的状态，位于 ``suid``/``sgid`` 一类字段。
#. Filesystem UID/GID 是 VFS 文件权限检查使用的重要身份，位于 ``fsuid``/``fsgid`` 一类字段。
#. Supplementary Groups 由 ``group_info`` 表示，参与目标对象 Group 权限或 ACL 匹配。
#. “进程显示为 root”不等于本次文件访问一定使用 FSUID 0。
#. Setuid、Service Manager、User Namespace、Credential Override 和 ``setfsuid`` 都可能让多个身份字段不同。
#. Real ID 主要回答 Task 属于谁；Effective ID 主要回答当前特权身份；Saved ID 主要约束后续恢复；FS ID 主要参与文件系统访问。
#. 文件访问检查不能只看 ``euid``，应读取 ``fsuid``、``fsgid``、Supplementary Groups、Capability 与目标 Inode。
#. ``struct file`` 的 ``f_cred`` 保存打开文件时取得的 Credential 引用。
#. ``file->f_cred`` 让后续某些操作使用打开者的安全身份快照，降低 fd 传递造成的 Confused Deputy 风险。
#. 文件描述符传给另一个进程后，``struct file`` 仍是同一个打开文件对象，``f_cred`` 不会自动改为接收者身份。
#. 具体后续操作使用 ``file->f_cred``、当前 Credential 或重新做对象检查，必须按对应子系统源码确认。
#. 权限结论发生在对象访问点，而不是只发生在系统调用入口。
#. 文件对象要结合 Path Lookup、Mount 状态、Inode 类型、Mode、ACL、Capability、Device Cgroup 和 LSM 判断。
#. 进程对象要结合 Signal、Ptrace、Credential 关系、PID Namespace 与 LSM 判断。
#. Socket、IPC、Key、BPF、Device 等对象各有自己的访问动作和安全检查入口。
#. 系统调用只负责把用户请求送入对象路径；``openat()`` 名称本身不足以说明最终检查顺序。
#. 普通打开路径常沿 Path Lookup → ``may_open``/对象状态检查 → ``inode_permission`` → 文件系统/DAC → Capability → LSM → 创建 ``struct file`` 推进。
#. 精确函数名和拆分随内核版本变化，但“对象状态 → DAC/Capability → LSM → 发布对象”是稳定读法。
#. DAC 是 Discretionary Access Control，主要围绕对象 Owner、Group、Mode、ACL 与主体 UID/GID/Groups。
#. 普通 Mode 位判断通常按 Owner、Group、Other 选择一组权限，不是把三组权限位相加。
#. ACL 可扩展普通 Mode 位，但仍属于文件系统对象访问语义的一部分。
#. Capability 可以在特定路径绕过或补充 DAC，例如 ``CAP_DAC_OVERRIDE`` 与 ``CAP_DAC_READ_SEARCH``。
#. Capability 检查具有具体动作边界，拥有某个 Capability 不表示自动绕过所有权限和所有对象状态。
#. LSM 可以在 DAC 和 Capability 允许后继续拒绝；普通文件所有者无法自行绕过强制策略。
#. 只读 Mount、Immutable/Append-only Inode、对象类型错误和文件系统状态可能在 DAC 之外先返回错误。
#. ``EROFS``、``EISDIR``、``ENOTDIR``、``ETXTBSY``、``EPERM`` 与 ``EACCES`` 代表不同失败层级，不能都归因于 Mode 位。
#. ``EACCES`` 常用于访问权限拒绝；``EPERM`` 常用于操作不允许或缺少特权，但具体 Errno 由访问点定义。
#. 用户态库可能改写、重试或压缩错误，诊断时应通过 ``strace`` 找到真实失败 Syscall 和 Errno。
#. Pathname 是用户态名字；内核权限对象通常是路径解析后的 Mount、Dentry、Inode 或 File。
#. Bind Mount、OverlayFS、Chroot、Mount Namespace 和 Rename 会让用户看到的路径与底层对象关系变化。
#. 同一路径字符串在不同 Mount Namespace 中可指向不同 Inode；同一个 Inode 也可经多个路径访问。
#. 安全判断应记录目标 Mount ID、Device、Inode、File Type 和 Namespace，而不是只记录字符串路径。
#. 打开成功只证明 Open 阶段通过；后续 ``read``、``write``、``mmap``、``ioctl``、``fcntl`` 仍可有独立检查。
#. 已打开 fd 可跨 Rename/Unlink 继续引用同一 ``struct file`` 和 Inode；路径名消失不等于访问对象立即消失。
#. Inode Mode 改变后，已打开 fd 的后续语义取决于操作是否重新检查，而不是一律撤销。
#. Exec 是 Credential 转换的关键边界，Setuid/Setgid Bit、File Capability、``no_new_privs``、LSM 和 Ptrace 状态都可能影响新 Credential。
#. Credential 修改必须在线程和进程语义下读取；Linux Credential 本质上是 Per-thread，但线程组通常共享一致身份约定。
#. 修改 UID/GID 或 Groups 时要检查多线程约束、用户态线程库同步和各 Task 的 Credential 发布。
#. ``setuid``、``setresuid``、``setfsuid`` 等接口具有不同状态变换规则，不能只按函数名猜测最终四组 UID。
#. Saved ID 是否允许恢复 Effective ID，需要按调用者当前权限和具体系统调用规则判断。
#. User Namespace 改变 Kernel UID/GID 的解释和 Capability 作用范围。
#. 内核内部常用 ``kuid_t``/``kgid_t`` 表示带 User Namespace 映射语义的 ID，而不是直接使用裸整数。
#. ``make_kuid``、``from_kuid`` 一类接口负责在 User Namespace 视图和内核 ID 之间转换，精确接口按版本确认。
#. 容器内 UID 0 可映射到宿主普通 UID；判断文件 Owner 时必须确认对象 ID 与主体 ID 在哪个 User Namespace 中解释。
#. 映射不存在时，用户态可能看到 Overflow ID，权限判断仍按内核映射结果执行。
#. Capability 也必须带 User Namespace 语境；``ns_capable()`` 一类检查回答主体是否在目标 User Namespace 范围拥有权力。
#. DAC 允许不表示 Capability 检查一定允许；Capability 允许也不表示 LSM 一定允许。
#. 权限检查链不是单一固定顺序覆盖所有对象，但排障时应逐层验证对象状态、DAC、Capability、LSM 和 Seccomp。
#. Seccomp 发生在 Syscall 入口面，可能在对象查找之前阻止请求；它和对象权限检查属于不同层级。
#. Audit 可把 Subject、Object、Operation、Errno 和 LSM/Seccomp 决策连接成运行证据。
#. ``/proc/<pid>/status`` 可观察 UID/GID、Groups、Capability 位图、``NoNewPrivs`` 和部分 Namespace PID 信息。
#. ``/proc/<pid>/loginuid``、Audit UID 与当前 UID 不同，前者用于追踪登录身份，不能替代当前 Credential。
#. ``stat``/``namei``/``getfacl`` 用于观察文件对象与路径权限；容器场景需在目标 Mount/User Namespace 中解释。
#. ``ls -l`` 只显示 Mode、Owner、Group 的一部分视图，不能显示全部 ACL、LSM Label、Mount Flag 和 Capability。
#. ``getcap`` 观察 File Capability；``getfattr`` 或 LSM 工具观察扩展属性；结果依文件系统和权限可见性。
#. SELinux/AppArmor 等拒绝通常需要查看 Audit 或内核日志，应用 ``EACCES`` 无法指出具体策略。
#. 权限问题排查第一步是固定宿主机 Task、失败 Syscall、目标对象和访问动作。
#. 第二步记录当前/打开时 Credential：UID/GID 四组字段、Supplementary Groups、Capability、User Namespace。
#. 第三步记录目标对象：Mount、Inode、Owner、Group、Mode、ACL、Label、只读与特殊标志。
#. 第四步按对象访问路径确认第一个拒绝层：对象状态、DAC、Capability、Device Policy、LSM、Seccomp。
#. 第五步用 Audit、Trace 或最小复现证明拒绝发生在该时间窗口。
#. 不应通过直接 ``chmod 777``、关闭 LSM 或赋予全部 Capability 来掩盖根因。
#. 修复应缩小到缺失的主体身份、对象标签、单一权限位或必要 Capability，并验证没有扩大其它攻击面。
#. Credential 泄漏会保留 User、Keyring、Groups 和 LSM 状态；错误引用释放会形成 Use-after-free。
#. 安全 Teardown 必须保证使用 Credential 的异步工作、File 和对象引用结束后再释放关联状态。
#. 精确 ``struct cred`` 字段、Helper、Hook 和 UID 转换规则具有版本差异。
#. 稳定源码阅读顺序是：Task Role → ``cred``/``real_cred`` → ID/Groups/Capability → Target Object → Access Mask → DAC/LSM → File Snapshot → Copy-and-commit。

必背路径
--------

文件打开权限链：

::

   用户调用 openat/openat2
   → 在当前 Mount Namespace 完成路径解析
   → 得到 Mount + Dentry + Inode
   → 检查对象类型、Mount 和 Inode 状态
   → 读取 current Credential 的 fsuid/fsgid/groups
   → 执行 Mode/ACL/DAC 判断
   → 检查相关 Capability 与 Device Policy
   → 执行 LSM Hook
   → 创建 struct file 并保存 f_cred
   → 返回 fd

Credential 更新：

::

   current 持有旧 struct cred
   → prepare_creds 创建私有副本
   → 修改 UID/GID/Groups/Capability/LSM 状态
   → 验证所有字段和引用
   → commit_creds 原子发布新指针
   → 旧 Credential 通过引用与 RCU 延迟释放

对象访问诊断：

::

   固定宿主 PID 与失败 Syscall
   → 记录 current Credential 和 User Namespace
   → 解析路径到真实 Mount/Inode
   → 读取 Mode、ACL、Owner、Label 与特殊状态
   → 对照访问动作找到 DAC/Capability/LSM 检查点
   → 对齐 Errno 与 Audit 记录

文件描述符身份：

::

   Task A 以 Credential A 打开对象
   → struct file 保存 f_cred=A
   → fd 通过 SCM_RIGHTS 或继承交给 Task B
   → Task B 使用同一 struct file
   → 后续操作按具体接口使用 f_cred、current cred 或重新检查
   → 不能假设身份自动变成 B

必须区分
--------

* ``cred`` 与 ``real_cred``：前者表示当前动作主体，后者表示 Task 作为目标对象时的客观身份。
* Effective ID 与 Filesystem ID：Effective ID 表示当前特权身份；VFS 普通权限检查重点读取 FSUID/FSGID。
* 路径名与内核对象：路径经过 Namespace、Mount 和 VFS 解析后才得到实际 Dentry/Inode/File。
* DAC 允许与最终允许：Capability、LSM、Mount 状态、Device Policy 和 Seccomp 仍可影响结果。
* 关闭 fd 与 Credential 释放：``struct file`` 持有的 ``f_cred`` 引用会随 File 生命周期结束，不由路径名或发送者进程退出直接决定。

一句话结论
----------

Linux 权限检查不是比较一个 UID 数字，而是用稳定 Credential 对象描述主体，再在真实内核对象访问点组合 DAC、Capability 与安全策略作出决定。
