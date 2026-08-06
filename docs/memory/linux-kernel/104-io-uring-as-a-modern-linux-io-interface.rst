第104章：io_uring 作为现代 Linux I/O 接口
=========================================

本章必须记住
------------

#. ``io_uring`` 把用户态与内核态的高频 I/O 交互组织成共享 Submission Queue 和 Completion Queue 协议。
#. 它优化的是请求描述、批量提交、完成返回和资源复用，不自动改变文件系统、Page Cache 或设备本身的语义。
#. ``io_uring_setup()`` 创建 ring 实例并返回 ring fd；ring fd 是实例生命周期与后续 enter/register 操作的句柄。
#. ``struct io_uring_params`` 返回队列大小、共享区偏移和 feature，用户态必须按实际返回布局建立映射。
#. 用户态通常通过 ``mmap`` 映射 SQ ring、CQ ring 和 SQE 数组，具体映射方式受 feature 和版本影响。
#. SQ 用于用户发布请求，CQ 用于内核发布完成；两条队列拥有各自的 head 与 tail。
#. SQE 数组与 SQ ring array 是两个层次：应用填写 SQE，再把 SQE 索引发布到 SQ ring。
#. 应用写完完整 SQE 后才能以 release 语义推进 SQ tail；内核以 acquire 语义观察 tail 后才能消费请求。
#. 内核写完 CQE 后才推进 CQ tail；用户以 acquire 语义观察 tail 后才能读取完整 CQE。
#. 直接操作裸 ring 时必须遵守 UAPI 内存顺序；通常应使用 ``liburing`` helper 封装这些规则。
#. 推进 SQ tail 只让请求对内核可见，不保证内核已经消费，更不保证请求已经完成。
#. ``io_uring_enter()`` 可以提交、等待完成或执行其它 ring 动作，返回值属于 ring 入口层结果。
#. 具体请求的结果通常位于对应 CQE 的 ``res`` 字段，不能和 ``io_uring_enter`` 返回值混为一层。
#. SQE 是请求描述符，CQE 是完成描述符；两者通过 ``user_data`` 建立应用定义的身份关联。
#. ``user_data`` 是 64 位不透明值，应用可放 ID、索引、generation 或受控指针，但必须保证对应上下文生命周期。
#. 使用裸指针作为 ``user_data`` 时，对象在最后一个相关 CQE 消费前不能释放。
#. SQE 中各 union 字段的意义由 ``opcode`` 决定，必须先解析 opcode，再解释 fd、off、addr、len 和附加标志。
#. CQE ``res >= 0`` 对 read/write 常表示字节数；``res < 0`` 表示负 errno。
#. 短读、短写和 EOF 都可能通过非负 ``res`` 表达，不能只把非负值视为“完成全部请求”。
#. CQE ``flags`` 可以携带 buffer selection、更多完成等附加状态，含义具有 opcode 和版本边界。
#. 普通单次请求通常产生一个终结 CQE；multishot 请求可以为一个 SQE 产生多个 CQE。
#. 对 multishot 请求，只有完成 flags 表明不再继续时，应用才能结束该请求的完整生命周期。
#. SQE 被内核消费后，SQE 槽位可以复用；原始 I/O buffer 和业务 token 仍要等请求完成。
#. 提交顺序不保证完成顺序，不同缓存命中、设备、worker 和依赖会导致 CQE 乱序出现。
#. 应用必须按 ``user_data`` 或等价 token 关联结果，不能用 CQE 的数组位置推断原提交顺序。
#. ``io_uring`` 可以提交 buffered I/O，也可以提交 Direct I/O；是否经过 Page Cache 仍由文件标志、opcode 和文件系统路径决定。
#. 使用 ``io_uring`` 提交 buffered read 不会自动绕过 Page Cache；使用 ``O_DIRECT`` 仍需满足对齐和 buffer 生命周期约束。
#. 某些请求能在提交上下文快速完成，某些能原生异步派发，某些可能转交 ``io-wq`` worker。
#. 因此 ``io_uring`` 不等于“没有线程”或“所有操作都绝不阻塞”。
#. 文件系统锁、Page Cache miss、块分配、元数据、DNS/网络或其它阻塞点仍可能需要 worker 或同步准备。
#. ``IOSQE_ASYNC`` 一类标志可影响派发策略，具体行为必须按目标版本和 opcode 验证。
#. Registered files 让 ring 长期持有 ``struct file`` 引用，请求通过 fixed-file 索引避免每次普通 fd lookup。
#. 注册文件后关闭原 fd 不一定结束 ring 对 ``struct file`` 的引用；必须更新或注销 fixed file table。
#. Fixed file 索引不是进程 fd 数字，使用时需要设置对应 SQE 标志并按注册表解释。
#. Registered buffers 让 ring 预先建立并持有 buffer 相关映射/pin，固定请求通过 buffer 索引引用。
#. 预注册可以减少每次请求的地址验证、页固定和引用成本，但会延长内存被 pin 或保留的时间。
#. Registered buffer 不自动等于端到端 zero-copy，文件系统、Page Cache、协议和设备仍可能发生复制。
#. 注册大批长期 buffer 会影响回收、迁移、NUMA 和内存配额，必须限制规模并监控实际收益。
#. Buffer 更新、注销和 ring teardown 前必须确认没有请求仍使用旧槽位。
#. Buffer selection/提供 buffer ring 允许内核从用户提供的池中选择接收 buffer，返回 CQE 后应用按标识回收。
#. Buffer pool 需要防止同一槽位同时被多个请求拥有，并处理短接收、multishot、取消与重新提供。
#. Registered personalities、restrictions 和其它资源机制具有版本与安全边界，不能从某个新内核示例推广到所有环境。
#. Ring 的 SQ/CQ 深度是有限资源，申请 entries 不等于任意时刻都能无限提交。
#. SQ 满表示用户尚未获得可发布槽位或内核尚未消费足够请求；CQ 积压表示用户消费完成太慢。
#. CQ 容量和 overflow 行为受 ring feature 与配置影响，应用应在正常路径持续 reap，而不是依赖溢出补救。
#. 在途上限应按业务、buffer 数量、设备队列和尾延迟设定，不能只按 SQ entries 填满。
#. 批量提交减少 syscall 与队列同步次数，也可能让首个请求等待更久；batch 大小要和延迟目标平衡。
#. SQPOLL 由内核线程轮询 SQ，目标是减少提交 syscall；它消耗 CPU，并受权限、空闲和版本配置约束。
#. IOPOLL 轮询设备完成，要求底层路径支持适合的 polling，通常与 Direct I/O 和设备能力相关。
#. SQPOLL 轮询提交，IOPOLL 轮询完成，两者解决不同阶段，不能混为同一种优化。
#. Polling 模式可能降低中断和调度延迟，也可能占用 CPU、增加功耗并影响同核负载。
#. Linked SQE 用 ``IOSQE_IO_LINK`` 一类标志把多个操作组织成依赖链。
#. 普通 link 链中上游失败可能取消后续操作；hard link 等语义不同，必须按 UAPI 规则处理。
#. Link 表达执行依赖，不自动把多个文件系统写组成一个原子事务。
#. Link timeout、请求 timeout 和 cancel 都存在“目标已完成或正在完成”的竞态。
#. 取消成功不表示已经发生的设备副作用被回滚；写入可能已部分或全部执行。
#. Timeout CQE 与原请求 CQE 可能按竞态分别出现，状态机必须识别两类 token 并避免重复释放。
#. ``IOSQE_IO_DRAIN`` 一类语义可要求先前请求完成后再执行当前请求，但具体全局/链边界具有版本语义。
#. 提交 fsync 与先前写建立可靠顺序时，应使用明确的链、drain 或应用 completion 状态，不应只依赖“先填 SQE”。
#. ``io_uring`` 支持的 opcode 和 flag 持续演进，程序必须根据内核 feature/probe 结果选择能力和降级路径。
#. UAPI 结构稳定不代表所有 opcode 在所有文件类型、文件系统和安全策略下都可用。
#. Ring 创建可能受系统配置、安全策略、容器、seccomp 或发行版限制，应用必须处理 setup/register 失败。
#. Ring fd 也遵守 fd 继承与 close-on-exec 规则，创建时应明确 CLOEXEC 和跨 exec 生命周期。
#. 多提交者并发操作同一 ring 时，需要遵守库提供的并发模型或额外同步，不能假设所有 helper 自动多生产者安全。
#. 多消费者并发 reap CQE 时必须定义 completion 所有权，防止一个 CQE 被重复处理。
#. ``io_uring`` completion 在用户态被看见后，应用仍要推进 CQ head 才算归还完成槽位。
#. 忘记推进 CQ head 会造成 CQ 看似不断变满，即使业务已读取结果。
#. Ring teardown 的正确顺序是停止新提交、取消或等待在途请求、消费终结 CQE、注销资源、最后关闭 ring。
#. 直接 close ring fd 时内核会执行清理，但应用仍需保证自己的业务对象和 buffer 不被过早释放。
#. 请求对象应携带 generation 或状态位，防止对象地址复用后迟到 CQE 命中新对象形成 ABA。
#. 对连接或文件对象销毁，应让所有 multishot、poll、timeout 和 worker 请求先进入终结状态。
#. ``strace`` 可以观察 setup/enter/register，不能展示共享 ring 中每个 SQE 参数和 CQE 生命周期的全部细节。
#. 应用侧统计应记录 SQ 提交数、内核消费进度、CQE 数、overflow、在途数、batch、取消和 timeout。
#. 内核侧可用 tracepoint、perf、ftrace 或 eBPF 观察请求创建、派发、worker、文件系统和完成路径，事件名依版本而定。
#. 性能分析要把用户排队、SQ 等待、内核派发、文件系统、块层、设备服务和 CQ 消费分别计时。
#. 最稳定源码阅读顺序是：setup/context → mmap ring → SQE 发布 → 内核请求对象 → 文件/网络具体路径 → CQE 发布 → 用户 reap → 资源注销。

