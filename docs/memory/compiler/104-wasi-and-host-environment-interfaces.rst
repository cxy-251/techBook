第104章：WASI and Host Environment Interfaces
===============================================

核心知识点
----------

* WebAssembly 核心规范定义可执行代码、内存、类型和模块机制，但不直接定义完整文件系统、网络、时钟、随机数、环境变量等操作系统能力。
* WASI（WebAssembly System Interface）承担 browser 外 Wasm 程序的标准宿主接口层，让多语言程序能以更可移植的方式请求系统能力。
* 一个源语言调用通常经历 ``language library → WASI binding → Wasm import → runtime resolver → host resource``，外部能力在每一层被重新表示。
* WASI 更适合被理解为一组 standards-track API family，而不是一张固定 syscall table。文件、clock、random、CLI、socket、HTTP 等能力可以分散在不同接口包中独立演进。
* WASI 与 Wasm 的职责不同：Wasm 定义模块如何计算，WASI 定义模块如何以标准方式请求宿主能力。
* Core module 与 Component Model 是不同组合层级。传统 Preview 1 更偏 core-module imports；后续接口体系更多围绕 WIT、world、component 和 typed interface composition 展开。
* WIT（WebAssembly Interface Types）用于描述跨组件/宿主边界的结构化类型与接口；world 可以同时声明组件需要的 imports 和提供的 exports。
* Capability-oriented access 的核心是“宿主显式授予资源”。程序不会因为知道某个路径或 API 名字就自动获得权限，而是要拿到宿主提供的目录、socket、stream 或其它能力句柄。
* Capability 模型使同一个 Wasm 组件可以在不同宿主上绑定真实文件系统、虚拟文件系统、内存资源、代理服务或测试实现。
* 编译成功不代表运行环境已经满足。最终可执行性还取决于 runtime 支持的 WASI/component 版本、接口实现范围和部署时授权。
* Import-resolution failure、interface-version mismatch、capability denial 和程序内部 I/O error 是不同故障层级，排查时必须分开。
* WASI 的可移植性仍是“接口合同层可移植”。宿主是否实现某接口、是否允许某资源，以及行为的部署策略仍由具体 runtime/host 决定。
* 安全边界应从 interface/world、runtime linker 和启动配置中读取，而不是只从源码中猜程序拥有的权限。
* 对 compiler engineer 来说，WASI 的意义是把“系统调用依赖”从目标 OS 私有 ABI 提升成可以被编译器、runtime 和宿主共同理解的标准接口契约。

关键路径
--------

系统能力调用：

::

   source-level file/clock/network call
   → language runtime / standard library
   → WASI binding / generated interface call
   → Wasm import or component import
   → runtime resolves interface
   → host-provided capability
   → OS / virtual resource
   → result returned across boundary

组件接口：

::

   WIT interfaces
   → compose into world
   → component declares imports/exports
   → runtime/host satisfies imports
   → instantiate component
   → typed calls cross component boundary

权限判断：

::

   program requests resource
   → is interface supported?
   → is concrete capability granted?
   → is requested resource inside granted scope?
   → yes: perform operation
   → no: capability/host error

概念辨析
--------

* **Wasm core 与 WASI**：前者定义执行机器与 module，后者定义标准宿主能力接口。
* **WASI 与 POSIX**：WASI 不是简单复制传统进程 syscall 模型，而更强调可移植接口和显式资源能力。
* **Interface 与 capability**：interface 说明“能调用什么操作”，capability 决定“当前实例实际被授予哪些资源”。
* **Core module 与 component**：core module 侧重低层 Wasm imports/exports，component 侧重更高层 typed interface composition。
* **Compile target support 与 runtime permission**：编译器能生成 WASI 调用，不代表部署环境一定实现或授权这些调用。

本章结论
--------

WASI 的稳定模型是 ``Wasm Computation + Standard Host Interfaces + Explicit Capabilities``。它把文件、时钟、随机数、网络等宿主需求从平台私有调用提升为可描述、可组合、可授权的接口边界；真正判断程序能否运行，要同时检查接口版本、runtime 实现和宿主授予的资源。