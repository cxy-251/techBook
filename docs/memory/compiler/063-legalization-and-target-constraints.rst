第063章：Legalization and Target Constraints
=============================================

核心知识点
----------

* Legalization 解决的是“IR 能表达，但当前目标机器/后端阶段不能直接处理”的问题。它把 portable IR 收缩到 target legal set。
* Legal set 同时由 opcode、operand/result type、register class、memory semantics、addressing mode 和 subtarget feature 决定；“目标不支持”必须具体到哪一维不合法。
* Type legalization 处理值类型无法被目标原生承载的情况，例如窄整数、宽整数、非法向量宽度；operation legalization 处理 opcode 或 opcode+type 组合无直接实现的情况。
* 常见策略包括 promote、expand、split、scalarize、custom lowering 和 libcall。真实后端常把多种策略组合使用。
* Promote 把较小类型提升到目标原生宽度，再在需要处截断或符号/零扩展；必须保持源类型下的 signedness、overflow 和比较语义。
* Expand 把一个非法 operation 改写成多条合法 operations，例如大立即数地址、宽整数算术或特殊位操作。
* Split/scalarize 把宽整数或向量拆成多个目标可承载的部分；拆分后还要正确维护 carry、lane order、shuffle 和 memory layout。
* Libcall lowering 把难以直接实现的 operation 变成 runtime helper 调用，同时引入 ABI、链接、异常和运行时库可用性约束。
* Address legalization 处理目标寻址模式限制。一个 IR 地址表达式可能需要先显式计算地址，再执行合法 load/store。
* Target feature flags 会改变 legality。相同 ISA 在开启/关闭 SIMD、atomic、float、crypto 扩展后，其合法类型和操作集合可能不同。
* Legalization 不是“随便拆开就行”。每次改写都必须严格向 legal set 推进，并保证后续 selector 能理解新节点，流程最终能终止。
* Legalization 的输出形状可能比输入更复杂，但复杂度增加只是为了满足硬件约束；正确性仍以原 IR 语义保持为准。

关键路径
--------

合法化判断：

::

   IR operation + type + operands
   → query target legal set
   → legal? keep
   → illegal type? promote / split / scalarize
   → illegal op? expand / custom lower / libcall
   → illegal address? materialize address
   → recheck legality
   → hand to instruction selection

宽操作处理：

::

   wide scalar/vector operation
   → inspect native register width / vector support
   → split into legal pieces
   → preserve carry/lane/order semantics
   → merge result if required

概念辨析
--------

* **IR 合法 与 target 合法**：前者说明表示符合 IR 规则，后者说明当前目标后端能继续处理该形态。
* **Type legalization 与 operation legalization**：前者改变载体类型，后者改变操作实现；实际框架中二者可以交织。
* **Promote 与 zero/sign extend**：提升动作必须选择符合源语义的扩展方式，不能只看位宽变大。
* **Split 与 vectorization**：split 是为了适应目标能力，可能把向量拆窄；vectorization 则是为了提取并行性而把标量合宽。
* **Libcall 与普通函数调用**：libcall 是后端为了实现缺失硬件语义引入的 runtime 契约。

本章结论
--------

Legalization 是 portable IR 与 non-portable hardware 之间的适配层。稳定理解路径是 ``Legality Query → Promote/Expand/Split/Libcall → Recheck → Selection``；目标越受限，表示越可能被拆分或转成 helper 调用，但任何形态变化都必须完整保留源操作的数值、内存和异常语义。