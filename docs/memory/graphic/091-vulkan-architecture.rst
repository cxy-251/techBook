第091章：Vulkan 架构
===================

核心知识点
----------

Vulkan 的核心是把 GPU 工作显式化
   应用需要明确创建 instance、device、queue、swapchain、pipeline、command buffer、descriptor 与同步对象，并负责对象生命周期、资源状态、命令录制和提交顺序。驱动不再替应用维持一套大型隐式全局状态。

Instance、Physical Device 与 Logical Device 是三层能力边界
   ``VkInstance`` 是应用接入 Vulkan 的全局入口；``VkPhysicalDevice`` 表示实际 GPU 与能力集合；``VkDevice`` 是应用针对选定 GPU 启用具体 feature、extension 与 queue 后形成的运行契约。后续 buffer、image、pipeline、descriptor、command pool 都属于该 logical device。

Queue Family 决定执行能力与资源所有权边界
   Physical device 可暴露 graphics、compute、transfer、present 等不同 queue family。最小路径可选同一 family 同时承担 graphics/present；多队列系统则必须额外处理 semaphore 与 queue family ownership transfer。

Graphics Pipeline 预组合大量 Draw 状态
   Shader stage、vertex input、primitive topology、rasterization、multisample、depth/stencil、blend、pipeline layout 与 render target contract 会进入 ``VkPipeline``。Viewport、scissor 等启用为 dynamic state 后，可在 command buffer 中单独设置。

Draw Call 只是已准备状态的触发器
   ``vkCmdDraw`` 本身很短，真正决定结果的是之前绑定的 pipeline、descriptor set、vertex/index buffer、dynamic state、attachment 与 image layout。黑屏排查要检查 draw 前的完整命令状态，而不是只看 shader。

Command Buffer 把 CPU 录制与 GPU 执行分开
   Command buffer 具有 initial、recording、executable、pending 等生命周期。CPU 可以提前录制，提交后 GPU 异步执行；pending 状态下不能被 CPU 重置或改写。Frame resource 必须等 fence 完成后再复用。

Command Pool 适合按线程、按帧划分
   Command pool 本身需要外部同步。多线程录制常采用“每 worker 每 frame 一个 pool”，避免多个线程争用同一 pool，并让 command buffer 回收和 frame fence 绑定。

Swapchain 是渲染与窗口呈现的连接点
   Surface capabilities、format、present mode、image count 与 extent 决定 swapchain 配置。Resize、surface lost 或 format 变化需要重建 swapchain 相关 image view/attachment，同时尽量保留 device、pipeline cache 和长期资源。

Acquire、Submit、Present 构成一帧提交闭环
   CPU acquire 可写 swapchain image，录制渲染命令，queue submit 等待 image-available 信号并在完成后产生 render-finished 信号，present 再消费结果。Fence 用来保护 CPU 对 frame slot 的复用。

Validation Layer 是显式 API 的主要错误证据入口
   Vulkan 的错误通常能落到具体 object、usage、layout、stage/access 或 VUID。开发期应开启 validation、debug messenger 和对象命名，把 pass、pipeline、image、descriptor 与 command buffer 映射到可读日志。

Feature 与 Extension 必须按层级启用
   Instance extension 主要连接 surface、debug、portability 等全局能力；device extension 主要扩展具体 GPU 的 swapchain、descriptor indexing、ray tracing、mesh shader、synchronization 等能力。Core version、extension 与 feature bit 应统一收敛到 capability profile。

Vulkan 初始化应先建立能力契约，再建立渲染对象
   稳定顺序是 loader/instance → surface → physical device → queue family → feature/extension query → logical device → swapchain → image views/attachments → pipeline/descriptor → frame resources。这样平台能力错误不会延迟到 draw 阶段才暴露。

关键路径
--------

Vulkan 初始化：

::

   Vulkan loader
   → VkInstance + validation
   → surface
   → enumerate VkPhysicalDevice
   → query features / extensions / queue families
   → choose physical device
   → create VkDevice + VkQueue
   → create swapchain + image views
   → create pipeline / descriptors / frame resources

一帧提交：

::

   wait/recycle frame fence
   → acquire swapchain image
   → reset command pool / buffer
   → record barriers + rendering state
   → bind pipeline / descriptors / buffers
   → draw / dispatch
   → end command buffer
   → queue submit
   → signal render-finished
   → present

黑屏排查：

::

   validation messages
   → swapchain image / extent / format
   → attachment + image layout
   → pipeline + pipeline layout
   → descriptor sets / vertex-index buffers
   → viewport / scissor / dynamic state
   → command buffer lifecycle
   → queue submit / semaphore / present

概念辨析
--------

* **Instance 与 Device**：instance 是应用级 Vulkan 入口，device 是针对某个 physical device 启用具体能力后的运行对象。
* **Physical Device 与 Queue**：physical device 描述硬件能力，queue 是 logical device 暴露的 GPU 执行流。
* **Command Pool 与 Command Buffer**：pool 提供命令存储和分配域，buffer 保存实际录制命令。
* **Pipeline State 与 Dynamic State**：前者固化进 ``VkPipeline``，后者必须在录制时通过 ``vkCmdSet*`` 补齐。
* **Semaphore 与 Fence**：semaphore 主要连接 GPU 执行依赖，fence 主要让 CPU 观察 GPU 完成进度。
* **Extension 与 Feature**：extension 暴露 API 能力入口，feature 决定具体设备功能是否可启用，两者经常需要同时满足。
* **Swapchain Image 与普通 Image**：前者由呈现系统管理并进入 acquire/present 生命周期，后者由应用自行分配和使用。

本章结论
--------

Vulkan 应按“Instance—Physical Device—Logical Device—Queue—Swapchain—Pipeline/Descriptor—Command Buffer—Submit/Present”理解。黑屏先查 swapchain、attachment/layout 和 validation，再查 pipeline、descriptor 与动态状态；卡顿则区分 CPU fence wait、command recording、queue dependency 与真实 GPU pass 成本。Vulkan 的本质不是 API 名称更多，而是每个对象、状态、资源用途和执行依赖都必须由应用明确声明并可追踪。