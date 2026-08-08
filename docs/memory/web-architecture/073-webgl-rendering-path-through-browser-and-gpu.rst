WebGL Rendering Path Through Browser and GPU
============================================

核心知识点
----------

* WebGL 通过浏览器向页面暴露受控 GPU 渲染能力；页面获得的是浏览器管理的图形上下文，不是对原生 GPU 驱动的直接访问。
* WebGL 的核心资源包括 buffer、texture、shader、program、uniform、framebuffer 和 draw call；应用负责创建、绑定、更新和释放这些资源。
* 典型渲染路径是 CPU 组织场景与命令，浏览器验证调用，再由图形栈/GPU 执行 shader、光栅化与纹理访问，最终结果进入浏览器合成管线。
* 浏览器需要验证参数、初始化资源、限制越界访问、隔离页面和驱动故障，因此 WebGL 的行为不能简单等同于原生 OpenGL。
* CPU 与 GPU 异步工作。大量 draw call、频繁状态切换、纹理上传、同步 readback 和主线程计算都可能比 shader 本身更早成为瓶颈。
* GPU 资源上传和读回都跨越 CPU/GPU 边界；反复 ``readPixels``、大纹理更新和每帧重新创建资源会制造同步与带宽成本。
* WebGL context loss 是一级故障：GPU reset、驱动异常、资源压力或浏览器策略都可能使 context 丢失，应用必须能停止提交并重建资源。
* 资源生命周期要显式：场景销毁、路由切换或 context 恢复时，应释放/重建 buffer、texture、program 和 framebuffer，而不是只删除 JavaScript 引用。

关键路径
--------

``Application State → JS / Engine → WebGL API → Browser Validation → Graphics Process / Driver → GPU Pipeline → Surface → Browser Compositor → Display``

单帧常见路径：

``Update CPU State → Upload/Bind Resources → Set Program/Uniforms → Draw Calls → GPU Execute → Framebuffer → Composite``

故障恢复：

``webglcontextlost → stop rendering / preserve app state → recreate context → recreate GPU resources → restore scene → resume``

性能分析依次检查：主线程计算 → draw call / state change → buffer/texture upload → shader 与 fill rate → GPU/CPU 同步点 → compositor。

概念辨析
--------

* **WebGL ≠ 原生 OpenGL 直通**：浏览器在 API 与驱动之间增加验证、安全和隔离层。
* **JavaScript 调用返回 ≠ GPU 已完成**：命令可能仍在 GPU 队列中执行。
* **GPU 加速 ≠ 自动高性能**：CPU 调度、资源搬运、状态切换和同步读回都能吞掉收益。
* **删除 JS 对象 ≠ GPU 资源立即释放**：GPU 资源有独立生命周期，应主动 dispose/delete。
* **context loss ≠ 普通绘制异常**：原有 GPU 对象通常不能继续使用，需要完整重建。

本章结论
--------

WebGL 的稳定心智模型是“浏览器托管的 GPU 命令管线”。应用负责资源与命令，浏览器负责安全验证和图形上下文，GPU 异步执行，浏览器再把结果合成到页面。性能和可靠性都应围绕 CPU/GPU 协作、资源生命周期、同步点和 context loss 设计。