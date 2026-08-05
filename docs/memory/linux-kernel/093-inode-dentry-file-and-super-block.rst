第093章：inode、dentry、file 与 super_block
==========================================

本章必须记住
------------

#. 一次文件访问至少要区分名字、文件系统对象、打开实例和已挂载文件系统实例四个层次。
#. ``struct dentry`` 表达“某父目录下某名字的查找结果”。
#. ``struct inode`` 表达“这个文件系统对象是什么以及它的元数据和实现状态”。
#. ``struct file`` 表达“某次打开如何访问该对象”。
#. ``struct super_block`` 表达“这些对象属于哪个已挂载文件系统实例”。
#. 路径名先解析成 ``struct path``，其中包含 mount 和 dentry；dentry 再连接 inode。
#. ``open`` 成功后创建或取得 ``struct file``，后续 fd I/O 主要围绕该打开实例进行。
#. ``inode`` 可表示普通文件、目录、符号链接、设备节点、FIFO、socket inode 等文件系统对象。
#. ``inode`` 保存对象级权限、类型、所有者、大小、时间戳、链接数和文件系统私有状态。
#. ``inode->i_mapping`` 连接对象与 ``struct address_space``，普通文件数据由该映射管理 Page Cache。
#. ``inode->i_op`` 指向名字和元数据操作，``inode->i_fop`` 常提供默认打开后文件操作。
#. ``inode->i_sb`` 把对象放回所属 ``super_block``。
#. inode number 通常只在对应文件系统实例中具有身份意义，不能脱离 superblock 单独当作全局唯一 ID。
#. 一个 inode 可以被多个 dentry 指向，硬链接正是多个名字连接同一文件系统对象。
#. 硬链接共享 inode 的数据、权限、大小和链接计数，但每个名字拥有独立 dentry 位置。
#. inode 不保存某次 open 的文件偏移；偏移属于 ``struct file``。
#. 多次打开同一个 inode 可以创建多个 ``struct file``，各自拥有独立 ``f_pos`` 和打开状态。
#. 具体文件系统常把通用 ``struct inode`` 嵌入私有 inode 结构，用 ``container_of`` 取得扩展状态。
#. VFS 管理通用 inode 生命周期节点，具体文件系统负责填充、写回、回收和私有资源清理。
#. inode cache 中存在对象不表示磁盘元数据永远最新；远程和特殊文件系统可能要求 revalidate。
#. ``struct dentry`` 绑定父 dentry、组件名、目标 inode 和 dcache 生命周期状态。
#. dentry 是名字缓存项，不是磁盘目录项的简单永久镜像。
#. Positive dentry 指向有效 inode；negative dentry 表示该父目录下该名字当前未找到对象。
#. Negative dentry 能缓存 ``ENOENT`` 查找结果，减少重复目录 lookup。
#. 创建文件时，已有 negative dentry 可以转为连接新 inode 的 positive dentry。
#. unlink、rename、mount 和远程重验证都会改变 dentry 与 inode 的关系或有效性。
#. dcache key 的核心是父目录与名字；相同字符串位于不同父目录时是不同查找关系。
#. dentry 可以因打开 file、cwd/root、mount、路径引用或 RCU 生命周期继续存在。
#. 删除路径名不等于 dentry、inode 或打开文件立刻销毁。
#. 已打开但 unlink 的文件仍可通过 ``struct file`` 继续读写，直到最后引用消失。
#. ``struct file`` 是 open file description 的内核对象，保留本次打开状态。
#. ``file->f_path`` 保存打开对象对应的 mount+dentry 位置，``file->f_inode`` 可快速定位 inode。
#. ``file->f_flags`` 保存 ``O_APPEND``、``O_NONBLOCK`` 等 open file status flags。
#. ``file->f_mode`` 保存内核解释后的读写和能力模式，不能只靠用户原始 flags 判断。
#. ``file->f_op`` 决定读写、poll、mmap、ioctl、fsync 和 release 等打开实例操作。
#. ``file->private_data`` 常由具体文件系统、驱动、socket 或伪文件系统保存实例私有状态。
#. 通过 ``dup`` 或 fork 共享同一 ``struct file`` 时，偏移、状态标志和私有打开状态也被共享。
#. 同一路径重新 open 得到新 ``struct file``，即使 dentry 和 inode 相同，打开状态仍可独立。
#. ``struct file`` 的生命周期由引用计数管理，fd table 只是可能的引用来源之一。
#. 最后 ``fput`` 会调用 ``file_operations->release`` 等清理，再释放路径和 inode 相关引用。
#. ``release`` 通常在最后打开引用消失时调用，不等于每个 fd close 都调用一次。
#. ``struct super_block`` 表示一个 mounted filesystem instance 的 VFS 视图。
#. superblock 保存文件系统类型、块大小、魔数、状态、根 dentry、操作表和文件系统私有信息。
#. ``super_block->s_root`` 是该文件系统实例的根 dentry，不等于进程看到的全局根路径。
#. ``super_block->s_op`` 处理 inode 分配/销毁、同步、冻结、统计和 evict 等实例级操作。
#. ``super_block->s_fs_info`` 常保存具体文件系统的实例私有结构。
#. 同一文件系统类型可以创建多个 superblock 实例，例如多个 ext4 分区或多个 tmpfs 挂载。
#. Mount 对象把某个 superblock 的根连接到命名空间中的挂载点。
#. Mount 与 superblock 不是必然一对一；bind mount 或共享挂载关系可能复用已有对象关系。
#. 进程路径解析必须同时携带 mount 与 dentry，因为单独 dentry 无法表达挂载树位置。
#. 同一 superblock 中的 inode 可以通过不同 mount 路径在命名空间中出现。
#. Superblock 只读、冻结、错误和 shutdown 状态会影响整个文件系统实例的操作。
#. Sync 文件数据不只涉及 ``struct file``，还可能进入 inode、address_space、superblock 和设备层。
#. 文件对象生命周期常见链是：dentry 引用 inode，file 引用 path，mount 引用 superblock，但实际引用关系有更多分支。
#. 引用计数证明对象存活，不自动保证对象内容不并发变化；还需要锁、RCU、序列计数或文件系统协议。
#. Dentry lock、inode ``i_rwsem``、file position lock、folio lock 和 superblock 锁保护不同不变量。
#. RCU path walk 中看到 dentry/inode 指针必须遵守 RCU 和序列验证规则，不能离开保护后继续使用裸指针。
#. Inode 被标记删除后仍可能因 open file、mmap、写回和 RCU 使用而延迟 evict。
#. Evict inode 表示 VFS 缓存对象进入最终清理，不等价于普通 unlink 系统调用完成时刻。
#. 文件系统崩溃恢复、NFS stale handle 和动态伪文件都会改变对象从后端重新验证的方式。
#. Procfs/sysfs 等伪文件系统的 inode 和 dentry 仍使用 VFS 对象模型，但内容可能由回调动态生成。
#. Socket fd 使用 ``struct file`` 接入 fd table，但底层不是普通磁盘文件，必须继续沿 socket 操作理解。
#. 目录 ``struct file`` 可以保存 readdir 位置和私有迭代状态，目录 inode 则保存目录对象元数据。
#. Pathname、fd、inode number 和设备号是不同句柄，不能互相无条件替代。
#. ``stat`` 返回的是某时刻对象元数据快照，不包含打开实例完整状态。
#. ``/proc/<pid>/fdinfo`` 展示部分 file 状态，``stat``/``statx`` 展示 inode/path 属性，两者观察层次不同。
#. 调试“同一路径不同内容”时，应检查 mount namespace、dentry 目标、inode identity、open file 是否仍指向旧对象。
#. 调试“文件删除但空间未释放”时，应寻找仍打开的 file、mmap、硬链接和文件系统延迟释放状态。
#. 调试 dentry/inode cache 增长时，应区分有效缓存、negative dentry、不可回收引用和文件系统私有对象。
#. 最稳定对象阅读顺序是：mount namespace → ``struct path`` → dentry 名字 → inode 对象 → file 打开实例 → superblock 实例。

