第179章：PWA Installability, Manifest, Service Worker Update, and App Shell
===========================================================================

核心知识点
----------

* PWA 把普通网站扩展为可安装、可从系统入口启动、可离线降级的 Web 应用；运行时仍是浏览器和 Web 安全模型。
* Manifest 描述应用身份与启动行为，包括 name、icons、start_url、scope、display、theme/background color 等；它不负责离线缓存逻辑。
* Service Worker 位于 document 与 network 之间，可拦截同 scope 请求，决定网络、Cache Storage 或 fallback 路径。
* App shell 是稳定 UI 框架和基础资源，适合与动态业务数据分层缓存；shell 可长期复用，业务数据仍按新鲜度与权限规则读取。
* ``start_url``、router base、manifest scope、Service Worker scope 与部署目录必须一致，否则安装后导航会越界或失去控制。
* Service Worker 注册成功不等于当前页面立即被控制；install、waiting、activate、clients claim 等生命周期决定新旧 worker 如何交接。
* Service Worker update 本质是版本迁移。新 worker、旧 client、旧 shell cache、新静态资源和已打开页面可能同时存在。
* ``skipWaiting`` 可以加速新 worker 激活，也可能让正在运行的旧页面突然面对新缓存/协议，因此必须评估版本兼容。
* Cache 清理必须跟 release version 绑定。激活新 worker 时可删除旧 shell cache，但不能误删仍被旧 client 使用的必要资源。
* Hashed asset 与 shell version 应协同：静态资源用不可变 URL，shell/worker 负责切换版本，回滚时旧资源需要仍可获取。
* Installability 会提高用户对身份、离线能力、更新稳定性、权限透明和可卸载性的预期；它不是只多一个“安装按钮”。
* PWA 发布必须包含 rollback 与 cache cleanup 方案，否则错误 worker 可能比普通网页版本更长时间留在用户设备上。

关键路径
--------

安装与启动：

::

   browser loads HTTPS page
   → discover manifest
   → register service worker
   → browser evaluates installability
   → user installs
   → system launcher opens start_url
   → active service worker handles scoped requests
   → shell + runtime data compose UI

更新：

::

   publish new service-worker script
   → browser detects change
   → install new worker + prepare new caches
   → waiting while old clients exist
   → activate under chosen policy
   → clean obsolete caches
   → old/new clients converge or request reload

概念辨析
--------

* **Manifest 与 Service Worker**：manifest 描述应用身份和启动方式，Service Worker 控制请求、离线和更新路径。
* **App Shell 与 Business Data**：shell 是稳定界面框架，业务数据有独立权限、新鲜度和一致性要求。
* **HTTP Cache 与 Cache Storage**：HTTP cache 由浏览器缓存语义管理，Cache Storage 由应用/Service Worker 显式读写。
* **Install 与 Activate**：PWA 被用户安装和 Service Worker 激活是不同生命周期事件。
* **Update 与 Immediate Replacement**：发现新 worker 不代表立即替换旧 active worker；等待和 client 生命周期是版本安全边界。

本章结论
--------

PWA 应按 ``Identity/Manifest → Install Entry → Service Worker Scope → App Shell → Version Update → Cache Cleanup/Rollback`` 阅读。PWA 的难点不在“可安装”，而在安装后长期存在的新入口、新缓存和新版本生命周期必须与 Web 发布体系保持一致。