Call Stack, Heap, Object Allocation, and Garbage Collection
===========================================================

核心知识点
----------

* Call stack 表示当前同步执行链：函数调用、返回位置、局部执行状态和异常展开都在这里体现；它回答“现在正在运行什么”。
* Heap 保存对象、数组、函数、闭包环境、Promise、Map/Set、框架状态、缓存等长期运行时对象；它回答“哪些对象仍然存在、为何仍可达”。
* GC 以可达性为核心：从 roots 出发仍可到达的对象必须保留，不可达对象才具备回收资格。业务上“已经不用”不等于运行时“已经不可达”。
* 闭包把局部 binding 的生命周期从当前调用栈延长到 heap 引用图。listener、timer、Promise continuation、subscription 都可能成为长期 owner。
* DOM 节点属于浏览器 DOM runtime，但 JavaScript wrapper、事件 listener 和闭包可以形成跨 JS/DOM 的保留链；从文档移除的 detached DOM 仍可能因 JS 引用而存活。
* allocation pressure 与 retained size 是两类问题：前者是单位时间创建对象过多、GC 频繁；后者是 GC 后 live heap 仍持续增长，通常指向 cache、listener、closure 或状态生命周期失配。
* 现代 GC 常采用 generational、incremental、parallel、concurrent 等策略降低停顿，但具体实现属于引擎细节；应用无法把 GC 当作精确业务调度接口。
* 内存优化的核心是所有权与生命周期：谁创建、谁引用、何时释放、缓存如何淘汰、异步工作何时失效。

关键路径
--------

一次交互中的对象生命周期：

``event task → call stack → allocate objects/closures → store references in state/cache/listener → stack returns → heap objects remain reachable``

GC 判断：

``GC roots → global / active stack / host-held callbacks / live DOM bindings → reference graph → reachable objects kept → unreachable objects reclaimed``

典型泄漏链：

``long-lived listener / timer → closure → component state / DOM reference → detached subtree → cannot be collected``

排查顺序：

``当前是否有长同步调用 → allocation rate 是否过高 → GC 后 heap baseline 是否回落 → 找 retained object → 查看 retaining path → 修正 owner / cleanup / cache policy``

概念辨析
--------

* **Call stack vs Heap**：stack 记录当前同步执行；heap 保存可跨调用存活的对象图。
* **Allocation pressure vs Memory leak**：高分配率可能造成频繁 GC但最终能回落；memory leak 指本应释放的对象仍被引用，live heap 基线不断上升。
* **Closure vs Leak**：闭包是正常语言能力；闭包生命周期超过业务生命周期且保留大对象时才形成问题。
* **Detached DOM vs Removed DOM**：节点从 document 移除只改变 DOM 归属；仍有 JS 引用时不会自动消失。
* **GC pause vs Long task**：GC 可能贡献主线程停顿，但长任务也可能来自脚本、布局、框架更新；需要 Performance/Memory 证据区分。
* **Cache vs Leak**：缓存是有意保留；没有容量、TTL、路由生命周期或淘汰策略的缓存会表现得像泄漏。

本章结论
--------

内存问题应沿 ``Active Stack → Allocation → Heap Reachability → GC → Retaining Path`` 分析。先区分“当前执行太久”与“对象长期不释放”，再区分“分配太快”与“存活体积持续增长”。最终修复点通常不是手动控制 GC，而是明确 state、cache、listener、timer、DOM 和异步 continuation 的所有者与清理时机。
