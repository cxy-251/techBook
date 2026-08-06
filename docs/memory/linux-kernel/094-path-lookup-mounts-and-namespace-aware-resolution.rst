第094章：路径查找、挂载与命名空间感知解析
========================================

本章必须记住
------------

#. 路径字符串不是文件对象；它必须在调用进程的根目录、cwd、dirfd、mount namespace 和挂载树中执行解析。
#. 相同字符串在不同进程、不同 mount namespace 或不同 root 下可以指向不同对象。
#. VFS 用 ``struct path`` 表示解析中的位置，它由 mount 与 dentry 共同组成。
#. 单独 dentry 只表达某文件系统内部名字关系，不能说明该 dentry 在挂载树中的位置。
#. 绝对路径从调用进程的有效 root 开始；相对路径从 cwd 或 ``*at`` 调用提供的 dirfd 开始。
#. ``AT_FDCWD`` 表示使用当前工作目录作为相对路径起点。
#. ``openat2`` 的 resolve flags 可以限制符号链接、mount crossing、``..``、magic link 等行为，具体语义按 UAPI 定义。
#. 路径解析按组件逐级推进，不会一次性把整个字符串转换成 inode。
#. 每一步都要判断当前组件、当前目录、权限、dcache、文件系统 lookup、挂载点和符号链接状态。
#. ``struct nameidata`` 一类内部状态保存当前 path、剩余组件、查找标志和符号链接处理状态。
#. 普通中间组件必须解析为可搜索目录，否则常见 ``ENOENT`` 或 ``ENOTDIR``。
#. 目录 execute/search 权限决定能否穿过目录，不等同于目录内容的 read/list 权限。
#. 最终组件由具体 syscall 决定语义：查找现有对象、创建新对象、删除、重命名或要求目录。
#. ``open(path, O_CREAT)`` 可以允许最终组件不存在，但中间目录仍必须存在且可搜索。
#. 尾部斜杠通常要求最终结果按目录语义处理，不能当作无意义字符忽略。
#. 路径查找先查 dcache，命中时可走内存快路径。
#. dcache 的查找键核心是父 dentry 与组件名，而不是全路径字符串。
#. Positive dentry 表示名字已解析到 inode；negative dentry 表示当前未找到对象。
#. Negative dentry 可以加速重复失败查找，也必须在创建、重命名或远程状态变化时更新/重验证。
#. dcache miss 会进入具体目录 inode 的 ``lookup`` 回调，由文件系统解释目录内容。
#. 本地文件系统通常能较稳定地缓存名字结果；远程文件系统可能使用 ``d_revalidate`` 等机制检查有效性。
#. dcache 命中不等于整个组件处理结束，还要检查权限、mount crossing、符号链接和查找标志。
#. 路径查找存在 RCU-walk 与 REF-walk 等实现模式，函数名和细节随版本演进。
#. RCU-walk 优先使用 RCU 和序列验证读取缓存，避免频繁引用计数和重锁。
#. 需要睡眠、文件系统慢路径、重验证或观察不稳定时，路径查找会退到更保守的 REF-walk。
#. 从 RCU-walk 退回后必须重新验证路径状态，不能继续使用先前未经稳定引用保护的判断。
#. Rename、unlink、mount、unmount 和目录修改可与 lookup 并发，路径状态必须通过锁和序列机制验证。
#. 解析到挂载点 dentry 后，VFS 会检查是否有 mounted filesystem 覆盖该位置。
#. Mount crossing 会把当前 ``struct path`` 从旧 mount+dentry 切换到新 mount 的 root dentry。
#. 同一路径组件在 mount crossing 前后属于不同 superblock 与 inode 空间。
#. Bind mount 把已有目录树的某个位置重新暴露到另一个挂载点，不复制文件内容。
#. 同一 inode/dentry 关系可以通过不同 mount 路径在一个或多个 namespace 中出现。
#. Mount namespace 隔离进程看到的挂载树，不直接复制底层文件系统数据。
#. ``/proc/<pid>/mountinfo`` 是观察目标进程挂载关系的主要证据，主机自己的 ``mount`` 输出不能替代它。
#. ``/proc/<pid>/root``、``cwd`` 和 ``mountinfo`` 共同决定该进程解释路径的起点与挂载视图。
#. 容器中的 ``/etc/hosts``、``/proc`` 或配置路径可能由 bind mount、tmpfs 或运行时注入，和宿主机同名路径不同。
#. ``chroot`` 改变进程路径解析根，但不自动提供 mount namespace 隔离或完整安全沙箱。
#. ``pivot_root``、容器 runtime 和 mount namespace 会共同改变可见根与挂载树。
#. ``..`` 不是简单读取 dentry parent；到达 mount root 时还要考虑 mounted-on dentry 和进程 root 边界。
#. 解析 ``..`` 不能越过调用进程的有效 root，即使挂载树在外部还有父层次。
#. Bind mount、mount root 和 namespace 会让 ``..`` 的实际结果依赖当前 ``struct path``。
#. ``.`` 通常保持当前位置，但仍位于当前 mount+dentry 上下文。
#. 符号链接保存的是另一段路径文本，解析时会把目标重新注入路径查找过程。
#. 绝对符号链接目标从调用进程 root 重新开始，非宿主机全局根。
#. 相对符号链接目标从符号链接所在目录解释，不从调用者原 cwd 重新开始。
#. 符号链接可以跨目录和挂载点，因此会改变后续对象链。
#. 内核限制符号链接解析深度，循环或过深链通常返回 ``ELOOP``。
#. 最终组件是否跟随符号链接取决于 syscall 和 flags，例如 ``O_NOFOLLOW``、``AT_SYMLINK_NOFOLLOW``。
#. Procfs magic links 可能表达内核对象引用而不只是普通文本链接，安全敏感路径应使用 ``openat2`` 限制。
#. Path traversal 安全不能只做字符串去除 ``..``；符号链接、bind mount、rename 和 namespace 都会改变真实路径。
#. 安全打开应把可信目录 fd 作为锚点，并使用内核提供的解析约束，而不是先字符串拼接再验证。
#. 路径查找中的权限检查依赖每个目录组件、目标对象、凭据、ACL、LSM 和 mount 属性。
#. Idmapped mount 会改变 inode UID/GID 在该 mount 视图中的权限解释，不能只看磁盘原始数值。
#. 文件系统 casefold、Unicode、加密目录和远程名称规则会影响组件比较，不能假设所有 lookup 都是字节串直接比较。
#. 路径解析得到 ``struct path`` 后，对象仍可能在后续操作前被 rename 或 unlink；内核依靠引用和锁保证对象操作语义。
#. 已打开 file 通常不再依赖原路径字符串；rename 后 fd 仍指向原打开对象。
#. ``/proc/<pid>/fd/<n>`` 显示的是内核当前可表示的路径视图，不一定等于最初 open 时传入的字符串。
#. ``realpath`` 结果是某时刻用户态解析视图，不能作为后续无竞态安全打开的授权证明。
#. 路径性能问题应区分 dcache 命中、文件系统 lookup、远程 revalidate、符号链接、mount crossing 和权限检查。
#. 大量随机不存在名字会制造 negative dentry 与目录 lookup 压力，不只是数据 I/O 问题。
#. 热路径被频繁 rename 或 mount 修改会导致序列重试和 RCU-walk fallback。
#. 诊断相同路径结果不一致时，应同时保存 PID、namespace inode、root、cwd、dirfd、mountinfo 和 syscall flags。
#. 最稳定的路径阅读顺序是：选择起点 → 拆组件 → dcache/lookup → 权限 → mount crossing → symlink/``..`` → 最终组件语义。

