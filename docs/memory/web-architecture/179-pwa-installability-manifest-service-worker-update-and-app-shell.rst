第179章：PWA Installability, Manifest, Service Worker Update, and App Shell
===========================================================================

核心知识点
----------

* PWA 把普通网站扩展为可安装、可从系统入口启动并获得更接近平台应用的使用体验；运行时仍受浏览器与 Web 安全模型约束。
* Installability 与 offline capability 是两条不同路径。支持安装的浏览器通常依据 HTTPS、安全上下文、Web App Manifest 与自身安装规则判断是否可安装；Service Worker **不是 PWA 可安装的通用必要条件**。
* Manifest 描述应用身份与启动行为，包括 name、icons、start_url、scope、display、theme/background color 等；它不负责离线缓存逻辑。
* Service Worker 位于 document 与 network 之间，可在受控 scope 内拦截请求，选择网络、Cache Storage 或 fallback 路径；它主要承担离线、请求控制、后台事件与版本更新责任。
* App shell 是稳定 UI 框架和基础资源，适合与动态业务数据分层缓存；shell 可长期复用，业务数据仍按新鲜度、权限和一致性规则读取。
* ``start_url``、router base、manifest scope 与部署目录必须协调；若同时使用 Service Worker，其 scope 也要与这些 URL 边界兼容，但四者不要求机械相等。
* Service Worker 注册成功不等于当前页面立即被控制；install、waiting、activate、claim/control 等生命周期决定新旧 worker 如何交接。
* Service Worker update 本质是客户端版本迁移。新 worker、旧 client、旧 shell cache、新静态资源和已打开页面可能同时存在。
* ``skipWaiting`` 可以加速新 worker 激活，也可能让正在运行的旧页面突然面对新缓存或新协议，因此必须评估版本兼容。
* Cache 清理必须跟 release version 绑定。激活新 worker 时可删除明确过期的 cache，但不能误删仍被旧 client 依赖的资源。
* Hashed asset 与 shell version 应协同：静态资源用不可变 URL，HTML/manifest/worker 负责选择版本，回滚时旧资源需要在兼容窗口内仍可获取。
* Installability 会提高用户对身份、启动稳定性、权限透明、更新与可卸载性的预期；offline 则是另外一项产品承诺，不能因为“已安装”就默认成立。
* 只有产品确实需要离线、请求拦截或后台能力时才应引入 Service Worker；错误 worker 的驻留时间和缓存影响往往比普通网页发布更长。

关键路径
--------

安装与启动：

::

   browser loads secure page
   → discover web app manifest
   → browser evaluates current installability rules
   → user installs
   → system launcher opens start_url
   → browser creates app window / document
   → normal network path or optional active service worker
   → runtime data composes UI

可选离线与请求控制：

::

   page registers service worker
   → install
   → waiting / activate
   → control scoped clients
   → fetch event chooses cache / network / fallback
   → offline-capable response path

更新：

::

   publish new service-worker script
   → browser detects change
   → install new worker + prepare caches
   → waiting while old clients exist
   → activate under chosen policy
   → clean obsolete caches
   → old/new clients converge or request reload

概念辨析
--------

* **Installability 与 Service Worker**：安装能力由 manifest、安全上下文和浏览器规则决定；Service Worker 常用于离线与请求控制，但不是通用安装前提。
* **Manifest 与 Service Worker**：manifest 描述应用身份和启动方式，Service Worker 控制受管 scope 内的请求与后台生命周期。
* **Installed 与 Offline-Capable**：应用能从系统入口启动，不代表离线时一定能加载 shell 或业务数据。
* **App Shell 与 Business Data**：shell 是稳定界面框架，业务数据有独立权限、新鲜度和一致性要求。
* **HTTP Cache 与 Cache Storage**：HTTP cache 由浏览器缓存语义管理，Cache Storage 由应用或 Service Worker 显式读写。
* **Install 与 Activate**：PWA 被用户安装和 Service Worker 激活是不同生命周期事件。
* **Update 与 Immediate Replacement**：发现新 worker 不代表立即替换旧 active worker；等待和 client 生命周期是版本安全边界。

本章结论
--------

PWA 应拆成两条路径理解：``Manifest / Secure Context → Install Entry → start_url`` 负责安装与启动，``Optional Service Worker → Cache/Network → Update/Cleanup`` 负责离线、请求控制与客户端版本迁移。最重要的边界是不要把“可安装”和“有 Service Worker / 可离线”写成同一个必要条件。