第092章：VFS 作为文件系统抽象层
===============================

本章必须记住
------------

#. VFS 位于系统调用与具体文件系统之间，为不同文件系统提供统一的对象模型、入口和缓存框架。
#. ext4、XFS、Btrfs、tmpfs、procfs、NFS 等实现不同，但都通过 VFS 接受常见文件接口。
#. VFS 不是把所有文件系统实现成相同算法，而是统一调用边界并保留具体实现的策略差异。
#. VFS 核心对象包括 ``struct super_block``、``struct inode``、``struct dentry``、``struct file`` 和 ``struct path``。
#. ``super_block`` 表示已挂载文件系统实例，``inode`` 表示文件系统对象，``dentry`` 表示名字关系，``file`` 表示打开实例。
#. 路径名调用和 fd 调用的第一批对象不同，阅读源码必须先判断入口类型。
#. ``open(path)``、``stat(path)``、``unlink(path)`` 等首先进入路径解析，目标是获得 dentry、inode 或父目录关系。
#. ``read(fd)``、``write(fd)``、``ioctl(fd)`` 等首先从 fd table 得到 ``struct file``，通常不重新解析原路径。
#. ``openat``、``openat2`` 等还携带目录 fd、解析标志和相对路径起点语义。
#. VFS 系统调用通常运行在进程上下文，可访问 ``current``、凭据、fd 表、命名空间、cwd 和 root。
#. 普通 VFS 路径可能睡眠，等待内存、inode 锁、folio 锁、设备 I/O、远程文件系统或文件系统事务。
#. 持 spinlock、硬中断或其它原子上下文不能无条件调用可能睡眠的 VFS 路径。
#. 用户路径字符串和用户缓冲区必须通过 uaccess 或 ``iov_iter`` 等受控机制跨越用户/内核边界。
#. VFS 公共路径执行 fd lookup、路径解析、权限检查、引用管理、锁协调和返回值规范化。
#. 具体文件系统负责目录 lookup、数据读写、属性更新、日志、块映射、网络一致性或伪文件内容生成。
#. VFS 通过 C 结构体中的函数指针表实现多态。
#. ``struct file_operations`` 处理打开实例上的 ``read_iter``、``write_iter``、``llseek``、``mmap``、``fsync``、``poll``、``ioctl``、``release`` 等操作。
#. ``struct inode_operations`` 处理名字与元数据层面的 ``lookup``、``create``、``link``、``unlink``、``rename``、``getattr``、``setattr`` 等操作。
#. ``struct super_operations`` 处理挂载实例级 inode 生命周期、同步、冻结、统计和卸载相关动作。
#. ``struct address_space_operations`` 连接 inode 的 Page Cache 与文件系统后端读入、写回和失效路径。
#. ``dentry_operations`` 允许文件系统控制 dentry revalidate、hash、compare、release 等名字缓存行为。
#. 回调表字段是否存在、函数签名和具体调用点会随内核版本演进，稳定方法是从对象职责追踪分发。
#. ``file->f_op`` 是打开时确定或替换的操作表；后续 fd I/O 通常沿该表进入具体实现。
#. ``inode->i_op`` 服务 inode 和目录名字操作；不能用 file operations 替代路径查找语义。
#. 普通文件、目录、字符设备、socket、pipe 和 procfs 条目都能以 ``struct file`` 接入，但操作表完全不同。
#. VFS 的统一接口不表示所有对象都支持所有操作；不支持的回调会返回对应错误或使用通用 fallback。
#. ``read_iter`` 返回字节数、0 或负错误码；短读不一定是错误，必须按接口语义处理。
#. ``write_iter`` 成功写入部分数据也可能返回短写，调用者必须决定是否继续。
#. 内核内部通常使用负 errno 传播错误，系统调用边界再转换为用户态 ``-1`` 与 ``errno``。
#. ``ENOENT``、``ENOTDIR``、``EACCES``、``EROFS``、``EIO`` 等错误对应不同 VFS 或文件系统阶段。
#. VFS 缓存主要包括 dentry cache、inode cache 和 Page Cache，它们缓存不同层次的结果。
#. dcache 缓存父目录与名字的查找结果，包括不存在目标的 negative dentry。
#. inode cache 缓存文件系统对象元数据和内核对象状态，不等于目录名字缓存。
#. Page Cache 缓存文件内容，和 dentry/inode 元数据缓存不是同一层。
#. mount cache 与挂载树让路径在遇到挂载点时切换到另一个文件系统实例。
#. 缓存命中减少目录 I/O 和对象重建，仍需按文件系统一致性规则进行 revalidate。
#. 本地文件系统通常能较强地信任 dcache；NFS 等远程文件系统可能频繁要求重新验证。
#. VFS 缓存占用内存不等于泄漏，回收器会在压力下通过 shrinker 等机制回收可释放元数据对象。
#. 缓存对象是否可回收取决于引用、脏状态、挂载、打开实例、RCU 和文件系统私有生命周期。
#. 文件系统模块注册 ``struct file_system_type``，使 VFS 能识别文件系统名称并调用挂载/初始化入口。
#. 挂载成功会建立文件系统上下文、superblock、根 dentry 和 mount 对象关系。
#. 同一种文件系统类型可以存在多个挂载实例，每个实例拥有自己的 ``super_block`` 和挂载状态。
#. 一个 superblock 可被一个或多个 mount 关系引用，mount 与 superblock 不能机械视为一对一。
#. 文件系统的磁盘格式和 VFS 内存对象不是同一层；inode number、目录项和 superblock 字段还要经过具体实现映射。
#. VFS 权限检查同时依赖 task credentials、inode mode/ACL、mount 属性、LSM 和 idmapped mount 等规则。
#. 只读文件权限允许不代表挂载可写，也不代表 LSM 允许操作。
#. 路径解析成功也不代表最终 ``open`` 成功；打开标志、lease、锁、设备状态和文件系统回调还会继续失败。
#. fd 查找成功也不代表读写成功；``f_mode``、操作支持、用户缓冲区、I/O 和后端状态都可能产生错误。
#. ``stat`` 主要读取对象元数据，``read`` 主要使用打开实例和数据路径，二者不能按同一调用链理解。
#. ``chmod(path)`` 需要路径解析和 inode 属性更新，``fchmod(fd)`` 从已有打开实例定位对象。
#. VFS 锁的作用域不同：目录 inode 锁、dentry 锁、file position 锁、folio 锁和 superblock 锁不能互相替代。
#. 路径查找可使用 RCU-walk 快路径，并在需要睡眠、重验证或状态不稳定时退到 REF-walk。
#. VFS 对象生命周期广泛使用引用计数、RCU、锁和延迟释放；取得指针后必须遵守对应保护规则。
#. 删除路径名不一定立即销毁 inode；打开 file、mmap、其它硬链接和内核引用都可能继续保持对象。
#. 卸载文件系统前必须停止新访问并收束打开文件、cwd/root、映射、子挂载和内核内部引用。
#. 具体文件系统崩溃、I/O 错误或远程断连会沿回调返回到 VFS，VFS 不会自动消除后端故障。
#. 分析一次 VFS 请求时，应同时记录 syscall、路径或 fd、进程凭据、mount namespace、对象类型和具体文件系统。
#. 源码阅读应先定位公共入口，再沿 operation table 找具体回调，最后追踪文件系统内部对象和后端。
#. 只搜索具体文件系统函数容易漏掉 VFS 已完成的权限、引用、缓存和路径语义。
#. 只停留在 VFS 公共函数也无法解释磁盘布局、事务、网络一致性和设备错误。
#. 最稳定的 VFS 阅读顺序是：系统调用输入 → 通用 VFS 对象 → 公共检查 → operation table → 具体文件系统 → 后端。

