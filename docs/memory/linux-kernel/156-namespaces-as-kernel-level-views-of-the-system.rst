第156章：Namespaces 作为内核级系统视图
======================================

本章必须记住
------------

#. Namespace 的本质是为某类全局内核资源提供一张可切换、可共享、可引用的进程视图。
#. Namespace 不会复制一整套 Linux 内核；进程只是通过对象指针进入不同的编号、命名、查找和权限范围。
#. 读 Namespace 时必须拆成三个对象：被管理的资源、Namespace 视图对象、Task 到该视图的成员关系。
#. 同一 Namespace 内的进程共享该类资源视图；不同 Namespace 内的进程可以看到不同名字、编号或对象集合。
#. Namespace 改变“进程看见什么”，不直接控制“进程最多使用多少 CPU、内存或 I/O”；后者主要由 Cgroup 负责。
#. Namespace 也不等于安全边界完整成立；Credential、Capability、LSM、Seccomp、文件权限和设备访问仍需独立检查。
#. ``task_struct`` 表示执行实体；多数 Namespace 通过 ``task_struct`` 关联的 ``struct nsproxy`` 间接持有。
#. ``struct nsproxy`` 聚合 Mount、UTS、IPC、Network、Cgroup、Time 等 Namespace 指针，并保存面向子进程的 PID/Time Namespace 关系。
#. User Namespace 更紧密地关联 Credential，通常从 ``struct cred`` 的 ``user_ns`` 一类字段进入。
#. PID Namespace 还需要结合 ``struct pid`` 的多层编号关系理解，不能只看 ``nsproxy``。
#. Namespace 是按类型独立的：两个进程共享 Mount Namespace，不表示它们也共享 Network、PID 或 User Namespace。
#. 判断成员关系必须逐类型比较，不能把“属于同一个容器”当作所有 Namespace 必然相同的证据。
#. ``/proc/<pid>/ns/`` 是用户态观察 Namespace 成员关系和取得 Namespace 文件句柄的主要接口。
#. ``/proc/<pid>/ns/<type>`` 通常由 nsfs 投影为 ``type:[inode]`` 形式的链接。
#. 对同一 Namespace 类型，设备号和 inode 相同，表示两个进程引用同一个活动 Namespace 对象。
#. 只比较 ``readlink`` 字符串适合人工观察；脚本应优先比较 ``stat`` 暴露的 ``st_dev`` 与 ``st_ino``。
#. Namespace inode 只在对象活动期间具有身份意义，对象销毁后编号可能被复用，不能作为跨重启永久 ID。
#. 打开 ``/proc/<pid>/ns/<type>`` 得到的 fd 会引用 Namespace 对象。
#. 即使原成员进程已经退出，只要 Namespace fd、Bind Mount 或其它内核引用仍存在，该 Namespace 仍可存活。
#. Namespace 生命周期不是“最后一个成员进程退出就必然销毁”，而是“最后一个对象引用归零后释放”。
#. 把 Namespace 文件 Bind Mount 到持久路径，本质是为 Namespace 对象保留一个 VFS/nsfs 引用。
#. ``clone()``/``clone3()`` 配合 ``CLONE_NEW*`` 标志，通常在创建子 Task 时建立新的 Namespace 视图。
#. ``unshare()`` 让调用 Task 脱离原共享上下文，并为后续执行进入新的 Namespace 组合。
#. ``setns()`` 通过 Namespace fd 加入一个已存在的 Namespace 视图。
#. ``clone``、``unshare``、``setns`` 都不是无条件切换；每类 Namespace 有权限、线程状态和对象关系约束。
#. 创建或加入多数 Namespace 时，Capability 检查通常在相关 User Namespace 范围内执行，而不是简单检查全局 UID 是否为 0。
#. User Namespace 的创建和进入规则与其它 Namespace 不完全相同，不能把同一套 ``CAP_SYS_ADMIN`` 结论机械套用。
#. Namespace 数量还可能受到 ``/proc/sys/user/max_*_namespaces`` 一类系统限制约束。
#. ``setns`` 的目标 fd 类型必须和请求类型一致；错误 fd、错误 Namespace 类型或权限不足都会导致失败。
#. 加入 Mount Namespace 会改变后续路径解析视图，不会自动改变已经打开 fd 指向的文件对象。
#. 加入 Network Namespace 会改变后续 Socket、设备、路由和端口查找，不会自动把已有 Socket 迁移到新网络栈。
#. 加入 UTS Namespace 会改变后续 Hostname/NIS Domain 视图，不改变调度或文件系统对象。
#. PID Namespace 的当前成员关系具有特殊性：进程不能像切换 Network Namespace 那样直接改变自己的当前 PID 编号视图。
#. ``/proc/<pid>/ns/pid`` 表示 Task 当前 PID Namespace；``pid_for_children`` 表示其后续子进程使用的 PID Namespace。
#. ``unshare(CLONE_NEWPID)`` 或相关 ``setns`` 操作主要影响之后创建的子进程，调用进程自身仍保留当前 PID Namespace 身份。
#. Time Namespace 同样存在当前视图与面向子进程视图的边界，精确接口依目标内核版本。
#. Namespace 对象创建后，具体资源子系统还需初始化自己的状态，例如 ``struct net`` 的 Per-net 数据、Mount Tree 或 IPC 表。
#. Namespace 创建成功不表示内部环境已经可用；新的 Network Namespace 最初可能只有未启用的 Loopback，新的 Mount Namespace 也可能仍继承原挂载关系。
#. Namespace 隔离经常依赖多种类型组合：独立 PID 树通常还要配合匹配的 ``/proc`` Mount 才能让 ``ps`` 等工具显示正确视图。
#. 独立 Mount Namespace 仍可能因 Shared Mount Propagation 把挂载事件传播到宿主或其它 Namespace。
#. 独立 Network Namespace 仍需要 Veth、Bridge、Route 或显式设备移动才能与外部通信。
#. User Namespace 可以改变 UID/GID 和 Capability 的解释范围，不等于自动获得宿主 Initial User Namespace 权限。
#. Cgroup Namespace 主要改变 Cgroup 路径的可见起点，不改变 Task 的真实 Cgroup 资源归属和限制。
#. Namespace View 与底层对象可能共享：不同 Mount Namespace 可引用相同 Superblock/Inode，不同 PID 视图仍指向同一个 ``task_struct``。
#. 因此“容器里看不到宿主对象”不等于该对象在内核中不存在或被复制。
#. Namespace 切换和成员关系更新需要遵守引用计数、RCU、锁和具体子系统同步规则。
#. 读源码时应先找调用路径怎样从 ``current`` 取得 Namespace 指针，再追踪该指针怎样参与对象查找和权限检查。
#. ``copy_namespaces()``、``switch_task_namespaces()``、``put_nsproxy()`` 一类函数是 Namespace 组合复制、切换和释放的重要入口，精确函数组织随版本演进。
#. Namespace fd 由 nsfs 与 ``proc_ns_operations`` 一类接口连接到具体 Namespace 的 ``get``、``put``、``install`` 和所有者判断。
#. ``setns`` 成功的核心不是修改一个字符串，而是用受保护的新对象引用替换 Task 的相关 Namespace 关联。
#. 多线程进程进行 Namespace 切换时会受共享 ``fs_struct``、Credential、线程组和具体 Namespace 规则限制。
#. Container Runtime 常通过专门的 Init 子进程完成 Namespace 装配，避免普通业务线程在共享状态下切换。
#. Namespace 并不隐藏所有观察接口；宿主机处于祖先或 Initial Namespace 时通常仍能看到和管理子 Namespace 中的对象。
#. PID Namespace 具有祖先可见、后代不可反向看见祖先进程的层级语义。
#. User Namespace 也形成层级，Capability 是否有效必须同时问“当前 Credential 位于哪个 User Namespace”和“目标对象由哪个 User Namespace 拥有”。
#. Namespace 引用可以跨进程传递，例如通过 Unix Socket 传递 Namespace fd，再由接收进程执行 ``setns``。
#. 这种 fd 传递不会自动赋予加入权限；内核仍执行类型和 Capability 检查。
#. 排查 Namespace 问题时，第一步必须固定宿主机视角下的目标 PID。
#. 容器内 PID 与宿主 PID 可能不同，使用错误 PID 会让后续 Namespace、Cgroup 和 Credential 证据全部指向错误对象。
#. 第二步逐类型比较 ``/proc/<pid>/ns``，确认目标进程和参照进程在哪些视图相同、哪些不同。
#. 第三步进入目标视图执行只读观察，例如在目标 Net Namespace 内看地址和路由，在目标 Mount Namespace 内看 ``mountinfo``。
#. ``nsenter`` 是用户态封装，核心仍是打开 Namespace fd 并调用 ``setns``。
#. 进入 Namespace 后看到的工具输出只说明目标视图内部状态；跨 Namespace 的 Veth、宿主转发、Capability 和 LSM 仍需继续检查。
#. Namespace 创建失败应区分权限不足、系统数量限制、内存分配失败、目标类型不支持和调用状态不允许。
#. Namespace 看似未销毁时，应查找成员 Task、打开 Namespace fd、nsfs Bind Mount 和 Runtime/守护进程引用。
#. Namespace 泄漏会保留其内部资源，例如 Network Namespace 中的设备、Socket、Route 或 Per-net 状态。
#. 安全销毁顺序通常是停止新成员加入、停止内部工作负载、撤销外部连接、释放 Namespace fd/Bind Mount，最后让引用归零。
#. 精确 Namespace 类型、结构字段、权限规则和内核配置具有版本差异。
#. 稳定源码阅读顺序是：Task/Cred → Namespace Pointer → Resource Lookup → ``clone/unshare/setns`` → nsfs fd → Reference Release。

