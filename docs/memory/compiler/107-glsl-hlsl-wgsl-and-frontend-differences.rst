第107章：GLSL, HLSL, WGSL, and Frontend Differences
====================================================

核心知识点
----------

* GLSL、HLSL、WGSL 都是 shader frontend source language，核心任务相同：把源码中的 stage、interface、resource binding 和类型规则转换成后续 IR 能验证和执行的 pipeline semantics。
* GLSL 主要服务 OpenGL/OpenGL ES/Vulkan 生态。``layout(location=...)``、``set/binding``、``in/out``、``gl_Position`` 等构成常见接口证据。
* HLSL 主要服务 Direct3D 生态。输入输出常通过 semantics 表达，系统值使用 ``SV_`` 系列语义；资源通过 ``register``/space 等机制进入 binding model。
* WGSL 与 WebGPU 强绑定，使用 ``@vertex``、``@fragment``、``@compute``、``@location``、``@builtin``、``@group``、``@binding`` 和显式 address space 描述 shader contract。
* 三种语言“语法像什么”不是核心；核心是前端如何从 source-level annotations 中恢复 stage interface 和 resource layout。
* GLSL 的版本/profile 与目标 API 很重要。OpenGL GLSL、ES GLSL 与 Vulkan GLSL 在合法 qualifier、resource model 和编译目标上并不完全相同。
* HLSL 的 shader model/profile 决定可用 stage、系统语义、资源能力和指令特性。相同源码在不同 target profile 下可用能力不同。
* WGSL 更强调静态可验证性与跨平台一致性，许多类型、地址空间、resource binding 和 stage-interface 规则必须在创建 pipeline 前被明确验证。
* Inter-stage 数据连接方式不同：GLSL/WGSL 常显式使用 location/builtin，HLSL 常以 semantic 表达；跨编译时 frontend 必须把这些来源映射到目标 IR 的统一接口表示。
* Resource model 也存在差异。GLSL descriptor set/binding、HLSL register/space、WGSL group/binding 都在描述“程序需要哪个资源槽”，但目标 API 的布局规则和对象模型不同。
* HLSL 编译到 SPIR-V、GLSL 转换到其他后端、WGSL 映射到 Vulkan/Metal/D3D 都属于 cross-compilation；语言表面转换只是第一步，resource semantics、matrix layout、address space、builtins 和 stage rules 必须同时保持。
* Shader frontend 的正确性目标是把语言特性映射成 pipeline-compatible semantics，而不是机械翻译关键字。
* 分析前端差异时应固定五个维度：target API、stage/profile、entry point、stage I/O、resource binding。只比较语法会丢失真正的工程差异。

关键路径
--------

Frontend 主链：

::

   shader source
   → parse + type check
   → identify target API/profile
   → identify entry point + stage
   → normalize stage inputs/outputs
   → normalize resource bindings
   → emit SPIR-V / DXIL / MSL / internal IR
   → target-specific validation

跨语言接口映射：

::

   GLSL layout/location/set/binding
   or HLSL semantic/register/space
   or WGSL location/builtin/group/binding
   → frontend semantic model
   → common IR decorations/interface metadata
   → target API pipeline layout

概念辨析
--------

* **GLSL location 与 HLSL semantic**：都可参与 stage interface，但前者偏数字化槽位，后者先表达语义角色；跨编译时通常要归一化。
* **HLSL register 与 Vulkan binding**：二者都是资源地址体系，但规则不同，不能只按数字直接类比。
* **WGSL validation 与 GPU driver compilation**：WGSL 前端能提前拒绝大量非法程序，但合法 WGSL 仍需后端编译到具体 GPU。
* **Source-language portability 与 shader portability**：语法能转换不代表 resource model、builtin、precision 和 target capability 一定等价。
* **Frontend translation 与 backend lowering**：前端固定语言/stage 语义，后端再根据真实 GPU 做指令与资源实现。

本章结论
--------

GLSL、HLSL、WGSL 的共同核心是 ``Source Syntax → Stage/Interface/Resource Semantics → Target IR``。比较三者时，应围绕 entry point、I/O、builtin、binding 与 target API 建模，而不是围绕关键字表面差异；shader frontend 的本质是把不同语言风格收敛成同一类可验证 pipeline contract。