======================================================================
01.03 低延迟音频捕获、混音与回放子系统
======================================================================

.. note:: 前置背景与上下文承接
   在前两章中，我们先后剖析了跨平台屏幕画面的抓取（《01.01 跨平台屏幕像素捕获底层原语与抓屏引擎实现》）以及键鼠事件的注入与状态同步（《01.02 跨平台输入事件注入引擎与多端同步实现》）。至此，画面的“看”与输入的“控”已经建立了底层基石。然而，完整的沉浸式远程体验离不开**声画同步的低延迟音频流**。受控端操作系统的系统声音（扬声器播放流）与麦克风输入如何在无虚拟声卡驱动侵入的前提下完成环回采集？多声道与异构采样率如何完成实时重采样并送入低延迟 Opus 编码器？本章将深入 RustDesk 的 ``src/server/audio_service.rs``，系统解剖其音频管道的物理模型与工程实现。

***
操作系统音频拓扑与环回采集（Loopback）物理模型
***

音频在现代操作系统中的处理路径与视频捕获存在本质差异。视频通常可以直接从桌面合成器抓取最终合成纹理，而音频子系统通常将“输入（麦克风/Line-In）”与“输出（扬声器/耳机）”严格物理隔离。远程桌面所期望采集的“系统声音”，本质上属于**正在向音频硬件渲染端点（Render Endpoint）写入的音频输出流**，这一过程被称为**环回录制（Loopback Recording）**。

.. list-table:: 三大操作系统音频架构与环回采集原语对比
   :widths: 18 25 32 25
   :header-rows: 1

   * - 操作系统
     - 音频核心架构
     - 环回采集（Loopback）实现路径
     - 延迟与驱动依赖
   * - **Windows**
     - Windows Audio Session API (WASAPI)
     - ``IAudioClient`` 激活 ``AUDCLNT_STREAMFLAGS_LOOPBACK``
     - 硬件抽象层直接支持，延迟低至 10ms~20ms，零第三方驱动依赖
   * - **macOS**
     - CoreAudio / ScreenCaptureKit
     - macOS 13+ 基于 ScreenCaptureKit 捕获；旧版依赖 BlackHole / Soundflower
     - ScreenCaptureKit 支持无内核扩展（KEXT-less）捕获系统伴音
   * - **Linux**
     - PulseAudio / PipeWire / ALSA
     - 监听 Sink 的监视源（``.monitor`` source）或 PipeWire 虚拟节点
     - 通过独立 IPC 服务进程（``_pa``）建立低延迟环回流

---
Windows 平台：WASAPI 硬件渲染端点环回捕获
---

在 Windows Vista 及更高版本中，Core Audio API 提供了基于 WASAPI（Windows Audio Session API）的纯硬件环回能力。RustDesk 借助 ``cpal``（Cross-Platform Audio Library）抽象层，定位 Windows 的默认输出设备（Default Render Endpoint）：

.. code-block:: rust
   :caption: Windows 端获取默认输出设备并开启环回（src/server/audio_service.rs）

   #[cfg(windows)]
   fn get_device() -> ResultType<(Device, SupportedStreamConfig)> {
       let audio_input = super::get_audio_input();
       if !audio_input.is_empty() {
           return get_audio_input(&audio_input);
       }
       // 定位默认音频渲染输出设备（扬声器/耳机端点）
       let device = HOST
           .default_output_device()
           .with_context(|| "Failed to get default output device for loopback")?;
       log::info!(
           "Default output device: {}",
           device.name().unwrap_or("".to_owned())
       );
       let format = device
           .default_output_config()
           .map_err(|e| anyhow!(e))
           .with_context(|| "Failed to get default output format")?;
       log::info!("Default output format: {:?}", format);
       Ok((device, format))
   }

WASAPI 环回的工作原理在于：音频引擎（Audio Engine）在将混合后的 PCM 缓冲区提交给物理 DAC（数模转换器）硬件 DMA 之前，复制一份未衰减的数字 PCM 样本流推入客户端的环回输入缓冲区。这意味着即使受控端物理音箱被静音（若在驱动层实现），数字音频流依然能够无损捕获。

---
macOS 平台：ScreenCaptureKit 现代伴音捕获与 CoreAudio 演进
---

历史上，macOS CoreAudio 出于安全与隐私考量，严禁非特权用户态应用读取其他进程向 Default Output Device 写入的音频数据。以往的远程控制软件必须强制用户安装内核扩展（KEXT）或虚拟音频驱动（如 Soundflower、BlackHole）。

从 macOS 13 (Ventura) 开始，Apple 在 **ScreenCaptureKit** 中引入了原生系统音频流捕获接口。RustDesk 通过特性开关与 cpal 后端实现了自适应接入：

