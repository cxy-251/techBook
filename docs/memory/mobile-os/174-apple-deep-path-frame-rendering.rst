第174章：Apple Deep Path Frame Rendering
========================================

核心知识点
----------

* Apple Frame Rendering 的稳定路径是 ``App State → UIKit / SwiftUI → Layout / Drawing → CALayer Tree / Transaction → Core Animation / Metal → Display Server / Composition → Display Controller → Panel``。
* App 层决定“画什么”：状态变化、layout、drawing、view hierarchy；Layer 层决定可合成状态，例如 geometry、opacity、transform、contents、mask 与 animation transaction。
* ``CALayer`` 保存 model layer state，Core Animation 在 transaction commit 后把变化交给渲染/合成侧；很多 transform/opacity 动画可复用已有 backing store，不必每帧重新 CPU drawing。
* Metal 提供显式 GPU command buffer、render pass、texture 与 drawable；GPU 工作是异步的，command 提交完成不等于像素已经 present。
* Display server / compositor 负责跨窗口、系统 UI、layer、颜色/HDR 等合成责任；具体 iOS 私有进程与内部实现不属于 public API 契约。
* Display controller 与 panel 按刷新节奏输出，ProMotion/可变刷新率会改变 frame deadline 和功耗预算。
* 一次 jank 可能来自主线程 layout、CPU drawing、layer transaction 太晚、GPU workload 过重、drawable 等待、compositor 负载或 display refresh/present miss。
* 诊断必须用同一帧时间线区分 CPU、layer、GPU、composition 与 display，而不是看到掉帧就直接归因 GPU。

关键路径
--------

* UIKit 普通 UI 更新：``state change → setNeedsLayout / setNeedsDisplay → main RunLoop → layout/draw → CA transaction commit → composition → present``。
* Metal 路径：``App encode commands → command buffer → CAMetalDrawable → GPU completion → present → system composition → display``。
* 主线程如果在 deadline 前没有完成 layout、drawing 和 transaction commit，后续 GPU 即使空闲也无法显示新状态。
* Layer-only 动画重点看 transaction 与 compositor；内容重绘则还要检查 CPU drawing、texture upload 和 backing store 更新。
* GPU 慢时观察 command buffer、shader、fragment load、bandwidth、render pass、texture upload；合成慢时检查透明层、模糊、HDR、跨进程 layer 和 present timing。
* Instruments / Core Animation / Metal System Trace 的稳定用法是先锁定慢帧，再沿 main thread → layer commit → GPU → present 回溯责任。

概念辨析
--------

* ``UIView / SwiftUI state`` 表达 App UI 语义；``CALayer`` 表达可合成视觉状态，两层关联但职责不同。
* ``Drawing`` 生成或更新内容；``Composition`` 组合已有 layer/buffer，二者成本来源不同。
* ``Core Animation`` 不等于所有工作都在 GPU；main thread layout/drawing 和 transaction commit 仍可能成为瓶颈。
* ``Metal command buffer completed`` 与 ``frame presented`` 不是同一时间点，后者还要经过系统合成与显示刷新。
* ``Refresh rate`` 决定可用帧预算，但刷新率下降可能是系统功耗/热策略结果，不一定是 App 自己主动设定。

本章结论
--------

Apple 一帧画面的责任链应从 App 状态更新一直追到 panel scanout。主线程负责及时生成并提交可见状态，Core Animation 和 layer 系统负责组织合成，Metal/GPU 负责执行图形工作，display server 与硬件负责最终 present。分析 jank 时，先定位哪一段错过 deadline，再处理对应 CPU、layer、GPU、composition 或 display 问题。