第001章：Mobile OS and Desktop OS Shared Foundations, Different Constraints
============================================================================

核心知识点
----------

* 桌面 OS 与移动 OS 共享同一组基础抽象：进程、线程、虚拟内存、文件、网络、设备、身份与权限。差异主要不在“有没有这些机制”，而在资源开放程度和系统控制强度。
* 桌面系统更接近长期用户会话模型：窗口可并行存在，后台进程可持续运行，文件系统与外设访问面更宽，用户或管理员承担更多配置责任。
* 移动系统更接近受控能力模型：App 默认位于沙箱内，敏感资源通过权限和系统服务开放，前后台状态、功耗、温控、隐私与连接状态都可改变一次请求的结果。
* App 不能把“拥有 API”理解为“拥有资源”。相机、麦克风、定位、蓝牙等能力实际由 system service、daemon、driver 和 kernel 管理，App 只获得受约束的访问入口。
* Mobile OS 会把 lifecycle 直接纳入资源策略。Foreground、background、suspended、cached、terminated 等状态会影响 CPU、网络、传感器、定位、后台任务和进程保留。
* 后台任务不是前台代码的无限延续。系统会通过 job、alarm、push、foreground service、Background Tasks 等入口控制唤醒频率、执行时长、网络条件和优先级。
* 文件访问在手机上通常以 app container 为默认边界；容器外数据通过 document picker、photo picker、media provider、share extension 等系统入口按对象授权。
* 安装、签名、应用身份、沙箱和分发渠道共同构成移动平台信任入口。应用被系统识别的不只是一个进程，而是一个带签名与权限状态的持久身份。
* Battery、thermal、privacy、sensor 和 connectivity 是移动平台的一等约束。弱网、高温、低电量、锁屏、权限撤销都可能让相同代码得到不同结果。
* 用户看到的权限弹窗、后台中断、通知延迟、掉帧、发热和耗电，通常是多层系统策略叠加后的输出，而不是单个 Framework API 的行为。

关键路径
--------

通用资源路径：

::

   user action
   → app process / threads
   → framework API
   → system policy and permission checks
   → system service / daemon
   → kernel resources and device path
   → result or failure

移动端后台路径：

::

   app leaves foreground
   → lifecycle state changes
   → system recalculates importance and budget
   → keep / suspend / defer / reclaim / terminate
   → later resume, relaunch, or restore state

信任入口：

::

   package / executable
   → signature validation
   → app identity
   → sandbox / container
   → permission grants
   → capability access

概念辨析
--------

* **共同 OS 基础与平台行为**：Linux、XNU、Windows kernel 都提供底层资源抽象；移动平台真正可见的差异大量发生在 kernel 之上的 service、runtime、policy 和 app model。
* **后台运行与后台能力**：进程存在不等于任意后台工作都被允许；系统按能力类型和预算决定是否继续执行。
* **Permission 与 resource ownership**：权限表示调用资格，资源所有权仍掌握在系统服务和底层设备栈中。
* **Sandbox 与文件不可访问**：沙箱定义默认隔离边界，系统仍可通过受控选择器或 capability 把特定外部数据授权给 App。
* **硬件支持与 App 可用**：设备具备能力只是前提，系统开放策略、当前状态和用户授权共同决定最终可用性。

本章结论
--------

桌面 OS 与移动 OS 使用相同的操作系统基本原语，但移动 OS 在其上建立了更强的控制面。理解手机系统时，应把权限、沙箱、生命周期、后台预算、功耗、温控、传感器隐私、网络状态、签名和分发视为资源路径的一部分；App 的用户可见行为是这些约束共同裁决后的结果。