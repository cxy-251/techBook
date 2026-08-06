第126章：字符设备注册与 file_operations
=======================================

核心知识点
----------

字符设备用文件语义暴露内核对象
   字符设备可以表达字节流、消息、事件或控制命令。它的共同点是通过 ``struct file`` 分发操作，不是所有字符设备都具有连续字节流语义。

设备号连接路径与驱动入口
   打开路径解析到字符设备 inode 后，``inode->i_rdev`` 提供 ``dev_t``，内核再由 major/minor 找到 ``struct cdev`` 和对应 ``file_operations``。

``cdev`` 只负责注册关系
   ``struct cdev`` 把一段设备号范围连接到操作表，不保存完整硬件状态。驱动通常把它嵌入私有对象，并在 ``open`` 中恢复宿主实例。

发布之前必须完成初始化
   ``cdev_init()`` 只初始化对象，``cdev_add()`` 才建立可打开入口。添加成功后用户态可能立即访问，因此锁、等待队列、状态和引用协议必须预先就绪。

设备节点不是设备本体
   ``/dev`` 节点只是路径和设备号，通常由 devtmpfs 或 udev 创建。节点存在不证明驱动已绑定、硬件在线或操作能够成功。

``inode`` 与 ``file`` 生命周期不同
   Inode 表示设备节点；``struct file`` 表示一次打开实例。多个进程可拥有不同 file，也可通过 ``dup`` 或 ``fork`` 共享同一 file。

``open`` 建立会话所有权
   驱动常在 ``open`` 中取得设备引用，并把设备或会话对象保存到 ``file->private_data``。``release`` 归还该打开实例持有的资源和引用。

读写必须遵守文件返回语义
   ``read`` 和 ``write`` 返回实际传输字节数，短读短写可以合法。阻塞模式在条件不满足时等待，非阻塞模式通常返回 ``-EAGAIN``；用户复制失败要正确处理部分完成和 ``-EFAULT``。

Poll 是就绪协议
   ``poll`` 通过 ``poll_wait()`` 登记等待队列并返回当前就绪掩码，不执行数据传输。状态检查、登记和唤醒必须构成无丢失唤醒的协议。

Ioctl 是长期二进制 ABI
   命令号、结构体布局、字段语义和错误码发布后都需要兼容。输入应先复制到内核缓冲区，再验证版本、flags、保留字段、长度、权限和设备状态。

Mmap 引入独立映射生命周期
   VMA 可以在 fd 关闭后继续存在，因此映射对象必须有独立引用。普通页、vmalloc、DMA buffer 和 MMIO 需要不同映射接口，不能统一通过物理地址强行映射。

删除入口不等于释放对象
   ``cdev_del()`` 只阻止新打开，旧 fd、VMA、IRQ、work、DMA 和异步请求仍可能使用私有对象。最终释放必须等待所有访问路径收束。

关键路径
--------

字符设备注册：

::

   初始化私有对象、锁、等待队列和引用
   → alloc_chrdev_region 申请 dev_t
   → cdev_init 绑定 file_operations
   → cdev_add 发布打开入口
   → 创建 class/device 并发送 uevent
   → devtmpfs/udev 创建 /dev 节点

打开与访问：

::

   用户 open 设备节点
   → VFS 取得字符设备 inode
   → dev_t 查找 struct cdev
   → 安装驱动 file_operations
   → 驱动 open 取得设备引用
   → file->private_data 保存设备或会话
   → read/write/poll/ioctl/mmap
   → release 归还打开引用

安全移除：

::

   设置 disconnected 并阻止新硬件请求
   → 撤销设备节点和用户入口
   → cdev_del 阻止新 open
   → 唤醒阻塞读写和 poll
   → 停止 IRQ、DMA、timer、work 与异步 I/O
   → 旧 fd 返回断开错误
   → 等待 fd、VMA 和对象引用归零
   → 注销设备号并释放私有对象

概念辨析
--------

设备节点与字符设备对象
   设备节点是路径和 ``dev_t``；``cdev``、私有状态与硬件资源才构成实际驱动对象。

``inode`` 与 ``struct file``
   Inode 表示节点身份；file 表示一次打开实例，并保存标志、偏移和 ``private_data``。

``cdev_del`` 与最终释放
   Del 撤销新打开入口；最终释放还要等待已有 file、VMA 和异步执行结束。

阻塞读取与 Poll
   阻塞读取可以睡眠直到条件成立；poll 只登记等待关系并报告当前是否可能推进。

Ioctl 编码与参数安全
   命令宏编码方向和声明大小；驱动仍须验证真实结构版本、范围、权限和状态。

模块引用与设备引用
   ``file_operations.owner`` 保护驱动代码，设备私有对象仍需独立 refcount 或高层对象引用。

本章结论
--------

字符设备通过 ``dev_t`` 和 ``cdev`` 把路径连接到 ``file_operations``；真正正确性取决于打开实例的引用、阻塞与就绪语义、稳定 UAPI，以及移除后旧 fd 和 VMA 的安全收束。
