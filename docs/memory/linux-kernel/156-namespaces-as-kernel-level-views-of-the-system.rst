第156章：Namespaces 作为内核级系统视图
======================================

核心知识点
----------

Namespace 是资源视图对象
   Namespace 不复制整套内核，而是让 Task 在某类资源查找中使用不同的编号、名字、对象表或层级根。底层 Task、Inode、设备和 Page 仍可能被多个视图共享。

成员关系按类型独立组合
   一个进程同时关联 PID、Mount、Network、IPC、UTS、Time、Cgroup 和 User 等视图。共享一种 Namespace 不表示其它类型也共享，因此不存在单一的“容器 Namespace”。

Task 通过多条对象链取得视图
   多数 Namespace 从 ``task_struct`` 关联的 ``nsproxy`` 进入；User Namespace 主要随 ``cred``；PID 编号还要经过 ``struct pid`` 与分层 ``pid_namespace``。源码分析必须先确定具体类型的入口链。

Namespace 改变可见性，不直接限制资源
   Namespace 回答进程看见哪些对象以及怎样命名；CPU、内存、I/O 和任务数量的统计与限额主要由 Cgroup Controller 完成。两者解决不同问题。

创建、脱离和加入具有不同语义
   ``clone/clone3`` 配合 ``CLONE_NEW*`` 为新 Task 建立视图，``unshare`` 让调用者脱离共享组合，``setns`` 通过 Namespace fd 加入既有对象。每种类型都有独立权限和线程状态约束。

部分视图区分当前状态与子进程状态
   PID 和 Time Namespace 存在面向当前 Task 与面向后续子进程的不同关联。改变 ``pid_for_children`` 不会把调用进程自身重新编号，必须在创建子 Task 后才体现新层级。

nsfs 把 Namespace 暴露为可引用对象
   ``/proc/<pid>/ns/<type>`` 由 nsfs 投影为文件对象。同类型 Namespace 的 ``st_dev`` 与 ``st_ino`` 可用于比较活动对象身份，打开 fd 或 Bind Mount 会增加对象引用。

对象生命周期由引用决定
   最后一个成员进程退出不保证 Namespace 立即销毁。Task、Namespace fd、nsfs Bind Mount、Socket、设备及子系统内部对象都可能延长其生命周期，最终释放发生在最后一个引用归零之后。

权限判断依赖 User Namespace 范围
   创建或加入视图时，Capability 往往相对于相关 User Namespace 解释。子 User Namespace 中的 Root 只在其管理范围内拥有能力，不能据此推导 Initial User Namespace 的全局权限。

新视图不等于完整可用环境
   新 Network Namespace 仍需设备、地址和路由；新 Mount Namespace 仍需 Rootfs 与传播属性；新 PID Namespace 还需匹配的 procfs。视图建立只是资源环境装配的第一步。

关键路径
--------

资源查找路径：

::

   current task
   → task_struct / nsproxy / cred / struct pid
   → 取得目标类型 Namespace
   → 在该视图的树、编号或对象表中查找
   → 执行 namespace-aware 权限检查
   → 返回该视图下的结果

创建或加入视图：

::

   clone3 / unshare / setns
   → 检查类型、线程状态与 Capability
   → 分配、复制或引用 Namespace 对象
   → 构造新的 Namespace 组合
   → 切换 Task 关联或交给新子 Task
   → 初始化具体子系统状态

Namespace 退出：

::

   阻止新成员和新外部引用
   → 停止内部工作负载
   → 撤销设备、Socket、Mount 等外部连接
   → 关闭 Namespace fd 与 nsfs Bind Mount
   → 各持有者执行 put
   → 最后引用归零后释放子系统状态

概念辨析
--------

* Namespace 与 Cgroup：前者定义资源视图和命名范围；后者定义资源统计、分配和限制。
* 视图隔离与对象复制：不同视图可以隐藏同一底层对象，并不意味着对象被复制。
* Namespace inode 与永久身份：inode 适合比较当前活动对象，销毁后可复用，不能作为永久业务 ID。
* 当前 PID Namespace 与 ``pid_for_children``：前者决定当前 Task 的编号视图，后者决定以后创建的子 Task 所在层级。
* 成员退出与对象释放：成员数归零只是一个条件，fd、Mount 和子系统引用仍可保留对象。

本章结论
--------

Namespace 是 Task 持有的一组内核资源视图引用。它改变对象的可见、编号和查找方式，而底层资源共享、权限边界与最终释放仍由各子系统的真实对象关系决定。
