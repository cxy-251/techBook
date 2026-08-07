第089章：HLSL Shader 系统
========================

核心知识点
----------

HLSL 系统是一条从源码到 GPU 执行的完整工程链
   ``.hlsl/.hlsli`` 只是输入。稳定结果还依赖 entry point、target profile、DXC、DXIL、root signature、PSO、descriptor binding、debug info 与 GPU capture。Shader 文件能编译，不代表资源与 pipeline 已正确集成。

HLSL 正确性应同时满足五类契约
   语言契约要求类型与 intrinsic 合法；stage 契约要求 entry input/output semantic 正确；资源契约要求 ``b/t/u/s`` register 与 space 匹配；编译契约要求 macro/include/profile/compiler 可复现；工具契约要求 capture 能回溯到准确 shader blob 与源码版本。

Semantic 是 Shader Stage 与固定管线之间的接口标签
   ``POSITION``、``NORMAL``、``TEXCOORD`` 属于应用语义，``SV_Position``、``SV_Target``、``SV_DispatchThreadID`` 属于系统值语义。顶点输入和 stage 输出异常时，先确认 semantic 与 pipeline stage 对齐，再检查内部数学。

Entry Point 与 Target Profile 共同定义 Shader 身份
   同一个文件可以包含 VS/PS/CS；编译时 ``-E`` 选择入口，``-T`` 选择 ``vs_6_x``、``ps_6_x``、``cs_6_x`` 等目标。Cache key 必须包含 entry、profile、macro、include 依赖和编译器版本。

Shader 模块应围绕可复现依赖组织
   公共类型、资源声明、光照函数、材质逻辑可以拆入 ``.hlsli``；可编译入口留在 ``.hlsl``。源码依赖图变化应触发对应 blob 重编译，而不是依赖人工清缓存。

DXC 与 DXIL 是现代 HLSL 工具链核心
   DXC 将 HLSL 编译为 DXIL，validator 验证合法性，driver 再生成硬件代码。工程问题复现应保存 HLSL、DXC 版本、编译参数、DXIL blob、reflection 与 root signature。

Shader Permutation 应只承载真正改变代码结构的条件
   Normal map、alpha test、skinning、shadow receiver 等大分支适合 permutation；每 draw 小开关适合 root/material constant；每像素变化的数据适合 texture/buffer。Permutation 过度会放大编译时间、PSO 数量和测试矩阵。

Reflection 是 Shader 与引擎 Binding Contract 的验证器
   Reflection 可读资源 register/space、constant layout、input/output signature。构建阶段应校验它与 root signature、input layout、render target 数量和材质资源表一致。

HLSL Register/Space 是 API Binding 的虚拟地址
   ``b`` 对应 CBV，``t`` 对应 SRV，``u`` 对应 UAV，``s`` 对应 sampler；``space`` 用来划分逻辑资源域。Shader 声明必须和 D3D12 root signature/descriptor range 完整对齐。

Stage Integration 必须和 PSO/Root Signature 一起检查
   VS 需要 IA 输入与 constant；PS 需要 SRV/sampler/RTV；CS 需要 dispatch geometry、SRV/UAV 与 barrier。Shader 源码只描述 stage 内计算，不定义 resource state、descriptor heap 或 render target binding。

Descriptor Array 的非一致索引需要显式表达
   一个 draw/dispatch 内不同 lane 访问不同 descriptor 时，应使用 ``NonUniformResourceIndex`` 等正确路径，并接受潜在硬件成本。Bindless 错纹理经常来自 index、descriptor heap 或 non-uniform 语义错误。

Compute Shader 的风险与 Pixel Shader 不同
   CS 重点检查 thread-group 尺寸、dispatch 覆盖、越界、shared memory/barrier、UAV 原子操作与资源状态；PS 则更关注 interpolation、texture sampling、depth/blend 与 render target 输出。

Shader Model 是能力契约，不只是语法版本
   Wave ops、DXR、mesh shader、bindless 等特性必须同时满足 DXC、runtime/SDK、GPU/driver 与 feature query。引擎应以 capability profile 选择 permutation 和 fallback，而不是统一强制最高 profile。

Wave Operations 是同一 Wave 内的显式协作工具
   Reduction、scan、vote、broadcast 等可降低共享内存与多 pass 成本，但需要理解 lane/wave 执行与 divergence。它们属于算法优化，不应仅因 Shader Model 支持就无条件使用。

Shader 调试应从具体 Draw/Dispatch 进入
   先定位异常 pass 与 event，再看 PSO、root signature、descriptor、shader source/disassembly、输入输出和 render target。开发构建应生成 PDB/debug info；发布构建至少保留 shader hash、entry、profile、macro key 与源码版本映射。

关键路径
--------

离线编译：

::

   source + includes
   → entry point
   → target profile
   → macro / permutation key
   → DXC
   → DXIL + debug info
   → reflection metadata
   → root signature / PSO validation
   → shader cache

一次材质 Draw：

::

   IA vertex attributes
   → VS entry + semantics
   → interpolants
   → PS resources via b/t/s registers
   → material sampling / lighting
   → SV_Target
   → output merger

Compute：

::

   descriptor binding
   → Dispatch dimensions
   → SV_DispatchThreadID
   → group/shared operations
   → UAV writes
   → barrier / transition
   → next pass consumes result

调试：

::

   locate bad draw/dispatch
   → exact shader hash / permutation
   → compile/link metadata
   → PSO + root signature
   → descriptor bindings
   → shader inputs / outputs
   → DXIL / source / counters
   → resource state + render target

概念辨析
--------

* **HLSL Source 与 Shader Blob**：source 是源码，blob 是特定 entry/profile/macro/compiler 组合产生的 DXIL 产物。
* **Semantic 与 Register**：semantic 连接 pipeline stage 数据，register/space 连接 shader 资源绑定。
* **Permutation 与 Runtime Branch**：前者生成不同 shader blob，后者在同一 blob 中根据数据选择路径。
* **Shader Model 与 Feature Support**：profile 表示编译目标，最终能力仍需 runtime、driver 与硬件查询确认。
* **Reflection 与 Runtime Binding**：reflection 用于验证声明，runtime binding 决定当前 draw 实际绑定哪一资源。
* **Pixel Shader 与 Compute Shader**：一个连接 raster/OM，一个由 dispatch/thread group 驱动，资源与同步风险不同。
* **DXIL 与 GPU ISA**：DXIL 是编译中间表示，不是最终硬件机器码。

本章结论
--------

HLSL 应按“Source—Entry/Profile—DXC/DXIL—Reflection—Root Signature/PSO—Descriptor—GPU Event”理解。黑屏时先确认具体 permutation 和 draw，再查 semantic、root binding 与 descriptor；compute 结果错误则额外检查 dispatch、UAV 与 barrier；性能问题才进入 wave、divergence、texture/sample 与反汇编/counter。可靠 shader 系统的核心，是让每个 GPU blob 都能被准确复现、验证并映射回源码与资源契约。