第021章：Shader Model 演进
=========================

核心知识点
----------

Shader Model 本质是 GPU 可编程能力合同
   它规定 shader 可使用哪些 stage、资源类型、执行粒度、编译目标与指令能力。源码只能请求能力，编译器、API feature 查询、pipeline 创建和驱动共同决定这些能力能否真正执行。

版本号不能替代具体 capability
   Direct3D 的 SM4、SM5、SM6 描述不同语言和编译能力，但 ray tracing、mesh shader、VRS、barycentric、native 16-bit 等能力仍需查询对应 feature。工程上应按功能逐项判断，而不是用“支持 SM6”作为所有现代特性的总开关。

可编程管线把视觉控制权交给 shader
   固定函数时代由 API 状态完成变换、光照和纹理组合；现代管线把顶点变换、材质、光照、采样、通用计算甚至部分几何生成交给 shader。表达能力增强的同时，资源布局、变体、性能和 fallback 的责任转移到引擎。

Shader 能力要从四个维度描述
   Stage 说明代码运行在哪个阶段；resource model 说明能访问哪些 buffer、texture、sampler 或 acceleration structure；execution granularity 说明单 invocation、wave/subgroup 或 threadgroup 能否协作；compile target 说明 HLSL profile、SPIR-V capability、MSL/GLSL 版本等编译边界。

SM4、SM5、SM6 对应不同的工程能力层次
   SM4 建立更统一的 common-shader core；SM5 扩展 compute、tessellation、structured buffer 和更广的 GPU 数据处理；SM6 进入 DXIL/DXC 体系并把 wave-level 操作暴露给 HLSL。版本越高，重点越从单线程 shader 扩展到显式并行协作与现代 GPU-driven 能力。

跨 API 要建立 capability profile
   Vulkan 通过 physical device feature、extension、limit、format 和 SPIR-V capability 描述能力；Metal 通过 Metal version、GPU family 和 feature table；OpenGL 通过 context/GLSL version、extension 和 implementation limit。上层系统应抽象成 ClassicPBR、WaveOptimizedPBR、ComputeLightCulling、RayQueryShadow 等能力组合。

资源与性能模型随可编程化而变化
   固定函数主要受状态组合和 pass 数限制；shader 化后，ALU、texture fetch、register pressure、branch divergence、wave occupancy、shared memory 和同步进入性能模型。视觉功能和硬件执行之间的关系更直接，也更需要 profiler 证据。

能力缺失必须有明确降级路径
   Wave reduction 可以退回普通 shared-memory reduction，ray query 阴影可以退回 shadow map，mesh shader 可以退回传统 vertex/index 或 compute indirect 路径。Fallback 应在 pipeline 创建前决定，不能等运行时失败后临时猜测。

关键路径
--------

从视觉需求到可执行 shader：

::

   视觉目标
   → 拆成 shader 行为
   → 确定 stage、resource、execution granularity
   → 选择编译 target/profile
   → 查询 API feature、extension 与 limit
   → 生成 capability profile
   → 编译 shader module
   → 创建 pipeline
   → GPU 执行
   → 用 frame capture 验证实际路径

跨平台功能选择：

::

   列出 normal map、wave op、compute、ray query、mesh shader 等功能
   → 对每项建立独立 capability bit
   → Vulkan/Direct3D/Metal/OpenGL 后端分别查询
   → 组合成平台 profile
   → 缺失能力选择 fallback
   → 材质和 pass 只请求 profile 已承诺的能力

Shader 能力错误排查：

::

   确认 shader stage 与 entry point
   → 确认编译 target/profile
   → 检查资源声明与绑定模型
   → 检查 feature/extension/limit
   → 检查 pipeline 创建错误
   → 检查工具捕获中的实际 shader 与资源
   → 最后再判断 shader 公式本身

概念辨析
--------

* **Shader Model 与 feature level**：Shader Model 主要描述 shader 语言和编译能力；feature level 或 device feature 描述设备与 API 可执行能力，二者不能互相替代。
* **版本号与 capability**：版本号是能力集合的入口；工程决策应落到具体 feature bit、extension 和 limit。
* **固定函数与可编程管线**：固定函数通过有限状态组合描述效果；可编程管线通过 shader 直接表达算法，同时承担更多资源和性能责任。
* **Shader stage 与执行粒度**：stage 表示管线位置；wave/subgroup/threadgroup 表示同一 stage 内线程如何协作，是两个不同维度。
* **源码能力与运行时能力**：代码能编译不代表当前设备和 pipeline 一定支持；必须把编译目标、设备查询和 pipeline 创建放在同一条链上。
* **跨平台抽象与最低公分母**：跨平台抽象不应只取所有后端的最低能力，而应使用 capability profile 保存高端路径并为低端设备提供 fallback。
* **SM6 与所有现代特性**：SM6 提供现代 HLSL/DXIL 与 wave 能力，但 mesh shader、ray tracing 等仍有独立设备和 API 条件。

本章结论
--------

Shader Model 应被当作“代码—编译器—API—驱动—GPU”之间的能力合同。工程上先从视觉目标推导具体 shader 行为，再按 stage、资源、执行粒度和编译目标查询设备能力，最后建立 capability profile 与 fallback；只有把版本号拆成可验证的功能边界，跨平台材质、pipeline 创建和性能排查才会稳定。