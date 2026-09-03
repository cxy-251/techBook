==================================================================================================
现代并发与协程支持：std::generator 惰性流、std::jthread 自动加入、stop_token 协作取消与 std::atomic
==================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 4 节（``07_modern_stl_and_ranges_architecture/04_constexpr_containers_and_compile_time_algorithms.rst``）中，我们深入剖析了编译期 STL 的运行机制，包括常量求值引擎的解释执行模型、P0784R7 瞬态动态内存分配（Transient Allocation）契约、``constexpr std::vector`` 的三指针映射以及双态执行分发机制。至此，现代 C++ 的编译期单线程确定性计算体系已建立完备。然而，现代高性能计算体系的另一核心维度在于**运行期的异步事件流与高度并发的硬件多核协同**。C++20 与 C++23 标准库对这一领域进行了重构：引入语言级协程基础设施并推出了与 Ranges 管道无缝集成的 ``std::generator`` 惰性生成器；彻底修复了 ``std::thread`` 析构触发 ``std::terminate()`` 的历史缺陷，推出了具备 RAII 自动汇入与协作式取消能力的 ``std::jthread`` 与 ``stop_token`` 体系；同时在 ``std::atomic`` 内存模型之上演进出了无锁等待唤醒原语（``wait/notify``）与轻量级同步屏障（``std::latch`` / ``std::barrier``）。本节将全面拆解现代并发与协程 STL 的物理微架构与底层交互机理。

C++20 协程状态机物理拓扑与 std::generator 惰性数据流
---------------------------------------------------

C++20 引入的核心协程是**无栈协程（Stackless Coroutines）**。与需要预分配独立调用栈、产生重度上下文切换开销（保存/恢复数十个 CPU 寄存器）的有栈协程（如纤程 Fiber）不同，C++ 无栈协程在编译期由编译器前端直接降解为一组精细的控制流重写与堆分配状态机。

协程帧（Coroutine Frame）的内存布局与 HALO 优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当一个普通函数内部包含 ``co_await``、``co_yield`` 或 ``co_return`` 中任意关键字时，该函数即被编译器判定为协程。编译器将对其进行彻底重构：原函数的局部变量、调用参数、当前挂起点索引以及协程承诺对象（Promise Object）均无法存放于易失的 CPU 栈帧（Stack Frame）上，而是被打包搬移至一个由编译器合成的堆内存结构——**协程帧（Coroutine Frame）**中。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  C++20 编译器合成协程帧（Coroutine Frame）物理布局          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   高地址                                                                    |
   |   +---------------------------------------------------------------------+   |
   |   | 局部变量存储区 (Local Variables Area)                               |   |
   |   | (跨越挂起点存活的局部对象，按对齐紧凑排布)                          |   |
   |   +---------------------------------------------------------------------+   |
   |   | 函数实参暂存区 (Captured Arguments Area)                            |   |
   |   | (按值拷贝或引用的实参副本，保障生命周期)                            |   |
   |   +---------------------------------------------------------------------+   |
   |   | 承诺对象 (Promise Object: promise_type)                             |   |
   |   | (控制协程生命周期、暂存 yield 数据、捕获异常)                       |   |
   |   +---------------------------------------------------------------------+   |
   |   | 挂起点恢复索引 (Suspend Point Index / State, 通常为 4~8 字节整数)   |   |
   |   | (记录协程当前处于第几个 co_await / co_yield 阶段)                   |   |
   |   +---------------------------------------------------------------------+   |
   |   | 函数指针表 (Function Pointers / Vtable-like Header):                |   |
   |   |   - resume_fn: 指向编译期合成的恢复执行逻辑入口                     |   |
   |   |   - destroy_fn: 指向销毁协程帧并调用内部对象析构函数的清理入口      |   |
   |   +---------------------------------------------------------------------+   |
   |   低地址 (std::coroutine_handle<Promise>::address() 指向此处)               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

协程帧的内存开销与生命周期控制依赖以下核心机制：
1. **默认堆分配（operator new）**：
   在进入协程时，编译器默认隐式调用 ``operator new`` 分配协程帧所需的字节空间；在协程最终挂起（``final_suspend``）并被销毁时，调用 ``operator delete`` 释放该内存。