必背路径
--------

Namespace 资源查找：

::

   当前 Task 执行系统调用
   → 从 task_struct / nsproxy / cred 取得对应 Namespace
   → 在该 Namespace 的编号、树或对象表中查找
   → 执行权限与对象操作
   → 返回该视图下的名字、编号或结果

比较两个进程的 Namespace：

::

   固定宿主机 PID A 与 PID B
   → 分别读取 /proc/A/ns/<type> 与 /proc/B/ns/<type>
   → 比较同类型 st_dev + st_ino
   → 相同则共享该视图
   → 不同则继续检查创建、继承或 setns 路径

创建新视图：

::

   clone/clone3/unshare 传入 CLONE_NEW*
   → 检查 User Namespace 范围内的权限和系统限制
   → 分配或复制具体 Namespace 对象
   → 构造新的 Namespace 组合
   → 子 Task 继承或当前 Task 切换
   → 初始化该 Namespace 内的资源状态

加入既有视图：

::

   打开 /proc/<pid>/ns/<type>
   → fd 持有 Namespace 引用
   → setns(fd, type)
   → 验证类型、线程状态与 Capability
   → 安全替换 Task 的 Namespace 关联
   → 后续资源操作进入目标视图

Namespace 生命周期：

::

   Task / Namespace fd / Bind Mount / 内核对象持有引用
   → 成员进程退出
   → 仍有引用则 Namespace 继续存活
   → 撤销外部引用与挂载
   → 最后一个 put
   → 具体子系统执行退出和资源释放

必须区分
--------

* Namespace 与 Cgroup：Namespace 控制资源视图；Cgroup 负责资源统计、分配和限制。
* 资源视图与资源副本：Namespace 改变查找和编号关系，底层 Inode、Task、Page 或设备并不一定复制。
* Namespace inode 与永久身份：nsfs inode 适合比较活动对象，不能作为跨销毁和跨重启的永久 ID。
* 当前 PID Namespace 与 ``pid_for_children``：当前 Task 的 PID 视图保持稳定；后者决定以后创建的子进程进入哪一层。
* 最后一个成员退出与 Namespace 释放：成员数归零不保证释放，fd、Bind Mount 和其它引用仍可延长生命周期。

一句话结论
----------

Namespace 是 Task 持有的一组内核资源视图引用：它改变进程如何看见和命名对象，而对象何时销毁仍由真实引用生命周期决定。
