========================================================================================
02.04 智能代理池、X-Forwarded-For 地理欺骗与网络故障指数退避重试算法
========================================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们全面解构了 ``RequestDirector`` 的多后端分发模型、基于 ``curl_cffi`` 的浏览器 TLS/HTTP2 指纹模拟以及跨平台的 ``CookieJar`` 凭证解密提取机制。然而，在面对严格的跨国地理区域限制（Geo-blocking）、IP 封禁、CDN 频次限流（Rate Limiting）以及弱网丢包抖动时，流媒体下载引擎必须具备强大的流量路由调度与故障容灾自愈能力。本节将深入解剖 ``yt-dlp`` 的代理协议栈选择器、自研零依赖 SOCKS 协议栈状态机、基于 ``GeoUtils`` 的 ``X-Forwarded-For`` 伪装算法，以及基于 ``RetryManager`` 的指数退避抖动重试模型。

***
代理协议栈调度架构与统一选择器
***

在分布式采集与复杂网络拓扑中，代理配置可能来源于全局 CLI 参数、环境变量、配置文件、或是特定提取器针对子域名的动态覆盖。``yt-dlp`` 通过 ``clean_proxies`` 与 ``select_proxy`` 构建了确定性的分层优先级决议体系。

.. code-block:: text
   :caption: 代理配置优先级覆盖与选择流向

   +-------------------------------------------------------------------+
   | 优先级 1: 请求级强制代理 (headers['Ytdl-Request-Proxy'])          |
   |           最高优先级，强行覆盖所有下层规则 (包括 NO_PROXY)        |
   +---------------------------------+---------------------------------+
                                     |
                                     v 未指定
   +-------------------------------------------------------------------+
   | 优先级 2: 细粒度协议映射 (Request.proxies[scheme] / ydl.proxies)   |
   |           区分 http, https, ftp, all 以及 no (白名单规则)         |
   +---------------------------------+---------------------------------+
                                     |
                                     v 未指定
   +-------------------------------------------------------------------+
   | 优先级 3: 操作系统环境变量 (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY)    |
   +-------------------------------------------------------------------+
                                     |
                                     v 提取目标 URL
   +-------------------------------------------------------------------+
   | 4. 统一选择器决议 (select_proxy)                                   |
   |    - 检查 no_proxy 规则 (proxy_bypass_environment / proxy_bypass) |
   |    - 命中白名单则返回 None (直连)                                 |
   |    - 否则提取对应协议代理或 'all' 兜底代理                        |
   +-------------------------------------------------------------------+

SOCKS5 vs SOCKS5H 远端 DNS 强制规范化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在常规网络请求库中，``socks5://`` 往往意味着“由客户端本地解析 DNS 后将目标 IP 发送给代理服务器”，这会导致严重的 **DNS 污染** 以及客户端真实地理位置的 **DNS 泄漏**。

``clean_proxies`` 在初始化阶段执行了强制规范化重写：

.. code-block:: python

   replace_scheme = {
       'socks5': 'socks5h',  # 强制将 socks5 提升为 socks5h (远端 DNS 解析)
       'socks': 'socks4',    # 向后兼容映射
   }
   if proxy_scheme in replace_scheme:
       proxies[proxy_key] = urllib.parse.urlunparse(
           urllib.parse.urlparse(proxy_url)._replace(scheme=replace_scheme[proxy_scheme]))

通过将所有 SOCKS5 代理无缝提升为 ``socks5h``，域名解析工作被严格限定在远端代理节点执行，彻底切断了本地 DNS 泄露途径。

---
自研轻量级 SOCKS 协议栈状态机实现
---

为了在标准库 ``UrllibRH`` 及 ``WebsocketsRH`` 中实现对 SOCKS 代理的零依赖原生支持，``yt-dlp`` 在 ``yt_dlp/socks.py`` 中内置了完整的 SOCKS4 / SOCKS4A / SOCKS5 客户端协议栈（``sockssocket``），彻底摆脱了对外部第三方库（如 ``PySocks``）的依赖。

.. list-table:: SOCKS 协议族支持矩阵与握手特征
   :widths: 18 20 32 30
   :header-rows: 1

   * - 协议版本
     - 认证支持
     - 目标地址寻址方式
     - 典型握手报文结构
   * - ``SOCKS4``
     - 仅 User ID (无密码)
     - 仅 IPv4 (4 字节)
     - ``\x04\x01<Port:2B><IPv4:4B><User>\x00``
   * - ``SOCKS4A``
     - 仅 User ID
     - 远端域名解析 (DSTIP 设为 ``0.0.0.255``)
     - ``\x04\x01\x00\x00\x00\xff<User>\x00<Domain>\x00``
   * - ``SOCKS5``
     - 无认证 / 用户名密码
     - IPv4 (0x01) / IPv6 (0x04)
     - 协商方法 $\rightarrow$ 认证 $\rightarrow$ ``\x05\x01\x00<ATYP><Addr><Port>``
   * - ``SOCKS5h``
     - 无认证 / 用户名密码
     - 远端域名寻址 (ATYP: 0x03)
     - 携带 1 字节变长长度前缀的 Domain Name 字节流

