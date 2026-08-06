第100章：伪文件系统作为内核接口
================================

核心知识点
----------

伪文件系统复用 VFS 语义
   Procfs、sysfs、debugfs、tracefs、tmpfs 和 devtmpfs 都可通过路径、权限、open、read、write 和 mmap 接入用户空间，但其后端对象与持久化语义不同。

路径形式不能说明数据来源
   一个文件能被读取，只表示它提供 VFS 接口。内容可能动态来自 task、kobject、追踪缓冲区、内存页或设备驱动，而不是磁盘数据块。

Procfs 投影进程与系统状态
   ``/proc/<pid>``、``/proc/meminfo`` 和 ``/proc/sys`` 等路径根据当前任务、namespace 和子系统状态生成视图。结果通常是读取期间的瞬时快照。

Procfs 受 PID namespace 影响
   ``/proc/<pid>`` 的对象集合由 procfs 挂载所关联的 PID namespace 决定。容器只改变 namespace 却复用错误的 procfs 挂载，会得到不匹配的进程视图。

``/proc/sys`` 是控制面
   写入 sysctl 文件会修改运行时内核参数，不是保存普通文本配置。范围、单位、权限与持久化方式由具体参数定义。

Sysfs 投影设备模型
   Sysfs 以 kobject、device、bus、class、driver 和 module 关系组织目录，属性读取进入 ``show()``，写入进入 ``store()``。

Sysfs 属性不是普通文件内容
   属性通常表达一个明确值或动作，不保证支持追加、随机写或保留用户输入文本。写入可能立即触发设备重配置、解绑、电源或策略变化。

Debugfs 不承诺稳定 ABI
   Debugfs 面向开发和诊断，路径、格式和权限可随内核版本改变。生产程序默认不应把它当长期兼容接口。

Tracefs 是专用追踪控制面
   Tracefs 暴露 tracer、event、filter、trigger 和 ring buffer 等接口。它与 debugfs 的历史挂载关系不能混同为相同 ABI。

Tmpfs 保存真实文件内容
   Tmpfs 拥有 dentry、inode、文件数据、权限、mmap 和 truncate 等普通文件语义，只是存储主要来自内存与 swap，卸载或重启后通常消失。

Devtmpfs 提供设备节点入口
   节点保存字符或块设备号，打开后由 major/minor 找到已注册驱动。节点本身不实现设备读写语义。

伪文件读取可能有显著成本
   Seq_file 或属性回调可能遍历任务、设备和内核对象、取得锁并格式化文本。高频监控会增加 CPU、锁竞争和对象生命周期压力。

ABI 等级必须显式确认
   文档化 procfs/sysfs 接口可能属于稳定或测试 ABI；debugfs、日志和部分 trace 文本通常不提供同等级兼容承诺。

命名空间只改变可见视图
   Mount、PID、user 和其它 namespace 会影响路径、对象集合与权限，但不会自动隔离所有主机设备或内核全局状态。

关键路径
--------

读取 procfs 状态：

::

   在当前 mount namespace 解析 /proc 路径
   → procfs 按 PID namespace 定位 task 或系统对象
   → 执行权限、ptrace 与 LSM 检查
   → read / seq_file 回调读取当前内核状态
   → 格式化文本并返回
   → 调用者按瞬时视图解释结果

读写 sysfs 属性：

::

   路径解析到 kernfs/sysfs node
   → 节点关联 kobject 与 attribute
   → 验证对象生命周期和权限
   → read 调用 show 生成当前值
   → write 解析完整输入并调用 store
   → 子系统更新设备或策略
   → 通过状态属性或事件确认异步结果

Tmpfs 文件生命周期：

::

   在 tmpfs mount 中创建 dentry 与 shmem inode
   → 写入时分配内存页
   → 文件可读写、mmap、truncate 或换出
   → 受 mount size、inode、memcg 和系统内存限制
   → unlink 后等待最后引用
   → 卸载或重启后内容消失

打开 devtmpfs 设备节点：

::

   路径查找到字符或块设备节点
   → inode 提供 major/minor
   → VFS 查找已注册设备
   → 创建 struct file 并选择驱动操作表
   → read/write/ioctl/poll 分发到驱动
   → close 收束驱动私有状态与引用

概念辨析
--------

* 伪文件系统与磁盘文件系统：二者都走 VFS；伪文件后端可以是动态内核对象而非持久化块。
* Procfs 与 sysfs：Procfs 主要投影进程和系统状态；sysfs 主要投影 kobject 与设备模型关系。
* Sysfs 与 debugfs：文档化 sysfs 属性可形成用户 ABI；debugfs 默认只服务开发诊断。
* Tracefs 与 debugfs：Tracefs 专门承载追踪控制和数据；不能按 debugfs 普通调试文件解释其状态机。
* Tmpfs 与动态属性文件：Tmpfs 保存用户写入的真实文件内容；procfs/sysfs 多在读取时生成内容。
* Devtmpfs 节点与设备驱动：节点提供设备号和路径入口；实际操作语义由驱动实现。

本章结论
--------

Linux 的“一切皆文件”主要表示不同内核对象可以复用 VFS 接口；正确使用伪文件系统必须同时确认后端对象、ABI 等级、命名空间、权限与生命周期。
