Style Calculation and Render Tree Construction
==============================================

核心知识点
----------

* Style calculation 把 DOM、CSSOM、UA/user/author styles、media/container condition、custom property、伪类和运行时 mutation 合并成具体元素的样式结果。
* 一个属性的结果需要经过 selector matching、cascade、继承/defaulting 和 value computation；computed value 与最终 layout 使用的 used value 不是一回事。
* Custom property 自身参与 cascade 和继承，``var()`` 在属性值计算时解析；变量放置位置会扩大或收窄失效范围。
* DOM tree 与视觉结构并非一一对应：``display:none`` 会移除视觉盒，``display:contents`` 可保留 DOM 节点但移除自身盒，伪元素能生成 DOM 中不存在的视觉内容。
* Render/box tree 是 computed style 到 layout 的中间结构，决定哪些元素、文本、伪元素和匿名盒参与几何计算。
* Style invalidation 应尽量局部化；高频修改祖先 class、根变量或复杂 selector 会放大 ``Recalculate Style`` 范围。

关键路径
--------

样式计算：

``DOM + CSSOM → selector matching → cascade → inheritance/defaulting → computed style``

视觉结构：

``computed style → display/position/pseudo/content rules → box/render tree → layout``

运行时更新：

``User/Event → JavaScript DOM/class mutation → style invalidation → affected subtree → recalculate style → render tree update``

概念辨析
--------

* **Specified/Cascaded Value vs Computed Value**：前者表示规则竞争后的声明结果；后者已完成继承和可计算值解析。
* **Computed Value vs Used Value**：百分比宽度等值仍需 layout 根据 containing block 才能得到实际使用尺寸。
* **DOM Tree vs Render/Box Tree**：DOM 服务文档和脚本对象关系；视觉树服务 layout/paint，两者允许过滤、生成和重组视觉对象。
* **Pseudo-element vs DOM Node**：伪元素可产生视觉内容，但通常不是普通 DOM 节点。
* **Style Recalculation vs Layout**：前者决定属性值；后者根据这些值计算几何。

本章结论
--------

Style calculation 是 DOM/CSS 语义进入像素管线的转换边界。视觉错误先查 matched rules、cascade 和 computed style；性能问题先找 mutation 和 invalidation 范围，再看它是否推动了大面积 render tree 更新和后续 layout。