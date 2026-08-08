第108章：Capture, Playback, Mixing, Resampling, Latency
======================================================

核心知识点
----------

* Audio Capture 是输入路径，Playback 是输出路径；两者方向相反，但都依赖设备、HAL、系统音频服务、buffer 和调度线程。
* PCM frame 是同一时间点所有 channel 的 sample 集合；``duration = frame_count / sample_rate``，buffer 时间长度比单纯字节数更重要。
* 系统 mixer 负责把允许同时播放的多个流按音量、格式和时间线合成；是否允许混音由焦点或 audio session 等策略先决定。
* Resampling 解决 App、mixer、HAL、外设之间 sample rate 不一致的问题；声道、bit depth、float / integer 转换也属于格式适配。
* Ring buffer 用来吸收生产者和消费者节奏差异。buffer 越大越稳定但延迟越高，越小延迟越低但更容易发生 xrun。
* Underrun 是播放端来不及提供数据；overrun 是采集端来不及消费数据。两者本质都是 deadline 与 buffer 管理失败。
* 端到端音频延迟由 App、Framework、mixer、HAL、driver、硬件以及 Bluetooth / USB 等外设阶段叠加形成。

关键路径
--------

采集：

``Microphone → ADC / Codec → Driver / HAL → Audio Service → App Capture Buffer``

播放：

``App Playback Buffer → Audio Service → Mixer / Resampler → HAL / Driver → DAC or Wireless Codec → Output Device``

实时双向场景：

``Input latency → App processing → Output latency = round-trip latency``

常用换算：

``buffer_duration_ms = frame_count / sample_rate × 1000``

概念辨析
--------

* **Sample vs frame**：sample 是单声道某一时刻的值；frame 是同一时刻所有声道的 sample 集合。
* **Mixing vs routing**：mixing 决定多条流怎样合成；routing 决定最终送到哪个设备。
* **Resampling vs encoding**：resampling 改变采样率；Bluetooth codec 或 AAC/Opus encoding 改变数据表示和压缩方式。
* **Latency vs stability**：增大 buffer 往往提高抗抖动能力，同时增加排队时间。
* **Underrun vs overrun**：前者是消费者缺数据，后者是生产者数据来不及被消费。

本章结论
--------

分析音频数据流时先确定方向，再固定 PCM 格式和 buffer 周期，然后检查 mixer、resampler、HAL、driver 与实际 route。音频连续性不是“平均速度够快”即可，而是每个 callback 周期都必须按时完成。