第063章：Android App Component Process Model
============================================

核心知识点
----------

* Android 先安装 package，再按需创建承载组件的 Linux 进程；Activity、Service、BroadcastReceiver、ContentProvider 的状态共同决定进程重要性。
* 默认情况下组件共享应用主进程；``android:process`` 可以把组件拆到独立私有进程，从而形成独立地址空间、主线程、堆和故障边界。
* Activity 的可见性直接影响进程优先级：resumed Activity 通常使进程处于前台高保护状态，stopped Activity 所在进程更容易进入 cached 状态。
* Service 表达无界面工作或 IPC 服务语义。started service、bound service、foreground service 的系统意义不同，不能把任意后台线程等同于 Service。
* BroadcastReceiver 适合短生命周期事件处理；长任务应尽快转交 WorkManager、JobScheduler、foreground service 等系统认可入口。
* ContentProvider 既是数据访问接口，也可能触发目标进程创建，并建立跨进程依赖关系。
* Android 会依据进程重要性、组件状态和内存压力决定回收顺序；cached process 是主要回收候选。
* 组件生命周期与进程生命周期不是一回事：task/back stack 可以存在，而承载它的进程已经被系统杀死。

关键路径
--------

Intent / Binder / ContentResolver 等入口到达
→ 系统解析目标 package 与组件
→ 根据 Manifest 的 ``android:process`` 决定承载进程
→ 进程不存在则创建并初始化 Application
→ 分发 Activity / Service / Receiver / Provider 生命周期
→ Framework 根据活跃组件和跨进程依赖计算进程重要性
→ 前台组件提升保护等级
→ 后台组件受执行限制和调度策略约束
→ 无活跃组件的进程进入 cached 候选
→ 内存压力下系统回收进程
→ 下次组件入口重新创建进程并恢复状态。

概念辨析
--------

``Component`` 与 ``Process``：组件是 Android 应用语义单位，进程是执行容器；多个组件可以共用一个进程，也可以被显式拆分。

``Started Service`` 与 ``Foreground Service``：前者表示服务已被启动；后者还要求任务对用户可感知，并承担更严格的通知、类型和启动限制。

``BroadcastReceiver`` 与 ``Background Worker``：Receiver 只提供短执行窗口，可靠长任务应转交调度器或服务。

``Task / Back Stack`` 与 ``Process``：任务栈表达用户导航历史；进程可以在任务仍存在时被回收。

本章结论
--------

Android 进程模型以组件状态驱动进程重要性。设计和排障时应先定位组件在哪个进程运行、它当前处于什么生命周期状态、是否存在跨进程依赖，再判断后台限制和内存回收如何影响该进程。
