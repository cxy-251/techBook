第060章：App Process as a Managed System Entity
===============================================

核心知识点
----------

* 移动平台中的 App process 既是普通操作系统进程，也是被平台生命周期和资源策略管理的系统实体。
* PID 只标识一次运行实例；package / bundle identity、签名与用户范围才构成长期应用身份。
* App process 同时是调度对象、内存对象、安全主体、生命周期载体和系统服务客户端。
* Framework 管理组件或 Scene 语义，runtime 管理代码执行与对象，system service 管理全局资源和策略，kernel 管理线程、内存与基础隔离。
* 前台、后台、挂起、缓存等状态会影响 CPU、内存、网络、定位、音频等资源可用性。
* 用户看到的一个 App 不一定只对应一个进程；多进程组件、extension 和系统宿主都会打破一一对应关系。
* 进程存活只是运行时优化，不能承担业务状态长期保存职责。

关键路径
--------

用户启动 App
→ 系统定位 package / bundle 与用户身份
→ 创建或复用 App process
→ 建立应用安全与资源上下文
→ runtime 建立主线程和执行环境
→ Framework 创建应用与界面对象
→ App 调用系统服务
→ 系统服务结合身份、生命周期和资源状态执行策略
→ kernel 分配 CPU、内存和 I/O
→ App 离开前台后进程重要性下降
→ 系统保留、挂起或回收进程
→ 下次按稳定应用身份重新创建并恢复用户任务。

概念辨析
--------

``PID`` 与 ``App identity``：PID 是短期运行句柄；package name、bundle id 和签名身份用于跨运行实例识别同一应用。

``Unix process`` 与 ``Mobile App process``：后者继承地址空间、线程和文件描述符，同时受生命周期、后台执行和平台资源策略控制。

``App`` 与 ``Process``：一个 App 可以拥有多个进程；进程死亡也不等于用户任务和持久化数据消失。

``Framework state`` 与 ``Process state``：前者描述组件或界面语义，后者描述系统对执行容器的资源保护等级。

本章结论
--------

移动 OS 把 App process 当成承载身份、生命周期、安全、调度和内存策略的受管执行容器。分析 App 行为时，应从应用身份和生命周期状态出发，再判断 runtime、system service 与 kernel 如何共同管理当前进程。
