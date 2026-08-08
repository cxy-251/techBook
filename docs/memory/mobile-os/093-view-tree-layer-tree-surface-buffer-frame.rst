第093章：View Tree, Layer Tree, Surface, Buffer, Frame
====================================================

核心知识点
----------

* ``View Tree`` 表达 UI 结构、布局、事件命中、状态和无障碍语义；它解决“界面是什么、谁响应事件、哪里需要更新”。
* ``Layer Tree`` 表达可合成的视觉状态，如位置、transform、opacity、clip、shadow、corner radius 和动画；它解决“视觉对象怎样被组合”。
* ``Surface`` 是图形内容从生产者进入系统合成路径的提交边界，常对应窗口、视频、相机预览或自定义 GPU 内容。
* ``Buffer`` 是像素或 GPU 可读写内存的真实载体。跨进程图形传递通常传递 buffer handle、共享内存引用和 fence，而不是复制整块像素。
* ``Frame`` 是一次 ``Acquire → Render → Queue → Compose → Present → Release`` 的生命周期，不只是某一块 buffer。
* 图形系统可统一为 Producer / Consumer 模型：App、Camera、Decoder 生产 buffer；SurfaceFlinger、Core Animation / display service、显示控制器消费或继续转交。

关键路径
--------

``UI State → View Tree → Layer Tree → Surface → Buffer Queue → Compositor → Display``

典型 buffer 生命周期：

``Acquire / Dequeue → Render → Queue → Fence Signal → Latch / Acquire → Compose → Present → Release``

视频页面的统一读法：

``Video Decoder → Video Surface / Buffer``

``UI View Tree → UI Layer / Buffer``

``Video + UI + System UI → System Compositor → Display``

概念辨析
--------

* ``View`` 是交互与布局对象；``Layer`` 是视觉合成对象，两者不是同一层级。
* ``Surface`` 是提交边界；``Buffer`` 是数据载体。Surface 本身不是像素内存。
* ``Window`` 管焦点、大小、输入区域和系统策略；``Surface`` 负责图形内容提交。
* ``Buffer`` 不等于 ``Frame``：同一帧可能涉及多个 Layer 的多个 buffer，以及一组 transaction 和 fence。
* ``Model layer`` 表示目标视觉状态，``presentation layer`` 表示动画中的当前可见状态；二者在 Apple Core Animation 中尤其需要区分。

本章结论
--------

View、Layer、Surface、Buffer、Frame 分别对应 UI 语义、视觉状态、提交边界、像素载体和时间生命周期。排查问题时应先判断异常属于结构、视觉属性、跨进程提交、buffer 同步还是帧调度，再进入对应层级。