必背路径
--------

普通路径解析：

::

   用户传入 pathname
   → 判断绝对路径或相对路径
   → 选择 root / cwd / dirfd 起点
   → 建立 nameidata 与当前 struct path
   → 拆出下一个组件
   → 查询 dcache
   → 未命中时调用文件系统 lookup
   → 检查目录权限与组件类型
   → 检查挂载点并更新 mount+dentry
   → 重复直到最终组件

Mount crossing：

::

   当前目录中查到目标 dentry
   → 检查该 dentry 是否为挂载点
   → 在当前 mount namespace 查覆盖 mount
   → 取得新 mount 引用
   → 当前 path 切换到新 mount 的 root dentry
   → 后续组件在新 superblock 中解释

符号链接：

::

   当前组件解析为 symlink inode
   → 检查是否允许跟随
   → 取得链接目标文本
   → 检查深度与循环限制
   → 绝对目标从进程 root 开始
   → 相对目标从链接所在目录开始
   → 将剩余路径继续解析

处理 ``..``：

::

   遇到 .. 组件
   → 检查是否已到进程 root
   → 若在普通目录则走父 dentry
   → 若在 mount root 则回到 mounted-on path
   → 按 namespace 和 root 边界验证
   → 更新当前 struct path
   → 继续下一组件

诊断路径差异：

::

   固定目标 PID
   → 读取 /proc/<pid>/root 与 cwd
   → 读取 /proc/<pid>/mountinfo
   → 确认 dirfd 与 openat2 flags
   → 逐组件检查 symlink 和 mount point
   → 对齐 strace 返回值
   → 必要时追踪 VFS lookup 与具体文件系统

必须区分
--------

* 路径字符串与 ``struct path``：字符串只是输入；``struct path`` 才是当前 namespace 中的 mount+dentry 对象位置。
* Dcache 命中与文件存在的永久事实：命中是缓存结果，仍可能需要 revalidate，并受并发目录变化影响。
* Dentry 与 Mount：Dentry 表达文件系统内部名字；mount 决定该名字在命名空间挂载树中的位置。
* 绝对路径与宿主机根：绝对路径从调用进程有效 root 开始，不保证是宿主机初始命名空间的 ``/``。
* ``..`` 与简单父指针：``..`` 还要处理 mount root、mounted-on dentry 和进程 root 边界。
* 字符串清洗与安全解析：去除 ``..`` 不能解决 symlink、bind mount 和 rename 竞态；应使用 dirfd 和内核解析约束。

一句话结论
----------

路径是一次在调用进程根、目录 fd、mount namespace、dcache 与文件系统回调中逐组件执行的解析过程，最终结果必须用 mount+dentry 表达。
