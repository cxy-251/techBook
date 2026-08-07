第052章：Context Managers and Resource Cleanup Architecture
===========================================================

核心知识点
----------

* context manager 的核心协议是 ``__enter__`` / ``__exit__``；``async with`` 对应 ``__aenter__`` / ``__aexit__``。
* ``with`` 的关键保证是：只要 ``__enter__`` 成功返回，语句体正常结束、抛异常或目标绑定失败，都会进入对应 ``__exit__``。
* ``__exit__(exc_type, exc, tb)`` 返回真值可抑制当前异常；返回假值或 ``None`` 时异常继续向外传播。
* class-based context manager 适合复杂状态机；``@contextmanager`` 适合短小线性资源边界，``yield`` 前是获取阶段，``yield`` 后通常放释放逻辑。
* 生成器式 context manager 必须恰好 yield 一次；获取阶段失败与资源已获取后的释放失败应分开理解。
* deterministic cleanup 的重点是让文件、锁、事务、临时目录、连接、订阅等外部资源有明确释放点，而不是依赖对象何时被 GC。
* ``ExitStack`` 用 LIFO 栈动态登记同步退出动作，适合资源数量和组合在 runtime 才确定的场景。
* ``enter_context(cm)`` 只有在 ``__enter__`` 成功后才登记 ``__exit__``；因此中途获取失败时，只清理已经成功取得的资源。
* ``ExitStack.callback()`` 注册普通 cleanup，不参与异常抑制；``push()`` 注册 exit-style 回调，可以接收并改变异常状态。
* ``pop_all()`` 可表达资源所有权转移：全部获取成功后，把退出责任从临时 stack 转移给新的 owner。
* ``AsyncExitStack`` 同时管理同步和异步资源；异步 cleanup 必须被 ``await``，因此退出栈自身要通过 ``async with`` 或 ``aclose()`` 收束。
* ``aclosing()`` 适合确保异步生成器在当前任务和 contextvars 环境中完成 ``aclose()``。
* ``nullcontext`` 用于统一“当前函数拥有资源”和“借用调用方传入资源”两种控制流，但 ownership 仍要由 API 设计明确。
* ``closing`` / ``aclosing`` 只是把已有 close/aclose 方法包装成 context protocol，不会改变底层资源所有权语义。
* finalizer 和 ``__del__`` 不适合作为核心外部资源释放机制；GC 时机、循环引用、解释器退出和异常路径都使其不可作为主要确定性边界。

关键路径
--------

单个同步资源：

::

   evaluate context expression
       ↓
   call __enter__
       ↓
   enter succeeded?
       ├─ no  → propagate acquisition error
       └─ yes → bind value
                ↓
             execute body
                ↓
          normal / exception
                ↓
       call __exit__(exc info)
                ↓
       suppress? / propagate?

``ExitStack`` 动态资源路径：

::

   create ExitStack
       ↓
   acquire resource A → register A exit
       ↓
   acquire resource B → register B exit
       ↓
   acquire resource C fails
       ↓
   run exits in reverse order
       ↓
   B cleanup → A cleanup
       ↓
   propagate acquisition error

异步退出路径：

::

   async with AsyncExitStack
       ↓
   enter_async_context / enter_context
       ↓
   register async + sync cleanup
       ↓
   body returns / raises / is cancelled
       ↓
   await cleanup in LIFO order
       ↓
   propagate or suppress final exception state

概念辨析
--------

* **context manager 与 ``try/finally``**：前者把获取/释放封装为可组合协议；后者是更底层、通用的控制流保证。
* **释放资源与回收内存**：``close``、unlock、rollback 属于协议动作；对象内存何时被 GC 是另一层问题。
* **owner 与 borrower**：owner 负责最终释放；borrower 只在约定生命周期内使用资源。
* **``ExitStack.callback`` 与 ``push``**：callback 只做清理；push 的 exit 函数参与异常三元组处理和抑制。
* **同步 stack 与异步 stack**：异步 cleanup 需要 await，不能交给普通 ``ExitStack.close()``。
* **异常抑制与异常替换**：退出函数可抑制当前异常；cleanup 自身抛出新异常时，还可能改变外层最终看到的异常链。
* **context manager 与 finalizer**：context manager 有明确控制流释放点；finalizer 的时机不可作为业务资源正确性的基础。

本章结论
--------

资源清理架构可以压缩为“获取成功后立即建立释放责任，多个责任按 LIFO 收束，异常状态随退出协议传播”。固定资源用 ``with``，动态资源集合用 ``ExitStack``，异步资源用 ``AsyncExitStack``；所有情况下都要先确认谁拥有资源、何时登记 cleanup、失败时哪些资源已经取得。这样才能把文件、锁、事务、连接和取消路径统一到同一个确定性生命周期模型中。