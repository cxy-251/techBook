第100章：伪文件系统作为内核接口
================================

本章必须记住
------------

#. 伪文件系统复用 VFS 的路径、权限、打开和读写语义，但后端不一定是持久化磁盘数据。
#. 看到一个路径时，先确认它属于 procfs、sysfs、debugfs、tmpfs、devtmpfs 还是其它文件系统，再解释内容。
#. “能够 open/read/write”只说明它提供文件接口，不表示它具有普通磁盘文件的持久化、缓存和 ABI 语义。
#. Procfs 主要导出进程视图和系统运行状态，典型路径包括 ``/proc/<pid>``、``/proc/meminfo`` 和 ``/proc/sys``。
#. Procfs 内容常在读取时根据 task、mm、namespace 或子系统状态动态生成。
#. ``/proc/<pid>`` 的可见性和内容受 PID namespace、权限、hidepid、LSM 和进程生命周期影响。
#. ``/proc/self`` 按读取进程解析到自身视图，不是固定 PID 目录。
#. Procfs 文本通常是瞬时快照；读取多行期间对象状态可以继续变化，不自动形成全局一致事务快照。
#. Procfs 字段可能增加，稳健解析应按字段名和文档读取所需值，而不是依赖固定行号或全部字段数量。
#. ``/proc/sys`` 把部分 sysctl 暴露成文件接口，写入会改变运行时内核参数，不是普通配置文件编辑。
#. Sysctl 写入的范围、单位、权限和持久化由具体参数与用户态配置机制决定。
#. Sysfs 主要导出 kobject、设备模型、总线、class、driver、module 及其属性关系。
#. Sysfs 目录层级反映内核对象关系，符号链接常用于表达 class、bus 和 device 之间的视图连接。
#. Sysfs 属性读取通常进入 ``show()``，写入进入 ``store()``；一个属性文件应尽量表达一个清晰值。
#. Sysfs 文本通常使用 ASCII，并常要求整次读取从 offset 0 获得一个属性值；具体行为由属性实现决定。
#. Sysfs 文件不是通用配置文件，不能假设支持随机写、追加写或保留用户写入的原始文本。
#. 写入 sysfs 可能立即触发设备重配置、解绑、扫描、电源、队列或策略变化，必须检查返回值和内核日志。
#. Sysfs ABI 是否稳定应查 ``Documentation/ABI`` 和子系统文档，不能仅因路径长期存在就自行推断。
#. Kobject 生命周期结束后，对应 sysfs 节点会消失；打开 fd 是否还能继续操作取决于 kernfs 和属性实现。
#. Debugfs 面向开发和调试，不承诺稳定用户态 ABI，文件名、格式、权限和存在性都可随版本改变。
#. Debugfs 常由内核开发者直接挂接 ``file_operations`` 或 helper，适合诊断内部状态和实验控制。
#. 生产自动化依赖 debugfs 时必须固定内核版本、配置、权限和失败降级，默认不应把它当稳定产品接口。
#. Debugfs 通常需要 ``CONFIG_DEBUG_FS`` 并单独挂载，安全环境可能完全不提供该视图。
#. Tracefs 是追踪接口的专用文件系统，常挂在 ``/sys/kernel/tracing``，不应与 debugfs 的历史挂载方式混淆。
#. Tmpfs 是真正具有目录、inode、文件内容和权限的内存文件系统，只是后端主要来自内存和 swap。
#. Tmpfs 内容在卸载或重启后通常消失，不具有普通持久化块设备文件系统的掉电保留语义。
#. Tmpfs 可以按需增长，受 mount size、inode、memcg、系统内存和 swap 等限制。
#. Tmpfs 文件仍可能进入 Page Cache/shmem、swap、mmap、truncate 和文件锁等普通文件语义。
#. ``/run``、``/dev/shm`` 和容器临时目录常使用 tmpfs，但实际挂载类型必须从 mountinfo 确认。
#. Tmpfs 使用内存不等于永远驻留 RAM；可交换页面可能进入 swap，具体受配置和锁页状态影响。
#. Devtmpfs 为设备模型创建和维护 ``/dev`` 下的设备节点视图，节点本身不实现设备数据语义。
#. 打开 ``/dev/null``、块设备或 tty 后，真正读写行为由字符设备或块设备驱动的操作表决定。
#. Device node 主要保存设备类型和 major/minor 入口；权限、udev 规则和驱动注册共同决定可用性。
#. Devtmpfs 与 udev/systemd-udevd 角色不同：前者提供内核基础节点，后者可设置命名、权限、链接和策略。
#. ``/dev`` 中也可能存在 tmpfs 内容、符号链接、socket 和用户态创建节点，不能把整个目录都视为 devtmpfs 设备。
#. Kernfs 是 sysfs、cgroupfs 等接口可复用的内部基础设施，具体用户可见语义仍由上层子系统定义。
#. Cgroupfs 通过文件接口管理 cgroup 层级和控制器状态，不是普通磁盘目录权限模型的简单复制。
#. Configfs 与 sysfs 方向不同：configfs 通常由用户态创建对象以驱动内核配置，sysfs 主要展示已有内核对象。
#. Securityfs、pstore、efivarfs、BPF fs 等也使用 VFS 暴露专用内核对象，各自有独立 ABI 与生命周期。
#. 伪文件系统读操作可能在读取时分配内存、取得锁、遍历对象或格式化大量文本，不保证零成本。
#. 大量或高频读取 procfs/sysfs/debugfs 可能增加锁竞争、CPU 和对象遍历成本，监控应控制采样频率。
#. 单次读取结果可能因并发状态变化不一致；需要一致性时应使用子系统提供的快照、序列号或专用接口。
#. ``seq_file`` 是内核生成顺序文本的常用辅助框架，帮助处理多次 read、偏移和大输出，具体使用不等于结果原子一致。
#. 伪文件系统写回调必须解析用户输入、验证范围和权限；用户态不能假设写入部分字节会被保留。
#. Store/write 返回短写或错误时，调用者必须按该接口文档处理，不能像普通文件那样盲目重试拼接。
#. 路径可见性由 mount namespace 决定；容器可以拥有独立 procfs、sysfs 或 tmpfs 挂载视图。
#. PID namespace 与 procfs 挂载配合决定容器中可见的进程集合，只改变 namespace 不重新挂载 procfs 可能得到错误视图。
#. Sysfs 通常反映主机设备模型，即使在容器中 bind mount，也不自动提供完整设备隔离。
#. User namespace、capabilities、LSM、mount flags 和只读 bind mount 共同限制伪文件系统的写能力。
#. Chroot 只改变路径根，不自动隔离 procfs/sysfs 中可见的内核对象。
#. Mount propagation 可能让宿主机和容器对伪文件系统挂载变化产生不同可见结果。
#. ``/proc/<pid>/root``、``mountinfo`` 和 namespace inode 是排查同名路径差异的关键证据。
#. Stable ABI、testing ABI、debug-only interface 和内部实现必须分开判断。
#. UAPI 文档化 proc/sysfs 接口通常需要保持兼容，但格式仍可能允许增加新字段和状态值。
#. 用户态解析枚举状态时应容忍未来新增值，不能把未知值直接当数据损坏。
#. Debugfs、内核日志文本和 trace 格式通常不提供与正式 UAPI 同等级的长期兼容保证。
#. Tmpfs 文件内容由用户态创建，文件格式稳定性属于应用协议，不属于 tmpfs 内核 ABI。
#. Devtmpfs 节点名称可能受设备模型与用户态管理器影响，程序更应依赖正式设备发现和 udev 属性。
#. 不应通过轮询 debugfs 代替 netlink、ioctl、sysfs ABI 或其它正式事件接口。
#. 需要异步设备/网络状态时，应优先使用对应子系统事件机制，而不是高频 cat 动态文件。
#. 读取伪文件系统失败时，应区分未挂载、路径不存在、对象已销毁、权限拒绝、配置未启用和 namespace 不可见。
#. ``ENOENT`` 在 procfs/debugfs 中可能表示对象已退出或功能未注册，不一定是安装损坏。
#. ``EACCES``/``EPERM`` 可能来自 Unix mode、capability、ptrace access、LSM、mount flags 或 lockdown。
#. 写 sysfs/debugfs 后返回成功不代表外部硬件动作已经最终完成，异步驱动状态还需读取状态或等待事件确认。
#. 最稳定分析顺序是：路径 → mount 类型 → VFS file → 后端内核对象 → read/write callback → ABI 等级 → namespace 与权限。

