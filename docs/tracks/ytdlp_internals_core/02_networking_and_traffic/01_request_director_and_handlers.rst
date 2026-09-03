========================================================================================
02.01 RequestDirector 调度架构与多后端 RequestHandler 适配
========================================================================================

.. note:: 前置背景与上下文承接
   在第 1 模块中，我们完整解析了 ``YoutubeDL`` 的控制中枢、生命周期状态机与任务调度管线。当调度器执行 ``ydl.urlopen(req)`` 时，所有针对目标网站的探测、元数据拉取以及流媒体分片抓取，均被委托给底层的网络请求层。在早期的 ``youtube-dl`` 时代，网络层严重依赖 Python 标准库的 ``urllib.request.OpenerDirector``，在应对现代反爬机制（如 TLS 指纹检测、HTTP/2 帧头校验、WebSocket 交互、自定义 SOCKS 代理及多后端会话复用）时显得脆弱且难以扩展。``yt-dlp`` 彻底重构了网络栈，推出了以 ``RequestDirector`` 为核心、多后端 ``RequestHandler`` 插件化适配的现代化网络体系。本节将深度解构该架构的调度算法、抽象契约与多后端实现。

***
RequestDirector 统一调度中枢与多后端分发模型
***

``RequestDirector`` 是 ``yt-dlp`` 网络请求层的顶层控制中枢。它不再将请求逻辑硬编码在单一 HTTP 客户端中，而是维护一个后端处理器集合（``handlers``）与动态优先级评估规则集（``preferences``）。

.. code-block:: text
   :caption: RequestDirector 动态分发与故障降级状态机

   发起网络请求 Request(url, data, headers, extensions)
                           |
                           v
   +-------------------------------------------------------------------+
   | 1. 动态优先级计算 (Preference Evaluation)                         |
   |    - 遍历已注册的 RequestHandler (urllib, requests, curl_cffi, ws) |
   |    - 汇总评估函数: score = sum(pref(rh, request) for pref in ...) |
   |    - 按 score 降序对 handlers 进行排序                            |
   +-------------------------------+-----------------------------------+
                                   |
                                   v 遍历候选 Handler 队列 (for handler in sorted_handlers:)
   +-------------------------------------------------------------------+
   | 2. 能力前置校验 (Capability Validation)                           |
   |    - 调用 handler.validate(request)                               |
   |    - 校验 URL Scheme (http/https/ws/wss/data/ftp/file)            |
   |    - 校验 Proxy Scheme (socks5/http) 与 Features (NO_PROXY 等)    |
   |    - 校验 Extensions (impersonate, cookiejar, timeout 等)        |
   +-------------------------------+-----------------------------------+
                                   |
                   +---------------+---------------+
                   |                               |
                 未通过                          通过
                   v                               v
   [捕获 UnsupportedRequest]       +-----------------------------------+
   [记录至 unsupported_errors]     | 3. 发起物理网络请求 (handler.send)|
   [继续尝试下一个候选 Handler]    +---------------+-------------------+
                                                   |
                                   +---------------+---------------+
                                   |                               |
                                发生异常                         请求成功
                                   v                               v
                   [捕获 RequestError 或未预期异常]    [封装为统一 Response 对象]
                   [记录至 unexpected_errors]          [返回上层提取器 / 下载器]
                   [降级重试下一 Handler (若支持)]
                                   |
                                   v 若所有 Handler 均耗尽
                   [抛出 NoSupportingHandlers 聚合错误]

动态优先级决议算法 (Preference Resolution)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个 ``RequestHandler`` 拥有不同的网络特性与依赖要求。例如，``curl_cffi`` 专精于浏览器 TLS 指纹伪装但开销较大；``requests`` 具备连接池优势；``urllib`` 为零外部依赖的兜底保障；``websockets`` 专职处理全双工 WebSocket 长连接。

系统通过装饰器 ``@register_preference`` 注册打分策略函数：

.. code-block:: python

   def _get_handlers(self, request: Request) -> list[RequestHandler]:
       preferences = {
           rh: sum(pref(rh, request) for pref in self.preferences)
           for rh in self.handlers.values()
       }
       return sorted(self.handlers.values(), key=preferences.get, reverse=True)

