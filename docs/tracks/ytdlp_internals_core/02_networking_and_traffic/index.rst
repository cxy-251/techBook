========================================================================
第 2 模块：网络请求层与协议栈适配 (02_networking_and_traffic)
========================================================================

本模块深入剖析 ``yt-dlp`` 现代化的网络抽象层系统。针对高对抗性反爬环境与多协议场景，``yt-dlp`` 构建了高度解耦的 ``RequestDirector`` 与请求处理器分发机制。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_request_director_and_handlers
   02_browser_impersonation_and_tls
   03_cookiejar_and_session_management
   04_proxy_and_geo_bypass

模块核心要点
------------

1. **RequestDirector 架构**：多后端 RequestHandler (`urllib`, `requests`, `curl_cffi`, `websockets`) 的优先级挂载、动态重试与错误分发。
2. **浏览器指纹伪装**：基于 ``curl_cffi`` 的 Client Hello 协商、JA3/JA4 TLS 指纹模拟与 HTTP/2 帧头伪装。
3. **CookieJar 凭证提取与管理**：系统级 Keyring 结合 DPAPI/Keychain/SecretStorage 的本地浏览器 Cookie 解密与基于 URL 的安全作用域隔离。
4. **代理与地理位置规避**：复杂代理链 (HTTP/SOCKS5)、IP 欺骗与基于 X-Forwarded-For 的地理围栏突破机制。
