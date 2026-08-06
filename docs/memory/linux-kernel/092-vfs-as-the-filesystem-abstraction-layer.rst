第092章：VFS 作为文件系统抽象层
===============================

核心知识点
----------

VFS 统一接口而不统一实现
   VFS 位于系统调用与具体文件系统之间，为 ext4、XFS、Btrfs、tmpfs、procfs、NFS 等提供共同对象模型和调用边界，同时保留各自的数据布局、一致性和持久化策略。

核心对象承载不同层次
   ``super_block`` 表示文件系统实例，``inode`` 表示文件系统对象，``dentry`` 表示名字关系，``file`` 表示打开实例，``path`` 用 mount+dentry 表示命名空间中的位置。

路径调用与 fd 调用入口不同
   ``open()``、``stat()``、``unlink()`` 先执行路径解析；``read()``、``write()``、``ioctl()`` 先从 fd table 取得已有 ``struct file``，通常不会重新解析最初路径。

VFS 请求通常运行在进程上下文
   公共路径可以访问 ``current``、凭据、cwd、root、fd 表和 mount namespace，也可能等待锁、内存、文件系统事务、远程响应或设备 I/O。

公共层负责通用语义
   VFS 处理用户参数、fd lookup、路径解析、权限检查、引用管理、锁协调和 errno 传播，再把对象特定工作交给 operation table。

函数指针表实现文件系统多态
   ``file_operations`` 服务打开实例 I/O，``inode_operations`` 服务名字与元数据操作，``super_operations`` 服务实例级管理，``address_space_operations`` 连接 Page Cache 与后端，``dentry_operations`` 控制名字缓存行为。

``file_operations`` 面向打开实例
   ``read_iter``、``write_iter``、``llseek``、``mmap``、``fsync``、``poll``、``ioctl`` 和 ``release`` 等回调围绕 ``struct file`` 的状态运行。

``inode_operations`` 面向对象与目录关系
   ``lookup``、``create``、``link``、``unlink``、``rename``、``getattr`` 和 ``setattr`` 等操作处理名字、目录和 inode 元数据，不能由 file operations 替代。

缓存分属三个不同层次
   Dcache 缓存父目录与名字的解析结果，inode cache 缓存对象元数据，Page Cache 缓存文件内容。三者的命中、失效与回收条件不同。

挂载树参与路径语义
   Mount 对象把文件系统根接入 mount namespace。路径越过挂载点时，当前 ``path`` 会切换到另一 mount 和 superblock，不能只靠 dentry 判断位置。

统一入口不保证操作支持
   普通文件、目录、字符设备、socket、pipe 和伪文件都能通过 ``struct file`` 接入 VFS，但各自 ``f_op`` 不同；缺失或不支持的操作会返回对应错误。

短 I/O 属于正常返回模型
   ``read_iter`` 和 ``write_iter`` 可以返回部分字节数。正数表示已完成进度，0 和负 errno 具有各自语义，调用者不能把短读写自动视为故障。

缓存对象仍受生命周期约束
   Dentry、inode、file 和 superblock 广泛使用引用计数、RCU、锁和延迟释放。引用保证存活，不自动保证字段状态稳定。

删除名字不等于销毁对象
   Unlink 只改变名字到 inode 的关系。打开 file、mmap、硬链接、writeback 和其它内核引用可以继续保持 inode 与数据存活。

VFS 不能屏蔽后端故障
   文件系统错误、远程断连、日志中止和块设备 I/O 失败会沿具体回调返回公共层。VFS 只规范边界，不消除实现差异和后端错误。

关键路径
--------

路径名打开：

::

   openat2(path)
   → 选择 root、cwd 或 dirfd 起点
   → 逐组件路径解析
   → dcache 命中或 inode->i_op->lookup
   → 得到 dentry 与 inode
   → 权限和打开标志检查
   → 创建 struct file 并选择 f_op
   → 安装到 fd table

fd 读路径：

::

   read(fd)
   → files_struct 查找 fd
   → 取得 struct file
   → VFS 公共读检查
   → file->f_op->read_iter
   → 文件系统、设备或 socket 实现
   → 返回字节数或错误

元数据查询：

::

   statx(path)
   → 路径解析得到 struct path
   → 定位 dentry 与 inode
   → 通用属性和权限处理
   → 必要时调用 inode_operations->getattr
   → 转换为用户 ABI 并返回

操作表分发：

::

   公共入口取得 VFS 对象
   → 校验对象类型和操作能力
   → 读取对应 operation table
   → 调用具体回调
   → 实现层更新私有状态
   → 公共层完成引用、锁和返回值收尾

概念辨析
--------

* VFS 与具体文件系统：VFS 提供公共对象与入口；具体实现决定 lookup、数据、元数据和持久化策略。
* 路径调用与 fd 调用：前者先得到 ``path``、dentry 和 inode；后者先得到已有 ``struct file``。
* ``file_operations`` 与 ``inode_operations``：前者处理打开实例；后者处理名字关系和对象元数据。
* Dcache、inode cache 与 Page Cache：分别缓存名字、对象元数据和文件内容。
* 文件系统类型与 superblock：类型表示实现；superblock 表示一个具体文件系统实例。
* 统一接口与统一行为：相同系统调用可以进入完全不同的后端实现、错误路径和性能模型。

本章结论
--------

VFS 通过统一对象模型、公共检查和 operation table，把系统调用分发给具体文件系统；稳定阅读顺序是公共入口、VFS 对象、回调表、具体实现和后端。