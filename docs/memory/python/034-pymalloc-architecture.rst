第034章：Pymalloc 架构
======================

核心知识点
----------

* CPython 的对象“被销毁”与进程 RSS “立即下降”属于两个层级。对象生命周期结束后，底层存储仍可能保留在 freelist、pymalloc pool/arena、mimalloc heap/page 或系统 allocator 中等待复用。
* **默认 GIL-enabled CPython** 通常使用 pymalloc 优化小对象分配。当前公开文档中的小对象阈值为 512 bytes；超过阈值的请求进入其它 allocator 路径。
* **free-threaded CPython 3.14 不使用 pymalloc 来分配 Python 对象**。它要求 ``mimalloc`` 作为 ``PYMEM_DOMAIN_MEM`` 与 ``PYMEM_DOMAIN_OBJ`` 的 allocator；在 free-threaded build 中不能切换回 pymalloc 或普通 malloc 作为这些 domain 的实现。
* 因此“CPython 小对象一定走 arena → pool → block”只适用于 pymalloc 路径，不是所有 3.14 build 的统一对象分配模型。分析内存前必须先确认是否为 free-threaded build。
* pymalloc 的三层模型是 **arena → pool → block**：arena 管理大块地址空间，pool 服务单一 size class，block 是最终交给小对象使用的内存块。
* pymalloc 会先把小对象请求映射到 size class，再从对应 pool 的 free block 中分配；固定 size class 减少频繁系统 ``malloc`` 调用，代价是存在内部碎片。
* 一个 pymalloc pool 通常只服务一个 size class。释放 block 时可以直接回到对应 free list；arena 只有在内部 pool 状态满足条件时才可能进一步归还给底层 allocator。
* free-threaded build 的 mimalloc 使用多个独立 heap，并结合 per-thread allocation 与并发回收策略降低锁竞争。不同 heap 的空闲内存不能任意互相复用，因此内存行为和 pymalloc 的 arena/pool 模型不同。
* free-threaded build 还使用 QSBR（quiescent-state based reclamation）保护部分允许无锁读取的数据结构。对象或容器逻辑上已经释放后，底层内存可能要等所有相关线程经过安全点才能真正重新使用或归还。
* ``gc.collect()`` 可以推动 QSBR 持有的部分待释放内存进入实际回收，但底层 mimalloc 仍可能继续缓存页面，因此 RSS 仍不保证立即下降。
* mimalloc 本身也会延迟把空闲内存归还给 OS；free-threaded 下的 RSS 调试必须把对象存活、QSBR 延迟、mimalloc page/heap 缓存三层分开。
* 对象类型还可能维护自己的 **freelist**。freelist 认识“可复用的某类对象壳”，而 allocator 只认识原始存储；两者属于不同缓存层。
* tuple、list、frame 等高频对象路径的具体 freelist 与复用策略会随 CPython 版本和 build mode 变化，不能作为稳定语言语义。
* 地址被重新分配给新对象后，CPython 的 ``id()`` 可以复用旧值。因此历史 ``id`` 不能当作跨生命周期的永久对象编号。
* CPython C API 把内存分配划分为 Raw、Mem、Object 等 domain；分配和释放必须保持同一 domain，不能把 ``PyMem_Malloc``、``PyObject_Malloc`` 与系统 ``free`` 随意混用。
* 默认非 free-threaded build 也可以在平台支持时显式选择 mimalloc；因此最终 allocator 仍要结合 build type 与 ``PYTHONMALLOC`` 判断。

关键路径
--------

先判断 allocator：

::

   CPython process
   → free-threaded build ?
      ├─ yes → mimalloc required for MEM / OBJ domains
      │          → per-thread / multiple heaps
      │          → QSBR may defer reclamation
      └─ no  → default usually pymalloc for small objects
                 → PYTHONMALLOC may select another supported allocator

pymalloc 小对象路径：

::

   object/type requests memory
       ↓
   request size <= 512-byte threshold ?
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

free-threaded 释放路径：

::

   object becomes logically reclaimable
       ↓
   direct free or QSBR-deferred reclamation ?
       ↓
   safe quiescent point reached
       ↓
   mimalloc heap/page receives free storage
       ↓
   reuse inside allocator
       or
   delayed return to OS

内存增长调查：

::

   RSS grows
   → are live Python objects growing ?
   → is memory waiting in GC / QSBR ?
   → which allocator is active ?
   → pymalloc arena retained or mimalloc heap/page retained ?
   → type freelist / cache still holds objects ?
   → only then classify leak vs allocator retention

概念辨析
--------

* **pymalloc 与 mimalloc**：pymalloc 是默认 GIL build 的小对象 allocator；free-threaded build 使用并要求 mimalloc 处理 MEM/OBJ domain。
* **arena/pool/block 与 mimalloc heap/page**：它们属于两套不同 allocator 的内部组织，不能把 pymalloc 名词套到 free-threaded 内存路径。
* **对象释放与 RSS 下降**：对象语义生命周期结束，只说明对象不能再被使用；底层页是否归还给 OS 取决于 allocator 和延迟回收状态。
* **QSBR 与内存泄漏**：QSBR 为并发安全主动延迟复用/释放；等待安全点的内存不等于失去引用而无法回收的 leak。
* **freelist 与 allocator cache**：freelist 是类型级对象缓存；pymalloc/mimalloc 管理更底层原始存储。
* **内部碎片与泄漏**：size class 或 heap page 没有完全利用属于 allocator 成本；真正 leak 是对象或内存失去合理释放路径却持续增长。
* **Raw、Mem、Object domain**：它们是 C API 内存所有权边界；底层具体实现可以随 build 与配置改变。

本章结论
--------

2026 年理解 CPython 内存不能再把 pymalloc 当成唯一对象 allocator。默认 GIL build 仍以 ``arena → pool → block`` 的 pymalloc 模型解释小对象；free-threaded 3.14 则必须切到 mimalloc，并叠加 QSBR 等并发回收机制。排查内存时第一步应是确认 build 与 allocator，再区分活对象、延迟回收、allocator 缓存和真正泄漏。