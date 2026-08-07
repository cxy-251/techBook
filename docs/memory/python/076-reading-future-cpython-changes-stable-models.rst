第076章：Reading Future CPython Changes with Stable Models
==========================================================

核心知识点
----------

* 阅读未来 CPython 变化时，优先使用跨版本稳定的 runtime 分层，而不是记某个 opcode、C 函数名或源码行号。
* 最重要的稳定层包括：execution model、object model、protocol model、compiler model、memory/concurrency model。
* execution model 关注 code block、名字绑定、作用域、frame、调用与异常传播；这些语义比当前解释器 loop 的实现形态稳定。
* object model 关注 identity、reference sharing、mutation、type 与 attribute storage。allocator、refcount 策略和对象头可以变化，但 Python 层对象关系仍是分析起点。
* protocol model 关注 attribute lookup、descriptor、special method lookup、call protocol、iterator/context/async protocol、exception chaining。specialization 只能在保持这些可见协议语义的前提下成立。
* compiler model 固定“tokenizer/parser → AST → symbol table → code object → execution”链。语法变化、AST 变化、bytecode 变化应放到对应层判断。
* memory/concurrency model 关注 object lifetime、GC、allocator、shared mutable state、GIL/free-threading、subinterpreter 和 C extension ownership。
* 版本 release note 中的 parser、bytecode、adaptive interpreter、JIT、GC、free-threaded、subinterpreter、C API 等变化应先分类，再判断对工程的实际影响。
* opcode、inline cache、JIT trace、源码文件拆分、对象头字段都属于高变实现细节；name binding、object identity、protocol dispatch、exception propagation、resource ownership 是更稳定的判断骨架。
* C API 变化必须再分 public API、Limited API、Stable ABI、Unstable/private/internal API；源码能编译与二进制能跨版本加载是两层不同兼容性。
* 对未来版本做性能判断时，先证明语义路径，再看当前实现是否增加 specialization/JIT/allocator/GC 优化，避免把一次版本测试结果误写成语言规律。

关键路径
--------

遇到一条新的 CPython 版本变化，可按下面的固定顺序阅读：

.. code-block:: text

   release note / PEP / source diff
              ↓
   1. language-visible semantics changed ?
              ↓
   2. execution / object / protocol layer
              ↓
   3. compiler / bytecode representation
              ↓
   4. memory / GC / concurrency model
              ↓
   5. C API / ABI / build boundary
              ↓
   6. tooling / performance / deployment impact

若研究一段普通 Python 代码，例如方法调用：

.. code-block:: text

   name binding
      ↓
   object + type
      ↓
   attribute lookup
      ↓
   descriptor / method binding
      ↓
   callable dispatch
      ↓
   frame execution
      ↓
   result / exception

未来版本可以在每个节点增加 cache、specialization、JIT 或新的内部结构；只要语言语义没有改变，这条主模型仍然成立。

概念辨析
--------

**稳定模型与固定实现**
   稳定模型描述对象和语义关系；固定实现假设某个 opcode、字段或函数永远不变。源码阅读应依赖前者。

**语言变化与性能变化**
   新语法、注解语义等可能改变语言可见行为；adaptive opcode、tail-call interpreter、JIT 通常主要改变执行成本和工具观察。

**对象语义与 allocator/refcount 实现**
   identity、mutation、引用共享是 Python 对象层事实；对象如何分配、何时写 refcount、是否 immortal 属于 CPython 内存实现。

**协议稳定与 specialization**
   specialization 只是协议的快速实现。guard 失效后必须回到通用协议，因此不能用 specialized opcode 反向定义 Python 语义。

**API 与 ABI**
   API 是源码调用面；ABI 是编译后二进制依赖面。版本迁移需要分别验证。

本章结论
--------

未来 CPython 会继续改变 parser、bytecode、执行器、JIT、对象内存、GC、并发和 C API。稳定阅读方法是先锁定“执行、对象、协议、编译、内存/并发”五层模型，再把版本变化贴到具体层上。实现细节可以快速演进，判断骨架仍应围绕名字绑定、对象身份、协议分发、异常传播、资源所有权和 runtime state 展开。
