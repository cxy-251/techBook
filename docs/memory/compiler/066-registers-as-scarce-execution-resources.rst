第066章：Registers as Scarce Execution Resources
=================================================

核心知识点
----------

* 后端在寄存器分配前可以用大量 virtual registers 表达机器级值流；真实 CPU 只有有限 physical registers，因此最终必须把无限名字压缩到有限硬件槽位。
* Virtual register 表达值身份和 def-use；physical register 是机器指令真正编码使用的资源。二者之间没有固定一一关系。
* Register class 定义某类虚拟值可映射到哪些物理寄存器，例如整数、浮点、向量、地址和特殊状态通常属于不同资源池。
* 寄存器类别是合法性约束，不是性能提示。整数值不能因为 GPR 紧张就随意塞进不被目标指令接受的 FPR。
* 物理寄存器还存在 alias/overlap 关系，例如宽窄子寄存器可能共享同一硬件存储，分配器必须按真实重叠关系避免覆盖仍活跃的值。
* 某些目标指令、参数传递、返回值、除法或特殊操作会要求 fixed/precolored registers；普通分配必须围绕这些固定点安排 copy 或腾挪其它值。
* Register pressure 表示某个程序点同时需要寄存器承载的 live values 数量。压力接近或超过可分配寄存器数时，spill 概率迅速上升。
* “目标有多少寄存器”不等于“当前有多少可分配寄存器”。stack pointer、frame pointer、平台保留寄存器、ABI 固定寄存器和特殊状态都会缩小候选集合。
* Caller-saved registers 允许 callee 覆盖，因此跨调用仍 live 的值若放在其中，caller 必须在调用前保存或在调用后恢复/重建。
* Callee-saved registers 由 callee 使用后负责恢复，适合承载跨调用长生命周期值，但会增加 prologue/epilogue 保存恢复成本。
* Reserved registers 通常不进入普通分配集合，例如 stack pointer、平台寄存器、某些线程/全局指针或架构特殊状态。
* 寄存器分配的质量不是“尽量不用栈”这么简单，还要权衡 copy 数量、call crossing、live range 长度、寄存器类别、spill cost 和目标指令约束。
* 优化越激进，可能同时制造更多 live temporaries。Unrolling、vectorization、inlining 能提升并行度，也可能显著增加 register pressure。

关键路径
--------

资源映射：

::

   Machine IR values
   → virtual registers
   → register classes
   → liveness / pressure
   → physical-register candidates
   → assign register or spill
   → register-allocated machine code

跨调用值：

::

   value live before CALL
   → still needed after CALL?
   → caller-saved candidate: save / spill / rematerialize
   → callee-saved candidate: preserve via function frame
   → restore value after call

固定寄存器约束：

::

   target instruction / ABI requirement
   → require specific physical register
   → insert or coalesce COPY
   → keep interfering live values elsewhere
   → satisfy encoding constraint

概念辨析
--------

* **Virtual register 与 physical register**：前者是后端值身份，后者是有限硬件存储槽位。
* **Register class 与 register count**：类别先限制候选集合；总寄存器很多也不代表某类值有足够可用寄存器。
* **Register pressure 与 instruction count**：压力由同时 live 的值决定，不由静态指令数直接决定。
* **Caller-saved 与 callee-saved**：区别是调用边界保存责任，不是某类寄存器“更安全”或“更快”。
* **Reserved register 与 occupied register**：reserved 从普通分配集合中排除；occupied 只是某个时刻被已分配值使用。

本章结论
--------

寄存器是后端最稀缺的高速临时存储。理解分配问题应沿 ``Virtual Value → Register Class → Liveness/Pressure → ABI/Fixed Constraints → Physical Register or Spill`` 追踪；代码质量的核心，是让最重要的 live values 在最合适的硬件槽位中存活，同时尽量减少保存、拷贝和内存流量。