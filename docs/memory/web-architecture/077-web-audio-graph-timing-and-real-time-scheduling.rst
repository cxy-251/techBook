Web Audio Graph, Timing, and Real-Time Scheduling
=================================================

核心知识点
----------

* Web Audio 把声音处理表示为一张由 ``AudioNode`` 组成的图，``AudioContext`` 是运行时中心，负责时间线、节点连接、调度和最终输出。
* 常见节点包括 source、gain、filter、analyser、panner、destination；应用通过连接关系表达“声音从哪里来、经过什么处理、送到哪里”。
* 音频时间要求比普通 UI 更严格。主线程 timer、React/Vue 更新、GC 或长任务都不能承担样本级实时调度职责。
* ``AudioContext.currentTime`` 是音频调度基准；播放、参数 automation 和事件应尽量按音频时间线安排，而不是依赖 ``setTimeout`` 的墙钟回调精度。
* ``AudioWorklet`` 允许自定义处理进入更接近实时音频线程的路径，适合 DSP、合成器、效果器和低延迟处理。
* AudioWorkletProcessor 内应避免阻塞、不可预测大计算和频繁分配；控制参数与 UI 状态通过 ``MessagePort`` 或 AudioParam 跨线程传递。
* Web Audio 可与 ``MediaStream``、媒体元素、WebRTC track、麦克风输入和录制输出组合，形成采集、处理、传输和播放闭环。
* autoplay、用户激活、页面可见性、后台策略、音频设备切换和权限变化都会影响 AudioContext 的 ``suspended/running/closed`` 状态。
* 实时音频架构必须把 latency、buffer、clock、device、线程边界与恢复路径作为一级约束，而不是最后调优项。

关键路径
--------

基本图：

``Audio Source → AudioNode Graph → AudioContext Clock → Destination / Device``

实时处理：

``User / App State → Main Thread Control → MessagePort / AudioParam → AudioWorkletProcessor → Audio Graph → Output``

与 WebRTC/媒体协同：

``Microphone / MediaStream / MediaElement → Web Audio Graph → processing/analyser → MediaStreamDestination / speakers / recorder / peer connection``

故障排查依次确认：context 状态 → 用户激活/权限 → device 与 sample rate → graph 是否连接 → processing 是否赶上实时 deadline → 是否存在主线程或消息通道积压。

概念辨析
--------

* **Web Audio graph ≠ DOM 树**：节点是音频运行时对象，不参与页面布局。
* **AudioContext 时间 ≠ ``Date.now()`` / timer 时间**：音频调度应依赖音频时钟。
* **AudioWorklet ≠ 普通 Worker**：它服务于实时音频处理路径，执行约束更严格。
* **主线程不卡 ≠ 音频一定稳定**：worklet 算法过重、设备 buffer 太小或输入输出时钟异常同样会爆音。
* **权限通过 ≠ 音频自动播放**：浏览器 autoplay 和用户激活策略仍可能让 context 保持 suspended。

本章结论
--------

Web Audio 的核心模型是“以 AudioContext 时钟驱动的实时处理图”。主线程负责交互和控制，音频图负责持续信号处理，AudioWorklet 承担自定义低延迟 DSP。稳定系统必须围绕音频时钟、实时 deadline、跨线程通信、设备状态和浏览器播放策略设计。