2. **堆分配消除优化（HALO - Heap Allocation of Coroutine Frame Optimization）**：
   若编译期能够通过内联展开与逃逸分析（Escape Analysis）证明协程帧的生命周期完全被调用者的栈帧生命周期所包含（即协程不会逃逸至其他线程或长周期全局上下文），编译器优化流水线（如 LLVM 的 ``CoroElide`` Pass）会直接消除 ``operator new`` 堆调用，将整个协程帧直接内嵌（Inlined）在调用者的局部运行栈上，实现极致的零堆分配开销。

promise_type、coroutine_handle 与 Awaitable 契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++20 协程不是黑盒语法，而是高度定制化的控制流契约系统。它由三个相互啮合的组件支撑：

- **Promise Object（承诺对象）**：
  定义协程内部行为的中枢。协程定义必须提供嵌套的 ``promise_type``，它向编译器提供以下生命周期回调接口：
  - ``get_return_object()``：构造并返回给外部调用者的外部句柄类型（如 ``std::generator<T>``）；
  - ``initial_suspend()``：协程首次被调用时是立刻执行（``std::suspend_never``）还是惰性挂起（``std::suspend_always``）；
  - ``final_suspend() noexcept``：协程执行完毕后的最终挂起状态（必须为 ``noexcept``，防止栈展开与协程帧析构冲突）；
  - ``yield_value(T)``：响应 ``co_yield`` 表达式，暂存产生的值并挂起；
  - ``return_value(V)`` / ``return_void()``：响应 ``co_return``；
  - ``unhandled_exception()``：捕获协程体内未处理的异常。

- **coroutine_handle<P>（协程句柄）**：
  底层非拥有的原始指针包装器，充当协程帧的不透明操作句柄。提供 ``resume()`` 恢复执行、``destroy()`` 显式释放协程帧、``done()`` 查询是否终止，以及与原始地址 ``void*`` 的双向转换。

- **Awaitable 与 Awaiter 概念**：
  控制具体挂起逻辑的协议。一个 Awaiter 对象必须实现三个方法：
  - ``await_ready() noexcept -> bool``：快速路径，返回 ``true`` 表示条件满足无需挂起直接继续；
  - ``await_suspend(coroutine_handle<>) -> void | bool | coroutine_handle<>``：真正挂起时的底层分发（支持对称转移 Symmetric Transfer）；
  - ``await_resume() -> ReturnType``：协程恢复后该表达式的最终求值结果。

C++23 std::generator<Ref, Value, Allocator> 惰性生成器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++20 确立协程机制后，C++23 在标准库中正式标准化了 ``std::generator``（P2502R2）。它是专为**同步惰性求值序列**设计的轻量级协程抽象，与 C++20 Ranges 概念体系达成了完全的原生融合。

.. list-table:: std::generator 与常规容器、Views 视图的设计维度对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 标准容器（如 std::vector）
     - 视图（如 std::views::transform）
     - 协程生成器（std::generator）
   * - **内存占用模型**
     - 全量瞬时堆分配，占用 $\mathcal{O}(N)$ 空间
     - 零数据拷贝，非拥有观察者，引用外部序列
     - $\mathcal{O}(1)$ 空间占用，仅消耗单个协程帧
   * - **计算时序**
     - 饥饿求值（Eager Evaluation）
     - 惰性管道适配（Lazy Pipeline）
     - 按需生产（On-demand Pull-based Evaluation）
   * - **控制流表达能力**
     - 静态平坦数据组织
     - 需组合复杂的闭包算子
     - 允许使用原生循环、多层嵌套、条件分支与递归
   * - **Ranges 协议建模**
     - 满足 ``contiguous_range`` 等全部概念
     - 满足 ``view``、可多轮遍历（若底层支持）
     - 严格满足 ``std::ranges::input_range``（单向单轮消费）