必背路径
--------

路径名打开：

::

   用户调用 openat2(path)
   → 复制并解析路径参数
   → 选择 root / cwd / dirfd 起点
   → VFS 逐组件路径查找
   → dcache 命中或 inode->i_op->lookup
   → 得到目标 dentry 与 inode
   → 执行权限和打开标志检查
   → 创建 struct file 并选择 f_op
   → 安装到 fd table
   → 返回 fd

fd 读路径：

::

   用户调用 read(fd)
   → 当前 files_struct 查 fd
   → 取得 struct file
   → 检查 f_mode 与位置
   → VFS 通用读入口
   → file->f_op->read_iter
   → 文件系统 / 设备 / socket 实现
   → 返回字节数或错误

元数据查询：

::

   用户调用 statx(path)
   → 路径解析得到 struct path
   → 找到 dentry 与 inode
   → 通用属性和权限处理
   → 必要时 inode_operations->getattr
   → 具体文件系统填充属性
   → VFS 转换为用户 ABI
   → copy_to_user 返回

回调分发：

::

   VFS 公共入口取得通用对象
   → 判断对象类型和操作是否存在
   → 从 file / inode / superblock 读取操作表
   → 调用具体函数指针
   → 具体实现更新私有状态
   → 返回统一 errno 或结果
   → 公共层完成引用和锁收尾

诊断 VFS 请求：

::

   确认 syscall 与参数类型
   → 路径请求检查 namespace / root / cwd
   → fd 请求检查 fdtable / struct file
   → 确认 dentry / inode / superblock
   → 找到实际 operation table 回调
   → 对齐文件系统日志、trace 和后端 I/O
   → 确认错误产生阶段

必须区分
--------

VFS 与具体文件系统
   VFS 提供公共对象和入口；具体文件系统实现 lookup、数据、元数据和持久化策略。

路径名调用与 fd 调用
   前者先解析 dentry/inode；后者先从 fd table 取得已有 ``struct file``。

``file_operations`` 与 ``inode_operations``
   前者服务打开实例上的 I/O；后者服务名字查找和对象元数据操作。

Dcache、inode cache 与 Page Cache
   它们分别缓存名字关系、对象元数据和文件内容。

文件系统类型与挂载实例
   ``file_system_type`` 表示实现类型；``super_block`` 表示具体已挂载实例。

统一接口与统一行为
   相同 VFS 调用边界可以进入完全不同实现，错误、性能和一致性仍由具体对象和后端决定。

一句话结论
----------

VFS 用统一对象模型、公共检查和函数指针表把系统调用分发给不同文件系统，实现“统一入口、分层对象、具体策略”的文件访问框架。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 19，File Descriptors, VFS, Inode, Dentry, and Superblock；
* AIBook 章节：Chapter 92，VFS as the Filesystem Abstraction Layer；
* 源文件：``docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_092_VFS_as_the_Filesystem_Abstraction_Layer.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_092_VFS_as_the_Filesystem_Abstraction_Layer.md>`_。