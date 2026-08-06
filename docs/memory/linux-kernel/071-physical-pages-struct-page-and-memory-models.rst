第071章：物理页、struct page 与内存模型
========================================

本章必须记住
------------

#. 物理内存进入 Linux 管理后，通常按 ``PAGE_SIZE`` 切分成固定大小的 page frame。
#. ``PAGE_SIZE`` 和 ``PAGE_SHIFT`` 由架构与内核配置决定，不能把所有系统都写死为 4 KiB。
#. PFN（Page Frame Number）是物理页框编号，不是物理地址，也不保存页面内容。
#. 物理地址右移 ``PAGE_SHIFT`` 得到 PFN；PFN 左移 ``PAGE_SHIFT`` 得到页框起始物理地址。
#. 一个普通 order-0 页表示一个 page frame；order-n 页块表示 ``2^n`` 个物理连续页框。
#. ``struct page`` 是物理页框的内核元数据描述符，真实数据仍存放在对应物理页中。
#. 内核通过 ``struct page`` 记录页面状态、引用、映射关系、LRU、buddy、复合页和上层归属。
#. ``struct page`` 大量使用 union 复用字段；解释字段前必须先确认页面当前属于空闲页、匿名页、文件页、slab、复合页还是设备页。
#. ``flags`` 记录页面状态及部分 node、zone 信息，具体位布局和 helper 具有版本与架构差异。
#. 页面引用计数表示仍有多少内核路径要求页面保持存活，应通过 ``get_page()``、``put_page()``、folio helper 等接口操作。
#. 页表映射计数与普通页面引用不是同一概念；页面可以仍被内核引用，却没有用户页表映射。
#. 一个文件页可以被多个进程映射；一个页面也可以被页缓存、回写或 I/O 路径持有而暂时不在用户页表中。
#. ``mapping`` 等字段把页面连接到文件 ``address_space``、匿名反向映射或特殊内存对象。
#. 空闲页进入 buddy allocator 后，同一组字段会被解释为 buddy 链表、order 和迁移类型状态。
#. 复合页由一个 head page 和若干 tail page 组成；许多操作必须先通过 ``compound_head()`` 或 folio 接口回到头页。
#. Folio 是一组连续、对齐并作为同一内存对象管理的页面视角，不取消 ``struct page`` 作为底层页框元数据的作用。
#. PFN 与 ``struct page`` 之间通过 ``pfn_to_page()`` 和 ``page_to_pfn()`` 转换。
#. 不是所有数值 PFN 都对应可正常解引用的普通 RAM ``struct page``；转换前要确认 PFN 有效且属于目标内存模型管理范围。
#. ``pfn_valid()`` 只回答架构和内存模型定义下的有效性条件，不能自动证明页面当前在线、可分配或属于普通 RAM。
#. ``virt_to_page()`` 通常只适用于内核直接映射中的普通内存地址，不能用于用户地址、``vmalloc`` 地址或 ``ioremap`` 地址。
#. ``page_to_virt()`` 同样依赖直接映射条件；高端内存、设备内存和特殊映射需要对应的映射接口。
#. 用户虚拟地址必须先经过进程页表得到 PFN，再关联 ``struct page``；不能直接用用户指针做 ``virt_to_page()``。
#. ``vmalloc`` 地址对应虚拟连续、物理可分散的页面，应使用 ``vmalloc_to_page()`` 等匹配接口。
#. ``ioremap`` 返回设备 MMIO 映射，其地址语义是 ``__iomem``，不能当普通 RAM 页面处理。
#. FLATMEM 使用接近线性的全局 memmap 组织页描述符，适合物理地址空间较连续的系统。
#. SPARSEMEM 把物理地址空间分成 section，只为存在的范围建立或连接页元数据，适合稀疏大内存和热插拔。
#. ``SPARSEMEM_VMEMMAP`` 常用虚拟连续的 vmemmap 映射组织 ``struct page``，PFN 到页描述符的转换仍由内存模型接口封装。
#. 内存模型决定页元数据怎样定位，不改变 PFN 表示物理页框编号这一基本语义。
#. 物理内存热插拔需要建立、上线、隔离和移除对应 section、node、zone 与页元数据，不能只修改一个容量数字。
#. ``ZONE_DEVICE`` 等设备内存也可能拥有 ``struct page``，但其访问、迁移、引用和释放规则不能按普通系统 RAM 套用。
#. 页面属于哪个 node 和 zone，是后续水位、NUMA、回收和分配路径的重要输入。
#. 页面描述符内存本身也有成本；大内存机器需要用稀疏模型、vmemmap 优化和复合页策略控制元数据开销。
#. 排查一个物理页时，应先确认 PFN、node、zone、页面类型和 head/tail 关系，再解释 flags、引用和 mapping。
#. ``struct page`` 的联合字段不能脱离状态机读取；同一字段位置在不同页面状态下可能具有完全不同含义。
#. Page flags、引用计数和 mapcount 的瞬时值会并发变化，静态读取需要配合锁、引用、dump 工具或稳定观察协议。
#. 内核分配器、页表、页缓存、回收和迁移操作的共同对象不是裸物理地址，而是 PFN 与页面元数据组成的管理对象。

必背路径
--------

从物理地址定位页面对象：

::

   物理地址
   → 按 PAGE_SHIFT 得到 PFN
   → 确认 PFN 属于有效并在线的受管范围
   → pfn_to_page 定位 struct page
   → 判断 node、zone 和页面类型
   → 判断 compound head / tail
   → 再读取 flags、引用和 mapping

从用户地址定位物理页：

::

   用户虚拟地址
   → 找到 task 与 mm_struct
   → 查找 VMA 与访问权限
   → 遍历页表得到页表项
   → 从页表项提取 PFN
   → 确认该 PFN 可以关联普通 struct page
   → 分析页面元数据和上层归属

页面状态转换：

::

   buddy 中的空闲页
   → 分配器摘除空闲块
   → 建立页面引用和用途
   → 进入匿名页、文件页、slab 或其它对象
   → 解除映射和上层持有
   → 引用归零并完成清理
   → 返回 PCP 或 buddy

内存模型转换：

::

   固件提供物理内存范围
   → 早期内核建立 PFN 范围
   → FLATMEM 或 SPARSEMEM 建立页元数据组织
   → pfn_to_page / page_to_pfn 屏蔽模型差异
   → node、zone 和 allocator 接管页面

必须区分
--------

* 物理页内容与 ``struct page``：物理页保存实际数据；``struct page`` 保存管理这页所需的元数据。
* PFN 与物理地址：PFN 是页粒度编号；物理地址是字节粒度地址。
* 页面引用与页表映射：引用保证页面仍被持有；mapcount 描述页表映射关系，二者不能互相替代。
* 普通页与复合页：普通页单独管理；复合页由 head page 统一承载主要状态，tail page 不能独立解释。
* 直接映射与 ``vmalloc`` / ``ioremap``：直接映射地址可按普通 RAM 规则转换；虚拟映射和设备映射必须使用匹配接口。
* FLATMEM 与 SPARSEMEM：二者决定页描述符怎样组织和定位，不改变 PFN 与物理页框的基本关系。

一句话结论
----------

Linux 先把物理内存编号为 PFN，再用 ``struct page`` 把每个可管理页框变成具有状态、引用、归属和生命周期的内核对象。