``std::generator`` 核心架构与递归展开（elements_of）
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``std::generator`` 建模了典型的 **Pull-based（拉式）数据生成模型**：
1. 调用协程函数时，通过 ``initial_suspend()`` 返回 ``std::suspend_always``，协程不会立即执行计算，而是瞬间返回一个 ``std::generator`` 实例。
2. 外部消费者通过 ``begin()`` 获取迭代器，对迭代器解引用与自增（``operator++()``）时，内部调用 ``coroutine_handle::resume()`` 唤醒协程。
3. 协程内部执行计算，遇到 ``co_yield expr`` 时，将产生的值引用存储在 Promise 内部槽位中，随后挂起自身，控制权交还给外部迭代器。
4. **C++23 递归生成优化（``std::ranges::elements_of``）**：
   在树形遍历或嵌套递归生成场景下，常规协程如果直接递归调用自身会产生 $\mathcal{O}(D)$ 层的调用栈与独立协程句柄嵌套，导致严重的内存占用与调度虚耗。C++23 提供了 ``std::ranges::elements_of`` 辅助标签，允许协程直接将另一个子 Generator 的控制权以堆栈链接方式就地扁平化展开，消除了递归深度的上下文跳转开销。

std::jthread 物理架构与 RAII 自动汇入
-------------------------------------

自 C++11 起引入的 ``std::thread`` 在现代系统级软件设计中存在广为人知的工程缺陷：如果一个可加入（Joinable）的 ``std::thread`` 对象在离开其局部作用域（无论是常规分支退出还是抛出异常）时，既没有被显式调用 ``.join()``，也没有被调用 ``.detach()``，**其析构函数将无条件调用 ``std::terminate()`` 强制终止整个进程**。

std::thread 的历史缺陷与安全陷阱
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

这种设计违背了 C++ 核心的 RAII（Resource Acquisition Is Initialization）哲学。RAII 要求对象的生命周期应当自动管理其拥有的系统底层资源，并在析构时安全回收。在大型工程中，由于异常引发的栈展开（Stack Unwinding）往往极易跳过手动编写的 ``t.join()`` 语句，导致致命的不可恢复崩溃；而若草率使用 ``t.detach()``，则后台线程可能在主线程资源、局部对象或捕获引用销毁后继续访问非法内存，产生更隐蔽的内存踩踏与悬垂指针缺陷。

std::jthread 的内存拓扑与 RAII 保证
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++20 正式引入了 ``std::jthread``（Cooperative Cancellation and Joining Thread）。``std::jthread`` 是对底层系统线程句柄与协作式取消中枢的高阶封装。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      std::jthread 内部物理组合拓扑结构                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   std::jthread 对象本体 (栈上占用空间: 16 字节 / 64位体系):                 |
   |   +---------------------------------------------------------------------+   |
   |   | std::thread _M_thread; (底层原生 OS 线程句柄与 thread::id)          |   |
   |   +---------------------------------------------------------------------+   |
   |   | std::stop_source _M_stop_source; (指向共享停止状态的引用指针)       |   |
   |   +---------------------------------------------------------------------+   |
   |                                      |                                      |
   |                                      v                                      |
   |   共享取消控制块 (Shared Stop State, 动态分配或引用计数管理):               |
   |   +---------------------------------------------------------------------+   |
   |   | std::atomic<uint32_t> _M_state;                                     |   |
   |   |   - bit 0: 停止请求标志 (Stop Requested Flag: 0 = 运行, 1 = 请求停止) |   |
   |   |   - bit 1: 正在执行回调 (Callback Running Flag)                     |   |
   |   |   - bits 2~31: stop_callback 注册数量与引用计数                     |   |
   |   +---------------------------------------------------------------------+   |
   |   | std::thread::id _M_requesting_thread; (记录发出取消请求的线程 ID)   |   |
   |   +---------------------------------------------------------------------+   |
   |   | stop_callback_node* _M_callbacks_head; (挂载的链表头，保护回调注册) |   |
   |   +---------------------------------------------------------------------+   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

``std::jthread`` 的 RAII 析构契约极其明确且安全：
当 ``std::jthread`` 对象析构时，如果当前内部线程处于可汇入（``joinable()``）状态，其析构函数将**按序原子执行两项操作**：
1. 隐式调用 ``request_stop()``，发出停止取消信号；
2. 紧接着调用 ``join()``，阻塞当前线程，直至后台工作线程安全退出。

这一机制彻底阻断了未 join 导致程序崩溃或分离线程访问悬垂引用的内存灾难。

协作式取消机制：stop_token、stop_source 与 stop_callback
--------------------------------------------------------

