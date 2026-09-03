====================================================================================================
领域特定编译器：SPIR-V 着色器编译、AI 计算图算子融合 (Operator Fusion) 与 Tensor IR
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 9 模块第 2 节（``02_mlir_dialects_and_progressive_lowering``）中，我们系统解构了 MLIR 的模块化 Dialect 扩展哲学、Operation/Region/Block/Type 核心层次拓扑，以及基于 ConversionTarget 与 RewritePattern 的渐进降级（Progressive Lowering）流水线。现代计算硬件与软件工作负载的急剧分化，催生了脱离传统通用标量编译管线的领域特定编译器（Domain-Specific Compiler, DSC）。
   在图形渲染、通用 GPU 计算（GPGPU）与人工智能深度学习系统两个最具代表性的加速计算领域，计算任务分别以大规模细粒度着色器并发（Shader SIMT）和高维张量数据流（Tensor Dataflow）为核心形态。本章深入剖析面向 GPU 图形与通用计算的标准化二进制中间表示 SPIR-V，解构其显式执行模型、存储类拓扑与结构化控制流约束；随后推导现代 AI 编译器的图优化理论，揭示算子融合（Operator Fusion）消除中间张量物化（Materialization）的核心物理本质，详述逐元素融合、归约融合、分块生产者-消费者融合与 GEMM 尾部（Epilogue）融合的判定条件与代价模型，最后交付一套自包含的 C++ AI 计算图优化与融合引擎实现。

SPIR-V 规范与现代 GPU 着色器编译体系
------------------------------------

GPU 架构以海量并行计算单元与单指令多线程（SIMT, Single Instruction Multiple Threads）为核心特征。在 Vulkan、OpenCL 等现代底层计算与图形 API 诞生前，着色器源码（如 GLSL、HLSL）多以高层文本形式直接递交给驱动程序，导致驱动编译器体积臃肿、编译耗时不可控且跨厂商行为差异显著。Khronos 推出的 SPIR-V（Standard Portable Intermediate Representation - V）打破了这一壁垒，确立了跨平台、跨厂商的标准化二进制中间表示。

SPIR-V 物理二进制拓扑与词流模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SPIR-V 在物理存储上呈现为规整的 32 位无符号整数字字流（32-bit Word Stream），彻底剥离了源码排版、注释、宏展开与语法糖。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     SPIR-V 二进制模块 (Module) 物理布局                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 5-Word 固定头部 (Header) ]                                               |
   |     Word 0: 魔数 (Magic Number: 0x07230203)                                 |
   |     Word 1: SPIR-V 版本规范版本号 (Version: e.g., 0x00010600 代表 1.6)       |
   |     Word 2: 编译器生成工具链 ID (Generator Magic Number)                    |
   |     Word 3: 标识符边界分配上限 (Bound: 当前模块内所有 <id> 的最大界限值)     |
   |     Word 4: 保留字 (Schema: 目前置 0)                                       |
   |                                                                             |
   |   [ 顺序指令流 (Sequential Instruction Stream) ]                            |
   |     每条指令编码格式:                                                       |
   |     +-----------------------------------+-----------------------------------+
   |     | Word Count (高 16 位, 指令总字数) | Opcode (低 16 位, 操作码枚举)     |
   |     +-----------------------------------+-----------------------------------+
   |     | [可选 Type <id>] (当指令生成带类型结果时占用 1 Word)                  |
   |     +-------------------------------------------------------------------+
   |     | [可选 Result <id>] (当指令产出 SSA 值绑定时占用 1 Word)               |
   |     +-------------------------------------------------------------------+
   |     | 操作数字流 (Operands: 字面量、枚举、输入 <id> 列表) ...              |
   |     +-------------------------------------------------------------------+
   |                                                                             |
   +-----------------------------------------------------------------------------+

SPIR-V 采用严格的静态单赋值（SSA）命名系统。每个生成计算值的指令分配唯一的全局数值 ``Result <id>``，所有输入操作数均以目标 ``<id>`` 进行引用，构建出纯粹而紧凑的值依赖有向无环图。

模块声明、执行模型与入口点契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SPIR-V 模块是自包含的编译单元。模块必须按照规范声明的线性阶段有序组织，确立其运行环境约束：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        SPIR-V 模块逻辑分区与指令顺序                        |
   +-----------------------------------------------------------------------------+
   |  1. 能力声明 (Capabilities)     : OpCapability Shader, Float64, Matrix ...  |
   |  2. 扩展引入 (Extensions)       : OpExtension "SPV_KHR_storage_buffer_..."  |
   |  3. 扩展指令集引入              : %glsl = OpExtInstImport "GLSL.std.450"    |
   |  4. 内存模型声明                : OpMemoryModel Logical GLSL450             |
   |  5. 入口点与执行模型            : OpEntryPoint Fragment %main "main" %out   |
   |  6. 执行模式配置                : OpExecutionMode %main OriginUpperLeft     |
   |  7. 调试与命名元数据            : OpString, OpName, OpMemberName            |
   |  8. 装饰与接口布局 (Decoration) : OpDecorate %out Location 0                |
   |                                   OpDecorate %buf DescriptorSet 0 Binding 1 |
   |  9. 类型与常量声明 (Types/Const): %void = OpTypeVoid, %f32 = OpTypeFloat 32 |
   | 10. 全局变量声明 (Variables)    : %out = OpVariable %ptr Output             |
   | 11. 函数体定义 (Functions)      : OpFunction -> OpLabel -> Blocks ...       |
   +-----------------------------------------------------------------------------+