默认基准偏好分值分布：
* ``RequestsRH``：基准权重 ``+100``（在安装了 ``requests`` 与 ``urllib3`` 时默认优先使用连接池）；
* ``UrllibRH``：基准权重 ``0``（标准库内置，稳健兜底）；
* ``CurlCFFIRH``：基准权重 ``-100``（仅在请求显式声明 ``impersonate`` 扩展或特定反爬提取器请求时动态提升权重）；
* 命令行参数 ``--compat-options prefer-legacy-http-handler``：动态向 ``UrllibRH`` 注入 ``+500`` 权重，实现即时降级。

---
Request 与 Response 抽象契约与扩展机制
---

为了隔绝不同第三方库（``urllib``、``requests``、``curl_cffi``、``websockets``）在请求/响应对象 API 上的巨大差异，网络层定义了严格的抽象契约。

统一请求对象 (Request)
~~~~~~~~~~~~~~~~~~~~~~

``Request`` 类统一封装了 HTTP/WS 请求的全部上下文元数据：

.. code-block:: python

   class Request:
       def __init__(self, url: str, data: RequestData = None,
                    headers: Mapping | None = None, proxies: dict | None = None,
                    query: dict | None = None, method: str | None = None,
                    extensions: dict | None = None):
           self.url = normalize_url(url)
           self.method = method  # 未指定时依据 data 是否存在自动决议为 POST 或 GET
           self.headers = HTTPHeaderDict(headers)  # 大小写不敏感且支持保序与大小写保留
           self.data = data      # 支持 bytes, Iterable[bytes], IOBase 流式负载
           self.proxies = proxies or {}
           self.extensions = extensions or {}  # 扩展元数据载荷

``extensions`` 扩展槽位允许上层提取器按需向底层透传精细化控制指令：
* ``impersonate``: 声明目标伪装浏览器（如 ``ImpersonateTarget('chrome', '120', 'macos', '14')``）；
* ``cookiejar``: 覆盖当前请求专用的 Cookie 容器；
* ``timeout``: 覆盖单个请求的 Socket 超时时间；
* ``legacy_ssl``: 强制开启不安全的遗留 SSL/TLS 握手兼容（针对老旧流媒体服务器）；
* ``keep_header_casing``: 强制底层保持 HTTP 头部字符的原始大小写（抵御特定 WAF 探测）。

统一响应适配器 (Response)
~~~~~~~~~~~~~~~~~~~~~~~~~

``Response`` 类继承自标准 ``io.IOBase``，以统一的流式接口适配所有底层的响应数据源：

.. code-block:: python

   class Response(io.IOBase):
       def __init__(self, fp: io.IOBase, url: str, headers: Mapping[str, str],
                    status: int = 200, reason: str | None = None, extensions: dict | None = None):
           self.fp = fp
           self.headers = Message()
           for name, value in headers.items():
               self.headers.add_header(name, value)
           self.status = status
           self.reason = reason
           self.url = url
           self.extensions = extensions or {}

       def read(self, amt: int | None = None) -> bytes:
           # 统一流式读取，底层发生网络中断时统一转换为 TransportError / IncompleteRead
           ...

---
四大多后端 RequestHandler 深度实现
---

.. list-table:: RequestHandler 多后端特性与协议栈支持矩阵
   :widths: 16 18 26 20 20
   :header-rows: 1

   * - 处理器名称
     - 底层核心依赖
     - 支持的 URL Scheme
     - 支持的代理类型
     - 核心优势与应用场景
   * - ``UrllibRH``
     - Python 标准库
     - ``http``, ``https``, ``data``, ``ftp``, ``file``
     - ``http``, ``socks4/5``
     - 零外部依赖、自研 SOCKS 代理直连、原生标准流式传输
   * - ``RequestsRH``
     - ``requests`` + ``urllib3``
     - ``http``, ``https``
     - ``http``, ``https``, ``socks4/5``
     - HTTP 连接池复用、Keep-Alive 长连接优化、高吞吐并发
   * - ``CurlCFFIRH``
     - ``curl_cffi`` (libcurl-impersonate)
     - ``http``, ``https``
     - ``http``, ``https``, ``socks4/5``
     - TLS JA3/JA4 指纹模拟、HTTP/2 Akamai 指纹混淆、反爬突破
   * - ``WebsocketsRH``
     - ``websockets``
     - ``ws``, ``wss``
     - ``socks4/5``
     - 全双工长连接、实时弹幕/直播元数据交互、SOCKS 代理穿透

