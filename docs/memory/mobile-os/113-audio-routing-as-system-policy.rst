第113章：Audio Routing as System Policy
=======================================

核心知识点
----------

* Audio routing 是系统把输入/输出音频流连接到具体设备的策略过程，不是 App 直接切换硬件开关。
* 路由决策同时考虑设备状态、音频用途、用户选择、权限、通话状态、焦点、前后台状态、功耗和延迟目标。
* Speaker、receiver、wired headset、Bluetooth、USB 的能力不同；Bluetooth 还要区分媒体与通话 profile，USB 还受设备描述和采样能力约束。
* “设备存在”不等于“当前用途可用”。通话需要双向语音和回声控制，媒体更重视音质，闹钟更重视可靠可听，录音还要满足隐私策略。
* Route change 是系统状态变化，不是单纯通知。App 应重新读取实际设备、采样率、声道、buffer 与 session / policy 状态。
* Android 通过 AudioAttributes、AudioManager、Audio Policy、AudioFlinger 和 HAL 完成路由；Apple 通过 AVAudioSession category、mode、option 与系统音频策略完成同类仲裁。
* 路由策略直接影响延迟、音质、功耗和隐私，例如从 A2DP 切到通话 profile 往往会改变编码、带宽与延迟特征。

关键路径
--------

通用路由闭环：

``App Audio Intent → Framework API → System Audio Service / Policy → Device State + Usage + User Choice + Call/Focus + Permission → Route Decision → HAL / Driver / Hardware``

状态反馈：

``Route Change → Framework Notification → App Re-read Route / Format → Rebuild Audio Graph or Stream → Update UI / Playback State``

Android：

``AudioAttributes / AudioManager → AudioPolicyManager → AudioFlinger → Audio HAL → Device``

Apple：

``AVAudioSession category / mode / option → System Policy → Current Route → Core Audio / Hardware``

概念辨析
--------

* **Routing vs mixing**：routing 决定去哪个设备；mixing 决定多条流怎样合成。
* **Preferred device vs actual device**：App 可以表达偏好，实际设备由系统策略最终确认。
* **Media route vs communication route**：媒体偏重音质和连续性；通信偏重双向、低延迟、回声处理和隐私。
* **Route change vs interruption**：route change 是设备路径变化；interruption 是会话被更高优先级事件暂停或改变，两者可能同时发生。
* **Bluetooth device vs Bluetooth profile**：同一耳机在媒体和通话场景可使用不同 profile，音质与延迟随之改变。

本章结论
--------

Audio routing 是系统级资源仲裁。正确模型不是“App 选择设备”，而是 ``App 声明用途和偏好 → 系统结合全局状态决定 route → App 响应 route change``。任何依赖固定设备、固定采样率或固定延迟的实现都必须为路由变化设计重配置路径。