必背路径
--------

创建并提交 ring：

::

   io_uring_setup(entries, params)
   → 取得 ring fd 与实际 feature/layout
   → mmap SQ / CQ / SQE 区域
   → 取得空闲 SQE 槽位
   → 填写 opcode、资源、参数和 user_data
   → 把 SQE index 放入 SQ array
   → release 发布 SQ tail
   → io_uring_enter 或 SQPOLL 让内核消费

请求完成：

::

   内核读取 SQE
   → 建立内部 request 并保存资源引用
   → 快速执行 / 原生异步派发 / io-wq
   → 具体 VFS、文件系统、网络或块层完成
   → 填写 CQE user_data、res、flags
   → release 发布 CQ tail
   → 用户 acquire 读取 CQE
   → 处理结果并推进 CQ head
   → 释放业务 token 和 buffer

Fixed file：

::

   io_uring_register 注册 fd 数组
   → ring 持有 struct file 引用
   → SQE 设置 fixed-file 标志
   → fd 字段解释为注册表索引
   → 请求无需普通 fdtable lookup
   → 更新/注销前等待使用者结束
   → 释放 ring 持有的 file 引用

Linked write 与 fsync：

::

   准备 write SQE
   → 设置 link 关系
   → 准备 fsync SQE
   → 批量发布
   → 内核按链依赖执行
   → write 失败时按 link 规则处理后续
   → 分别消费 write 与 fsync CQE
   → 只有 fsync 成功后建立对应持久化假设

