第054章：Side Effects, Volatile, and Observable Behavior
========================================================

核心知识点
----------

* 优化器真正必须保持的是语言、IR 和目标平台定义的 observable behavior，而不是源码语句数量或局部变量形状。
* Pure computation 只消费 values 并产生 result；side-effecting operation 还会修改或观察内存、I/O、同步状态、异常状态、设备寄存器或其它外部世界。
* 纯计算最适合 constant folding、CSE、DCE 和 code motion；副作用操作的删除、合并和移动必须先证明可观察事件保持。
* 未知函数调用是典型 effect boundary。缺少函数体或属性时，通常要保守认为它可能读写内存、抛异常、阻塞、执行 I/O、捕获指针或调用运行时。
* Function attributes/effect summaries 可以缩小调用边界，例如“只读内存”“不访问内存”“不抛异常”等；这些属性本身是优化正确性的契约。
* ``volatile`` 的核心是访问本身具有可观察性。编译器不能像普通 load/store 那样随意删除、合并访问次数或改变要求保持的 volatile 顺序。
* ``volatile`` 不等于 atomic，也不建立完整线程同步。跨线程通信、happens-before 和内存序需要 atomic、lock、fence 或语言并发模型提供证据。
* I/O 调用通常直接连接外部世界，不能因为返回值无人使用就删除；设备寄存器访问同样可能通过读取/写入动作本身产生效果。
* Atomic operation 与 fence 同时约束编译器和硬件可重排范围。合法优化必须遵守 memory order、同步关系和数据竞争语义。
* 可能抛异常、trap 或触发用户代码的 operation 也属于控制流可观察边界。把它提前到原本不会执行的路径可能新增失败行为。
* Side-effect ordering 不意味着所有普通计算都固定不动。只要 operand 可用、没有新增异常且可观察事件顺序保持，纯计算仍可跨某些 effect 边界重排。
* Debug info 通常不是普通运行时 observable behavior，但优化器仍需按工具链契约尽量维护 source mapping；这与程序语义正确性是不同层面的约束。
* Effect modeling 越精确，优化器自由度越高；把真实 effect 错误标成 pure/readonly 会直接造成错误删除或重排。

关键路径
--------

操作分类：

::

   operation
   → pure value computation?
   → ordinary memory read/write?
   → volatile / atomic / fence?
   → call / exception / I/O?
   → assign effect and ordering constraints
   → decide legal rewrite

调用边界：

::

   call site
   → inspect visible callee / attributes / summaries
   → determine memory read/write set
   → determine throw/capture/I-O behavior
   → preserve unknown effects conservatively
   → enable stronger optimization only with proof

可观察顺序：

::

   observable event A
   → candidate computation/memory operation
   → observable event B
   → prove moving/removing candidate preserves values and required order
   → transform or keep

概念辨析
--------

* **Pure computation 与 unused result**：纯计算结果无人使用时通常可删；有副作用的 operation 即使 result 无人使用也可能必须保留。
* **Volatile 与 atomic**：volatile 主要约束访问可观察性；atomic 还承载原子性和线程间内存序。
* **Unknown call 与 impure call**：未知表示编译器缺少证明，因此按可能有副作用处理；它并不声明运行时一定产生所有副作用。
* **Observable behavior 与源码形状**：变量、block 和普通算术可以消失，只要外部可观察结果和事件保持。
* **Effect summary 与 optimization hint**：错误的 effect 属性不是“性能提示错误”，而是可能让优化器基于假事实破坏语义。

本章结论
--------

优化自由度止于可观察行为边界。判断一条指令能否删除、合并或移动时，应先区分纯值计算、普通内存、未知调用、volatile、atomic、I/O 与异常，再按各自 effect contract 证明值与事件顺序保持；越靠近外部世界，优化越需要明确而可信的语义证据。