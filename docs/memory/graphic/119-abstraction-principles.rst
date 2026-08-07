第119章：抽象原则
================

核心知识点
----------

跨 API 抽象层首先抽象“渲染语义”，不是 API 函数名
   上层关心 device capability、resource、pipeline、command、binding、barrier 与 present；Vulkan、Direct3D、Metal、OpenGL、WebGPU 的原生对象和调用方式留在 backend。稳定接口必须能描述 GPU 真正需要的状态和资源关系。

抽象层应服务一帧的可移植执行
   一个离屏颜色 pass 再采样到 swapchain 的最小 frame 已包含 resource usage、pipeline format、descriptor/binding、状态转换和 present。若这条链在不同 backend 上不能得到等价执行，抽象边界就不成立。

职责边界可压缩为五类核心契约
   Device 契约描述 feature、limit、format 和 queue；Resource 契约描述尺寸、格式、usage、memory domain 与 lifetime；Pipeline 契约描述 shader、layout、render state 和 attachment format；Command 契约描述 pass/draw/dispatch/copy；Sync 契约描述访问顺序、状态迁移和 queue ownership。

上层表达“需要什么”，Backend 表达“如何执行”
   上层 texture 只需说明 ``renderTarget + sampled`` 等用途；Vulkan backend 再生成 image/layout，D3D12 backend 生成 resource state，Metal backend 使用 texture usage/encoder 语义，WebGPU backend 按 usage 与 validation 规则执行。

抽象设计应从最严格 Backend 反推
   显式 API 对 usage、layout、barrier、descriptor 和 lifetime 的要求更严格。先保留这些显式语义，再由 OpenGL 等隐式后端内部补状态跟踪，能让错误更早暴露，也让 frame graph 获得一致依赖信息。

Binding 抽象要统一语义而非统一名字
   Vulkan descriptor set、D3D root descriptor/table、Metal argument buffer、WebGPU bind group、OpenGL texture unit 都在解决“shader 如何看到资源”。抽象层应保存 resource type、logical group、binding、visibility、array count 和 dynamic offset 等共同语义。

状态转换必须留在抽象层
   ``RenderTargetWrite → ShaderRead`` 这样的资源边应是上层可见事实。即使某个 backend 可以隐式处理，也不能把这条依赖彻底隐藏，否则 Render Graph 无法推导 barrier，工具也无法解释 producer/consumer 错误。

Capability Profile 应集中表达平台差异
   Texture format、sample count、compute、bindless、timestamp、mesh shader、ray tracing、storage texture 等能力应在启动时归一化成 profile。功能层按 profile 选择路径，而不是在 draw loop 里散落 backend 判断。

失败语义也是抽象契约的一部分
   Usage 不合法、format 不支持、binding layout 不匹配、pipeline format 冲突、资源仍在 GPU 使用等问题应转成统一错误结构，并保留 backend 原始消息。错误必须能定位到 pass、resource、pipeline、frame 和调用上下文。

生命周期必须包住原生句柄
   抽象 handle 需要创建、引用、延迟释放、frame fence 和 generation 规则。CPU 引用归零不等于 GPU 已完成；swapchain resize、transient resource aliasing 和 descriptor cache 都依赖一致的生命周期模型。

便利接口不能替代底层 RHI 粒度
   ``drawMesh(mesh, material)`` 可存在于高层，但底层仍需保留 bind pipeline、bind resources、set buffers、draw/dispatch 等接近 GPU 执行的操作。越靠近 RHI，接口越需要精确表达状态和资源。

抽象成本必须可测量
   Resource lookup、pipeline lookup、descriptor allocation、validation、barrier planning 和 backend translation 都消耗 CPU。大量 draw 下应缓存 pipeline/resource set、使用稳定 handle、批量命令并减少动态分配。

通用性不应抹平平台特性
   Ray tracing、mesh shader、tile memory、argument buffer、descriptor indexing 等能力应通过 extension/capability 进入上层，而不是为了“统一”被永久隐藏。统一核心与受控扩展应同时存在。

比较跨 API 框架时应看边界而非品牌
   bgfx 更偏可嵌入 API-agnostic renderer；Dawn/wgpu 更偏 WebGPU 对象与安全模型；大型引擎 RHI 往往与 render graph、shader pipeline、resource lifetime 和平台扩展深度集成。选型要看它与自身 frame 架构是否匹配。

关键路径
--------

跨 API Frame：

::

   frame graph
   → device capability/profile
   → resource descriptions/usages
   → pipeline + binding layouts
   → command recording
   → logical resource transitions
   → backend mapping
   → queue submit
   → present

资源映射：

::

   abstract TextureDesc
   → validate format/usage
   → backend resource object
   → abstract view/binding
   → backend descriptor/slot
   → pass access
   → state transition
   → deferred release

性能检查：

::

   fixed test frame
   → CPU submit baseline
   → pipeline/resource-set cache hits
   → descriptor allocations
   → barrier count
   → backend state changes
   → GPU frame time
   → compare abstraction overhead vs render cost

概念辨析
--------

* **RHI 与 Backend**：RHI 定义统一渲染语义，backend 把这些语义映射到具体 API。
* **抽象对象 与 原生对象**：抽象 handle 是引擎稳定身份，VkImage/ID3D12Resource/MTLTexture 等是具体实现对象。
* **Resource Usage 与 Resource State**：usage 描述资源生命周期中允许的角色，state 描述当前访问阶段的具体语义。
* **Binding Group 与 API Descriptor**：前者是逻辑资源集合，后者是各 API 的实际绑定实现。
* **通用核心 与 平台扩展**：通用核心保证可移植正确性，扩展负责暴露高端能力，两者不是互斥关系。
* **抽象成本 与 GPU 算法成本**：抽象成本多落在 CPU 组织/提交，算法成本多落在 GPU pass；必须分别测量。

本章结论
--------

跨 API 抽象应按“Capability—Resource—Pipeline—Binding—Command—Synchronization—Backend—Evidence”理解。稳定抽象不是把底层细节全部藏掉，而是保留所有 backend 都必须遵守的资源、状态、生命周期和失败语义，再把平台差异集中到有限映射点。只有当同一 frame 在不同 API 上能被等价执行、诊断和测量，抽象层才真正成立。