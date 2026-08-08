URL as Address, State, Capability, and Routing Input
====================================================

核心知识点
----------

* URL 是 Web 的稳定公共接口：它能被收藏、分享、抓取、记录、缓存和重放，生命周期远长于页面内存状态。
* 一个 URL 同时承担地址、路由输入、可分享状态和能力载体等角色；不同角色必须区分，否则容易把敏感状态、临时状态和公共接口混在一起。
* ``scheme``、``host``、``port``、``path``、``query``、``fragment`` 被不同系统读取：浏览器、DNS、CDN、服务器、框架和页面脚本关注的部分并不相同。
* Origin 主要由 scheme、host、port 决定；path 和 query 改变资源或应用状态，通常不改变 origin。
* path 更适合表达资源身份与层级，query 更适合表达筛选、分页、排序等可分享视图状态；fragment 通常只在客户端参与文档内定位或局部状态。
* URL 会参与浏览器导航、CDN cache key、服务器路由、框架 route match、日志与监控，因此 URL 设计本质上是跨系统契约设计。
* 带 token、签名或邀请码的 URL 属于 capability URL：拿到字符串本身就可能获得权限，必须限制有效期、权限范围、重放与日志暴露。

关键路径
--------

普通导航路径：

``User Intent → Browser URL Parse → Origin / Navigation Decision → CDN / Edge Route → Server Route → Framework Match → Data / Representation → Browser Document → Fragment / UI State``

URL 组件责任：

``scheme → protocol/security``

``host/port → origin/DNS/virtual host``

``path → resource/router``

``query → shareable request state/cache variation``

``fragment → client-side document/application state``

Capability URL 安全路径：

``URL token → browser/history/log/referrer exposure → server validation → scope/expiry/replay check → limited action``

概念辨析
--------

* **URL vs 页面内状态**：URL 可被外部系统长期保存和重放；组件内存状态只存在于当前 runtime 生命周期。
* **Origin vs Domain**：同一注册域下的不同 host 仍可能属于不同 origin；scheme 或 port 变化也会改变 origin。
* **Query vs Fragment**：query 会随常规 HTTP 请求进入服务器并可能影响缓存键；fragment 通常不会发送给服务器。
* **资源身份 vs 视图状态**：资源身份更适合稳定 path；排序、筛选、分页等通常更适合 query。
* **普通 URL vs Capability URL**：普通 URL 主要定位资源；capability URL 本身携带可执行权限，应按凭据管理。
* **框架路由 vs URL 语义**：框架只是 URL 路由的一层消费者，浏览器、CDN、服务器和缓存已经先读取同一个 URL。

本章结论
--------

URL 不是页面地址字符串，而是跨 browser、network、cache、server、framework 和 security boundary 的长期接口。设计 URL 时应先确定资源身份、可分享状态、origin、安全暴露与缓存语义，再决定 path、query、fragment 和 token 的归属。