第003章：Hardware Capability Mediation and System Control
=========================================================

核心知识点
----------

* 移动 OS 不把硬件设备直接交给 App，而是把硬件能力转换成可授权、可调度、可审计、可撤销、可降级的 system capability。
* 必须区分四个层次：硬件真实能力、系统开放能力、Framework API 能力表面、当前用户授权状态。任何一层收缩都会改变 App 最终结果。
* Capability-based access 的关键是 App 只声明意图，例如拍照、录音、定位、蓝牙扫描；system service 决定使用哪个设备、何时执行、是否允许和如何回收。
* Device-level access 会扩大故障、安全和兼容性风险。第三方 App 通常不能直接打开底层设备并控制寄存器、DMA 或 firmware protocol。
* 相机、麦克风等资源接近独占；定位、传感器等更适合共享或聚合；蓝牙扫描、音频路由属于条件共享。资源形态决定仲裁策略。
* System service 会维护 client/session/token，并基于前后台状态、窗口焦点、系统角色、通话状态、权限、全局隐私开关和设备能力决定 allow、queue、share、preempt 或 deny。
* 权限检查不是只发生一次。Framework 可做前置检查，service/daemon 必须在可信边界重新检查 caller identity；kernel/driver 仍负责底层访问保护。
* 权限记录回答“调用者是否获得资格”，资源仲裁回答“当前时刻是否能获得资源”。有权限仍可能因为占用、后台限制、高温或设备故障而失败。
* App 崩溃与硬件故障必须被隔离。App 退出后系统应通过 IPC death/session cleanup 回收资源；driver 或 firmware 出错时应向上层传播错误而不是让 App 持有失控设备状态。
* Power 和 thermal policy 会参与硬件 mediation。持续位置、相机、麦克风、蓝牙、网络等能力可能被降低采样率、缩短执行时间、限制后台使用或直接停止。
* Sensor privacy 把 camera、microphone、location、Bluetooth 等能力连接到用户授权、状态指示器、全局开关、权限撤销和审计入口。
* Vendor boundary 和稳定接口决定 OTA 后硬件能力是否还能工作。HAL/driver ABI、firmware 版本和 vendor implementation 都属于长期兼容性的一部分。

关键路径
--------

硬件能力开放：

::

   physical device capability
   → driver / firmware support
   → HAL / driver framework capability description
   → system service policy
   → framework API surface
   → app-visible capability

一次访问请求：

::

   app request
   → identify caller
   → check permission / entitlement
   → check lifecycle and global privacy state
   → arbitrate resource ownership
   → apply power / thermal constraints
   → open hardware path or reject

权限撤销与资源回收：

::

   user revokes permission / app loses eligibility
   → policy state changes
   → service invalidates client session
   → callbacks / errors delivered
   → HAL and driver release device
   → app updates user-visible state

概念辨析
--------

* **硬件能力与系统能力**：硬件支持只是物理事实，系统能力是经过平台策略裁剪后的可用集合。
* **Permission 与 arbitration**：Permission 判断调用资格，arbitration 判断当前资源归谁使用。
* **独占与共享资源**：相机常需要强仲裁，定位可由系统聚合多个订阅；不同能力不能套用同一种并发模型。
* **Framework check 与 trusted check**：客户端检查用于体验和快速失败，真正安全边界必须在可信 service/daemon/kernel 侧执行。
* **App failure 与 device failure**：App 崩溃应局部回收会话；底层硬件故障应通过分层错误路径传播，不能混为同一故障域。

本章结论
--------

Hardware mediation 是移动 OS 把物理设备转成平台能力的核心机制。系统通过身份、权限、生命周期、资源所有权、隐私、功耗、温控和 vendor boundary 共同裁决每次硬件访问；App 获得的是随时可能被拒绝、抢占、降级或撤销的能力会话，而不是设备本身。