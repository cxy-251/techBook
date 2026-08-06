第165章：Audit、攻击面与安全可观测性
===================================

核心知识点
----------

Audit 是安全事件证据层
   DAC、Capability、LSM 与 Seccomp 负责允许或拒绝，Linux Audit 负责记录进入审计路径的主体、对象、操作、结果与策略上下文。它不是安全策略本身，也不是普通应用日志。

一次事件通常由多条 Record 组成
   ``SYSCALL``、``PATH``、``CWD``、``EXECVE``、``AVC``、``SECCOMP`` 等记录可共享同一 Event ID。分析必须先聚合完整事件，再解释其中任意一行。

Subject 身份具有多个维度
   PID、PPID、Comm、Exe、UID/EUID、AUID、Credential、Capability、Namespace 与 LSM Context 共同描述主体。AUID 追踪登录来源，不等于当前有效 UID。

Object 身份不能只依赖路径
   路径受 Mount Namespace、OverlayFS、Bind Mount、Rename 与 Hard Link 影响。Device、Inode、对象类别、Label 和 Mount 关系更接近内核实际目标。

Syscall Number 必须结合 Architecture
   不同架构和兼容 ABI 使用不同编号。``exit`` 为负值时通常编码 ``-errno``，必须按该 ABI 解释，而不是把数字孤立展示。

LSM 与 Seccomp 记录语义不同
   SELinux AVC 关注 Subject/Target Context、Object Class 与 Requested Permission；Seccomp 记录关注 Architecture、Syscall、Action 与 Task。两者不能用同一权限模型解释。

Audit Rule 决定记录范围
   规则可以按 Architecture、Syscall、路径/目录、权限、UID/AUID、结果、对象属性和 Key 过滤。规则写入成功只证明配置被接受，不证明业务已经命中或日志已经持久化。

规则 Key 只是管理标签
   Key 便于查询和分组，不是事件或对象的稳定身份。可靠关联仍需要 Event ID、Boot ID、时间、Task、对象和部署 Generation。

没有日志不等于没有事件
   Audit 可能未启用、规则未匹配、Action 不产生日志、权限不可见，或内核 Backlog、Rate Limit、Auditd 与存储链发生丢失。

Backlog 与 Lost 是证据完整性指标
   内核队列满、Auditd 消费过慢、磁盘满、轮转失败或转发插件阻塞都会破坏证据链。生产系统必须监控 Lost、Backlog、Daemon 与存储状态。

攻击面是多层可达集合
   它包含系统调用入口、可见对象、Capability、设备、网络路径、全局资源与横向移动通道。缩小攻击面需要 Namespace、Cgroup、最小对象暴露、Capability、LSM、``no_new_privs`` 与 Seccomp 共同作用。

每种机制只覆盖一个维度
   Namespace 不限制资源，Cgroup 不隐藏对象，Seccomp 不理解路径，Capability 不表达业务对象策略，Audit 不执行阻断。完整沙箱来自互补边界，而不是单一开关。

策略和证据都必须带版本
   安全事件应关联内核、策略、容器镜像、可执行文件、配置与对象 Generation。否则同一拒绝在更新前后无法准确复盘。

可观测性本身有性能与隐私成本
   对高频普通读写全量审计会制造日志风暴、存储压力与敏感数据暴露。规则应优先覆盖高价值拒绝、身份变化、特权操作、策略加载与关键对象修改。

修复必须从第一个拒绝边界出发
   自动生成的放行建议可能把攻击尝试永久写入策略。应先证明业务需要该对象与操作，再选择更小的对象暴露、fd Broker、Capability、LSM 或 Syscall 例外。

关键路径
--------

Audit Event 重建：

::

   固定绝对时间、Boot ID 与 Event ID
   → 聚合同一事件的全部 Record
   → 从 SYSCALL 还原 Arch、Number、Result 与 Task
   → 从 PATH/CWD 还原对象路径与 Inode
   → 从 AVC/SECCOMP 还原安全决策
   → 关联 Runtime、Container 与 Policy Generation
   → 判断最终用户态结果

Audit 数据链：

::

   内核访问路径产生候选事件
   → Audit Rule 过滤和标记
   → Record 进入内核 Backlog
   → Auditd 从 Netlink 消费
   → 聚合、写盘、轮转或远程转发
   → 监控 Lost、Backlog 与磁盘状态
   → 查询工具按 Event ID 重建

攻击面收缩：

::

   只暴露必要 Mount、fd、Device 与 Network
   → 使用 Namespace 限制视图
   → 使用 Cgroup 限制资源
   → 设置最小 UID/GID 与 Capability
   → 应用 LSM 对象策略
   → 设置 no_new_privs
   → 安装 Seccomp Allowlist
   → 用 Audit 验证拒绝与特权使用

安全事件调查：

::

   固定宿主 PID/Container ID 与时间窗口
   → 还原 Subject Credential、Capability 与 Namespace
   → 还原 Object Inode、Label 与类别
   → 还原 Syscall、参数和请求权限
   → 确认第一个拒绝机制
   → 检查 Audit Lost 与规则命中
   → 对照策略仓库和部署版本
   → 做最小修复并复现验证

概念辨析
--------

* Audit 与安全策略：Audit记录决策证据；DAC、Capability、LSM、Seccomp等机制执行决策。
* Event 与 Record：一个事件可包含多条不同类型Record，必须按Event ID聚合。
* UID 与 AUID：UID表示当前Credential身份；AUID主要追踪登录来源。
* Path 与对象身份：Path便于阅读，Device+Inode+Namespace更接近内核对象。
* 无记录与无事件：日志缺失还可能来自规则、队列、Daemon、存储或权限问题。

本章结论
--------

Linux 安全可维护性的核心，是用多层最小权限机制缩小真实攻击面，再由 Audit 把主体、对象、入口、策略和结果连接成可验证、可复盘且带版本的事件链。