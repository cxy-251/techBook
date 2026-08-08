第103章：Validation, Security, and Sandboxing
==============================================

核心知识点
----------

* Wasm 的安全模型不是单一“沙箱开关”，而是由 validation、受限执行模型、linear-memory bounds checks、typed calls 和显式 host capabilities 共同构成。
* Module 在执行前先经过 decoding 与 validation。验证器检查 function/body types、operand stack、locals、imports/exports、index spaces、structured control flow 等静态不变量。
* Validation 可以证明 ``i32.store8`` 的地址和值类型正确，却无法提前知道运行时地址是否越界。静态合法与动态安全必须分阶段理解。
* Operand stack 具有静态类型。验证器沿指令模拟 stack effect，要求每条指令获得正确类型输入，并在 block/function 边界产生声明的结果类型。
* Structured control flow 通过 ``block``、``loop``、``if`` 等嵌套结构限制跳转目标，避免把任意字节偏移当作执行地址。
* 间接调用同样受类型约束。``call_indirect`` 可以动态选择 table entry，但实际函数引用必须满足调用点期望签名。
* Linear memory 提供模块级内存隔离。模块只能通过受控 memory instructions 访问自己的线性地址空间，超出当前 memory 范围的访问会在运行时 trap。
* Wasm bounds checking 保护的是整个 linear memory 边界，不是 C/C++ 对象边界。两个数组都位于合法 linear memory 内时，对 A 的越界仍可能破坏 B，因此 Wasm sandbox 不等于源语言 memory safety。
* Trap 是执行期失败，不等同于 validation error。类型不匹配等问题应在加载前拒绝；动态除零、越界访问、无效间接调用等可能在执行时 trap。
* Host capability 是第三类安全边界。Wasm 核心本身不会自动给模块文件、网络、DOM、数据库或系统调用权限；这些能力必须通过 imports/WASI/embedding API 显式提供。
* “没有 ambient authority”意味着模块能接触什么外部资源，主要由宿主实例化时给它绑定了什么能力决定。
* 恶意但 valid 的 module 仍可能消耗 CPU、memory 或制造大量 host calls，因此宿主还需要 execution budget、memory limits、timeouts、fuel、resource quotas 等策略。
* 沙箱边界保护的是 module 与 host 之间的控制/内存/能力关系，不能自动修复模块内部算法错误、逻辑漏洞或源语言级未定义行为。
* 排查 Wasm 安全问题时应先分类：validation failure、runtime trap、in-module data corruption、host capability violation、resource exhaustion。

关键路径
--------

加载执行安全链：

::

   Wasm bytes
   → decode module
   → validate types/stack/control/indexes
   → resolve authorized imports
   → instantiate isolated state
   → execute
   → dynamic bounds/type/trap checks
   → host policy enforces resource access

Memory access：

::

   runtime integer address
   → memory instruction
   → check address + access width
   → in range? perform access
   → out of range? trap

Host capability：

::

   module requests import
   → host decides implementation/resource
   → bind allowed capability at instantiation
   → module can only call granted interface
   → denied/unprovided capability blocks access

概念辨析
--------

* **Validation error 与 trap**：前者是执行前静态结构不合法，后者是 valid module 在具体运行状态下触发动态失败。
* **Memory isolation 与 object safety**：Wasm 阻止越过 linear memory 边界，但不自动检测同一 linear memory 内的对象级越界。
* **Structured control flow 与 no branches**：Wasm 仍有分支，只是目标受嵌套控制结构和类型规则约束。
* **Sandbox 与 complete security**：sandbox 限制模块权限和执行边界，应用逻辑、资源滥用和宿主接口设计仍需单独防护。
* **Import 与 ambient authority**：import 是显式依赖；模块没有被绑定的宿主能力就不能直接凭空访问外部系统。

本章结论
--------

Wasm 安全链应按 ``Validation → Typed/Structured Execution → Memory Bounds → Explicit Host Capabilities`` 理解。它的优势是把大量非法执行状态在加载期排除，把动态越界收束成 trap，再把系统权限交给宿主显式授权；沙箱安全来自这些边界叠加，而不是来自某一个机制。