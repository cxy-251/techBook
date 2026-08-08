第060章：Service Worker, Cache Storage, Offline Path, and Request Interception
=============================================================================

核心知识点
----------

* Service Worker 是注册在 origin/scope 下、运行在页面之外的事件驱动 worker；它没有 DOM 访问权，却能在受控 scope 内成为页面与网络之间的可编程中介层。
* 页面受 active Service Worker 控制后，匹配请求会进入 ``fetch`` event；``respondWith()`` 可以用 Cache Storage、网络结果或应用 fallback 提供 ``Response``。
* Service Worker 不会绕过 CORS、cookie、安全上下文等浏览器安全模型；它拥有请求路由能力，不拥有更高安全权限。
* 生命周期由 registration、install、waiting、activate、control 组成。上传新脚本不等于所有已打开页面立即切换到新版本。
* ``event.waitUntil()`` 把 install/activate 中的异步工作纳入生命周期成功条件；安装失败时旧 worker 可以继续服务当前用户。
* Cache Storage 是应用显式管理的 Request/Response 缓存，与 HTTP cache 不同。前者由代码决定 put/match/delete，后者由 HTTP cache semantics 决定复用。
* 缓存策略必须按资源语义区分：hashed static asset 常适合 cache-first；导航常适合 network-first + offline fallback；允许短暂陈旧的数据可使用 stale-while-revalidate。
* 写请求不能因为“离线”就伪装成已持久化成功。离线 mutation 应显式建模 pending queue、幂等性、重试、冲突和服务器最终确认。
* Service Worker 版本、Cache Storage 版本和本地 schema 需要协调，否则会出现旧 worker + 新页面、旧缓存 + 新代码的客户端 split-brain。

关键路径
--------

受控请求：

::

   Page navigation / fetch
     → Browser Fetch
     → active Service Worker fetch event
     → route by Request semantics
       → Cache Storage
       → Network / HTTP cache / Server
       → Offline fallback
     → Response
     → Page

更新生命周期：

::

   register
     → fetch SW script
     → install
     → waiting
     → activate
     → claim/control clients

离线写入：

::

   User mutation
     → offline detected / request fails
     → persist pending operation
     → UI marks pending
     → reconnect
     → retry with idempotency key
     → server confirmation
     → clear pending state

概念辨析
--------

* Service Worker 与 Web Worker：前者面向请求拦截、离线和后台事件；后者主要承担页面之外的计算任务。
* Cache Storage 与 HTTP cache：Cache Storage 是应用显式缓存；HTTP cache 受 ``Cache-Control``、``ETag``、``Vary`` 等协议语义控制。
* offline fallback 与离线数据正确：能打开离线页面只说明 UI 可用，不能证明业务数据新鲜或 mutation 已同步。
* ``skipWaiting`` 与“立即升级”：它可以加速版本切换，也可能让同一页面生命周期前后由不同 worker 版本处理请求。
* cache-first 与长期正确：只有 URL/version 能稳定表达内容版本时，静态资源长期 cache-first 才安全。
* Service Worker response 与 server response：页面最终拿到的 ``Response`` 可能来自本地缓存或合成结果，调试必须先确认响应所有者。

本章结论
--------

Service Worker 的核心不是“做缓存”，而是改变请求所有权。分析时沿 ``Page → Browser → Service Worker → Cache/Network → Response`` 追踪，并把生命周期、版本、离线恢复和写入一致性放在同一模型中。静态资源、导航、读取接口和 mutation 必须分别设计策略，不能用一个通用缓存分支覆盖全部请求。