``OpEntryPoint`` 将特定的内部函数符号绑定至具体的硬件执行阶段（Execution Model）：
- **图形管线阶段**：``Vertex``（顶点着色）、``TessellationControl`` / ``TessellationEvaluation``（细分着色）、``Geometry``（几何着色）、``Fragment``（片元像素着色）。
- **通用计算阶段**：``GLCompute``（计算着色器 Compute Shader）、``Kernel``（OpenCL 风格通用计算核心）。
- **光线追踪阶段**：``RayGenerationKHR``、``ClosestHitKHR``、``MissKHR`` 等。

每个入口点显式声明其引用的接口变量集合（如全局输入、全局输出与 Uniform 常量）。同一 SPIR-V 模块内可容纳多个入口点，共享下层辅助工具函数与全局常量定义。

存储类 (Storage Class) 与 GPU 硬件内存拓扑映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SPIR-V 中的指针与变量必须显式归属于特定的 **Storage Class（存储类）**。Storage Class 直接对应 GPU 芯片内部物理异构存储层次与访问控制契约：

.. list-table:: SPIR-V 核心存储类 (Storage Class) 与硬件存储映射
   :widths: 18 20 28 34
   :header-rows: 1
   :class: tight-table

   * - 存储类枚举
     - 对应 GLSL / HLSL 概念
     - 硬件物理存储介质
     - 访问权限、生命周期与同步边界
   * - **Input**
     - ``in`` / Attribute
     - 顶点属性寄存器 / 光栅化插值硬件缓冲区
     - 只读。单次 Invocation 独享，由图形固定硬件流水线预先装载。
   * - **Output**
     - ``out`` / SV_Target
     - 颜色缓冲区写入队列 / 后续阶段寄存器
     - 可写。单次 Invocation 独享，阶段结束时传递至下阶段或输出合并器。
   * - **Uniform**
     - Uniform Buffer Object (UBO)
     - 板载显存 + GPU 片上只读 L1/L2 常量缓存 (K-Cache)
     - 只读。所有线程共享，适合小尺寸、高频广播读取的高局部性常量参数。
   * - **StorageBuffer**
     - Shader Storage Buffer (SSBO)
     - 全局显存 (Global Device Memory / VRAM / HBM)
     - 读写。支持大容量结构化数组与原子操作，依赖内存屏障保证一致性。
   * - **PushConstant**
     - Push Constant
     - GPU 指令发射单元内嵌寄存器常量槽
     - 只读。容量极小（通常 128~256 字节），零内存延迟直通指令流水线。
   * - **Workgroup**
     - ``shared`` / ``groupshared``
     - GPU 流多处理器（SM/CU）内部片上共享内存 (SRAM)
     - 读写。同一 Workgroup/Threadblock 内线程共享，延迟极低（单周期级）。
   * - **Function**
     - 局部局部变量
     - 物理通用寄存器堆 (GPR) / 线程私有溢出栈
     - 读写。单线程生命周期，超出物理寄存器预算时触发 Local Memory 栈溢出。

结构化控制流 (Structured Control Flow) 约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在标量 CPU 架构中，控制流图（CFG）允许包含由 ``goto`` 构成的任意复杂控制流。但在 GPU SIMT 架构中，多个线程（NVIDIA Warp 包含 32 线程，AMD Wavefront 包含 32 或 64 线程）锁步执行同一条指令指针。当出现分支分歧（Divergence）时，硬件依赖屏蔽掩码与收敛栈（Convergence Stack）串行执行各分支路径。

为了使驱动编译器能确定性分析分歧收敛点，SPIR-V 严格执行 **结构化控制流（Structured Control Flow）** 规范：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       SPIR-V 条件分支结构化收敛拓扑                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ Header Block ] (分歧起点)                                               |
   |     ...                                                                     |
   |     OpSelectionMerge %merge_label None  <-- 显式声明收敛汇合点 Target       |
   |     OpBranchConditional %cond %true_bb %false_bb                            |
   |                                                                             |
   |              /                               \                              |
   |             v                                 v                             |
   |     [ True Block ]                     [ False Block ]                      |
   |       ...                                ...                                |
   |       OpBranch %merge_label              OpBranch %merge_label              |
   |             \                                 /                             |
   |              \                               /                              |
   |               v                             v                               |
   |                                                                             |
   |   [ Merge Block (%merge_label) ] (硬件重收敛终点)                           |
   |     %val = OpPhi %f32 %v_true %true_bb %v_false %false_bb                   |
   |     ... 后续指令执行 ...                                                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

- **选择合并指令（OpSelectionMerge）**：位于条件分支判断头块，携带唯一的 ``Merge Block`` 标签参数，强制声明该分支网络所有可能路径的唯一汇合点。
- **循环合并指令（OpLoopMerge）**：位于循环头块（Loop Header），携带 ``Merge Block``（循环跳出后继）与 ``Continue Block``（循环步进块）两个关键锚点。
- **单入口单出口嵌套**：结构化控制流构成立体严格嵌套区间，禁止交叉跨越边（Cross Edges）穿透进入循环或选择体内，确保驱动编译器能将代码无歧义映射到硬件 SIMT 分歧处理单元上。

AI 计算图模型与高层图优化
-------------------------

在人工智能深度学习框架（PyTorch、JAX、TensorFlow、ONNX）中，神经网络模型以 **计算图（Computation Graph）** 的形态呈现。AI 编译器（如 XLA、TVM、MLIR-Torch）直接在计算图抽象层上执行全局优化。

有向无环图数据流语义与张量元数据
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

