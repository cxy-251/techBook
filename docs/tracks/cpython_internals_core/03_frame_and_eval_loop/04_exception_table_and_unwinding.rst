=============================================================================
零开销异常处理表 Exception Table 与栈回溯 Unwinding 物理机制
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解构了 PEP 659 自适应指令特化体系（Specializing Adaptive Interpreter）的四态转换状态机、16 位指数退避计数器以及内联缓存（Inline Cache）如何使正常执行路径逼近原生 C 速度。然而，程序的控制流不仅包含顺序执行与条件跳转，还包含异常（Exception）引发的非正常跳跃。
   
   在早期 Python 中，进入 ``try`` 块必须在运行时栈上压入块上下文，使得即使从未抛出异常，``try`` 语句也会产生固定开销。自 Python 3.11+ 起，CPython 彻底推翻了旧模型，构建了基于静态表驱动的**零开销异常处理机制（Zero-Cost Exception Handling）**。本章将深入 CPython 核心源码文件 ``Python/ceval.c``、``Python/ceval.h``、``Python/assemble.c``、``Python/traceback.c`` 以及 ``Python/errors.c``，深度推导静态字节码区间与 ``co_exceptiontable`` 的变长 Varint 编码格式、异常发生时的二分/线性混合查找算法、值栈脏数据原子回滚与帧间 Unwinding 机制、PEP 654 异常组（``except*``）的树形拆解物理算法，以及 ``_PyErr_StackItem`` 在协程 Yield 切换中的异常上下文隔离屏障。

-----------------------------------------------------------------------------
1. 从 Block Stack 到 Zero-Cost：异常处理的范式跃迁
-----------------------------------------------------------------------------

旧版 CPython（$\le$ 3.10）的块栈痛点
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Python 3.10 及以前，每个栈帧 ``PyFrameObject`` 内部维护了一个定长的 ``f_blockstack[CO_MAXBLOCKS]`` 数组。
- **进入 ``try`` 块**：必须发射并执行 ``SETUP_FINALLY`` 指令，在运行时向 ``f_blockstack`` 压入一个 ``PyTryBlock`` 结构体（记录处理函数偏移、栈层级等）；
- **离开 ``try`` 块**：必须执行 ``POP_BLOCK`` 指令将该块弹出。

这意味着：**哪怕代码在 99.99% 的情况下从未抛出任何异常，正常业务路径（Happy Path）每次进出 ``try`` 块都必须承受指令分发、内存写栈与弹栈的性能惩罚**。

现代 Python 3.11+ 的零开销异常处理（Zero-Cost Exceptions）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 CPython 彻底废弃了 ``SETUP_FINALLY`` 与 ``POP_BLOCK`` 指令：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 旧版 Block Stack vs 现代 Zero-Cost 机制对比             |
   +====================+==========================+=========================+
   | 核心特性           | 传统 Block Stack 机制    | 现代 Zero-Cost 静态表   |
   +--------------------+--------------------------+-------------------------+
   | Happy Path 运行开销| 执行 SETUP_FINALLY 指令  | **0 字节码指令, 0 耗时**|
   |                    | 产生栈写入与弹栈开销     | (完全等同于普通直线代码)|
   +--------------------+--------------------------+-------------------------+
   | 元数据存储位置     | 运行时栈帧动态数组       | 静态不可变 CodeObject   |
   |                    | (f_blockstack)           | (co_exceptiontable)     |
   +--------------------+--------------------------+-------------------------+
   | 异常捕获定位算法   | 直接弹出栈顶 Block       | 基于指令偏移在表中查找  |
   |                    |                          | (二分查找 + Varint 扫描)|
   +--------------------+--------------------------+-------------------------+

在现代架构下，编译器在离线阶段直接计算出每个 ``try`` 块覆盖的字节码区间，并紧凑编码为静态二进制表 ``co_exceptiontable``。在正常执行时，没有任何额外的指令被执行；只有当真正抛出异常时，解释器才去查表寻址。

-----------------------------------------------------------------------------
2. co_exceptiontable 变长 Varint 编码格式
-----------------------------------------------------------------------------

为了将异常表的内存体积压缩至极致，CPython 在 ``Python/assemble.c`` 中设计了一种高密度的变长整数（Varint）字节流编码：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               co_exceptiontable 单个 Entry 的逻辑四元组                 |
   +=========================================================================+
   | (start_offset,  size,  target_handler,  depth_and_lasti)                |
   +-------------------------------------------------------------------------+

Varint 字节流微观编码规范
~~~~~~~~~~~~~~~~~~~~~~~~~