1. UrllibRH 深度实现机制
~~~~~~~~~~~~~~~~~~~~~~~~

``UrllibRH`` 构建了高内聚的 ``urllib.request.OpenerDirector`` 处理器链条：

* **动态 SOCKS 代理直连**：通过 ``make_socks_conn_class`` 动态重写 ``HTTPConnection`` 与 ``HTTPSConnection`` 的 ``connect()`` 方法，直接在传输层接入 ``yt-dlp`` 自研的轻量级 SOCKS 协议栈（``yt_dlp/socks.py``），无需依赖第三方 ``PySocks``；
* **透明解压缩管道**：在 ``HTTPHandler.http_response()`` 中支持多层复合压缩编码（``gzip``, ``deflate``, ``brotli``），按照 ``Content-Encoding`` 响应头逆序解压；
* **RFC 7231 重定向合规修正**：自研 ``RedirectHandler``，精确纠正标准库在处理 301/302/303/307/308 重定向时的请求方法转换（如 POST 重定向为 GET 时自动剥离 ``Content-Length`` 与 ``Content-Type``，并清洗跨域 ``Cookie`` 头）。

2. RequestsRH 深度实现机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

``RequestsRH`` 针对多媒体高频分片拉取场景进行了深度适配：

* **自定义 SOCKS 连接池**：通过重构 ``SOCKSProxyManager`` 与 ``SocksHTTPConnectionPool``，使 ``requests`` 无缝复用系统的轻量 SOCKS 连接工厂；
* **大小写与百分号编码保护**：Monkey-patch ``urllib3.util.url._PERCENT_RE``，防止 ``urllib3`` 在 URL 规范化过程中将小写百分号转义（如 ``%2f``）强制转为大写，规避严格校验 URL 签名的 CDN 403 封锁；
* **308 重定向无缝修复**：在 ``RequestsSession.rebuild_method`` 中修复标准 ``requests`` 丢弃自定义请求体的缺陷。

3. CurlCFFIRH 深度实现机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

``CurlCFFIRH`` 是突破 Cloudflare、Akamai、DataDome 等先进反爬网关的利器：

* **单线程单响应生命周期管理**：针对底层 libcurl 句柄在单线程下仅允许一个活动流响应的限制，实现 ``CurlCFFIResponseReader``，在流读取完毕或发生异常时立即触发 ``close()`` 释放底层资源；
* **低速传输超时模拟**：通过配置 ``CurlOpt.LOW_SPEED_LIMIT = 1``（1 Byte/s）与 ``CurlOpt.LOW_SPEED_TIME = ceil(timeout)``，在 C 语言层面精确实现 Read Timeout 监测；
* **HTTPS 代理隧道**：显式设置 ``CurlOpt.HTTPPROXYTUNNEL = 1``，在访问 HTTPS 目标时严格启用 HTTP CONNECT 隧道代理。

4. WebsocketsRH 深度实现机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对当代直播平台（如 Twitch、YouTube Live Chat、Bilibili 直播）通过 WebSocket 推送元数据和时间线的架构：

* **同步长连接封装**：基于 ``websockets.sync.client`` 实现全双工管道，适配 ``WebSocketRequestHandler`` 基类契约；
* **SOCKS 代理穿透**：通过 ``create_socks_proxy_socket`` 在握手前建立底层的 TCP 代理隧道；
* **防挂死快速关闭**：强制注入 ``close_timeout = 0``，杜绝子进程在异常退出时因 WebSocket 双向握手挥手阻塞导致主线程挂死。

---
统一异常拓扑与错误自适应转换
---

为了防止底层各个库特有的原始异常（如 ``urllib.error.URLError``、``requests.exceptions.ConnectionError``、``curl_cffi.requests.errors.RequestsError``）泄漏至业务提取器，网络层通过 ``@wrap_request_errors`` 装饰器建立了统一的异常映射拓扑。

