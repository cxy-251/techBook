第043章：SSA Construction and Destruction
=========================================

核心知识点
----------

* SSA construction 把可变变量或栈槽改写成“一次定义一个 value”的图结构；SSA destruction 则把优化后的 SSA value 落回寄存器、栈槽和 move 序列。
* 线性代码的构造核心是重命名：每次定义生成新 version，每个 use 引用当前支配路径上的最新 version。
* CFG 中的重命名通常沿 dominator tree 进行。进入 block 时建立新 version，处理 use 时读取当前 version，离开支配区域时恢复外层定义。
* 多路径合流处仅靠重命名不够，需要插入 ``phi`` 或 block argument，给后续 use 建立统一且合法的 SSA definition。
* ``phi`` 的经典插入依据是 dominance frontier：当不同定义的支配范围在控制流边界相遇，合流 block 成为新定义候选位置。
* Minimal/pruned SSA 会避免无用 ``phi``。若合流后的变量根本不 live，则没有必要为它制造新的合流 value。
* ``mem2reg`` 类转换把可提升局部栈槽的 ``alloca/load/store`` 改写成 SSA values，使原本隐藏在内存中的值流变成直接 def-use 关系。
* 可提升性依赖地址逃逸、别名访问、volatile/atomic、异常和调试等语义；不是所有 stack slot 都能安全消除。
* SSA destruction 不能把 ``phi`` 简单按文本顺序变成赋值。``phi`` 表达 edge 上的 parallel-copy 语义，需要在 predecessor edge 或拆分后的 edge block 上安排 copies。
* Parallel copies 可能形成交换环，例如 ``a<-b, b<-a``，后端需要临时寄存器、寄存器重命名或 copy-resolution 算法打破循环。
* Register allocation 常与 SSA destruction 紧密关联。某些后端先消除 phi，再分配寄存器；某些后端利用 SSA 性质完成 coalescing 后再落到机器寄存器。
* CFG 改写、critical edge splitting、copy insertion 和 register assignment 必须保持 predecessor-specific value 语义，否则会把不同路径的值混淆。

关键路径
--------

SSA construction：

::

   CFG + mutable definitions
   → compute dominance / dominance frontier
   → insert phi/block arguments where needed
   → walk dominator tree
   → rename each definition to new SSA value
   → rewrite uses to current version
   → verify dominance and incoming edges

Memory-to-SSA：

::

   local alloca/load/store
   → prove slot promotable
   → identify definitions and uses
   → insert merge values
   → rename loads to SSA operands
   → remove redundant stores/loads/alloca

SSA destruction：

::

   phi/block arguments
   → derive edge parallel copies
   → split critical edges if required
   → resolve copy cycles / coalesce values
   → assign registers or stack slots
   → emit machine moves

概念辨析
--------

* **Renaming 与 phi insertion**：重命名解决单一路径上的版本选择；``phi`` 解决多路径合流。
* **Dominance frontier 与 dominator tree**：前者定位定义影响力相遇边界，后者提供必经关系和重命名遍历结构。
* **Mem2Reg 与“把内存变寄存器”**：它本质是把可证明局部的内存 value flow 提升成 SSA，不保证最终机器一定只用物理寄存器。
* **Phi 与 sequential copies**：phi inputs 在 edge 上具有并行语义，不能机械按顺序赋值。
* **SSA destruction 与 loss of semantics**：销毁的是 SSA 表示形式，不是值来源语义；路径相关选择必须由 copies/register assignments 等价保存。

本章结论
--------

SSA 的生命周期应按“CFG/Dominance—Phi Placement—Renaming—Optimization—Parallel Copy—Register/Memory”理解。构造阶段把隐含的变量历史变成显式 value graph，销毁阶段再把这张图映射到真实机器资源；两端都必须保持同一条路径上的值来源不变。