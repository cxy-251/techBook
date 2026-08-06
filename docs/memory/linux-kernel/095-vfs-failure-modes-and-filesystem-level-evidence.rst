第095章：VFS 故障模式与文件系统级证据
====================================

本章必须记住
------------

#. VFS 错误码只压缩表示最后失败阶段，不能单独还原完整根因。
#. 诊断文件问题必须先确定 syscall、PID、路径或 fd、mount namespace 和具体文件系统。
#. 同一个错误码可由不同路径组件、权限层次或后端状态产生，必须放回对象链解释。
#. ``ENOENT`` 表示当前解析语义下没有得到目标对象，缺失的可能是中间目录、符号链接目标或最终组件。
#. ``open(path, O_CREAT)`` 允许最终组件不存在，不允许中间目录不存在。
#. ``ENOENT`` 还可能来自动态伪文件、容器挂载切换、网络文件系统状态或并发 rename/unlink。
#. ``ENOTDIR`` 常表示某个中间组件不是目录，或尾部斜杠要求目录但目标类型不符。
#. ``EACCES`` 可能发生在任一目录组件的 search 权限、目标 inode 权限、ACL、LSM 或其它策略检查。
#. 目标文件本身可读，不表示调用者能穿过所有父目录。
#. ``EPERM`` 与 ``EACCES`` 都可表示权限/策略拒绝，但具体使用场景和操作语义不同。
#. ``EROFS`` 表示操作落到只读文件系统或只读挂载语义，不能只修改 inode mode 解决。
#. ``EEXIST`` 常见于创建最终组件已存在；必须确认 syscall 的 final-component 语义。
#. ``EXDEV`` 常见于跨挂载点 rename 或 link，表示操作要求的同一文件系统边界不成立。
#. ``ELOOP`` 常见于符号链接循环、过深解析或禁止跟随时的接口语义。
#. ``ESTALE`` 常见于 NFS、集群文件系统或需要 revalidate 的后端，表示缓存句柄或对象身份已经失效。
#. ``ESTALE`` 需要检查服务器端重建、导出变化、rename/delete、快照回滚和客户端重验证。
#. ``EIO`` 表示更底层 I/O 或文件系统一致性错误，必须结合 kernel log、文件系统日志和设备状态。
#. ``ENOSPC`` 不只表示数据块耗尽，也可能来自 inode、日志、配额、保留空间或特定分配域耗尽。
#. ``EDQUOT`` 表示用户、组或项目配额限制，应与全局空闲空间分开判断。
#. ``EBUSY`` 表示目标状态转换被活动引用或层级关系阻止，不等于“目录中还有普通文件”。
#. 卸载 ``EBUSY`` 的常见来源包括打开文件、cwd、root、文件 mmap、子挂载和内核内部引用。
#. Mount namespace 会让 busy 引用来自另一个进程视图；只查当前 shell 的路径可能漏掉真实持有者。
#. Lazy unmount 只从当前命名空间断开可达关系，活动引用仍可继续使用对象直到最终释放。
#. Force unmount 的支持和安全性取决于文件系统，不是通用清理泄漏手段。
#. fd 泄漏会保持 ``struct file``、dentry、inode、mount、socket、pipe 或设备私有资源存活。
#. 打开文件被 unlink 后，``/proc/<pid>/fd`` 可能显示 ``(deleted)``，磁盘空间仍不会释放到最后引用消失。
#. 一个进程关闭 fd 后，文件 mmap 仍可通过 VMA 保持文件和 mount 引用。
#. 当前工作目录和进程 root 本身就是 path 引用，即使进程没有普通打开 fd 也可能阻止卸载。
#. ``/proc/<pid>/fd`` 用于观察打开 fd；``fdinfo`` 用于补充偏移、flags、mnt_id 和子系统状态。
#. ``/proc/<pid>/cwd`` 与 ``root`` 用于发现目录和根路径引用。
#. ``/proc/<pid>/maps`` 用于发现仍映射目标文件系统文件的 VMA。
#. ``/proc/<pid>/mountinfo`` 用于把进程路径视图映射到 mount ID、父 mount、root、mount point 和文件系统类型。
#. ``lsof`` 可汇总进程、fd、设备号、inode 和路径，是定位打开引用的辅助工具。
#. ``lsof`` 结果受权限、namespace、瞬时竞争和内核内部引用限制，不能作为唯一证据。
#. ``fuser`` 可辅助定位访问某 mount/path 的进程，也需要结合 namespace 和对象类型验证。
#. ``strace -e trace=%file`` 可观察路径相关 syscall、参数和 errno，证明用户态实际请求了什么。
#. ``strace`` 不能展示 dcache、inode 锁、mount crossing 和文件系统内部回调，需与内核 trace 配合。
#. ``strace -yy`` 可尝试补充 fd 指向对象信息，仍是用户态观察视角。
#. ftrace、tracefs、perf 或 eBPF 可观察 VFS、writeback、block I/O 和具体文件系统事件，事件名依内核版本而变。
#. 动态追踪必须先控制过滤条件和采样开销，避免把高频路径自身拖慢。
#. 用户态看到的路径可能已经 rename，打开 ``struct file`` 仍指向原对象；必须区分当前名字和原始打开关系。
#. ``readlink /proc/<pid>/fd/<n>`` 展示当前可表示路径，不保证就是 open 时传入的字符串。
#. Dentry cache 压力应通过 ``/proc/sys/fs/dentry-state``、slab 统计和 shrinker/reclaim 趋势分析。
#. ``dentry-state`` 中 unused 等计数是瞬时缓存视图，字段解释以目标内核文档为准。
#. 大量 dentry/inode 不自动等于泄漏，它们可能是高路径工作集的正常缓存。
#. 大量 negative dentry 可能来自反复探测不存在文件、包管理、构建、容器 overlay 或攻击流量。
#. 元数据缓存是否有问题，要看增长是否无界、回收是否有效、refault/lookup 成本和内存压力。
#. ``/proc/slabinfo`` 或 ``slabtop`` 可观察 dentry、inode cache 和文件系统私有 slab 的对象数量。
#. 通用 ``inode_cache`` 不能代表所有文件系统 inode；ext4、XFS、NFS 等可能使用私有 cache。
#. ``SReclaimable`` 高表示部分 slab 具备回收潜力，不表示所有对象此刻都无引用。
#. Reclaim 扫描很多但释放很少，可能说明 dentries/inodes 被打开 file、cwd、mount 或文件系统状态固定。
#. 远程文件系统 cache pressure 还要结合 attribute cache、dentry revalidate 和服务端响应时间。
#. Overlayfs 路径可能跨 upper/lower/workdir 多层对象，错误码和 inode identity 需要按 overlay 语义解释。
#. 容器中排查路径必须进入目标进程 mount namespace 或使用 ``/proc/<pid>`` 视图，不能只从宿主机同名路径推断。
#. 权限排查应记录实际 UID/GID、supplementary groups、capabilities、user namespace、LSM 和 idmapped mount。
#. 只执行 ``chmod 777`` 会掩盖部分权限线索，也无法解决父目录、LSM、只读挂载或 namespace 错误。
#. Path race 问题应使用 ``openat2``、目录 fd 和对象句柄降低 TOCTOU，不应反复 ``stat`` 后按字符串操作。
#. 诊断文件“偶尔不存在”时，应对齐部署 rename/symlink 切换、reader open 时刻和旧 fd 生命周期。
#. 原子 rename 可以切换目录项关系，但无法让已经打开旧文件的进程自动切换到新 inode。
#. 配置热更新需要明确使用“每次按路径重新 open”还是“长期持有 fd”，两种模型观察到的版本不同。
#. ``fsync`` 成功/失败、writeback error 和 close 返回值属于数据持久化证据，和路径查找错误是不同层。
#. 文件写成功后异步回写失败可能在后续 ``fsync``、close 或其它接口报告，不能只看初次 write。
#. Busy mount 修复前必须识别引用所有者；强杀进程或强卸载可能导致数据丢失和服务故障。
#. 元数据缓存调优前必须先证明瓶颈来自 lookup/revalidate 或回收，而不是数据 I/O、锁和应用请求模式。
#. 运行时证据必须按同一时间窗口收集：syscall、fd 表、mountinfo、slab、内核日志、trace 和业务错误。
#. 单次快照无法证明瞬时 fd 泄漏或路径竞态，需采样增长趋势和事件时间线。
#. 最稳定的 VFS 故障顺序是：syscall/errno → 起点与 namespace → 路径组件 → dentry/inode → file 引用 → filesystem/backend。

