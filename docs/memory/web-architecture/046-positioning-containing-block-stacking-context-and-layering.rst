Positioning, Containing Block, Stacking Context, and Layering
============================================================

核心知识点
----------

* ``position`` 决定元素采用哪套几何规则：``static`` 走 normal flow；``relative`` 保留占位后偏移；``absolute`` 脱离 flow；``fixed`` 通常相对 viewport；``sticky`` 在 normal flow 与滚动阈值之间切换。
* Containing block 决定 ``top/right/bottom/left``、``inset``、百分比尺寸等坐标的参照矩形。``position``、``transform``、``filter``、``contain``、``will-change`` 等都可能改变定位参照。
* Stacking context 是局部绘制深度边界。``z-index`` 只在当前 stacking context 的比较范围内生效，无法穿透祖先创建的上下文。
* ``transform``、``opacity < 1``、``filter``、``isolation``、部分 positioned/flex/grid item、``contain``、top layer 等都可能创建 stacking context。
* Overlay 问题要同时处理几何、绘制、命中测试、滚动与焦点。Modal、toast、全局 popover 等通常需要专门 overlay root / portal，而不是嵌在任意局部组件 DOM 中。
* CSS 层级与交互层级必须一致：视觉上盖住背景还不够，还需要背景点击拦截、scroll lock、focus trap、关闭顺序和焦点恢复。

关键路径
--------

浮层定位：

``Overlay Element → position mode → containing block → inset/size resolution → stacking context tree → paint order → hit testing → focus/keyboard``

定位排查：

``是否占 normal flow → position 值 → containing block → overflow/transform/contain ancestors → stacking context → z-index comparison``

全局 overlay 常见结构：

``App DOM → Portal/Overlay Root → fixed/absolute layer → backdrop → dialog/popover → focus management``

概念辨析
--------

* **Positioning vs Stacking**：positioning 决定坐标；stacking 决定重叠绘制顺序。
* **Containing Block vs Stacking Context**：前者是几何参照；后者是局部深度排序边界。一个祖先可以同时创建二者，也可以只创建其中之一。
* **Absolute vs Fixed**：absolute 通常依赖最近定位祖先；fixed 通常依赖 viewport，但某些祖先属性会把 fixed 绑定到局部 containing block。
* **Sticky vs Fixed**：sticky 仍保留 normal-flow 占位并依赖滚动容器；fixed 脱离普通文档流。
* **高 z-index vs 更高层级**：数值再大也只能在当前 stacking context 内比较；真正跨上下文通常要调整 DOM/portal 或移除不必要的上下文创建条件。
* **视觉覆盖 vs 交互覆盖**：看起来在最上层并不代表键盘、pointer、scroll 和辅助技术已经被正确限制。

本章结论
--------

浮层故障应按“坐标系 → 深度系统 → 交互系统”排查。先确认 containing block，再展开 stacking context 树，最后检查 hit testing、scroll 和 focus。全局 overlay 的几何与交互责任应放在统一层级管理，而不是靠不断增大 ``z-index`` 修补。