抢占式线程终止（如 POSIX 的 ``pthread_cancel`` 或强行发送 ``SIGKILL``）在现代 C++ 对象模型中是极度危险的，因为强行终止线程会剥夺局部对象的析构函数执行权利，导致互斥锁（Mutex）处于被永久锁死（Deadlock）的未定义状态，引发严重的资源泄露与数据一致性撕裂。现代并发体系要求必须采用**协作式取消（Cooperative Cancellation）**。

协作式取消三元组职责划分
~~~~~~~~~~~~~~~~~~~~~~~~

C++20 提供了由三种核心对象构成的协作式取消架构：

1. **std::stop_source（取消信号源）**：
   持有共享停止状态的所有权。拥有发起取消的主动控制权。调用 ``source.request_stop()`` 会将共享状态原子性地置位为“请求停止”。
2. **std::stop_token（停止状态观察者）**：
   用于向后台任务传递只读的取消观察视图。它是可轻量拷贝的非拥有句柄。工作线程通过 ``token.stop_requested()`` 轮询查询是否已被请求退出。当使用支持取消的函数签名（接收 ``std::stop_token`` 作为首参数）初始化 ``std::jthread`` 时，``jthread`` 会自动将自身持有的 ``stop_token`` 注入到工作线程函数中。
3. **std::stop_callback（回调注册器）**：
   事件驱动模型的核心。允许在工作线程内部或外部注册一个可调用对象（Lambda）。当任意线程调用 ``stop_source::request_stop()`` 时，已注册的所有回调函数将在发出请求的同一线程上下文中被立即就地同步触发。

.. list-table:: 协作式取消组件职责与方法契约
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 组件名称
     - 构造与移动语义
     - 核心成员方法与职责
   * - **std::stop_source**
     - 支持拷贝与移动，共享底层控制块引用计数
     - ``request_stop()`` 发出取消请求；``get_token()`` 生成只读观察 Token；``stop_possible()`` 查询是否可取消
   * - **std::stop_token**
     - 极轻量类型，仅包含单个共享指针，高效值传递
     - ``stop_requested()`` 快速原子读取是否被取消；``stop_possible()`` 检查关联的 source 是否仍存活
   * - **std::stop_callback**
     - 模板类型，禁止拷贝，生命周期绑定当前作用域
     - 析构时安全反注册；构造时若检测到目标已处于 stop 状态，则直接在当前线程同步执行该回调

基于 condition_variable_any 的原子打断机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工作线程往往阻塞于条件变量（Wait on Condition Variable）或 I/O 操作中。如果仅仅轮询 ``token.stop_requested()``，处于休眠状态的线程将无法感知取消信号，导致死锁或无法及时退出。

为解决这一难题，C++20 将 ``std::condition_variable_any`` 扩展为原生接受 ``std::stop_token``：

.. code-block:: cpp

   template <class Lock, class Predicate>
   bool wait(Lock& lock, std::stop_token stoken, Predicate pred);

底层物理机理：在调用 ``wait`` 时，系统内部隐式在 ``stoken`` 上构造一个临时的 ``std::stop_callback``。当外部线程调用 ``request_stop()`` 时，回调函数被触发，内部执行 ``notify_all()``，条件变量被立即强制唤醒并退出等待，彻底消除了基于休眠轮询（Sleep Polling）带来的 CPU 延迟与算力浪费。

std::atomic、内存序微架构与现代同步原语
---------------------------------------

现代多核 CPU（如 x86、ARM、RISC-V）为了最大化指令吞吐量，深度应用了乱序执行（Out-of-Order Execution）、多层 Store Buffer 与私有高速缓存（L1/L2/L3 Cache）。这导致代码在源码中的书写顺序与多核之间实际观察到的内存读写顺序产生偏差。

六种原子内存序（Memory Order）的微架构物理映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++11/C++20 标准定义了六种内存顺序模型，精确指导编译器与 CPU 硬件在不同一致性强度下的重排与屏障生成：

1. **std::memory_order_relaxed（松弛模型）**：
   仅保证单变量操作本身的原子性与修改顺序（Modification Order）一致，不保证任何跨变量的同步或指令依赖。编译器与硬件可以任意跨越该操作进行读写重排。无任何硬件内存屏障开销。
2. **std::memory_order_consume（消费依赖模型）**：
   仅保证与当前载入值具有数据依赖（Data Dependency）关系的后续指令不被前置重排。由于绝大多数编译器实现难以维护数据依赖追踪，主流实践通常直接将其升级为更保守的 Acquire 语义。
