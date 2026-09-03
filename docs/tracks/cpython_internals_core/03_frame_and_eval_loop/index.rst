======================================================
第 3 模块：虚拟机栈帧与 CEval 解释器核心
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_pyframeobject_and_stack_layout
   02_ceval_interpreter_loop
   03_specialized_adaptive_interpreter
   04_exception_table_and_unwinding

模块概述
========

本模块聚焦 CPython 字节码虚拟机的核心运行时执行引擎。

深入拆解 `_PyInterpreterFrame` 物理栈帧结构、局部变量与操作数栈内存对齐；追踪 `_PyEval_EvalFrameDefault` 主解释器循环中的 Direct Threaded Code 机制与指令分发状态机；全面剖析 PEP 659 自适应指令特化（Specializing Adaptive Interpreter）机制、Inline Cache 内联缓存布局与 Quickening 状态转换；解析基于 Exception Table 的零开销异常处理与栈解退（Stack Unwinding）物理机制。
