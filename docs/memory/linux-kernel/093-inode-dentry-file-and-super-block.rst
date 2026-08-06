第093章：inode、dentry、file 与 super_block
==========================================

核心知识点
----------

文件访问由四类对象共同表达
   ``dentry`` 表示名字关系，``inode`` 表示文件系统对象，``file`` 表示打开实例，``super_block`` 表示文件系统实例。它们不能合并为一个“文件对象”。

``struct path`` 还必须携带 mount
   路径解析结果由 mount+dentry 组成。单独 dentry 只能说明文件系统内部名字关系，不能说明该名字位于哪个挂载树位置。

Inode 表示对象级身份与元数据
   ``inode`` 保存类型、权限、所有者、大小、时间戳、链接数、操作表和文件系统私有状态；文件偏移和本次打开标志不属于 inode。

Inode 身份依赖 superblock
   inode number 通常只在所属文件系统实例中有意义。定位对象身份需要把设备或 superblock 与 inode number 结合起来。

一个 inode 可以拥有多个名字
   硬链接让多个 dentry 指向同一个 inode。不同名字共享数据和对象元数据，但位于不同父目录和 dcache 关系中。

Dentry 缓存名字查找结果
   Dentry 的键由父 dentry 与组件名构成。Positive dentry 指向 inode，negative dentry 缓存当前不存在的名字结果。

Dentry 不是磁盘目录项副本
   Rename、unlink、创建、远程重验证和挂载变化都可能改变 dentry 状态。缓存对象的存在只表示内核保留了名字关系，不表示关系永远有效。

``struct file`` 表示一次打开实例
   它保存 ``f_path``、``f_pos``、``f_flags``、``f_mode``、``f_op`` 和 ``private_data``。同一 inode 可以同时拥有多个彼此独立的打开实例。

Dup 与重复 open 的对象关系不同
   ``dup`` 和普通 fork 可以共享同一个 ``struct file``，从而共享偏移和打开状态；重新 open 同一路径通常创建新的 file，偏移彼此独立。

``file->f_op`` 决定打开后的行为
   普通文件、目录、socket、设备和伪文件都通过 ``struct file`` 接入 fd table，但读写、poll、mmap、ioctl 和 release 语义由不同操作表实现。

``super_block`` 表示文件系统实例
   它保存文件系统类型、块大小、根 dentry、实例状态、操作表和私有信息。相同文件系统类型可以创建多个独立 superblock。

Superblock 与 mount 不是同一对象
   Superblock 表示文件系统实例，mount 把该实例的某个根连接到命名空间挂载树。Bind mount 和共享挂载可以让同一底层对象通过多个路径出现。

Unlink 只删除名字关系
   删除目录项会降低链接数并改变 dentry/inode 关系；已打开 file、mmap、其它硬链接和 writeback 可以继续保持 inode 与数据存活。

最后引用结束后才进入 evict
   ``release``、``fput``、dentry 回收和 inode eviction 处于不同阶段。对象被标记删除后，也可能长期等待打开引用、映射、RCU 和文件系统清理结束。

引用保证存活，不保证状态稳定
   Dentry lock、inode ``i_rwsem``、file position lock、folio lock 和 superblock 锁保护不同不变量。取得引用后仍需对应同步协议读取或修改字段。

关键路径
--------

路径到文件系统对象：

::

   用户路径字符串
   → 在 mount namespace 中选择起点
   → 逐组件得到 dentry
   → dentry 连接 inode
   → inode->i_sb 连接 super_block
   → 形成 struct path = mount + dentry

创建打开实例：

::

   路径解析得到 dentry 与 inode
   → 执行权限和打开标志检查
   → 分配 struct file
   → 设置 f_path、f_mode、f_flags 和 f_op
   → 执行具体 open 回调
   → 安装到 fd table

同一 inode 的多种关系：

::

   多个硬链接 dentry 指向 inode X
   → open 名字 A 创建 file F1
   → open 名字 B 创建 file F2
   → F1 与 F2 各自维护打开状态
   → 数据和 inode 元数据仍指向同一对象

Unlink 后延迟销毁：

::

   unlink 删除 dentry 到 inode 的目录关系
   → 链接计数下降
   → 已打开 file 或 mmap 继续持有对象
   → 最后名字、打开实例和映射引用结束
   → 文件系统执行 eviction 和存储回收

挂载实例建立：

::

   file_system_type 创建或取得 super_block
   → 建立文件系统根 dentry
   → mount 把根连接到命名空间挂载点
   → 路径穿越挂载点进入该实例
   → inode 通过 i_sb 归属 super_block

概念辨析
--------

* Dentry 与 inode：Dentry 表示父目录下的名字；inode 表示文件系统对象及其元数据。
* Inode 与 file：Inode 是对象级状态；file 是一次打开的偏移、标志、操作和私有状态。
* Superblock 与 mount：Superblock 表示文件系统实例；mount 表示该实例在命名空间中的挂载关系。
* Positive 与 negative dentry：前者连接 inode；后者缓存当前不存在的名字查找结果。
* Unlink 与对象销毁：Unlink 删除名字；对象可能因打开实例、硬链接和映射继续存活。
* 引用与同步：引用阻止对象释放；锁、RCU 或序列协议保证字段读取和状态转换正确。

本章结论
--------

VFS 用 dentry 表达名字、inode 表达对象、file 表达打开实例、superblock 表达文件系统实例；路径、访问状态和生命周期必须在这些对象之间分别追踪。