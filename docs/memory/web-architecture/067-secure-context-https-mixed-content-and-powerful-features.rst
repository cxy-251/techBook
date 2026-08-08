第067章：Secure Context, HTTPS, Mixed Content, and Powerful Features
===================================================================

核心知识点
----------

* Secure Context 是浏览器开放强能力 API 的前提条件；很多 Service Worker、Clipboard、Geolocation、媒体、设备和 GPU 能力只在可信上下文中工作。
* ``window.isSecureContext`` 可观察当前 ``Window`` 是否满足 secure-context 前提，但它只回答第一层门槛，后续仍要检查 API 支持、permission、user activation、设备状态等条件。
* HTTPS 同时承担传输机密性、服务器身份认证和响应完整性，并把页面放进可信的 ``https://`` origin 安全模型。
* Secure Context 判断不仅看当前 URL，也会受 ancestor frame、worker owner、浏览器信任规则等关系影响。
* ``localhost``、``127.0.0.1`` 等本地环境通常有 potentially trustworthy 例外；局域网 IP、临时预览域名和真机调试地址不能默认获得同样待遇。
* Mixed Content 是 HTTPS document 继续加载不安全 HTTP 子资源。它破坏“页面及其依赖都来自可信通道”的假设。
* 脚本、stylesheet、iframe、font、Fetch 等高影响资源通常属于可阻止 mixed content；部分图片、音视频可能被浏览器自动升级到 HTTPS。
* 自动升级只在目标资源真实支持 HTTPS 时有效；旧 CDN、CMS 内容、绝对 HTTP URL 仍可能导致资源缺失或功能失败。
* HTTP→HTTPS redirect、HSTS、证书更新、CDN TLS、回源协议和子资源 URL 必须作为一个部署契约设计。
* HSTS 的作用是让浏览器在已知站点上直接使用 HTTPS，减少首次 HTTP 跳转被劫持的机会；策略失误也可能让证书故障变成整站不可达。
* 生产依赖 secure-context-only API 时，dev、preview、test 环境应尽量保持安全前提一致，避免“本地可用、预览失败”或相反情况。

关键路径
--------

页面能力路径：

``User Navigation → HTTPS/TLS → Certificate + Host Verification → Secure Document → isSecureContext → API Surface Check → Permission/User Activation → Device/Browser Capability → Result``

Mixed Content 路径：

``HTTPS Document → Discover HTTP Subresource → Browser classify mixed content → auto-upgrade to HTTPS 或 block → resource success/failure → UI/feature result``

部署路径：

``HTTP Entry → redirect/HSTS → CDN/Edge TLS → HTTPS Origin → Secure Response → HTTPS subresources/workers/API → Browser secure-context enforcement``

排查时先确认地址栏与 ``isSecureContext``，再看证书/TLS，再看 Network/Security 面板中的 mixed content，最后检查 CDN、模板、CMS、worker、API 和第三方资源的实际 URL。

概念辨析
--------

* HTTPS ≠ 用户已经授权能力。HTTPS 只是 secure context 的基础，camera/location/notification 等仍有独立 permission 门槛。
* Secure Context ≠ API 一定存在。浏览器版本、设备和产品策略仍决定 API surface。
* Mixed Content ≠ 只有脚本问题。图片、媒体、字体、iframe、API 请求都可能破坏或触发安全处理。
* 自动升级 ≠ 完整迁移。浏览器把 ``http`` 改为 ``https`` 后，目标域必须真的提供正确 HTTPS 资源。
* CDN 对外 HTTPS ≠ 全链路安全。边缘到源站的回源协议、证书与信任配置同样属于运营安全边界。
* 本地可信例外 ≠ 生产保证。开发环境的 localhost 便利行为不能作为远程预览和正式部署的安全前提。

本章结论
--------

Secure Context 应作为现代 Web 的运行环境基线理解：``HTTPS 可信交付 → 安全文档 → 安全子资源 → 强能力 API``。只要产品依赖后台执行、权限、设备、实时媒体或 GPU，就必须把证书、HTTPS 升级、mixed content 和各环境安全一致性纳入架构，而不是等 API 报错后再补。