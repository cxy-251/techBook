第097章：Jank, Main Thread, Render Thread, GPU, Missed Frame
============================================================

核心知识点
----------

* Jank 本质是 ``Frame Deadline`` 失败：某一帧没有在期望时间完成 update、render、latch、compose 或 present，屏幕继续显示旧帧或以不稳定节奏更新。
* Main Thread 常见瓶颈包括长任务、同步 I/O、同步 IPC、锁等待、GC / allocation、图片解码、复杂文本和 layout storm。
* Render Thread / Render Server 瓶颈说明 UI 状态已经提交，但渲染树同步、GPU command 构建、资源上传或后端执行过慢。
* GPU 瓶颈常见于 overdraw、复杂 shader、blur / shadow、fill rate、纹理带宽、大尺寸 render target 和热降频。
* Buffer Queue 与 Fence 问题会造成 producer stall、consumer delay、queue depth 上升和 present latency，即使平均 FPS 看起来尚可。
* 系统 compositor 也有独立 deadline。Android FrameTimeline 可区分 App deadline、SurfaceFlinger CPU/GPU deadline、Display HAL 等类型。
* Jank、ANR、Missed Frame 属于不同严重度和不同时间尺度：掉帧可以只持续一个刷新周期，ANR 是长时间主线程/系统响应失败。

关键路径
--------

``Input / Animation Tick → Main Thread → Layout / Draw → Render Thread → GPU → Buffer / Fence → System Compositor → Present``

诊断顺序：

``1. 找到晚帧``

``2. 判断 App 侧还是 compositor 侧``

``3. 看 CPU thread busy / blocked / waiting``

``4. 看 RenderThread / GPU``

``5. 看 Buffer Queue / Fence``

``6. 看 SurfaceFlinger / Display Present``

概念辨析
--------

* ``Jank`` 不是“某段代码超过 16ms”的同义词；真正判断依据是是否错过当前目标刷新周期的 deadline。
* Main Thread 阻塞既可能是 CPU 计算，也可能是锁、futex、Binder/XPC 等等待，两者优化方向完全不同。
* GPU busy 与 GPU wait 不同：前者说明硬件工作量高，后者可能在等依赖、同步或资源。
* FPS 稳定不代表低延迟；buffer queue 很深时可以维持帧率，同时让输入结果晚多个周期出现。
* 掉帧和输入延迟高度相关，但输入系统、App 处理和显示流水线仍应分别测量。

本章结论
--------

Jank 必须按一帧的完整责任链诊断。先找到哪一帧晚，再确定晚在 Main Thread、Render Thread、GPU、buffer/fence、compositor 还是 display。只有责任层级确认后，优化才有意义。