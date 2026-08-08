第109章：Android AudioRecord, AudioTrack, AudioFlinger, Audio HAL, Driver
========================================================================

核心知识点
----------

* ``AudioRecord`` 是 App 侧录音入口，``AudioTrack`` 是 App 侧播放出口；它们不直接控制硬件。
* AudioFlinger 负责音频数据面：record thread、playback thread、track buffer、mixing、resampling、effect chain 与 HAL stream 读写。
* AudioPolicyManager 负责策略面：根据 AudioAttributes、audio source、设备状态、通话状态和系统配置选择 route、volume 与 device。
* 录音路径需要同时满足 ``RECORD_AUDIO`` 权限、source 语义、前后台限制、实际 input device 和 buffer 消费节奏。
* 播放路径依赖 usage / content type、focus、buffer 供给和 output device；App 写入过慢会造成 underrun。
* Fast track / low-latency path 依赖设备能力、格式匹配、buffer、线程优先级和当前 route；请求低延迟不等于一定进入 fast path。
* Audio HAL 是 Framework / AudioFlinger 与 vendor driver、DSP、codec hardware 之间的稳定边界。

关键路径
--------

录音：

``Microphone → Driver → Audio HAL input stream → AudioFlinger RecordThread → AudioRecord shared buffer → App``

播放：

``App → AudioTrack buffer → AudioFlinger MixerThread / FastMixer → Audio HAL output stream → Driver → Speaker / Headset / Bluetooth``

策略链：

``AudioAttributes / Source → AudioPolicyManager → Device / Route / Volume → AudioFlinger thread``

排查顺序：

``App intent / permission → AudioPolicy route → AudioFlinger track/thread → HAL stream → Driver / DSP / Hardware``

概念辨析
--------

* **AudioFlinger vs AudioPolicyManager**：前者处理数据和线程，后者处理设备与策略。
* **Audio source vs microphone device**：source 表示采集用途；真实麦克风由 policy 选择。
* **AudioTrack usage vs stream type**：现代策略优先使用 AudioAttributes usage；stream type 更多承担兼容语义。
* **FastMixer vs normal mixer**：FastMixer 追求短周期和低延迟；normal mixer 支持更通用的混音、转换与效果。
* **HAL vs driver**：HAL 向系统暴露音频流接口；driver 负责 DMA、codec、硬件寄存器和内核设备。

本章结论
--------

Android 音频栈要同时按“数据面”和“策略面”阅读。``AudioRecord / AudioTrack`` 只是 App 边界；真正的跨 App 混音、录音仲裁和路由由 AudioFlinger 与 AudioPolicyManager 完成，再通过 HAL、driver 落到硬件。