第079章：Garbage Collection and Memory Safety Support
=====================================================

核心知识点
----------

* GC 把堆对象何时释放的决定交给 runtime，但 collector 能正确工作，依赖编译器持续提供“哪些值是引用、这些引用当前在哪里、哪些程序点可安全暂停”的精确信息。
* GC 的核心判据是 reachability。Collector 从 roots 出发遍历对象图，只保留仍可到达的对象；源码作用域只是线索，真正 root 集合来自机器级 live references。
* Roots 可以位于 stack slots、registers、globals、TLS、runtime handle tables 等位置；编译器尤其负责把当前函数帧中的 live GC references 映射到机器位置。
* Stack map/GC map 把 safepoint 与 live value locations 关联起来。运行时据此知道某个引用位于哪个寄存器、哪个栈偏移，或如何通过表达式恢复。
* Precise GC 要区分“GC pointer”和普通整数/非 GC 指针。精确追踪能减少误保留，并允许 moving collector 安全更新引用。
* Safepoint 是编译代码和 collector 约定的可暂停、可解析、可更新位置。把 GC 只允许在有限 safepoints 发生，可以避免在任意机器指令处恢复所有引用状态。
* Moving collector 可以把对象从旧地址搬到新地址；源语言对象身份必须保持不变，因此所有 roots 和对象字段中的旧引用都要被更新。
* 编译器在 safepoint 前必须保证所有未来仍会使用的 GC references 都被 materialize 到 runtime 可枚举的位置；遗漏一个 live reference 就可能形成 use-after-move 或错误回收。
* 对象布局同样是 GC 协议的一部分。Runtime 需要知道对象中哪些字段是引用、哪些是普通数据，才能从一个对象继续追踪子对象。
* Write barrier 在对象字段写入时维护 collector 不变量。Generational GC 中常用于记录 old-to-young reference；并发/增量 collector 还可能通过 barrier 维护标记状态。
* Read barrier 由部分 collector 使用，在读取引用时完成转发、标记或一致性动作。是否需要 barrier 取决于 collector 设计，并非所有 GC 都相同。
* Barrier 可以被编译器 inline 成快速检查，也可以 lower 成 runtime helper；优化器不能把它当作普通无副作用指令删除或跨越相关内存写重排。
* GC 与内存安全不是同义词。GC 主要解决对象生命周期和可达性；bounds、类型安全、data race、unsafe/native pointer 等仍需要其它语言和运行时机制。
* Native/FFI 边界会增加 GC 难度。对象引用离开 managed frame 后通常需要 handle/pinning/stack-map 协议，避免 collector 移动对象时 native code 持有失效地址。
* GC bug 排查应从 safepoint、liveness、root map、object layout 和 barrier 五类证据入手，而不是只看 collector 算法名称。

关键路径
--------

GC root 生成：

::

   IR values marked as GC references
   → liveness at possible collection points
   → register allocation / spill locations
   → emit stack map / GC map
   → runtime pauses at safepoint
   → enumerate roots
   → trace object graph

Moving collection：

::

   safepoint reached
   → stop / coordinate mutator
   → read roots and object layout
   → move surviving objects
   → produce new addresses
   → update roots and object fields
   → resume generated code with relocated references

Barrier：

::

   object reference store/read
   → check collector policy
   → inline fast barrier or call helper
   → update remembered/marking state
   → perform/complete memory access

概念辨析
--------

* **Source variable 与 GC root**：源码变量名可以消失，GC root 是 safepoint 上真实可达的机器级引用位置。
* **Stack map 与 debug info**：前者服务运行时正确性和引用更新，后者服务源码调试；二者都描述位置，但目的不同。
* **Safepoint 与 arbitrary instruction**：collector 通常只在状态可解析的受控点暂停，不要求任意 PC 都能恢复精确引用集合。
* **Moving GC 与 object identity**：物理地址可以改变，语言层对象身份必须保持。
* **GC 与 complete memory safety**：GC 防止一类生命周期错误，但不自动解决越界、竞态或 unsafe/native misuse。

本章结论
--------

GC 是编译器和 runtime 共同维护的对象生命周期协议。稳定理解路径是 ``GC Reference → Liveness → Safepoint/Stack Map → Root Trace → Move/Collect → Barrier-Maintained Heap``；collector 是否正确，首先取决于编译器有没有把每一个仍然重要的引用位置和对象布局准确交给运行时。