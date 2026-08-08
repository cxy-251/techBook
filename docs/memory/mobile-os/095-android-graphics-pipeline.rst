第095章：Android Graphics Pipeline
=================================

核心知识点
----------

* Android View 图形主链为 ``View / ViewRootImpl → RenderNode / Display List → RenderThread → Skia / GPU → Surface / BufferQueue → SurfaceFlinger → HWC → Display``。
* ``ViewRootImpl`` 组织一帧 traversal；``measure`` 决定尺寸，``layout`` 决定位置，``draw`` 生成绘制记录。``Choreographer`` 把输入、动画和 traversal 对齐到 VSync。
* ``RenderThread`` 把主线程提交的渲染树与 display list 转换成 GPU 工作，并管理部分 buffer 提交，从而把 UI 逻辑与 GPU 提交解耦。
* ``Canvas`` 是绘制 API 表面，``Skia`` 是主要 2D 图形实现，OpenGL ES / Vulkan 等是 GPU 后端；三者不能混为同一层。
* ``Surface`` 是图形生产入口；``BufferQueue`` 用 producer/consumer 协议管理 buffer；``Gralloc`` 负责图形缓冲分配与硬件 usage 约束。
* ``SurfaceFlinger`` 是系统合成服务，负责 Layer 状态、buffer latch、composition decision 和最终显示 transaction。
* ``Hardware Composer HAL`` 把 SurfaceFlinger 的 Layer 集合映射到显示硬件能力，决定 device composition、overlay plane 与 client composition。
* Android 掉帧必须区分 App 主线程、RenderThread、GPU、BufferQueue、SurfaceFlinger、HWC 和显示硬件。

关键路径
--------

``Input → Choreographer → ViewRootImpl → measure / layout / draw``

``→ RenderNode / Display List → RenderThread → Skia / GPU``

``→ Surface → BufferQueue → SurfaceFlinger → HWC → Display Controller → Panel``

典型 BufferQueue：

``dequeueBuffer → render → queueBuffer → acquireBuffer → compose → releaseBuffer``

掉帧定位：

``UI Thread → RenderThread → GPU Fence → Buffer Queue → SurfaceFlinger → HWC Present``

概念辨析
--------

* ``invalidate`` 表示内容需要重绘；``requestLayout`` 表示几何需要重新测量/布局，后者通常更重。
* ``View.draw`` 不等于直接写屏幕像素；硬件加速下大量操作会先记录到 RenderNode / display list。
* ``Canvas`` 不是 GPU API，Skia 也不是 SurfaceFlinger；它们分别属于 API、绘制实现和系统合成层。
* ``SurfaceFlinger`` 不负责 App 业务绘制；它消费各个 producer 已提交的 Layer / buffer，并做全局合成。
* ``HWC`` 不是 GPU driver；它描述和控制显示硬件的合成/显示能力。

本章结论
--------

Android 图形管线应按“App 生成绘制状态 → GPU 生成 buffer → SurfaceFlinger 全局合成 → HWC / Display 扫描输出”理解。定位 jank 时先确定晚帧属于 App 侧还是系统合成侧，再沿对应线程、buffer 和 fence 向下追踪。