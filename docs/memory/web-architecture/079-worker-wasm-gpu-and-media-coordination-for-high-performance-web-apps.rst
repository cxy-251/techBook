Worker, WASM, GPU, and Media Coordination for High-Performance Web Apps
======================================================================

核心知识点
----------

* 高性能 Web 应用通常不是单管线系统，而是 DOM/UI、Worker、WASM、WebGL/WebGPU、WebCodecs、Web Audio、WebRTC、Canvas 等执行区协同工作的结果。
* 主线程应优先保留用户输入、DOM、焦点、可访问性和最终 UI 提交；可隔离的计算、解析、仿真、编码或批处理适合进入 Worker。
* Worker 的收益来自减少主线程压力，成本来自消息协议、structured clone、transferable、线程启动、错误传播和生命周期管理。
* WebAssembly 适合把 C/C++/Rust 等编译产物放入浏览器沙箱执行高密度计算，但仍受线性内存、JS/WASM binding、线程能力、安全上下文和浏览器资源限制。
* GPU 与媒体工作通常异步于 JavaScript：``queue.submit``、draw call、encode/decode、AudioWorklet、WebRTC 传输都可能在 JS 调用返回后继续推进。
* 数据移动经常比计算更贵。structured clone、buffer copy、CPU↔GPU upload/readback、frame 转换、序列化和跨线程消息都要计入端到端预算。
* 能转移所有权时优先使用 transferable；真正需要共享内存时才使用 ``SharedArrayBuffer``，并同时承担 cross-origin isolation 与并发协议成本。
* 多管线系统必须有背压。视频帧、网络消息、GPU command、音频块和 Worker 任务若生产速度高于消费速度，应丢弃、合并、降采样、限流或暂停输入。
* 系统应显式记录每份数据的 owner、格式、时间戳、版本和生命周期，避免同一帧/同一状态在多个 runtime 中形成不可控副本。
* 高性能架构最终优化的是用户可见 deadline：输入响应、帧时间、音频连续性、端到端媒体延迟和内存稳定，而不是单个函数 benchmark。

关键路径
--------

典型多管线：

``User Input → Main Thread State → Worker/WASM Compute → transferable result → WebGPU/Canvas/WebCodecs → Browser Compositor/Media Output → User``

实时媒体示例：

``Capture → MediaStream/VideoFrame → Worker/WASM processing → GPU processing / encoder → WebRTC → remote → decode/render``

背压控制：

``Producer rate > Consumer rate → queue growth → latency/memory growth → drop/coalesce/throttle/pause → bounded queue``

分析顺序：先画 runtime 图 → 标出数据副本和所有权 → 标出异步队列 → 查找同步等待与大数据搬运 → 定义每条管线 deadline → 加入取消、背压、device/context loss 与降级。

概念辨析
--------

* **Worker ≠ 自动加速**：小任务或大对象频繁复制时，通信开销可能超过计算收益。
* **WASM ≠ 绕过浏览器沙箱的原生程序**：它仍运行在浏览器受控 runtime 内。
* **GPU submit ≠ GPU 完成**：提交后仍要考虑 in-flight 资源和同步点。
* **零拷贝 ≠ 没有所有权变化**：transferable 会转移资源控制权，共享内存则需要显式并发协议。
* **队列吞吐高 ≠ 用户延迟低**：无限排队可以提高总吞吐，却会让实时体验持续变差。
* **单组件快 ≠ 整体系统快**：跨 runtime 数据移动、调度和同步才是复杂 Web 应用的常见瓶颈。

本章结论
--------

高性能 Web 架构应被理解为“多 runtime、多异步队列、多资源管线的能力编排”。主线程保护交互，Worker/WASM 承担可隔离计算，GPU/媒体管线异步执行；数据移动、所有权、背压、同步与故障恢复决定最终性能。优化必须面向端到端用户 deadline，而不是孤立 API。