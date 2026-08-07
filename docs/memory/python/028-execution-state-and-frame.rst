第028章：Execution State and Frame
==================================

核心知识点
----------

* frame 是 Python 某一次代码执行的现场，保存当前 code object、局部变量、globals、builtins、当前指令位置、调用关系以及调试和异常相关状态。
* function object 表达可调用对象，code object 表达编译后的静态执行计划，frame 表达这份计划的一次具体运行；同一 function/code object 可以对应多次不同 frame。
* Python 调用栈可以通过 frame 的 ``f_back`` 关系观察。当前 frame 指向调用者 frame，traceback 与 ``inspect`` 都依赖这条执行链。
* CPython 3.11 以后公开 ``PyFrameObject`` 已是 opaque C API；解释器内部使用更轻量的 internal frame 表示。Python 层可观察语义稳定，内部字段布局属于版本敏感实现。
* frame 内部可按三类状态理解：fast locals 保存编译期确定的局部变量槽；value stack 保存表达式中间对象；异常表和 unwind 状态保存控制流清理边界。
* fast locals 通过索引访问局部变量，速度和普通 dict lookup 不同；``f_locals`` 是对执行局部状态的可观察映射视图。
* Python 3.13+ 中优化作用域的 ``frame.f_locals`` 使用 write-through proxy；``locals()`` 在优化作用域中更接近当前局部状态快照。版本判断必须纳入分析。
* traceback 节点保存 ``tb_frame``、``tb_lasti``、``tb_lineno``、``tb_next``，因此异常对象可以间接持有整条 frame 链和 frame 内的局部对象。
* frame introspection 会改变对象生命周期。长期保存 frame、traceback 或异常对象可能把大对象、文件句柄等局部引用一起延长存活。
* generator/coroutine 会让 frame 脱离普通“调用即执行到结束”的生命周期：frame 可以在 ``yield``/``await`` 附近挂起，保存局部变量和恢复位置，等待后续继续执行。
* frame lifecycle 需要按 created / running / suspended / returned-or-failed / released 来理解，而不是只看函数对象是否还存在。

关键路径
--------

普通调用中的 frame 关系：

::

   caller frame
       ↓ call
   callee code object
       ↓
   create execution frame
       ↓
   initialize parameters / fast locals
       ↓
   evaluation loop mutates value stack + locals
       ↓
   return value or raise exception
       ↓
   callee leaves active frame chain
       ↓
   caller resumes

异常路径：

::

   exception raised
       ↓
   traceback node captures current frame
       ↓
   unwind to caller
       ↓
   append / connect next traceback frame
       ↓
   handler or top-level reporter reads frame chain

generator 挂起路径：

::

   generator object created
       ↓
   first resume enters frame
       ↓
   execute until yield
       ↓
   save instruction position + fast locals + required stack state
       ↓
   frame becomes suspended
       ↓
   next/send resumes same execution state

概念辨析
--------

* **function、code object、frame**：function 保存可调用对象及 defaults/closure 等状态；code object 保存静态指令；frame 保存一次运行现场。
* **Python frame stack 与 C stack**：前者描述 Python 调用关系；后者描述 CPython 解释器自身的 C 函数调用。
* **fast locals 与 ``f_locals``**：fast locals 是执行器高效局部槽；``f_locals`` 是 Python 层可观察接口，两者不是简单同一个 dict。
* **value stack 与 locals**：value stack 保存表达式短期中间对象；locals 保存已经绑定到局部名字的对象引用。
* **traceback 与 frame**：traceback 不是 frame 本身；它在异常路径上保存对 frame 的引用以及失败位置。
* **frame 存活与 frame 正在执行**：suspended generator 的 frame 仍存活，却不在当前普通调用栈顶执行。

本章结论
--------

frame 是 CPython execution state 的核心边界。Code object 说明“执行什么”，frame 说明“这一次执行现在在哪里、有哪些局部状态、从谁调用而来、出错后怎样回溯、是否可以暂停”。阅读运行时问题时，应先定位具体 frame，再区分 fast locals、value stack、instruction position、traceback 和 suspension 状态；这样普通调用、异常、调试、generator 与 coroutine 都可以放进同一套执行状态模型。