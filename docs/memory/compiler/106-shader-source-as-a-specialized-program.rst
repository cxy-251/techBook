第106章：Shader Source as a Specialized Program
================================================

核心知识点
----------

* Shader 不是普通函数换了语法，而是嵌在图形或计算 pipeline contract 中的并行程序。它的意义由 stage、输入输出接口、资源绑定、fixed-function state 和 GPU 执行模型共同决定。
* Vertex、fragment、compute、geometry、mesh 等 stage 拥有不同输入来源、输出去向和 invocation frequency；分析 shader 的第一步必须先固定 stage。
* Entry point 的 stage 标记决定函数由谁调用。普通应用函数通过语言调用约定进入，shader entry point 则由 graphics/compute pipeline 按 draw、dispatch、primitive、vertex、fragment 或 workgroup 规则触发。
* Stage interface 包含 location、builtin、interpolation、resource binding 等契约。相同的 ``location 0`` 在 vertex input、inter-stage varying 和 fragment output 中属于不同接口面。
* Builtin 变量由 pipeline 赋予特殊意义，例如 position、vertex id、fragment coordinate、global invocation id；它们不是普通用户变量。
* Resource binding 把 uniform/storage buffer、texture、sampler、image 等外部对象接入 shader。源码声明只给出逻辑接口，实际 buffer/image/sampler 由 application 与 pipeline layout 绑定。
* Shader 语言通常原生支持 vector、matrix、texture sampling、address space、workgroup/shared memory 等 GPU 语义；这些操作比普通函数调用携带更强的 stage 与硬件约束。
* 坐标空间、插值和纹理采样往往同时依赖源码与 pipeline context。变量名本身不能证明它处于 object/world/view/clip/screen 哪个空间，必须沿 builtin/location 与应用侧约定追踪。
* Shader compiler 前端负责解析、类型检查、stage/interface 验证，并生成 SPIR-V、DXIL、MSL 或 driver IR 等后续表示；driver 仍要继续 lower 到具体 GPU ISA。
* Application、API、driver、GPU 形成多层编译边界。应用提供 shader 与 pipeline state，API 验证接口与对象，driver 做目标相关优化和代码生成，GPU 最终执行 machine code。
* 同一 shader source 在不同 GPU、不同 pipeline state、不同 specialization 值下可能得到不同最终机器码；源文件不是性能分析的唯一输入。
* Shader correctness 同样跨层：源码语法正确并不代表 pipeline interface、resource layout 或 target capability 一定合法。

关键路径
--------

Shader 编译执行链：

::

   shader source
   → parse/type check
   → identify entry point + stage
   → validate inputs/outputs/resources
   → shader IR (SPIR-V/DXIL/other)
   → API/pipeline validation
   → driver internal IR
   → target-specific lowering
   → GPU machine code + metadata
   → stage invocations execute on GPU

接口判断：

::

   fix current stage
   → inspect entry point
   → inspect location/builtin inputs
   → inspect location/builtin outputs
   → inspect bound resources
   → inspect fixed-function pipeline state
   → determine actual program meaning

概念辨析
--------

* **Shader function 与 ordinary function**：普通函数由程序调用，shader entry point 由 pipeline 按 stage 规则启动。
* **Location 与 builtin**：location 连接用户定义接口，builtin 由 API/stage 赋予预定义语义。
* **Shader source 与 pipeline state**：源码描述可编程计算，pipeline state 决定这些输入输出如何进入固定功能阶段和资源系统。
* **Shader IR 与 GPU ISA**：SPIR-V/DXIL 等仍是可移植或 API 级中间表示，真实 GPU 机器码由 driver 后端生成。
* **源码变量名 与 坐标空间**：名字只是人类约定，真正空间语义来自数学变换、builtin 与 pipeline contract。

本章结论
--------

Shader 的稳定模型是 ``Stage + Interface + Resources + Pipeline State + GPU Execution``。阅读 shader 时不要先盯算术表达式，而应先确定“谁调用它、它读什么接口、写什么接口、依赖哪些资源”，再沿 frontend → IR → driver → GPU 追踪最终执行。