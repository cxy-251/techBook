第094章：Descriptor Set 与资源
=============================

核心知识点
----------

显式资源绑定的核心是 Shader Resource Table
   Shader 声明逻辑资源坐标，layout 描述每个坐标对应的资源类型、数量和 stage visibility，运行时资源表再把这些逻辑坐标映射到真实 buffer、image view、sampler 或 acceleration structure。资源创建成功并不等于 shader 已正确绑定它。

Vulkan Descriptor Set Layout 是资源接口契约
   ``VkDescriptorSetLayout`` 定义 binding、descriptor type、count 与 shader stage；``VkPipelineLayout`` 再组合多个 set layout 与 push constant range。Shader 的 set/binding 必须完整落在该接口中。

Descriptor Set 保存实际资源访问描述
   Set 从 descriptor pool 分配，经 ``vkUpdateDescriptorSets`` 写入 buffer/image/sampler 等内容，录制时通过 ``vkCmdBindDescriptorSets`` 绑定。它描述“shader 在这个坐标看到哪个资源视图”，不拥有底层 GPU 内存本身。

资源布局应按更新频率分层
   Frame set 保存 camera/time/global history；pass set 保存 lights、shadow、G-buffer；material set 保存材质纹理和参数；object set 保存 transform、skinning、object id。按频率分层能减少无效重绑和 descriptor 更新范围。

低频 Set 更适合保持长期兼容
   Frame/pass 等低频资源放在较稳定的 set 位置，有利于 pipeline layout compatibility 和 pipeline 切换时保留已有绑定；高频 object/material 资源则使用后续 set、dynamic offset、storage buffer index 或 bindless table。

Dynamic Uniform Buffer 是小型 Per-Object 数据的常用路径
   Descriptor 指向大 uniform buffer 的基地址，draw 时通过 dynamic offset 选择对象切片。Offset 必须满足设备 ``minUniformBufferOffsetAlignment`` 等约束；对象数据量大或随机访问多时，storage buffer + index 更合适。

Bindless/Descriptor Indexing 适合大规模材质资源
   大量 texture/SRV 放进 descriptor array，材质只保存索引，可显著减少 per-draw set 切换。代价是 feature 依赖、数组大小、未绑定项、residency、越界和 non-uniform index 都必须显式管理。

Metal 的资源绑定对象不同，但抽象职责相同
   常规 Metal 通过 encoder 的 ``set*Buffer``、``set*Texture``、``set*SamplerState`` 直接绑定参数；argument buffer 可把一组资源编码成资源表。跨 API 引擎应统一建模 Frame/Pass/Material/Object Resource Table，再映射到 Vulkan set 或 Metal argument table。

Argument Buffer 适合降低大量 Encoder Binding 调用
   小型 renderer 直接逐资源绑定更简单；材质规模、bindless 访问或 GPU-driven 渲染增长后，argument buffer 能把多个资源和索引打包。它仍需要正确的结构布局、alignment、residency 和多帧生命周期。

Descriptor 生命周期必须跟 GPU Frame Timeline 对齐
   GPU 仍在读取某个 descriptor set、argument buffer 或 uniform slice 时，CPU 不能覆盖它。多帧并行通常准备 N 套 frame-level mutable resources，slot 只有在对应 fence/command completion 到达后才能重用。

偶发错材质通常优先查资源表复用
   贴图随机串台、上一帧 transform、极少数 draw 错资源，高概率来自 descriptor set/argument buffer 被提前覆盖、dynamic offset 算错、material index 越界或 frame slot 复用过早。

资源热更新应使用版本和延迟释放
   新 texture 上传完成并可读后，material table 才切换到新 descriptor/version；旧 descriptor 与旧资源进入 retire queue，等待所有可能引用它的 frame 完成后再释放。

Descriptor Pool、GPU Memory 与 Staging Allocation 是不同分配问题
   Descriptor pool 管 descriptor 数量；GPU allocator 管 buffer/image memory；staging allocator 管 CPU→GPU 上传；frame allocator 管短生命周期切片。它们的回收证据和碎片化策略不能混为同一个 allocator。

资源分配策略应服务访问模式
   长期材质 set 使用长期 pool；per-frame 临时 set 使用 transient pool；高频 object 数据优先 ring/storage buffer；静态 texture/buffer 放 device-local/private memory；上传走 staging/shared 路径。优化目标是减少每 draw 更新和同步等待。

关键路径
--------

Vulkan 资源绑定：

::

   shader set/binding declaration
   → descriptor set layout
   → pipeline layout
   → allocate descriptor set from pool
   → write buffer/image/sampler descriptors
   → bind set in command buffer
   → optional dynamic offset / index
   → draw / dispatch
   → shader resource access

多帧动态资源：

::

   select frame slot
   → verify slot fence completed
   → update frame/pass buffer slices
   → update mutable descriptor/argument region
   → record command buffer
   → submit
   → keep resources immutable while in flight
   → retire/reuse after completion

材质热更新：

::

   upload new texture
   → wait/observe upload completion
   → create view / descriptor
   → publish new material resource version
   → future frames bind new version
   → old version enters retire queue
   → free after all referencing frames finish

概念辨析
--------

* **Resource 与 Descriptor**：resource 是真实 GPU 数据，descriptor 是 shader 如何解释和访问该数据的视图。
* **Set Layout 与 Descriptor Set**：layout 定义接口形状，set 保存某次绑定的实际资源内容。
* **Pipeline Layout 与 Resource Table**：pipeline layout 定义 shader 可见资源表结构，resource table 是运行时当前绑定内容。
* **Dynamic Offset 与 Bindless Index**：前者在同一 buffer 中选择地址切片，后者在大资源表中选择 descriptor。
* **Descriptor Pool 与 Memory Allocator**：一个分配 descriptor 对象，一个分配 buffer/image 内存。
* **Vulkan Descriptor Set 与 Metal Argument Buffer**：对象形式不同，但都可承担“批量 shader 资源表”的职责。
* **Resource Lifetime 与 Descriptor Lifetime**：底层资源和引用它的 descriptor/argument entry 都必须分别保证不被 in-flight GPU 使用时释放或覆盖。

本章结论
--------

资源绑定应按“Shader Declaration—Layout—Resource Table—Bind—GPU Access”理解，并用 frame/pass/material/object 的更新频率组织布局。随机错材质先查 frame slot、descriptor/argument table 覆盖和索引；CPU 提交高则把 descriptor 更新移到资源变化时，draw 阶段只保留绑定、offset 或索引。稳定系统的关键，是让资源接口、实际绑定、内存生命周期和 GPU 完成证据处在同一套资源时间线上。