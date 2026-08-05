第096章：真实文件系统如何接入 VFS
=================================

本章必须记住
------------

#. VFS 规定统一的对象、系统调用入口和操作表合同；具体文件系统决定磁盘布局、分配策略、崩溃一致性和性能行为。
#. 一个文件系统类型通过 ``struct file_system_type`` 向 VFS 注册，类型对象不等于某次具体挂载实例。
#. ``register_filesystem()`` 让内核认识某种文件系统类型；实际 mount 时才创建或取得 ``struct super_block``。
#. 新挂载 API 通常围绕 ``fs_context`` 初始化、参数解析、``get_tree`` 和 ``fill_super`` 一类阶段组织。
#. 块设备文件系统常通过 ``get_tree_bdev()`` 一类公共路径连接块设备，再由具体文件系统填充 superblock。
#. ``fill_super`` 的稳定角色是读取并校验后端元数据、初始化私有状态、设置操作表并建立根 inode 与根 dentry。
#. ``struct super_block`` 表示一次已挂载文件系统实例，``struct file_system_type`` 表示可创建这类实例的类型。
#. 同一种文件系统类型可以在不同设备、不同参数和不同 mount namespace 中形成多个实例。
#. 文件系统私有 superblock 状态通常通过 ``s_fs_info`` 等连接到 VFS ``super_block``，具体结构和字段具有版本差异。
#. 根 dentry 把挂载实例接入 VFS 路径树；mount 对象再决定该根在某个 mount namespace 中的位置。
#. ``/proc/filesystems`` 说明当前内核认识哪些文件系统类型，不说明某个实例已经挂载或采用了哪些参数。
#. ``/proc/<pid>/mountinfo``、``findmnt`` 等用于观察具体进程可见的挂载实例和选项。
#. VFS 通过函数指针表实现文件系统多态，不能只从系统调用名称判断具体执行函数。
#. ``super_operations`` 管理挂载实例级动作，如 inode 生命周期、同步、统计、冻结和卸载相关路径。
#. ``inode_operations`` 管理名字和元数据语义，如 lookup、create、unlink、rename、getattr 和 setattr。
#. ``file_operations`` 管理打开实例相关动作，如 read_iter、write_iter、llseek、mmap、fsync、ioctl 和 release。
#. ``address_space_operations`` 或 iomap 相关接口连接 Page Cache、文件偏移、块映射、direct I/O 和 writeback。
#. VFS 公共代码负责 fd/path 查找、通用权限和对象引用；具体文件系统在回调前后加入自己的锁、事务和映射规则。
#. 同一个 regular file 的读写、目录 lookup、inode 回收和 superblock 同步属于不同对象层，必须分别追对应操作表。
#. 文件系统可以复用 ``generic_file_*``、iomap 等公共 helper；复用 helper 不表示所有文件系统具有相同持久化语义。
#. 文件系统在调用公共 helper 前后的检查和事务边界，往往正是具体行为差异所在。
#. 磁盘 inode、目录项、extent、位图和日志属于持久化格式；VFS inode、dentry、file、folio 属于运行时对象。
#. 磁盘 inode 与内存 ``struct inode`` 有映射关系，但不是同一个对象，也不具有同一生命周期。
#. 一个磁盘 inode 可以被多个 dentry 名字引用，也可以被多个 ``struct file`` 打开实例引用。
#. Dentry cache 命中不等于从磁盘重新读取目录项；inode cache 命中也不等于磁盘元数据没有变化。
#. 网络和集群文件系统可能要求 revalidate，缓存可信度由具体文件系统语义决定。
#. Page Cache 保存文件数据的内存副本；磁盘块映射和写回由文件系统及其后端决定。
#. 用户态 ``write()`` 成功通常只证明数据已被当前写路径接受，不自动证明数据和元数据已到稳定介质。
#. ``fsync()`` 的具体保证由 VFS 合同、具体文件系统实现、挂载选项和设备 flush/ordering 共同决定。
#. 文件系统日志通常主要保护元数据事务一致性；是否记录数据内容必须看具体数据模式。
#. 崩溃后“文件系统可挂载”和“应用数据满足业务事务”是两个不同保证。
#. Mount option 是运行时策略输入，可能改变日志模式、delayed allocation、DAX、discard、压缩、校验和或权限行为。
#. 相同文件系统类型在不同挂载选项下可以具有明显不同的延迟、空间和恢复特征。
#. Mount option 必须从目标实例的实际挂载视图确认，不能只读配置文件或启动命令推断。
#. 某些选项只在 mount 时确定，某些支持 remount/reconfigure；具体能力取决于文件系统和版本。
#. 不支持或冲突的选项应在挂载阶段失败或被明确报告，不能假设内核总会静默接受。
#. 文件系统 feature bits 决定磁盘格式能力和兼容边界；内核不认识关键不兼容特性时应拒绝挂载。
#. 只读兼容特性可能允许只读挂载而禁止读写挂载，具体规则由格式定义。
#. Filesystem module unload 前必须没有挂载实例、活动回调和其它引用继续依赖模块代码。
#. 卸载 mount 和注销 filesystem type 是两层生命周期；先结束实例，再考虑移除类型。
#. 错误路径必须逆序撤销已取得的块设备、私有状态、journal、root inode、root dentry 和注册关系。
#. ``kill_sb``/put_super 类路径负责实例退出，但打开 file、mmap、cwd/root、子挂载等引用会影响卸载时机。
#. Forced shutdown 是部分文件系统在检测严重一致性错误后停止进一步修改的保护状态，具体语义由实现决定。
#. 文件系统报告错误时，应同时保存 VFS errno、内核日志、挂载选项、设备错误和具体文件系统状态。
#. ``statfs`` 展示的是文件系统提供的空间视图，不同文件系统对预留、共享、压缩和元数据的统计模型不同。
#. “可用空间”不能跨 ext4、XFS、Btrfs 等实现机械比较，必须理解其分配域和保留策略。
#. 分析一次文件操作时，先确认对象层：mount、path、inode、file、mapping；再找对应 operation table。
#. 最稳定源码阅读顺序是：filesystem type 注册 → mount/fs_context → fill_super → 建立 VFS 对象 → operation table 分发 → 文件系统私有事务和后端。

