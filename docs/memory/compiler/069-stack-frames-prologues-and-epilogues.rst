第069章：Stack Frames, Prologues, and Epilogues
===============================================

核心知识点
----------

* Stack frame 是一次函数调用在当前线程栈上的运行时工作区，用于保存返回路径、callee-saved registers、局部内存对象、spill slots、对齐填充和调用相关临时数据。
* 源码局部变量不等于 stack slot。优化后很多局部值完全驻留寄存器，只有需要地址、跨资源约束或被 spill 的值才必须进入内存。
* Frame layout 由 ABI、目标 ISA、register allocation、局部对象大小/对齐、动态 alloca、异常展开、调试和安全机制共同决定。
* Prologue 是函数入口建立执行环境的机器序列，通常负责调整 stack pointer、保存 callee-saved registers、建立 frame pointer、分配 frame space，并配套 unwind metadata。
* Epilogue 是退出路径的逆向恢复：释放 frame、恢复保存寄存器和 frame pointer、把 stack pointer 恢复到 ABI 期望状态，再返回 caller。
* Prologue/epilogue 通常在寄存器分配之后才能最终确定，因为后端此时才知道使用了哪些 callee-saved registers、产生了多少 spill slots 和最终 frame size。
* Frame pointer 提供稳定基准，但会占用一个物理寄存器。优化构建可在满足平台、unwind 和动态栈约束时省略 frame pointer，用 stack pointer/其它基址访问 frame objects。
* Dynamic alloca、可变长度对象、复杂 unwind 或调试需求可能迫使后端保留 frame/base pointer，因为 stack pointer 在函数体内不再保持固定偏移关系。
* Stack alignment 是 ABI 契约。函数入口、调用点和 SIMD/宽对象访问常要求特定对齐，prologue 必须为 frame size 和 outgoing calls 保持这一约束。
* Red zone 是部分 ABI 允许在当前 stack pointer 下方临时使用、无需显式调整 SP 的小区域；它是平台约定，不是通用栈特性。
* Leaf function 没有进一步调用，若无需栈对象、spill 和保存寄存器，可以没有传统 stack frame，甚至完全省略 prologue/epilogue 调整。
* Non-leaf function 要处理返回地址和跨调用状态。不同 ISA 形态不同，例如 x86 ``call`` 通常把返回地址压栈，AArch64 ``BL`` 先写 link register，再由非叶函数按需保存。
* Stack canary、stack probing、shadow stack、pointer authentication、sanitizer 和异常处理都可能扩大入口/出口序列；这些是 ABI/安全/运行时约束在 frame 上的体现。
* 多个 return、tail call、shrink wrapping 会让保存/恢复代码不必集中在唯一入口和唯一出口，判断 frame 时应沿真实 CFG 观察。

关键路径
--------

Frame 构造：

::

   register allocation + local objects
   → collect callee-saved registers / spill slots
   → compute size and alignment
   → assign frame indices to offsets
   → emit prologue
   → access frame during body
   → emit epilogue

函数入口：

::

   caller transfers control
   → preserve required return/callee state
   → establish frame/base pointer if needed
   → adjust stack pointer
   → satisfy alignment / security / unwind rules
   → execute function body

函数退出：

::

   prepare return value
   → destroy local frame area
   → restore callee-saved state
   → restore SP/FP and return address state
   → transfer control to caller

概念辨析
--------

* **Stack frame 与 source locals**：frame 是机器运行时结构，不是源码局部变量列表的直接映射。
* **Frame pointer 与 stack pointer**：SP 表示当前栈顶并可能变化；FP 在需要时提供更稳定的帧基准。
* **Prologue/epilogue 与函数语义**：它们通常不是源语言显式行为，却是满足 ABI 和机器状态恢复的必要代码。
* **Leaf function 与 frameless function**：叶函数更容易无 frame，但是否真正 frameless 还取决于 spill、局部对象、安全机制等。
* **Red zone 与 allocated frame**：red zone 是 ABI 允许的隐式临时区域，不等于通过 ``sub sp`` 正式分配的 frame space。

本章结论
--------

Stack frame 是函数调用在机器上的运行时影子。理解路径应是 ``RA/Local Objects → Frame Layout → Prologue → Body Frame Access → Epilogue → Caller State Restored``；源码只描述函数逻辑，真正可执行的函数还必须把寄存器、返回地址、栈空间、对齐和展开规则组织成一个可恢复的 ABI 状态。