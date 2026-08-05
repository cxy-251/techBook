第078章：Slab 与 SLUB 对象缓存
===============================

本章必须记住
------------

#. Slab cache 是一组同大小、同属性内核对象的复用池；SLUB 是现代 Linux 常见的 slab allocator 实现。
#. Page allocator 提供页，SLUB 把页切成对象槽位，子系统通过 ``kmem_cache_alloc()`` 取得对象。
#. ``struct kmem_cache`` 描述对象大小、实际槽位大小、对齐、标志、构造函数、节点状态和 per-CPU 状态。
#. 通用 ``kmalloc-*`` cache 按大小等级服务普通分配；专用 cache 按对象类型服务高频内核对象。
#. ``kmem_cache_create()`` 创建专用 cache，创建成功后才可分配对象。
#. ``kmem_cache_alloc(cache, gfp)`` 从指定 cache 分配对象，失败返回 ``NULL``。
#. ``kmem_cache_zalloc()`` 从 cache 分配并清零对象，但仍需调用对象专用初始化 helper。
#. ``kmem_cache_free(cache, obj)`` 必须把对象归还到它所属的兼容 cache，不能用错误 cache 释放。
#. ``kmem_cache_destroy()`` 前必须确保没有活动对象、并发分配者或延迟释放路径仍引用该 cache。
#. 一个 slab 是 cache 从 page allocator 获得的一组 backing pages，其中包含多个固定大小对象槽位。
#. Slab 可以处于空、部分使用或满状态；分配器重点管理可继续提供对象的 partial slab。
#. 对象释放后槽位可很快被同 cache 的另一对象复用，原地址不再代表旧对象身份。
#. 专用 cache 适合 ``dentry``、``inode``、VMA、网络元数据等大小固定、数量多、分配频繁的对象。
#. 专用 cache 能提供类型级名称、统计、对齐、构造、回收属性和调试信息，这是通用字节分配不具备的语义。
#. ``SLAB_HWCACHE_ALIGN`` 一类标志可改善对象对齐和 cacheline 局部性，也可能增加每个对象的空间开销。
#. ``SLAB_RECLAIM_ACCOUNT`` 表示 cache 中对象通常属于可回收内核缓存，但真正回收仍由子系统 shrinker 和生命周期规则完成。
#. Cache merging 可能让属性兼容的 cache 共用后端；cache 名称不总能证明它拥有完全独立的 slab 集合。
#. 调试标志、对齐、构造函数和禁止合并属性会影响 cache 是否可被合并，具体规则以目标内核为准。
#. Cache 构造函数通常在新槽位建立时执行，不保证每次 ``kmem_cache_alloc()`` 都重新调用。
#. 构造函数不能初始化每次对象使用都会变化的引用计数、所有权、业务状态和外部指针。
#. 每次分配后仍必须显式建立当前对象实例的完整状态。
#. SLUB 快路径优先使用当前 CPU 的 freelist 和当前 slab，减少全局锁、node 锁和跨 CPU cacheline 竞争。
#. 当前 CPU 没有可用对象时，分配器会尝试 node partial slab，再按需向 page allocator 申请新 backing pages。
#. 释放到当前 CPU 本地 cache 通常更便宜；远程释放和跨 CPU 对象流动可能增加原子操作与 cacheline 迁移。
#. Per-CPU 快路径只优化对象槽位管理，不自动保证对象业务字段的线程安全。
#. 对象仍需由锁、引用计数、RCU 或其它协议保护其并发访问和生命周期。
#. Slab cache 复用意味着新对象可能看到旧字节残留；敏感字段和业务字段必须清零或重新初始化。
#. Red zone 在对象边界附近放置检查区域，用于发现越界写入。
#. Poisoning 用特定字节模式填充空闲或新对象，帮助发现 use-after-free 和未初始化使用。
#. Freelist hardening 与随机化提高 freelist 篡改难度，但不是对象生命周期正确性的替代品。
#. KASAN 通过影子内存等机制检测越界与 UAF，报告中的 cache、对象地址和 alloc/free 栈是关键证据。
#. KFENCE 以较低采样频率用隔离页捕捉部分越界与 UAF，适合低开销长期运行场景。
#. SLUB debug 会增加对象元数据、检查和路径成本，可能改变布局、时序和可复现性。
#. ``slab_debug`` 启动参数可以按 cache 启用 redzone、poison、用户跟踪等功能，参数语义具有版本差异。
#. ``/proc/slabinfo`` 和 ``/sys/kernel/slab/`` 可观察 cache 名称、对象大小、活动对象、slab 数量和调试属性。
#. Slabinfo 展示 cache 层占用，不能直接证明哪个业务引用仍持有具体对象。
#. 内存泄漏排查还需结合引用路径、kmemleak、page owner、对象 trace 或子系统统计。
#. ``SLAB_TYPESAFE_BY_RCU`` 只延迟 slab 存储被归还，不保证槽位中的旧对象内容或身份保持不变。
#. 在 ``SLAB_TYPESAFE_BY_RCU`` cache 中，读者取得指针后仍必须验证对象身份，并安全取得引用后再使用。
#. RCU grace period 可以保护存储页不被释放，却不能阻止同一槽位被新对象复用。
#. Cache 对象含有敏感数据时，应评估清零策略，不能依赖后续复用自然覆盖。
#. Cache 对象被 shrinker 回收时，shrinker 负责选择可释放对象，SLUB 只负责最终归还槽位和 backing pages。
#. 调试对象损坏时，应先确定 cache 和对象边界，再还原分配栈、最后释放栈、当前复用者和并发访问路径。
#. 最可靠的专用 cache 设计必须同时定义创建、分配初始化、发布、引用、回收、释放和销毁顺序。

