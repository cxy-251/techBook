第164章：Seccomp 与系统调用过滤
===============================

核心知识点
----------

Seccomp 裁剪系统调用入口面
   Seccomp 在系统调用进入具体实现前，根据 ABI、系统调用号与整数参数选择处置动作。它减少进程可触达的内核接口，不负责文件、Socket 或 Inode 的对象级授权。

Seccomp 与其它边界互补
   Namespace 控制资源视图，Cgroup 控制资源消耗，Credential/Capability 与 LSM 控制对象访问。Seccomp 放行后这些检查仍会执行；Seccomp 拒绝时系统调用主体通常不会开始。

Filter 状态属于线程
   已安装规则随线程状态存在，并可继承到子 Task 与 ``execve()`` 后的新程序。多线程进程若只限制一个线程，其它线程可能保留更大的接口面。

限制只能单向叠加
   普通进程不能移除既有 Filter。后续安装只能继续收紧，多个 Filter 的结果按 Action 优先级组合，不是简单使用最后一条结果。

Strict Mode 与 Filter Mode 目标不同
   Strict Mode 只允许极小固定集合，适合已经准备好 fd 的简单计算。Filter Mode 使用受限 BPF 程序检查 ``struct seccomp_data``，是现代服务、浏览器和容器的主要模型。

``seccomp_data`` 描述 ABI 入口事实
   过滤器可读取 Architecture、Syscall Number、Instruction Pointer 与最多六个参数值。规则必须同时验证 Architecture 与编号，避免兼容 ABI 或不同架构编号碰撞。

Filter 不能解引用用户指针
   路径字符串、复杂结构体与指针指向内容不在 Seccomp 的稳定检查范围内。该限制避免基于可变用户内存形成 TOCTOU，但也意味着路径策略必须交给 Mount、DAC 或 LSM。

参数过滤适合稳定整数语义
   ``ioctl`` Command、``clone`` Flags、``bpf`` Command、fd 与长度等可以进一步限制。规则必须考虑位宽、兼容 ABI 和未来扩展，不能只按用户态函数名推断。

``no_new_privs`` 是常见安装前提
   无特权线程通常先设置 ``no_new_privs``，确保后续 Exec 无法通过 Setuid、Setgid 或 File Capability 获得新特权，再安装 Filter。该状态同样不可撤销。

Action 表达不同失败模型
   ``ALLOW`` 继续执行；``ERRNO`` 直接返回指定错误；``TRAP`` 触发 ``SIGSYS``；``KILL_THREAD``/``KILL_PROCESS`` 终止执行；``LOG`` 记录后继续；``USER_NOTIF`` 交给用户态 Supervisor。

User Notification 引入新的代理边界
   Supervisor 必须验证通知身份、目标生命周期与参数，并处理退出、超时和 fd 传递。直接继续原系统调用可能受到用户内存变化影响，不能把通知机制视为自动安全代理。

线程组同步必须显式保证
   ``TSYNC`` 类机制可尝试把 Filter 同步到线程组，安装可能因现有线程状态不兼容而失败。创建新线程、Fork 与 Exec 的继承路径都要进入测试范围。

安装时机决定攻击窗口与兼容性
   过早安装会阻止动态加载、Mount、Network、日志与线程初始化；过晚安装会留下宽接口窗口。稳定顺序是先完成环境装配和权限收缩，再安装运行期 Filter。

Default Deny 对新系统调用更保守
   Allowlist 会在内核新增系统调用时保持拒绝，升级成本较高；Default Allow 配合 Denylist 更兼容，却可能无意暴露未来入口。安全关键进程应以实际工作负载维护明确集合。

诊断必须还原 Arch、编号与 Action
   ``EPERM``、``SIGSYS`` 或进程退出只是表象。应读取目标线程的 Seccomp/NoNewPrivs 状态、真实 Profile、Audit ``SECCOMP`` 记录与失败参数，确认最先命中的规则。

关键路径
--------

Filter Mode 安装：

::

   完成需要特权的初始化
   → Drop 不再需要的 Capability
   → 设置 no_new_privs
   → 构造带 Architecture 检查的 Filter
   → seccomp/prctl 提交规则与 Flags
   → 内核验证控制流和返回 Action
   → 发布 Filter 到线程或线程组
   → 后续 Fork/Exec 继承限制

系统调用评估：

::

   Task 进入架构系统调用入口
   → 构造 seccomp_data
   → 遍历已安装 Filter Chain
   → 组合各 Filter Action 优先级
   → ALLOW 则进入系统调用实现
   → ERRNO/TRAP/KILL/NOTIFY 等走对应拒绝路径
   → 可生成 Audit、Signal 或通知事件

User Notification：

::

   Filter 返回 USER_NOTIF
   → 目标线程阻塞
   → 内核向 Listener 发布通知与唯一 ID
   → Supervisor 验证 ID、Task 与参数
   → 选择返回值、注入 fd 或受控继续
   → 处理目标退出和重复通知竞态
   → 释放在途通知状态

拒绝诊断：

::

   固定宿主 PID/TID 与架构
   → 取得失败 Syscall Number 和参数
   → 读取 NoNewPrivs、Seccomp Mode 与 Filter 数
   → 对照 Runtime/Profile 的默认 Action 和规则
   → 查询 Audit SECCOMP 与 SIGSYS
   → 确认线程组覆盖和最先命中规则
   → 只增加真实需要的最小入口

概念辨析
--------

* Seccomp 与 LSM：Seccomp限制系统调用入口；LSM根据真实内核对象执行强制策略。
* Strict Mode 与 Filter Mode：前者是固定极小集合，后者是可配置的 ABI 过滤程序。
* ``ERRNO`` 与对象权限失败：Seccomp的 ``ERRNO`` 不执行系统调用主体；DAC/LSM拒绝发生在对象路径内部。
* ``LOG`` 与阻断：``LOG`` 通常记录后继续执行，出现记录不表示请求被拒绝。
* Seccomp BPF 与 eBPF：Seccomp使用受限过滤模型，不拥有通用 eBPF 的 Map、Helper 和 Attach Point 语义。

本章结论
--------

Seccomp 是系统调用 ABI 的单向入口过滤器；安全性来自准确的 Architecture/参数规则、完整线程覆盖与正确安装时机，而对象权限、资源限制和路径策略必须由其它内核机制补足。