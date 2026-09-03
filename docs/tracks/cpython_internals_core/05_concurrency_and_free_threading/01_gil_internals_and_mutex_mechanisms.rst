=============================================================================
传统 GIL 全局解释器锁底层机制、竞争与切换时机
=============================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块【核心内建数据结构实现】中，我们自底向上深入解构了 CPython 3.13+ 的字典（Compact Dict / Split Table）、字符串（PEP 393 FSR）、元组与列表（Over-allocation 扩容）以及集合（开放寻址与扰动探查）的底层物理拓扑。在单线程视角下，这些数据结构通过紧凑的内存对齐和位操作达成了极高的执行吞吐。
   
   然而，当多个操作系统原生线程并发访问解释器内部状态时，如何保证对象引用计数（``ob_refcnt``）、内存分配池（``pymalloc`` / ``mimalloc``）以及全局状态的安全一致性，构成了 CPython 三十余年架构演进中最著名的核心议题——**全局解释器锁（Global Interpreter Lock, GIL）**。本章作为**第 5 模块【并发、GIL 与 3.13+ Free-Threading】的开篇之作**，将深入 CPython 核心源码文件 ``Python/ceval_gil.c``、``Include/internal/pycore_gil.h`` 以及 ``Include/internal/pycore_ceval.h``，深度剖析经典 GIL 的设计哲学、旧版 Tick 机制向新版时间片条件变量机制的历史演进、``_gil_runtime_state`` 结构体内存拓扑、``take_gil()`` / ``drop_gil()`` 核心状态机与 ``FORCE_SWITCHING`` 防抖竞争控制算法，以及子解释器独立 GIL（PEP 684）与 Free-Threading 下的瞬态 GIL 回退体系。

-----------------------------------------------------------------------------
1. GIL 诞生历史与核心存在价值
-----------------------------------------------------------------------------

为什么 CPython 需要 GIL？
~~~~~~~~~~~~~~~~~~~~~~~~~

在 1990 年代初设计 Python 运行时时，计算机普遍为单核架构。为了实现高性能且内存占用极小的高级脚本语言，CPython 确立了两大基石：
1. **侵入式引用计数（Intrusive Reference Counting）**：每个 ``PyObject`` 对象头均直接内联 ``ob_refcnt``，对象的创建、传递、引用与销毁通过原子性或非原子的自增/自减（``Py_INCREF`` / ``Py_DECREF``）实时管理；
2. **非线程安全的小对象内存池（pymalloc）**：为了避免频繁调用操作系统 ``malloc()`` 引发的系统调用开销，CPython 维护了无锁/极弱锁的进程级 Pool / Arena 内存池；
3. **C 扩展生态的极简集成**：C 扩展模块开发者无需在编写第三方 C/C++ 库时在每一个全局变量、静态缓存或结构体字段上加细粒度互斥锁（Mutex），默认享有全局执行独占保护。

如果为每个 Python 对象分配独立的互斥锁，不仅单对象内存开销将暴增 200% 以上，而且单线程执行下的高频加解锁开销将使解释器性能劣化 **30%~50%**。因此，CPython 引入了单一进程级粗粒度互斥锁——**GIL**。

-----------------------------------------------------------------------------
2. 旧版 Tick GIL vs 新版时间片条件变量 GIL
-----------------------------------------------------------------------------

旧版 Tick 机制的致命缺陷（Python 2 ~ Python 3.1）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在早期 CPython 中，GIL 的切换基于 **字节码执行计数器（Tick Counter）**：
- 解释器每执行 100 条字节码指令（``sys.setcheckinterval(100)``），主动释放 GIL 并立即尝试重新获取；
- **多核下的“护航效应与虚假争用”（Convoy Effect & Battle of GIL）**：
  在多核 CPU 系统上，正在运行的线程（Core 0）释放 GIL 时，操作系统唤醒在另一个核心（Core 1）休眠的等待线程需要数十微秒的上下文切换延迟；而 Core 0 由于指令缓存和 L1 Cache 极其热度，释放后瞬间再次抢回 GIL。这导致 CPU 密集型线程长期饥饿 I/O 密集型线程，且多核并发时 CPU 占用率虚高达 200% 却伴随巨大的性能雪崩。

新版时间片条件变量机制（Antoine Pitrou 新 GIL，Python 3.2+）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了彻底根除 Tick 机制的缺陷，Python 3.2 引入了由 Antoine Pitrou 设计的基于**纳秒/微秒级超时时间片与 POSIX 条件变量（Condition Variable）**的新型 GIL 架构：
- 默认时间片阈值设为 **5000 微秒（5 毫秒）**，由 ``sys.setswitchinterval(0.005)`` 动态调节；
- 等待线程在条件变量上休眠指定时间片，若超时未获得 GIL，则向当前持有线程发送**强制退让中断信号（``_PY_GIL_DROP_REQUEST_BIT``）**；
- 结合 ``FORCE_SWITCHING`` 机制，强制释放者必须休眠等待接盘者真正上位，彻底消除了“原地抢回”的恶性争用。

-----------------------------------------------------------------------------
3. _gil_runtime_state 结构体物理拓扑
-----------------------------------------------------------------------------