必背路径
--------

专用 cache 生命周期：

::

   子系统初始化
   → kmem_cache_create 定义名称、大小、对齐和标志
   → 分配路径 kmem_cache_alloc
   → 每次建立对象实例状态
   → 发布对象并管理引用
   → 停止新查找并等待现有使用者
   → kmem_cache_free 归还槽位
   → 所有对象和异步路径结束
   → kmem_cache_destroy

SLUB 分配快路径：

::

   当前 CPU 请求对象
   → 检查 per-CPU freelist
   → 命中时摘取本地槽位
   → 未命中时寻找 node partial slab
   → 仍无可用槽位时向 page allocator 要 backing pages
   → 建立新 slab 和 freelist
   → 返回对象给调用者初始化

对象释放与复用：

::

   解除对象外部可见性
   → 等待引用、RCU 和异步使用结束
   → 执行对象析构或敏感数据清理
   → kmem_cache_free
   → 槽位进入 freelist
   → 可能立即承载新的同类型对象
   → 旧指针和旧身份全部失效

分析 SLUB 损坏：

::

   保存完整 KASAN / SLUB debug 报告
   → 确认 cache、对象地址和合法边界
   → 查看 alloc stack 与 free stack
   → 判断越界、double free、UAF 或 freelist 损坏
   → 检查对象发布与最后引用
   → 检查远程释放和异步回调
   → 用目标配置复现并验证修复

``SLAB_TYPESAFE_BY_RCU`` 查找：

::

   在 RCU 读侧定位对象槽位
   → 读取对象身份字段
   → 尝试安全增加引用
   → 再次验证身份未变化
   → 成功后离开 RCU 并使用对象
   → 失败时重试查找
   → 最终 put 归还引用

必须区分
--------

Slab 抽象与 SLUB 实现
   Slab 表示同型对象缓存模型；SLUB 是实现该模型的具体分配器后端。

通用 cache 与专用 cache
   ``kmalloc-*`` 按大小分类；专用 cache 还表达对象类型、构造、回收和调试属性。

构造函数与每次初始化
   构造函数不一定每次分配执行；每个新对象实例仍需完整初始化可变状态。

槽位存活与对象身份
   槽位内存仍存在不表示旧对象仍存在；释放后同一地址可以承载新对象。

Per-CPU 快路径与业务同步
   SLUB 本地 freelist 降低分配锁竞争；对象字段并发仍由子系统同步协议保护。

RCU 延迟释放与类型安全
   ``SLAB_TYPESAFE_BY_RCU`` 保护 slab 存储回收时机，不自动保护槽位内容、对象身份或引用取得。

一句话结论
----------

Slab/SLUB 通过同型对象槽位和 per-CPU 复用降低小对象成本，但对象身份、初始化、并发和最终回收仍必须由子系统生命周期协议完整证明。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 16，Kernel Memory Allocation Slab, Slub, Vmalloc, and Per-CPU Memory；
* AIBook 章节：Chapter 78，Slab and Slub Object Caches；
* 源文件：``docs/LinuxK/Part_16_Kernel_Memory_Allocation_Slab_Slub_Vmalloc_and_Per_CPU_Memory/Chapter_078_Slab_and_Slub_Object_Caches.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_16_Kernel_Memory_Allocation_Slab_Slub_Vmalloc_and_Per_CPU_Memory/Chapter_078_Slab_and_Slub_Object_Caches.md>`_。