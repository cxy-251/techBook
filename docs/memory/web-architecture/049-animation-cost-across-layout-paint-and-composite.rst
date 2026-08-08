Animation Cost Across Layout, Paint, and Composite
==================================================

核心知识点
----------

* 动画是连续帧上的重复渲染工作。分析动画先看每帧改变哪些属性，再判断它触发 layout、paint 还是仅 composite。
* 改变 ``width/height/top/left/margin/padding/font-size`` 等几何属性通常会进入 layout，并可能继续触发 paint 与 composite；成本会沿布局依赖传播。
* 改变颜色、阴影、滤镜、背景等可能跳过 layout，却仍需要重新 paint/raster；大面积 blur、shadow、clip、filter 依旧可能昂贵。
* ``transform`` 与 ``opacity`` 在合适的 layer 条件下常能走 compositor-friendly 路径，减少主线程 layout/paint 工作；它们不是绝对零成本，仍有 layer、texture、memory 与合成开销。
* Layer promotion 是资源权衡。``will-change`` 应短生命周期、少量使用；大量常驻 layer 会把 CPU 压力转成 GPU memory、raster 与管理成本。
* CSS Animation、Transition、Web Animations API、``requestAnimationFrame`` 只决定时间线和更新入口；真正性能由被动画属性和渲染管线决定。
* 动画与用户输入竞争帧预算和主线程时间。高刷新率设备的单帧窗口更短，低端设备、复杂页面和多个并行动画会放大成本。
* ``prefers-reduced-motion`` 是用户偏好边界；动效设计必须提供减少或移除非必要运动的路径。

关键路径
--------

完整动画帧：

``Input/App State → Style Update → Layout → Paint/Raster → Composite → Display``

Paint 路径：

``Style Update → Paint/Raster → Composite → Display``

Compositor-friendly 路径：

``Style Update(transform/opacity) → Composite → Display``

优化判断：

``property changes → geometry? → pixels? → compositor-only possible? → layer/memory cost → frame/input evidence``

概念辨析
--------

* **Animation API vs Animation Cost**：API 说明谁产生时间线；属性决定浏览器每帧实际做什么。
* **Layout Animation vs Transform Animation**：前者改变真实几何并影响依赖对象；后者可把布局位置和视觉位置分开，常更适合纯移动效果。
* **Paint-free vs Cost-free**：跳过 paint 仍需要 composite、texture 和 GPU/内存资源。
* **Layer Promotion vs GPU 加速万能论**：独立 layer 能减少局部 repaint，却增加纹理、raster 和生命周期管理成本。
* **``will-change`` vs 强制优化**：它只是提前提示，不保证浏览器采用特定层策略；长期滥用会造成反效果。
* **流畅度 vs 可访问性**：视觉流畅不能覆盖用户减少运动的系统偏好，关键状态变化必须在低动效模式下仍清晰可理解。

本章结论
--------

动画优化应沿渲染管线做，而不是围绕某个框架 API。优先避免每帧改变大范围几何，其次控制 paint 面积和复杂度，再争取使用 transform/opacity 的合成路径；同时限制 layer 数量、验证真实帧时间和输入响应，并尊重 reduced-motion。