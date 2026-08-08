Layout, Paint, Rasterization, and Compositing
=============================================

核心知识点
----------

* 浏览器像素管线可压缩为 ``Style → Layout → Paint → Rasterization → Compositing → Frame``；不同属性变化会触发不同最小阶段。
* Layout 把 computed style、containing block、formatting context、字体度量、图片固有尺寸和 viewport 等约束转换成元素几何。
* Layout 是依赖图：父子尺寸、普通流、flex/grid、文本换行、百分比、container query 等都会让局部变化扩散。
* 交错执行 DOM/style 写入与 ``getBoundingClientRect()``、``offsetHeight`` 等同步几何读取，会强迫浏览器提前刷新 style/layout，形成 layout thrashing。
* Paint 根据几何、颜色、文字、图片、阴影、clip、stacking order 等生成绘制指令；几何不变的视觉属性也可能触发 repaint。
* Rasterization 把绘制指令转成 bitmap/tile/texture；Compositing 再按 layer、transform、opacity、clip 等关系组合最终帧。
* 图片、字体、视频等资源 readiness 会影响 layout、paint、raster 和最终视觉稳定性。

关键路径
--------

完整视觉更新：

``DOM/CSS mutation → Style → Layout → Paint → Raster → Composite → Display Frame``

几何变化：

``class/content/resource size change → affected layout dependency graph → new geometry → repaint/raster/composite``

只需重绘：

``color/shadow/background change → Paint → Raster → Composite``

可合成更新：

``existing layer + transform/opacity change → Composite → Frame``

概念辨析
--------

* **Layout vs Paint**：layout 计算位置和尺寸；paint 决定这些盒子如何被画。
* **Paint vs Rasterization**：paint 生成绘制指令；raster 把指令变成像素或纹理 tile。
* **Rasterization vs Compositing**：raster 生成图像内容；compositing 组合已有 layer/texture 形成最终帧。
* **Reflow vs Layout**：reflow 是常见旧称；工程判断应直接看实际 layout 触发和失效范围。
* **Visual Change vs Geometry Change**：颜色变化可能不需要 layout；高度、字体、宽度、内容换行通常会改变几何。

本章结论
--------

页面卡顿要按渲染阶段定位。先从用户动作找到状态变化，再判断它是否改变样式、几何、绘制内容或仅改变合成属性；随后用浏览器性能记录验证真正发生的 Layout、Paint、Raster 与 Composite，而不是把所有视觉问题归为“DOM 慢”或“GPU 慢”。