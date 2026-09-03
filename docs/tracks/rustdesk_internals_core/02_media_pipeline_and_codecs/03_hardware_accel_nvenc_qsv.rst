======================================================================
02.03 硬件加速编解码架构 (NVENC, QSV, AMF, VideoToolbox)
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《02.02 软件视频编码器集成与优化 (libvpx VP8/VP9, libaom AV1)》中，我们解剖了纯 CPU 软件编码器在极低延迟约束下的多线程分片与屏幕内容感知优化。软件编码虽然具备极高的通用性与兼容性，但在高分辨率（$2	ext{K}/4	ext{K}$）与高刷新率（$60	ext{FPS}/120	ext{FPS}$）场景下，CPU 占用率和功耗急剧上升。现代 PC 与移动设备均集成了**专用硬件编解码芯片（ASIC Dedicated Media Engines）**。如何屏蔽异构芯片厂商的 API 差异？如何实现显存级零拷贝与动态码率热重配？当硬件编码器发生驱动重置（TDR）或显存耗尽时如何平滑回退？本章将深入剖析 RustDesk 在 ``libs/scrap/src/common/hwcodec.rs``、``vram.rs`` 及 ``codec.rs`` 中的跨平台硬件加速架构。

***
专用 ASIC 硬件编解码器物理架构与跨厂商生态
***

现代 GPU 与 SoC 内部开辟了独立于 3D 渲染核心（Shader Cores / ALUs）的固定功能硬件视频处理单元。硬件编码器直接对显存中的未压缩像素执行硬件级离散余弦变换（DCT）、运动估计（ME）与熵编码（CABAC），完全不占用 CPU 计算周期与 GPU 3D 渲染管线。

.. list-table:: 主流硬件编解码引擎与接口对比
   :widths: 18 20 32 30
   :header-rows: 1

   * - 硬件厂商 / 平台
     - 专用 ASIC 核心
     - 核心 SDK / API 抽象层
     - 典型原生输入格式与特性
   * - **NVIDIA**
     - NVENC / NVDEC
     - NVIDIA Video Codec SDK / Direct3D11 Interop
     - NV12 / P010，极速微秒级延迟，无 B 帧超低延迟模式
   * - **Intel**
     - Quick Sync Video (QSV)
     - Intel Media SDK / oneVPL / VAAPI
     - NV12，集成于 Iris / UHD 核显，能效比极高
   * - **AMD**
     - VCE / VCN
     - AMD Advanced Media Framework (AMF)
     - NV12，支持 Direct3D11 / Vulkan 纹理共享
   * - **Apple**
     - Apple Media Engine
     - CoreVideo / VideoToolbox
     - IOSurface / CVPixelBuffer，统一内存架构（UMA）零拷贝直通
   * - **Android**
     - 移动 SoC DSP / NPU
     - Android NDK MediaCodec (Codec2 / OMX)
     - Surface / AHardwareBuffer，跨进程 DMA 缓冲直通

---
RustDesk ``hwcodec`` 统一硬件抽象层设计
---

为了避免在上层业务逻辑中编写大量针对各厂商 SDK 的分支判断，RustDesk 在 ``libs/scrap/src/common/hwcodec.rs`` 中构建了高度统一的硬件加速抽象层：

```
                    [ 统一编码调度层 (EncoderApi) ]
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
[ VRamEncoder (显存直通零拷贝) ]                     [ HwRamEncoder (系统内存中转) ]
         │                                                   │
         ├─────────────────────────┬─────────────────────────┤
         ▼                         ▼                         ▼
   [ NVIDIA NVENC ]         [ Intel QSV/oneVPL ]        [ AMD AMF ]
         │                         │                         │
         └─────────────────────────┴─────────────────────────┘
                                   │
                  [ Apple VideoToolbox / MediaCodec ]
```

1. 运行时硬件能力探测（Runtime Capability Probing）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在系统启动或服务初始化阶段，RustDesk 会主动执行硬件探测，向 GPU 驱动查询支持的编码标准（H.264 / H.265 / AV1）、最大吞吐分辨率、GOP 参数以及 LUID（Locally Unique Identifier）物理设备绑定关系：

.. code-block:: rust
   :caption: 硬件编解码能力探测与上下文初始化（libs/scrap/src/common/vram.rs）

   pub(crate) fn check_available_vram() -> (Vec<FeatureContext>, Vec<DecodeContext>, String) {
       let d = DynamicContext {
           device: None,
           width: 1280,
           height: 720,
           kbitrate: 5000,
           framerate: 60,
           gop: MAX_GOP as _,
       };
       // 探测系统中所有可用 GPU 的硬件编码器与解码器实例
       let encoders = encode::available(d);
       let decoders = decode::available();
       let available = Available {
           e: encoders.clone(),
           d: decoders.clone(),
       };
       (
           encoders,
           decoders,
           available.serialize().unwrap_or_default(),
       )
   }

2. 双轨数据通道：VRamEncoder 与 HwRamEncoder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 根据抓屏来源与显卡拓扑自适应选择数据路径：

* **``VRamEncoder``（纯显存零拷贝模式）**：
  直接接收 DXGI Desktop Duplication 输出的 ``ID3D11Texture2D`` 显存纹理指针，通过硬件驱动共享句柄直接送入 ASIC 编码器，完全消除 PCIe 显存-内存总线拷贝。
