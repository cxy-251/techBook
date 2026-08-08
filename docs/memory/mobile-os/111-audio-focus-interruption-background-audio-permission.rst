第111章：Audio Focus, Interruption, Background Audio, Permission
================================================================

核心知识点
----------

* 多 App 音频的核心不是“谁先播放”，而是系统根据用途、焦点、通话状态、后台资格、权限和用户意图做统一仲裁。
* Android Audio Focus 用 gain / transient / may-duck / loss 等状态表达播放关系；Apple 通过 ``AVAudioSession`` category、mode、option 和 interruption 表达同类策略。
* Ducking、pausing、mixing、exclusive 是四种不同策略，选择依据是内容语义和用户预期，不是单纯音量大小。
* Interruption 表示系统因电话、闹钟、语音助手或更高优先级音频改变当前 App 会话状态；App 必须保存状态并谨慎恢复。
* 后台音频需要平台认可的长期执行资格：Android 依赖 foreground service / media session 等机制，Apple 依赖后台音频能力与合适的 session category。
* 麦克风录音属于隐私敏感能力，必须同时满足运行时权限 / TCC、前后台限制、隐私开关和当前 route。
* Bluetooth、蜂窝通话、VoIP 与媒体播放会竞争 profile、route 和系统策略；“有设备”不等于“当前用途可使用该设备”。

关键路径
--------

播放焦点：

``App audio intent → Framework focus / session request → System Audio Policy → Duck / Pause / Mix / Exclusive → Player state``

中断：

``Phone / Alarm / Other High-Priority Audio → System Service → Focus Loss / Interruption Began → Save State → Interruption End / Gain → Resume only if user intent still allows``

录音：

``Microphone Permission / TCC → Foreground & Privacy Policy → Audio Session / Source → Route → Capture Stream``

后台播放：

``User-visible playback → Approved background capability → Media control / session state → System keeps audio path eligible``

概念辨析
--------

* **Audio Focus vs route**：focus 决定多 App 播放关系；route 决定声音实际进入哪个设备。
* **Ducking vs pausing**：duck 保持播放但降低音量；pause 暂停时间线，更适合 spoken audio 冲突。
* **Interruption vs permanent stop**：interruption 通常是系统临时改变状态；是否恢复还要结合用户在中断期间的动作。
* **Background capability vs process immortality**：后台音频只允许与用户可感知音频任务相关的持续执行，并不保证进程永远存活。
* **Microphone permission vs audio session**：权限解决“能否采集”，session/source/route 决定“如何采集”。

本章结论
--------

移动音频策略的稳定模型是 ``App 声明意图 → 系统仲裁 → App 响应状态变化``。播放、录音、后台执行和设备路由都不是 App 单方面决定；正确实现必须把焦点、中断、权限、生命周期和用户意图放在同一状态机中。