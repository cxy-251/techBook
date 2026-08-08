GPU Acceleration, Layer Promotion, and Compositor Pipeline
=========================================================

核心知识点
----------

* GPU acceleration 主要加速 raster、texture、effect、composite 和 draw，不会替代 JavaScript、style calculation 或 layout。
* 页面更新应先判断最小必要 pipeline：改变几何通常进入 layout；改变绘制属性进入 paint/raster；已有纹理上的 ``transform``、``opacity`` 更可能走 compositor-only 路径。
* Layer promotion 把部分视觉内容拆成独立 composited layer，使后续 transform、opacity、scroll 等更新减少对其它区域的 repaint。
* ``will-change`` 只是优化提示，应短生命周期、局部使用；大量常驻 layer 会增加 texture memory、tile raster 和 compositor 管理成本。
* Compositor thread 可以独立推进部分滚动和动画，但需要 main thread 裁决的事件、layout、DOM mutation 仍会阻塞用户反馈。
* Passive input listener 能减少滚动等待 main thread 的情况；可取消默认滚动的 listener 会把输入裁决重新拉回主线程。
* GPU/driver/context 问题常表现为黑屏、context lost、纹理压力或合成卡顿，与主线程 long task 的症状不同。

关键路径
--------

完整路径：

``DOM/CSS change → Style → Layout → Paint → Raster → Layerize/Composite → GPU Draw → Screen``

可合成动画：

``existing composited layer → transform/opacity update → compositor thread → GPU draw → frame``

滚动路径：

``Input → compositor scroll``

若需要主线程裁决：

``Input → main-thread listener/layout/work → compositor → frame``

概念辨析
--------

* **GPU Acceleration vs GPU Executes Web App**：GPU 处理图形相关任务，页面脚本和文档生命周期仍主要在 CPU/browser runtime 上执行。
* **DOM Element vs Composited Layer**：两者没有稳定一一映射；layer 是浏览器实现的合成工作单元。
* **Layer Promotion vs 性能提升**：独立 layer 可减少部分 repaint，但会增加内存、raster 与管理成本。
* **Compositor-only Animation vs JavaScript Animation**：是否只走 compositor 取决于最终修改的视觉属性和 layer 状态，不取决于动画由 CSS 还是 JS 发起。
* **Main-thread Jank vs GPU Jank**：前者常见于 scripting/layout/paint；后者更接近 raster、texture、context 或 draw 路径。

本章结论
--------

GPU 优化的目标是让高频视觉变化尽可能停留在最小的 compositor 路径，同时控制 layer 和纹理成本。判断动画或滚动卡顿时，先看属性触发了哪些阶段，再看主线程、raster、layer 和 GPU 资源证据；盲目 ``will-change`` 或“强制 GPU”不是稳定优化策略。