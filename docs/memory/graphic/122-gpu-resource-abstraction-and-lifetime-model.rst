第122章：GPU 资源抽象与生命周期模型
==================================

核心知识点
----------

资源系统的核心不是包装 API Handle，而是建立可追踪 Resource Record
   引擎层 handle 应指向包含类型、desc、owner、backend object、generation、引用、最后使用 frame、release fence 和 debug name 的资源记录。VkImage、ID3D12Resource、MTLTexture 等只是记录中的后端实现。

Handle 与 Backend Object 必须分离
   同一个逻辑 texture 在 Vulkan 中可能对应 image、memory、view，在 D3D12 中对应 resource + descriptors，在 Metal 中对应 texture。上层只持稳定 handle，backend 可自由组织原生对象。

Generation 用来阻止陈旧 Handle 误用
   资源槽位释放后可被复用，旧 handle 的 index 可能仍然相同。加入 generation 后，CPU 侧能在访问前识别 stale handle，而不是把错误留给 GPU 或 debug layer。

所有权应在创建时确定
   PersistentAsset、FrameGraphTransient、ExternalSwapchain、Borrowed/Interop 等 owner 决定谁创建、谁回收、是否允许 alias、device lost 时谁负责重建。

CPU 引用归零不等于 GPU 生命周期结束
   CPU refcount 只能说明主机对象是否仍被系统持有；GPU queue 是否完成必须由 frame fence/timeline 判断。真正释放后端对象需要 Deferred Release Queue。

Resource View 表达“资源在当前 Pass 中怎样被解释”
   同一 SceneColor 可作为 RTV/color attachment、SRV/sampled texture、UAV/storage texture 或某个 mip/layer view。View 独立保存 type、format override、subresource range 和访问语义。

View Cache Key 必须包含资源 Generation
   旧 descriptor/image view 若继续指向已替换的 backend object，会形成隐蔽资源错绑。Key 至少应覆盖 handle+generation、view type、format、mip/layer/aspect 和 device identity。

Shader Binding 应连接 Reflection 与 View
   Shader reflection 给出逻辑资源名、类型、group/binding；资源系统提供相应 view；backend 再生成 descriptor、argument slot 或 bind group。错误画面应能沿 binding name → view → resource record → backend object 反查。

创建 Contract 要覆盖未来访问
   Texture/Buffer/Sampler 创建描述应包含尺寸、format、mip/sample、usage、memory domain、initial state、debug name 和 capability requirement。后续 pass 不应临时补充未声明用途。

能力验证应发生在创建前
   Format 是否可做 render target/storage/sample，sample count 是否支持，buffer usage/size 是否超 limit，都应先查询 device capability。不能创建“部分合法”的资源再让后续绑定失败。

Debug Name 是资源 Contract 的一部分
   ``SceneColor.HDR``、``BloomTemp.Mip0``、``SceneDepth.Main`` 应同步到 backend object、view、descriptor 和 capture marker，使工具中的资源能直接映射到引擎记录。

Transient Pool 通过生命周期区间复用资源
   BloomTemp 等临时资源只在少数 pass 之间存活。若两个资源 desc 兼容且 lifetime 不重叠，可复用同一 allocation，降低每帧创建销毁、内存碎片和显存峰值。

Aliasing 必须由 Hazard Tracker 证明安全
   资源 A 生命周期结束后，其物理内存才能交给资源 B。需要确认最后一次 GPU 使用已完成、必要 alias barrier 已建立、旧 view/descriptor 不再可见。

Upload、Readback 与 GPU-Only 应分 Pool
   Upload 是 CPU 写/GPU 读，readback 是 GPU 写/CPU 读，访问方向和 memory domain 不同。把它们混用会引入 map、cache 和同步错误。

动态资源复用需要五步检查
   Desc 兼容 → lifetime 不重叠 → 上一 GPU fence 已完成 → view/descriptor cache 可失效或复用 → state tracker 从正确初始状态开始。任何一步不成立都不应复用。

Feature Fallback 应返回明确失败类别
   Format unsupported、storage usage unsupported、sample count unsupported、memory budget insufficient、descriptor limit 等应成为结构化原因，而不是统一 ``CreateFailed``。

降级路径应由资源能力反推
   高质量 Bloom 的 RGBA16F storage texture 不支持时，可切 graphics render-target path、换低精度可写格式，或关闭效果。Resource system 提供事实，quality/render feature system 决定策略。

关键路径
--------

资源生命周期：

::

   ResourceDesc
   → capability validation
   → allocate ResourceRecord + generation
   → create backend object
   → create/cache views
   → passes bind/read/write
   → state/hazard tracking
   → CPU references released
   → DeferredReleaseQueue
   → GPU fence complete
   → destroy/recycle backend allocation

Transient 复用：

::

   frame graph computes lifetime
   → resource A last consumer
   → compatible resource B requested
   → verify no lifetime overlap
   → alias/reuse allocation
   → invalidate or rebuild views
   → establish initial state/barrier

错误定位：

::

   wrong resource in frame capture
   → shader binding name
   → resource view
   → handle + generation
   → resource record/owner/desc
   → backend object/descriptor
   → state + fence history

概念辨析
--------

* **Resource Handle 与 Backend Handle**：前者是引擎稳定身份，后者是具体 API 对象。
* **Resource 与 View**：resource 定义存储，view 定义某次绑定对这段存储的解释。
* **Refcount 与 GPU Fence**：refcount 管 CPU 所有权，fence 管 GPU 完成时机；两者共同决定最终释放。
* **Pooling 与 Aliasing**：pooling 复用资源对象/分配，aliasing 允许不同逻辑资源共享同一物理内存，后者需要更严格 hazard 控制。
* **Usage 与 Capability**：usage 是应用意图，capability 是设备是否允许这种意图。
* **Fallback 与 Silent Degradation**：fallback 是显式、可记录的替代路径，静默降级会破坏诊断和画质契约。

本章结论
--------

GPU 资源系统应按“Handle—Resource Record—View—Pass Access—State/Hazard—Fence—Reuse/Release—Fallback”理解。跨 API 稳定性的核心不是把 texture/buffer 包一层类，而是让每个资源都能回答谁拥有、如何被解释、在哪些 pass 使用、GPU 何时结束使用、何时可复用或销毁，以及设备不支持理想契约时走哪条降级路径。