第109章：Driver Compilers and GPU Machine Code
===============================================

核心知识点
----------

* SPIR-V、DXIL 等 shader IR 进入 driver 后仍不是最终程序。Driver compiler 必须把标准化 GPU IR 转成 vendor/internal IR，再 lower 到具体 GPU ISA。
* Driver 后端的任务包含 target-specific optimization、instruction selection、register allocation、instruction scheduling、resource lowering 和 pipeline metadata 生成。
* SPIR-V 保留 shader stage、resource binding、structured control flow、texture/image operation 和 SSA value；vendor IR 会进一步暴露真实硬件需要的 scalar/vector execution、memory path、register class 和 scheduling constraints。
* Driver 往往先把标准 IR 转成内部 IR，再执行优化与 lowering。内部 IR 是厂商后端的工作语言，不属于跨厂商稳定接口。
* Texture sampling、uniform/storage-buffer access、push constant、subgroup operation 等高层 GPU 操作最终需要映射到具体 descriptor 读取、地址计算、special-function unit、memory instruction 或专用 texture message。
* Resource binding 不只是 shader 里的 set/binding 数字。Pipeline layout、descriptor state、push constants、bound images/buffers/samplers 和 stage visibility 共同决定机器码怎样取得真实资源。
* Shader executable 通常同时包含机器指令与配套 metadata；后者可能描述 register usage、shared/LDS memory、resource slots、stage inputs/outputs、scratch requirements 等运行配置。
* Register pressure 是 GPU shader 性能核心约束之一。Live values 越多，单个 invocation 占用的 registers 越多，能够同时驻留的 warp/wave/workgroup 数量就可能越少。
* Occupancy 表示计算单元上可同时驻留/执行的并行工作量，但高 occupancy 不是目标本身；最终性能还取决于 latency hiding、memory bandwidth、ALU utilization、texture latency 和 divergence。
* Spill 会把本应驻留寄存器的值放到 scratch/local memory，引入额外 memory traffic；大型临时数组、复杂控制流、过度 unrolling 和高 live-range overlap 都可能提高 spill 风险。
* GPU scheduling 与 CPU scheduling 不同。后端不仅要安排 instruction dependency，还要考虑 SIMT/SIMD execution、wave/warp、memory latency、special units 和 issue resources。
* 同一 SPIR-V 在不同 GPU/driver 上产生不同 machine code 是正常结果，因为 ISA、register file、wave size、cache hierarchy、texture units 和 target heuristics 均不同。
* 排查 shader 问题必须区分前端/SPIR-V 错误与 driver/backend 问题。合法 IR 在特定 GPU 上性能异常，才应继续看 vendor IR、register usage、occupancy、spills 和 machine code。
* GPU 机器码是 shader semantics 与真实 throughput geometry 相交的最终层：这里高层 resource/interface 语义已经被压成硬件寄存器、指令和状态。

关键路径
--------

Driver 编译：

::

   validated shader IR
   → translate to vendor/internal IR
   → optimize + stage-link interfaces
   → lower resources and abstract GPU ops
   → instruction selection
   → register allocation
   → spill/scratch insertion if required
   → instruction scheduling
   → GPU ISA + execution metadata
   → upload/cache executable

资源访问：

::

   SPIR-V DescriptorSet/Binding
   → pipeline layout
   → bound descriptor/resource
   → driver lowers descriptor lookup
   → compute device address / resource handle
   → target load/sample/store instruction

性能判断：

::

   shader IR
   → live values / register pressure
   → allocated registers + scratch
   → occupancy / resident waves
   → latency hiding + memory/ALU behavior
   → measured GPU performance

概念辨析
--------

* **SPIR-V 与 vendor IR**：SPIR-V 是标准交付格式，vendor IR 是 driver 内部为特定后端优化设计的工作表示。
* **Resource binding 与 memory address**：binding 是逻辑接口，driver/pipeline state 最终把它解析成设备资源描述和访问路径。
* **Register pressure 与 occupancy**：前者描述同时活跃值对寄存器的需求，后者描述资源约束下能驻留多少并行执行单元。
* **High occupancy 与 high performance**：occupancy 只是 latency-hiding 条件之一，不能单独代表性能好坏。
* **Shader machine code 与 pipeline metadata**：前者执行计算，后者告诉硬件/driver 该代码需要怎样的资源和 stage 状态。

本章结论
--------

Driver backend 的稳定模型是 ``Portable Shader IR → Vendor IR → Hardware Lowering → Register Allocation/Scheduling → GPU ISA``。真正的 GPU 性能问题要在这一层结合 resource binding、register pressure、occupancy、spills 与硬件执行模型判断；SPIR-V 只是进入具体 GPU 后端的结构化起点。