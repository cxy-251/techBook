第031章：procfs 是进程与内核状态的运行时视图
==============================================

本章必须记住
------------

#. ``procfs`` 是通常挂载在 ``/proc`` 的伪文件系统，用文件形式暴露运行中的进程状态和系统状态。
#. ``/proc`` 中的大多数文件不对应磁盘数据；读取时，内核根据当前对象和计数器即时生成文本。
#. 读取 ``/proc`` 的基本路径是：用户态 ``read`` → VFS → procfs inode → ``proc_ops`` 或 ``seq_file`` → 内核对象 → 格式化文本。
#. ``/proc/<pid>`` 中的 PID 是当前 PID namespace 看到的进程标识；不同 namespace 看到的目录集合可能不同。
#. ``/proc/<pid>/status`` 提供适合人工阅读的 task 摘要，包括身份、线程数、信号、capability 和粗粒度内存状态。
#. ``/proc/<pid>/stat`` 提供紧凑、适合程序解析的进程和调度字段；解析时必须正确处理带括号的进程名字段。
#. ``/proc/<pid>/maps`` 展示进程虚拟内存区域，也就是 VMA 的地址范围、权限、文件偏移和映射来源。
#. ``maps`` 展示虚拟地址空间结构，不等于物理内存占用；物理页贡献还要结合 RSS、PSS 和 ``smaps`` 判断。
#. ``/proc/<pid>/smaps`` 为每个 VMA 提供 RSS、PSS、共享页、私有页和脏页等细节，但读取成本明显高于 ``status`` 和 ``maps``。
#. ``/proc/<pid>/fd`` 把文件描述符表投影为符号链接；每个条目对应进程持有的一个打开对象引用。
#. ``fd`` 条目可能指向普通文件、socket、pipe、eventfd 或匿名 inode，链接文本只是对象的用户态表示。
#. ``/proc/meminfo`` 提供系统级内存统计，``MemAvailable`` 比单独的 ``MemFree`` 更接近系统还能分配多少内存的估计。
#. ``/proc/interrupts`` 按 CPU 和中断源显示硬中断计数，适合观察 IRQ 是否集中、停滞或异常增长。
#. ``/proc/softirqs`` 显示软中断类别在各 CPU 上的累计执行次数，常用于网络、定时器和 RCU 路径观察。
#. ``/proc/slabinfo`` 显示 slab cache 状态，适合怀疑内核对象缓存增长时使用，但需要结合具体对象生命周期解释。
#. ``/proc/sys`` 是 sysctl 的文件系统投影，读取表示观察运行参数，写入会改变内核运行状态。
#. ``sysctl`` 参数是运行时配置，不等于编译期 Kconfig；重启后是否保留取决于系统配置和启动流程。
#. ``/proc`` 输出通常是瞬时视图或累计计数，读取期间对象和计数器仍可能被其它 CPU 修改。
#. 单次采样只能证明读取时附近的状态；判断增长、泄漏、负载偏移和长期趋势需要多次同口径采样。
#. 条目是否可见受权限、ptrace 检查、capability、PID namespace、``hidepid`` 挂载选项和 LSM 策略影响。
#. 文件缺失或权限不足不能直接证明内核对象不存在，应先检查配置、namespace、挂载和权限边界。
#. ``seq_file`` 用 start、next、show、stop 等回调分段输出长列表，输出期间底层集合可能发生变化。
#. ``/proc`` 给出运行时证据入口，不自动解释根因；最终仍要回到结构体、计数器来源、状态变化和调用路径。

必背路径
--------

读取型 procfs 文件：

::

   用户态打开 /proc 路径
   → VFS 找到 procfs inode
   → 调用 proc_ops 或 seq_file 回调
   → 定位 task、mm、files、计数器或 sysctl 对象
   → 读取当前字段
   → 格式化为文本
   → 复制到用户缓冲区

排查单个进程：

::

   /proc/<pid>/status 查看身份、线程和内存摘要
   → /proc/<pid>/fd 查看打开对象数量与类型
   → /proc/<pid>/maps 查看虚拟地址空间结构
   → 必要时使用 smaps 查看页级贡献
   → 多次同口径采样确认变化趋势
   → 回到对应内核对象与资源路径

排查系统级异常：

::

   meminfo 判断内存分布
   → interrupts 判断硬中断分布
   → softirqs 判断延后执行负载
   → slabinfo 判断内核对象缓存
   → vmstat 或子系统计数器补充趋势
   → 结合日志和 tracing 定位具体路径

修改 sysctl 前：

::

   读取当前值
   → 查明参数单位、范围和作用对象
   → 保存修改前证据
   → 在可恢复环境中写入
   → 验证行为变化
   → 明确是否需要持久化配置

必须区分
--------

伪文件与磁盘文件
   procfs 文件是内核对象的动态接口；普通文件的数据由文件系统和存储介质保存。

虚拟内存与物理内存
   ``maps`` 描述虚拟区域；RSS、PSS 和页级统计描述当前物理页贡献。

状态与计数
   状态表示当前对象处境；累计计数表示某类事件从某个起点以来发生的次数。

快照与趋势
   单次读取是局部证据；趋势需要固定时间间隔和相同口径的连续采样。

读取与控制
   大部分 ``/proc`` 条目用于观察；``/proc/sys`` 和少数控制文件的写入会改变系统状态。

条目不可见与对象不存在
   权限、namespace、挂载选项和配置都可能隐藏条目，不能仅凭路径缺失下结论。

一句话结论
----------

``procfs`` 把进程对象、内存状态、文件表和系统计数器转换成可查询文本；读取结果是运行时证据，不是静态真相，也不是根因本身。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 31，procfs as a Runtime View of Processes and Kernel State；
* 源文件：``docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_031_procfs_as_a_Runtime_View_of_Processes_and_Kernel_State.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_031_procfs_as_a_Runtime_View_of_Processes_and_Kernel_State.md>`_。