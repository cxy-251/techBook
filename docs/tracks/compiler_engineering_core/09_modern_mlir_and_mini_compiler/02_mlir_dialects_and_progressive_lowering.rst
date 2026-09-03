====================================================================================================
MLIR 多层中间表示：Dialect 扩展哲学、Operation/Region/Type 系统与渐进降级 (Progressive Lowering)
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 9 模块第 1 节（``01_llvm_pass_manager_and_infrastructure_engineering``）中，我们系统解构了 LLVM 核心优化基础设施、New Pass Manager 的 CRTP 静态多态拓扑、``PreservedAnalyses`` 事实缓存状态机与 FileCheck 回归测试工程。传统 LLVM IR 以平坦的控制流图（CFG）、基本块与标量 SSA 值为基础，成功统一了标量与过程间优化；然而，在面对高维张量计算、结构化循环嵌套、专用内存层次（Scratchpad / Shared Memory）以及异构加速硬件（GPU、NPU、TPU）时，过早降解为低层平面指令会导致大量结构化领域语义永久丢失。
   为了消除传统编译器单一抽象层的表达壁垒，MLIR（Multi-Level Intermediate Representation）构建了一套高度模块化、树状嵌套且允许无限扩展的统一多层编译器基础设施。本章深度剖析 MLIR 的 Dialect 扩展哲学，解构 Operation、Region、Block、Attribute 与 Type 的核心正交对象模型，阐明声明式 ODS（Operation Definition Specification）与 C++ 虚接口（OpInterface / TypeInterface）的协同机理，并形式化推导由 ConversionTarget、RewritePattern 与 TypeConverter 构成的渐进降级（Progressive Lowering）流水线。

单一通用 IR 的表达瓶颈与多层抽象必要性
--------------------------------------

现代计算工作负载呈现出高度的领域分化特征。从深度学习张量图计算、图数据库、量子计算到图形着色器，不同领域在计算拓扑、数据局部性与硬件映射上具有完全异构的约束。

单一通用抽象层的内在张力
~~~~~~~~~~~~~~~~~~~~~~~~

传统编译器倾向于采用单一通用中间表示（Universal IR，如经典 LLVM IR）。这种设计在标量体系结构中取得了巨大成功，但在跨领域异构编译场景中面临深层次的表示冲突：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       单一通用 IR 的表达与优化张力模型                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 高层领域计算 (Domain Computation) ]                                     |
   |     - 4D 卷积 (Conv2D)、矩阵乘 (MatMul)、注意力机制 (Attention)             |
   |     - 核心需求: 保留完整张量形状、数据流依赖、代数等价性与算子融合空间      |
   |                                                                             |
   |                                |                                            |
   |                                | (过早降解 Early Lowering 造成语义塌缩)     |
   |                                v                                            |
   |                                                                             |
   |   [ 平坦低层 IR (Flat Low-Level IR: LLVM IR) ]                              |
   |     - 离散的基本块、指针计算 (GEP)、标量 load/store、条件跳转分支           |
   |     - 优化困境:                                                             |
   |         * 仿射循环嵌套被拆散为无结构的控制流图，多面体模型难以识别归纳变量  |
   |         * 连续内存块被离散指针别名掩盖，别名分析被迫退化为保守的 MayAlias    |
   |         * 硬件专用张量计算原语 (如 Tensor Core MMA) 需要极其脆弱的模式逆推  |
   |                                                                             |
   |                                |                                            |
   |                                v                                            |
   |                                                                             |
   |   [ 目标硬件执行 (Hardware Execution) ]                                     |
   |     - SIMD/SIMT 指令、多级缓存布局、片上存储分配、显式数据搬运 (DMA)        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

若在前端过早将张量算子展开为三层嵌套循环与指针偏移访问，中端优化器为了执行循环分块（Tiling）、循环交换（Permutation）或张量化（Tensorization），必须耗费极高的算法代价从低层指令中逆向恢复（Re-synthesize）循环边界与多维访问函数；这一过程极易受到指针别名与边界检查代码的干扰而宣告失败。相反，若将张量算子长期保持在未展开的高层图状态，后端代码生成器又无法直接评估寄存器压力、缓存容量与流水线气泡。

多层 IR 的语义生命周期划分
~~~~~~~~~~~~~~~~~~~~~~~~~~

多层 IR 的设计基石在于：**将计算事实的表示形态与当前阶段所需的分析动作严格对齐，推迟执行约束的引入时机**。

