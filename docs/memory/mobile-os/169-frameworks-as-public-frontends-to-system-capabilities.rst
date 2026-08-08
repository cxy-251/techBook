第169章：Frameworks as Public Frontends to System Capabilities
==============================================================

核心知识点
----------

* Apple framework 是 App 接触系统能力的稳定公开表面：开发者依赖对象、方法、delegate、completion、error 和 authorization state，而底层资源由系统服务持有。
* Foundation / Core Foundation 提供对象、时间、URL、文件、RunLoop、通知、集合等基础语义，是多个上层能力 framework 的公共胶水。
* AVFoundation、Core Media、Core Audio 分别承担高层媒体会话、时间/sample buffer 数据模型和低层音频能力入口；App 不直接拥有 camera、microphone、codec 或 audio route。
* Core Location、Core Bluetooth、Core NFC 把定位、无线与近场能力抽象成 manager/session/state/delegate；系统开关、授权、后台状态与功耗策略共同决定结果。
* Core Animation 与 Metal 把 view/layer 变化和 GPU 工作送入系统显示链；App 只负责可提交状态和命令，跨窗口合成与最终 present 属于系统边界。
* Security、Keychain、LocalAuthentication 把秘密存储、证书/密钥和本机认证包装成受身份与策略控制的接口，并可进一步连接 Secure Enclave。
* Public API 与 private architecture 之间应保持证据边界：API 行为可依赖，daemon 名称、内部消息格式和硬件调度细节不可当成稳定契约。

关键路径
--------

* 通用路径：``App behavior → Framework API → caller identity / authorization → system service / daemon → XNU / driver / hardware → callback / error``。
* 媒体路径：``AVFoundation → capture/playback session → system media service → camera/audio/codec → sample buffer / route / frame``。
* 设备能力路径：``Core Location / Bluetooth / NFC → authorization + state → daemon → radio/sensor/controller → delegate``。
* 安全路径：``Security / LocalAuthentication → access group / policy → security service → Keychain / Secure Enclave → status``。
* 图形路径：``UIKit / CALayer / Metal → transaction / command buffer → compositor / display server → display``。
* 排查 framework API 时先确认 API 前置条件与公开状态，再看授权和生命周期，随后才推断 daemon、driver 或硬件问题。

概念辨析
--------

* ``Framework`` 不是一个单纯函数库；对系统能力而言，它通常是 App 侧 frontend，后端由独立服务和硬件资源承担。
* ``Foundation`` 提供基础语义，不等于某个硬件 service；它常承载回调、文件、时间和事件循环等跨 framework 公共能力。
* ``Core Media sample`` 是媒体数据表达；``AVFoundation session`` 是资源与流程控制，两者职责不同。
* ``Core Animation`` 主要管理 layer、transaction 和合成语义；``Metal`` 提供显式 GPU 命令接口，二者可以在同一显示链中协作。
* ``Keychain`` 是系统秘密存储服务；``Secure Enclave`` 是硬件隔离安全域，Keychain item 不一定都由 Secure Enclave 保存。

本章结论
--------

Apple 平台的公开架构应优先从 framework 阅读。先识别 App 调用了哪个 public framework，再判断该能力的授权、状态与错误模型，最后沿 system service、XNU、driver 和 hardware 追踪责任。这样既能解释系统能力如何开放给 App，也能避免把不可验证的私有实现细节误当成平台契约。