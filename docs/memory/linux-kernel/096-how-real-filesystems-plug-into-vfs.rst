第096章：真实文件系统如何接入 VFS
=================================

核心知识点
----------

VFS 定义合同，文件系统实现语义
   VFS 统一系统调用入口、对象模型、引用规则和操作表；磁盘布局、空间分配、日志、恢复与性能行为仍由 ext4、XFS、Btrfs 等具体实现决定。

文件系统类型与挂载实例分离
   ``struct file_system_type`` 描述一种可注册实现，``struct super_block`` 描述该实现的一次具体实例。同一类型可以在不同设备、参数和命名空间中建立多个实例。

注册只建立类型可发现性
   ``register_filesystem()`` 把类型加入 VFS 注册表，使 mount 能按名称找到实现。注册完成不表示已经读取设备、创建根目录或形成挂载实例。

挂载通过上下文逐步构造实例
   新挂载路径通常经过 ``fs_context`` 初始化、参数解析、``get_tree`` 和文件系统填充 superblock。块设备文件系统还要取得并校验目标设备。

Superblock 初始化连接持久化格式
   ``fill_super`` 一类阶段读取磁盘 superblock 和 feature bits，建立文件系统私有状态，设置 ``s_op``，并创建根 inode 与根 dentry。

Mount 把实例放入命名空间
   Superblock 表示文件系统实例，mount 对象把其根 dentry 接到某个 mount namespace 的挂载点。二者不是同一个对象，也不必严格一对一。

操作表按对象层分发
   ``super_operations`` 管理实例，``inode_operations`` 管理名字和元数据，``file_operations`` 管理打开实例，``address_space_operations`` 或 iomap 连接缓存页、文件偏移和后端块映射。

公共 helper 不统一最终行为
   文件系统可以复用 ``generic_file_*``、iomap、writeback 等框架。回调前后的锁、事务、分配和错误处理仍会产生不同的一致性与性能语义。

磁盘对象与 VFS 对象生命周期不同
   磁盘 inode、目录项、extent 和日志是持久化格式；内存 inode、dentry、file、folio 和私有结构是运行时视图。缓存对象可被重建，也可能因引用长期保留。

挂载参数是实例策略
   日志模式、压缩、校验和、DAX、discard、权限和错误处理等选项可能改变同一文件系统类型的运行行为。实际值必须从目标挂载实例读取。

Feature bits 决定兼容边界
   文件系统格式中的兼容、只读兼容和不兼容特性决定当前内核能否读写挂载。未知关键特性通常必须拒绝，而不是猜测处理。

持久化保证必须继续追到后端
   ``write()`` 成功通常只表示写路径接受数据。``fsync()`` 的最终保证还依赖文件系统事务、writeback、日志提交、设备 flush 和硬件顺序。

实例退出先于类型注销
   卸载要收束打开文件、映射、cwd/root、后台工作和事务；只有所有实例及回调都结束后，文件系统模块和类型实现才可安全移除。

关键路径
--------

文件系统注册与挂载：

::

   模块准备 file_system_type
   → register_filesystem 建立类型可发现性
   → mount 找到目标类型
   → 创建并配置 fs_context
   → 解析参数并取得设备或后端
   → get_tree / fill_super 初始化 super_block
   → 创建根 inode 与根 dentry
   → mount 接入目标 namespace

VFS 操作分发：

::

   系统调用取得 path、inode 或 struct file
   → VFS 完成公共权限、引用和参数检查
   → 从对应对象读取 operation table
   → 调用具体文件系统回调
   → 文件系统进入私有锁、事务和映射路径
   → 访问 Page Cache、日志或块设备
   → 结果按 VFS errno/返回值合同返回

实例卸载：

::

   从挂载树阻止新路径进入
   → 收束 file、mmap、cwd/root 和子挂载引用
   → 同步数据、元数据和日志
   → 停止 worker 与事务
   → 释放根对象和文件系统私有状态
   → kill_sb / put_super 解除后端
   → 最后回收 mount 与 super_block

概念辨析
--------

* 文件系统类型与挂载实例：类型描述实现；实例描述一次实际挂载及其设备、选项和状态。
* Superblock 与 mount：Superblock 表示文件系统实例；mount 表示该实例在命名空间中的连接位置。
* VFS 对象与磁盘格式：VFS 对象是内存中的运行时视图；磁盘结构是崩溃后仍需解释的持久化状态。
* 公共 helper 与统一语义：复用公共代码减少重复实现，不会消除事务、分配和持久化策略差异。
* ``write`` 完成与稳定介质：前者完成当前写入接口；后者还要求文件系统和设备满足同步顺序。
* 卸载实例与注销类型：实例退出是资源生命周期；类型注销是实现代码生命周期，顺序不能颠倒。

本章结论
--------

真实文件系统通过类型注册、挂载实例和多层操作表接入 VFS；任何空间、恢复或持久化判断都必须从 VFS 合同继续追到具体文件系统及其设备后端。