计算图形式化定义为带有张量属性的拓扑图 $\mathcal{G} = (\mathcal{V}, \mathcal{E})$：
- **节点（$\mathcal{V}$）**：承载具体的操作算子（Operator），如全连接矩阵乘（``MatMul``）、二维卷积（``Conv2D``）、批归一化（``BatchNorm``）、激活函数（``ReLU``）与张量变换（``Reshape``、``Transpose``）。
- **边（$\mathcal{E}$）**：承载计算产出的张量值（Tensor Value），定义严格的生产者-消费者（Use-Def）依赖关系。

每个张量值携带丰富的多维静态类型元数据：
1. **形状（Shape）**：维度张量尺寸元组，例如动态批次卷积激活张量 $[N, C, H, W]$ 或权重矩阵 $[C_{out}, C_{in}, K_h, K_w]$。
2. **数据基元（DType）**：浮点精度（``f32``, ``f16``, ``bf16``, ``fp8``）、整型量化表示（``i32``, ``i8``, ``u4``）或复合复数。
3. **物理排布（Layout）**：逻辑坐标到物理连续线性内存的映射阶，如计算机视觉中的通道优先（``NCHW``）与通道最后（``NHWC``）。

图级规范化优化：常量折叠、死节点修剪与代数化简
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在深入高阶算子重写前，AI 编译器管线首先执行基础规范化三部曲：

.. list-table:: 现代 AI 计算图典型优化 Pass 与分析维度
   :widths: 22 26 52
   :header-rows: 1
   :class: tight-table

   * - 优化 Pass 类别
     - 分析触发条件
     - 变换动作与核心系统收益
   * - **常量折叠 (Constant Folding)**
     - 算子的全部输入输入边均绑定静态编译期已知张量常量。
     - 编译期直接调用 CPU/GPU 主机端计算内核求值，将整段常量子图替换为单一具象张量权重节点。消除运行时内核调用开销与中间分配。
   * - **死节点消除 (DCE)**
     - 节点输出未通向最终模型输出，且算子自身具备纯函数（Pure）无副作用特质。
     - 从模型输出根节点与外部依赖点出发逆向遍历标记活跃节点，物理擦除所有不可达孤岛算子。降低显存占用与模型参数体积。
   * - **代数恒等式化简 (Algebraic Simplification)**
     - 子图计算拓扑符合数学代数等价性规则。
     - 消除冗余操作（如消除与 $0$ 矩阵的相加、与 $1$ 的矩阵乘）、合并连续张量维度变换（如合并连续 Reshape、抵消双重 Transpose）。

算子融合 (Operator Fusion)：访存瓶颈打破与 Tensor IR 抽象
---------------------------------------------------------

在计算硬件（特别是 GPU 与专用 AI 加速器）上，算子的执行效率严格遵循 **运算强度（Operational Intensity, 算力/访存比：FLOPs/Byte）** 的物理规律。

算子执行的内存带宽墙 (Memory Wall) 困境
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

深度学习网络中存在大量点操作（Elementwise）算子，例如激活函数（ReLU、GELU）、偏置加法（Bias Add）、归一化缩放（LayerNorm Scale/Shift）与残差相加（Residual Add）。此类算子的算力密度极低：每个浮点数据加载仅伴随 1~2 次运算，导致硬件计算核心吞吐大幅闲置，执行时间完全被高延迟、受限带宽的全局显存（HBM / GDDR）读写占满。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     未融合算子链的全局显存往返瓶颈 (Memory Wall)            |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 全局显存 HBM ]                                                          |
   |       |          ^              ^              ^              ^             |
   |       | (读输入) | (写中间值)   | (读中间值)   | (写中间值)   | (读中间值)  |
   |       v          |              v              |              v             |
   |   +------------+ |          +------------+     |          +------------+    |
   |   | Kernel 1   |-+          | Kernel 2   |-----+          | Kernel 3   |    |
   |   | (Bias Add) |            | (Scale)    |                | (ReLU)     |    |
   |   +------------+            +------------+                +------------+    |
   |         |                         |                             |           |
   |         v                         v                             v           |
   |   [启动 Kernel 1]           [启动 Kernel 2]               [启动 Kernel 3]   |
   |                                                                             |
   +-----------------------------------------------------------------------------+
   | 物理代价: 3 次 GPU Kernel 启动开销 + 2 次巨量中间张量内存往返读写 (DRAM)    |
   +-----------------------------------------------------------------------------+

算子融合的物理本质是：**消除中间张量在物理内存中的实体物化（Materialization）**。通过合并多个计算逻辑，使数据仅从全局显存加载一次，各中间算子计算直接在芯片片上高速存储（寄存器堆或 SRAM 共享内存）中级联求值，仅将最终结果写回显存。