每个整数采用 7-bit 分段编码，最高位（Bit 7）作为边界标志位：
- **Entry 首字节**：Bit 7 强制置 1，标志着一个全新 Entry 的物理起始点；
- **后续字节**：Bit 7 置 0，低 7 位（Bits 0~6）存储整数有效载荷；

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Entry 字段物理含义与位运算拓扑                         |
   +====================+====================================================+
   | start_offset       | 受保护区间的起始 Code Unit 偏移 (Varint)           |
   +--------------------+----------------------------------------------------+
   | size               | 受保护区间的长度 (Code Units, Varint)              |
   +--------------------+----------------------------------------------------+
   | target_handler     | 捕获异常后的跳转目标 Handler 偏移 (Varint)         |
   +--------------------+----------------------------------------------------+
   | depth_and_lasti    | 复合字段: (stack_depth << 1) | preserve_lasti      |
   |                    | ├── stack_depth: 异常发生时必须精准恢复的值栈深度  |
   |                    | └── preserve_lasti: 是否在栈顶保留异常发生时的 PC  |
   +--------------------+----------------------------------------------------+

通过这种编码，一个典型的 ``try-except`` 块元数据仅需占用 **3 到 6 个字节**，且整个异常表被封装为一个不可变的 ``PyBytesObject`` 挂载于 ``PyCodeObject.co_exceptiontable``。

-----------------------------------------------------------------------------
3. 异常分发与栈指针回滚：get_exception_handler()
-----------------------------------------------------------------------------

当 CEval 主循环中的某条指令执行失败并返回错误指示时，解释器立即跳转至异常处理核心函数 ``get_exception_handler()``（位于 ``Python/ceval.h``）：

.. code-block:: c

   static Py_NO_INLINE int
   get_exception_handler(PyCodeObject *code, int index, int *level, int *handler, int *lasti)
   {
       unsigned char *start = (unsigned char *)PyBytes_AS_STRING(code->co_exceptiontable);
       unsigned char *end = start + PyBytes_GET_SIZE(code->co_exceptiontable);

       /* 1. 表项较多 (>40 字节) 时：启动二分跳跃查找加速定位 */
       if (end - start > MAX_LINEAR_SEARCH) {
           ...
           do {
               unsigned char *mid = start + ((end - start) >> 1);
               mid = scan_back_to_entry_start(mid); // 沿 Bit 7=1 逆向对齐到 Entry 首字节
               parse_varint(mid, &offset);
               if (offset > index) end = mid;
               else start = mid;
           } while (end - start > MAX_LINEAR_SEARCH);
       }

       /* 2. 线性快速扫描，匹配目标区间 [start_offset, start_offset + size) */
       unsigned char *scan = start;
       while (scan < end) {
           int start_offset, size;
           scan = parse_varint(scan, &start_offset);
           if (start_offset > index) break;
           scan = parse_varint(scan, &size);
           if (start_offset + size > index) {
               scan = parse_varint(scan, handler);
               int depth_and_lasti;
               parse_varint(scan, &depth_and_lasti);
               *level = depth_and_lasti >> 1;
               *lasti = depth_and_lasti & 1;
               return 1; // 成功命中本地 Handler！
           }
           scan = skip_to_next_entry(scan, end);
       }
       return 0; // 当前栈帧未捕获
   }

值栈原子回滚（Stack Level Reset）的物理实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在抛出异常的瞬间，求值栈上可能残留了大量未计算完成的中间操作数（例如正在计算 ``a + b * func(c)`` 时 ``func()`` 抛出异常，栈上残留了 ``a`` 和 ``b``）。

一旦 ``get_exception_handler()`` 命中：
1. **瞬间清空脏栈**：解释器直接执行物理指针重设：

   $$	ext{stack\_pointer} = 	ext{\_PyFrame\_Stackbase}(	ext{frame}) + 	ext{level}$$

   将栈顶指针秒级回拨至进入 ``try`` 块时的基准线，所有中间脏数据全部被瞬间丢弃；
2. **压入异常对象**：将捕获到的全局异常引用压入栈顶（``*stack_pointer++ = exc``）；
3. **指令指针跃迁**：将 ``next_instr`` 指向 ``handler`` 偏移，解释器无缝进入 ``except`` 字节码分支执行。

-----------------------------------------------------------------------------
4. 帧间回溯（Frame Unwinding）与 Traceback 惰性构造
-----------------------------------------------------------------------------

若当前栈帧未找到匹配的异常处理器（``get_exception_handler()`` 返回 0），虚拟机启动**跨帧栈回溯（Frame Unwinding）**：

.. code-block:: text

   [当前帧 Frame N 发生未捕获异常]
                 │
                 ▼
   1. 调用 _PyTraceBack_FromFrame(tb, frame)
      └─ 惰性构造当前行号的 Traceback 节点，链接入 Exception.__traceback__
                 │
                 ▼
   2. 弹出并销毁当前物理栈帧
      └─ _PyEval_FrameClearAndPop(tstate, frame)
      └─ 数据栈游标回退 (tstate->datastack_top 回拨)
                 │
                 ▼
   3. 恢复上一层调用方栈帧
      └─ frame = tstate->current_frame = frame->previous
                 │
                 ▼
   4. 递归检查上一层栈帧的 co_exceptiontable
      ├─ 命中 Handler ──► 回滚调用方值栈，压入异常，恢复执行！
      └─ 未命中 ────────► 重复 Unwinding 向上逃逸直至顶层模块

