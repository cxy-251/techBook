第059章：Cookie, Local Storage, Session Storage, IndexedDB, and Storage Lifetime
================================================================================

核心知识点
----------

* 浏览器存储的首要判断是状态所有权与生命周期，不是 API 语法。先问状态由 server、browser、tab、origin 还是应用缓存拥有，再决定存储位置。
* Cookie 是 request-bound state：浏览器会按 Domain、Path、Secure、SameSite 等条件自动把匹配 cookie 放进请求，适合 session id 等需要服务端解释的小型状态句柄。
* ``HttpOnly`` cookie 不能被页面脚本读取，但仍能随匹配请求发送；它适合降低 XSS 直接窃取 session token 的暴露面。
* ``localStorage`` 按 origin 提供持久字符串键值存储；``sessionStorage`` 额外绑定当前 tab / browsing context 生命周期。二者 API 同步，频繁大对象序列化会占用主线程。
* IndexedDB 是异步、事务化、结构化的客户端数据库，适合离线草稿、大对象集合、索引查询和待同步 mutation 队列。
* 浏览器本地存储都不是绝对持久事实源。用户清理站点数据、隐私模式、配额、浏览器 eviction、partitioning 都可能使本地副本消失。
* 必须长期可靠保存的数据应有服务端 durable state；浏览器副本主要承担加速、离线、临时恢复和用户体验优化。
* 存储设计还必须包含 schema version、migration、TTL/清理、跨标签页同步、权限撤销和损坏数据恢复。

关键路径
--------

登录态：

::

   Server authenticates user
     → Set-Cookie
     → browser cookie jar
     → matching request automatically carries Cookie
     → server session lookup
     → authorization / personalized response

轻量 UI 偏好：

::

   UI state
     → localStorage
     → same-origin future page load
     → parse / validate / apply

单 tab 临时状态：

::

   Current tab interaction
     → sessionStorage
     → navigation / refresh in same tab
     → restore
     → tab closed → lifecycle ends

离线结构化状态：

::

   App intent
     → IndexedDB transaction
     → local durable candidate
     → sync worker / page
     → server confirmation
     → mark committed / delete pending record

概念辨析
--------

* Cookie 与 localStorage：cookie 会自动进入匹配 HTTP 请求；localStorage 只由脚本显式读取，不随请求自动发送。
* localStorage 与 sessionStorage：前者按 origin 跨页面/重启通常可保留，后者更接近当前 tab 的短期状态。
* Web Storage 与 IndexedDB：前者是同步字符串键值 API，适合小状态；后者是异步事务数据库，适合结构化和较大数据。
* 浏览器持久化与服务端持久化：浏览器数据受用户设备和浏览器策略影响，不能替代服务器数据库对关键事实的承诺。
* client validation 与 trusted state：任何脚本可改写的本地数据都不能直接作为权限、支付或业务真相。
* storage lifetime 与 application lifetime：应用升级、logout、tenant 切换时也需要主动清理旧本地状态，不能只依赖浏览器 eviction。

本章结论
--------

选择存储时固定检查 ``Owner → Request Participation → Read/Write Model → Lifetime → Recovery``。需要服务端自动识别的轻量状态进入 cookie；轻量 UI 偏好进入 localStorage；当前 tab 临时过程进入 sessionStorage；结构化离线数据进入 IndexedDB。关键业务事实必须有服务器落点，本地存储只是一份受生命周期和浏览器策略约束的副本。