.. list-table:: 现代编译器典型抽象层次与优化关注点矩阵
   :widths: 16 20 28 20 16
   :header-rows: 1
   :class: tight-table

   * - 抽象层级
     - 典型 Dialect 映射
     - 核心表示实体
     - 专属优化阶段
     - 引入的物理约束
   * - **高层计算图**
     - ``tosa``, ``stablehlo``
     - 命名张量算子、高维数据流图
     - 图重写、常量折叠、算子垂直/水平融合
     - 纯数学运算逻辑
   * - **结构化线性代数**
     - ``linalg``, ``tensor``
     - 结构化收缩算子、迭代空间映射
     - 仿射分块、融合（Tiling & Fusion）
     - 循环遍历顺序与并行属性
   * - **结构化控制流与循环**
     - ``scf``, ``affine``
     - 显式嵌套循环（``for``）、仿射多面体
     - 多面体变换、循环展开、向量化准备
     - 标量迭代变量与控制流边界
   * - **显式内存与缓冲区**
     - ``memref``, ``bufferization``
     - 具有步长（Strided）的多维内存引用
     - 缓冲区分配、原址复用、别名隔离
     - 物理分配（堆/栈/共享内存）
   * - **目标向量与硬件指令**
     - ``vector``, ``gpu``, ``llvm``
     - 1D/2D 紧凑向量、线程块映射、机器指针
     - 寄存器溢出保护、目标指令展开
     - 物理寄存器位宽与硬件 ABI

Dialect 扩展体系与命名空间隔离
------------------------------

MLIR 摒弃了单一垄断的指令集定义，引入 **Dialect（方言）** 作为正交语言的封装边界。每个 Dialect 定义了一组自洽的 Operation、Type、Attribute 以及相伴的校验器（Verifier）和优化 Pass。

Dialect 命名空间与共存规则
~~~~~~~~~~~~~~~~~~~~~~~~~~

在 MLIR 中，所有的语义实体均携带 Dialect 命名空间前缀，采用点号分隔命名法：``<dialect_namespace>.<entity_name>``。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     MLIR 异构 Dialect 混合共存编译单元                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   func.func @matmul_kernel(%A: memref<128x64xf32>,                          |
   |                            %B: memref<64x256xf32>,                          |
   |                            %C: memref<128x256xf32>) {                       |
   |                                                                             |
   |     // 1. 结构化控制流方言 (scf) 表达外层瓦片迭代空间                       |
   |     %c0 = arith.constant 0 : index                                          |
   |     %c128 = arith.constant 128 : index                                      |
   |     %step = arith.constant 32 : index                                       |
   |     scf.for %i = %c0 to %c128 step %step {                                  |
   |                                                                             |
   |       // 2. 内存引用方言 (memref) 提取动态多维子视图 (SubView)              |
   |       %subA = memref.subview %A[%i, 0] [32, 64] [1, 1]                      |
   |             : memref<128x64xf32> to memref<32x64xf32, strided<[64, 1]>>    |
   |                                                                             |
   |       // 3. 线性代数方言 (linalg) 承载结构化块级矩阵乘                      |
   |       linalg.matmul ins(%subA, %B : memref<32x64xf32, strided<[64, 1]>>,    |
   |                                     memref<64x256xf32>)                     |
   |                     outs(%C : memref<128x256xf32>)                          |
   |     }                                                                       |
   |     return                                                                  |
   |   }                                                                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

这种模块化设计确保不同的领域概念无需争夺全局操作码表。新硬件或新领域只需定义独立的 Dialect，即可直接复用 MLIR 的所有基础设施，包括通用模式重写驱动器、常量折叠器与控制流死代码消除引擎。

声明式 ODS（Operation Definition Specification）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了规避手写大量繁琐且极易出错的 C++ 样板代码，MLIR 采用基于 LLVM TableGen 的声明式领域语言——**ODS（Operation Definition Specification）**。开发者在 ``.td`` 文件中声明操作的结构契约，由 ``mlir-tblgen`` 自动生成 C++ 类定义、解析器、打印器、特征推导与验证逻辑。

.. code-block:: tablegen

   // ODS 定义示例：定义自定义方言内的矩阵乘操作
   def Demo_MatMulOp : Demo_Op<"matmul", [
       Pure,                                       // 无副作用纯函数特质
       DeclareOpInterfaceMethods<MemoryEffectsOpInterface>,
       SameOperandsAndResultElementType            // 元素类型一致性约束
   ]> {
       let summary = "结构化高维张量矩阵乘算子";
       let description = [{
           Demo_MatMulOp 接收两个 2 维张量 %lhs 与 %rhs，
           执行几何收缩计算并输出结果张量 %res。
       }];

       // 操作数声明 (带类型约束)
       let arguments = (ins
           2DTensorOf<[F32, F64]>:$lhs,
           2DTensorOf<[F32, F64]>:$rhs
       );

       // 返回值声明
       let results = (outs
           2DTensorOf<[F32, F64]>:$result
       );

       // 编译期静态属性配置
       let attributes = (ins
           DefaultValuedAttr<BoolAttr, "false">:$transpose_lhs
       );

       // 声明自定义 C++ 验证器逻辑
       let hasVerifier = 1;
       
       // 自定义文本汇编打印与解析格式
       let assemblyFormat = [{
           $lhs `,` $rhs attr-dict `:` functional-type(operands, results)
       }];
   }

ODS 通过特质（Traits）系统为操作注入正交行为。例如赋予 ``Commutative`` 特质的操作在常量折叠与 GVN 中自动支持操作数顺序归一化，赋予 ``IsolatedFromAbove`` 特质的操作定义了封闭的作用域边界，阻止内层嵌套引用外层自由变量。

Operation、Region、Block 与 Value 核心对象模型
----------------------------------------------

