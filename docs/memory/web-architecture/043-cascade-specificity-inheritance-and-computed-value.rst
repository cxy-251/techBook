Cascade, Specificity, Inheritance, and Computed Value
====================================================

核心知识点
----------

* CSS 是约束系统：DOM、stylesheet、runtime condition 共同进入 style calculation，输出每个元素的 computed value。
* Cascade 解决同一元素、同一属性上的候选声明冲突；判断顺序依次考虑 relevance、origin/importance、cascade layer、specificity、scope proximity 与 source order。
* Specificity 只在前述层级相同后参与比较；它不是 CSS 优先级的全部。大型系统应优先用 ``@layer``、``:where()``、token 与明确覆盖入口治理，而不是不断堆高 selector 权重。
* Inheritance 沿 DOM 树传播部分属性值，字体、颜色、line-height 等适合通过祖先建立局部默认值；非继承属性不会自动向下传播。
* Custom property 本身参与 cascade 与 inheritance，真正成本和语义取决于它最终被哪个 CSS 属性消费。
* Specified value、computed value、used value、actual value 是不同阶段；百分比宽度、字体度量、布局约束等可能在 computed value 之后才得到最终几何结果。

关键路径
--------

样式值形成路径：

``DOM + CSS Rules + Runtime Conditions → Selector Match → Cascade → Inheritance → Custom Property Resolution → Computed Value → Used Value → Layout/Paint``

冲突判断：

``relevance → origin/importance → layer → specificity → scope proximity → source order``

大型样式治理：

``reset/base → theme → component → utility/override``

并把可变主题、状态和组件覆盖尽量收敛到 custom property 或显式 layer。

概念辨析
--------

* **Cascade vs Specificity**：cascade 是完整冲突解决算法；specificity 只是其中一个排序条件。
* **Inheritance vs Cascade**：cascade 先决定当前元素是否已有获胜声明；没有合适声明时，继承属性才从父级取得值。
* **Custom Property vs 普通属性**：custom property 是值通道，可继承、可覆盖；真正的视觉与性能影响由使用它的目标属性决定。
* **Computed Value vs Used Value**：computed value 已完成大部分语义计算；used value 还要结合 containing block、字体、布局等实际约束。
* **高权重 selector vs 稳定架构**：高 specificity 能压住局部冲突，却会收窄未来覆盖路径；layer、scope 与 token 更适合长期治理。

本章结论
--------

CSS 冲突要按系统顺序分析：先确定候选规则，再按 cascade 层级筛选，随后追踪继承和变量，最后区分 computed value 与布局阶段的 used value。样式系统的可维护性来自明确优先级边界，而不是更长的 selector。