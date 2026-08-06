第041章：task_struct 是 Linux 内核的任务对象
============================================

本章必须记住
------------

#. ``struct task_struct`` 是 Linux 表示可调度执行实体的核心对象；调度器直接处理的是 task，而不是抽象的“应用程序”。
#. 用户态常说的一个进程通常对应一个线程组；线程组中的每个线程通常各有一个 ``task_struct``。
#. ``task_struct`` 同时承载调度状态、身份关系、父子关系、资源引用、信号状态、权限和生命周期信息。
#. 阅读 ``task_struct`` 不能背字段列表，应先判断当前问题属于调度、身份、资源关系还是生命周期。
#. ``current`` 指向当前 CPU 正在执行的 task；它表示当前调度实体，不自动表示普通用户进程。
#. ``pid`` 通常对应单个 task 的线程 ID 视角，``tgid`` 对应线程组 ID 视角。
#. 用户态 ``getpid()`` 通常返回线程组 ID，``gettid()`` 返回当前 task 的线程 ID。
#. 单线程进程中 PID 与 TGID 通常相同；多线程进程中各线程 TID 不同，但 TGID 相同。
#. ``group_leader`` 指向线程组 leader；线程组 leader 为线程组提供进程级身份。
#. PID namespace 允许同一个 task 在不同层级显示不同编号；容器内 PID 与宿主机 PID 可以同时正确。
#. ``/proc/<pid>/status`` 中的 ``Pid``、``Tgid``、``Threads`` 和 ``NSpid`` 是 task、线程组与 namespace 关系的用户态投影。
#. ``task_struct`` 通过 ``mm`` 指向用户地址空间对象 ``mm_struct``。
#. 多个 task 指向同一个 ``mm_struct``，表示它们共享用户虚拟地址空间。
#. ``task_struct`` 通过 ``files`` 指向 ``files_struct``；该对象拥有文件描述符表。
#. 多个 task 共享同一个 ``files_struct`` 时，一个线程打开、关闭或替换 fd 会影响其它共享者。
#. ``fs_struct`` 保存根目录、当前工作目录和 umask 等路径上下文。
#. ``signal_struct`` 保存线程组级信号与资源状态，``sighand_struct`` 保存信号处理动作。
#. ``cred`` 和 ``real_cred`` 连接 task 的主观权限身份；访问控制还要结合目标对象和 LSM 状态。
#. ``nsproxy`` 把 task 连接到 mount、UTS、IPC、network、cgroup、time 等 namespace。
#. 调度字段把 task 连接到调度策略、优先级、CPU 亲和性和调度实体。
#. task 本身与其连接的资源对象具有不同生命周期；task 退出不等于所有共享资源立即释放。
#. ``get_task_struct()`` 与 ``put_task_struct()`` 用于持有和归还 task 引用；仅保存裸指针不能保证对象继续存在。
#. task 退出后会释放大部分运行资源，但可能以 zombie 形式保留退出信息，等待父进程回收。
#. ``EXIT_ZOMBIE`` 表示退出信息仍待父进程读取，``EXIT_DEAD`` 表示对象进入最终清理阶段。
#. RCU 或任务列表遍历只保护特定读取区间；需要跨越该区间长期使用 task 时，应取得正式引用。
#. 同一个 fd 数值、PID 数值或用户地址只有放回当前 task、资源表和 namespace 语境后才有完整意义。
#. 排查进程问题时，应从具体 task 出发，再沿它连接的 mm、files、signal、cred 和 namespace 对象继续追踪。

必背路径
--------

从用户态 PID 找到内核关系：

::

   确认观察者所在 PID namespace
   → 读取 /proc/<pid>/status
   → 区分 Pid、Tgid、Threads 和 NSpid
   → 定位具体 task 与线程组
   → 判断问题属于单 task 还是共享资源
   → 沿 mm、files、signal、cred 或 nsproxy 继续追踪

读取一个 ``task_struct``：

::

   先看运行与调度状态
   → 再看 pid、tgid、group_leader 和父子关系
   → 再看 mm、files、fs、signal、sighand、cred、nsproxy
   → 判断各对象是独占、复制还是共享
   → 最后确认 task 处于创建、运行、退出还是回收阶段

安全持有 task：

::

   在受保护的查找路径获得 task 指针
   → 判断现有锁或 RCU 保护范围
   → 需要跨保护区间使用时增加 task 引用
   → 使用 task 及其关联对象
   → 结束后归还引用
   → 不在最终 put 后继续访问字段

必须区分
--------

* 进程与 task：用户态进程通常是一个线程组和一组共享资源；task 是调度器可以独立运行和阻塞的实体。
* PID 与 TGID：PID/TID 标识具体 task；TGID 标识线程组的进程级身份。
* task 对象与资源对象：``task_struct`` 是关系中心；地址空间、文件表、信号和凭证由各自对象管理。
* 共享指针与复制内容：两个 task 指向同一资源对象表示共享；指向不同对象但内容初始相同表示复制。
* 退出与最终释放：task 停止执行后可能仍保留退出信息和引用，最终释放发生在回收与引用归零之后。
* RCU 可见与长期存活：RCU 可以保证特定读取阶段不被立即回收；跨阶段持有仍需要正式引用。

一句话结论
----------

``task_struct`` 是 Linux 执行、身份和资源关系的中心：一个用户态进程通常由多个 task 及其共享的内存、文件、信号和权限对象共同构成。
