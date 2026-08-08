第180章：SurfaceFlinger Skia Vulkan and Core Animation Metal
============================================================

核心知识点
----------

* Android 与 Apple 图形栈都要解决五个问题：谁生成绘制状态或像素、谁持有 buffer、谁决定合成、谁对齐显示时钟、谁承担 GPU / 显示功耗。
* Android 普通 UI 常沿 ``View → RenderThread → HWUI / Skia → Surface / BufferQueue → SurfaceFlinger → HWC → Display`` 输出；视频、相机和游戏可以拥有独立 Surface，与普通 UI 在系统合成阶段汇合。
* ``Surface`` 是 producer 侧图形缓冲入口，``BufferQueue`` 管理 producer / consumer，``SurfaceFlinger`` 持有系统 layer 和合成状态，``Hardware Composer`` 决定 GPU client composition 与硬件 overlay / device composition 的分工。
* Vulkan / OpenGL ES 是 GPU 命令接口；它们负责生成应用或合成所需 GPU 工作，不替代 SurfaceFlinger / HWC 的系统显示责任。
* Apple 常沿 ``View / SwiftUI state → CALayer → Core Animation transaction → GPU / Metal → Display Server → Display`` 输出；CALayer 让几何、透明度、transform、contents 和 animation 成为可合成状态。
* Core Animation 能复用已有 backing store，让很多动画只修改 layer 属性而不重新绘制像素；Metal 用 command buffer、texture、drawable 表达显式 GPU 工作。
* Android 更显式暴露 Surface / buffer 管线；Apple 更强调 layer tree / transaction / animation 模型。两者最终都必须在 frame deadline 前提交可显示状态和完成必要 GPU / composition 工作。
* 掉帧可能来自 App 主线程、RenderThread / Core Animation 提交、GPU、buffer 等待、系统合成、HWC / display server 或刷新率 / thermal policy，不能只看一个线程。

关键路径
--------

::

   Android:
   App State → View / Draw → RenderThread / Skia
       → Surface Buffer → BufferQueue → SurfaceFlinger
       → HWC / GPU Composition → Display Controller → Panel

   Apple:
   App State → UIKit / SwiftUI → CALayer Tree
       → Core Animation Transaction → Metal / GPU
       → Display Server Composition → Display Controller → Panel

一帧分析应同时检查 ``app deadline``、``GPU completion``、``buffer handoff``、``composition`` 与 ``present``。

概念辨析
--------

* ``Surface`` 不等于 ``View``：View 是 UI 对象，Surface 是图形 buffer 的生产入口。
* ``SurfaceFlinger`` 不等于 GPU：它是系统 compositor，GPU 只是其可能使用的合成执行资源之一。
* ``CALayer`` 不等于像素 bitmap：它是可合成状态与内容的容器，可承载 backing store、transform 和 animation。
* ``Metal`` 不等于 Core Animation：Metal 提供显式 GPU API，Core Animation 负责 layer / animation / composition 语义；二者可协作。

本章结论
--------

Android 以 Surface / BufferQueue / SurfaceFlinger / HWC 构造显式 buffer 合成链，Apple 以 CALayer / Core Animation / Metal / display server 构造 layer 合成链。两者都把 App 绘制和最终显示拆成多个时序阶段，掉帧必须沿完整 frame pipeline 定位。