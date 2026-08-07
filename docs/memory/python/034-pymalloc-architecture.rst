第034章：Pymalloc 架构
======================

核心知识点
----------

* CPython 的对象“被销毁”与进程 RSS “立即下降”属于两个层级。对象引用计数归零后会释放对象占用的存储，但底层 block 可能继续保留在 freelist、pool、arena 或系统 allocator 中等待复用。
* 常规 GIL-enabled CPython 中，pymalloc 主要优化小对象分配。公开文档中的当前小对象阈值为 512 bytes；超过阈值的请求会进入底层 allocator 路径。
* pymalloc 的三层模型是 **arena → pool → block**：arena 管理大块地址空间，pool 服务单一 size class，block 是最终交给小对象使用的内存块。
* small object allocator 会先把请求映射到 size class，再从对应 pool 的 free block 中分配；固定 size class 减少频繁切割、合并和系统 ``malloc`` 调用。
* 一个 pool 通常只服务一个 size class。这样释放 block 时可以直接回到对应 free list，代价是请求大小与 class 大小之间存在内部碎片。
* arena 只有在内部 pool 状态满足归还条件时才可能进一步还给底层 allocator；少量长寿命对象占住若干 pool，就可能让整个 arena 长时间保留。
* Python 层短时间大量创建、销毁小对象后，RSS 保持高位并不能单独证明存在对象泄漏；需要同时观察活对象数量、allocator 统计和长寿命引用图。
* 对象类型还可能维护自己的 **freelist**。freelist 认识“可复用的某类对象壳”，而 pymalloc 只认识“N bytes 的 block”；两者属于不同缓存层。
* tuple、list、frame 等高频对象路径可能利用类型级复用策略，具体对象和上限会随 CPython 版本变化。
* 地址被重新分配给新对象后，CPython 的 ``id()`` 可以快速复用旧值。因此历史 ``id`` 不能当作跨生命周期的永久对象编号。
* CPython C API 把内存分配划分为 Raw、Mem、Object 等 domain；分配和释放必须保持同一 domain，不能把 ``PyMem_Malloc``、``PyObject_Malloc`` 与系统 ``free`` 随意混用。
* 类型对象通常通过 ``tp_alloc``、``tp_free``、``PyObject_New``、``PyObject_GC_New`` 等接口把通用内存块连接到具体 Python 对象布局和 GC 约定。
* 对象内部的大缓冲不一定和对象壳走同一路径。list 元素数组、dict 表、bytes 大数据区等可能跨出 pymalloc 小对象路径。
* 内存 profile 前应确认解释器版本、build 类型、``PYTHONMALLOC`` 配置和平台 allocator；free-threaded build 的默认 allocator 路径可能与常规构建不同。

关键路径
--------

小对象分配路径：

::

   object/type requests memory
       ↓
   request size <= small-object threshold ?
       ├─ no  → underlying allocator
       └─ yes
            ↓
        map to size class
            ↓
        find pool for this class
            ↓
        take free block
            ↓
        initialize Python object
            ↓
        object enters runtime

对象释放后的多层复用路径：

::

   refcount reaches zero
       ↓
   object deallocator runs
       ↓
   type freelist accepts object shell ?
       ├─ yes → keep for same-type reuse
       └─ no
            ↓
        block returned to pymalloc pool
            ↓
        pool becomes reusable
            ↓
        arena still contains live pools ?
            ├─ yes → arena retained
            └─ no  → may return to lower allocator

概念辨析
--------

* **对象释放与 RSS 下降**：对象语义生命周期结束，只说明对象不能再被使用；底层页是否归还给 OS 取决于多个 allocator 层的状态。
* **freelist 与 pymalloc pool**：freelist 是类型级对象缓存，知道对象种类；pool 是通用小块内存缓存，只按 size class 管理 block。
* **arena、pool、block**：arena 是大范围管理单位，pool 是单一 size class 的区域，block 是实际小对象分配单位。
* **内部碎片与泄漏**：size class 多分配出的空间属于 allocator 内部碎片；真正 leak 是对象或内存块失去合理释放路径却持续占用资源。
* **``id`` 复用与对象复活**：新对象获得旧地址只表示 allocator 复用了内存，并不表示旧对象继续存在。
* **Raw、Mem、Object domain**：它们是 C API 内存所有权边界；选择哪个接口取决于这块内存是否属于 Python object、Python private heap 或更底层 raw buffer。

本章结论
--------

Pymalloc 应按“对象生命周期 → 类型级 freelist → block → pool → arena → 底层 allocator”分层理解。Python 对象已经销毁后，内存仍可能在进程内被缓存和复用，因此排查内存问题时不能只看 RSS。先确认活对象是否持续增长，再确认请求属于哪个 size class、是否命中 freelist、pool 和 arena 是否仍被长寿命对象占用，最后再判断系统 allocator 是否真正持有无法回收的内存。