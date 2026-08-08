第096章：Apple Graphics View, Layer, Core Animation, Metal, WindowServer, Display
=============================================================================

核心知识点
----------

* Apple 图形主链可抽象为 ``View → Layer → Core Animation → Metal / Render Service → Display Server → Display``。
* ``UIView / NSView / SwiftUI`` 负责交互、布局和 UI 状态；``CALayer`` 负责可合成视觉属性，如位置、transform、opacity、contents、corner radius、shadow 和 sublayers。
* Core Animation 通过 transaction 批量提交 Layer Tree 变化，并负责大量属性动画的时间插值与显示调度。
* Core Animation 中应区分 ``model layer tree``、``presentation tree`` 与私有 ``render tree``：前者保存目标状态，presentation 表示当前屏幕状态。
* ``Metal`` 是 App 主动编码 GPU 工作的接口。典型链路为 ``MTLCommandQueue → MTLCommandBuffer → Encoder → Drawable → Present``。
* ``CAMetalLayer`` 把 Metal 渲染结果接入 Core Animation / Display 链路；App 完成 command buffer 并不等于最终屏幕已 present。
* WindowServer / display server 角色负责跨窗口、跨进程和系统 UI 的全局合成；移动平台具体私有实现不应当作公开 API 依赖。

关键路径
--------

普通 UI：

``SwiftUI / UIKit → View State → CALayer → Core Animation Transaction → Render / Display Service → Display``

Metal 内容：

``CAMetalLayer.nextDrawable → Encode GPU Commands → CommandBuffer.commit → Present Drawable → Core Animation / Display System``

动画状态：

``Model Layer Target → Transaction → Presentation State → Render → Screen``

概念辨析
--------

* ``View`` 负责 UI 语义；``CALayer`` 负责视觉合成状态，二者不是同一种对象。
* ``Model layer`` 是目标值，``presentation layer`` 是动画中的当前可见值；调试动画位置时必须区分。
* Core Animation 不是单纯“动画库”，它还是 Apple UI 到系统合成之间的重要提交层。
* Metal 是 GPU 命令接口，不替代 Core Animation 的窗口与系统合成职责。
* ``WindowServer`` 在 macOS 是公开可观察角色；iOS / iPadOS 的具体显示服务内部实现应保持为平台私有边界。

本章结论
--------

Apple 图形栈把 UI 语义、Layer 视觉状态、动画提交、GPU 工作和全局显示合成分层处理。排查问题时先区分 View 状态、CALayer 属性、Core Animation transaction、Metal GPU 工作和系统 present，避免把所有显示问题都归因到主线程或 GPU。