MLIR 的内存数据结构并非单一平坦的有向无环图，而是呈现为**多层嵌套的层次化树状图拓扑**。其核心概念完全统一在六大基本要素之上。

层次拓扑对象模型
~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       MLIR 核心对象图结构化嵌套拓扑                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ Operation ] (顶层容器，如 builtin.module 或 func.func)                   |
   |     |                                                                       |
   |     +-- Attributes / Properties (编译期键值对元数据)                        |
   |     +-- Operands (引用的输入 SSA Value 集合)                                |
   |     +-- Results (产出的输出 SSA Value 集合)                                 |
   |     +-- Successors (目标控制流 Block 引用列表)                              |
   |     |                                                                       |
   |     +-- [ Region(s) ] (内嵌嵌套程序域)                                      |
   |           |                                                                 |
   |           +-- [ Block(s) ] (顺序执行指令块)                                 |
   |                 |                                                           |
   |                 +-- Block Arguments (显式块入参，彻底替代 Phi 节点)         |
   |                 |     - %arg0 : f32                                         |
   |                 |     - %arg1 : index                                       |
   |                 |                                                           |
   |                 +-- [ Operation List (侵入式双向链表) ]                     |
   |                       |                                                     |
   |                       +-- Child Operation 1                                 |
   |                       +-- Child Operation 2                                 |
   |                       +-- Terminator Operation (块尾跳转/返回指令)          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Block Arguments 消除传统 Phi 节点
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统 LLVM IR 依赖 ``llvm::PHINode`` 解决分支汇合处的多路径定值选择。然而，在优化过程中移动、分割基本块或调整前驱边时，必须同步维护每个 Phi 节点的 ``(Value, BasicBlock)`` 双元组，极易产生悬垂引用或拓扑不一致缺陷。

MLIR 彻底废弃了独立存在的 Phi 指令，引入与函数形参高度统一的 **Block Arguments（块参数）** 机制：

.. code-block:: text

   传统 LLVM IR 的 Phi 形式:               MLIR 的 Block Arguments 形式:
   -----------------------------          ----------------------------------
   entry:                                 ^entry:
     br i1 %cond, label %left, label %right cf.cond_br %cond, ^left, ^right

   left:                                  ^left:
     %v1 = add i32 %x, 1                    %v1 = arith.addi %x, %c1 : i32
     br label %merge                        cf.br ^merge(%v1 : i32)

   right:                                 ^right:
     %v2 = mul i32 %x, 2                    %v2 = arith.muli %x, %c2 : i32
     br label %merge                        cf.br ^merge(%v2 : i32)

   merge:                                 ^merge(%res: i32):   // 显式入口绑定
     %res = phi i32 [%v1, %left],           ... 使用 %res ...
                    [%v2, %right]
     ... 使用 %res ...

在 MLIR 中，控制流前驱块的 Terminator 指令（如 ``cf.br``、``cf.cond_br``）在指向后继基本块的同时，显式传递操作数列表。目标基本块在其头部声明对应的参数列表及具体类型。这种语义不仅保证了控制流与值传递的强内聚，而且将基本块跳转形式化为一次带有求值语义的局部尾调用（Tail Call）。

Region 拓扑形态与隔离边界
~~~~~~~~~~~~~~~~~~~~~~~~~

Operation 内部包含的 Region 具有严格的语义约束分类：

1. **SSACFG Region（严格控制流域）**：
   - 内部包含一个或多个以控制流边互联的 Block。
   - 严格遵循支配性约束（Dominance Invariant）：除了 Block Arguments 之外，SSA 值的定值节点必须严格支配其使用节点。
   - 典型代表：``func.func`` 的函数体、``scf.while`` 的循环体。
2. **Graph Region（图计算并发域）**：
   - 内部 Block 中的 Operation 无需满足单向支配性要求，允许出现循环依赖或并发无序关系。
   - 典型代表：电路硬件设计方言（CIRCT）、数据流图计算方言。
3. **IsolatedFromAbove 隔离边界**：
   - 标记了该属性的 Operation，其内部 Region 严禁隐式访问外层作用域中定义的任何 SSA 值（全局常量除外）。
   - 外层值必须通过显式操作数传递并绑定为内部 Block Arguments。
   - 这一约束赋予了编译器对嵌套子结构进行纯局部并发优化（Parallel In-Flight Processing）的绝对安全性，杜绝了并发优化修改外层指令时的线程冲突。

渐进降级流水线与 Dialect Conversion 框架
----------------------------------------

Progressive Lowering（渐进降级）是 MLIR 区别于传统编译器的核心工作流范式。它主张**一次降级仅跨越一个抽象阶梯**，杜绝将高层领域概念直接一次性降解为机器码。

