第070章：gcmodule.c and obmalloc.c
==================================

核心知识点
----------

* CPython 内存生命周期要分三层：引用计数负责大多数对象的直接释放，cyclic GC 补充处理容器引用环，``obmalloc``/pymalloc 负责小对象内存块的分配与复用。
* cyclic GC 只关注可能形成引用环的 container objects。``int``、普通不可变字符串等没有内部 Python 引用边的对象通常不需要参与循环图扫描。
* GC tracking 说明对象是否进入 cyclic GC 候选集合，不表示对象“由 GC 而非引用计数管理”。被 tracking 的对象仍持续维护引用计数。
* 一个环在外部仍可达时不是垃圾；只有当候选对象图没有候选集合外部的有效引用时，GC 才把它视为 unreachable。
* 循环检测的核心思路是从候选对象真实引用计数复制临时计数，再通过 ``tp_traverse`` 扣除候选集合内部引用；仍有外部引用贡献的对象是 reachable，无外部贡献的集合进入 unreachable 处理。
* ``tp_traverse`` 让 GC 看见扩展对象内部引用；``tp_clear`` 用于打断不可达容器之间的强引用。自定义 C 容器类型若声明 GC 支持，必须正确实现这些协议。
* weakref、finalizer、对象复活和 ``tp_clear`` 让收集顺序比“发现环 → free”更复杂。现代 finalization 语义允许安全处理更多带 ``__del__`` 的循环。
* generational GC 用“年轻对象更可能很快死亡”的经验减少扫描成本。generation/threshold 的具体策略会随 CPython 版本演进，应以目标版本 ``gc`` 文档和源码为准。
* ``gc.collect()`` 解决的是对象图可达性，不保证进程 RSS 同步下降。对象释放后的内存可能仍停留在 pymalloc arena、system allocator 或 OS page cache 中。
* pymalloc 面向大量小 Python 对象：典型层级是 block → pool → arena。小尺寸请求映射到 size class，从合适 pool 取 block；pool 再属于更大的 arena。
* block 被释放后通常先回到 pymalloc 可复用结构，而不是立刻交回 OS。只有 arena 整体满足释放条件时，才有机会把较大内存区域归还底层 allocator。
* pymalloc 管理的是 raw memory，不决定 Python 对象是否可达。对象 deallocator 先结束对象生命周期，再把对应内存交给 allocator。
* free-threaded CPython 的 GC/allocator 路径与默认 GIL build 有额外差异；并发 collector、mimalloc 等具体实现必须按版本与构建模式确认。

关键路径
--------

普通引用计数释放：

::

    strong reference removed
        ↓
    Py_DECREF
        ↓
    refcount > 0 ?
       ├─ yes → object remains alive
       └─ no  → type deallocator
                 ↓
              release child references/resources
                 ↓
              free object memory
                 ↓
              allocator reuse

引用环：

::

    container objects form cycle
        ↓
    external roots disappear
        ↓
    refcounts still > 0 due internal edges
        ↓
    cyclic GC selects tracked candidates
        ↓
    copy refcounts to temporary GC refs
        ↓
    tp_traverse subtracts internal candidate edges
        ↓
    distinguish reachable / unreachable
        ↓
    weakref/finalizer/resurrection handling
        ↓
    tp_clear breaks internal strong refs
        ↓
    normal DECREF/deallocation completes

pymalloc：

::

    small-object allocation request
        ↓
    choose size class
        ↓
    pool for that class
        ↓
    free block available?
       ├─ yes → return block
       └─ no  → obtain/init pool from arena
        ↓
    object uses block
        ↓ deallocation
    block returned to pool
        ↓
    pool/arena may be reused by later objects

排查“内存没降”：

::

    object still reachable?
       ↓ no
    cycle still uncollected?
       ↓ no
    Python object already deallocated
       ↓
    pymalloc/system allocator retains memory?
       ↓
    arena/page still resident in process RSS

概念辨析
--------

* 引用计数与 cyclic GC 不是两套互斥回收器；GC 是引用计数对循环的补充。
* ``gc.is_tracked(obj)`` 表示是否进入循环扫描候选，不表示对象是否“垃圾”。
* ``gc.collect()`` 返回值与释放给操作系统的字节数没有一一对应关系。
* 对象死亡与内存块复用是不同阶段；``id()`` 后续复用只说明地址被 allocator 再利用。
* generation 是 GC 扫描策略，不是对象语义属性。
* ``tp_traverse`` 用于暴露引用边，``tp_clear`` 用于打断边，deallocator 最终释放对象；三者职责不同。
* pool/arena 是 allocator 结构，不是 Python 对象容器，也不参与对象可达性判断。
* RSS 高不等于 Python 引用泄漏；必须先确认对象图，再确认 allocator 和 OS 层。

本章结论
--------

CPython 内存问题必须按“对象可达性 → 引用计数/循环 GC → 对象析构 → allocator → OS”分层。cyclic GC 通过 ``tp_traverse`` 分析候选图、通过 ``tp_clear`` 打断不可达环；pymalloc 再把已经释放对象留下的 small blocks 在 pool/arena 中复用。只要把 GC 和 allocator 混成一个概念，就无法正确解释 RSS、``gc.collect``、引用环和地址复用现象。