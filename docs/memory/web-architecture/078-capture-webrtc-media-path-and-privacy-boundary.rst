Capture, WebRTC Media Path, and Privacy Boundary
===============================================

核心知识点
----------

* 摄像头、麦克风和屏幕共享首先是权限与设备能力问题。浏览器在 secure context、用户意图、设备选择和权限状态满足后，才向页面返回媒体句柄。
* ``MediaStream`` 与 ``MediaStreamTrack`` 表示活跃媒体能力；track 具有 ``enabled``、``muted``、``readyState``、``ended`` 等生命周期状态，可被 stop、replace 或因设备/权限变化终止。
* WebRTC 把 signaling 与媒体传输分开。SDP/offer/answer/candidate 如何通过业务服务器交换由应用决定；浏览器负责 ``RTCPeerConnection``、ICE、DTLS、SRTP、RTP/RTCP 等媒体连接能力。
* ICE 负责在真实网络中寻找可用路径；STUN 用于发现网络映射，TURN 在无法直连时提供 relay。TURN 带宽和区域部署直接影响可靠性、成本和延迟。
* WebRTC 连接是动态状态机。网络切换、Wi-Fi/蜂窝变化、NAT、企业防火墙、candidate 变化和带宽波动都可能触发重协商或路径变化。
* 实时媒体质量需要在 bitrate、resolution、frame rate、codec、丢包、jitter、RTT 和 CPU/GPU 编码负载之间动态权衡。
* 屏幕共享具有更强隐私风险：被共享的窗口、标签页、通知和其他应用都可能暴露敏感信息，浏览器必须提供明确选择与持续共享提示。
* 页面应在用户结束通话、切换设备、撤销权限或路由离开时主动停止不再需要的 track，释放设备占用并更新 UI。
* 隐私边界属于媒体架构本身：采集什么、传到哪里、是否录制、保存多久、谁能访问，都需要与 codec 和网络设计同时确定。

关键路径
--------

采集：

``User Action → getUserMedia/getDisplayMedia → Browser Permission + Device Selection → MediaStreamTrack → local preview / processing``

WebRTC：

``Application Signaling → offer/answer + ICE candidates → RTCPeerConnection → ICE path(STUN/TURN/direct) → DTLS/SRTP → remote peer/media server``

运行时恢复：

``network/device/permission change → track/connection state change → detect → renegotiate / replaceTrack / lower quality / reconnect → restore UI state``

排查顺序：权限与设备 → track 状态 → signaling 是否一致 → ICE candidate/connection state → TURN 可达性 → codec/带宽统计 → 用户可见恢复。

概念辨析
--------

* **WebRTC ≠ signaling 协议**：WebRTC 不规定业务服务器如何交换 offer、answer 和 candidate。
* **MediaStreamTrack ≠ 媒体文件**：它是实时能力句柄，生命周期随设备、连接和权限变化。
* **STUN ≠ TURN**：STUN 帮助发现可直连地址，TURN 实际转发媒体流量。
* **连接建立 ≠ 媒体质量稳定**：带宽、丢包、编码器负载和设备变化会持续改变体验。
* **用户授权一次 ≠ 永久设备所有权**：权限可撤销，track 可结束，应用必须随时处理失效。

本章结论
--------

实时音视频的完整模型是“用户授权的媒体能力 + 应用 signaling + 浏览器 WebRTC 传输 + 网络穿透/relay + 动态恢复”。隐私、设备生命周期、ICE/TURN、质量自适应和停止采集都属于主路径，不能被当作媒体 API 之外的附加问题。