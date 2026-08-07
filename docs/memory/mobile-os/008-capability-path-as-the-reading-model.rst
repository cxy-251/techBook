第008章：Capability Path as the Reading Model
==============================================

核心知识点
----------

* Capability Path 是阅读移动 OS 的主模型：先追踪一次 App 意图如何变成受控系统能力，再把 Android/Apple 的平台名词放回路径角色。
* 一条完整路径通常是 ``App → Framework API → IPC → System Service / Daemon → Policy → HAL / Driver → Kernel → Hardware → Return Path``。
* App 拥有业务意图，Framework 拥有公开 API 形状，system service/daemon 拥有资源状态与策略执行权，driver/kernel 拥有设备控制路径。
* 读源码或文档时先问五个问题：调用者是谁、公开入口在哪里、跨进程边界在哪里、能力所有者是谁、失败如何返回。
* Framework manager 往往只是客户端代理。真正的权限检查、资源仲裁和设备状态判断常发生在另一个进程的 service method 中。
* Caller identity 是系统能力判断的基础。UID、package/bundle identity、pid、signature、user、attribution、entitlement 等信息用于 permission、audit、foreground state 和 policy 决策。
* System Service 到 Hardware Boundary 的路径要继续追踪 HAL/driver framework、buffer、firmware、device state，而不能在 service 调用成功后就认为硬件路径完成。
* Return Path 必须和请求路径同等重视。错误可能被逐层转换成 exception、callback、delegate、status、disconnect 或 user-visible UI。
* Capability Path 可以反向用于故障诊断：从用户现象倒推 Framework 状态、service decision、policy input、HAL/driver result 和 kernel/hardware evidence。
* 相机、音频、定位、蓝牙、网络、通知、后台任务都可以使用同一阅读框架，只是中间能力所有者与硬件边界不同。
* Android 读取时常沿 Framework manager → Binder/AIDL proxy → service → permission/AppOps → HAL/native service → driver；Apple 读取时以 public Framework → IPC/daemon → entitlement/sandbox/privacy → XNU/driver boundary 为主。
* Apple 私有 daemon 和内部 method 不应当作稳定必背知识；应记住公开能力角色和边界，具体实现以当前公开证据为准。
* Capability Path 的价值是把大量名词转换为“输入—责任主体—策略—输出”，使跨版本、跨平台分析保持稳定。

关键路径
--------

正向阅读：

::

   user / app intent
   → public API
   → client proxy
   → IPC transaction
   → system capability owner
   → identity + permission + lifecycle checks
   → resource arbitration
   → HAL / driver / kernel / hardware
   → result callback

反向诊断：

::

   user-visible symptom
   → framework error / callback
   → service decision
   → permission / policy / ownership state
   → HAL / daemon status
   → driver / kernel evidence
   → hardware state

源码定位：

::

   manager / framework class
   → service interface handle
   → IPC definition / proxy
   → service implementation
   → permission and caller-identity checks
   → lower-layer call
   → error translation

概念辨析
--------

* **平台名词与责任角色**：Binder、XPC、HAL、entitlement 等名词只有放入请求路径后才有完整意义。
* **Framework API 与 capability owner**：API 是客户端入口，真正持有共享资源状态的通常是系统服务或 daemon。
* **请求路径与调用栈**：Capability Path 是稳定架构责任链，不要求每次都等同某个版本的精确函数调用栈。
* **正向执行与反向诊断**：前者从 App 追到硬件，后者从现象追到第一个发生拒绝、降级或故障的边界。
* **公开架构与私有实现**：稳定记忆公开职责、边界和行为；私有服务名、内部消息格式和版本细节不应提升为长期模型。

本章结论
--------

Capability Path 是移动 OS 最可复用的阅读坐标。面对任何 App 行为，先画出 App、Framework、IPC、能力所有者、策略、硬件边界和返回路径，再把具体平台组件填进去；这样既能理解 Android 与 Apple 的对应角色，也能从用户可见现象反向定位真正发生问题的系统边界。