第160章：Android system_server Service Map
==========================================

核心知识点
----------

* ``system_server`` 是 Android 大量 Java System Service 的宿主进程，是阅读组件生命周期、包、窗口、电源、通知、输入策略等系统行为的第一张服务地图。
* ``SystemServer`` 由 Zygote 派生后按启动阶段创建和启动核心服务；服务共享一个进程空间，同时各自维护 Binder 接口、Handler、锁和全局状态。
* ``ActivityManagerService`` 负责进程、Service、Broadcast、ContentProvider 和进程重要性等生命周期状态；Activity/Task 相关职责在现代 Android 中也由 ActivityTaskManager 体系协同承担。
* AMS 保存进程记录和重要性，连接前台可见性、后台限制与内存回收策略。用户切回 App 是否需要重建，与进程状态和系统内存压力直接相关。
* ``PackageManagerService`` 负责安装包、Manifest、签名、组件、权限声明、用户安装状态和 Intent 解析，是“系统事实库”之一。
* PMS 给出的权限/组件事实不等于一次能力访问最终一定放行；AppOps、调用方身份、system service 内部 policy 仍可继续限制。
* ``WindowManagerService`` 持有窗口 token、z-order、focus、display policy、可见性和输入目标。Activity 已 RESUMED 不等于窗口已经完成绘制和获得输入焦点。
* ``PowerManagerService`` 管理 WakeLock、sleep/wake、screen state、电源状态和相关策略，是 App 声明“需要保持系统清醒”进入系统控制面的入口。
* ServiceManager 负责 Binder service 注册和查找。App / Framework 通过 service name 获得 Binder handle，再进入对应 system service。
* ``system_server`` 集中宿主带来共享故障面：主线程阻塞、关键全局锁长期持有、Binder thread pool 堵塞都可能影响多个系统服务。
* Watchdog 监控关键线程和锁的健康；ANR 主要针对 App/组件响应失败。系统服务卡死可能进一步触发 watchdog 诊断甚至 system_server 重启。
* 低延迟、数据流密集或强隔离能力通常进一步下沉到 native service，例如 SurfaceFlinger、AudioFlinger、CameraService、SensorService。

关键路径
--------

::

   App Framework call
   → Binder ServiceManager lookup
   → system_server Binder entry
   → AMS / PMS / WMS / PowerMS / other service
   → permission + identity + global state
   → process / package / window / power decision
   → callback / lifecycle / error

页面启动的典型协作：

::

   startActivity
   → package / component resolution
   → process start or reuse
   → activity lifecycle scheduling
   → window token and focus policy
   → App ViewRoot creates window surface
   → first frame becomes visible

概念辨析
--------

* **system_server 与 System Service**：system_server 是宿主进程，AMS/PMS/WMS 等是其中的服务对象。
* **AMS 与 WMS**：AMS/ATMS 决定组件和任务生命周期，WMS 决定窗口、焦点和显示策略。
* **PMS 与 runtime policy**：PMS 保存包、签名、权限等事实，实际调用还要经过服务侧权限和策略判断。
* **ANR 与 Watchdog**：ANR 关注 App/组件在规定窗口内未响应；Watchdog 更关注关键系统线程和服务健康。
* **Java Service 与 Native Service**：前者偏 Framework 策略和全局状态，后者常承担图形、音频、相机等低延迟资源控制和数据路径。

本章结论
--------

阅读 ``system_server`` 时，先把现象映射到状态所有者：进程/组件找 AMS/ATMS，包和权限事实找 PMS，窗口和焦点找 WMS，电源找 PowerMS。随后再追 Binder、线程、锁和下游 native service，避免把所有系统问题笼统归因给 system_server。