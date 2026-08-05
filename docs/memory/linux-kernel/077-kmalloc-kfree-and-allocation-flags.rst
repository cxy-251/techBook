第077章：kmalloc、kfree 与分配标志
==================================

本章必须记住
------------

#. ``kmalloc()`` 是普通内核小对象和字节缓冲区的通用分配入口，输入是字节数和 ``gfp_t``。
#. ``kmalloc`` 返回内核可直接解引用的连续虚拟地址，常见实现把请求映射到通用 SLUB 大小等级。
#. ``kmalloc`` 对象的实际 bucket 可能大于请求大小，但调用者的合法对象边界仍以请求大小和类型定义为准。
#. 不能依赖 bucket 尾部的额外空间；KASAN、FORTIFY 和边界检查仍按原始请求语义工作。
#. ``sizeof(*ptr)`` 能把分配大小绑定到目标类型，结构体分配应优先使用这种写法。
#. ``kmalloc()`` 返回的内容默认未初始化，可能保留同一槽位上旧对象的数据。
#. ``kzalloc()`` 等价于分配后将请求区域清零，适合零值就是合法初始状态的对象。
#. 清零只能建立字节级零状态，不能自动初始化锁、链表、引用计数、RCU 头或需要专用 helper 的对象字段。
#. ``kcalloc(n, size, gfp)`` 和 ``kmalloc_array(n, size, gfp)`` 会检查 ``n * size`` 的整数溢出，数组分配应优先使用它们。
#. 使用 ``kmalloc(n * size, gfp)`` 处理外部规模时，乘法溢出可能导致小分配和随后越界写入。
#. ``struct_size()``、``flex_array_size()`` 等 helper 适合带 flexible array member 的对象规模计算。
#. ``krealloc()`` 成功时可能返回新地址并释放旧存储，旧指针随后不能继续使用。
#. ``krealloc()`` 失败时通常返回 ``NULL`` 且原对象仍有效，必须先保存返回值再决定是否替换原指针。
#. ``krealloc_array()`` 等数组重分配接口应在需要时用于保留溢出检查。
#. 零大小分配可能返回 ``ZERO_SIZE_PTR`` 一类特殊非 ``NULL`` 值；它可以传给对应释放接口，但不能解引用。
#. ``kfree(NULL)`` 是安全的，错误回滚可以无条件释放可能为空的普通 kmalloc 指针。
#. ``kfree()`` 只能释放来自兼容 kmalloc family 的对象，不能释放栈、静态区、用户地址、``vmalloc`` 地址或任意对象内部指针。
#. 必须把分配返回的基址传给 ``kfree()``，不能传递 ``ptr + offset``。
#. 对象释放后可能立即回到 freelist 并被复用；指针数值不再代表原对象身份。
#. ``kfree_sensitive()`` 适合需要在释放前清除密钥等敏感内容的 kmalloc 对象，普通 ``kfree`` 不保证擦除旧数据。
#. ``GFP_KERNEL`` 是普通可睡眠进程上下文中的默认选择，允许直接回收并可能进入 I/O 和文件系统路径。
#. ``GFP_KERNEL`` 分配在压力下可能长时间阻塞，不能在硬中断、softirq、持 spinlock 或其它原子上下文中使用。
#. ``GFP_NOWAIT`` 不执行会睡眠的直接回收，适合失败后能立即降级、丢弃或转移工作的快速路径。
#. ``GFP_ATOMIC`` 适合无法睡眠且需要尝试使用部分紧急保留的路径，仍然可能失败。
#. ``GFP_ATOMIC`` 不是“永不失败”的标志，也不能作为错误上下文设计的补丁。
#. ``GFP_NOIO`` 限制回收进入块 I/O，适合已处于 I/O 栈中、需要避免递归的路径。
#. ``GFP_NOFS`` 限制回收进入文件系统，适合持有文件系统锁或处于文件系统内部递归敏感路径。
#. ``memalloc_noio_save()``、``memalloc_nofs_save()`` 一类作用域接口可把限制传播到深层调用，必须成对恢复。
#. ``__GFP_ZERO`` 请求分配器清零返回区域；对应高层常用接口是 ``kzalloc``、``kcalloc``。
#. ``__GFP_NOWARN`` 只抑制分配失败日志，不提高成功率，也不能替代调用者处理 ``NULL``。
#. ``__GFP_NORETRY`` 倾向快速失败；``__GFP_RETRY_MAYFAIL`` 允许更积极尝试但仍可失败。
#. ``__GFP_NOFAIL`` 只适用于内核明确允许长期等待且不能失败的受控路径，不应被普通对象分配使用。
#. GFP 中的 zone、迁移性、memcg 和 reclaim 位共同影响分配路径，不能只根据宏名称推断完整行为。
#. 选择 GFP 时应从当前执行上下文和锁依赖出发，不能从“希望成功”反推更激进标志。
#. 分配成功后，调用者必须完成所有字段初始化，再把对象发布给其它 CPU、查找结构或异步路径。
#. 发布半初始化对象会把内存分配问题升级为并发可见性和生命周期问题。
#. 分配对象进入全局表、队列或 RCU 结构前，应先完成引用计数、锁、列表和状态字段初始化。
#. 错误路径必须区分对象是否已经发布；未发布对象可直接回滚，已发布对象必须先停止查找和并发使用。
#. 对象含有嵌套分配时，释放顺序通常与成功申请顺序相反。
#. 使用 ``devm_kmalloc`` 一类 managed resource 时，设备解绑会自动释放存储，但异步访问和对象注销仍需驱动显式收束。
#. 大块 ``kmalloc`` 可能进入高阶页分配，对外部碎片更敏感；只要求虚拟连续时应评估 ``kvmalloc`` 或 ``vmalloc``。
#. ``kvmalloc()`` 可能先尝试 kmalloc，再退到 vmalloc，因此返回区域不能按物理连续内存使用。
#. ``kvmalloc`` 路径可能睡眠，通常只适合可睡眠上下文；返回值应由 ``kvfree()`` 释放。
#. DMA 需求必须使用 DMA API，不能因为 ``kmalloc`` 内存通常物理连续就绕过设备映射、DMA mask 和缓存一致性规则。
#. 调试一次 kmalloc 失败时，应记录请求大小、对应 bucket、GFP、上下文、memcg、NUMA node 和调用栈。
#. 调试 UAF 或越界时，应同时检查原始请求边界、对象发布点、最后引用、释放调用栈和槽位复用情况。