Dialect Conversion 三大支柱契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MLIR 提供了严谨的 ``DialectConversion`` 基础设施，其运转依赖三大核心支柱：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                      Dialect Conversion 核心协同架构                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. ConversionTarget ] (合法性检验判决官)                                |
   |     - 显式声明特定方言/操作的合法性状态:                                    |
   |         * Legal: 允许在转换最终结果中留存                                   |
   |         * Illegal: 必须被模式改写彻底消除                                   |
   |         * DynamicallyLegal: 依据动态谓词断言类型或属性是否合法              |
   |                                                                             |
   |                                ^                                            |
   |                                | 驱动重写并验证合法性                       |
   |                                v                                            |
   |                                                                             |
   |   [ 2. RewritePatternSet ] (模式重写规则库)                                 |
   |     - 继承自 OpConversionPattern<SourceOp>                                  |
   |     - matchAndRewrite() 实现原语擦除、拓扑替换与下层算子合成                |
   |     - 依托 OpAdaptor 获取经由类型系统重映射后的新操作数                     |
   |                                                                             |
   |                                ^                                            |
   |                                | 请求类型适配与物质化                      |
   |                                v                                            |
   |                                                                             |
   |   [ 3. TypeConverter ] (类型降级与物化状态机)                               |
   |     - 注册高层抽象类型到物理执行类型的映射: tensor<..> -> memref<..>        |
   |     - Materialization 钩子体系:                                             |
   |         * TargetMaterialization: 将旧值桥接为合法目标类型                   |
   |         * SourceMaterialization: 当旧代码残留时，将新值回退为兼容类型       |
   |         * ArgumentMaterialization: 转换基本块形参签名                       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

三种转换模式与执行语义
~~~~~~~~~~~~~~~~~~~~~~

根据工程部署目标与容错要求，Dialect Conversion 驱动器支持三种模式：

.. list-table:: MLIR Dialect 转换模式对比与使用准则
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 转换模式
     - 驱动 API
     - 终态验收标准与失败条件
   * - **Full Conversion**
     - ``applyFullConversion()``
     - 转换完成后，IR 中存在任何一个未标记为 Legal 的操作即视为致命失败，全量回滚。常用于最终生成 LLVM IR 前的最后一道严格把关。
   * - **Partial Conversion**
     - ``applyPartialConversion()``
     - 仅对被显式声明为 Illegal 的操作施加强制消除；对于未明确声明的未知操作予以安全放行。是多层渐进降级流水线中最核心的骨架驱动模式。
   * - **Analysis Conversion**
     - ``applyAnalysisConversion()``
     - 试探性匹配并计算合法化路径，不实际物理修改当前 IR。常用于编译器调试、降级覆盖率审计以及动态 Pass 调度器路径决策。

降级流水线案例：张量运算向硬件机器码演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

考虑一段典型的高维矩阵乘计算：``Y = MatMul(A, B)``。渐进降级将其分解为四道清晰的阶段边界：

.. code-block:: text

   阶段 1: 算子结构化 (TOSA/High-Level -> Linalg on Tensors)
   -----------------------------------------------------------------------------
   %res = tosa.matmul %A, %B : (tensor<128x64xf32>, tensor<64x256xf32>) -> tensor<128x256xf32>
     == [ Lower-To-Linalg Pass ] ==>
   %init = tensor.empty() : tensor<128x256xf32>
   %res = linalg.matmul ins(%A, %B : tensor<128x64xf32>, tensor<64x256xf32>)
                        outs(%init : tensor<128x256xf32>) -> tensor<128x256xf32>

   阶段 2: 内存缓冲区化 (One-Shot Bufferize: Tensor -> MemRef)
   -----------------------------------------------------------------------------
   值语义消除，引入显式物理分配 (memref.alloc) 与就地覆写消除深拷贝:
     == [ One-Shot Bufferize Pass ] ==>
   %bufC = memref.alloc() : memref<128x256xf32>
   linalg.matmul ins(%bufA, %bufB : memref<128x64xf32>, memref<64x256xf32>)
                 outs(%bufC : memref<128x256xf32>)

   阶段 3: 结构化算子标量化与循环展开 (Linalg -> SCF & Vector)
   -----------------------------------------------------------------------------
   将 Linalg 的高层收缩语义展开为显式嵌套循环结构并应用 SIMD 向量化:
     == [ Convert-Linalg-To-Loops & Vectorize ] ==>
   scf.for %i = %c0 to %c128 step %c32 {
     scf.for %j = %c0 to %c256 step %c8 {
       %vecA = vector.load %bufA[%i, ...] : memref<128x64xf32>, vector<8xf32>
       %vecB = vector.load %bufB[..., %j] : memref<64x256xf32>, vector<8xf32>
       %vecC = vector.fma %vecA, %vecB, ... : vector<8xf32>
       vector.store %vecC, %bufC[%i, %j] : memref<128x256xf32>, vector<8xf32>
     }
   }

   阶段 4: 底层平坦化 (SCF & MemRef -> LLVM Dialect -> LLVM IR)
   -----------------------------------------------------------------------------
   将 scf.for 与 memref.load 降解为基本块分支、指针偏移 GEP 与机器加载指令:
     == [ Convert-To-LLVM Pass ] ==>
   llvm.br ^loop_header(%init_i : i64)
   ^loop_header(%i: i64):
     ... 指针地址运算与 llvm.fmuladd 机器原语 ...