3. **std::memory_order_acquire（获取语义，用于 Load）**：
   **读屏障语义**：保证在当前操作之后的所有后续读写操作，绝对不能被重排到当前 Acquire 操作之前。
4. **std::memory_order_release（释放语义，用于 Store）**：
   **写屏障语义**：保证在当前操作之前的所有先前读写操作，绝对不能被重排到当前 Release 操作之后。
   - **Acquire-Release 同步环（Synchronizes-With）**：当线程 A 带有 Release 地写入原子变量，线程 B 随后通过 Acquire 读取到该相同的值时，线程 A 在该写入点前所有的内存副作用（包括对普通非原子变量的写入），在线程 B 的该 Acquire 之后对线程 B 全量立即可见。
5. **std::memory_order_acq_rel（获取-释放双向模型）**：
   用于读-修改-写（Read-Modify-Write, 如 ``fetch_add``、``compare_exchange_strong``）复合操作，同时具备 Acquire 与 Release 边界屏障约束。
6. **std::memory_order_seq_cst（顺序一致性模型，默认）**：
   提供最严格的全局统一时间线视图。在保证 Acquire-Release 的同时，保证所有核心观察到的全部 ``seq_cst`` 操作存在一个绝对全局的偏序关系。

.. list-table:: x86 TSO 与 ARM64 弱内存模型下的原子内存序编译代码对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 内存序模型
     - x86-64 硬件编译映射 (TSO 强内存序)
     - ARM64 硬件编译映射 (弱内存序架构)
   * - **Relaxed Store**
     - ``mov [mem], reg`` (天然单周期执行)
     - ``str reg, [mem]`` (无屏障)
   * - **Release Store**
     - ``mov [mem], reg`` (硬件天然禁止 Store-Store 重排)
     - ``stlr reg, [mem]`` (带释放屏障的专用指令)
   * - **Acquire Load**
     - ``mov reg, [mem]`` (硬件天然禁止 Load-Load 重排)
     - ``ldar reg, [mem]`` (带获取屏障的专用指令)
   * - **Seq_cst Store**
     - ``xchg [mem], reg`` 或 ``mov [mem], reg + mfence``
     - ``stlr reg, [mem] + dmb ish`` (强制全同步总线屏障)

C++20 std::atomic 等待与通知机制（wait/notify）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++20 之前，若需要在原子状态变更前阻塞当前线程，只能编写轮询自旋锁（Busy-Wait Loop）或外挂复杂的 ``std::mutex`` 与 ``std::condition_variable``。前者在高争用下空耗 CPU 核心电能与指令流水线，后者则产生巨大的互斥量元数据与系统调用开销。

C++20 在 ``std::atomic<T>`` 与 ``std::atomic_ref<T>`` 成员中原生注入了系统底层的等待-通知协议：

.. code-block:: cpp

   void wait(T old, std::memory_order order = std::memory_order_seq_cst) const noexcept;
   void notify_one() noexcept;
   void notify_all() noexcept;

- **Linux 物理机理**：底层直接降解为 Linux 内核的高性能 ``futex(FUTEX_WAIT)`` 与 ``futex(FUTEX_WAKE)`` 系统调用。当值等于 ``old`` 时，内核将当前线程置于挂起睡眠队列，不消耗任何 CPU 时钟周期；直至其他核心调用 ``notify_one/all`` 时由内核精准唤醒。
- **Windows / macOS 物理机理**：分别映射至 Windows 的 ``WaitOnAddress`` 与 Darwin 的 ``__ulock_wait``。

std::atomic_ref 与现代同步屏障（latch 与 barrier）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **std::atomic_ref<T>（非拥有式原子引用）**：
  在高性能并行图计算与科学矩阵运算中，若将整块海量数据全量声明为 ``std::atomic<T>``，其结构体膨胀与只读阶段的开销是不可接受的。C++20 的 ``std::atomic_ref<T>`` 允许在计算的关键并发阶段，将一个普通对齐的非原子对象临时包装为原子对象进行读写，在并行结束后自动注销，达成零多余元数据开销。
- **std::latch（一次性单向倒计时门闩）**：
  内部维持一个原子计数器。每个工作线程完成后调用 ``count_down()``，主线程通过 ``wait()`` 阻塞等待计数器归零。只能倒数一次，不可复用，适用于阶段性初始化汇聚。