SOCKS5 双阶段握手与认证状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text
   :caption: SOCKS5 客户端握手状态机流向

   客户端 (sockssocket)                                         SOCKS5 代理服务器
           |                                                           |
           |-- 1. 方法协商: [0x05, N_METHODS, AUTH_NONE, USER_PASS] -->|
           |<-- 2. 选择方法: [0x05, SELECTED_METHOD] -------------------|
           |                                                           |
      [若 SELECTED_METHOD == 0x02 (USER_PASS)]                         |
           |-- 3. 鉴权请求: [0x01, USER_LEN, USER, PASS_LEN, PASS] --->|
           |<-- 4. 鉴权响应: [0x01, STATUS] (0x00 为成功) --------------|
           |                                                           |
      [建立连接请求 (CMD_CONNECT: 0x01)]                               |
           |-- 5. CONNECT: [0x05, 0x01, 0x00, ATYP, ADDR, PORT] ------>|
           |      (若远端解析: ATYP=0x03, ADDR=[LEN, domain])          |
           |<-- 6. CONNECT 响应: [0x05, REP_CODE, 0x00, BND_ADDR, PORT]|
           |                                                           |
      [握手完成，进入 TCP 原始透明传输管道]

在 ``sockssocket._setup_socks5`` 中，当目标地址属于未解析域名时，引擎设置 ``ATYP = Socks5AddressType.ATYP_DOMAINNAME (0x03)``，并打包 ``len(destaddr) + destaddr``，由代理网关完成目标解析与连接建立。

---
地理围栏对抗：X-Forwarded-For 伪造与 GeoUtils 算法
---

许多流媒体服务（如某些区域性电视台、BBC iPlayer 早期版本、日本门户网站）基于客户端请求头中的代理链信息来判定用户所在的物理地域。如果请求携带合法目标国家的 IP 伪装头，服务网关将跳过严格的底层 TCP IP 审查。

.. code-block:: text
   :caption: X-Forwarded-For 地理伪装注入模型

   YoutubeDL.extract_info()
             |
             v 启用 --geo-bypass 或 --geo-bypass-country JP
   +-------------------------------------------------------------------+
   | 1. GeoUtils.random_ipv4('JP')                                     |
   |    - 查询 _country_ip_map['JP'] 获取 CIDR 块: '133.0.0.0/8'       |
   |    - struct.unpack 计算 addr_min 与 addr_max                      |
   |    - random.randint 生成范围内随机 IP (如 133.242.18.91)          |
   +---------------------------------+---------------------------------+
                                     |
                                     v
   +-------------------------------------------------------------------+
   | 2. 注入 InfoDict: info['__x_forwarded_for_ip'] = '133.242.18.91'  |
   +---------------------------------+---------------------------------+
                                     |
                                     v
   +-------------------------------------------------------------------+
   | 3. 请求构建前同步至 HTTP 请求头                                   |
   |    headers['X-Forwarded-For'] = '133.242.18.91'                   |
   +-------------------------------------------------------------------+

GeoUtils CIDR 子网随机 IP 生成算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``yt-dlp/utils/_utils.py`` 内置了全球 200 多个国家/地区的代表性 IPv4 CIDR 映射表（``_country_ip_map``）。随机生成算法具备严密的位运算拓扑：

.. code-block:: python

   @classmethod
   def random_ipv4(cls, code_or_block):
       if len(code_or_block) == 2:
           block = cls._country_ip_map.get(code_or_block.upper())
           if not block:
               return None
       else:
           block = code_or_block
       addr, preflen = block.split('/')
       addr_min = struct.unpack('!L', socket.inet_aton(addr))[0]
       # 计算网络广播掩码，生成最大地址边界
       addr_max = addr_min | (0xffffffff >> int(preflen))
       # 在子网有效地址空间内均匀随机采样
       return str(socket.inet_ntoa(
           struct.pack('!L', random.randint(addr_min, addr_max))))

