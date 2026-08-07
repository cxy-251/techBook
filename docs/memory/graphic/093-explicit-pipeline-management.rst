第093章：显式 Pipeline 管理
==========================

核心知识点
----------

显式 Pipeline 管理的核心是把 Draw 条件提前固化
   Shader、资源布局、vertex input、render target format、sample count、raster/depth/blend 等状态应在 draw 前整理成可缓存的 pipeline 对象。运行时只绑定已有 pipeline 和少量动态状态，减少临时验证与不确定性。

Pipeline Key 决定是否需要新 PSO
   Key 至少要覆盖 shader variant、pipeline/resource layout、vertex input、color/depth format、attachment count、sample count、raster/depth/blend 与 dynamic-state mask。Key 漏字段会错误复用，字段过多则会导致 pipeline 数量爆炸。

输出合约应优先进入 Pipeline Key
   G-buffer、forward、shadow、post-process 等 pass 的 attachment format、数量、depth/stencil、MSAA 与 fragment output 是最先影响合法性的条件。相同 shader 在不同输出合约下也可能需要不同 pipeline。

Shader Variant 与材质参数要分开
   Skinning、alpha test、velocity output 等会改变 shader 结构或接口，适合进入 variant；roughness 数值、颜色等普通材质数据应留在 buffer/texture。把每个参数都编译成 permutation 会制造组合爆炸。

Pipeline Layout 是 Shader 资源接口的一部分
   Vulkan 的 pipeline layout、Metal 的 argument/resource interface 都必须与 shader 声明一致。资源绑定结构变化时，不能只更新 shader blob 而复用旧 pipeline。

Vulkan Pipeline Cache 与引擎 Pipeline Cache 是两层对象
   ``VkPipelineCache`` 复用驱动内部编译结果；引擎 cache 用稳定 ``PipelineKey → PipelineHandle`` 避免重复创建并记录实际热路径。只有驱动 cache 而没有引擎 key/manifest，仍会在首次请求时发生创建尖峰。

Pipeline Prewarm 应由实际场景驱动
   加载场景、角色、材质和质量档位时收集真实会出现的 key，生成 manifest 并提前创建。不要枚举理论上的全部组合；实际热路径通常只是 permutation 笛卡尔积的一小部分。

磁盘 Cache 必须带兼容性元数据
   Vendor/device、pipeline cache UUID、驱动版本、shader package 版本、pipeline key schema 与平台 profile 任一发生变化，都可能要求分区或失效旧 cache。缓存命中异常先检查兼容条件，而不是默认驱动性能退化。

Dynamic State 用来减少 Pipeline 组合数量
   Viewport、scissor、blend constants、stencil reference 等适合在支持时转为动态状态。某字段是否动态化应基于“组合膨胀是否明显 + API 是否支持 + 实机性能是否稳定”，不能只因功能可用就全部动态化。

动态状态必须在 Command Recording 中完整补齐
   Pipeline 声明某状态为 dynamic 后，draw 前必须调用对应 ``vkCmdSet*`` 或 Metal encoder state。遗漏动态状态会产生 validation error、沿用旧值或输出异常。

Hot Reload 必须保留旧 Pipeline 到安全点
   新 shader/pipeline 创建成功前继续使用旧对象；创建失败则保留旧画面并展示编译错误。旧 pipeline 只有在所有引用它的 in-flight command 完成后才能销毁。

Pipeline Library 适合高复用、组合较多的场景
   将 vertex-input、pre-raster、fragment shader、fragment-output 等部分拆开复用，可以降低部分 runtime 创建成本；若项目 pipeline 数量本来很小，预热和普通 cache 已足够时，引入 library 只会增加复杂度。

Pipeline 错误应分成创建、绑定、输出与性能四类
   创建失败看 API 返回值、shader/layout/format；绑定错误看 command buffer state；输出错误看 attachment、depth/blend 与 shader IO；性能错误看 runtime miss、创建时间、cache 命中率与 GPU pipeline switch。

Fallback 应保持上层 Pass 输出语义
   Pipeline 创建失败时可降到低质量 shader、flat/debug material 或关闭可选效果，但应尽量维持原 pass 的 attachment 与资源语义，让后续 frame graph 不需要因 fallback 重写整条链。

关键路径
--------

Pipeline 请求：

::

   pass output contract
   → shader variant
   → resource/pipeline layout
   → vertex input + fixed state
   → dynamic-state mask
   → normalize PipelineKey
   → engine cache lookup
   → create/prewarm if miss
   → bind pipeline
   → set dynamic state
   → draw

预热：

::

   load scene / material assets
   → collect actually used variants
   → build pipeline manifest
   → load compatible disk cache
   → create pipelines
   → record failures / fallbacks
   → enter interactive frame

Hot Reload：

::

   shader change
   → rebuild shader blob
   → rebuild dependent key/pipeline
   → validation succeeds
   → atomically publish new pipeline
   → retire old pipeline after frame fences

概念辨析
--------

* **Shader Cache 与 Pipeline Cache**：shader cache 复用编译产物，pipeline cache 复用 shader+layout+fixed/output state 的完整组合。
* **VkPipelineCache 与 Engine Cache**：前者由驱动管理内部编译数据，后者由引擎管理稳定 key、句柄和预热集合。
* **Pipeline State 与 Dynamic State**：前者创建时固定，后者录制时设置；dynamic 不是“无状态”。
* **Permutation 与 Pipeline Key**：permutation 只描述 shader 编译变体，pipeline key 还包含 layout、format、sample count 和固定功能状态。
* **Prewarm 与 Runtime Compile**：prewarm 把已知热路径创建成本移到加载阶段，runtime compile 处理真正未预见组合。
* **Fallback 与错误掩盖**：fallback 要保持应用可运行，同时必须保留错误日志和 debug visual，不能让错误静默消失。

本章结论
--------

显式 Pipeline 应按“Output Contract—Shader Variant—Layout—Fixed/Dynamic State—Pipeline Key—Cache/Prewarm—Bind”理解。切场景卡顿先查 runtime pipeline miss 和预热覆盖；画面错误先查 key 是否遗漏 format/layout/state；热重载则必须处理旧 pipeline 的 in-flight 生命周期。稳定系统的关键不是缓存越多越好，而是让每个 pipeline 为什么存在、何时创建、何时复用、何时失效和失败时如何降级都可推导。