* **``HwRamEncoder``（内存中转模式）**：
  当抓屏源为跨显卡（如集显抓屏、独显编码）或软抓屏（GDI / X11 SHM）时，将系统内存中的 NV12 数据通过 DMA 上传至硬件编码器的输入表面进行硬件压缩。

---
超低延迟硬件参数实时调控
---

通用视频播放器通常采用数十帧的缓冲区以保证播放平滑，但远程控制必须追求极致的单帧处理速度与瞬时网络响应。

1. 实时流预设与无 B 帧管道（Zero B-Frames & Low Latency）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

硬件编码器必须强制关闭 B 帧（双向预测帧）。因为 B 帧的解码依赖于未来的 P 帧，引入 B 帧必然导致编码器产生重排序延迟（Reordering Delay）：

.. code-block:: rust
   :caption: 低延迟硬件编码上下文参数构造

   let ctx = EncodeContext {
       f: config.feature.clone(),
       d: DynamicContext {
           device: Some(config.device.device),
           width: config.width as _,
           height: config.height as _,
           kbitrate: bitrate as _,
           framerate: 30,
           gop: config.keyframe_interval.unwrap_or(MAX_GOP as _) as i32,
       },
   };

2. 动态码率无缝热重配（Dynamic Bitrate Reconfiguration）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当网络发生丢包或带宽波动时，RustDesk 必须实时动态调整编码器输出码率，而不能通过“销毁并重建编码器”来改变参数（销毁重建会导致数百毫秒的画面黑屏与卡顿）：

.. code-block:: rust
   :caption: 硬件编码器无损热调速（libs/scrap/src/common/vram.rs）

   fn set_quality(&mut self, ratio: f32) -> ResultType<()> {
       let bitrate = Self::bitrate(
           self.ctx.f.data_format,
           self.ctx.d.width as _,
           self.ctx.d.height as _,
           ratio,
       );
       if bitrate > 0 {
           // 调用驱动级 API 热更新码率寄存器，无需重启编码会话
           if self.encoder.set_bitrate((bitrate) as _).is_ok() {
               self.bitrate = bitrate;
           }
       }
       Ok(())
   }

---
硬件异常检测与容灾自动降级机制
---

硬件加速虽然性能强劲，但在复杂的客户端 PC 环境中极易遭遇硬件异常：例如 AMD 显卡在静态画面时可能出现驱动编码长度锁定卡死（AMF Bug）、笔记本在拔掉电源时触发核显/独显热切换，或显卡超频引发 TDR 重置。

RustDesk 在底层建立了严格的**故障探测与状态机降级模型**：

.. code-block:: rust
   :caption: 坏帧连续计数与编码器自愈切换（libs/scrap/src/common/vram.rs）

   // 针对 AMD AMF 驱动在静态画面下编码输出长度异常固定的缺陷（如持续输出 40 字节空包导致画面冻结）
   const MIN_BAD_LEN: usize = 100;
   const MAX_BAD_COUNTER: usize = 30;

   let this_frame_len = frames[0].data.len();
   if this_frame_len < MIN_BAD_LEN && this_frame_len == self.last_frame_len {
       self.same_bad_len_counter += 1;
       // 当连续 30 帧检测到异常定长坏包时，主动熔断当前硬件编码器
       if self.same_bad_len_counter >= MAX_BAD_COUNTER {
           log::info!(
               "{} times encoding len is {}, switch encoder",
               self.same_bad_len_counter,
               self.last_frame_len
           );
           // 抛出切换异常，触发上层状态机平滑降级
           bail!(crate::codec::ENCODE_NEED_SWITCH);
       }
   } else {
       self.same_bad_len_counter = 0;
   }
   self.last_frame_len = this_frame_len;

当触发 ``ENCODE_NEED_SWITCH`` 或硬件初始化失败时，RustDesk 的容灾降级阶梯为：

$$	ext{VRamEncoder (显存直通)} \xrightarrow{	ext{降级}} 	ext{HwRamEncoder (内存硬件编码)} \xrightarrow{	ext{降级}} 	ext{Vpx/Aom (纯 CPU 软件编码)}$$

整个切换过程在后台异步完成，上层传输通道无需断开 TCP/UDP 连接，保证了远程控制在极端硬件环境下的坚韧可用性。

***
小结与下章导读
***

本章全面解构了 RustDesk 跨厂商硬件加速编解码架构的设计与实现：
* 阐明了专用 ASIC 媒体引擎（NVENC, QSV, AMF, VideoToolbox, MediaCodec）的硬件物理模型。
* 剖析了统一硬件抽象层 ``hwcodec`` 的运行时能力探测、LUID 多显卡拓扑对齐以及 VRam/Ram 双轨流水线。
* 揭示了无 B 帧超低延迟调度、动态码率无损热重配以及针对厂商驱动缺陷的坏帧熔断与自动降级容灾模型。

在下一节中，我们将深入多媒体管道的自适应控制核心：
* **《02.04 动态码率自适应、丢包补偿与帧率平滑调度》**：解析远程桌面如何结合网络往返时延（RTT）、丢包率反馈（GCC / BBR 算法思想）动态调节编码码率、执行按需 I 帧请求以及渲染端平滑去抖动。
