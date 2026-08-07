第121章：Shader 抽象模型
=======================

核心知识点
----------

Shader 抽象层位于“源码语义”与“后端对象”之间
   源码语义包括 source、entry、stage、resource、binding、variant、capability 和 diagnostic；后端对象包括 SPIR-V、DXIL、MSL function、WGSL module 及对应 pipeline layout。抽象层保存前者并生成后者。

统一 Shader 架构首先解决所有权
   Shader 作者声明逻辑接口；编译器生成真实 binary 与 reflection；binding generator 根据 reflection 生成 pipeline layout；backend 创建 native shader/pipeline 对象。任何一层都不应靠手写索引修补上一层缺失的信息。

Reflection 是编译后的事实证据
   Manifest 表达作者意图，reflection 表达最终产物中实际存在的 entry、resource、location、binding、push/constant、workgroup size 等。两者不一致时，应在构建阶段失败，而不是等到 draw 时出现黑材质。

资源 Binding 应先逻辑分组，再映射后端地址
   Frame、material、object、pass 等 logical group 可分别映射到 Vulkan descriptor set、D3D space/table、WebGPU bind group、Metal argument buffer/index。材质系统只面对逻辑资源名和组。

Variant 条件应与 Resource Contract 绑定
   ``USE_NORMAL_MAP=1`` 时才要求 NormalTexture；基础 Camera/Material buffer 则所有 variant 都必须存在。编译器优化掉未使用资源时，抽象层才能区分“合法裁剪”和“接口丢失”。

跨语言兼容应比较稳定字段
   HLSL、GLSL、WGSL、MSL、SPIR-V 语法不同，但 entry、stage、resource address、stage IO、layout、feature gate、reflection 都可放进统一 compatibility contract。

Capability Mask 决定哪些 Variant 可生成
   Subgroup、16-bit、storage texture format、ray tracing、mesh shader、sample type 等能力应在编译前过滤。缺能力时选择 fallback shader 或剔除 variant，而不是让运行时 pipeline creation 随机失败。

统一架构应分成五层
   Authoring 层描述材质/compute/post 语义；Compile 层处理 include、宏、target、IR；Reflection 层保存真实接口；Binding 层生成 layout；Runtime 层创建 shader module、pipeline、resource binding 并负责 warmup。

Debug Identity 必须跨后端保持一致
   一个 shader 在 Vulkan、D3D、Metal、WebGPU 中可能对应完全不同 binary，但都应能反查到 ``LitSurface/PSMain/USE_NORMAL_MAP=1`` 这样的统一 identity。Cache key、pipeline debug name、reflection 和 capture label 应共享这组字段。

Compile Cache Key 必须覆盖所有产物输入
   Source/include hash、entry、stage、compiler/version、args、target profile、backend、feature mask、variant values、layout schema、render state 等只要会改变 binary，就必须进入 key。字段缺失会错误复用，字段过多会降低命中率。

Variant Stripping 要基于真实使用和能力
   大量 feature 组合会指数增长。构建系统应根据材质资产、质量档位、平台 profile、render path 和 feature dependency 删除永远不会使用的组合，而不是把所有 permutation 都带到运行时。

Warmup 解决第一帧/首次出现 Hitch
   常用 shader/pipeline 应在关卡加载、场景切换或后台阶段提前编译和创建。Runtime 临时遇到 cache miss 时应有可观察 marker，并能选择 fallback，避免在主 frame 同步阻塞。

负结果也值得缓存
   某个 variant 因 capability、编译错误或 layout 冲突失败时，可保存失败 key 和诊断，避免重复构建。Source/compiler/schema 变化时再失效。

Fallback 必须显式进入 Render Path
   Material shader 缺失可用 error shader；compute culling 缺失可回退 CPU；post effect 缺失可跳过。Fallback 应写入 diagnostics 和 frame statistics，而不是静默改变画面。

Shader Library 应按 Pass 语义组织
   MaterialLibrary 关注 vertex/material/fragment；ComputeLibrary 关注 storage、workgroup、dispatch 与 barrier；PostEffectLibrary 关注 input/history/output format 和全屏/tile pass。三者共享统一 source/reflection/binding/variant 基础设施。

关键路径
--------

Shader 构建：

::

   source + manifest
   → entry/stage/resources/features
   → compiler frontend
   → backend binary / IR
   → reflection
   → validate source contract
   → generate binding/pipeline layout
   → cache artifact
   → runtime shader/pipeline object

Variant Chain：

::

   material/render feature set
   → platform capability mask
   → generate candidate variants
   → strip impossible/unused variants
   → compile/cache
   → warmup common pipelines
   → runtime fallback on miss/failure

跨 API 调试：

::

   black/wrong material
   → shader identity + variant key
   → entry/stage
   → reflection resources
   → binding layout
   → backend descriptor/bind group
   → capability/format
   → pipeline capture

概念辨析
--------

* **Manifest 与 Reflection**：manifest 是作者声明，reflection 是编译产物事实；应互相校验。
* **Logical Binding 与 Backend Binding**：逻辑分组属于引擎语义，set/space/group/index 是具体后端地址。
* **Variant 与 Runtime Parameter**：variant 改变编译/pipeline 结构，普通材质数值应留在 buffer/texture 数据中。
* **Compile Cache 与 Pipeline Cache**：前者缓存 shader 编译产物，后者缓存 shader + fixed state + layout 等形成的 pipeline 对象。
* **Stripping 与 Fallback**：stripping 删除不会使用的组合，fallback 处理运行时能力不足或产物缺失。
* **Shader Library 与 Shader Language**：library 按渲染职责组织，语言只是源码/后端实现选择。

本章结论
--------

Shader 抽象应按“Source Contract—Compiler—Reflection—Binding—Variant—Cache/Warmup—Backend Object—Diagnostic”理解。跨 API 的核心不是强迫所有平台共享同一种源码语法，而是让 entry、资源、绑定、变体和能力在不同语言与后端中拥有同一份可验证语义。只要 reflection、cache key、pipeline layout 和 debug identity 可追踪，Shader 系统才能真正跨平台稳定演进。