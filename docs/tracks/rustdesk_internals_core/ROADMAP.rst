====================================================
RustDesk 核心架构与远程桌面底层机制专著开发路线图
====================================================

本项目旨在对开源远程桌面系统 **RustDesk** 进行端到端、源码级的深度架构解剖。

.. note:: 编写与施工规范
   * 遵循严格的知识拓扑顺序：硬件与操作系统原语 -> 音视频与编解码管线 -> 网络打洞与信令 -> 安全加密 -> 客户端状态机 -> FFI 与跨平台 UI -> 服务端中继调度。
   * 单章保持高信息密度（5KB~15KB），结合物理事实、汇编/内核 API、Rust 数据结构所有权与并发模型展开，严禁浅层概括。

里程碑总览
==========

模块 01：操作系统与硬件底层交互原语 (01_os_and_hardware_abstraction) [已完结]
---------------------------------------------------------------------------------
- [x] 01. 跨平台屏幕像素捕获底层原语与抓屏引擎实现 (01_screen_capture_primitives.rst)
- [x] 02. 跨平台输入事件注入引擎与多端同步实现 (02_input_injection_engine.rst)
- [x] 03. 低延迟音频捕获、混音与回放子系统 (03_audio_capture_pipeline.rst)
- [x] 04. IddCx 虚拟显示驱动与隐私屏黑屏机制 (04_virtual_display_drivers.rst)

模块 02：音视频媒体管线与编解码 (02_media_pipeline_and_codecs) [已完结]
-------------------------------------------------------------------------
- [x] 01. 帧缓冲对齐、色彩空间转换 (YUV/NV12) 与零拷贝模型 (01_framebuffer_and_zerocopy.rst)
- [x] 02. 软件视频编码器集成与优化 (libvpx VP8/VP9, libaom AV1) (02_software_codecs_vpx_aom.rst)
- [x] 03. 硬件加速编解码架构 (NVENC, QSV, AMF, VideoToolbox) (03_hardware_accel_nvenc_qsv.rst)
- [x] 04. 动态码率自适应、丢包补偿与帧率平滑调度 (04_adaptive_bitrate_control.rst)

模块 03：信令通道、Protobuf 与 NAT 穿透 (03_network_signaling_and_nat) [已完结]
---------------------------------------------------------------------------------
- [x] 01. Protobuf 协议模型设计与消息帧编解码 (01_protobuf_protocol_models.rst)
- [x] 02. 自研可靠 UDP / KCP 传输层与拥塞控制算法 (02_udp_reliable_transport.rst)
- [x] 03. NAT 类型探测与 UDP Hole Punching P2P 打洞机制 (03_nat_traversal_and_punching.rst)
- [x] 04. rendezvous_mediator 状态机与连接建立全流程 (04_rendezvous_mediator_state.rst)

模块 04：端到端加密与安全会话 (04_security_and_encryption) [已完结]
---------------------------------------------------------------------
- [x] 01. 基于 NaCl / libsodium 的非对称密钥体系与 Ed25519 身份认证 (01_nacl_cryptographic_primitives.rst)
- [x] 02. X25519 密钥协商与临时会话对称密钥派生 (02_x25519_key_exchange.rst)
- [x] 03. 会话数据流加密 (XSalsa20/ChaCha20-Poly1305) 与防重放攻击 (03_session_packet_encryption.rst)
- [x] 04. 权限控制模型、一次性口令与 Windows 服务提权 (04_privilege_elevation_model.rst)

模块 05：客户端架构、Tokio 运行时与状态机 (05_client_architecture_and_state) [已完结]
-----------------------------------------------------------------------------------------
- [x] 01. Tokio 异步运行时拓扑与 IO/Worker 线程池协同机制 (01_tokio_async_concurrency.rst)
- [x] 02. 客户端生命周期状态机与多路复用连接管理 (02_client_lifecycle_statemachine.rst)
- [x] 03. 文件传输子系统：并发分块传输、断点续传与校验 (03_file_transfer_subsystem.rst)
- [x] 04. 端口转发、TCP/UDP 隧道与远程打印协议扩展 (04_tunneling_and_port_forwarding.rst)

模块 06：Rust-Flutter FFI 桥接与跨平台渲染 (06_ffi_bridge_and_ui) [已完结]
---------------------------------------------------------------------------
- [x] 01. flutter_rust_bridge 架构与跨语言内存安全传递 (01_flutter_rust_bridge_codegen.rst)
- [x] 02. StreamSink 异步事件总线与 UI 状态同步模型 (02_streamsink_and_event_loops.rst)
- [x] 03. 远程桌面画面渲染：GPU Texture 纹理共享与着色器流水线 (03_texture_rendering_backend.rst)

模块 07：服务端架构与中继调度 (07_server_infrastructure_and_relay) [已完结]
---------------------------------------------------------------------------
- [x] 01. 注册与 ID 寻址服务器 (hbbs) 架构与 Peer 状态存储 (01_hbbs_id_server_internals.rst)
- [x] 02. 中继服务器 (hbbr) 高并发数据转发与限速模型 (02_hbbr_relay_server_pipeline.rst)
- [x] 03. 自建服务集群部署、证书认证与高可用故障转移 (03_cluster_routing_and_failover.rst)
