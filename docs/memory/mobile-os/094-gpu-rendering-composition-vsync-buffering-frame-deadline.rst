第094章：GPU Rendering, Composition, VSync, Buffering, Frame Deadline
====================================================================

核心知识点
----------

* ``GPU Rendering`` 负责把某个内容源生成成可合成 buffer；``Composition`` 负责把多个 Layer 合成最终显示结果，两者责任不同。
* ``VSync`` 是显示节奏源，用来协调 App 更新、动画 tick、buffer latch、系统合成和显示 present。图形管线本质是按显示周期推进的流水线。
* 60Hz、90Hz、120Hz 的刷新周期约为 16.67ms、11.11ms、8.33ms；刷新率越高，App、GPU 和 compositor 的交接窗口越紧。
* Buffering 用于解耦 Producer 与 Consumer。双缓冲降低内存成本，三缓冲提高吞吐和容错，但队列更深会增加输入到显示的延迟。
* Fence 表示 GPU 或其他硬件是否完成对 buffer 的读写。没有 fence，producer/consumer 会出现覆盖、读脏数据或错误同步。
* ``Frame Deadline`` 是当前结果赶上某一刷新周期必须满足的时间边界；错过 deadline 常意味着继续显示旧帧。
* CPU、GPU、compositor、display controller 可以流水并行，但必须在固定交接点完成各自工作。

关键路径
--------

``Input → App Update → Render Commands → GPU → Queue Buffer → Fence → Compositor Latch → Composition → Present``

VSync 流水线可简化为：

``App VSync → App 生成未来帧``

``Compositor VSync → 合成已完成 buffer``

``Hardware VSync → Display 扫描输出``

Buffer 生命周期：

``Free → Dequeued → Rendering → Queued → Acquired → Presented → Released``

概念辨析
--------

* ``Frame rate`` 是内容生产速度；``refresh rate`` 是屏幕刷新速度，二者不必相等。
* ``VSync`` 不是“固定每 16ms 调一次函数”，而是一整套显示相位与交接时间模型。
* ``Double buffering`` 与 ``triple buffering`` 的核心取舍是延迟、吞吐和内存，不是简单“越多越好”。
* GPU 完成绘制不代表这一帧已显示；compositor 还要 latch、compose、present。
* 平均耗时低不代表帧节奏稳定；稳定 pacing 比单纯平均 FPS 更能解释用户感知流畅度。

本章结论
--------

图形性能的核心不是单点速度，而是每个阶段能否在正确的 VSync 相位完成交接。Buffering 提供流水能力，Fence 提供同步，Frame Deadline 决定用户最终看到哪一帧。