- **std::barrier（可循环阶段性分步屏障）**：
  专为迭代式分步并发计算（如多线程物理引擎步进、神经网络并行反向传播）设计。各工作线程通过 ``arrive_and_wait()`` 相互等待，当所有线程均到达时，自动触发注册的阶段完成回调函数（Completion Function），随后自动重置计数器进入下一轮计算。

自包含工业级现代并发与协程引擎实战
----------------------------------

为了全方位验证上述理论与标准库核心组件的底层运作模式，下面提供一套完整的、自包含的高性能现代并发与协程核心代码。

实现包含：
1. **轻量级同步流生成器 MiniGenerator<T>**：手动实现 C++20 协程 ``promise_type``、``coroutine_handle``、``initial_suspend`` 惰性挂起、``co_yield`` 数据中转以及完整的 STL 输入迭代器（``InputIterator``）契约；
2. **RAII 线程取消包装器 MiniJThread 与 MiniStopToken**：演示原子状态下的协作取消、自动 join 以及析构异常安全；
3. **基于 atomic wait/notify 的轻量级同步门闩**：实现无锁自旋转 futex 挂起的高性能同步状态机；
4. **端到端集成测试与断言套件**。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <coroutine>
   #include <thread>
   #include <atomic>
   #include <chrono>
   #include <functional>
   #include <cassert>
   #include <utility>
   #include <vector>
   #include <memory>

   namespace core_stl {

   // =========================================================================
   // 1. 自包含轻量级协程生成器 MiniGenerator<T> (模拟 C++23 std::generator)
   // =========================================================================

   template <typename T>
   class MiniGenerator {
   public:
       struct promise_type {
           const T* current_value = nullptr;

           MiniGenerator get_return_object() noexcept {
               return MiniGenerator{std::coroutine_handle<promise_type>::from_promise(*this)};
           }

           // 初始严格挂起：实现惰性求值
           std::suspend_always initial_suspend() noexcept { return {}; }

           // 最终挂起：保持协程帧存活，由外层 RAII 对象负责 destroy
           std::suspend_always final_suspend() noexcept { return {}; }

           // 响应 co_yield：暂存指针并挂起协程
           std::suspend_always yield_value(const T& val) noexcept {
               current_value = std::addressof(val);
               return {};
           }

           void return_void() noexcept {}
           void unhandled_exception() { throw; }
       };

       using handle_type = std::coroutine_handle<promise_type>;

       // 迭代器结构：满足 std::ranges::input_range 的基本契约
       class iterator {
       public:
           using value_type = T;
           using difference_type = std::ptrdiff_t;
           using reference = const T&;
           using pointer = const T*;
           using iterator_category = std::input_iterator_tag;

           iterator() noexcept : coro_(nullptr) {}
           explicit iterator(handle_type coro) noexcept : coro_(coro) {}

           iterator& operator++() {
               assert(coro_ && !coro_.done() && "Cannot increment finished coroutine");
               coro_.resume();
               if (coro_.done()) {
                   coro_ = nullptr;
               }
               return *this;
           }

           void operator++(int) {
               (void)operator++();
           }

           reference operator*() const noexcept {
               assert(coro_ && "Cannot dereference null or finished coroutine iterator");
               return *coro_.promise().current_value;
           }

           pointer operator->() const noexcept {
               return std::addressof(operator*());
           }

           bool operator==(const iterator& other) const noexcept {
               return coro_ == other.coro_;
           }

           bool operator!=(const iterator& other) const noexcept {
               return !(*this == other);
           }

       private:
           handle_type coro_;
       };

       explicit MiniGenerator(handle_type h) noexcept : handle_(h) {}

       ~MiniGenerator() {
           if (handle_) {
               handle_.destroy();
           }
       }

       // 禁用拷贝语义，提供严谨的移动所有权
       MiniGenerator(const MiniGenerator&) = delete;
       MiniGenerator& operator=(const MiniGenerator&) = delete;

       MiniGenerator(MiniGenerator&& other) noexcept : handle_(other.handle_) {
           other.handle_ = nullptr;
       }

       MiniGenerator& operator=(MiniGenerator&& other) noexcept {
           if (this != &other) {
               if (handle_) handle_.destroy();
               handle_ = other.handle_;
               other.handle_ = nullptr;
           }
           return *this;
       }

       iterator begin() {
           if (handle_) {
               if (!handle_.done()) {
                   handle_.resume(); // 推进到首次 co_yield
               }
               if (handle_.done()) {
                   return iterator{nullptr};
               }
               return iterator{handle_};
           }
           return iterator{nullptr};
       }

       iterator end() noexcept {
           return iterator{nullptr};
       }

   private:
       handle_type handle_;
   };

   // =========================================================================
   // 2. 自包含协作式取消与 RAII 自动加入线程 MiniJThread
   // =========================================================================

   class MiniStopToken;

   class MiniStopSource {
   public:
       MiniStopSource() : stop_requested_(std::make_shared<std::atomic<bool>>(false)) {}

       void request_stop() noexcept {
           if (stop_requested_) {
               stop_requested_->store(true, std::memory_order_release);
           }
       }

       [[nodiscard]] bool stop_requested() const noexcept {
           return stop_requested_ && stop_requested_->load(std::memory_order_acquire);
       }

       [[nodiscard]] MiniStopToken get_token() const noexcept;

   private:
       std::shared_ptr<std::atomic<bool>> stop_requested_;
   };

   class MiniStopToken {
   public:
       MiniStopToken() = default;
       explicit MiniStopToken(std::shared_ptr<std::atomic<bool>> flag) : flag_(std::move(flag)) {}

       [[nodiscard]] bool stop_requested() const noexcept {
           return flag_ && flag_->load(std::memory_order_acquire);
       }

   private:
       std::shared_ptr<std::atomic<bool>> flag_;
   };

   inline MiniStopToken MiniStopSource::get_token() const noexcept {
       return MiniStopToken{stop_requested_};
   }

   class MiniJThread {
   public:
       MiniJThread() noexcept = default;

       template <typename Callable, typename... Args>
       explicit MiniJThread(Callable&& func, Args&&... args) {
           stop_source_ = MiniStopSource{};
           auto token = stop_source_.get_token();

           // 启动原生线程，并将取消令牌传递给执行体
           thread_ = std::thread([func = std::forward<Callable>(func), 
                                  token, 
                                  ...captured_args = std::forward<Args>(args)]() mutable {
               if constexpr (std::is_invocable_v<Callable, MiniStopToken, Args...>) {
                   std::invoke(func, token, captured_args...);
               } else {
                   std::invoke(func, captured_args...);
               }
           });
       }

       // RAII 核心：析构时自动请求取消并安全 join
       ~MiniJThread() {
           if (joinable()) {
               request_stop();
               join();
           }
       }

       MiniJThread(const MiniJThread&) = delete;
       MiniJThread& operator=(const MiniJThread&) = delete;

       MiniJThread(MiniJThread&& other) noexcept
           : thread_(std::move(other.thread_)), stop_source_(std::move(other.stop_source_)) {}

       MiniJThread& operator=(MiniJThread&& other) noexcept {
           if (this != &other) {
               if (joinable()) {
                   request_stop();
                   join();
               }
               thread_ = std::move(other.thread_);
               stop_source_ = std::move(other.stop_source_);
           }
           return *this;
       }

       void request_stop() noexcept {
           stop_source_.request_stop();
       }

       [[nodiscard]] bool stop_requested() const noexcept {
           return stop_source_.stop_requested();
       }

       [[nodiscard]] bool joinable() const noexcept {
           return thread_.joinable();
       }

       void join() {
           thread_.join();
       }

       void detach() {
           thread_.detach();
       }

   private:
       std::thread thread_;
       MiniStopSource stop_source_;
   };

   // =========================================================================
   // 3. 基于 std::atomic 的轻量级同步门闩 MiniLatch
   // =========================================================================

   class MiniLatch {
   public:
       explicit MiniLatch(std::ptrdiff_t expected) : count_(expected) {
           assert(expected >= 0);
       }

       void count_down(std::ptrdiff_t update = 1) noexcept {
           auto prev = count_.fetch_sub(update, std::memory_order_acq_rel);
           if (prev <= update) {
               // 计数归零，唤醒等待者
               count_.notify_all();
           }
       }

       void wait() const noexcept {
           while (true) {
               auto current = count_.load(std::memory_order_acquire);
               if (current <= 0) return;
               // 原生底层等待机制：避免自旋空耗 CPU
               count_.wait(current, std::memory_order_relaxed);
           }
       }

       void arrive_and_wait(std::ptrdiff_t update = 1) noexcept {
           count_down(update);
           wait();
       }

   private:
       mutable std::atomic<std::ptrdiff_t> count_;
   };

   } // namespace core_stl

   // =========================================================================
   // 4. 协程业务示例与综合测试驱动验证
   // =========================================================================

   // 惰性斐波那契生成器协程
   core_stl::MiniGenerator<uint64_t> fibonacci_stream(std::size_t limit) {
       uint64_t a = 0;
       uint64_t b = 1;
       for (std::size_t i = 0; i < limit; ++i) {
           co_yield a;
           uint64_t next = a + b;
           a = b;
           b = next;
       }
   }

   namespace test {

   inline void runModernConcurrencyAndCoroutineTestSuite() {
       std::cout << \"=======================================================\n\";
       std::cout << \" 现代并发与协程支持底层架构验证套件\n\";
       std::cout << \"=======================================================\n\n\";

       // 1. 验证 MiniGenerator 惰性流与范围遍历
       std::cout << \"[测试 1: 协程生成器 MiniGenerator 惰性求值]:\n\";
       auto gen = fibonacci_stream(10);
       std::vector<uint64_t> results;
       for (uint64_t val : gen) {
           results.push_back(val);
       }

       assert(results.size() == 10);
       assert(results[0] == 0);
       assert(results[1] == 1);
       assert(results[2] == 1);
       assert(results[3] == 2);
       assert(results[4] == 3);
       assert(results[5] == 5);
       assert(results[9] == 34);

       std::cout << \"  - 斐波那契数列前 10 项通过协程按需生成成功: \";
       for (auto v : results) std::cout << v << \" \";
       std::cout << \"\n  - 协程状态机在遍历终点安全析构。\n\n\";

       // 2. 验证 MiniJThread 的 RAII 自动取消与析构 Join 机制
       std::cout << \"[测试 2: MiniJThread RAII 自动取消与汇入]:\n\";
       std::atomic<int> work_cycles{0};
       {
           core_stl::MiniJThread worker([&](core_stl::MiniStopToken token) {
               while (!token.stop_requested()) {
                   work_cycles.fetch_add(1, std::memory_order_relaxed);
                   std::this_thread::sleep_for(std::chrono::milliseconds(5));
               }
           });

           std::this_thread::sleep_for(std::chrono::milliseconds(30));
           // worker 在离开此处花括号作用域时发生析构
           // 其析构函数将自动发出 request_stop() 并 join() 等待线程结束
       }

       assert(work_cycles.load() > 0);
       std::cout << \"  - 工作线程正常执行循环周期数: \" << work_cycles.load() << \"\n\";
       std::cout << \"  - MiniJThread 析构函数顺利触发自动协作取消与线程汇入，无死锁、无异常退出。\n\n\";

       // 3. 验证 MiniLatch 协同倒计时同步
       std::cout << \"[测试 3: MiniLatch 基于 atomic wait/notify 的同步屏障]:\n\";
       constexpr int ThreadCount = 4;
       core_stl::MiniLatch latch(ThreadCount);
       std::atomic<int> completed_tasks{0};

       std::vector<core_stl::MiniJThread> pool;
       pool.reserve(ThreadCount);

       for (int i = 0; i < ThreadCount; ++i) {
           pool.emplace_back([&, id = i]() {
               std::this_thread::sleep_for(std::chrono::milliseconds(10 * (id + 1)));
               completed_tasks.fetch_add(1, std::memory_order_release);
               latch.count_down();
           });
       }

       // 主线程等待所有工作线程到达门闩
       latch.wait();
       assert(completed_tasks.load(std::memory_order_acquire) == ThreadCount);
       std::cout << \"  - 全部 \" << ThreadCount << \" 个工作线程安全同步完成，主线程被精准唤醒。\n\n\";

       std::cout << \"=======================================================\n\";
       std::cout << \" 全部测试用例通过，现代并发与协程体系契约严格满足。\n\";
       std::cout << \"=======================================================\n\";
   }

   } // namespace test
