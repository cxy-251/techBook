第083章：OpenGL 状态管理与 Context
================================

核心知识点
----------

大型 OpenGL 工程的核心问题是隐式状态所有权
   一次 draw 会读取 current context 的 program、VAO、texture、FBO、viewport、depth/blend/cull 等状态。代码规模变大后，必须明确“谁写状态、谁持有 context、谁负责恢复”，否则状态污染会跨 pass、窗口和线程传播。

Current Context 是线程局部执行环境
   GL 命令作用于当前线程 current 的 context；同一 context 同一时刻只能由一个线程持有。主渲染线程、预览窗口线程和上传线程若各自执行 GL 命令，应有清晰固定的 context ownership。

Binding Point 与 Object State 要分开理解
   Binding point 表示当前 context 的槽位，例如 UBO binding、texture unit、framebuffer；object state 表示 texture、buffer、VAO 等对象内部保存的数据和参数。Direct State Access 可以直接修改对象，减少为了“编辑对象”而临时污染 context binding。

Enable Flag 属于 Context 全局状态
   Depth、blend、cull、scissor、multisample 等开关不会自动随材质或 mesh 切换。Pass 入口应完整声明所需 flag，而不是依赖上一 draw 的残留状态。

State Cache 是应用侧对 OpenGL 隐式状态的镜像
   Cache 记录当前 program、VAO、FBO、textures、samplers 和开关，跳过重复提交。它只有在所有 GL 状态修改都经过统一 wrapper 时才可靠；任何裸 ``glBind*`` 绕过 backend 都会让 cache 与真实 context 分裂。

Dirty Bit 用来减少派生状态重算
   Pass、material、mesh、resource 各自维护变化标志，只在对应层变化时重新绑定或派生状态。稳定提交顺序通常是 pass state → material state → mesh state → draw。

每个 Context 都应拥有自己的 State Cache
   多窗口应用在同一线程切换不同 context 时，不能沿用线程全局 cache。Viewport、FBO、VAO 和 enable flag 都属于 context 状态，切换后必须使用对应 context 的 cache 和 pass 初始化路径。

Share Group 只共享部分 GPU 对象
   多 context 可以共享 texture、buffer、shader/program 等资源，但 VAO、FBO、query 等容器对象通常应视为 context-local。共享存储与本地 view/configuration 要分开建模。

后台 Upload Context 适合资源准备，不适合分散主渲染命令流
   上传线程可以解码并创建/更新共享 texture、buffer，主渲染线程保持主 context 的稳定 draw 提交。多个 context 同时提交大量细碎命令可能被 driver 串行化，反而增加锁竞争和调试复杂度。

跨 Context 可见性必须使用同步证据
   上传线程完成 texture/buffer 更新后应插入 ``GLsync`` fence 并 flush；渲染线程在资源进入可用表之前确认 fence signal，必要时使用 client wait 或 GPU-side wait。不能假设“另一个线程函数返回了，所以主 context 已经可见”。

CPU Wait 与 GPU Wait 语义不同
   ``glClientWaitSync`` 让 CPU 查询/等待 fence；``glWaitSync`` 把等待加入 GPU 命令流。资源加载路径应尽量非阻塞检查，避免在主帧中直接等待慢上传。

多 Context 生命周期必须有统一资源所有权
   主 context 先创建，其他 context 加入 share group；窗口关闭时先停止对应线程命令，释放 context-local 对象，再销毁 context；共享资源由统一 resource manager 在最后引用释放时删除。

大型应用应尽量把 OpenGL Context 隐藏在 Backend
   上层使用 RenderDevice、RenderContext、CommandEncoder、GpuResource 等显式抽象，OpenGL backend 再翻译成 current context、state cache 和 GL object。这样可以把隐式状态限制在底层，也更容易迁移到 Vulkan/Metal/WebGPU。

关键路径
--------

主渲染 Context：

::

   render thread
   → make main context current
   → context-local state cache
   → pass state
   → material / geometry / resources
   → draw
   → swap

共享上传：

::

   CPU decode
   → upload thread + shared context
   → create/update shared texture or buffer
   → glFenceSync
   → glFlush
   → resource state = Uploading
   → render thread checks / waits fence
   → resource state = Resident
   → draw consumes resource

多 Context 排查：

::

   thread owns current context?
   → correct share group?
   → object type shareable?
   → upload commands flushed?
   → correct fence waited?
   → correct context-local VAO/FBO/cache?
   → resource lifetime still valid?

概念辨析
--------

* **Thread 与 Context**：线程只是执行者，真正决定 GL 状态的是当前 context；同一线程可切 context，但风险高。
* **Shared Object 与 Context-Local Object**：texture/buffer 等可共享存储，VAO/FBO 等状态容器通常应按 context 单独创建。
* **State Cache 与 Driver State**：cache 是应用侧镜像，真实权威仍是 OpenGL context；绕过 cache 会造成二者失配。
* **DSA 与 Binding**：DSA 减少“绑定后修改对象”的临时状态，不会消除 draw 时的绑定状态。
* **CPU Wait 与 GPU Wait**：前者阻塞或查询 CPU，后者只约束后续 GPU 命令顺序。
* **Upload Context 与 Render Context**：前者优化资源准备，后者负责主 draw 提交；二者通过共享对象和同步连接。
* **多 Context 与多 GPU 并行**：创建多个 context 不意味着 GPU 自动并行，driver 仍可能串行化命令和共享资源访问。

本章结论
--------

OpenGL 状态管理应按“线程—Current Context—Binding/Global State—Object—Draw”理解，多 context 则再加入“Share Group—Sync—Context-Local State”边界。状态 cache、dirty bit 和 DSA 解决的是可维护性与冗余提交；shared upload context 解决的是资源准备吞吐；fence 解决的是跨 context 可见性。大型应用最重要的不是创建更多 context，而是让每个 context 的线程所有权、共享对象范围、状态缓存和资源生命周期都能被明确追踪。