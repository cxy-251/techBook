第149章：云端与远程图形
=====================

核心知识点
----------

Cloud/Remote Graphics 的核心是把渲染地点从本地设备迁到远端 GPU
   客户端主要负责输入采集、媒体解码和显示；服务端负责应用逻辑、GPU 渲染、编码和会话运行。用户体验由图形管线和媒体传输管线共同决定。

远程图形必须按端到端交互闭环理解
   输入 → 上行网络 → 服务端 simulation/render → encode → 下行网络 → jitter buffer → decode → display → 下一次输入。任何一段过慢，都会让用户感觉“画面隔着一层缓冲”。

服务端 FPS 不能代表真实交互延迟
   即使 GPU 稳定 60 FPS，输入上行、编码、网络抖动、客户端解码和显示队列仍可能产生明显迟滞。真正要观察的是 input-to-display / round-trip feedback latency。

编码器是图形管线后的正式阶段
   Framebuffer 生成后还要 color conversion、encode、packetize。低延迟编码通常需要减少缓冲和参考结构，代价是码率上升或同码率画质下降。Encoder time、QP、dropped frame 都应进入 telemetry。

Jitter Buffer 在稳定与延迟之间取舍
   缓冲更大可以吸收网络抖动，却直接增加交互延迟；缓冲更小则更容易出现卡顿、马赛克和帧丢失。不同应用应使用不同策略，不能统一套视频点播逻辑。

远程桌面、云游戏、XR 串流和数字孪生共享同一基本链路
   差异主要在延迟敏感度、图像内容、输入频率、文字清晰度、双眼/头动要求和会话持续时间。底层都需要 session、GPU、encoder、network、client 和 telemetry 协同。

Session Manager 决定用户连接到哪个运行实例
   它要处理认证、区域选择、新建/恢复/迁移/销毁，并判断目标应用需要何种 GPU、显存、encoder 和持久化状态。错误的区域或实例选择会直接变成高 RTT、冷启动和能力不匹配。

GPU Scheduler 必须把显存、编码器和网络出口一起调度
   远程图形不是只分配 GPU 算力。每个会话还需要 VRAM、encoder session、CPU、network bandwidth 和隔离。共享 GPU 会提高利用率，也会引入时间片、显存碎片和资源争用。

Asset Cache 是云图形的重要性能层
   CAD、数字孪生和大型 DCC 工程常受首次资源加载影响。模型、texture、shader cache、plugin 和用户配置应尽可能靠近渲染节点，降低冷启动与重复下载。

Telemetry 必须覆盖全链路而不是只看 GPU
   需要同时记录 input timestamp、RTT、server CPU/GPU frame、encode time、bitrate、packet loss、jitter、decode time、present time、session load、VRAM、encoder utilization 和区域信息。

区域部署决定网络延迟下限
   用户离 GPU 节点越远，RTT 和抖动越难压低。低延迟应用应优先做 region/edge placement，再谈 shader 微优化。云游戏与 XR 对区域距离尤其敏感。

GPU Virtualization 提高并发密度，也增加稳定性风险
   独占 GPU 最稳定但成本高；vGPU/共享 GPU 可以提升利用率，却可能受显存配额、encoder 争用和邻居负载影响。应用类型需要对应不同 profile。

Streaming Rendering 的视觉质量由运动复杂度和码率共同决定
   静态 CAD 画面容易压缩，高速镜头、粒子、噪声、细网格和文本会增加编码压力。固定码率下，高运动场景更容易出现块效应和细节丢失。

Adaptive Bitrate 应与图形质量联动
   网络恶化时，可以先降 bitrate，也可以降低 render resolution、frame rate、效果质量或采用更保守编码参数。只让 encoder 独自承担网络压力，可能导致不可读文字或高频结构崩坏。

成本优化要绑定任务语义
   静态设计审阅可降低帧率、共享 GPU 并提高文字码率优先级；高动态演示、游戏和 XR 需要更稳定帧 pacing 与低延迟。资源 profile 应服务实际用户任务，而不是固定 60 FPS/固定 bitrate。

冷启动是成本与体验的交叉点
   预热实例和缓存能缩短启动，但会增加空闲成本；完全按需启动更省钱，却可能让用户等待镜像、驱动、资产和 shader cache。平台应基于使用模式设计 warm pool。

Cloud Gaming 最能暴露端到端问题
   玩家持续输入、画面高速运动，任何上行 RTT、simulation tick、GPU spike、encoder backlog、packet loss、decode/present 队列都会被感知。需要同时报告 server rendered FPS 与用户端实际显示/响应。

关键路径
--------

远程交互帧：

::

   client input sample
   → uplink / gateway
   → server simulation
   → GPU render
   → framebuffer capture
   → hardware encode
   → network transport
   → jitter buffer
   → client decode
   → display present
   → next user input

平台调度：

::

   user/session request
   → choose low-RTT region
   → choose GPU/vGPU profile
   → allocate VRAM + encoder + bandwidth
   → attach asset cache
   → start or resume application
   → stream telemetry
   → scale / migrate / degrade if needed

卡顿排查：

::

   remote experience bad
   → verify input reaches server
   → inspect server CPU/GPU frame pacing
   → inspect encoder latency/drops
   → inspect RTT/loss/jitter
   → inspect client decode/present
   → correlate with session/resource contention

概念辨析
--------

* **Server FPS 与 End-to-End Latency**：服务端帧率只覆盖远端渲染，用户还要经历网络、编码、解码和显示。
* **Cloud Rendering 与 Video Streaming**：前者有交互闭环，输入会改变下一批服务端帧；普通视频主要是单向播放。
* **GPU Sharing 与 Free Capacity**：共享提高利用率，也会引入资源争用和尾部延迟。
* **Bitrate 与 Render Quality**：前者控制媒体压缩，后者控制服务端生成图像；两者会共同影响用户看到的质量。
* **Jitter Buffer 与 Network Fix**：缓冲只能吸收到达时间波动，不能消除高 RTT 或长期带宽不足。
* **Cold Start 与 Runtime Performance**：冷启动影响会话建立，运行后帧性能是另一条独立路径。

本章结论
--------

云端与远程图形应按“Input—Region/Session—Server Render—Encode—Network—Decode—Display—Telemetry/Cost”理解。稳定平台必须同时管理 GPU、显存、encoder、资产缓存和网络，并用端到端时间戳把用户感知问题定位到具体链路；性能与成本优化也应围绕实际任务、区域距离和并发模型，而不是只追求服务端高 GPU 利用率。