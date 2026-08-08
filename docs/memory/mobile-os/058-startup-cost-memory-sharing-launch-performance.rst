第058章：Startup Cost, Memory Sharing, Launch Performance
========================================================

核心知识点
----------

* App launch 是从系统接受启动请求到首帧可见、核心入口可响应的完整路径，不只等于某个生命周期函数。
* 启动成本可拆成六类：进程创建、代码装载、资源装载、runtime 初始化、framework 生命周期初始化、首帧布局与绘制。
* Android 冷启动会经过 system_server、Zygote、ART、Application / Activity 与 first frame；Apple 会经过进程创建、dyld、语言 runtime、UIKit / SwiftUI 生命周期和首帧。
* TTID 关注首个可见界面，TTFD 关注完整可用状态；首帧路径只应承载用户马上需要的最小工作集。
* Cold / Warm / Hot Resume 的本质差异是系统和进程保留了多少状态以及多少缓存仍然命中。
* Runtime cache、page cache、AOT / JIT code、Zygote preload、dyld shared cache 和进程保留都能降低重复启动成本。
* 共享收益依赖只读代码页和稳定预加载；写脏页、COW、过重常驻对象和大量 App 私有初始化会降低共享效果。

关键路径
--------

通用启动链：

``Launch Request → Process Create / Resume → Code Mapping → Runtime Init → Framework Lifecycle → App Init → Layout / Draw → First Frame → Fully Ready``

Android 典型路径：

``Launcher → system_server → Zygote / cached process → ART → Application → Activity → View / Compose → first frame``

Apple 典型路径：

``SpringBoard / system launch → process → dyld → ObjC / Swift runtime → UIApplication / Scene → UIKit / SwiftUI → first frame``

排查顺序：

#. 先区分 cold、warm、resume，避免混用启动指标。
#. 看进程创建与 loader 阶段是否已经消耗大量时间。
#. 进入生命周期回调后，检查主线程同步 I/O、静态初始化、数据库、资源解码和布局工作。
#. 首帧后再分析完整数据加载，不要把 TTFD 工作塞回 TTID。
#. 同时观察启动期内存峰值，确认是否因 COW 破坏、图片缓存或大量对象初始化增加回收压力。

概念辨析
--------

* **TTID 与 TTFD**：TTID 是第一帧可见；TTFD 是应用达到完整可用状态。
* **Cold Start 与 Warm Start**：Cold 通常需要新进程；Warm 可复用部分进程、文件页或系统缓存。
* **Hot Resume 与 Cold Start**：Resume 主要恢复已有执行和 UI 状态，不应与从零创建进程比较同一成本模型。
* **Code Loading 与 Resource Loading**：前者建立可执行代码和类；后者建立布局、图片、资源表、数据库和首屏数据。
* **Memory Sharing 与 App Cache**：系统级共享减少多个进程重复页；App cache 是当前应用自己保留的数据和对象。

本章结论
--------

启动优化的核心是按时间线找出首帧前真正必须发生的工作。系统负责进程、装载、缓存和共享，App 负责收缩自己的首屏初始化。稳定判断应同时看启动类型、loader、runtime、主线程、资源 I/O、首帧和内存峰值，而不是只优化某个生命周期回调。