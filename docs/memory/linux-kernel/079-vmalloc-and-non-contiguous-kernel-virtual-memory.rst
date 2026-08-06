第079章：vmalloc 与非连续内核虚拟内存
=====================================

核心知识点
----------

``vmalloc`` 保证虚拟连续
   返回区域在内核虚拟地址空间中连续，CPU 可以使用普通指针线性访问；对应物理页可以彼此分散。

物理连续性是独立属性
   ``vmalloc`` 不保证连续 PFN、DMA 连续或设备可寻址。硬件访问必须通过 DMA API、scatter-gather 或设备专用分配机制建立。

``vmalloc`` 适合大块 CPU 区域
   当调用者只需要虚拟连续，并希望避免大块 ``kmalloc`` 对高阶物理页的依赖时，可以使用 ``vmalloc`` family。

分配过程包含映射建立
   内核先保留连续 vmalloc 虚拟区间，再取得 backing pages，并为每个虚拟页建立内核页表项。

灵活性带来额外成本
   区域创建和销毁需要管理虚拟区间、页表与 TLB；分散页面还可能增加 TLB 压力并降低 NUMA 和缓存局部性。

普通分配路径允许睡眠
   ``vmalloc()`` 可能进入页面分配和页表建立，不能在 hardirq、softirq、持 spinlock 或其它原子上下文中调用。

释放接口取决于来源
   ``vmalloc``、``vzalloc`` 结果由 ``vfree()`` 释放；``kvmalloc`` family 的来源可能是 kmalloc 或 vmalloc，应统一使用 ``kvfree()``。

``kvmalloc`` 表示可退化来源
   它通常先尝试 ``kmalloc``，再退到 ``vmalloc``。调用者必须从一开始就按物理页可能分散的语义使用返回区域。

``vmap`` 只负责映射已有页面
   ``vmap()`` 把调用者持有的 page 集合映射成连续虚拟地址，``vunmap()`` 只撤销映射，页面所有权仍由调用者管理。

普通直接映射转换不适用
   ``virt_to_phys()`` 和 ``virt_to_page()`` 不能用于一般 vmalloc 地址。应使用 ``vmalloc_to_page()`` 等接口逐页取得 backing page。

用户映射延长对象生命周期
   Vmalloc 页面映射给用户空间后，必须先撤销用户可见性并等待相关引用结束，才能释放原区域。

可执行区域需要专用协议
   模块、BPF 和内核文本使用具有权限转换和 W^X 约束的专用 vmalloc-like 路径，普通 ``vmalloc`` 区域不能直接当作可执行内存。

Vmalloc 虚拟地址空间也可能耗尽
   失败不仅可能来自物理页不足，还可能来自连续虚拟区间不足、区域碎片或页表资源不足。

关键路径
--------

``vmalloc`` 分配：

::

   确认只要求 CPU 虚拟连续访问
   → 确认允许物理页分散
   → 确认当前上下文可以睡眠
   → 保留连续 vmalloc 虚拟区间
   → 分配多个 backing pages
   → 建立内核页表映射
   → 返回起始虚拟地址
   → 处理 NULL 失败

``vmalloc`` 释放：

::

   阻止新访问和新用户映射
   → 等待引用、work、timer 与异步路径结束
   → vfree 撤销虚拟映射
   → 使旧 TLB 翻译失效
   → 归还 backing pages 和区域元数据
   → 原指针立即失效

分析 vmalloc 地址：

::

   确认地址属于有效 vmalloc 区域
   → 找到区域起点与长度
   → 对每个虚拟页调用 vmalloc_to_page
   → 分别取得 backing page 和 PFN
   → 不假设相邻 PFN
   → 检查区域生命周期与页表权限

选择分配接口：

::

   小对象或确需物理连续特征
   → 使用 kmalloc
   → 大块且只需虚拟连续
   → 使用 vmalloc
   → 希望小块优先 kmalloc、大块允许退化
   → 使用 kvmalloc
   → kvmalloc 结果统一 kvfree

设备访问 vmalloc 数据：

::

   识别访问者是设备
   → 不把 vmalloc 虚拟地址直接交给硬件
   → 检查 DMA mask 与一致性要求
   → 组织 backing pages 或 scatterlist
   → 使用 DMA API 建立总线映射
   → 完成同步、unmap 和原内存释放

概念辨析
--------

虚拟连续与物理连续
   ``vmalloc`` 保证前者；背后物理页可以分散，不能直接满足连续物理需求。

``vmalloc`` 与 ``vmap``
   ``vmalloc`` 同时取得页面并建立映射；``vmap`` 只映射调用者已经持有的页面。

``vfree`` 与 ``kvfree``
   ``vfree`` 面向明确 vmalloc 来源；``kvfree`` 面向可能来自 kmalloc 或 vmalloc 的 kvmalloc 结果。

CPU 地址与 DMA 地址
   CPU 通过内核页表解释 vmalloc 指针；设备需要 DMA API 建立可见的总线地址。

物理页不足与虚拟区不足
   前者缺少 backing pages；后者缺少连续 vmalloc 地址区间或页表资源。

底层延迟回收与访问权限
   实现可以延迟部分 TLB 或区域清理，但调用者在释放后立即失去访问权。

本章结论
--------

``vmalloc`` 用页表把分散物理页拼成连续内核虚拟区域，换取更高的大块分配灵活性。它适合可睡眠的 CPU 访问路径，不提供物理连续或 DMA 保证。