必背路径
--------

诊断 ``ENOENT``：

::

   保存真实 syscall 与 pathname
   → 确认绝对/相对路径和 dirfd
   → 读取目标进程 root / cwd / mountinfo
   → 逐组件检查目录和 symlink
   → 找出中间组件或最终组件缺失
   → 检查并发 rename/unlink 和部署切换
   → 必要时追踪文件系统 lookup

诊断 ``EACCES``：

::

   确认进程实际 credentials
   → 按路径逐级检查目录 search 权限
   → 检查目标 inode mode 与 ACL
   → 检查 mount flags 和只读状态
   → 检查 LSM 审计日志
   → 检查 user namespace / idmapped mount
   → 在目标进程 namespace 复现

诊断 busy mount：

::

   从 /proc/<pid>/mountinfo 确认目标 mount ID
   → 查 /proc/*/fd 中的打开对象
   → 查 /proc/*/cwd 与 root
   → 查 /proc/*/maps 文件映射
   → 查子挂载和其它 namespace
   → 查内核/文件系统内部引用
   → 收束使用者后正常 umount

诊断 fd 泄漏：

::

   周期采样 /proc/<pid>/fd 数量
   → 按对象类型和 mnt_id 分类
   → strace/trace 记录创建与 close
   → 检查 CLOEXEC 和 fork/exec
   → 检查错误回滚与异步对象
   → 找到缺失的关闭责任方
   → 验证 fd、inode 和 mount 引用回落

诊断元数据缓存压力：

::

   采样 dentry-state 与 slabinfo
   → 区分 dentry、inode 和私有 cache
   → 观察增长、unused 和 reclaim 趋势
   → 对齐 lookup/revalidate 工作负载
   → 检查 negative dentry 来源
   → 检查 open/cwd/mount 固定引用
   → 判断正常工作集、泄漏或回收失效

必须区分
--------

* 错误码与根因：Errno 只定位失败类别和阶段；完整根因需要路径、对象、namespace 与后端证据。
* ``ENOENT`` 与目标文件缺失：可能缺失的是任一中间目录、符号链接目标或最终组件。
* 目录内容与 Busy mount：Busy 来自活动对象引用和子挂载，不由目录是否为空直接决定。
* Fd 关闭与文件引用结束：mmap、其它 fd、cwd/root 和内核路径仍可保持对象和 mount 存活。
* 缓存增长与内存泄漏：Dentry/inode 是正常元数据缓存；只有无界增长、不可回收和业务损害才指向异常。
* 用户态工具与内核事实：strace/lsof/procfs 提供不同视角，必须和 trace、日志及具体文件系统状态交叉验证。

一句话结论
----------

VFS 故障诊断必须把 errno 放回目标进程的路径起点、挂载命名空间、dentry/inode、打开 file 引用和具体文件系统后端中还原。
