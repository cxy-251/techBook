第038章：Capability Interface Instead of Raw Device Access
==========================================================

核心知识点
----------

* 移动平台把相机、位置、蓝牙、音频、网络等真实设备包装成 Capability Interface，让 App 请求的是“能力”，而不是底层设备节点、寄存器或驱动命令。
* Raw Device Access 会同时扩大安全、稳定性、并发、兼容和隐私风险：App 既要理解设备细节，又可能绕过系统权限、资源仲裁和生命周期管理。
* Capability Interface 的核心结构是 ``App intent → Framework API → System Service → Policy → HAL / Daemon → Driver → Device``。
* App 看到 session、request、callback、result 和 error；系统持有真实 device ownership，并决定独占、共享、抢占、排队或拒绝。
* Device-specific control 应留在 HAL、daemon、driver 和 firmware 中；platform-level API 只承诺稳定、可查询、可降级的能力语义。
* 能力接口并不假设所有设备能力相同。App 仍应通过 capability query、feature flag、format list、profile、精度和错误码判断实际可用范围。
* Permission、policy、power 是一次能力访问的三个共同闸门：权限决定是否有资格，策略决定当前状态是否允许，电源/温控决定是否需要降级或延后。
* Android 常把 runtime permission、AppOps、前后台状态、系统设置、电池策略和 HAL capability 叠加；Apple 则通过 authorization、entitlement、TCC、background mode 和系统服务策略实现相同目标。
* Capability Interface 还能吸收多厂商差异。相同 Camera/Location/Audio API 背后可以对应不同 sensor、ISP、modem、codec 与 firmware，而 App 不必绑定具体硬件实现。
* 能力接口也是审计入口：系统可以记录哪个 App 在什么状态下请求了哪项敏感能力，并映射到权限提示、隐私指示器和撤销行为。

关键路径
--------

拍摄页能力请求：

::

   App requests camera / microphone / location
   → framework capability API
   → system service identifies caller
   → permission and policy checks
   → resource arbitration
   → HAL / daemon adapts device
   → driver operates hardware
   → result or error returns through same capability boundary

统一决策：

::

   caller identity
   + permission state
   + foreground/background state
   + user setting
   + device availability
   + power / thermal state
   → allow / deny / degrade / defer

厂商差异吸收：

::

   vendor-specific sensor / ISP / codec / modem
   → driver and firmware
   → HAL capability declaration
   → framework stable API
   → App capability query

概念辨析
--------

* **Device 与 capability**：Device 是真实硬件资源，capability 是系统允许 App 使用的受控语义。
* **Raw access 与 high-level API**：前者把设备细节和攻击面暴露给调用者；后者让系统保留资源所有权和策略控制。
* **Permission 与 capability availability**：权限通过只代表调用者有资格，请求仍可能因设备占用、后台限制、温控或硬件能力不足失败。
* **Uniform API 与 identical hardware**：统一 API 只统一调用合同，不意味着所有设备拥有完全相同的性能和特性。
* **Capability failure 与 driver failure**：能力接口返回失败可能来自策略层，也可能来自 HAL/driver/hardware，必须沿调用链继续定位。

本章结论
--------

移动平台稳定性的关键不是让 App 更接近硬件，而是让 App 面向能力、让系统持有设备。权限、生命周期、电源、并发、审计和厂商差异都可以在 capability boundary 内统一收束，从而让公开 API 长期稳定而底层硬件持续演进。