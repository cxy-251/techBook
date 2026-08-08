第107章：Audio Hardware, Codec, Microphone, Speaker, Audio Route
===============================================================

核心知识点
----------

* 手机音频硬件要按输入端点、输出端点和复合端点理解：麦克风负责采集，speaker / receiver / headset 负责播放，Bluetooth / USB 可能同时承担输入与输出。
* 音频硬件 codec 在本章指 ADC / DAC、模拟增益、偏置、功放与部分低功耗处理，不等同于 AAC、Opus 这类媒体编码格式。
* PCM 是系统音频数据面的核心表示，sample rate、channel、bit depth 决定数据率、格式兼容与处理成本。
* App 不能直接控制麦克风偏置、功放或 codec 寄存器；Framework、系统音频服务、HAL、driver 与硬件共同完成资源控制。
* 音频 route 是系统策略结果。内置扬声器、听筒、有线耳机、Bluetooth、USB、AirPlay / Cast 的格式、延迟、功耗和可用能力不同。
* 输入和输出必须分开判断：播放成功不代表采集正常，采集成功也不代表当前输出 route 正确。
* 麦克风访问还受权限、前后台状态和隐私指示约束；播放路径还受焦点、音量与设备策略约束。

关键路径
--------

录音主路径：

``Air → Microphone → Analog Signal → ADC / Codec → PCM → Driver / DMA → Audio HAL → System Audio Service → Framework → App Buffer``

播放主路径：

``App PCM → Framework → System Audio Service / Mixer → Audio HAL → Driver / DMA → DAC / Codec → Amplifier → Speaker / Receiver``

Bluetooth / USB 会把部分 codec、时钟和 buffer 环节移动到外部设备，但系统仍要完成格式、路由和生命周期协调。

概念辨析
--------

* **Audio hardware codec vs media codec**：前者负责模拟/数字音频转换和硬件控制；后者负责 AAC、Opus 等压缩编码与解码。
* **Speaker vs receiver**：speaker 面向外放；receiver 面向贴耳通话，音量曲线和使用场景不同。
* **Audio source vs input device**：source 是 App 表达的采集语义；input device 是系统策略最终选择的真实端点。
* **Route request vs route decision**：App 可表达偏好，系统保留最终路由仲裁权。
* **PCM format vs hardware capability**：App 请求的采样率和声道不保证硬件原生支持，系统可能插入重采样或格式转换。

本章结论
--------

移动音频硬件应沿 ``App → Framework → Audio Service / Policy → HAL → Driver → Codec / Device`` 阅读。排查时先分清输入或输出，再确认实际 route 与 PCM 格式，最后进入 HAL、driver 和硬件；不要把 App API、系统策略和真实设备控制混成一层。