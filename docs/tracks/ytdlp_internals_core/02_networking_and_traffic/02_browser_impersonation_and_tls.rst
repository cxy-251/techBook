========================================================================================
02.02 浏览器指纹伪装：ImpersonateTarget 与 TLS Client Hello / JA3 / JA4 握手特征模拟
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们剖析了 ``RequestDirector`` 的调度中枢与多后端 ``RequestHandler`` 分发机制。在当代流媒体对抗中，以 Cloudflare Bot Management、Akamai Bot Manager、DataDome、AWS WAF 为代表的边缘安全网关，已将防御阵地从传统的应用层请求头审查，前移至传输层安全协议（TLS Handshake）与应用层传输通道（HTTP/2 Framing）。Python 原生标准库（如 ``ssl`` 模块）因采用固定的 OpenSSL 握手模板，在建立 TCP 连接的瞬间便会暴露自动化程序特征。本节将深入剖析 ``yt-dlp`` 的浏览器指纹伪装引擎，解密 ``ImpersonateTarget`` 拓扑模型、Client Hello / JA3 / JA4 指纹模拟机制以及 HTTP/2 帧头特征对抗。

***
TLS 与 HTTP/2 协议层反爬对抗机理
***

在传输层与会话层，反爬网关主要通过 **多维协议指纹提取算法** 判定客户端是否为合法真实浏览器：

.. code-block:: text
   :caption: 反爬网关多层指纹检测拓扑

   客户端发起连接
         |
         v
   [Layer 1: TCP/IP 特征] --------> IP 地理位置、TCP SYN 报文中的 Window Size、TTL、MSS
         |
         v
   [Layer 2: TLS 握手特征] -------> Client Hello 密码套件列表、扩展顺序、椭圆曲线、GREASE 注入
   (JA3 / JA4 / Fingerprint)       ALPN 协商、签名算法集 (Signature Algorithms)
         |
         v
   [Layer 3: HTTP/2 帧层特征] ----> SETTINGS 帧参数与顺序、WINDOW_UPDATE 增量、伪头顺序
   (Akamai H2 Fingerprint)         (:method, :authority, :scheme, :path)
         |
         v
   [Layer 4: HTTP 应用层特征] -----> User-Agent 与 Client Hints (Sec-CH-UA-*) 的一致性校验

Python 原生 OpenSSL 栈的致命缺陷
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **缺失 GREASE (RFC 8701) 机制**：真实现代 Chrome 浏览器会在密码套件与扩展列表中随机插入保留的伪扩展码（如 ``0x0a0a``, ``0x1a1a`` 等），OpenSSL 默认不具备此混淆行为；
2. **密码套件与扩展顺序固定**：OpenSSL 发送的 Client Hello 扩展排列与主流浏览器存在结构性偏离；
3. **后量子密码学扩展缺失**：新版 Chrome 默认启用混合后量子密钥协商机制（如 ``X25519Kyber768Draft00``），而标准 Python 无法模拟此类前沿 TLS 扩展；
4. **HTTP/2 帧参数暴露**：标准库不支持细粒度控制 HTTP/2 的 ``SETTINGS`` 帧初始窗口及伪头排列顺序。

---
ImpersonateTarget 数据结构与模糊匹配拓扑
---

``yt-dlp/networking/impersonate.py`` 定义了不可变的强类型伪装目标类 ``ImpersonateTarget``：

.. code-block:: python

   @dataclass(order=True, frozen=True)
   class ImpersonateTarget:
       client: str | None = None      # 浏览器客户端名称 (chrome, safari, firefox, edge, tor)
       version: str | None = None     # 客户端大版本号 (如 120, 17.0, 135)
       os: str | None = None          # 运行操作系统 (windows, macos, android, ios, linux)
       os_version: str | None = None  # 操作系统版本 (如 10, 14, 15)

DSL 语法解析与字符串序列化
~~~~~~~~~~~~~~~~~~~~~~~~~~

``ImpersonateTarget`` 支持紧凑的 DSL 字符串表达，支持在 CLI（``--impersonate``）与提取器元数据中无缝切换：

