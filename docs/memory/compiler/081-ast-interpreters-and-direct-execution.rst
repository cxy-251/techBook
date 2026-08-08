第081章：AST Interpreters and Direct Execution
===============================================

核心知识点
----------

* AST interpreter 直接把抽象语法树当作可执行结构，不先生成 bytecode、低层 IR 或机器码。它通过遍历节点、读取环境和维护运行时值来实现语言语义。
* AST 已经丢失大部分源码表面形态。括号、缩进、分隔符等通常已被 parser 消化，解释器看到的是 ``VarDecl``、``Binary``、``Call``、``If``、``Return`` 等结构化节点。
* 表达式节点通常产生值，语句节点通常改变环境、产生副作用或改变控制流。解释器常用 ``eval_expr`` 与 ``execute_stmt`` 两类入口表达这个差异。
* AST 树结构已经编码优先级和结合性。解释 ``a + b * c`` 时无需再次判断优先级，只需递归执行对应子树。
* 每种 AST 节点都对应一条运行时语义规则。``Binary`` 负责求左右操作数并应用运算，``Call`` 负责求 callee/arguments 并建立调用环境，``If`` 负责根据 truthiness 选择路径。
* 解释器的核心动态状态是 environment。AST 中的 ``Name(x)`` 只记录名字，真正值需要沿 lexical environment/scope chain 在运行时查找。
* 环境通常形成父子链：global environment → function environment → block environment。名字解析顺序由语言作用域规则决定。
* 函数值不仅包含函数 AST，还需要保留声明时环境，形成 closure。闭包捕获的本质是函数执行时仍能访问创建位置可见的外层绑定。
* 调用函数时，解释器创建新的 call environment，把实参绑定到形参，再执行函数体。递归调用会产生多个独立环境实例。
* ``return``、``break``、``continue`` 等非普通顺序控制流可以通过宿主语言异常、显式状态对象或标记返回值实现；它们是解释器内部机制，不等于用户语言异常。
* 动态类型语言会在节点执行时检查 operand 类型、callability、truthiness、属性存在性等；静态类型语言则可能在前端提前排除部分失败。
* Runtime error 应带回 AST/source location。节点若保留源码范围，解释器就能把“变量未定义”“操作数类型错误”“调用非函数”等运行时失败映射回源代码。
* Tree-walk interpreter 实现简单、语义映射直观、调试友好，适合教学语言、REPL、配置语言和原型系统；代价是频繁节点分派、对象访问和递归遍历。
* AST interpreter 的性能瓶颈来自执行表示过于接近语法树：每个小操作都要经过节点类型判断、函数调用和动态数据结构访问，CPU 难以看到连续紧凑的执行流。
* Bytecode VM 是常见下一步：把树结构预先线性化成紧凑指令流，让执行循环围绕 program counter、frame 和 operand stack/virtual registers 工作。

关键路径
--------

直接执行：

::

   source text
   → lexer/parser
   → AST
   → dispatch by node kind
   → evaluate child nodes
   → read/write environment
   → produce runtime value / effect / control signal

函数与闭包：

::

   function declaration AST
   → create function value
   → capture declaration environment
   → call expression
   → create call environment
   → bind parameters
   → execute body AST
   → return control signal
   → caller receives value

名字查找：

::

   Name node
   → current environment
   → parent environment chain
   → find binding
   → return runtime value
   → otherwise runtime name error

概念辨析
--------

* **AST interpreter 与 compiler**：前者直接执行 AST 语义；compiler 会继续把 AST/IR 转成另一种可执行表示。
* **AST 与 runtime environment**：AST 保存静态程序结构，environment 保存这一次执行中的名字和值绑定。
* **Lexical scope 与 dynamic call stack**：名字通常按声明时词法结构解析，函数调用栈表示当前执行历史；二者不能混为一谈。
* **Closure 与 function AST**：函数 AST 只描述代码，closure 还包含声明时环境，使外层绑定能跨作用域生命周期存活。
* **Return signal 与 language exception**：二者都可在宿主实现中借助异常机制，但 ``return`` 是正常控制语义，用户可捕获异常是另一层语言机制。

本章结论
--------

AST interpreter 的稳定模型是 ``AST Structure + Runtime Environment → Direct Evaluation``。它不把程序先翻译成另一台机器，而是让每类节点直接成为语言执行规则；真正理解树解释器，应沿 ``Node Dispatch → Child Evaluation → Environment Lookup → Control Signal`` 追踪一次求值如何发生。