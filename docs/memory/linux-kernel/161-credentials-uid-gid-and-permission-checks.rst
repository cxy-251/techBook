第161章：Credentials、UID/GID 与权限检查
========================================

核心知识点
----------

``struct cred`` 描述操作主体
   内核权限判断的起点不是进程名或一个 UID 数字，而是当前 Task 引用的 Credential 对象。它集中保存 UID/GID、补充组、Capability、User Namespace、Keyring 与 LSM 私有状态。

``cred`` 与 ``real_cred`` 表达不同角色
   ``cred`` 通常表示当前操作使用的主观身份，``real_cred`` 表示 Task 作为被观察对象时的客观身份。二者多数时间相同，受控身份代理路径中可以不同。

Credential 使用复制后发布模型
   已发布的 ``cred`` 不能被并发原地修改。身份变更通常执行 ``prepare_creds()``、修改私有副本、验证字段，再由 ``commit_creds()`` 原子替换旧引用；失败路径必须撤销新对象。

UID/GID 具有多组语义
   Real ID 表示基本归属，Effective ID 参与一般特权语义，Saved ID 支持受控恢复，FSUID/FSGID 主要服务 VFS 访问判断。补充组通过 ``group_info`` 参与 Group 与 ACL 匹配。

内核 ID 必须结合 User Namespace
   ``kuid_t``、``kgid_t`` 表达内核内部身份，用户可见整数需要相对某个 User Namespace 映射。容器内 UID 0 可以映射为宿主普通 UID，不能直接推导宿主全局权力。

权限检查发生在真实对象访问点
   系统调用名只表明入口。最终检查对象可能是 Mount、Dentry、Inode、``struct file``、Task、Socket、IPC、Key、BPF 或设备对象，每类操作都有自己的访问掩码与检查链。

VFS 先把路径解析为对象
   同一字符串在不同 Mount Namespace 中可以指向不同对象。权限结论应绑定 Mount、Dentry、Inode、对象类型与打开实例，不能只绑定用户看到的路径名。

DAC 组合 Owner、Group、Mode 与 ACL
   普通权限位按 Owner、Group、Other 选择对应集合，ACL 可扩展匹配规则。只读 Mount、不可变标志、对象类型和文件系统状态还可能在 DAC 之外独立拒绝操作。

Capability 是范围明确的附加授权
   某些路径可用特定 Capability 绕过部分 DAC，但授权必须在目标 User Namespace 范围内成立。一个 Capability 只覆盖规定操作族，不自动绕过所有对象状态与安全策略。

LSM 可以继续收紧结果
   DAC 与 Capability 放行后，SELinux、AppArmor、Landlock 等 LSM 仍可在对象 Hook 上拒绝。Seccomp 则位于系统调用入口，属于另一层接口面限制。

``file->f_cred`` 保存打开者身份快照
   ``struct file`` 可保存打开时的 Credential 引用。fd 被继承或通过 ``SCM_RIGHTS`` 传递后，打开实例仍是同一个对象；后续操作究竟使用 ``f_cred`` 还是当前 Credential，必须按具体接口判断。

``execve()`` 是身份重算边界
   Setuid/Setgid、File Capability、``no_new_privs``、Ptrace 状态、Securebits、User Namespace 与 LSM 共同决定新程序的 Credential。执行成功后，后续检查只读取新身份。

引用与 RCU 保护生命周期
   Credential 可被 Task、File 和异步工作长期持有。RCU 保护短期并发读取，显式引用保护跨越调度或异步边界的长期使用；二者不能互换。

关键路径
--------

文件打开权限链：

::

   openat/openat2
   → 在当前 Mount Namespace 解析路径
   → 得到 Mount + Dentry + Inode
   → 检查对象类型、Mount 与 Inode 状态
   → 读取 FSUID/FSGID 与补充组
   → 执行 Mode/ACL/DAC
   → 检查相关 Capability
   → 执行 LSM Hook
   → 创建 struct file 并保存 f_cred
   → 安装 fd

Credential 更新：

::

   current 持有旧 cred
   → prepare_creds 创建私有副本
   → 修改 ID、Groups、Capability 与安全状态
   → 验证映射和引用
   → commit_creds 发布新指针
   → 旧对象经引用计数与 RCU 延迟释放

fd 跨进程传递：

::

   Task A 以 Credential A 打开对象
   → struct file 保存打开实例与 f_cred
   → fd 被继承或发送给 Task B
   → Task B 获得同一 struct file 的新引用
   → 后续操作按接口使用 f_cred 或 current cred
   → 最后一个 file 引用归零后释放

权限拒绝诊断：

::

   固定宿主 PID 与失败系统调用
   → 记录 cred、real_cred、User Namespace 与 Groups
   → 解析真实 Mount/Inode/File
   → 检查 Mode、ACL、特殊标志与对象状态
   → 定位 Capability 与 LSM 检查点
   → 对齐 Errno、Audit 与同一时间窗口

概念辨析
--------

* ``cred`` 与 ``real_cred``：前者描述当前动作主体，后者描述 Task 作为目标对象时的身份。
* Effective ID 与 FS ID：Effective ID 服务一般特权语义；FSUID/FSGID 是 VFS 常用身份。
* 路径名与内核对象：路径是解析输入，权限判断最终作用于 Mount、Inode、File 等对象。
* DAC 与 Capability：DAC按对象所有权分配权限；Capability 为特定操作提供额外授权。
* RCU 与显式引用：RCU保护短期读窗口；引用计数保护跨异步边界的对象存活。

本章结论
--------

Linux 权限判断是“稳定主体身份对真实内核对象执行具体动作”的计算；UID/GID、DAC、Capability、User Namespace 与 LSM 必须放在同一对象路径中解释。