惰性 Traceback 构造的设计精髓
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代 CPython 中，只要异常未被检查（如快速捕获并处理），Traceback 链表节点绝不提前在堆上分配。只有当回溯引擎向上跨越栈帧时，才按需调用 ``_PyTraceBack_FromFrame()`` 提取源码行号并生成回溯节点。这使得“用于控制流的短途异常”（如 ``StopIteration`` 或自定义流控异常）的开销被压制在极低水平。

-----------------------------------------------------------------------------
5. PEP 654 异常组与 except* 树形模式解构
-----------------------------------------------------------------------------

Python 3.11 引入的 PEP 654 允许在一个复合容器 **``BaseExceptionGroup``** 中同时包裹多个并发异常（如 ``asyncio.TaskGroup`` 并发失败）。

与传统的单异常捕获不同，``except*`` 语法采用了**树形过滤拆解算法**（实现在 ``Python/ceval.c`` 的 ``_PyEval_ExceptionGroupMatch()``）：

.. code-block:: text

   [原始复合异常组 ExceptionGroup: (ValueError, TypeError, KeyError)]
                                  │
                                  ▼
      遇到 except* (ValueError, TypeError) as eg:
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
   【匹配子树 Match Subtree】                    【未匹配子树 Rest Subtree】
   ExceptionGroup: (ValueError, TypeError)       ExceptionGroup: (KeyError)
   └─ 绑定给局部变量 eg，进入当前代码块执行        └─ 暂存入当前帧的挂起队列
                                                           │
                                                           ▼
                                  在所有 except* 块执行完毕后，
                                  若 Rest 不为空，自动重新向外层抛出！

``_PyEval_ExceptionGroupMatch()`` 在 C 语言层递归调用 ``ExceptionGroup.split()`` 方法，将匹配的部分与未匹配的部分物理切分为两个独立的异常组对象，并保证每个分支只消费其关心的异常子集，彻底奠定了 Python 现代异步并发结构化异常处理的底层运行基石。

-----------------------------------------------------------------------------
6. _PyErr_StackItem 协程与生成器异常上下文隔离
-----------------------------------------------------------------------------

在异步协程（``async/await``）与生成器频繁交替调度的场景下，如果不同协程共享全局的异常状态（``sys.exc_info()``），会导致一个协程内部正在处理的异常被另一个并发协程的异常意外覆盖。

CPython 在 ``_PyErr_StackItem`` 中实现了栈式异常上下文隔离：

.. code-block:: c

   typedef struct _err_stackitem {
       PyObject *exc_value;              /* 当前上下文正在处理的异常实体 */
       struct _err_stackitem *previous_item; /* 前一个异常上下文链表节点 */
   } _PyErr_StackItem;

- 每个生成器与协程对象（``_PyGenObject``）内部直接内嵌了一个 ``_PyErr_StackItem gi_exc_state``；
- 当生成器激活时，线程状态 ``tstate->exc_info`` 指针瞬间切换指向该生成器的私有异常栈；
- 当生成器执行 ``yield`` 挂起时，``tstate->exc_info`` 恢复指向外部调用方的上下文。

这种指针切换实现了完全零堆内存分配的**协程级异常上下文物理隔离**。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 零开销异常处理与栈回溯引擎的物理实现：
1. 从旧版 ``f_blockstack`` 动态操作向基于 ``co_exceptiontable`` 的 Zero-Cost 静态表驱动的架构飞跃；
2. 异常表四元组（``start``, ``size``, ``target``, ``depth_and_lasti``）的高密度变长 Varint 二进制编码格式；
3. ``get_exception_handler()`` 通过二分与线性混合扫描快速定位目标 Handler，并瞬间原子回退值栈指针（``stack_pointer``）；
4. 帧间回溯（Unwinding）与 Traceback 惰性链表构建流水线；
5. PEP 654 异常组（``except*``）的树形拆解匹配算法，以及基于 ``_PyErr_StackItem`` 的协程异常上下文隔离体系。

至此，全书**第 3 模块【虚拟机栈帧与 CEval 解释器核心】全部 4 个深度章节已全部圆满落盘**！

在下一章中，我们将正式开启**第 4 模块【核心内建数据结构实现】**，深入解构 Python 中使用频率最高、经过极致内存与哈希优化的核心容器—— **04_builtins_and_data_structures/01_compact_dict_and_split_table.rst（字典紧凑哈希表 Compact Dict、DKIX 表与 Split Table 内存优化）**。