.. code-block:: rust
   :caption: macOS ScreenCaptureKit 音频宿主探测

   #[inline]
   #[cfg(feature = "screencapturekit")]
   pub fn is_screen_capture_kit_available() -> bool {
       cpal::available_hosts()
           .iter()
           .any(|host| *host == cpal::HostId::ScreenCaptureKit)
   }

当 ``ScreenCaptureKit`` 可用时，RustDesk 直接通过系统服务在用户空间捕获完整的桌面伴音，彻底规避了外部虚拟声卡配置的复杂性；而在旧版系统或指定特定麦克风输入时，则平滑降级至标准 CoreAudio 输入端点。

---
Linux 平台：PulseAudio / PipeWire 独立 IPC 与零拷贝内存对齐
---

在 Linux 桌面体系中，音频服务通常由用户态守护进程（PulseAudio 或现代 PipeWire 的 ``pipewire-pulse`` 兼容层）统一管理。受控端的主机音频服务可能运行在独立的桌面会话或 root 服务中。

RustDesk 在 Linux 端通过独立的 IPC 套接字（``_pa``）与音频子进程通信，并实现了严格的 **4 字节内存对齐重构**：

.. code-block:: rust
   :caption: Linux PulseAudio 流读取与 IEEE 754 f32 零拷贝指针重解释

   #[cfg(any(target_os = "linux", target_os = "android"))]
   mod pa_impl {
       use super::*;

       /// 将原始字节流读取为 f32 切片需要保证 4 字节指针对齐。
       /// 仅在指针未对齐时执行小块内存重分配与拷贝；已对齐时实现零拷贝直通。
       fn align_to_32_if_needed(data: &[u8]) -> Option<hbb_common::mem::AlignedU8Vec> {
           if (data.as_ptr() as usize & 3) == 0 {
               return None;
           }
           let mut buf = hbb_common::mem::aligned_u8_vec(data.len(), 4);
           buf.extend_from_slice(data);
           Some(buf)
       }

       pub async fn run(sp: EmptyExtraFieldService) -> ResultType<()> {
           let mut stream = crate::ipc::connect(1000, "_pa").await?;
           let mut encoder = Encoder::new(crate::platform::PA_SAMPLE_RATE, Stereo, LowDelay)?;
           
           while sp.ok() && !RESTARTING.load(Ordering::SeqCst) {
               if let Ok(data) = stream.next_raw().await {
                   if data.len() != AUDIO_DATA_SIZE_U8 {
                       continue;
                   }
                   let data: Vec<u8> = data.into();
                   let aligned = align_to_32_if_needed(&data);
                   let bytes = aligned.as_deref().unwrap_or(&data[..]);
                   
                   // SAFETY: 已经校验 bytes 满足 4 字节内存对齐，安全将其重解释为 f32 PCM 样本
                   let samples = unsafe {
                       std::slice::from_raw_parts::<f32>(bytes.as_ptr() as _, bytes.len() / 4)
                   };
                   send_f32(samples, &mut encoder, &sp);
               }
           }
           Ok(())
       }
   }

---
音频管道规格化：重采样、声道重映射与样本归一化
---

声卡硬件可能工作在各种非标准的物理采样率（如 44.1kHz、96kHz、192kHz）和多声道配置（5.1 / 7.1 环绕声）下，而低延迟语音编码器 **Opus** 要求输入必须对齐到特定的采样频率。

1. 采样率阶梯对齐与重采样
~~~~~~~~~~~~~~~~~~~~~~~~

Opus 原生支持五种标准采样率：$8\,	ext{kHz}, 12\,	ext{kHz}, 16\,	ext{kHz}, 24\,	ext{kHz}, 48\,	ext{kHz}$。RustDesk 在采集初始化时根据硬件原生采样率执行向下阶梯匹配：

.. math::

   f_{	ext{target}} = \begin{cases}
   8000\,	ext{Hz} & f_{	ext{hw}} < 12000 \
   12000\,	ext{Hz} & 12000 \le f_{	ext{hw}} < 16000 \
   16000\,	ext{Hz} & 16000 \le f_{	ext{hw}} < 24000 \
   24000\,	ext{Hz} & 24000 \le f_{	ext{hw}} < 48000 \
   48000\,	ext{Hz} & f_{	ext{hw}} \ge 48000
   \end{cases}

当物理声卡输出 $44.1\,	ext{kHz}$ 时，管道会调用 ``audio_resample`` 插值重采样算法将其转换至 $48\,	ext{kHz}$。

