第108章：SPIR-V and GPU-Oriented Intermediate Representation
=============================================================

核心知识点
----------

* SPIR-V 是面向 graphics shader 和 compute kernel 的二进制中间表示。它已经脱离 GLSL/HLSL 等源码表面，但仍高于具体厂商 GPU ISA。
* SPIR-V module 是 API、工具链与 driver 之间的标准化交付单元。前端把不同 shader language 压缩成共同 IR，driver 再根据具体硬件继续 lowering。
* Module 先声明 capability、memory model、entry point、execution model 与 execution mode，再定义 types、constants、variables、functions、basic blocks 和 instructions。
* ``OpCapability`` 表示模块依赖的能力集合；目标 API/environment 必须支持这些能力，不能把 capability 当作注释。
* ``OpEntryPoint`` 把函数绑定到 Vertex、Fragment、GLCompute 等 execution model，并列出该入口使用的 interface variables。
* Storage class 决定变量属于 Input、Output、Uniform、StorageBuffer、PushConstant、Workgroup 等哪类存储/接口区域；同一 ``OpLoad/OpStore`` 在不同 storage class 下具有不同工程意义。
* Decorations 把 ``Location``、``Binding``、``DescriptorSet``、``Offset``、builtin 等 layout/interface 事实附加到 IR 对象上，是连接 pipeline 与资源布局的关键证据。
* SPIR-V 使用 SSA 风格表示中间值：一个 result id 由唯一指令产生，后续通过 id 建立 def-use；内存更新则通过显式 pointer、load、store 表达。
* Function 内部由 ``OpLabel`` 划分 basic blocks，并通过 branch/return 等 terminator 构成 CFG；分支合流可通过 ``OpPhi`` 表达路径相关值选择。
* Structured control flow 通过 selection/loop merge 等结构显式标记分支与循环汇合点，使 validator 和 driver 能检查控制流形态。
* SPIR-V 仍然保留 portability：它表达“采样纹理”“读取 storage buffer”“fragment entry point”等语义，却不决定真实寄存器编号、warp/wave 调度、cache policy 或最终 machine instruction encoding。
* Validation 会检查 binary layout、types、ids、capabilities、entry interfaces、control flow 和目标环境约束。一个 syntactically valid module 仍可能因为 Vulkan/WebGPU/OpenCL 环境规则不满足而非法。
* Driver 接收 SPIR-V 后通常会先转换到 vendor/internal IR，再做 target-specific optimization、register allocation 与 scheduling。
* 读 SPIR-V 时应先从 module-level contract 入手，再进入 function body；直接从某条 ``OpFMul`` 开始读通常会丢失 stage/resource 语义。

关键路径
--------

Shader 到硬件：

::

   GLSL/HLSL/other source
   → frontend
   → SPIR-V module
   → validate capability/environment/interface
   → driver internal IR
   → target-specific lowering
   → register allocation + scheduling
   → GPU ISA

Module 阅读：

::

   OpCapability / extensions
   → OpMemoryModel
   → OpEntryPoint / OpExecutionMode
   → decorations + storage classes
   → types/constants/globals
   → functions/basic blocks
   → SSA values + memory operations
   → control-flow merges

概念辨析
--------

* **SPIR-V 与 GPU machine code**：前者是标准化 GPU-oriented IR，后者绑定具体 GPU ISA、寄存器与调度模型。
* **Result id 与 memory variable**：result id 表达 SSA value identity；memory variable 通过 pointer/load/store 参与可变状态。
* **Execution model 与 execution mode**：前者说明入口属于哪个 stage/执行模型，后者增加该入口的具体执行约束。
* **Storage class 与 type**：type 说明值的形状，storage class 说明变量位于哪类存储/接口空间。
* **SPIR-V validity 与 API-environment validity**：IR 自身结构合法仍不保证当前 Vulkan/WebGPU/OpenCL target environment 允许所有能力和接口组合。

本章结论
--------

SPIR-V 的稳定模型是 ``Module Contract + Typed SSA/CFG + Explicit Resource Interfaces``。它把 shader source 压缩成 driver 可验证、可优化、可继续 lowering 的 GPU-oriented IR，同时把真实硬件寄存器、调度和 ISA 决策保留给后端；阅读时先看 capability/entry/interface，再追 SSA 与控制流。