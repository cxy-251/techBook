第030章：System Call Boundary and Kernel Object Model
=====================================================

核心知识点
----------

* System Call 是用户态请求 Kernel 服务的受控入口。用户态准备 ABI 参数并触发 trap/exception，Kernel 验证参数、解析对象、执行操作，再返回状态或 errno。
* App 使用文件、socket、timer、共享内存、设备和进程时，真正持有资源的是 Kernel；用户态通常只持有 fd、handle、port、token 或 Framework 对象等引用。
* Linux fd 把进程内小整数映射到 ``struct file``、socket、pipe、device 等 Kernel object；Binder handle 指向 Binder driver 管理的远端对象引用；Mach port 则通过 port right 表达消息能力。
* Kernel object 通常包含类型、状态、权限、引用计数、等待队列与生命周期规则。Process、Thread、File、Socket、Device、Timer、Buffer 都以类似方式被对象化管理。
* 用户态指针不能被 Kernel 直接信任。``copy_from_user``/``copy_to_user`` 或等价路径需要检查地址、长度、页权限和可访问性。
* 权限检查可能跨多层：Framework 预检查、System Service 身份/权限检查、Kernel credential/SELinux/sandbox hook、Driver capability/ownership 检查都可能拒绝请求。
* Android Binder 最终通过 Binder driver 与 ``ioctl`` 等 Kernel 机制承载 transaction、对象引用、线程等待和调用者身份传递。
* Apple 同时存在 BSD syscall 与 Mach trap/IPC；XPC 是更高层服务抽象，底层仍依赖 XNU 的 task、port、message 和 BSD object。
* System Call Boundary 也是性能与可观测性边界：上下文切换、参数复制、阻塞等待、错误码、tracepoint 和 audit 证据都集中在这里。

关键路径
--------

普通文件写入：

::

   App Framework
   → libc / runtime wrapper
   → syscall entry
   → validate fd + user buffer
   → resolve file object
   → VFS / filesystem
   → storage path
   → return bytes or errno

跨进程能力访问：

::

   App proxy
   → Binder / XPC request
   → IPC kernel objects
   → caller identity propagation
   → service-side policy check
   → target kernel / device object
   → result or security failure

概念辨析
--------

* **API 与 syscall**：Framework API 可以是一串用户态逻辑和 IPC；syscall 是真正进入 Kernel 的受控 ABI 入口。
* **fd 与真实资源**：fd 只是当前进程中的引用编号；真正 File/Socket/Device object 由 Kernel 维护。
* **Binder handle 与 fd**：Binder handle 表示 Binder 远端对象引用，fd 表示 Kernel 文件描述符表中的对象引用；二者可在 transaction 中同时传递。
* **Mach port 与普通指针**：port name/port right 是受 Kernel 管理的 IPC 能力，不是用户态可以解引用的对象地址。
* **权限检查与参数校验**：前者回答调用者是否有资格，后者回答输入结构是否安全有效，两者缺一不可。

本章结论
--------

移动 OS 的 Kernel Boundary 可以理解为“用户态引用 + 受控入口 + Kernel object”。分析一次 API 失败时，应沿调用链找到实际 syscall/IPC 入口，确认引用解析到了什么对象，检查身份、权限、参数和对象状态，再用 errno、异常、IPC failure 或 Driver 返回值确定失败层级。