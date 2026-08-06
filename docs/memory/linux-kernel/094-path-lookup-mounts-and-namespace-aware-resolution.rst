第094章：路径查找、挂载与命名空间感知解析
========================================

核心知识点
----------

路径是解析过程，不是对象身份
   路径字符串必须结合调用进程的 root、cwd、dirfd、mount namespace 和挂载树逐组件执行，最终结果才是可引用的内核对象位置。

``struct path`` 由 mount 与 dentry 组成
   Dentry 表示文件系统内部名字关系，mount 表示该关系位于哪棵挂载树。缺少任一部分都不能完整描述路径位置。

起点由调用方式决定
   绝对路径从进程有效 root 开始；相对路径从 cwd 或 ``*at`` 接口提供的 dirfd 开始。``AT_FDCWD`` 明确表示当前工作目录。

组件按顺序逐级解析
   每一层都要检查当前目录、名字缓存、目录 lookup、搜索权限、挂载点、符号链接和查找标志。内核不会一次性把整串文本转换成 inode。

Dcache 以父目录和名字为键
   Positive dentry 缓存存在对象，negative dentry 缓存未命中。Dcache miss 才进入目录 inode 的 ``lookup`` 回调。

缓存命中仍可能需要重验证
   远程文件系统、动态伪文件和并发目录修改可能使缓存结果失效。``d_revalidate`` 等机制决定现有 dentry 是否仍可使用。

RCU-walk 是路径快路径
   查找可在 RCU 与序列验证保护下读取 dcache，减少引用计数和重锁；需要睡眠、慢速 lookup、重验证或发现不稳定时，会退回 REF-walk。

退回慢路径必须重新验证
   Rename、unlink、mount 和目录修改可能在锁释放期间改变对象关系。旧 VMA 式思维不适用于路径对象，不能继续使用未经稳定引用保护的 dentry 判断。

挂载点会切换对象空间
   解析到被 mount 覆盖的 dentry 后，当前 ``path`` 切换到新 mount 的根 dentry，后续组件属于另一 superblock 和 inode 空间。

Mount namespace 决定可见挂载树
   相同路径字符串在宿主机、容器和不同进程中可以得到不同结果。诊断必须读取目标进程的 ``root``、``cwd`` 和 ``mountinfo``。

Bind mount 重新暴露已有树
   Bind mount 不复制文件数据，只把已有 mount+dentry 关系连接到新的挂载点，因此同一对象可以拥有多个可见路径。

符号链接会重新注入路径文本
   绝对链接目标从进程 root 重新开始，相对链接目标从链接所在目录继续。解析深度、循环和最终组件是否跟随由 syscall 与 flags 控制。

``..`` 不是简单父指针
   普通目录可走父 dentry；到达 mount root 时还要回到 mounted-on path，并且不能越过进程有效 root。

权限检查发生在每个目录组件
   穿过目录需要 search/execute 权限，和列出目录的 read 权限不同。目标文件权限正确，也不能补偿父目录不可搜索。

安全解析必须由内核约束
   字符串清洗不能消除 symlink、bind mount、rename 和 namespace 竞态。可信 dirfd 与 ``openat2`` resolve flags 才能把解析限制绑定到实际对象过程。

路径解析结果与最初字符串可分离
   对象被 rename 或 unlink 后，已打开 file 仍引用原对象；``/proc/<pid>/fd`` 显示的是当前可表达路径，不保证等于 open 时输入文本。

关键路径
--------

普通路径解析：

::

   取得 pathname 与 lookup flags
   → 选择 root、cwd 或 dirfd 起点
   → 建立当前 struct path
   → 拆出下一个组件
   → 查询 dcache
   → 未命中时调用文件系统 lookup
   → 检查目录权限与组件类型
   → 检查 mount crossing 和 symlink
   → 重复直到最终组件

挂载点穿越：

::

   当前目录解析出 dentry
   → 在 mount namespace 中检查覆盖 mount
   → 取得新 mount 引用
   → path 切换到新 mount 的 root dentry
   → 后续组件在新 super_block 中解释

符号链接处理：

::

   当前组件为 symlink
   → 检查调用是否允许跟随
   → 取得链接目标文本
   → 检查循环与深度限制
   → 选择进程 root 或链接所在目录为新起点
   → 继续解析目标与剩余组件

处理 ``..``：

::

   遇到父目录组件
   → 检查是否已到进程 root
   → 普通目录走父 dentry
   → mount root 回到 mounted-on path
   → 重新验证 namespace 与 root 边界
   → 更新当前 struct path

受约束的安全打开：

::

   预先打开可信目录得到 dirfd
   → 使用相对路径
   → 通过 openat2 设置 resolve 限制
   → 内核逐组件执行限制检查
   → 返回已验证对象的 fd
   → 后续操作围绕 fd 而非重新拼接路径

概念辨析
--------

* 路径字符串与 ``struct path``：字符串是解析输入；``path`` 是 mount namespace 中的 mount+dentry 结果。
* Dentry 与 mount：Dentry 表示名字；mount 决定名字位于哪棵挂载树。
* Dcache 命中与永久事实：缓存命中仍可能需要权限检查、重验证和并发状态确认。
* 绝对路径与宿主机根：绝对路径从调用进程的有效 root 开始，不必是初始 namespace 的 ``/``。
* ``..`` 与父 dentry：跨 mount root 时还要处理 mounted-on 关系和进程 root 边界。
* 字符串清洗与安全解析：文本过滤无法解决对象竞态；dirfd 和内核 resolve 约束才能限定真实解析过程。

本章结论
--------

路径解析是在调用进程的起点、挂载命名空间、dcache 和文件系统回调中逐组件推进的状态机，最终对象位置必须以 mount+dentry 表达。