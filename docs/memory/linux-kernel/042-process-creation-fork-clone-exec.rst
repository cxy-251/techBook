第042章：fork、clone 与 exec 的进程创建语义
==========================================

本章必须记住
------------

#. Linux 创建新的执行实体时，核心动作是创建新的 ``task_struct``，再决定资源是复制、共享还是重新初始化。
#. ``fork`` 的本质不是完整复制整个进程，而是受控复制当前执行上下文。
#. 典型主路径是：系统调用入口 → ``kernel_clone()`` → ``copy_process()`` → 复制或共享资源 → 分配 PID → ``wake_up_new_task()``。
#. ``copy_process()`` 是新 task 的对象装配中心，负责 task、调度状态、地址空间、文件表、信号、凭证、namespace 和父子关系。
#. ``dup_task_struct()`` 准备新的 task 基础结构与内核栈；后续各 ``copy_*`` 路径处理具体资源对象。
#. ``fork`` 后父子进程通常拥有不同 ``task_struct``、PID 和调度实体。
#. ``fork`` 的地址空间采用写时复制 COW：先复制 VMA 与页表关系，并共享物理页；写入时再为写入方复制页面。
#. COW 降低了创建开销，但 fork 仍需复制页表、VMA 和大量对象引用；大地址空间的 fork 仍可能昂贵。
#. ``fork`` 后父子通常拥有独立的文件描述符表，但表项引用同一批 ``struct file``。
#. 父子共享同一个 ``struct file`` 时，也会共享文件偏移和 open file description 层状态。
#. 子进程的 pending signal 不会简单复制父进程当前的未决信号；信号处理配置与线程组状态按明确规则复制或重建。
#. ``clone`` 与 ``clone3`` 的核心作用是用 flags 描述新 task 与调用者共享哪些资源。
#. ``CLONE_VM`` 共享 ``mm_struct``，因此多个 task 看到同一用户地址空间。
#. ``CLONE_FILES`` 共享 ``files_struct``，因此 fd 表的修改对共享者立即可见。
#. ``CLONE_FS`` 共享根目录、当前目录和 umask 等 ``fs_struct`` 状态。
#. ``CLONE_SIGHAND`` 共享信号处理动作，通常与更强的资源共享约束一起使用。
#. ``CLONE_THREAD`` 让新 task 加入同一线程组，共享 TGID 和线程组级信号状态。
#. ``CLONE_SETTLS`` 为新 task 设置线程局部存储入口。
#. ``CLONE_CHILD_CLEARTID`` 常在线程退出时清零用户地址并配合 futex 唤醒等待者。
#. Linux 的用户态进程与线程都建立在 task 创建机制上，差别主要来自资源共享 flags。
#. ``clone3`` 使用 ``struct clone_args`` 组织参数，便于扩展、大小检查和字段校验。
#. clone flags 存在组合依赖和互斥关系；不能把任意 flags 当作独立开关随意拼接。
#. ``execve`` 不创建新的 task；它在当前 task 中替换用户态程序映像。
#. exec 主路径会解析可执行文件格式、建立新 ``mm_struct``、装入代码和数据、创建新用户栈并设置入口寄存器。
#. exec 成功后 PID 与 task 身份通常保持不变，但用户地址空间、代码、数据、用户栈和大部分执行映像已经被替换。
#. exec 会关闭标记 ``FD_CLOEXEC`` 的文件描述符；未标记的 fd 通常继续保留。
#. exec 会重置信号处理器、线程组和其它进程状态中的一部分，具体规则属于稳定用户态 ABI。
#. 多线程进程成功 exec 后，执行 exec 的线程成为新程序的唯一用户线程，其它线程被清理。
#. exec 的提交点很重要：提交前失败应保持旧程序可继续运行；提交后失败空间受到更严格限制。
#. fork/clone 的错误路径必须按初始化阶段逆序释放 task、mm、files、signal、PID 和 namespace 引用。
#. ``vfork`` 具有更强同步关系，父任务通常等待子任务 exec 或退出；它不能等同于普通 fork。
#. 阅读创建路径时，必须逐项列出新 task 对每个资源对象采取的是复制、共享、清空还是替换。

必背路径
--------

``fork`` 创建：

::

   用户态 fork
   → 系统调用入口整理创建参数
   → kernel_clone
   → copy_process
   → 复制 task 外壳和内核栈
   → 复制或引用 mm、files、signal、cred、namespace
   → 分配 PID 并建立父子关系
   → wake_up_new_task
   → 父子从不同返回值继续执行

COW 写入：

::

   fork 后父子页表指向同一物理页
   → 页表限制写入
   → 任一方发生写缺页
   → 分配新物理页
   → 复制旧页内容
   → 更新写入方页表
   → 父子从此使用不同物理页

创建线程：

::

   pthread_create
   → 用户态线程库准备栈、TLS 和 clone flags
   → clone 或 clone3
   → 创建新 task
   → 共享 mm、files、sighand 和线程组状态
   → 设置独立 TID、栈、寄存器、TLS 与调度实体
   → 新线程进入调度器

``execve`` 替换映像：

::

   当前 task 调用 execve
   → 复制并校验路径、argv 和 envp
   → 打开可执行文件
   → 选择 binary format handler
   → 建立新地址空间
   → 加载程序段与解释器
   → 构造用户栈和入口寄存器
   → 处理 close-on-exec、信号和线程组状态
   → 提交新映像
   → 从新程序入口返回用户态

必须区分
--------

* ``fork`` 与完整内存复制：fork 复制地址空间结构并使用 COW；物理页通常在后续写入时才复制。
* ``fork`` 与 ``clone``：fork 使用传统进程式默认共享策略；clone 通过 flags 显式定义资源边界。
* 创建 task 与执行新程序：fork/clone 创建新的 task；exec 在当前 task 内替换程序映像。
* 独立 fd 表与共享 ``struct file``：fork 后 fd 表通常独立，但对应打开对象可以继续共享偏移和状态。
* 共享地址空间与独立栈：多线程 task 可以共享同一个 ``mm_struct``，同时各自在其中使用独立栈区域。
* exec 身份保留与映像保留：exec 通常保留 PID 和部分资源身份，但原用户代码、数据和栈被新映像替换。

一句话结论
----------

Linux 先用同一套 task 创建机制生成执行实体，再用 clone flags 决定资源共享；``fork`` 偏复制，线程偏共享，``exec`` 则在原 task 中替换用户态程序映像。
