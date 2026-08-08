第126章：Camera Privacy and Resource Arbitration
===============================================

核心知识点
----------

* Camera permission 只是敏感硬件访问的入口条件，不等于当前一定能打开设备。
* 一次真实相机访问至少经过 ``App identity → permission grant → lifecycle/foreground state → system service policy → resource ownership → session``。
* Permission prompt、grant state、service check、resource check 是不同层：用户同意后，系统仍会在每次访问时重新评估当前状态。
* 相机设备通常由系统服务持有并仲裁；多 App 竞争时，系统依据前台状态、优先级、平台角色和设备并发能力决定谁成为 owner。
* Privacy indicator 是用户可见的当前占用证据，与过去的授权记录不同。App 内相机开关应和真实 session 状态保持一致。
* Foreground / while-in-use policy 把持续相机采集与用户可见性绑定；后台使用通常受到更严格限制。
* Session 可能因另一个客户端抢占、设备断开、权限撤销、媒体服务重置或硬件错误而进入 disconnect / interruption / error 路径。
* 资源回收和错误恢复是正常设计要求：释放旧 session、更新 UI、保存业务状态，并在条件重新满足时重建会话。

关键路径
--------

访问判定：

``User Action → App Permission Check → Runtime Grant → Framework Open Request → System Service Identity / Policy Check → Resource Arbitration → Camera Session``

竞争与抢占：

``Existing Owner + New Client → System Priority / Concurrency Decision → Keep / Share / Preempt / Reject → Disconnect or Error Callback``

隐私闭环：

``Permission History + Active Camera Session → System Privacy Indicator / Dashboard → User-visible Occupancy``

概念辨析
--------

* **Permission vs availability**：permission 表示用户允许请求；availability 表示设备当前是否能分配。
* **Grant state vs service check**：grant 是授权记录；service check 是当前这次访问的实时策略判断。
* **Privacy indicator vs permission prompt**：prompt 发生在授权入口；indicator 表达此刻正在访问。
* **Disconnect vs crash**：session 被抢占或设备失效可以正常触发 disconnect/error，不等同于 App 崩溃。
* **Foreground qualification vs device ownership**：满足前台要求后仍要经过硬件资源仲裁。

本章结论
--------

相机隐私模型是一条持续授权链，不是一次弹窗。稳定判断应是 ``身份 → 权限 → 生命周期 → 系统策略 → 资源所有权 → Session → 用户可见指示``。因此“已经授权但打不开”“切后台后被断开”“另一个 App 打开后原会话失效”都属于系统资源治理的正常结果。