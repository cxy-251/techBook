第092章：App Drawing to Screen Pixel Pipeline
=============================================

核心知识点
----------

* 一帧从 App 状态变化到屏幕像素，稳定主链为 ``UI 状态 → Layout / Draw → Render Thread / Render Server → GPU → Buffer → Compositor → Display Controller → Panel``。
* UI Framework 负责交互语义、状态、布局与绘制记录；渲染线程/服务把这些状态变成更接近 GPU 的任务；GPU 生成像素；系统合成器负责全局 Layer；显示控制器负责最终扫描输出。
* ``Frame`` 是显示系统的基本输出单位，也是调度、合成和性能诊断的基本时间单位。60Hz、90Hz、120Hz 对应的刷新间隔约为 16.67ms、11.11ms、8.33ms。
* ``Layout`` 决定几何，``Draw`` 产生绘制描述，``Raster`` 产生像素，``Composite`` 合成多个 Layer，``Present`` 把结果交给显示硬件。
* App 完成 draw 不代表用户已经看到这一帧；后续还存在 GPU 执行、buffer 同步、系统合成和显示扫描。
* 移动图形链是跨进程、跨线程、跨硬件单元的流水线，任何阶段错过交接点都可能让整帧推迟一个刷新周期。

关键路径
--------

``Input → App State → Layout / Draw → Render → GPU → Surface / Buffer → System Compositor → Display Controller → Screen``

Android 常见映射：

``View / Compose → RenderThread / Skia → Surface / BufferQueue → SurfaceFlinger → HWC → Display``

Apple 常见映射：

``UIKit / SwiftUI → CALayer / Core Animation → Metal / Render Service → Display Server → Display``

掉帧定位顺序：

``Main Thread → Layout / Draw → Render Thread → GPU → Buffer / Fence → Compositor → Present``

概念辨析
--------

* ``View`` 不等于像素：View 表达 UI 结构和交互，像素要经过后续渲染与合成。
* ``Draw`` 不等于 ``Present``：Draw 只是生成内容，Present 才决定哪次刷新真正显示它。
* ``GPU rendering`` 不等于 ``system composition``：前者生成单个内容源，后者组合 App、视频、系统栏等多个内容源。
* ``Frame time`` 不是某一个函数耗时，而是整条显示链是否赶上目标刷新周期。
* 主线程快并不能证明图形链快；GPU、合成器和显示提交仍可单独成为瓶颈。

本章结论
--------

移动显示系统应按完整帧流水线阅读，而不是只看 App 绘制。稳定分析模型是：先确认 App 是否按时产生视觉状态，再确认 GPU 是否按时生成 buffer，再确认系统是否按时合成并 present，最后确认显示硬件是否在目标刷新周期扫描到该结果。