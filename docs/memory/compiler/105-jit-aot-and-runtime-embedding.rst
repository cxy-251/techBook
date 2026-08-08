第105章：JIT, AOT, and Runtime Embedding
=========================================

核心知识点
----------

* Wasm runtime 拿到 module 后，仍需要把其指令变成宿主 CPU 可执行行为。常见策略是 interpretation、JIT compilation、AOT compilation，区别主要在编译成本何时支付。
* Interpreter 直接执行 Wasm 或内部字节码表示，启动快、实现简单，但长期热路径会承担持续 dispatch 开销。
* JIT 在加载期、首次调用或运行时把 Wasm 编译成当前宿主 ISA 的机器码，保留 ``.wasm`` 分发可移植性，同时把编译延迟和编译内存带入运行时。
* AOT 在部署前、安装期或离线阶段生成 runtime/target-specific 本地产物，把编译从请求关键路径移走，但产物会更绑定目标架构、runtime 版本和配置。
* Interpretation、baseline JIT、optimizing JIT 与 AOT 可以组合成 tiered strategy；runtime 不必只选择一种执行方式。
* Runtime embedding 指浏览器、服务器、数据库、游戏引擎、插件系统或应用进程把 Wasm runtime 作为受控执行环境嵌入自身。
* Embedding 的主动作是 ``load bytes → validate/compile module → bind imports → instantiate → call exports → handle trap/resources``。
* Module 与 Instance 必须区分。Module 更接近已验证/编译的可复用代码；Instance 绑定具体 imports，并拥有自己的 memory、table、globals 和其它运行时状态。
* 同一 Module 可以实例化多次，因此编译结果复用和租户/插件状态隔离可以同时实现。
* Startup time 不是单一数字，通常由 download/read、decode、validate、compile、instantiate、initialize 和 first call 多段组成。性能分析应分别计时。
* Code cache 用 module hash、runtime/compiler version、target ISA、CPU features、optimization settings 等作为兼容条件，复用已编译机器码，减少重复 JIT 成本。
* Code cache/AOT 只能消除部分 compilation cost；imports resolution、memory/table initialization、instance creation 和业务初始化仍然存在。
* Host boundary crossing 也有成本。Wasm 调宿主函数或宿主调用 Wasm export，可能涉及参数转换、memory view、reference/handle 映射、权限检查和 runtime bookkeeping。
* 高频细粒度 host calls 可能比纯 Wasm 计算本身更昂贵，因此工程上常通过 batching、共享 linear memory、减少 round trips 等方式降低边界频率。
* Wasm 性能不能只看 instruction throughput；启动策略、code cache、instance lifecycle、host-call frequency、memory strategy 与 runtime policy 共同决定最终表现。
* 选择 interpreter/JIT/AOT 时应围绕 workload：短生命周期与冷代码重启动，长生命周期与热点重峰值性能，受限设备重 runtime 体积和部署可控性。

关键路径
--------

执行策略：

::

   Wasm bytes/module
   → validate
   → choose execution strategy
   → interpreter: execute virtual instructions
   → JIT: compile now to host machine code
   → AOT: load precompiled target artifact
   → execute exports

Embedding：

::

   host application
   → create runtime/engine/store
   → load or compile Module
   → provide imports/capabilities
   → instantiate Instance
   → initialize memory/table/global state
   → call exported function
   → guest may call host imports
   → return/trap

冷启动成本：

::

   read/download
   → decode
   → validate
   → compile or cache lookup
   → resolve imports
   → instantiate state
   → run initialization
   → first useful export call

概念辨析
--------

* **Interpretation 与 JIT**：前者持续解释虚拟指令，后者把程序生成宿主机器码后直接执行。
* **JIT 与 AOT**：两者都生成机器码，主要区别是生成时间点、可获得环境信息和产物可移植性。
* **Module 与 Instance**：Module 是可复用代码/元数据实体，Instance 是绑定 imports 并拥有具体 mutable state 的执行实体。
* **Code cache 与 instance cache**：code cache 复用编译结果，不等于复用某个实例的 memory/global 等运行状态。
* **Wasm execution cost 与 boundary cost**：模块内部计算和宿主跨边界调用是不同性能来源，必须分别测量。

本章结论
--------

Wasm runtime 的稳定模型是 ``Validate/Compile Module → Bind Host → Instantiate State → Execute Across Boundaries``。Interpreter、JIT 与 AOT只是把编译成本放在不同时间点；真正的系统性能还取决于缓存、实例化、宿主调用与生命周期管理，因此 runtime embedding 本质上是在决定“代码何时变快、状态何时创建、边界成本在哪里支付”。