第088章：Direct3D 资源绑定模型
============================

核心知识点
----------

Descriptor 是 Shader 访问 Resource 的最小解释单元
   Resource 保存 GPU 内存，descriptor 描述访问类型、格式、子资源范围和用途。CBV 用于常量读取，SRV 用于只读资源，UAV 用于读写资源，sampler 描述采样规则。Resource 存在不等于 shader 已经通过正确 descriptor 访问它。

Descriptor Heap 是连续 Descriptor 存储
   D3D12 常用 shader-visible CBV/SRV/UAV heap 和 sampler heap。RTV/DSV 走独立输出绑定路径。大型材质系统通常让长期资源驻留在全局 shader-visible heap，临时资源使用 per-frame dynamic region。

Root Signature 是 Shader Binding Contract
   Root signature 定义 root constants、root descriptor、descriptor table 与 static sampler，并把这些 root parameter 映射到 HLSL register/space。PSO、shader reflection 和 runtime binding 都应使用同一套 schema。

资源绑定路径可以固定为一条链
   ``resource → descriptor → descriptor heap → descriptor table/root descriptor → root parameter → HLSL register``。错纹理或空 buffer 的排查应沿这条链逐层确认，不要跳过 descriptor 与 heap 生命周期。

Root Signature 空间有限，应放高频小数据与表入口
   Descriptor table 只消耗少量 root 空间，root descriptor 和 root constants 更直接但 root argument 成本更高。大量材质纹理应留在 descriptor heap/table，per-draw object constants 才适合 root CBV 或 root constants。

绑定布局应优先按更新频率划分
   Per-frame 包含 camera/global history；per-pass 包含 light list、shadow atlas、G-buffer；per-material 包含贴图与材质参数；per-object 包含 transform、object id。变化频率决定 CPU 绑定次数、descriptor 生命周期和覆盖风险。

Bindless 是“大量低频资源 + Shader Index”的访问模型
   大量 texture/SRV 放入统一 descriptor array，material 只保存 index。它能减少 per-draw binding，但需要 hardware binding tier、Shader Model、descriptor indexing 与非一致索引支持，并要求严格的 index、residency 与越界管理。

Root Descriptor 适合高频 Buffer，不适合大量 Texture
   Root CBV/SRV/UAV 直接放 GPU virtual address，适合 per-object constants 或少量 buffer。Texture 与大型数组更适合 descriptor table。

Static Sampler 适合少量稳定采样状态
   Linear wrap、linear clamp、shadow comparison 等长期固定状态可以进入 root signature；材质需要动态 anisotropy、LOD bias 或 address mode 时仍应使用 sampler descriptor heap。

Register Space 应成为跨 Shader 的长期 ABI
   可以按 ``space0=frame/pass``、``space1=material/bindless``、``space2=object`` 组织资源。这样 shader reflection、root signature、材质编译与 Vulkan backend 都能共享同一引擎级绑定 schema。

Descriptor 生命周期必须与 Frame Fence 对齐
   正在被 GPU 使用的 descriptor 区间、upload buffer slice 与 transient resource 不能被 CPU 提前覆盖。常见方案是每个 in-flight frame 使用独立 dynamic descriptor region 与 upload ring，fence 完成后再回收。

UAV 写后读需要同步与状态转换
   Compute 以 UAV 写入 particle/light buffer，graphics 随后以 SRV 读取时，需要 UAV barrier 或适当 transition，并确保跨 queue 时有 fence/queue wait。Descriptor 正确而 barrier 错误，仍会读到旧数据或未定义结果。

Descriptor Recycling 是随机错材质的高频根因
   偶发采样到别的材质，优先检查 dynamic region 是否在 GPU 完成前被回收、material index 是否越界、heap offset 是否与 shader index 对齐，而不是先修改 shader。

D3D12 与 Vulkan 应在“引擎 Binding Schema”层互通
   D3D12 root signature/table/heap 可映射到 Vulkan pipeline layout/descriptor set layout/descriptor set/pool。不要做 API 对象一一复制，应保持 frame/pass/material/object 的频率分组、资源类型和 shader register 语义一致。

关键路径
--------

Shader 资源绑定：

::

   GPU resource
   → create CBV / SRV / UAV descriptor
   → allocate heap slot
   → build descriptor table
   → root signature parameter
   → SetGraphics/ComputeRootDescriptorTable
   → HLSL register + space
   → shader access

动态 Descriptor：

::

   select frame index
   → allocate per-frame heap region
   → copy/create descriptors
   → record root table handles
   → submit command list
   → signal frame fence
   → keep region immutable while in flight
   → recycle after fence completion

Compute → Graphics：

::

   UAV descriptor
   → compute dispatch writes resource
   → UAV / transition barrier
   → optional queue fence/wait
   → SRV descriptor
   → graphics root table
   → shader read

概念辨析
--------

* **Resource 与 Descriptor**：resource 是数据存储，descriptor 是 shader 如何解释和访问该数据。
* **Heap 与 Table**：heap 保存 descriptor，table 只是指向 heap 某段连续范围的绑定入口。
* **Root Descriptor 与 Descriptor Table**：前者直接绑定 buffer 地址，后者间接绑定一组 descriptor。
* **Static Sampler 与 Sampler Heap**：前者固化进 root signature，后者允许运行时动态切换采样状态。
* **Bindless 与 Material Table**：bindless 用大数组+索引减少重绑，material table 为每个材质绑定有限资源集合。
* **Descriptor Lifetime 与 Resource Lifetime**：descriptor slot 可复用时间和底层 resource 可释放时间是两个独立生命周期，都需要 fence 证明。
* **D3D12 Root Signature 与 Vulkan Pipeline Layout**：二者都是 shader 资源接口契约，但对象切分与运行时分配方式不同。

本章结论
--------

D3D12 资源绑定应按“Resource—Descriptor—Heap—Table/Root—Register”理解，并用 frame/pass/material/object 的更新频率组织布局。偶发错材质先查 descriptor recycling 与 index，compute 结果为空先查 UAV/barrier/queue dependency，常量落后一帧先查 upload ring 与 frame fence。稳定绑定系统的关键，是让 shader schema、descriptor 分配、资源状态和 GPU 生命周期处在同一条可验证 timeline 上。