必背路径
--------

读取 procfs：

::

   用户 open /proc/<pid>/status
   → 在当前 mount namespace 找到 procfs
   → PID namespace 解析目标 task
   → 权限与 ptrace/LSM 检查
   → proc file read / seq_file callback
   → 读取 task、mm、signal 等当前状态
   → 格式化文本返回用户态
   → 结果只代表读取期间的运行时视图

读取或写入 sysfs 属性：

::

   路径解析到 kernfs/sysfs node
   → 节点关联 kobject 与 attribute
   → 检查权限和对象生命周期
   → read 调用 show
   → write 解析输入并调用 store
   → 子系统更新设备或策略状态
   → 返回字节数或错误
   → 必要时通过状态属性/事件确认结果

Tmpfs 文件：

::

   在 tmpfs mount 中创建文件
   → 建立 dentry 与 shmem inode
   → 写入分配内存页并形成文件内容
   → 可 mmap、读写、truncate 或 swap
   → 受 size/inode/memcg 限制
   → unlink 后等待最后引用
   → 卸载或重启后内容消失

打开 devtmpfs 设备节点：

::

   路径查找到 /dev 节点
   → inode 保存字符/块设备号
   → VFS 根据 major/minor 查找已注册设备
   → 创建 struct file
   → 后续 read/write/ioctl/poll
   → 分发到具体设备驱动
   → close 时执行驱动 release 与引用清理

