第053章：Escape Analysis and Object Lifetime
===========================================

核心知识点
----------

* Escape analysis 回答“对象地址是否越过当前优化器可完整控制的区域”。返回地址、写入全局、传给未知调用、存入堆对象、闭包捕获或跨线程共享都可能让对象逃逸。
* 对象是否逃逸决定它是否必须真正物化成可长期访问的内存对象。未逃逸对象可能只存在于寄存器、SSA values 或局部栈槽中。
* 源码“局部变量”不等于机器“栈对象”。真正分配位置由对象生命期、地址可见性、运行时策略、大小和 ABI 等共同决定。
* 若对象地址不会在函数返回后继续被观察，编译器就有机会进行 stack allocation、allocation sinking、allocation elimination 等局部化优化。
* 返回对象地址或把地址写入全局会扩展对象生命期；编译器必须保证所有后续合法访问期间对象仍然存在。
* Scalar Replacement of Aggregates（SROA）依赖更强前提：对象不仅不逃逸，还不能有需要稳定整体地址/身份的观察；字段必须能拆成独立 SSA values。
* SROA 可删除聚合对象的 load/store，把字段值直接变成 scalar def-use，从而降低内存访问和 alias-analysis 压力。
* 对象地址身份、反射、FFI、未知函数、指针比较、可观察析构、异常清理等都可能阻止对象完全消失。
* Lifetime marker 描述存储在程序语义上何时有效，可帮助栈槽复用、DSE、GC/root 管理和 sanitizer；它不是普通业务逻辑中的显式分配/释放调用。
* 生命期与存储位置是不同维度。对象可以逻辑上结束生命期但物理栈空间仍存在，也可以在堆上由 GC 延迟回收。
* Escape analysis 通常是保守的数据流问题。未知调用如果可能捕获指针，就必须把对象视为可能逃逸，除非属性、内联或过程间分析提供更强证据。
* 编译器可以在不同粒度上做逃逸分析：函数内、内联调用簇、模块或 JIT 当前可见调用图。上下文越大，可能发现越多不逃逸事实，但分析成本更高。
* 最终决策还受实现成本模型影响。即使语义上可以栈分配，超大对象、动态尺寸、递归深度或目标运行时策略也可能让编译器保留堆分配。

关键路径
--------

逃逸判断：

::

   allocation site
   → trace address/value uses
   → return / global store / unknown call / capture / thread share?
   → yes: object escapes local region
   → no: local allocation candidate

对象消除：

::

   prove non-escaping
   → check address identity is unobservable
   → decompose fields
   → replace field loads/stores with SSA values
   → eliminate allocation if no remaining memory semantics

生命期检查：

::

   allocation
   → lifetime start
   → all legal uses
   → cleanup / lifetime end
   → verify no pointer outlives object
   → choose storage/reuse strategy

概念辨析
--------

* **Escape 与 heap allocation**：逃逸通常要求更长生命期，但具体是否放堆由语言/runtime 决定；二者不是定义上的同义词。
* **Local variable 与 stack object**：源码局部变量可能完全寄存器化，也可能因逃逸进入堆。
* **Stack allocation 与 scalar replacement**：前者仍保留对象内存，后者进一步把对象拆成独立值甚至消除物化。
* **Object lifetime 与 storage lifetime**：对象语义生命期结束不等于底层存储立即释放或清零。
* **Address escape 与 value escape**：把对象字段值返回不等于对象地址逃逸；关键是外部是否获得继续访问该对象存储的能力。

本章结论
--------

逃逸分析决定“这个对象必须有多真实”。只要地址和对象身份没有越过局部可控边界，编译器就能把堆对象收缩为栈对象、把聚合对象拆成 SSA values，甚至完全消除物化；一旦地址外流，优化器首先要保证生命期和后续可达访问正确，再谈分配成本。