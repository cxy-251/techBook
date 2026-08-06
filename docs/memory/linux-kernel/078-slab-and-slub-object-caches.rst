第078章：Slab 与 SLUB 对象缓存
===============================

核心知识点
----------

Slab 是同型对象缓存模型
   Cache 从 page allocator 取得一组页面，再把它们切成大小、对齐和属性相同的对象槽位。对象释放后回到缓存等待复用。

SLUB 是常见实现
   SLUB 通过 ``struct kmem_cache``、per-CPU freelist、node partial slab 和 backing pages 实现 slab 模型，重点优化高频分配的局部路径。

``kmem_cache`` 保存类型化规则
   Cache 描述对象大小、实际槽位大小、对齐、标志、构造函数、节点状态和 per-CPU 分配状态。它比普通字节分配携带更多对象语义。

通用 cache 与专用 cache 分工
   ``kmalloc-*`` cache 按大小等级服务普通请求；专用 cache 面向 VMA、inode、dentry 等高频固定类型对象，便于统计、调试和回收。

SLUB 快路径优先本 CPU 槽位
   当前 CPU freelist 命中时可以减少全局锁和 cacheline 迁移。无可用对象时再寻找 partial slab，必要时向 page allocator 申请新页面。

Slab 状态反映槽位使用情况
   一个 slab 可以为空、部分使用或已满。分配器重点维护仍可提供对象的 partial slab，并在条件满足时回收空 slab 页面。

构造函数不等于每次初始化
   Cache constructor 通常面向槽位的基础状态，不保证每次 ``kmem_cache_alloc()`` 都执行。引用计数、所有权和业务字段必须在每次分配后重新建立。

槽位存活不等于对象身份存活
   ``kmem_cache_free()`` 后，同一地址可以立即承载新对象。旧指针即使仍指向有效 slab 存储，也不再指向原对象。

远程释放会增加共享成本
   对象在非分配 CPU 上释放时，freelist 和缓存行可能跨 CPU 流动。Per-CPU 分配优化不替代子系统的对象同步和所有权设计。

调试能力会改变布局与成本
   Red zone、poisoning、freelist hardening、KASAN、KFENCE 和 SLUB debug 能发现越界、UAF、double free 与 freelist 损坏，但会增加元数据和路径开销。

``SLAB_TYPESAFE_BY_RCU`` 只保护存储回收时机
   RCU grace period 可以延迟 slab 页面归还，却不能阻止同一槽位被新对象复用。读者仍需验证对象身份并安全取得引用。

Shrinker 与 SLUB 职责不同
   子系统 shrinker 选择哪些缓存对象可以被回收；SLUB 只负责对象槽位和 backing pages 的最终管理。

Cache 销毁要求所有使用者结束
   ``kmem_cache_destroy()`` 前必须停止新分配，释放活动对象，并同步 RCU、work、timer 等延迟路径。

关键路径
--------

专用 cache 生命周期：

::

   子系统初始化
   → kmem_cache_create 定义大小、对齐和标志
   → kmem_cache_alloc 取得槽位
   → 每次初始化对象实例状态
   → 发布对象并管理引用
   → 停止新查找并等待旧使用者
   → kmem_cache_free 归还槽位
   → 所有对象和异步路径结束
   → kmem_cache_destroy

SLUB 分配路径：

::

   当前 CPU 请求对象
   → 检查 per-CPU freelist
   → 命中时摘取本地槽位
   → 未命中时查找 node partial slab
   → 仍无可用槽位时申请 backing pages
   → 建立新 slab 和 freelist
   → 返回槽位给调用者初始化

对象释放与复用：

::

   从外部结构摘除对象
   → 等待引用、RCU 和异步访问结束
   → 清理敏感字段或对象私有资源
   → kmem_cache_free
   → 槽位进入 freelist
   → 同一地址可能承载新对象
   → 旧身份和旧指针全部失效

``SLAB_TYPESAFE_BY_RCU`` 查找：

::

   在 RCU 读侧定位槽位
   → 读取对象身份字段
   → 尝试增加普通引用
   → 再次验证身份未变化
   → 成功后离开 RCU 并使用对象
   → 失败时重新查找
   → 最终 put 归还引用

分析对象损坏：

::

   确认 cache、对象地址和合法边界
   → 读取 alloc stack 与 free stack
   → 区分越界、UAF、double free 或 freelist 损坏
   → 检查对象发布点和最后引用
   → 检查远程释放和异步回调
   → 在相同调试配置下验证修复

概念辨析
--------

Slab 抽象与 SLUB 实现
   Slab 是同型对象复用模型；SLUB 是实现该模型的具体分配器。

通用 cache 与专用 cache
   通用 cache 按大小分类；专用 cache 还表达对象类型、对齐、回收和调试属性。

构造函数与每次初始化
   Constructor 不一定每次分配执行；每个实例的可变状态必须重新初始化。

槽位存活与对象身份
   存储仍属于 slab 不代表旧对象仍存在，释放后槽位可以立即复用。

Per-CPU 快路径与业务同步
   本地 freelist 只降低分配器竞争；对象字段仍需锁、引用、RCU 或其它协议保护。

RCU 延迟回收与类型安全
   ``SLAB_TYPESAFE_BY_RCU`` 延迟 slab 存储释放，不自动保证槽位内容、对象身份或引用取得安全。

本章结论
--------

Slab/SLUB 通过类型化槽位和 per-CPU 复用降低小对象成本。分配器管理存储，子系统仍必须证明对象初始化、身份、并发访问和最终回收正确。