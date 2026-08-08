第083章：Virtual Machines and Evaluation Loops
===============================================

核心知识点
----------

* Bytecode VM 是执行 bytecode 的运行时机器。它把每条虚拟指令解释成对 program counter、frame、locals、operand stack/registers、heap objects 和 exception state 的状态转换。
* Bytecode 本身只是执行蓝图；真正运行需要 VM state。最小状态通常包括当前 frame、frame stack、globals/module state、heap/object store 和异常上下文。
* Eval loop 的基本动作是 ``fetch → decode → dispatch → execute → update state``。循环不断读取 ``pc`` 指向的 opcode，进入 handler，再推进 ``pc`` 或改变控制流。
* ``switch`` dispatch 实现简单、可移植、容易插桩；代价是每条 bytecode 都回到公共分派点，dispatch 开销可能接近轻量 opcode 本身。
* Threaded/direct dispatch 通过让 handler 更直接地跳到下一 handler 减少公共分支成本，但通常增加实现复杂度、平台依赖和调试难度。
* 解释器 dispatch 优化仍属于解释执行；只有当 VM 把 bytecode/IR 生成本机机器码并直接执行时，才进入 JIT 路线。
* Frame 是一次函数调用的运行时容器。它保存当前 code object、``pc``、local slots、operand stack、返回位置、异常处理状态以及必要的运行时元数据。
* 同一函数递归调用会产生多个 frame；它们共享 code object，却拥有各自独立的 locals、operand stack 和 ``pc``。
* Stack VM 中，opcode 通过 stack effect 交换中间值；``ADD`` 一类操作弹出输入并压入结果。VM 必须维持栈高度、值类型和控制流汇合处状态一致性。
* Function call 会跨 frame 传递参数和返回值：调用者准备 arguments → VM 创建 callee frame → 参数进入 callee locals → ``RETURN`` 销毁 callee frame → result 回到 caller。
* Runtime objects 承载语言级值。动态语言的加法、属性访问、方法调用、truthiness 等 bytecode handler 往往还要调用对象协议或 runtime helper，不能直接等同于 CPU 指令。
* 异常是另一种 frame-stack 转移。当前 frame 无 handler 时，VM 弹出 frame 并向调用者传播，直到找到 handler 或终止顶层执行。
* VM 的“栈”通常至少有两层：frame/call stack 保存调用关系，operand stack 保存当前 frame 内的临时值；二者职责不同。
* Bytecode offset/``pc`` 是解释器级执行位置。调试器、traceback、profiler 和异常表常通过它重新连接源码位置或 code metadata。
* VM 性能由多层共同决定：dispatch cost、opcode granularity、object representation、allocation、dynamic checks、cache locality 和 runtime helper cost，而不仅是 eval loop 写法。

关键路径
--------

主执行循环：

::

   current frame + pc
   → fetch bytecode instruction
   → decode opcode/operand
   → dispatch to handler
   → mutate stack/locals/objects/pc
   → exception or call/return?
   → choose next frame/pc
   → repeat

函数调用：

::

   caller evaluates arguments
   → CALL opcode
   → create callee frame
   → bind arguments to local slots
   → execute callee bytecode
   → RETURN_VALUE
   → pop callee frame
   → restore caller pc
   → place return value in caller state

异常传播：

::

   opcode/runtime operation fails
   → create/set exception state
   → inspect current frame handler table
   → handler exists? jump to handler
   → otherwise pop frame
   → propagate to caller
   → repeat until handled or uncaught

概念辨析
--------

* **VM 与 bytecode**：bytecode 是程序表示，VM 是读取并执行这种表示的运行时系统。
* **Frame stack 与 operand stack**：前者表示函数调用链，后者保存当前 frame 的中间计算值。
* **Dispatch optimization 与 JIT**：threaded/direct dispatch 优化解释器分派；JIT 则把程序本身生成机器码。
* **Bytecode pc 与 machine PC**：前者指向虚拟指令位置；JIT/本机执行时还存在真实 CPU instruction address。
* **Opcode semantics 与 CPU instruction semantics**：``ADD`` 可能触发动态类型、对象协议甚至异常，不保证对应一条硬件加法指令。

本章结论
--------

VM 的核心模型是 ``Bytecode + Frame State + Eval Loop → Runtime Behavior``。稳定追踪一次执行应从 ``current frame → pc → opcode stack effect → call/return/exception transition`` 入手；bytecode 只是描述动作，真正把程序推进的是 VM 对调用栈、临时值和运行时对象的持续维护。