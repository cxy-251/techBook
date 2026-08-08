第166章：Apple Full Stack Capability Path
=========================================

核心知识点
----------

* Apple 平台能力访问的稳定主线是 ``App → Public Framework → XPC / Mach Service → System Daemon / Policy → XNU → IOKit / DriverKit → Hardware``，结果再沿回调、状态或错误返回 App。
* App 获得的不是硬件所有权，而是被 ``code signing + entitlement + sandbox + TCC + lifecycle + system policy`` 共同过滤后的调用资格。
* Bundle ID、Team ID、签名、provisioning profile 与 entitlement 共同建立调用者身份；系统服务据此判断受控能力是否可用。
* Framework 是稳定公开入口，例如 Core Location、AVFoundation、Core Bluetooth、Security；其内部服务和硬件路径可以演进，而 public API 维持主要语义契约。
* XPC / daemon 层持有跨 App 全局状态，承担权限检查、资源仲裁、会话管理、后台策略、功耗策略与错误恢复。
* XNU 提供 task/thread、VM、Mach IPC、BSD file/network、security 与驱动基础；IOKit / DriverKit 组织设备服务和受控驱动访问。
* Apple 私有 daemon、firmware、baseband、ISP 和部分 driver 实现不是稳定公开事实；分析时应把公开行为与内部推断分开。

关键路径
--------

* 定位请求的最小路径：``App → Core Location → IPC / Location Service → authorization & policy → XNU / driver → GNSS / Wi-Fi / Cellular / Sensor → callback``。
* 相机、蓝牙、Keychain 等能力虽然入口不同，但都遵循“App 表达意图、系统服务持有状态、底层能力由系统代理”的模型。
* 请求失败时按顺序检查：App 配置与用途声明 → entitlement / sandbox → 用户授权 → 生命周期与后台状态 → system service 状态 → hardware availability。
* 返回路径同样重要：hardware result / error → daemon → framework semantic object → delegate / completion → App UI；只追请求方向会漏掉 callback、降级与错误翻译。
* 调试 Apple 平台时优先使用公开证据：authorization state、framework error、Console、Instruments、MetricKit、sysdiagnose、crash / hang report。

概念辨析
--------

* ``Entitlement`` 表示平台授予的受控能力资格；``TCC permission`` 表示用户对隐私资源的授权，两者不能互相替代。
* ``Sandbox`` 限制进程可直接访问的资源；``System Service`` 则在沙箱外代理敏感能力，两者共同构成受控开放。
* ``Framework`` 是 App 可依赖的稳定前端；``Daemon`` 是系统能力后端，不应把 framework 对象误认为硬件对象。
* ``XNU`` 是底层操作系统内核；``完整 iOS / iPadOS 平台`` 还包含闭源 framework、daemon、隐私策略、App Store 与硬件集成。
* ``Public API 可观察事实`` 与 ``private architecture 推断`` 必须分开表达，后者不能被写成固定实现承诺。

本章结论
--------

Apple Full Stack 的核心不是“App 如何直接操作硬件”，而是“系统如何把硬件能力包装成带身份、权限、资源仲裁和生命周期的受控服务”。分析任何 Apple 能力时，都应从 public framework 出发，沿 IPC、service、policy、XNU、driver 到 hardware 定位责任，再沿返回路径验证回调、错误和降级结果。