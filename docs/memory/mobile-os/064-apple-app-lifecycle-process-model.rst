第064章：Apple App Lifecycle Process Model
=========================================

核心知识点
----------

* Apple 平台把 App process 作为带签名身份的执行容器，把 Scene 作为用户可见 UI session，两者生命周期不能混为一谈。
* Bundle identifier、code signing、entitlement、sandbox container 和 keychain / app group 等能力共同构成长期应用身份；PID 只代表本次运行实例。
* Scene-based lifecycle 允许同一进程承载多个 UI session；某个 Scene 离开前台并不必然意味着整个进程立即进入后台。
* Foreground active 表示 Scene 正在接收用户事件；inactive 是前台转换或中断状态；background 表示 UI session 已离开当前交互路径。
* 普通 App 进入后台后只获得有限执行窗口；更长期工作需要 BackgroundTasks、background URLSession、audio、location、Bluetooth 等系统认可机制。
* Suspended App 可能保留地址空间和对象图，但普通代码停止执行；系统可在内存压力下直接终止它。
* 进程被终止后，Scene session、NSUserActivity、持久化数据等恢复材料用于重建用户任务。
* Apple 生命周期策略的稳定边界是公开 framework、Scene 状态、background capability 和恢复契约；具体内部回收排序不应被应用依赖。

关键路径
--------

用户启动 App
→ 系统验证 bundle identity、签名与能力
→ 创建 App process
→ 连接或恢复 Scene session
→ Scene 进入 foreground inactive / active
→ 用户离开当前界面
→ Scene 进入 background
→ 系统给予有限后台收尾窗口或批准特定后台任务
→ 无持续执行理由时进程进入 suspended
→ 内存压力下系统可能终止进程
→ 用户返回时创建新进程
→ 系统重新连接 Scene session / user activity
→ App 从持久化状态重建界面与用户任务。

概念辨析
--------

``App identity`` 与 ``Process identity``：bundle 与签名身份长期稳定；进程实例可以反复创建和终止。

``Scene`` 与 ``Process``：Scene 表达 UI session；进程是执行容器。一个进程可承载多个 Scene，某个 Scene 后台化不一定使整个进程停止。

``Background`` 与 ``Suspended``：Background 仍可能执行短期或批准任务；Suspended 的普通线程不再推进。

``Background mode`` 与 ``Keep alive``：background mode 只服务特定平台语义，不是通用常驻机制。

本章结论
--------

Apple App 生命周期的核心是把应用身份、UI session、进程执行权和后台能力分层管理。可靠应用应把 Scene 状态与进程存活解耦，并默认 suspended process 可能随时被回收，通过系统恢复入口重建用户任务。