.. code-block:: text
   :caption: 网络层统一异常体系拓扑

                           YoutubeDLError
                                 |
                            RequestError
                                 |
     +---------------------------+---------------------------+
     |                           |                           |
   UnsupportedRequest     TransportError                  HTTPError
     |                           |                           |
   NoSupportingHandlers          +------- SSLError           (status, reason,
                                 |          |                 redirect_loop)
                                 |        CertificateVerifyError
                                 |
                                 +------- ProxyError
                                 |
                                 +------- IncompleteRead (partial, expected)

* **精确截断探测 (`IncompleteRead`)**：无论是标准库的 ``http.client.IncompleteRead`` 还是 libcurl 的 ``CurlECode.PARTIAL_FILE``，均统一解包并提取已读字节数 ``partial`` 与预期字节数 ``expected``，为断点续传器提供确切的重试分界点；
* **聚合异常报告 (`NoSupportingHandlers`)**：当所有 Handler 均因协议不匹配或缺少依赖而失败时，自动聚合输出所有 Handler 的具体拒绝原因（如 ``"Unsupported url scheme: 'wss' (urllib, requests) + curl_cffi not installed"``）。

---
端到端请求调用链与源码映射
---

.. code-block:: text
   :caption: RequestDirector 端到端请求流向时序

   InfoExtractor / Downloader        YoutubeDL.urlopen()       RequestDirector          RequestHandler (e.g. RequestsRH)
              |                               |                       |                               |
              |-- ydl.urlopen(Request) ------>|                       |                               |
              |                               |-- send(request) ----->|                               |
              |                               |                       |-- _get_handlers() (打分排序)  |
              |                               |                       |-- handler.validate(request) --|
              |                               |                       |-- handler.send(request) ----->|
              |                               |                       |                               |-- _create_instance()
              |                               |                       |                               |-- 建立 TCP / TLS 连接
              |                               |                       |                               |-- 发送 HTTP Payload
              |                               |                       |<-- ResponseAdapter -----------|<-- 获取原始 Socket 响应流
              |<-- Response (IOBase) ---------|<-- Response ----------|
              |
              |-- response.read(amt) ---------------------------------------------------------------->| 流式读取与动态解压

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 网络抽象层核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``RequestDirector``
     - ``yt_dlp/networking/common.py:45-125``
     - 调度中枢：Handler 优先级评估、动态能力校验、错误捕获与重试分发
   * - ``RequestHandler``
     - ``yt_dlp/networking/common.py:135-260``
     - 抽象基类：代理校验、Header 合并、SSLContext 生成与生命周期管理
   * - ``Request`` / ``Response``
     - ``yt_dlp/networking/common.py:270-420``
     - 统一数据契约、URL 规范化、流式适配器与废弃字段兼容层
   * - ``UrllibRH``
     - ``yt_dlp/networking/_urllib.py:180-260``
     - 基于标准库的轻量处理器、SOCKS 动态代理注入与多层解压
   * - ``RequestsRH``
     - ``yt_dlp/networking/_requests.py:170-265``
     - 基于 Requests 的连接池复用、urllib3 百分号编码保护与会话管理
   * - ``CurlCFFIRH``
     - ``yt_dlp/networking/_curlcffi.py:120-220``
     - 基于 libcurl-impersonate 的 TLS/HTTP2 指纹模拟与低速超时控制
   * - ``WebsocketsRH``
     - ``yt_dlp/networking/_websockets.py:65-135``
     - 同步 WebSocket 客户端封装、SOCKS 隧道穿透与防挂起超时管理

***
小结与下章导读
***

本节全面剖析了 ``yt-dlp`` 现代化的 ``RequestDirector`` 架构与四大多后端 ``RequestHandler`` 适配体系，厘清了：
1. 动态优先级分发算法与故障降级链条；
2. ``Request`` 与 ``Response`` 的统一契约与扩展槽设计；
3. ``UrllibRH``、``RequestsRH``、``CurlCFFIRH`` 与 ``WebsocketsRH`` 的底层运行机理与系统调用；
4. 统一网络异常拓扑与自适应错误捕获。

在下一节（``02_browser_impersonation_and_tls.rst``）中，我们将深入网络对抗的最前沿——剖析浏览器指纹伪装引擎，解密 ``ImpersonateTarget`` 如何在 Client Hello 阶段精确模拟各大主流浏览器（Chrome、Safari、Firefox、Tor）的密码套件、扩展顺序、ALPN、JA3/JA4 指纹及 HTTP/2 帧头特征。