分流控制：地理验证代理 (`--geo-verification-proxy`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在商业对抗场景中，高质量境外代理往往流量昂贵或带宽受限。``yt-dlp`` 提供了精细化的分流机制：
* **元数据验证阶段**：仅在提取器探测媒体可用性或解析地域授权令牌时，使用 ``--geo-verification-proxy`` 指定的代理进行地理穿透；
* **物理分片下载阶段**：主媒体分片（CDN 数据流通常不校验 IP 归属，只校验 URL 签名）自动回退至高速直连网络，实现带宽成本与翻墙能力的最佳平衡。

---
网络故障自适应重试与指数退避抖动模型 (RetryManager)
---

流媒体下载过程经常遭遇暂时性网络中断、TCP RST 重置、HTTP 429 请求过多以及 HTTP 503 服务不可用。简单的定频重试极易造成服务器负载雪崩（惊群效应，Thundering Herd Problem）。

``yt_dlp/utils/_utils.py`` 实现了通用的迭代器状态机 ``RetryManager``：

.. code-block:: python

   class RetryManager:
       def __init__(self, _retries, _error_callback, **kwargs):
           self.retries = _retries or 0
           self.error_callback = functools.partial(_error_callback, **kwargs)

       def _should_retry(self):
           return self._error is not NO_DEFAULT and self.attempt <= self.retries

       def __iter__(self):
           while self._should_retry():
               self.error = NO_DEFAULT
               self.attempt += 1
               yield self
               if self.error:
                   self.error_callback(self.error, self.attempt, self.retries)

指数退避与全抖动（Full Jitter Backoff）算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

系统支持通过 ``retry_sleep_functions`` 为四大独立场景（``http``、``fragment``、``file_access``、``extractor``）配置动态休眠函数：

.. code-block:: text
   :caption: 重试休眠退避算法数学模型

   设重试次数为 n (0 <= n < retries)，基准退避时间为 T_base，最大休眠上限为 T_max:
   
   1. 纯指数退避 (Exponential Backoff):
      T_exp = min(T_max, T_base * 2^n)
      
   2. 全抖动退避 (Full Jitter Backoff):
      Sleep_Time = Uniform_Random(0, T_exp)
      
   3. 防风控均匀随机间隔 (Request Throttling):
      Sleep_Time = Uniform_Random(sleep_interval, max_sleep_interval)

在重试回调 ``report_retry`` 中，系统自动捕获 ``ExtractorError`` 或底层传输异常，计算当前尝试次数并执行高精度浮点休眠，打印友好的重试倒计时进度，确保在大规模批量抓取时具备最高韧性。

---
端到端代理与重试调用时序与源码映射
---

.. code-block:: text
   :caption: 代理分发、地理伪装与重试恢复端到端时序

   Extractor                      YoutubeDL                   RequestDirector              sockssocket (SOCKS)
       |                              |                              |                              |
       |-- 开启 geo_bypass ---------->|                              |                              |
       |                              |-- GeoUtils.random_ipv4()     |                              |
       |                              |-- 注入 X-Forwarded-For 头    |                              |
       |                              |                              |                              |
       |-- urlopen(Request) --------->|-- send(Request) ------------>|                              |
       |                              |                              |-- select_proxy(url) -------->| (解析 socks5h)
       |                              |                              |-- connect() ---------------->|-- SOCKS5 握手认证
       |                              |                              |                              |-- 远端域名解析
       |                              |                              |<-- 发生网络波动 (503/Timeout)|<-- 连接中断
       |                              |                              |                              |
       |                              |<-- 抛出 TransportError ------|                              |
       |                              |                                                             |
       |<-- 触发 RetryManager ------->|-- report_retry() -> 计算 Jitter Delay -> time.sleep() ------|
       |    (重新发起第 2 次尝试)     |-- 重新建立代理通道与 HTTP 传输 (请求成功 200 OK) ---------->|

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 代理与网络容灾核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``select_proxy()``
     - ``yt_dlp/utils/networking.py:165-185``
     - 统一代理选择器：评估白名单（``no_proxy``）与分协议路由决议
   * - ``clean_proxies()``
     - ``yt_dlp/utils/networking.py:120-150``
     - 代理配置规范化：``socks5`` 强制升级 ``socks5h`` 杜绝 DNS 泄漏
   * - ``sockssocket``
     - ``yt_dlp/socks.py:75-210``
     - 纯 Python 零依赖 SOCKS4/4A/5/5H 完整客户端协议栈实现
   * - ``GeoUtils``
     - ``yt_dlp/utils/_utils.py:640-780``
     - 全球 200+ 国家 CIDR IP 字典与高精度随机 IPv4 位运算生成器
   * - ``RetryManager``
     - ``yt_dlp/utils/_utils.py:120-155``
     - 迭代器模式网络异常重试状态机与退避休眠回调调度
   * - ``_make_socks_conn_class()``
     - ``yt_dlp/networking/_urllib.py:85-110``
     - 传输层 Socket 动态重写，无缝注入 SOCKS 代理隧道

***
小结与下章导读
***

至此，我们完整解析了 **第 2 模块：网络请求层与协议栈适配** 的全部核心技术基石：
1. ``02.01`` 中 ``RequestDirector`` 的统一调度中枢与多后端分发矩阵；
2. ``02.02`` 中基于 ``ImpersonateTarget`` 的 TLS Client Hello / JA3 / JA4 与 HTTP/2 帧层指纹伪装；
3. ``02.03`` 中三端 OS 安全密钥环解密与基于 URL 的 Cookie 安全跨域隔离沙箱；
4. ``02.04`` 中智能代理选择器、原生 SOCKS5 协议栈、地理欺骗与指数退避重试模型。

在接下来的 **第 3 模块：InfoExtractor 抽象与解析流水线 (03_extractor_framework_and_pipeline)** 中，我们将深入 ``yt-dlp`` 最庞大的业务基石——剖析 1000+ 个网站提取器的基类抽象架构 ``InfoExtractor``，解密双向绑定机制、``_real_extract`` 设计范式与微数据抽取引擎。