.. list-table:: ImpersonateTarget DSL 表达范例
   :widths: 32 30 38
   :header-rows: 1

   * - DSL 字符串
     - 解析后的实体属性
     - 语义匹配范围
   * - ``chrome``
     - ``client='chrome'``
     - 匹配任意 OS 上的任意 Chrome 版本
   * - ``chrome-120:macos-14``
     - ``client='chrome', version='120', os='macos', os_version='14'``
     - 精确锁定 macOS 14 上的 Chrome 120
   * - ``safari:ios``
     - ``client='safari', os='ios'``
     - 匹配所有 iOS 平台上的 Mobile Safari
   * - ``firefox:windows-10``
     - ``client='firefox', os='windows', os_version='10'``
     - 匹配 Windows 10 平台上的 Firefox 浏览器

模糊匹配算法 (`__contains__`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了实现“提取器请求宽泛目标（如 ``chrome``）时，引擎自动匹配底层可用的最适宜具体版本（如 ``chrome-120:macos-14``）”，``ImpersonateTarget`` 重载了 ``__contains__`` 运算符：

.. code-block:: python

   def __contains__(self, target: ImpersonateTarget):
       if not isinstance(target, ImpersonateTarget):
           return False
       return (
           (self.client is None or target.client is None or self.client == target.client)
           and (self.version is None or target.version is None or self.version == target.version)
           and (self.os is None or target.os is None or self.os == target.os)
           and (self.os_version is None or target.os_version is None or self.os_version == target.os_version)
       )

当请求对象声明 ``extensions={'impersonate': ImpersonateTarget('chrome')}`` 时，系统评估函数 ``impersonate_preference`` 立即为支持该目标的处理器（如 ``CurlCFFIRH``）赋予 **+1000 绝对优先权**，确保请求直接路由至指纹伪装后端。

---
libcurl-impersonate 底层对抗与 TLS 握手特征重构
---

``CurlCFFIRH`` 通过底层 CFFI 绑定的 ``libcurl-impersonate``（基于打补丁的 BoringSSL 与 NSS），在 C 语言层面对 TLS Client Hello 字节流进行全量重构。

.. code-block:: text
   :caption: Client Hello 握手报文关键特征注入

   TLSv1.3 Record Layer: Handshake Protocol: Client Hello
   +-------------------------------------------------------------------+
   | Version: TLS 1.2 (0x0303)                                         |
   | Random: 32 bytes (Gmt_unix_time + Random Bytes)                   |
   | Session ID: 32 bytes                                              |
   | Cipher Suites (根据目标浏览器精确排列，包含 GREASE 0x0a0a 等):    |
   |   - TLS_AES_128_GCM_SHA256 (0x1301)                               |
   |   - TLS_AES_256_GCM_SHA384 (0x1302)                               |
   |   - TLS_CHACHA20_POLY1305_SHA256 (0x1303)                         |
   |   - TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256 (0xc02b)              |
   |   - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 (0xc02f)                |
   | Extension: server_name (SNI)                                      |
   | Extension: extended_master_secret                                 |
   | Extension: renegotiation_info                                     |
   | Extension: supported_groups (GREASE + X25519 + secp256r1 + ...)   |
   | Extension: ec_point_formats (uncompressed)                        |
   | Extension: session_ticket                                         |
   | Extension: application_layer_protocol_negotiation (h2, http/1.1)  |
   | Extension: signature_algorithms (ecdsa_secp256r1_sha256, ...)     |
   | Extension: key_share (GREASE + X25519 Key Exchange Data)          |
   | Extension: psk_key_exchange_modes                                 |
   | Extension: supported_versions (GREASE + TLS 1.3 + TLS 1.2)        |
   +-------------------------------------------------------------------+

HTTP/2 帧层指纹混淆 (Akamai H2 Fingerprinting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在建立 TLS 隧道并完成 ALPN 协商为 ``h2`` 之后，反爬网关会立即审查客户端发出的首个 HTTP/2 ``SETTINGS`` 帧及伪头排列：

1. **SETTINGS 帧参数与顺序精确模拟**：
   * Chrome 顺序：``SETTINGS_HEADER_TABLE_SIZE(65536)`` $\rightarrow$ ``SETTINGS_ENABLE_PUSH(0)`` $\rightarrow$ ``SETTINGS_MAX_CONCURRENT_STREAMS(1000)`` $\rightarrow$ ``SETTINGS_INITIAL_WINDOW_SIZE(6291456)`` $\rightarrow$ ``SETTINGS_MAX_HEADER_LIST_SIZE(262144)``；
   * Firefox 顺序：``SETTINGS_HEADER_TABLE_SIZE(65536)`` $\rightarrow$ ``SETTINGS_INITIAL_WINDOW_SIZE(131072)`` $\rightarrow$ ``SETTINGS_MAX_FRAME_SIZE(16384)``。
2. **伪头（Pseudo-Headers）顺序锁定**：
   * Chrome/Safari 标准顺序：``:method`` $\rightarrow$ ``:authority`` $\rightarrow$ ``:scheme`` $\rightarrow$ ``:path``；
   * 严禁出现标准 Python 客户端常见的乱序排列。

---
目标矩阵演进与启发式自适应优选 (`BROWSER_TARGETS`)
---

``yt_dlp/networking/_curlcffi.py`` 内置了跨版本的庞大浏览器指纹拓扑映射字典 ``BROWSER_TARGETS``，覆盖了从 ``curl_cffi`` 0.5.10 到 0.16.1+ 的全部预置目标。

.. list-table:: BROWSER_TARGETS 核心指纹版本演进与平台映射
   :widths: 18 24 30 28
   :header-rows: 1

   * - curl_cffi 版本区间
     - 代表性浏览器 Target
     - 目标操作系统
     - 握手特征升级要点
   * - ``0.5.x ~ 0.6.x``
     - ``chrome99``, ``chrome116``, ``safari170``
     - Windows 10, macOS 14
     - 初代 JA3 模拟，支持基础 TLS 扩展与 HTTP/2 帧重构
   * - ``0.7.x ~ 0.9.x``
     - ``chrome120``, ``chrome131``, ``firefox133``
     - macOS 14, Android 14
     - 引入 JA4 指纹支持，校准 Safari 17.2 iOS 移动指纹
   * - ``0.10.x ~ 0.12.x``
     - ``firefox135``, ``safari184``, ``safari260``
     - macOS 15, iOS 18.4
     - 优化 TLS 1.3 Key Share 混合协商，修复 Safari 18 拓展顺序
   * - ``0.14.x ~ 0.16.x``
     - ``chrome145``, ``chrome150``, ``firefox147``
     - macOS 26, Windows 11
     - 深度适配后量子密码学扩展（Kyber）与最新 Client Hints

指纹启发式降序优选权重算法
~~~~~~~~~~~~~~~~~~~~~~~~~~

当提取器仅请求模糊目标（如 ``impersonate=True``）时，引擎如何从数十个预置指纹中选出最佳目标？``_SUPPORTED_IMPERSONATE_TARGET_MAP`` 采用 **多维权重排序管道**：

.. code-block:: python

   key = lambda x: (
       # 1. 降级不可靠或已知被风控识别的特征目标 (_DEPRIORITIZED_TARGETS: chrome133a, chrome136)
       x[1] not in _DEPRIORITIZED_TARGETS,
       # 2. 降级移动端目标 (iOS/Android)，避免服务端返回移动版排版或跳转 App Store
       x[1].os not in ('ios', 'android'),
       # 3. 浏览器权重序列: tor < edge < firefox < safari < chrome (优先选用 Chrome 桌面端)
       ('tor', 'edge', 'firefox', 'safari', 'chrome').index(x[1].client),
       # 4. 优先选用更新的浏览器版本号 (Version Tuple 倒序)
       version_tuple(x[1].version or '0'),
       # 5. 按操作系统名称分组 (macOS / Windows)
       x[1].os,
   )

---
应用层请求头联动与 Client Hints 注入
---

单纯伪造 TLS 握手特征而不同步 HTTP 请求头，将导致 WAF 判定为 **“协议层与应用层特征不一致”** 从而触发高危拦截。

``ImpersonateRequestHandler._get_impersonate_headers()`` 构建了清洗与联动机制：

.. code-block:: text
   :caption: 应用层请求头清洗与 Client Hints 注入流向

   提取器传入的原始 headers
              |
              v
   [1. 剥离 Python 标准库默认头] ---> 剔除 std_headers (如 Python 自带的 User-Agent)
              |
              v
   [2. 注入目标浏览器原生 UA]   ---> 注入与 ImpersonateTarget 严格一致的 User-Agent 字符串
              |
              v
   [3. 注入现代 Client Hints]   ---> 注入 Sec-CH-UA, Sec-CH-UA-Mobile, Sec-CH-UA-Platform
              |
              v
   [4. 注入标准 Fetch 元数据]   ---> 注入 Sec-Fetch-Dest, Sec-Fetch-Mode, Sec-Fetch-Site
              |
              v
   [5. 字符大小写保护]         ---> 若声明 keep_header_casing，通过 sensitive() 保持原始大小写

---
端到端指纹伪装时序图与行级源码映射
---

.. code-block:: text
   :caption: 浏览器指纹伪装端到端调用时序

   Extractor (e.g. YoutubeIE)     RequestDirector          CurlCFFIRH               libcurl-impersonate (C/BoringSSL)
              |                          |                       |                                   |
              |-- Request(impersonate) ->|                       |                                   |
              |                          |-- _get_handlers() --->| (打分: +1000 绝对优先)            |
              |                          |-- validate() -------->| (解析并匹配 ImpersonateTarget)    |
              |                          |-- send(request) ----->|                                   |
              |                          |                       |-- _get_impersonate_headers() ---->| (清洗并同步 Client Hints)
              |                          |                       |-- session.request(impersonate) ->|
              |                          |                       |                                   |-- 组装 Client Hello (Ciphers/Extensions/GREASE)
              |                          |                       |                                   |-- TLS 1.3 握手协商 (ALPN: h2)
              |                          |                       |                                   |-- 发送 HTTP/2 SETTINGS 帧
              |                          |                       |                                   |-- 发送 GET / POST 请求帧
              |                          |                       |<-- curl_cffi.Response ------------|<-- 接收 HTTP/2 DATA 帧
              |<-- ResponseAdapter ------|<-- ResponseAdapter ---|

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 浏览器指纹伪装核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 结构
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``ImpersonateTarget``
     - ``yt_dlp/networking/impersonate.py:12-48``
     - 伪装目标不可变数据类、DSL 解析与 ``__contains__`` 模糊匹配
   * - ``ImpersonateRequestHandler``
     - ``yt_dlp/networking/impersonate.py:50-120``
     - 伪装基类抽象、Target 解析路由、应用层请求头与 Client Hints 同步
   * - ``BROWSER_TARGETS``
     - ``yt_dlp/networking/_curlcffi.py:80-165``
     - 跨版本浏览器指纹拓扑表（Chrome/Safari/Firefox/Edge/Tor）
   * - ``CurlCFFIRH``
     - ``yt_dlp/networking/_curlcffi.py:170-275``
     - libcurl-impersonate C 接口绑定、低速超时控制与 TLS 错误捕获
   * - ``_SUPPORTED_IMPERSONATE_TARGET_MAP``
     - ``yt_dlp/networking/_curlcffi.py:175-200``
     - 启发式权重排序管道（排除黑名单、桌面端优先、版本倒序）

***
小结与下章导读
***

本节系统剖析了 ``yt-dlp`` 浏览器指纹伪装与 TLS 模拟引擎的底层机理，厘清了：
1. 反爬网关在 L4/L7（TLS Client Hello / HTTP/2 Framing）的特征检测原理；
2. ``ImpersonateTarget`` 的 DSL 语法与模糊匹配拓扑；
3. ``libcurl-impersonate`` 对密码套件、扩展顺序、GREASE 与后量子密钥交换的重构；
4. 启发式多维权重排序算法对最优伪装目标的自适应决议。

在下一节（``03_cookiejar_and_session_management.rst``）中，我们将探讨网络层的凭证与会话中枢——深度剖析 ``CookieJar`` 架构，解密本地浏览器（Chrome、Firefox、Safari、Edge 等）基于 DPAPI、Keychain 与 SecretStorage 的凭证解密提取技术及跨域作用域安全隔离机制。
