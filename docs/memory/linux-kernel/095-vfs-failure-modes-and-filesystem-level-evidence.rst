第095章：VFS 故障模式与文件系统级证据
====================================

核心知识点
----------

Errno 只标记最终失败阶段
   VFS 错误码不能单独还原根因。诊断必须同时固定 syscall、PID、路径或 fd、mount namespace、对象类型和具体文件系统。

``ENOENT`` 不只表示最终文件缺失
   中间目录、符号链接目标、动态伪文件、容器挂载视图或最终组件任一处缺失，都可能得到 ``ENOENT``。

``ENOTDIR`` 指向组件类型冲突
   某个中间组件不是目录，或尾部斜杠要求目录而目标类型不符，都会在路径解析阶段失败。

权限拒绝可能发生在多层
   ``EACCES``、``EPERM`` 可能来自目录 search 权限、目标 inode mode、ACL、capability、LSM、user namespace、idmapped mount 或操作特定策略。

挂载与文件系统状态会覆盖 inode 权限
   ``EROFS`` 表示只读文件系统或只读挂载语义；``EXDEV`` 常表示 rename/link 要求的同一挂载边界不成立；修改文件 mode 不能修复这些结构性限制。

``ESTALE`` 表示对象身份需要重建
   NFS、集群文件系统和需要 revalidate 的后端可能发现句柄、dentry 或 inode 身份已失效。应检查服务端重建、导出变化、rename/delete 和缓存重验证。

``EIO`` 与 ``ENOSPC`` 需要继续下钻
   ``EIO`` 可能来自文件系统一致性或设备错误；``ENOSPC`` 可能表示数据块、inode、日志、配额或保留空间耗尽。错误名不能替代后端状态检查。

``EBUSY`` 表示活动引用阻止状态转换
   卸载失败不等于目录非空。打开 file、cwd、root、mmap、子挂载和内核内部引用都可能保持 mount 存活。

Namespace 决定 busy 引用的可见范围
   另一个 mount namespace 中的进程也可能持有同一底层对象。必须从目标进程的 ``mountinfo``、fd、cwd、root 和 maps 建立引用链。

Close fd 不一定结束文件引用
   其它 fd、进程、mmap 和异步内核路径仍可能持有对象。已 unlink 文件可显示 ``(deleted)``，空间要到最后引用结束后才真正回收。

长期持有 fd 会脱离当前路径名字
   原路径被原子 rename 替换后，旧 fd 仍指向旧 inode。配置热更新必须明确“每次按路径重开”还是“长期持有打开实例”。

元数据缓存增长不自动等于泄漏
   Dentry、inode 和文件系统私有 slab 是正常工作集缓存。只有无界增长、回收效率差、lookup/refault 成本上升或内存压力受损时，才形成异常证据。

Negative dentry 也可能形成压力
   反复探测不存在名字、构建系统、包管理器、overlay 层或攻击流量会增加 negative dentry 数量，应结合请求模式解释。

用户态工具观察不同层次
   ``strace`` 证明进程提交了什么 syscall 和 errno；``/proc/<pid>/fd``、``fdinfo``、``cwd``、``root``、``maps`` 和 ``mountinfo`` 展示对象引用；``lsof``、``fuser`` 提供汇总视角。

内核证据补充内部阶段
   Tracefs、ftrace、perf 或 eBPF 可以观察 VFS lookup、writeback、块 I/O 和具体文件系统事件。使用时必须限制范围并评估高频路径开销。

路径错误与持久化错误属于不同层
   ``write`` 成功后，异步 writeback 仍可能失败，并在 ``fsync``、close 或后续接口报告。不能用路径查找成功证明数据已经持久化。

关键路径
--------

诊断 ``ENOENT``：

::

   保存真实 syscall、pathname 和 dirfd
   → 确认目标进程 root、cwd 与 mountinfo
   → 逐组件检查目录、symlink 和 mount crossing
   → 判断中间组件或最终组件缺失
   → 对齐并发 rename、unlink 和部署切换
   → 必要时追踪文件系统 lookup

诊断权限失败：

::

   取得进程实际 credentials
   → 逐级检查目录 search 权限
   → 检查目标 inode mode 与 ACL
   → 检查 mount flags 和文件系统状态
   → 检查 capability、LSM 和 user namespace
   → 在目标 mount namespace 中复现

诊断 busy mount：

::

   从 mountinfo 确认目标 mount ID
   → 检查所有相关进程 fd 与 fdinfo
   → 检查 cwd、root 和文件 mmap
   → 检查子挂载与其它 namespace
   → 检查文件系统或内核内部引用
   → 收束引用后执行正常 unmount

诊断 fd 泄漏：

::

   周期采样进程 fd 数量
   → 按普通文件、socket、pipe 和 anon_inode 分类
   → 关联创建 syscall 与 close
   → 检查 CLOEXEC、fork/exec 和错误回滚
   → 检查异步请求和共享 files_struct
   → 修复唯一关闭责任方
   → 验证 fd 与对象引用回落

诊断元数据缓存压力：

::

   采样 dentry-state、slabinfo 和 reclaim 计数
   → 区分 dentry、通用 inode 与文件系统私有 cache
   → 检查 positive / negative dentry 来源
   → 检查 open、cwd、mount 等固定引用
   → 观察扫描量与实际释放量
   → 判断正常工作集、无界增长或回收失效

概念辨析
--------

* Errno 与根因：错误码标记失败类别；对象链、namespace 和后端证据才能解释根因。
* ``ENOENT`` 与最终文件缺失：缺失可以发生在任一中间组件、链接目标或最终组件。
* 目录内容与 busy mount：Busy 由活动 path、file、mapping 和子挂载引用造成，不由目录是否为空决定。
* Close 与引用结束：关闭一个 fd 不会撤销其它 fd、mmap、cwd/root 或内核持有关系。
* 缓存增长与泄漏：高 dentry/inode 数量可以是正常缓存；无界、不可回收和业务损害才构成故障。
* 用户态轨迹与内核事实：strace、procfs、lsof 和内核 trace 提供互补证据，任何单一视角都不完整。

本章结论
--------

VFS 故障诊断必须把 errno 放回目标进程的路径起点、挂载命名空间、dentry/inode、打开 file 引用和具体文件系统后端中，按同一时间线还原失败阶段。