必背路径
--------

文件系统类型注册：

::

   文件系统模块初始化
   → 准备 struct file_system_type
   → 设置类型名、fs_flags、上下文入口和 kill_sb
   → register_filesystem
   → 类型出现在内核文件系统注册表
   → VFS 可以按类型名匹配后续 mount 请求

创建挂载实例：

::

   用户发起 mount
   → VFS 找到 file_system_type
   → 初始化 fs_context
   → 解析 mount parameters
   → get_tree 取得后端
   → 文件系统 fill_super
   → 读取并校验持久化 superblock
   → 初始化私有状态和 operation tables
   → 建立根 inode 与根 dentry
   → mount 对象接入 namespace

一次打开后的读路径：

::

   fd lookup 得到 struct file
   → VFS 做通用模式和参数检查
   → file->f_op->read_iter
   → 具体文件系统检查自身状态
   → Page Cache / iomap / direct I/O
   → 文件偏移映射到后端存储
   → 返回字节数或错误

磁盘对象进入内存：

::

   路径查找到目标名字
   → dcache miss 时文件系统 lookup
   → 读取或构造磁盘对象元数据
   → 建立内存 struct inode
   → 连接 operation tables 和 mapping
   → dentry 关联 inode
   → 后续打开创建独立 struct file

卸载实例：

::

   阻止新路径进入目标 mount
   → 检查打开 file、cwd/root、mmap 和子挂载
   → 同步必要数据与元数据
   → 停止后台 worker 和事务
   → 释放 root dentry/inode 与私有状态
   → kill_sb / put_super
   → 解除块设备或后端引用
   → mount 实例最终回收

必须区分
--------

文件系统类型与挂载实例
   ``file_system_type`` 描述一种实现；``super_block`` 描述该实现的一次具体挂载。

VFS 合同与文件系统现实
   VFS 统一系统调用和对象；真实分配、日志、恢复和性能由具体文件系统决定。

磁盘元数据与内存对象
   前者是持久化格式；后者是缓存、锁、引用和操作表组成的运行时视图。

Operation table 与固定调用链
   操作表提供动态分发；同一 VFS 入口会因对象所属文件系统和状态进入不同实现。

``write`` 成功与持久化完成
   Write 返回表示当前写入路径完成；稳定介质语义还要看 fsync、日志、写回和设备顺序。

注册类型与卸载实例
   类型可以继续存在而没有实例；实例未退出时不能安全移除其实现代码。

一句话结论
----------

真实文件系统通过类型注册、挂载实例和多层操作表接入 VFS，而持久化、恢复、空间和性能语义必须继续追到具体文件系统及其后端实现。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 20，Filesystem Implementations ext4, XFS, Btrfs, and Pseudo Filesystems；
* AIBook 章节：Chapter 96，How Real Filesystems Plug into VFS；
* 源文件：``docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_096_How_Real_Filesystems_Plug_into_VFS.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_20_Filesystem_Implementations_ext4_XFS_Btrfs_and_Pseudo_Filesystems/Chapter_096_How_Real_Filesystems_Plug_into_VFS.md>`_。