2. 泛型样本归一化 (``dasp::sample::ToSample<f32>``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

硬件声卡可能以 8位无符号整数（``U8``）、16位有符号整数（``I16``）或 32位定点数（``I32``）交付缓冲区。RustDesk 在 ``build_input_stream`` 中通过 Rust 泛型约束与 ``dasp`` 库统一将任意格式映射为 IEEE 754 $[-1.0, 1.0]$ 区间内的 ``f32`` 标准浮点样本。

.. code-block:: rust
   :caption: 环形缓冲消费与声道矩阵重映射

   let frame_size = sample_rate_0 as usize / 100; // 10ms 帧时长基准
   let encode_len = frame_size * encode_channel as usize;
   let rechannel_len = encode_len * device_channel as usize / encode_channel as usize;

   let stream = device.build_input_stream(
       &stream_config,
       move |data: &[T], _: &InputCallbackInfo| {
           // 泛型类型归一化为 f32
           let buffer: Vec<f32> = data.iter().map(|s| T::to_sample(*s)).collect();
           let mut lock = INPUT_BUFFER.lock().unwrap();
           lock.extend(buffer);
           
           // 当环形队列累积满一个完整编码周期的样本时，弹出并分发
           while lock.len() >= rechannel_len {
               let frame: Vec<f32> = lock.drain(0..rechannel_len).collect();
               send(
                   frame,
                   sample_rate_0,
                   sample_rate,
                   device_channel,
                   encode_channel as _,
                   &mut encoder,
                   &sp,
               );
           }
       },
       err_fn,
       timeout,
   )?;

---
Opus 低延迟编码与静音门限（Noise/Silence Gate）
---

音频数据以 **10ms** 为基准分块（48kHz 双声道下为 480 个采样点，对应 960 个 ``f32`` 浮点数，即 ``AUDIO_DATA_SIZE_U8 = 3840`` 字节）。

1. Opus LowDelay 实时编码模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 选用 ``magnum_opus`` 编码库，初始化配置为 ``Application::LowDelay``。该模式专为实时双向音视频通信设计，关闭了前向冗余编码（FEC）引起的前瞻分析延迟（Lookahead Delay），将编码端自身延迟压缩至 5ms 以内。

2. 静音门限攻击时间控制（Noise Gate Attack Time）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在桌面没有播放任何声音的静默期，持续向网络发送全零的音频静音帧会浪费 CPU 与带宽资源。RustDesk 实现了带有攻击时间（Attack Time）状态机的静音门限控制：

.. code-block:: rust
   :caption: 静音门限过滤逻辑（src/server/audio_service.rs）

   const MAX_AUDIO_ZERO_COUNT: u16 = 800;
   static mut AUDIO_ZERO_COUNT: u16 = 0;

   fn send_f32(data: &[f32], encoder: &mut Encoder, sp: &GenericService) {
       // 检测当前帧是否包含有效非零振幅
       if data.iter().any(|x| *x != 0.0) {
           unsafe { AUDIO_ZERO_COUNT = 0; }
       } else {
           unsafe {
               // 当连续检测到静音帧超过门限值（MAX_AUDIO_ZERO_COUNT=800，约 3~8 秒）
               if AUDIO_ZERO_COUNT > MAX_AUDIO_ZERO_COUNT {
                   if AUDIO_ZERO_COUNT == MAX_AUDIO_ZERO_COUNT + 1 {
                       log::debug!("Audio Zero Gate Attack: 触发静音抑制，暂停发送");
                       AUDIO_ZERO_COUNT += 1;
                   }
                   return; // 抑制发送全零数据包
               }
               AUDIO_ZERO_COUNT += 1;
           }
       }

       // 正常编码并推入网络发送服务
       match encoder.encode_vec_float(data, data.len() * 6) {
           Ok(encoded_bytes) => {
               let mut msg_out = Message::new();
               msg_out.set_audio_frame(AudioFrame {
                   data: encoded_bytes.into(),
                   ..Default::default()
               });
               sp.send(msg_out);
           }
           Err(e) => {
               log::trace!("Opus encode error: {:?}", e);
           }
       }
   }

通过静音门限状态机，RustDesk 在声音停止后维持数秒的平滑过渡，随后彻底停止网络传输；一旦受控端有任何系统提示音或媒体播放，首个非零样本会瞬间将 ``AUDIO_ZERO_COUNT`` 清零，以零延迟立刻恢复音频推流。

***
小结与下章导读
***

本章系统解析了 RustDesk 音频子系统的端到端流转机制：
* 剖析了 Windows WASAPI 硬件渲染端点环回、macOS ScreenCaptureKit 伴音捕获以及 Linux PulseAudio/PipeWire 独立 IPC 进程的实现。
* 拆解了音频采样率对齐、声道矩阵重映射与 IEEE 754 样本归一化流水线。
* 揭示了 Opus LowDelay 编码参数选择与基于攻击时间的静音门限带宽优化策略。

在下一节中，我们将深入受控端显示扩展与系统级安全遮蔽技术：
* **《01.04 IddCx 虚拟显示驱动与隐私屏黑屏机制》**：解析 Windows 间接显示驱动（Indirect Display Driver, IddCx）、无头服务器（Headless）虚拟分辨率注入，以及远程控制时的物理屏幕隐私黑屏（Privacy Mode）底层实现。