四大核心融合模式与微架构约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据张量迭代空间、数据访问依赖与循环收缩维度，算子融合被归纳为四大模式：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    算子融合 (Operator Fusion) 四大经典拓扑                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   | 1. 逐元素融合 (Elementwise Fusion)                                          |
   |    [In] ---> [Add] ---> [Mul] ---> [ReLU] ---> [Out]                        |
   |    合并为单个多指令 Loop 核心: out[i] = relu((in[i] + bias[i]) * scale)     |
   |                                                                             |
   | 2. 尾部融合 (Epilogue Fusion)                                               |
   |    [MatMul] ----> [Bias Add] ----> [GELU] ----> [Out]                       |
   |    在 GEMM 乘加寄存器累加完成、写回全局显存前执行 Bias 与 GELU 激活计算     |
   |                                                                             |
   | 3. 归约融合 (Reduction Fusion)                                              |
   |    [In] ---> [GELU] ---> [ReduceSum(axis=1)] ---> [Out]                     |
   |    生产者 GELU 内联进局部归约循环内部: acc += gelu(in[r, c])                |
   |                                                                             |
   | 4. 分块生产者-消费者融合 (Tiled Producer-Consumer Fusion)                   |
   |    [Conv2D Tile] ===== (On-Chip Shared Memory) =====> [Pooling Tile]        |
   |    按输出分块逆推输入切片，将生产者切片保留在 SRAM 中立即消费               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: 算子融合模式分类与硬件微架构资源映射
   :widths: 20 22 28 30
   :header-rows: 1
   :class: tight-table

   * - 融合模式
     - 结构约束与合法性条件
     - 数据驻留层级
     - 微架构性能收益与风险
   * - **Elementwise Fusion**
     - 所有参与算子具有同构或广播兼容（Broadcast-Compatible）的输出迭代空间。
     - 物理寄存器（GPR）
     - 消除全部中间缓冲物化；极低寄存器开销，属于无条件盈利转换。
   * - **Epilogue Fusion**
     - 生产者为重算力收缩内核（GEMM、Conv2D），消费者为紧随其后的轻量级逐元素节点。
     - GEMM 寄存器累加器（Accumulator）
     - 隐蔽利用高算力内核访存通道；省去独立内核启动，但稍许延长寄存器驻留周期。
   * - **Reduction Fusion**
     - 逐元素生产者与归约消费者单向连接，归约维度与连续内存轴良好对齐。
     - Warp Shuffle 寄存器 / Workgroup Shared Memory
     - 消除高维输入张量展开；须满足浮点结合律与并行规约树精度一致性要求。
   * - **Tiled Fusion**
     - 算子间存在局部邻域访问（如卷积、池化窗口），需具备仿射索引映射（Affine Maps）。
     - 片上 SRAM / 共享内存 (Shared Memory)
     - 避免大张量全局落地；若边缘存在重叠数据（Halo），需权衡重复计算与带宽节省。

融合合法性、依赖环检测与代价模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

并非所有结构上相邻的算子均可随意融合。AI 编译器在聚类融合候选集时必须受控遵循三道防线：

1. **依赖成环与不可达约束（Cycle Detection）**：
   若算子 $A$ 产出的数据不仅流入算子 $B$，还流入图中的其他独立路径 $C$，且 $C$ 最终汇入 $B$ 的下游算子 $D$。若强行将 $A$ 与 $D$ 融合为单一节点，将导致 $C$ 的输入依赖 $A$（新节点内部），而新节点的输入又依赖 $C$，在计算图层面上构筑出逻辑循环依赖（Deadlock Cycle）。
2. **多消费者计算重复代价（Duplicate Compute Trade-off）**：
   当中间张量 $T$ 被后续多个非同构消费节点使用时，若将生成 $T$ 的算子完全融合进每个消费者内核中，将导致 $T$ 的计算在多个硬件内核中被重复执行。代价模型（Cost Model）需精准量化重复计算 FLOPs 消耗与节省显存读写带宽之间的盈亏平衡点。
3. **硬件资源上限拦截（Hardware Resource Quotas）**：
   将过多计算折叠入单一内核会导致内核指令数膨胀、需要的局部变量与向量累加器剧增。一旦寄存器分配超出硬件物理寄存器预算（如 NVIDIA SM 每个线程分配超过 255 个 32 位寄存器），硬件将被迫发生寄存器溢出（Register Spilling），将临时数据打入高延迟局部显存，导致并发线程占用率（Warp Occupancy）断崖式下跌，吞噬全部融合收益。

C++ 工业级 AI 计算图融合与降级编译器引擎实战
--------------------------------------------

为了直观呈现计算图数据流建模、死节点消除、常量折叠与多模式算子融合的工业级落地过程，以下给出一套自包含、无外部依赖的 C++ AI 计算图编译器内核实现：
1. **多维张量与图模型**：支持多维形状、静态常量、占位输入与浮点数据缓冲区。
2. **优化 Pass 驱动器**：
   - ``ConstantFoldingPass``：折叠图内所有编译期可求值的常量子图。
   - ``DeadNodeEliminationPass``：从最终图输出反向追踪可达性，物理修剪无用计算节点。
3. **融合引擎（Fusion Engine）**：
   - 识别连续的逐元素链（$BiasAdd 	o Scale 	o ReLU$），融合为复合的 ``FusedElementwiseOp``。
   - 识别重算力矩阵乘与其尾部逐元素算子构成的复合链，融合为 ``FusedMatMulEpilogueOp``。