在 ``Include/internal/pycore_gil.h`` 中，每个独立 GIL 实例封装为一个精密的 C 结构体：

.. code-block:: c

   struct _gil_runtime_state {
       unsigned long interval;          /* 时间片长度 (微秒, 默认 5000 us = 5 ms) */
       PyThreadState* last_holder;      /* 上一个持有 / 正在持有 GIL 的线程状态指针 */
       int locked;                      /* 原子变量: 1 表示被占用, 0 表示空闲, -1 表示未初始化 */
       unsigned long switch_number;     /* GIL 切换总次数计数器 (单调递增) */
       PyCOND_T cond;                   /* 等待 GIL 释放的条件变量 */
       PyMUTEX_T mutex;                 /* 保护 GIL 内部状态与 locked 变量的互斥锁 */
   #ifdef FORCE_SWITCHING
       PyCOND_T switch_cond;            /* 强制切换条件变量: 供释放者等待接收者上位 */
       PyMUTEX_T switch_mutex;          /* 保护 switch_cond 的专用互斥锁 */
   #endif
   #ifdef Py_GIL_DISABLED
       int enabled;                     /* 自由线程构建下: 0=禁用, >0=瞬态启用, INT_MAX=永久启用 */
   #endif
   };

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     _gil_runtime_state 内部物理拓扑                     |
   +=========================================================================+
   | interval (8 字节): 5000 us (时间片)                                     |
   | last_holder (8 字节指针): 指向当前/前任 PyThreadState                   |
   | locked (4 字节原子整数): 0 (空闲) / 1 (锁定)                            |
   | switch_number (8 字节整数): 累计切换序列号                              |
   +-------------------------------------------------------------------------+
   | 【互斥与条件同步总线】                                                  |
   | ├── mutex (pthread_mutex_t): 保护 locked 与条件变量的原子更新           |
   | ├── cond (pthread_cond_t): 唤醒在 take_gil 中排队的等待线程             |
   | ├── switch_mutex: 保护 FORCE_SWITCHING 状态机                           |
   | └── switch_cond: 阻断释放者直接重夺, 直至 last_holder 变更               |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
4. GIL 竞争、等待与抢夺核心算法（take_gil）
-----------------------------------------------------------------------------

当非持有线程需要进入 Python 虚拟机执行字节码时，必须调用 ``Python/ceval_gil.c`` 中的 ``take_gil(tstate)``：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        take_gil 物理执行流程状态机                      |
   +=========================================================================+
   |  [线程发起 take_gil(tstate)]                                            |
   |         │                                                               |
   |         ▼                                                               |
   |  获取 gil->mutex 互斥锁                                                 |
   |         │                                                               |
   |         ▼                                                               |
   |  ┌──► 检查 gil->locked 是否为 1？                                       |
   |  │      │                                                               |
   |  │      ├─► [为 0 (空闲)]: 直接抢占 ──► 标记 locked=1 ──► 退出循环      |
   |  │      │                                                               |
   |  │      └─► [为 1 (已被占用)]:                                          |
   |  │            │                                                         |
   |  │            ▼                                                         |
   |  │          记录当前切换号 saved_switchnum = gil->switch_number         |
   |  │          调用 pthread_cond_timedwait(&gil->cond, &gil->mutex, 5ms)   |
   |  │            │                                                         |
   |  │            ├─► [被正常唤醒 (持有者主动 drop_gil)]: 返回循环重试      |
   |  │            │                                                         |
   |  │            └─► [等待超时 5ms 超出 (持有者仍在运行)]:                 |
   |  │                  │                                                   |
   |  │                  ▼                                                   |
   |  │                若 switch_number 仍未变:                              |
   |  │                向 holder_tstate->eval_breaker 置位                   |
   |  │                【_PY_GIL_DROP_REQUEST_BIT】强制要求其退让!           |
   |  └──────────────────┘                                                   |
   |         │                                                               |
   |         ▼                                                               |
   |  更新 last_holder = tstate, 递增 switch_number++                        |
   |  触发 switch_cond 信号唤醒前任释放线程                                   |
   |  释放 gil->mutex, 线程成功持锁进入执行循环                              |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
5. 解释器中断响应与 FORCE_SWITCHING 防抖机制（drop_gil）
-----------------------------------------------------------------------------

解释器执行循环的中断拦截（eval_breaker）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在前面的章节中我们分析过，CPython 虚拟机在执行字节码时，在所有循环回边（Back-edges）和函数调用/返回边界，均会高频检查当前线程的 ``tstate->eval_breaker``。

当 ``_PY_GIL_DROP_REQUEST_BIT`` 被置位时，解释器主循环立即从字节码流水线中跳出，进入 ``_Py_HandlePending(tstate)``，进而调用 ``_PyThreadState_Detach(tstate)`` 触发 ``drop_gil()``。