安全关闭 ring：

::

   标记 stopping
   → 拒绝新 SQE
   → 取消 multishot/poll/timeout 和普通请求
   → 持续 reap CQE
   → 确认所有 token 终结
   → 注销 buffer/file 等固定资源
   → 解除用户映射和业务引用
   → close ring fd

必须区分
--------

* SQE 被消费与请求完成：内核取得 SQE 后槽位可复用；buffer、file 和业务 token 要等 CQE 终结。
* ``io_uring_enter`` 错误与 CQE 错误：前者属于 ring 入口操作；后者属于某个具体请求结果。
* ``user_data`` 值与对象生命周期：User data 只是身份标记；若保存指针，对象必须活到所有相关 CQE 被消费。
* Registered buffer 与 Zero-copy：注册减少重复 pin/校验；具体数据路径仍可能复制。
* SQPOLL 与 IOPOLL：前者轮询提交队列，后者轮询设备完成，成本与适用条件不同。
* Link 顺序与事务原子性：链接规定请求依赖和失败处理，不自动创建文件系统或业务事务。

一句话结论
----------

``io_uring`` 是用户态与内核共享的有界请求—完成协议，正确性取决于 SQ/CQ 内存顺序、请求身份、资源生命周期、完成消费和 teardown 全部闭合。