选择用户态接口：

::

   明确需要查询还是配置
   → 查官方 UAPI 与 Documentation/ABI
   → 优先正式 syscall/netlink/ioctl/sysfs/proc ABI
   → 测试接口标注版本和兼容范围
   → debugfs 只用于诊断或受控工具
   → 解析时容忍新增字段和值
   → 在目标 namespace 和权限下验证

必须区分
--------

伪文件系统与普通磁盘文件系统
   二者都走 VFS；伪文件的内容可能动态来自内核对象，而不是持久化数据块。

Procfs 与 Sysfs
   Procfs 主要展示进程和系统状态；sysfs 主要展示 kobject 与设备模型属性。

Sysfs 与 Debugfs
   文档化 sysfs 属性可作为用户 ABI；debugfs 默认不承诺长期兼容。

Tmpfs 与动态状态文件
   Tmpfs 保存用户态写入的真实文件内容；procfs/sysfs 常在读取时动态生成数据。

Devtmpfs 节点与设备驱动
   Devtmpfs 提供名字和设备号入口；实际设备操作由驱动定义。

路径存在与接口稳定
   文件能被读取不表示格式受稳定 ABI 保护，必须查接口文档和维护承诺。

一句话结论
----------

伪文件系统把 VFS 文件语义映射到进程、设备、调试、内存和驱动对象，使用前必须同时确认后端对象、ABI 等级、命名空间和生命周期。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 20，Filesystem Implementations ext4, XFS, Btrfs, and Pseudo Filesystems；
* AIBook 章节：Chapter 100，Pseudo Filesystems as Kernel Interfaces；
* 源文件：``docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_100_Pseudo_Filesystems_as_Kernel_Interfaces.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_100_Pseudo_Filesystems_as_Kernel_Interfaces.md>`_。