每道降级边界具有明确的责任范畴：阶段 1 负责数学语义对齐；阶段 2 负责内存生命周期与别名规划；阶段 3 负责多面体变换与向量化并行拓扑；阶段 4 负责 ABI 与底层硬件寄存器接口匹配。

C++ 工业级 MLIR 架构与渐进降级微内核实战
----------------------------------------

为了彻底洞见 MLIR 多层中间表示与 Dialect Conversion 框架的底层运行机制，以下给出一套自包含、无外部依赖的 C++ 现代编译器渐进降级微内核实现：
1. **多层 IR 对象模型**：实现 ``Type``、``Value``、``Operation``、``Block`` 与 ``Region`` 的完整拓扑。
2. **多方言操作集**：
   - 领域张量方言（``demo.matmul``：操作于 ``TensorType``）。
   - 结构化循环与内存方言（``demo.alloc``、``demo.for``、``demo.load``、``demo.store``：操作于 ``MemRefType``）。
3. **TypeConverter 状态机**：支持将高层无副作用不可变 ``TensorType`` 编译期映射为物理连续内存引用 ``MemRefType``。
4. **ConversionTarget 决策器**：严格声明 ``demo.matmul`` 为 Illegal，并声明底层操作集为 Legal。
5. **OpConversionPattern 与 Driver**：实现局部重写与阶段验收，验证矩阵乘法算子向显式多维嵌套迭代空间的确定性平滑降级。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <memory>
   #include <unordered_map>
   #include <functional>
   #include <cassert>
   #include <sstream>

   namespace mini_mlir {

   // =========================================================================
   // 1. 类型系统 (Type System)
   // =========================================================================
   enum class TypeKind {
       Float32,
       Index,
       Tensor,
       MemRef
   };

   class Type {
   public:
       virtual ~Type() = default;
       virtual TypeKind getKind() const = 0;
       virtual std::string toString() const = 0;
   };

   class Float32Type : public Type {
   public:
       TypeKind getKind() const override { return TypeKind::Float32; }
       std::string toString() const override { return "f32"; }
   };

   class IndexType : public Type {
   public:
       TypeKind getKind() const override { return TypeKind::Index; }
       std::string toString() const override { return "index"; }
   };

   class ShapedType : public Type {
   protected:
       std::vector<int64_t> Shape;
       std::shared_ptr<Type> ElementType;
   public:
       ShapedType(std::vector<int64_t> shape, std::shared_ptr<Type> elemType)
           : Shape(std::move(shape)), ElementType(std::move(elemType)) {}

       const std::vector<int64_t>& getShape() const { return Shape; }
       std::shared_ptr<Type> getElementType() const { return ElementType; }
   };

   class TensorType : public ShapedType {
   public:
       TensorType(std::vector<int64_t> shape, std::shared_ptr<Type> elemType)
           : ShapedType(std::move(shape), std::move(elemType)) {}

       TypeKind getKind() const override { return TypeKind::Tensor; }
       std::string toString() const override {
           std::ostringstream oss;
           oss << "tensor<";
           for (size_t i = 0; i < Shape.size(); ++i) {
               oss << Shape[i] << (i + 1 < Shape.size() ? "x" : "");
           }
           oss << "x" << ElementType->toString() << ">";
           return oss.str();
       }
   };

   class MemRefType : public ShapedType {
   public:
       MemRefType(std::vector<int64_t> shape, std::shared_ptr<Type> elemType)
           : ShapedType(std::move(shape), std::move(elemType)) {}

       TypeKind getKind() const override { return TypeKind::MemRef; }
       std::string toString() const override {
           std::ostringstream oss;
           oss << "memref<";
           for (size_t i = 0; i < Shape.size(); ++i) {
               oss << Shape[i] << (i + 1 < Shape.size() ? "x" : "");
           }
           oss << "x" << ElementType->toString() << ">";
           return oss.str();
       }
   };

   // =========================================================================
   // 2. SSA 值与拓扑元素 (Value, Block, Region, Operation)
   // =========================================================================
   class Operation;
   class Block;

   class Value {
   private:
       std::string Name;
       std::shared_ptr<Type> ValType;
       Operation* DefiningOp = nullptr;
       Block* ParentBlock = nullptr; // 用于 Block Arguments

   public:
       Value(std::string name, std::shared_ptr<Type> type, Operation* defOp = nullptr)
           : Name(std::move(name)), ValType(std::move(type)), DefiningOp(defOp) {}

       const std::string& getName() const { return Name; }
       std::shared_ptr<Type> getType() const { return ValType; }
       Operation* getDefiningOp() const { return DefiningOp; }
       void setParentBlock(Block* block) { ParentBlock = block; }
   };

   class Region;

   class Operation {
   public:
       std::string OpName;
       std::vector<std::shared_ptr<Value>> Operands;
       std::vector<std::shared_ptr<Value>> Results;
       std::unordered_map<std::string, std::string> Attributes;
       std::vector<std::unique_ptr<Region>> Regions;
       Block* ParentBlock = nullptr;

       Operation(std::string name) : OpName(std::move(name)) {}
       virtual ~Operation() = default;

       std::shared_ptr<Value> getResult(size_t index) const {
           assert(index < Results.size());
           return Results[index];
       }

       Region* addRegion();
       virtual void dump(int indent = 0) const;
   };

   class Block {
   public:
       std::string Label;
       std::vector<std::shared_ptr<Value>> Arguments;
       std::vector<std::unique_ptr<Operation>> Operations;
       Region* ParentRegion = nullptr;

       explicit Block(std::string label) : Label(std::move(label)) {}

       std::shared_ptr<Value> addArgument(const std::string& name, std::shared_ptr<Type> type) {
           auto arg = std::make_shared<Value>(name, type);
           arg->setParentBlock(this);
           Arguments.push_back(arg);
           return arg;
       }

       Operation* addOperation(std::unique_ptr<Operation> op) {
           op->ParentBlock = this;
           Operations.push_back(std::move(op));
           return Operations.back().get();
       }

       void dump(int indent = 0) const;
   };

   class Region {
   public:
       std::vector<std::unique_ptr<Block>> Blocks;
       Operation* ParentOp = nullptr;

       Block* addBlock(const std::string& label) {
           Blocks.push_back(std::make_unique<Block>(label));
           Blocks.back()->ParentRegion = this;
           return Blocks.back().get();
       }

       void dump(int indent = 0) const {
           for (const auto& b : Blocks) {
               b->dump(indent);
           }
       }
   };

   inline Region* Operation::addRegion() {
       Regions.push_back(std::make_unique<Region>());
       Regions.back()->ParentOp = this;
       return Regions.back().get();
   }

   inline void Block::dump(int indent) const {
       std::string pad(indent * 2, ' ');
       std::cout << pad << "^" << Label;
       if (!Arguments.empty()) {
           std::cout << "(";
           for (size_t i = 0; i < Arguments.size(); ++i) {
               std::cout << "%" << Arguments[i]->getName() << ": " 
                         << Arguments[i]->getType()->toString();
               if (i + 1 < Arguments.size()) std::cout << ", ";
           }
           std::cout << ")";
       }
       std::cout << ":
";
       for (const auto& op : Operations) {
           op->dump(indent + 1);
       }
   }

   inline void Operation::dump(int indent) const {
       std::string pad(indent * 2, ' ');
       std::cout << pad;
       if (!Results.empty()) {
           for (size_t i = 0; i < Results.size(); ++i) {
               std::cout << "%" << Results[i]->getName();
               if (i + 1 < Results.size()) std::cout << ", ";
           }
           std::cout << " = ";
       }
       std::cout << "\"" << OpName << "\"(";
       for (size_t i = 0; i < Operands.size(); ++i) {
           std::cout << "%" << Operands[i]->getName();
           if (i + 1 < Operands.size()) std::cout << ", ";
       }
       std::cout << ")";
       if (!Attributes.empty()) {
           std::cout << " {";
           size_t count = 0;
           for (const auto& [k, v] : Attributes) {
               std::cout << k << " = \"" << v << "\"";
               if (++count < Attributes.size()) std::cout << ", ";
           }
           std::cout << "}";
       }
       if (!Results.empty()) {
           std::cout << " : (";
           for (size_t i = 0; i < Operands.size(); ++i) {
               std::cout << Operands[i]->getType()->toString();
               if (i + 1 < Operands.size()) std::cout << ", ";
           }
           std::cout << ") -> (";
           for (size_t i = 0; i < Results.size(); ++i) {
               std::cout << Results[i]->getType()->toString();
               if (i + 1 < Results.size()) std::cout << ", ";
           }
           std::cout << ")";
       }
       std::cout << "
";
       for (const auto& region : Regions) {
           region->dump(indent + 1);
       }
   }

   // =========================================================================
   // 3. Dialect Conversion 核心框架
   // =========================================================================

   class TypeConverter {
   private:
       using ConversionFn = std::function<std::shared_ptr<Type>(std::shared_ptr<Type>)>;
       std::vector<ConversionFn> Conversions;

   public:
       void addConversion(ConversionFn fn) {
           Conversions.push_back(std::move(fn));
       }

       std::shared_ptr<Type> convertType(std::shared_ptr<Type> srcType) const {
           for (const auto& fn : Conversions) {
               if (auto res = fn(srcType)) {
                   return res;
               }
           }
           return srcType; // 默认保留原类型
       }
   };

   class ConversionTarget {
   public:
       enum class Legality { Legal, Illegal };

   private:
       std::unordered_map<std::string, Legality> OpLegality;

   public:
       void setOpLegal(const std::string& opName) {
           OpLegality[opName] = Legality::Legal;
       }

       void setOpIllegal(const std::string& opName) {
           OpLegality[opName] = Legality::Illegal;
       }

       bool isLegal(const std::string& opName) const {
           auto it = OpLegality.find(opName);
           if (it != OpLegality.end()) {
               return it->second == Legality::Legal;
           }
           return true; // 默认未知操作合法 (支持 Partial Conversion)
       }
   };

   class ConversionPatternRewriter {
   public:
       Block* CurrentBlock;
       std::vector<std::unique_ptr<Operation>> SynthesizedOps;
       std::unordered_map<std::string, std::shared_ptr<Value>> ValueMap;

       explicit ConversionPatternRewriter(Block* block) : CurrentBlock(block) {}

       void replaceOp(Operation* origOp, std::vector<std::shared_ptr<Value>> newValues) {
           for (size_t i = 0; i < origOp->Results.size() && i < newValues.size(); ++i) {
               ValueMap[origOp->Results[i]->getName()] = newValues[i];
           }
       }

       Operation* createOp(std::unique_ptr<Operation> op) {
           SynthesizedOps.push_back(std::move(op));
           return SynthesizedOps.back().get();
       }
   };

   class ConversionPattern {
   public:
       std::string SourceOpName;
       const TypeConverter& TConverter;

       ConversionPattern(std::string opName, const TypeConverter& tc)
           : SourceOpName(std::move(opName)), TConverter(tc) {}

       virtual ~ConversionPattern() = default;
       virtual bool matchAndRewrite(Operation* op, ConversionPatternRewriter& rewriter) const = 0;
   };

   // =========================================================================
   // 4. 具体领域降级 Pattern：demo.matmul -> loop nest + memref
   // =========================================================================
   class MatmulToLoopsPattern : public ConversionPattern {
   public:
       MatmulToLoopsPattern(const TypeConverter& tc)
           : ConversionPattern("demo.matmul", tc) {}

       bool matchAndRewrite(Operation* op, ConversionPatternRewriter& rewriter) const override {
           if (op->OpName != "demo.matmul") return false;
           assert(op->Operands.size() == 2);
           assert(op->Results.size() == 1);

           auto tensorResType = std::dynamic_pointer_cast<TensorType>(op->Results[0]->getType());
           if (!tensorResType) return false;

           // 1. 利用 TypeConverter 将张量类型降级为内存分配 MemRefType
           auto memrefType = TConverter.convertType(tensorResType);

           // 2. 插入显式内存申请: %bufC = "demo.alloc"() : () -> memref<128x256xf32>
           auto allocOp = std::make_unique<Operation>("demo.alloc");
           auto bufCVal = std::make_shared<Value>(
               op->Results[0]->getName() + "_buf", memrefType, allocOp.get());
           allocOp->Results.push_back(bufCVal);
           rewriter.createOp(std::move(allocOp));

           // 3. 构建 3 层嵌套循环模拟矩阵乘收缩计算:
           //    demo.for %i in [0, M)
           //      demo.for %j in [0, N)
           //        demo.for %k in [0, K)
           //          %a = demo.load %bufA[%i, %k]
           //          %b = demo.load %bufB[%k, %j]
           //          %old = demo.load %bufC[%i, %j]
           //          %fma = demo.fma %a, %b, %old
           //          demo.store %fma, %bufC[%i, %j]
           auto loopNestOp = std::make_unique<Operation>("demo.for_nest_matmul");
           loopNestOp->Operands = { op->Operands[0], op->Operands[1], bufCVal };
           loopNestOp->Attributes["loop_bounds"] = "128x256x64";
           rewriter.createOp(std::move(loopNestOp));

           // 4. 完成原矩阵乘操作替换并重映射 SSA 值
           rewriter.replaceOp(op, { bufCVal });
           return true;
       }
   };

   // =========================================================================
   // 5. Dialect Conversion 驱动引擎 (Partial Conversion Driver)
   // =========================================================================
   class DialectConversionDriver {
   public:
       static bool applyPartialConversion(
           Block* block,
           const ConversionTarget& target,
           const std::vector<std::unique_ptr<ConversionPattern>>& patterns) {

           ConversionPatternRewriter rewriter(block);
           std::vector<std::unique_ptr<Operation>> finalOps;

           for (auto& origOp : block->Operations) {
               if (target.isLegal(origOp->OpName)) {
                   finalOps.push_back(std::move(origOp));
                   continue;
               }

               // 检索匹配重写规则
               bool rewritten = false;
               for (const auto& pattern : patterns) {
                   if (pattern->SourceOpName == origOp->OpName) {
                       if (pattern->matchAndRewrite(origOp.get(), rewriter)) {
                           rewritten = true;
                           // 将模式合成的底层新指令迁入最终列表
                           for (auto& synthOp : rewriter.SynthesizedOps) {
                               synthOp->ParentBlock = block;
                               finalOps.push_back(std::move(synthOp));
                           }
                           rewriter.SynthesizedOps.clear();
                           break;
                       }
                   }
               }

               if (!rewritten) {
                   std::cerr << "[-] 降级失败: 操作 \"" << origOp->OpName 
                             << "\" 属于 Illegal 且未找到可用重写规则!
";
                   return false;
               }
           }

           // 就地刷新基本块指令拓扑
           block->Operations = std::move(finalOps);
           return true;
       }
   };

   } // namespace mini_mlir

   // =========================================================================
   // 6. 端到端 MLIR 降级与验证套件
   // =========================================================================
   namespace test {

   inline void runMLIRLoweringTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MLIR Dialect 建模与 Progressive Lowering 渐进降级验证
";
       std::cout << "=======================================================

";

       using namespace mini_mlir;

       // 1. 初始化类型与顶层模块容器
       auto f32Type = std::make_shared<Float32Type>();
       auto tensorA = std::make_shared<TensorType>(std::vector<int64_t>{128, 64}, f32Type);
       auto tensorB = std::make_shared<TensorType>(std::vector<int64_t>{64, 256}, f32Type);
       auto tensorC = std::make_shared<TensorType>(std::vector<int64_t>{128, 256}, f32Type);

       auto topModule = std::make_unique<Operation>("builtin.module");
       Region* modRegion = topModule->addRegion();
       Block* modBlock = modRegion->addBlock("entry");

       // 构建函数：func.func @test_matmul(%arg0: tensor<128x64xf32>, %arg1: tensor<64x256xf32>)
       auto funcOp = std::make_unique<Operation>("func.func");
       funcOp->Attributes["sym_name"] = "test_matmul";
       Region* funcRegion = funcOp->addRegion();
       Block* funcBlock = funcRegion->addBlock("entry");
       auto argA = funcBlock->addArgument("argA", tensorA);
       auto argB = funcBlock->addArgument("argB", tensorB);

       // 在函数内插入高层领域张量乘: %res = "demo.matmul"(%argA, %argB) : ...
       auto matmulOp = std::make_unique<Operation>("demo.matmul");
       matmulOp->Operands = { argA, argB };
       auto resVal = std::make_shared<Value>("res", tensorC, matmulOp.get());
       matmulOp->Results.push_back(resVal);
       funcBlock->addOperation(std::move(matmulOp));

       // 插入返回: "func.return"(%res)
       auto returnOp = std::make_unique<Operation>("func.return");
       returnOp->Operands = { resVal };
       funcBlock->addOperation(std::move(returnOp));

       modBlock->addOperation(std::move(funcOp));

       std::cout << "--- [阶段 1: 降级前高层领域张量 IR (High-Level Tensor Dialect)] ---
";
       topModule->dump();
       std::cout << "
";

       // 2. 配置 Dialect Conversion 核心构件
       TypeConverter typeConverter;
       // 注册规则: TensorType -> MemRefType (保持维度与元素类型)
       typeConverter.addConversion([](std::shared_ptr<Type> t) -> std::shared_ptr<Type> {
           if (auto tensor = std::dynamic_pointer_cast<TensorType>(t)) {
               return std::make_shared<MemRefType>(tensor->getShape(), tensor->getElementType());
           }
           return nullptr;
       });

       ConversionTarget target;
       target.setOpIllegal("demo.matmul");        // 强制消除高层矩阵乘
       target.setOpLegal("demo.alloc");          // 允许显式内存申请
       target.setOpLegal("demo.for_nest_matmul");// 允许循环嵌套
       target.setOpLegal("func.return");         // 允许返回

       std::vector<std::unique_ptr<ConversionPattern>> patterns;
       patterns.push_back(std::make_unique<MatmulToLoopsPattern>(typeConverter));

       // 3. 执行渐进降级驱动器 (针对函数入口块)
       std::cout << "--- [阶段 2: 执行 Dialect Conversion (Tensor -> MemRef & Loops)] ---
";
       // 导航至函数基本块
       Block* targetBlock = topModule->Regions[0]->Blocks[0]->Operations[0]->Regions[0]->Blocks[0].get();
       bool success = DialectConversionDriver::applyPartialConversion(targetBlock, target, patterns);
       assert(success);
       std::cout << "  >>> Dialect Conversion 执行成功，非法高层操作已消除并合法化!

";

       std::cout << "--- [阶段 3: 降级后中层结构化循环与内存 IR (Mid-Level MemRef/Loops)] ---
";
       topModule->dump();
       std::cout << "
";

       // 4. 自动化断言验证
       assert(targetBlock->Operations.size() == 3);
       assert(targetBlock->Operations[0]->OpName == "demo.alloc");
       assert(targetBlock->Operations[1]->OpName == "demo.for_nest_matmul");
       assert(targetBlock->Operations[2]->OpName == "func.return");
       assert(targetBlock->Operations[0]->Results[0]->getType()->getKind() == TypeKind::MemRef);

       std::cout << "=======================================================
";
       std::cout << " MLIR Dialect 扩展与渐进降级框架断言测试全量通过!
";
       std::cout << "=======================================================
";
   }

   } // namespace test

本章详细推导了 MLIR 多层中间表示在突破传统单一通用 IR 表达瓶颈中的核心工程设计。通过 Dialect 命名空间封装、ODS 声明式操作建模、Block Arguments 拓扑解耦以及由 ConversionTarget、RewritePattern 与 TypeConverter 构成的受控渐进降级流水线，现代编译器获得了在保留高层领域几何拓扑的同时、安全平滑向目标机器指令沉降的完整基础设施能力。在下一章中，我们将进一步聚焦现代领域特定编译器（Domain-Specific Compilers），深入解析面向 GPU 硬件的 SPIR-V 编译流、深度学习计算图算子自动融合（Operator Fusion）以及张量编译器（Tensor IR）的代码生成拓扑。