必背路径
--------

普通结构体分配：

::

   确认当前上下文可使用的 GFP
   → kzalloc(sizeof(*obj), gfp) 或 kmalloc
   → 检查 NULL
   → 初始化锁、引用、链表和业务字段
   → 建立所有权
   → 发布到查找结构或异步路径
   → 使用完成后停止新引用
   → 等待现有使用者
   → kfree

安全数组分配：

::

   取得元素数量 n 和元素大小
   → 检查业务上限
   → kcalloc / kmalloc_array 执行乘法溢出检查
   → 检查返回值
   → 只在合法元素范围内访问
   → 生命周期结束后 kfree

安全重分配：

::

   保留原指针 old
   → new = krealloc(old, new_size, gfp)
   → new 为 NULL 时继续保留 old 并处理失败
   → 成功时只使用 new
   → 更新所有保存该对象地址的所有权关系
   → 最终 kfree(new)

GFP 选择：

::

   判断是否处于进程上下文
   → 判断能否睡眠和直接回收
   → 判断回收能否进入 I/O
   → 判断回收能否进入文件系统
   → 判断是否存在可靠失败降级
   → 选择 GFP_KERNEL / NOWAIT / ATOMIC / NOIO / NOFS
   → 所有情况下处理分配失败

错误回滚：

::

   某一步分配失败
   → 不发布当前半初始化对象
   → 从最后成功资源开始逆序释放
   → 解除嵌套对象和引用
   → kfree(NULL) 可安全执行
   → 保留最初错误码
   → 返回调用者

必须区分
--------

请求大小与 bucket 大小
   请求大小定义合法对象边界；bucket 是分配器内部复用和对齐单位。

``kmalloc`` 与 ``kzalloc``
   前者内容未初始化；后者将请求区域清零，但不代替对象专用初始化。

``GFP_NOWAIT`` 与 ``GFP_ATOMIC``
   二者都不能正常睡眠回收；后者可尝试部分紧急保留，仍然没有成功保证。

``GFP_NOIO`` 与 ``GFP_NOFS``
   前者阻止回收进入 I/O；后者主要阻止进入文件系统递归路径。

``krealloc`` 失败与成功
   失败时原对象仍有效；成功时返回地址可能改变，旧指针不能继续使用。

``kfree`` 与对象生命周期结束
   ``kfree`` 归还存储；调用前必须先结束所有查找、引用和异步访问。

一句话结论
----------

``kmalloc`` family 的正确使用不只是申请字节，而是用准确大小和 GFP 声明上下文、完整初始化对象、处理失败，并在所有并发使用结束后用匹配接口释放。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 16，Kernel Memory Allocation Slab, Slub, Vmalloc, and Per-CPU Memory；
* AIBook 章节：Chapter 77，kmalloc, kfree, and Allocation Flags；
* 源文件：``docs/LinuxK/Part_16_Kernel_Memory_Allocation_Slab_Slub_Vmalloc_and_Per_CPU_Memory/Chapter_077_kmalloc_kfree_and_Allocation_Flags.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_16_Kernel_Memory_Allocation_Slab_Slub_Vmalloc_and_Per_CPU_Memory/Chapter_077_kmalloc_kfree_and_Allocation_Flags.md>`_。