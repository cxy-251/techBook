第064章：内存屏障与 CPU 重排
============================

核心知识点
----------

源码顺序不等于跨 CPU 可见顺序
   编译器可以移动、合并或省略访问，CPU 也会通过乱序执行、store buffer 和推测读取改变其它处理器看到的先后关系。单线程代码看起来有序，不代表并发观察也有序。

内存屏障只约束顺序
   屏障不提供互斥，不保证对象存活，也不会修复数据竞争。它只限制屏障两侧的内存访问以什么顺序对其它 CPU 或设备可见。

``READ_ONCE`` 与 ``WRITE_ONCE`` 固定单次访问
   它们防止编译器把一次共享访问合并、重复或拆分，适合标记无锁协议中的单次读写，但不自动建立 CPU 间的发布关系。

编译器屏障与 CPU 屏障层次不同
   ``barrier()`` 只阻止编译器跨点移动访问；``smp_mb()``、``smp_rmb()`` 和 ``smp_wmb()`` 还约束 SMP 系统中的运行时内存顺序。

Acquire/release 是常用单向协议
   Release 保证发布动作之前的写入先完成；acquire 保证观察发布值之后的读取不会越过获取点。它们通常比全屏障更准确地表达生产者—消费者关系。

同步变量连接两侧事件
   Payload 是被发布的数据，ready、指针、索引或状态位是同步变量。只有消费者实际观察到生产者通过 release 发布的值，acquire 才能把此前写入传递到消费者。

锁隐含特定顺序保证
   获取锁通常具有 acquire 语义，释放锁通常具有 release 语义，使遵守同一锁协议的临界区有序。绕开锁的无锁访问必须建立独立证明。

Atomic 操作的顺序取决于具体 API
   Relaxed RMW 只有原子性；需要时可选择 acquire、release 或文档规定的 atomic 专用屏障。屏障不能作为不理解协议时的装饰。

CPU 共享内存与设备 I/O 使用不同接口
   ``smp_*`` 面向 CPU 之间的缓存一致内存。DMA buffer、MMIO、descriptor 和 doorbell 必须遵守 DMA API、I/O accessor 与设备屏障规则。

RCU 指针 API 封装发布与读取顺序
   ``rcu_assign_pointer()`` 与 ``rcu_dereference()`` 不只是普通指针赋值和解引用，它们还承担 RCU 协议所需的编译器与内存顺序约束。

强序架构不能替代模型证明
   x86 上没有复现，不代表代码在 ARM64、RISC-V 等弱序架构上正确。内核同步代码应按 Linux Kernel Memory Model 的允许执行结果推理。

关键路径
--------

Release/acquire 发布：

::

   CPU0 写入 payload
   → CPU0 对 ready 执行 store-release
   → CPU1 对 ready 执行 load-acquire
   → CPU1 确认读取到发布值
   → CPU1 读取 payload
   → 生命周期协议保证对象未被回收

分析一段无锁代码：

::

   标出所有共享变量
   → 区分数据字段与同步字段
   → 列出每个 CPU 的 load、store 和 RMW
   → 检查 READ_ONCE / WRITE_ONCE
   → 检查 acquire、release、锁、RCU 或显式屏障
   → 确认观察侧实际读取发布侧的值
   → 检查失败重试和对象生命周期

CPU 与设备交互：

::

   判断内存属于普通缓存、DMA 还是 MMIO
   → 使用正确 DMA API 或 I/O accessor
   → 填写数据和 descriptor
   → 执行对应 DMA / I/O 顺序操作
   → 发布索引、所有权位或 doorbell
   → 按设备协议观察完成状态

验证顺序协议：

::

   写出发布者与观察者事件图
   → 定义必须禁止的错误结果
   → 检查当前 API 的最低顺序保证
   → 使用 LKMM litmus test 验证
   → 在弱序架构与压力场景复查
   → 不依赖单一架构偶然更强的行为

概念辨析
--------

编译器屏障与 CPU 屏障
   前者限制优化器移动访问；后者限制运行时内存系统的观察顺序。

``READ_ONCE`` / ``WRITE_ONCE`` 与同步
   它们固定访问形态；跨 CPU 发布仍需 acquire/release、锁、RCU 或屏障协议。

SMP 屏障与设备屏障
   ``smp_*`` 面向 CPU 共享内存；DMA 和 MMIO 必须使用设备专用顺序接口。

Acquire/release 与全屏障
   Acquire/release 是单向约束；全屏障同时限制更多读写方向，成本和约束通常更强。

顺序与生命周期
   屏障保证状态观察顺序；引用、RCU 和同步取消保证被观察对象仍然存在。

本章结论
--------

内存屏障的目标不是让本 CPU 按源码顺序执行，而是明确限制其它 CPU 或设备可以按什么顺序观察共享状态；正确屏障必须来自清晰的发布—观察事件图。