4. **底层代码生成（Codegen）**：模拟将高层融合计算图下沉为展开后的单内核紧凑 C 循环，消除所有中间张量物化。
5. **单元测试套件**：全量验证常量折叠、死节点擦除、尾部融合以及端到端计算数值一致性。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <cassert>
   #include <cmath>
   #include <functional>
   #include <sstream>

   namespace mini_ai_compiler {

   // =========================================================================
   // 1. 张量形状与物理缓冲区系统
   // =========================================================================
   class TensorShape {
   public:
       std::vector<int64_t> Dims;

       TensorShape(std::initializer_list<int64_t> dims) : Dims(dims) {}
       explicit TensorShape(std::vector<int64_t> dims) : Dims(std::move(dims)) {}

       size_t numElements() const {
           if (Dims.empty()) return 0;
           size_t n = 1;
           for (auto d : Dims) n *= d;
           return n;
       }

       bool operator==(const TensorShape& other) const {
           return Dims == other.Dims;
       }

       std::string toString() const {
           std::ostringstream oss;
           oss << "[";
           for (size_t i = 0; i < Dims.size(); ++i) {
               oss << Dims[i] << (i + 1 < Dims.size() ? ", " : "");
           }
           oss << "]";
           return oss.str();
       }
   };

   class TensorBuffer {
   public:
       TensorShape Shape;
       std::vector<float> Data;

       TensorBuffer(TensorShape shape, float initialVal = 0.0f)
           : Shape(shape), Data(shape.numElements(), initialVal) {}

       TensorBuffer(TensorShape shape, std::vector<float> data)
           : Shape(shape), Data(std::move(data)) {
           assert(Shape.numElements() == Data.size());
       }
   };

   // =========================================================================
   // 2. 计算图节点与算子类型拓扑
   // =========================================================================
   enum class OpType {
       Parameter,       // 动态输入或权重输入
       Constant,        // 编译期静态常量
       MatMul,          // 2D 矩阵乘法
       Add,             // 逐元素加法 / 广播偏置
       Mul,             // 逐元素乘法
       ReLU,            // 激活函数 max(0, x)
       FusedElementwise,// 融合逐元素操作
       FusedMatMulEpilogue // 融合矩阵乘与尾部激活
   };

   class Node;

   class Edge {
   public:
       std::shared_ptr<Node> Producer;
       std::shared_ptr<Node> Consumer;
       size_t ProducerOutputIdx;
       size_t ConsumerInputIdx;

       Edge(std::shared_ptr<Node> prod, std::shared_ptr<Node> cons, size_t pIdx, size_t cIdx)
           : Producer(std::move(prod)), Consumer(std::move(cons)),
             ProducerOutputIdx(pIdx), ConsumerInputIdx(cIdx) {}
   };

   class Node : public std::enable_shared_from_this<Node> {
   public:
       std::string Name;
       OpType Type;
       TensorShape OutputShape;
       std::shared_ptr<TensorBuffer> StaticData; // 仅对 Constant 节点非空

       std::vector<std::shared_ptr<Node>> Inputs;
       std::vector<std::shared_ptr<Node>> Outputs;

       // 尾部融合元数据参数
       float MulScale = 1.0f;
       bool HasBias = false;
       bool HasReLU = false;

       Node(std::string name, OpType type, TensorShape shape)
           : Name(std::move(name)), Type(type), OutputShape(shape) {}

       void addInput(const std::shared_ptr<Node>& inNode) {
           Inputs.push_back(inNode);
           inNode->Outputs.push_back(shared_from_this());
       }

       void replaceInput(size_t index, const std::shared_ptr<Node>& newNode) {
           assert(index < Inputs.size());
           auto oldNode = Inputs[index];
           Inputs[index] = newNode;
           newNode->Outputs.push_back(shared_from_this());

           // 从旧节点的 Outputs 中移除自身引用
           for (auto it = oldNode->Outputs.begin(); it != oldNode->Outputs.end(); ++it) {
               if (it->get() == this) {
                   oldNode->Outputs.erase(it);
                   break;
               }
           }
       }
   };

   class ComputationGraph {
   public:
       std::vector<std::shared_ptr<Node>> Nodes;
       std::shared_ptr<Node> OutputNode;

       std::shared_ptr<Node> createNode(const std::string& name, OpType type, TensorShape shape) {
           auto node = std::make_shared<Node>(name, type, shape);
           Nodes.push_back(node);
           return node;
       }

       std::shared_ptr<Node> createConstant(const std::string& name, TensorShape shape, std::vector<float> data) {
           auto node = createNode(name, OpType::Constant, shape);
           node->StaticData = std::make_shared<TensorBuffer>(shape, std::move(data));
           return node;
       }

       void setGraphOutput(const std::shared_ptr<Node>& outNode) {
           OutputNode = outNode;
       }

       void printGraphTopology() const {
           std::cout << "[Graph Topology Dump]
";
           for (const auto& n : Nodes) {
               std::cout << "  Node: " << n->Name << " (" << opTypeToString(n->Type) 
                         << "), Shape: " << n->OutputShape.toString() << "
";
               std::cout << "    Inputs : [";
               for (size_t i = 0; i < n->Inputs.size(); ++i) {
                   std::cout << n->Inputs[i]->Name << (i + 1 < n->Inputs.size() ? ", " : "");
               }
               std::cout << "]
    Outputs: [";
               for (size_t i = 0; i < n->Outputs.size(); ++i) {
                   std::cout << n->Outputs[i]->Name << (i + 1 < n->Outputs.size() ? ", " : "");
               }
               std::cout << "]
";
           }
       }

   private:
       static std::string opTypeToString(OpType t) {
           switch (t) {
               case OpType::Parameter: return "Parameter";
               case OpType::Constant: return "Constant";
               case OpType::MatMul: return "MatMul";
               case OpType::Add: return "Add";
               case OpType::Mul: return "Mul";
               case OpType::ReLU: return "ReLU";
               case OpType::FusedElementwise: return "FusedElementwise";
               case OpType::FusedMatMulEpilogue: return "FusedMatMulEpilogue";
           }
           return "Unknown";
       }
   };

   // =========================================================================
   // 3. 优化 Pass 体系：常量折叠与死节点修剪
   // =========================================================================
   class ConstantFoldingPass {
   public:
       static void run(ComputationGraph& graph) {
           bool changed = true;
           while (changed) {
               changed = false;
               for (auto& node : graph.Nodes) {
                   if (node->Type == OpType::Constant || node->Type == OpType::Parameter) continue;

                   // 判定所有前驱节点是否均为静态常量
                   bool allInputsConst = !node->Inputs.empty();
                   for (const auto& in : node->Inputs) {
                       if (in->Type != OpType::Constant || !in->StaticData) {
                           allInputsConst = false;
                           break;
                       }
                   }

                   if (allInputsConst) {
                       // 编译期静态求值折叠
                       auto foldedBuffer = evaluateConstantOp(node);
                       node->Type = OpType::Constant;
                       node->StaticData = foldedBuffer;
                       node->Inputs.clear(); // 断开对原有常量子节点的依赖
                       changed = true;
                       break;
                   }
               }
           }
       }

   private:
       static std::shared_ptr<TensorBuffer> evaluateConstantOp(const std::shared_ptr<Node>& node) {
           size_t n = node->OutputShape.numElements();
           std::vector<float> res(n, 0.0f);

           if (node->Type == OpType::Mul) {
               const auto& d0 = node->Inputs[0]->StaticData->Data;
               const auto& d1 = node->Inputs[1]->StaticData->Data;
               for (size_t i = 0; i < n; ++i) {
                   res[i] = d0[i] * d1[i];
               }
           } else if (node->Type == OpType::Add) {
               const auto& d0 = node->Inputs[0]->StaticData->Data;
               const auto& d1 = node->Inputs[1]->StaticData->Data;
               for (size_t i = 0; i < n; ++i) {
                   res[i] = d0[i] + d1[i];
               }
           }
           return std::make_shared<TensorBuffer>(node->OutputShape, std::move(res));
       }
   };

   class DeadNodeEliminationPass {
   public:
       static void run(ComputationGraph& graph) {
           if (!graph.OutputNode) return;

           std::unordered_set<Node*> reachable;
           std::vector<std::shared_ptr<Node>> worklist = { graph.OutputNode };
           reachable.insert(graph.OutputNode.get());

           // 从输出根节点反向追踪到达集
           while (!worklist.empty()) {
               auto curr = worklist.back();
               worklist.pop_back();

               for (const auto& inNode : curr->Inputs) {
                   if (reachable.find(inNode.get()) == reachable.end()) {
                       reachable.insert(inNode.get());
                       worklist.push_back(inNode);
                   }
               }
           }

           // 剔除所有不可达孤岛节点
           std::vector<std::shared_ptr<Node>> liveNodes;
           for (const auto& node : graph.Nodes) {
               if (reachable.find(node.get()) != reachable.end()) {
                   // 清理输出依赖中的死节点引用
                   std::vector<std::shared_ptr<Node>> cleanOutputs;
                   for (const auto& out : node->Outputs) {
                       if (reachable.find(out.get()) != reachable.end()) {
                           cleanOutputs.push_back(out);
                       }
                   }
                   node->Outputs = std::move(cleanOutputs);
                   liveNodes.push_back(node);
               }
           }
           graph.Nodes = std::move(liveNodes);
       }
   };

   // =========================================================================
   // 4. 算子融合引擎 (Operator Fusion Engine)
   // =========================================================================
   class OperatorFusionEngine {
   public:
       static void run(ComputationGraph& graph) {
           fuseElementwiseChain(graph);
           fuseMatMulEpilogue(graph);
           DeadNodeEliminationPass::run(graph); // 融合后物理清理被内联的孤岛
       }

   private:
       // 融合 (Add/Bias -> Mul/Scale -> ReLU) 连续逐元素链
       static void fuseElementwiseChain(ComputationGraph& graph) {
           for (size_t idx = 0; idx < graph.Nodes.size(); ++idx) {
               auto mulNode = graph.Nodes[idx];
               if (mulNode->Type != OpType::Mul) continue;

               // 匹配 Mul(Add(X, Bias), ConstantScale) 模式
               if (mulNode->Inputs.size() != 2) continue;
               auto in0 = mulNode->Inputs[0];
               auto in1 = mulNode->Inputs[1];

               std::shared_ptr<Node> addNode = (in0->Type == OpType::Add) ? in0 : 
                                               ((in1->Type == OpType::Add) ? in1 : nullptr);
               std::shared_ptr<Node> constScale = (in1->Type == OpType::Constant) ? in1 : 
                                                  ((in0->Type == OpType::Constant) ? in0 : nullptr);

               if (!addNode || !constScale || addNode->Outputs.size() > 1) continue;

               float scaleFactor = constScale->StaticData->Data[0];

               // 检查 Mul 下游是否连接单消费者 ReLU
               std::shared_ptr<Node> reluNode = nullptr;
               if (mulNode->Outputs.size() == 1 && mulNode->Outputs[0]->Type == OpType::ReLU) {
                   reluNode = mulNode->Outputs[0];
               }

               // 构建 FusedElementwise 节点
               auto fusedNode = graph.createNode(
                   addNode->Name + "_mul_relu_fused", 
                   OpType::FusedElementwise, 
                   mulNode->OutputShape
               );
               fusedNode->MulScale = scaleFactor;
               fusedNode->HasBias = true;
               fusedNode->HasReLU = (reluNode != nullptr);

               // 继承 Add 的输入 (主张量与偏置张量)
               fusedNode->addInput(addNode->Inputs[0]);
               fusedNode->addInput(addNode->Inputs[1]);

               auto replaceTarget = reluNode ? reluNode : mulNode;
               for (auto& consumer : replaceTarget->Outputs) {
                   for (size_t i = 0; i < consumer->Inputs.size(); ++i) {
                       if (consumer->Inputs[i] == replaceTarget) {
                           consumer->replaceInput(i, fusedNode);
                       }
                   }
               }

               if (graph.OutputNode == replaceTarget) {
                   graph.setGraphOutput(fusedNode);
               }
           }
       }

       // 融合 (MatMul -> FusedElementwise) 为 FusedMatMulEpilogue
       static void fuseMatMulEpilogue(ComputationGraph& graph) {
           for (size_t idx = 0; idx < graph.Nodes.size(); ++idx) {
               auto matmulNode = graph.Nodes[idx];
               if (matmulNode->Type != OpType::MatMul) continue;

               // 要求 MatMul 仅有单一消费者且该消费者为 FusedElementwise
               if (matmulNode->Outputs.size() != 1) continue;
               auto consumer = matmulNode->Outputs[0];
               if (consumer->Type != OpType::FusedElementwise) continue;

               // 构建 FusedMatMulEpilogue 综合算子
               auto fusedMatmul = graph.createNode(
                   matmulNode->Name + "_epilogue_fused", 
                   OpType::FusedMatMulEpilogue, 
                   matmulNode->OutputShape
               );
               fusedMatmul->MulScale = consumer->MulScale;
               fusedMatmul->HasBias = consumer->HasBias;
               fusedMatmul->HasReLU = consumer->HasReLU;

               // 链接 MatMul 的 A, B 矩阵输入
               fusedMatmul->addInput(matmulNode->Inputs[0]);
               fusedMatmul->addInput(matmulNode->Inputs[1]);
               // 链接 Bias 输入 (来自 FusedElementwise 的第 2 操作数)
               fusedMatmul->addInput(consumer->Inputs[1]);

               for (auto& finalConsumer : consumer->Outputs) {
                   for (size_t i = 0; i < finalConsumer->Inputs.size(); ++i) {
                       if (finalConsumer->Inputs[i] == consumer) {
                           finalConsumer->replaceInput(i, fusedMatmul);
                       }
                   }
               }

               if (graph.OutputNode == consumer) {
                   graph.setGraphOutput(fusedMatmul);
               }
           }
       }
   };

   // =========================================================================
   // 5. 底层代码生成器 (Kernel Codegen) 与端到端求值验证
   // =========================================================================
   class KernelCodegen {
   public:
       // 发射等价 C 语言单内核展开代码，直观展现消除中间内存写回 (Materialization)
       static std::string emitFusedKernelCode(const std::shared_ptr<Node>& fusedMatmul) {
           assert(fusedMatmul->Type == OpType::FusedMatMulEpilogue);
           std::ostringstream oss;
           int64_t M = fusedMatmul->OutputShape.Dims[0];
           int64_t N = fusedMatmul->OutputShape.Dims[1];
           // 从输入 0 获取 K 维尺寸
           int64_t K = fusedMatmul->Inputs[0]->OutputShape.Dims[1];

           oss << "// 自动融合生成的单一硬件执行内核: " << fusedMatmul->Name << "
";
           oss << "// 物理收益: 消除中间 MatMul 结果与逐元素结果的显存 (DRAM) 往返读写
";
           oss << "void " << fusedMatmul->Name << "_kernel(
"
               << "    const float* A,    // Shape: [" << M << ", " << K << "]
"
               << "    const float* B,    // Shape: [" << K << ", " << N << "]
"
               << "    const float* Bias, // Shape: [" << N << "]
"
               << "    float* Output      // Shape: [" << M << ", " << N << "]
"
               << ") {
";
           oss << "    for (int m = 0; m < " << M << "; ++m) {
";
           oss << "        for (int n = 0; n < " << N << "; ++n) {
";
           oss << "            // 1. 寄存器内累加求值 (GEMM 阶段)
";
           oss << "            float acc = 0.0f;
";
           oss << "            for (int k = 0; k < " << K << "; ++k) {
";
           oss << "                acc += A[m * " << K << " + k] * B[k * " << N << " + n];
";
           oss << "            }
";
           oss << "            // 2. 尾部算子 (Epilogue) 在寄存器内级联求值
";
           if (fusedMatmul->HasBias) {
               oss << "            acc += Bias[n];
";
           }
           if (fusedMatmul->MulScale != 1.0f) {
               oss << "            acc *= " << fusedMatmul->MulScale << "f;
";
           }
           if (fusedMatmul->HasReLU) {
               oss << "            acc = (acc > 0.0f) ? acc : 0.0f;
";
           }
           oss << "            // 3. 仅向物理内存执行一次最终写回 (Single Store)
";
           oss << "            Output[m * " << N << " + n] = acc;
";
           oss << "        }
";
           oss << "    }
";
           oss << "}
";
           return oss.str();
       }

       // 宿主机端到端仿真执行器，用于数值严密验证
       static std::vector<float> execute(
           const std::shared_ptr<Node>& fusedMatmul,
           const std::vector<float>& A,
           const std::vector<float>& B,
           const std::vector<float>& Bias
       ) {
           assert(fusedMatmul->Type == OpType::FusedMatMulEpilogue);
           int64_t M = fusedMatmul->OutputShape.Dims[0];
           int64_t N = fusedMatmul->OutputShape.Dims[1];
           int64_t K = fusedMatmul->Inputs[0]->OutputShape.Dims[1];

           std::vector<float> Output(M * N, 0.0f);
           for (int64_t m = 0; m < M; ++m) {
               for (int64_t n = 0; n < N; ++n) {
                   float acc = 0.0f;
                   for (int64_t k = 0; k < K; ++k) {
                       acc += A[m * K + k] * B[k * N + n];
                   }
                   if (fusedMatmul->HasBias) {
                       acc += Bias[n];
                   }
                   acc *= fusedMatmul->MulScale;
                   if (fusedMatmul->HasReLU) {
                       acc = std::max(0.0f, acc);
                   }
                   Output[m * N + n] = acc;
               }
           }
           return Output;
       }
   };

   // =========================================================================
   // 6. 综合测试套件
   // =========================================================================
   inline void runCompilerTestSuite() {
       std::cout << "[MiniAICompiler] 启动 AI 计算图融合与降级编译器测试套件...
";

       ComputationGraph graph;

       // 1. 构建初始测试网络:
       //    scale_const = 2.0 * 0.25 (可常量折叠)
       //    mat = MatMul(X, W)
       //    biased = Add(mat, Bias)
       //    scaled = Mul(biased, scale_const)
       //    activated = ReLU(scaled)
       //    dead_debug = Add(activated, 0.0) (死节点)
       //    graph_output = activated
       auto X = graph.createNode("X", OpType::Parameter, TensorShape({2, 3}));
       auto W = graph.createNode("W", OpType::Parameter, TensorShape({3, 2}));
       auto Bias = graph.createNode("Bias", OpType::Parameter, TensorShape({1, 2}));

       auto c1 = graph.createConstant("c1", TensorShape({1}), {2.0f});
       auto c2 = graph.createConstant("c2", TensorShape({1}), {0.25f});
       auto scaleConst = graph.createNode("scale_mul", OpType::Mul, TensorShape({1}));
       scaleConst->addInput(c1);
       scaleConst->addInput(c2);

       auto matmul = graph.createNode("matmul_0", OpType::MatMul, TensorShape({2, 2}));
       matmul->addInput(X);
       matmul->addInput(W);

       auto addBias = graph.createNode("add_bias", OpType::Add, TensorShape({2, 2}));
       addBias->addInput(matmul);
       addBias->addInput(Bias);

       auto mulScale = graph.createNode("mul_scale", OpType::Mul, TensorShape({2, 2}));
       mulScale->addInput(addBias);
       mulScale->addInput(scaleConst);

       auto relu = graph.createNode("relu_act", OpType::ReLU, TensorShape({2, 2}));
       relu->addInput(mulScale);

       // 挂载死节点
       auto deadDebug = graph.createNode("dead_debug", OpType::Add, TensorShape({2, 2}));
       deadDebug->addInput(relu);
       deadDebug->addInput(graph.createConstant("zero", TensorShape({1}), {0.0f}));

       graph.setGraphOutput(relu);

       std::cout << "
--- 优化前图结构 ---
";
       graph.printGraphTopology();

       // 2. 执行常量折叠 Pass
       ConstantFoldingPass::run(graph);
       assert(scaleConst->Type == OpType::Constant);
       assert(scaleConst->StaticData != nullptr);
       assert(std::fabs(scaleConst->StaticData->Data[0] - 0.5f) < 1e-6);
       std::cout << "[Pass 1] 常量折叠验证通过: scale_mul 折叠为常数 0.5f
";

       // 3. 执行死代码消除 Pass
       DeadNodeEliminationPass::run(graph);
       for (const auto& n : graph.Nodes) {
           assert(n->Name != "dead_debug");
       }
       std::cout << "[Pass 2] 死代码消除验证通过: dead_debug 节点成功物理修剪
";

       // 4. 执行多级算子融合引擎
       OperatorFusionEngine::run(graph);
       std::cout << "
--- 算子融合与降级后图结构 ---
";
       graph.printGraphTopology();

       // 验证融合结果
       assert(graph.OutputNode->Type == OpType::FusedMatMulEpilogue);
       assert(graph.OutputNode->HasBias == true);
       assert(graph.OutputNode->HasReLU == true);
       assert(std::fabs(graph.OutputNode->MulScale - 0.5f) < 1e-6);
       std::cout << "[Pass 3] 算子融合引擎验证通过: 成功生成 FusedMatMulEpilogue 综合内核
";

       // 5. 验证底层展开代码生成
       std::string emittedCode = KernelCodegen::emitFusedKernelCode(graph.OutputNode);
       std::cout << "
--- 生成的单内核 C 循环展开源码 ---
" << emittedCode;

       // 6. 数值基准一致性验证
       //    X = [[1, 2, 3], [4, 5, 6]]
       //    W = [[1, 2], [3, 4], [5, 6]]
       //    Bias = [-10, 5]
       //    MatMul(X, W):
       //      Row 0: [1*1 + 2*3 + 3*5, 1*2 + 2*4 + 3*6] = [22, 28]
       //      Row 1: [4*1 + 5*3 + 6*5, 4*2 + 5*4 + 6*6] = [49, 64]
       //    + Bias:
       //      Row 0: [12, 33]
       //      Row 1: [39, 69]
       //    * 0.5:
       //      Row 0: [6, 16.5]
       //      Row 1: [19.5, 34.5]
       //    ReLU: 均为正，保持原值
       std::vector<float> matA = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
       std::vector<float> matB = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
       std::vector<float> bias = {-10.0f, 5.0f};

       auto result = KernelCodegen::execute(graph.OutputNode, matA, matB, bias);
       assert(std::fabs(result[0] - 6.0f) < 1e-5);
       assert(std::fabs(result[1] - 16.5f) < 1e-5);
       assert(std::fabs(result[2] - 19.5f) < 1e-5);
       assert(std::fabs(result[3] - 34.5f) < 1e-5);
       std::cout << "[Pass 4] 端到端数值验证通过: 输出完全符合数学物理预期
";

       std::cout << "[MiniAICompiler] 全部测试用例无断言失败，执行圆满成功。
";
   }

   } // namespace mini_ai_compiler