`drop_gil()` 与 `FORCE_SWITCHING` 防原地复活算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   static void
   drop_gil(PyInterpreterState *interp, PyThreadState *tstate, int final_release)
   {
       struct _gil_runtime_state *gil = interp->ceval.gil;

       /* 1. 释放 GIL 状态 */
       MUTEX_LOCK(gil->mutex);
       _Py_atomic_store_int_relaxed(&gil->locked, 0);
       tstate->holds_gil = 0;
       COND_SIGNAL(gil->cond); /* 广播唤醒在 cond 上等待的线程 */
       MUTEX_UNLOCK(gil->mutex);

   #ifdef FORCE_SWITCHING
       /* 2. 如果本次释放是由外部强行发起 (DROP_REQUEST) */
       if (!final_release && _Py_eval_breaker_bit_is_set(tstate, _PY_GIL_DROP_REQUEST_BIT)) {
           MUTEX_LOCK(gil->switch_mutex);
           /* 若发现接盘侠尚未实际接管 (last_holder 依然是自己), 强制入睡! */
           if (((PyThreadState*)_Py_atomic_load_ptr_relaxed(&gil->last_holder)) == tstate) {
               _Py_unset_eval_breaker_bit(tstate, _PY_GIL_DROP_REQUEST_BIT);
               /* 阻塞等待, 直到新线程在 take_gil 中修改 last_holder 并发出 switch_cond 信号 */
               COND_WAIT(gil->switch_cond, gil->switch_mutex);
           }
           MUTEX_UNLOCK(gil->switch_mutex);
       }
   #endif
   }

通过 ``switch_cond`` 条件变量的强同步约束，释放 GIL 的线程被严格阻断，直到等待队列中的另一线程真正成功修改了 ``last_holder`` 并将其唤醒，**彻底解决了多核处理器上因 CPU 缓存热度导致的单线程独占霸屏问题**。

-----------------------------------------------------------------------------
6. I/O 阻塞与系统调用下的主动释放协议
-----------------------------------------------------------------------------

在执行网络通信、文件读写、密集型纯 C/C++ 计算（如 NumPy 矩阵乘法）或等待外部锁时，CPython 提供了著名的宏协议：

.. code-block:: c

   Py_BEGIN_ALLOW_THREADS
       /* 此代码块内部不持有 GIL: 其他 Python 线程可全速并发执行 */
       ret = read(fd, buf, count); // 操作系统阻塞调用
   Py_END_ALLOW_THREADS

- **物理底层实现**：
  - ``Py_BEGIN_ALLOW_THREADS`` 展开为 ``_PyThreadState_Detach(tstate)``，将线程标记为非挂载状态并调用 ``drop_gil()``；
  - ``Py_END_ALLOW_THREADS`` 展开为 ``_PyThreadState_Attach(tstate)``，重新调用 ``take_gil(tstate)`` 阻塞等待获取锁；
- **并发黄金法则**：在未持有 GIL 期间，C 扩展代码**绝对严禁**解引用任何 ``PyObject*`` 或调用任何 Python C-API，否则会导致灾难性的内存未定义行为（Undefined Behavior）。

-----------------------------------------------------------------------------
7. Python 3.13+ 多子解释器独立 GIL（PEP 684）与瞬态回退
-----------------------------------------------------------------------------

多子解释器独立 GIL（Per-Interpreter GIL）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

自 Python 3.12/3.13 起，CPython 正式落地 PEP 684。每个 ``PyInterpreterState`` 均可拥有自己专属的独立 ``_gil_runtime_state`` 实例（``interp->ceval.own_gil = 1``）。
多个子解释器在同一个进程内可各自绑定不同的 OS 线程独立运行，彼此互不干扰，**首次在标准 CPython 中实现了真正意义上的多核 CPU 并行 Python 执行**。

自由线程（Free-Threading）下的瞬态 GIL 启用
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在启用 PEP 703 Free-Threading 的构建版本中，GIL 默认被关闭（``gil->enabled = 0``）。但当加载未经多线程安全审计的传统 C 扩展模块时，运行时通过 ``_PyEval_EnableGILTransient()`` 触发全局 Stop-the-World 暂停，将 GIL 动态激活回退为传统单锁模式，兼顾前沿并发与庞大生态的向下兼容。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 传统全局解释器锁（GIL）的核心物理机制：
1. GIL 诞生的历史动因：以全局互斥代价换取极简引用计数与无锁小对象内存池的高性能；
2. 旧版基于 100 Ticks 字节码计数的护航效应缺陷与新版 5ms 时间片条件变量模型的演进；
3. ``_gil_runtime_state`` 结构体布局及 ``locked``、``cond``、``switch_cond`` 状态变量；
4. ``take_gil()`` 超时注入 ``_PY_GIL_DROP_REQUEST_BIT`` 与 ``drop_gil()`` 基于 ``FORCE_SWITCHING`` 的防恶性重夺机制；
5. ``Py_BEGIN_ALLOW_THREADS`` 的物理脱附/挂载协议以及 PEP 684 子解释器独立 GIL 拓扑。

在理解了 GIL 这一统治 Python 并发三十年的核心锁机制后，下一章我们将深入攻坚 Python 历史上最具里程碑意义的重大重构—— **05_concurrency_and_free_threading/02_pep_703_free_threaded_cpython.rst（PEP 703 Free-Threading 架构全景：禁用 GIL 后的内存安全性模型）**。
