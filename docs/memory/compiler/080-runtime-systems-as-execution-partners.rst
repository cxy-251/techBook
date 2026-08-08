第080章：Runtime Systems as Execution Partners
===============================================

核心知识点
----------

* Runtime system 是语言实现中在程序运行时继续承担语义责任的部分。它可以是启动代码、标准库、allocator、unwinder、GC、VM、module loader、thread runtime 或这些部件的组合。
* 编译器负责生成局部可执行路径和必要元数据；runtime 把这些路径接入对象生命周期、动态类型、异常、内存、线程、模块、I/O 和操作系统资源。
* 即使 C/C++/Rust 等静态语言，也依赖 startup code、ABI、libc、compiler runtime、allocator、unwinder、panic/exception support、TLS 和 OS interfaces。
* “静态语言”表示很多程序事实能在编译期确定，不表示程序运行时不需要环境。源码中的 ``main`` 通常也不是进程真正的第一条指令。
* 动态语言对 runtime 依赖更深。对象模型、属性查找、动态调用、GC、模块加载、解释器/JIT、reflection 和异常往往都在 runtime 中持续维护。
* Runtime call 既可能是优化屏障，也可能提供优化机会。未知调用会迫使编译器保守；带有明确 effect/alias/nothrow 属性的 helper 则可被更精确分析。
* Intrinsic 或 compiler-known helper 可以让优化器理解某些 runtime semantics，例如 allocation、memcpy、type test、deopt、safepoint，而不是把所有 runtime 边界都视作完全未知调用。
* JIT/runtime 可以把真实执行反馈送回编译器：hotness、type profile、branch behavior、inline cache、deoptimization metadata 都能支持 runtime specialization。
* Runtime boundary 的核心问题是契约：生成代码调用 runtime 时提供哪些参数和元数据，runtime 返回后生成代码可以继续假设哪些对象、寄存器、线程或异常状态。
* ABI 是这些契约的底座。调用约定、stack alignment、object layout、exception protocol、symbol naming 和 library version 只要一处不一致，都可能让局部正确的机器代码在系统层失败。
* 操作系统位于 runtime 的下一层。内存映射、线程调度、文件描述符、信号、系统调用、动态加载等最终都要进入 OS contract。
* 调试 runtime 问题应按边界分层：generated code → runtime helper/metadata → library/VM/collector → ABI → OS，找到第一个与约定不一致的位置。
* Runtime 性能也必须端到端评估。一次 helper call、allocation、GC safepoint、exception、FFI crossing 或 module lookup 的成本可能远高于邻近几条机器指令。
* 编译完成不是程序语义工作的终点；只有生成代码与它依赖的 runtime world 真正结合，语言实现才完成执行闭环。

关键路径
--------

完整执行链：

::

   source semantics
   → compiler generates code + metadata
   → linker/loader builds process image
   → startup runtime establishes environment
   → generated code executes
   → runtime/ABI boundary when dynamic service needed
   → runtime may call OS / allocator / VM / GC / unwinder
   → return or transfer control
   → generated code continues

运行时优化协作：

::

   generated generic path
   → runtime observes types / hotness / behavior
   → feed profile or cache state
   → specialize / JIT / inline fast path
   → install guards
   → assumptions fail? deopt / generic fallback

故障定位：

::

   observed failure
   → inspect generated call/metadata
   → verify helper/runtime contract
   → verify ABI and library version
   → inspect runtime state
   → inspect OS boundary if needed
   → identify first broken contract

概念辨析
--------

* **Compiler 与 runtime**：compiler 主要在执行前生成表示；runtime 在执行期间持续维护动态状态，二者共同实现语言。
* **Static language 与 runtime-free**：静态语言仍依赖启动、分配、异常、低级 helper、TLS、线程和系统接口。
* **Runtime call 与 optimization barrier**：未知 effect 会限制优化；已建模的 helper/intrinsic 可以成为优化事实来源。
* **Runtime system 与 operating system**：runtime 实现语言/库语义，OS 提供进程、内存、线程、文件等更底层资源；runtime 常通过系统接口使用 OS。
* **Generated code correctness 与 system correctness**：局部机器代码正确还不够，ABI、runtime metadata 和库协议错误仍会让整个程序失败。

本章结论
--------

Runtime 是语言实现的执行伙伴，不是编译完成后的附属物。稳定理解路径是 ``Generated Code + Metadata → ABI → Runtime State → Library/VM/GC/EH → OS → Back to Code``；只有把机器指令放回这条完整执行链中，才能正确解释真实程序的行为、性能和故障。