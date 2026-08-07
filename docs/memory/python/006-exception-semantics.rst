第006章：异常语义
================

核心知识点
----------

异常是运行时对象
   ``raise`` 传播的是 ``BaseException`` 的实例。异常类型表达处理类别，参数保存错误信息，``__traceback__`` 连接失败经过的 frame 与源码位置。

传播过程沿调用栈查找 handler
   操作失败后，解释器先检查当前 frame 覆盖该位置的异常处理区域；没有匹配 handler 时退出当前 frame，执行必要清理，再把同一异常交给调用方继续匹配。

traceback 既是证据也是引用链
   traceback 记录从抛出点到外层处理点的 frame 路径。长期保存异常或 traceback 可能同时保留 frame、locals 和相关对象，延长对象生命周期。

异常链保留错误转换关系
   ``raise new_error from old_error`` 把底层异常写入 ``__cause__``，用于明确表达直接原因；处理旧异常时自然产生的新异常会通过 ``__context__`` 保留隐式上下文。

异常层级定义捕获边界
   ``Exception`` 覆盖普通应用错误；``SystemExit``、``KeyboardInterrupt`` 和 ``GeneratorExit`` 直接位于 ``BaseException`` 下。普通业务代码捕获 ``Exception`` 时通常应让退出和中断信号继续传播。

``finally`` 绑定到控制流出口
   正常完成、``return``、``break``、``continue`` 和异常传播都会先执行覆盖该区域的 ``finally``。``finally`` 中的新 ``return`` 或异常可能覆盖原本待完成的控制流。

栈展开逐层执行清理
   stack unwinding 不只是丢弃 frame，而是按调用栈逐层执行 ``finally``、context manager 退出逻辑和其它收束动作，再继续传播异常。

CPython 3.11+ 使用 exception table
   异常处理范围主要记录在 code object 的 exception table 中，正常路径不必持续维护旧式 block 状态。“zero-cost”只描述未抛异常时的额外成本较低，异常创建、traceback 和 handler 仍有明显成本。

异常组表达多个并列失败
   ``ExceptionGroup`` 用树形对象组合多个异常，``except*`` 按叶子异常类型拆分出匹配子组；未匹配部分会重新组合并继续传播，每个叶子仍保留自己的 traceback 和异常链。

关键路径
--------

普通异常传播：

::

   操作失败或执行 raise
   → 建立异常对象与 traceback
   → 查找当前 frame 的匹配 handler
   → 未命中时执行当前 frame 的 cleanup
   → 退出 frame 并交给调用方继续匹配
   → handler 处理、转换、重新抛出或传播到调用栈外

错误转换路径：

::

   捕获底层异常
   → 创建上层稳定异常类型
   → 使用 raise new from old 建立 cause
   → 执行 finally 或 context cleanup
   → 调用方按上层类型处理
   → 日志与调试工具沿 cause 回到原始失败点

概念辨析
--------

* **异常对象与 traceback**：异常对象描述失败类别和参数；traceback 描述失败经过的执行位置，两者通过引用关系连接。
* **``__cause__`` 与 ``__context__``**：cause 是显式声明的直接原因；context 是处理旧异常期间自然产生的新异常背景。
* **``Exception`` 与 ``BaseException``**：前者面向普通可处理错误；后者还包含退出、中断和生成器收束等控制流信号。
* **``except`` 与 ``finally``**：``except`` 根据类型选择处理路径；``finally`` 无条件参与离开当前区域的收束。
* **正常路径成本与异常路径成本**：exception table 降低无异常时的额外开销，不会消除异常对象、traceback、栈展开和 handler 的成本。
* **普通异常与 ``ExceptionGroup``**：普通异常表示单条失败传播链；异常组同时保存多个并列或嵌套失败，并允许按叶子类型拆分处理。

本章结论
--------

排查异常时，应先找到主异常和最内层 traceback，再沿 ``__cause__`` 或 ``__context__`` 还原错误转换，随后检查每层 frame 的 handler、``finally`` 与 context cleanup；涉及批处理或并发失败时，还要把 ``ExceptionGroup`` 的整体传播位置与各叶子异常的独立证据分开阅读。
