第099章：GPU Composition, Overlay Plane, Display System Policy
==============================================================

核心知识点
----------

* 系统合成器需要为每个可见 Layer 决定由 GPU 先合成，还是交给显示硬件的 overlay / video plane 直接扫描。
* ``GPU Composition`` 适合复杂透明、模糊、mask、任意 transform 和复杂色彩转换；代价是额外 GPU 时间、内存带宽和中间 buffer。
* ``Hardware Composition`` 依赖显示控制器固定功能 plane，适合矩形、格式受支持、变换简单的视频和 UI Layer，通常功耗更低。
* Overlay plane 是否可用取决于 plane 数量、pixel format、alpha、crop、scale、rotation、color space、HDR 和带宽，不只是是否存在空闲 plane。
* 视频、相机预览、普通 UI、字幕和系统栏可以来自不同 producer，系统每帧按当前 Layer 状态重新做 composition decision。
* Color Management 与 HDR 让合成进入显示策略层：同屏 SDR / HDR、Display-P3、tone mapping、SDR dimming、亮度和 panel capability 都会改变路径。
* ``Display Policy`` 还负责 brightness、rotation、cutout、HDR mode、refresh rate、color mode 等全局显示状态。
* 合成策略直接影响延迟、功耗、GPU 占用、DRAM 带宽和温度，是图形子系统最终的系统级调度点。

关键路径
--------

``Visible Layers → System Compositor → Composition Decision → GPU Client Composition or Hardware Planes → Display Engine → Panel``

Android 常见决策：

``Layer State → SurfaceFlinger → HWC validate → CLIENT / DEVICE composition → present``

视频场景：

``Decoder Buffer → Video Plane``

``UI / Subtitle / System UI → Other Plane or GPU Client Target``

``→ Display Controller → Panel``

概念辨析
--------

* ``Overlay plane`` 不是普通 UI Layer；它是显示控制器中的硬件扫描输入通道。
* ``Hardware composition`` 不代表完全没有 GPU：某些 Layer 可走 plane，另一些 Layer 仍可能先由 GPU 合成成 client target。
* Layer 数量不是唯一决定因素；复杂 alpha、transform、HDR 和带宽限制都可能使系统回退 GPU 合成。
* 全屏视频更省电通常来自更直接的硬件显示路径，不是因为视频像素更少。
* Display policy 属于全局系统策略，单个 App 只能提供内容和部分偏好，不能独占决定 HDR、亮度、刷新率或最终 plane 分配。

本章结论
--------

最终显示路径是 compositor 根据 Layer 语义与硬件能力做出的动态决策。GPU 提供通用表达能力，display plane 提供低成本固定功能路径；系统在正确性、带宽、功耗、延迟、HDR 和显示策略之间选择每一帧的组合方案。