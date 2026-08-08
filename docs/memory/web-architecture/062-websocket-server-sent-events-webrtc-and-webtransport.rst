第062章：WebSocket, Server-Sent Events, WebRTC, and WebTransport
================================================================

核心知识点
----------

* 实时 Web 的核心变化是连接生命周期取代单次 request/response 生命周期。需要额外设计连接状态、消息顺序、重连、恢复、背压和页面生命周期。
* 选型先看状态语义，再看 API：消息方向、延迟目标、可靠性、是否允许丢弃、是否需要媒体、最终状态由谁拥有，决定通信模型。
* WebSocket 提供浏览器与服务器之间的持久双向应用消息通道。它适合协作、聊天、presence、行情等双向状态，但消息 schema、权限、版本、排序和恢复都要由应用协议定义。
* WebSocket 断线恢复不是协议自动完成。durable state 需要序号、版本、事件日志或快照；cursor/presence 等 ephemeral state 可以重连后重新发布。
* 浏览器标准 ``WebSocket`` 接口缺少完整 backpressure；需要结合 ``bufferedAmount``、服务端限速、消息合并和慢客户端处理控制队列增长。
* Server-Sent Events（SSE）是 server → browser 的长期文本事件流，适合任务进度、状态推送和通知；浏览器向服务器提交新动作仍用普通 HTTP 请求。
* WebRTC 解决浏览器间或浏览器到媒体基础设施的低延迟媒体/数据通信。signaling 由应用自定义，ICE/STUN/TURN 负责连通性协商，媒体权限和轨道生命周期属于浏览器设备能力边界。
* WebTransport 面向支持 HTTP/3 的 client-server 低延迟传输，可提供双向/单向 stream 与 datagram；它更接近传输层，应用必须自行定义消息、可靠性、恢复和认证语义。
* “实时”不等于“所有消息都必须可靠”。编辑提交需要 durable ordering；cursor 可以丢旧状态；音视频更关心延迟；datagram 适合可容忍丢失的新鲜状态。

关键路径
--------

WebSocket 协作：

::

   Browser local state
     → WebSocket message
     → realtime server
     → auth / room / ordering
     → durable log or current state
     → broadcast
     → clients apply by version

SSE 进度：

::

   POST create job
     → jobId
     → EventSource /jobs/:id/events
     → server event stream
     → progress / complete / failed
     → UI

WebRTC：

::

   User grants media permission
     → getUserMedia tracks
     → app signaling
     → SDP / ICE candidates
     → STUN / TURN / peer connectivity
     → encrypted media/data path
     → track lifecycle / renegotiation

WebTransport：

::

   Browser
     → HTTP/3 WebTransport session
     → reliable streams and/or datagrams
     → application framing / flow control
     → server realtime state

概念辨析
--------

* WebSocket 与 SSE：WebSocket 双向；SSE 主要是服务器单向推送，发送动作继续走普通 HTTP。
* WebSocket 与 WebRTC：WebSocket 是 client-server 应用消息；WebRTC 更适合实时音视频和 peer/data channel 场景，并需要 signaling 与 NAT traversal。
* WebSocket 与 WebTransport：前者提供消息式双向通道，生态成熟；后者更接近 QUIC transport，提供多 stream/datagram 与更细粒度传输控制。
* 实时连接与 durable state：连接只负责传输，数据库、事件日志或业务服务器才负责可恢复事实。
* 重连与恢复：重新建立 socket 只恢复连接，不自动补回断线期间的业务状态。
* 低延迟与无序/丢弃：是否允许丢消息由业务状态语义决定，不能单凭 API 名称判断。

本章结论
--------

实时能力选型固定检查 ``Direction → State Owner → Reliability → Latency → Recovery → Flow Control``。WebSocket 适合双向应用消息，SSE 适合服务器事件流，WebRTC 适合媒体与 peer communication，WebTransport 适合需要 stream/datagram 控制的低延迟 client-server 传输。真正的系统设计在连接之外：权限、版本、顺序、快照、重连和慢客户端策略决定实时功能是否可靠。