必背路径
--------

路径到对象：

::

   用户路径字符串
   → 选择 mount namespace 中的起点
   → 逐组件查找 dentry
   → dentry 连接目标 inode
   → inode 连接所属 super_block
   → 最终得到 struct path = mount + dentry

打开实例：

::

   路径查找得到 dentry 与 inode
   → 检查权限和打开标志
   → 分配 struct file
   → 保存 f_path / f_inode / f_flags / f_mode
   → 选择 file->f_op
   → 执行文件系统 open 回调
   → 安装 fd

同一对象多次打开：

::

   路径 A 和路径 B 可能是硬链接
   → 各自 dentry 指向同一 inode
   → open A 创建 struct file X
   → open B 创建 struct file Y
   → X 与 Y 各自维护 f_pos
   → 数据和 inode 元数据仍然共享

Unlink 后继续访问：

::

   unlink 移除名字到 inode 的目录关系
   → 链接计数减少
   → 已打开 struct file 继续持有 path/inode
   → fd 仍可读写旧对象
   → 最后 file、mmap 和硬链接引用消失
   → 文件系统 evict 并回收数据

挂载实例关系：

::

   file_system_type 创建文件系统实例
   → 建立 super_block
   → 建立 s_root dentry
   → mount 把根连接到命名空间挂载点
   → 路径穿越挂载点进入该 root
   → inode 通过 i_sb 归属该实例

必须区分
--------

Dentry 与 Inode
   Dentry 表达父目录下的名字关系；inode 表达文件系统对象及其元数据。

Inode 与 ``struct file``
   Inode 是对象级状态；file 是一次打开的偏移、标志、操作和私有状态。

Superblock 与 Mount
   Superblock 表示文件系统实例；mount 把实例放进具体命名空间挂载树。

路径删除与对象销毁
   Unlink 删除名字关系；打开实例、硬链接和映射可以继续保持 inode 与数据。

Positive 与 Negative dentry
   前者连接 inode；后者缓存当前不存在的名字查找结果。

引用存活与状态稳定
   引用保证对象内存不释放；对象字段的一致读取仍需要对应并发保护。

一句话结论
----------

VFS 用 dentry 表达名字、inode 表达文件系统对象、file 表达打开实例、superblock 表达挂载实例，四者共同构成文件访问与生命周期。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 19，File Descriptors, VFS, Inode, Dentry, and Superblock；
* AIBook 章节：Chapter 93，inode, dentry, file, and super_block；
* 源文件：``docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_093_inode_dentry_file_and_super_block.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_19_File_Descriptors_VFS_Inode_Dentry_and_Superblock/Chapter_093_inode_dentry_file_and_super_block.md>`_。