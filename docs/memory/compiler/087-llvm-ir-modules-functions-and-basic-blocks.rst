第087章：LLVM IR, Modules, Functions, and Basic Blocks
======================================================

核心知识点
----------

* LLVM IR 具有明确层级：``Module → Function → BasicBlock → Instruction``。这既是 ``.ll`` 文本结构，也是 LLVM C++ API 中的核心对象关系。
* Module 是顶层容器，保存 functions、global variables、aliases、metadata、source filename、target triple 和 data layout。
* ``target triple`` 描述目标架构/系统环境；``target datalayout`` 描述 pointer width、alignment、integer/native width 等布局规则。优化和 codegen 会依赖这些事实解释内存和类型大小。
* 以 ``@`` 开头的标识符属于 module-level global namespace，例如 global variable、function、alias；以 ``%`` 开头的标识符通常表示 function-local SSA values 或 block labels。
* Function definition 使用 ``define`` 并包含函数体；function declaration 使用 ``declare``，只给出签名和属性，表示实现由其它 module/library/runtime 提供。
* Basic block 是函数内部的单入口线性指令序列。普通指令顺序执行，最后必须以 terminator 结束。
* 常见 terminator 包括 ``br``、``ret``、``switch``、``invoke``、``unreachable``。CFG edge 由 terminator 明确定义，而不是由文本排列隐式决定。
* Entry block 是函数执行入口，没有 predecessor；这一点会影响 ``phi``、alloca 约定和 dominance 判断。
* Instruction 既是一个操作，也可能定义一个 typed SSA value。``add``、``load``、``icmp``、``phi`` 产生结果；``br``、``ret`` 主要产生控制流效果。
* LLVM IR 是 SSA-based representation。一个普通 SSA value 只有一个定义点，所有使用点直接引用该定义。
* Type 是 use-def 合法性的基础。算术、比较、branch、return、load/store 都要求 operand/result 类型满足对应 instruction 规则。
* Use-def chain 让 optimizer 能快速定位“谁使用这个值”，也让 verifier 检查 definition 是否支配 uses、类型是否一致、替换是否完整。
* ``phi`` 把 SSA 与 CFG 连接起来：每个 incoming pair 同时包含 value 和 predecessor block，表示控制流从哪条边进入时选择哪个值。
* ``phi`` 的语义发生在 block 入口/控制流边上，不能按普通顺序赋值理解；多个 ``phi`` 具有并行选择语义。
* Metadata 提供 debug、profile、TBAA、loop hints 等附加事实。Metadata 很重要，但不能替代从 CFG、types 和 SSA 本体读取核心执行语义。
* LLVM IR 有 textual IR、bitcode、in-memory object graph 三种常用形态；表示形式不同，语义应保持一致。
* 读 IR 的稳定顺序是：module target facts → function signature/attributes → blocks/terminators/CFG → instructions/types → SSA use-def → metadata。

关键路径
--------

结构层级：

::

   Module
   → target triple / data layout / globals / metadata
   → Function
   → Basic Blocks
   → Instructions
   → typed SSA values and effects

控制流：

::

   function entry block
   → sequential instructions
   → terminator
   → successor basic block
   → ...
   → ret / unreachable / exceptional exit

SSA 数据流：

::

   function argument or instruction result
   → one definition
   → use-def edges
   → branch merge
   → phi selects value by predecessor edge
   → later instruction / return

概念辨析
--------

* **Module 与 source file**：module 常对应一个编译单元，但它是 LLVM IR 容器，不等同于原始源码文件结构。
* **Function declaration 与 definition**：declaration 只有接口契约，definition 还包含 executable IR body。
* **Basic block 与 source block**：basic block 是 CFG 中的直线执行区域，和源码花括号块没有一一对应关系。
* **Instruction 与 SSA value**：部分 instruction 同时定义 value；terminator/store 等也可以只有 effect 而无普通结果值。
* **PHI 与普通 assignment**：phi 根据 predecessor edge 选择 incoming value，不是按文本顺序执行一次赋值。

本章结论
--------

阅读 LLVM IR 的核心不是逐行翻译文本，而是同时恢复两张图：``CFG`` 与 ``SSA use-def graph``。稳定模型是 ``Module Context → Function → Basic Blocks/Terminators → Typed Instructions → SSA Values``；只要先固定控制流，再沿 value definitions 和 uses 追踪数据，就能把大多数 LLVM IR 结构还原成可验证的程序语义。