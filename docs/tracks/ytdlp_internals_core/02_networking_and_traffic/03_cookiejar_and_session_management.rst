========================================================================================
02.03 CookieJar 多浏览器凭证解密提取与安全跨域作用域隔离
========================================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们剖析了 ``RequestDirector`` 的调度架构以及基于 ``ImpersonateTarget`` 的 TLS / HTTP2 指纹模拟技术。然而，在现代流媒体服务中，高画质码率（如 4K/8K/HDR）、会员专享内容、年龄限制视频以及私有订阅列表，均强依赖用户登录会话（Session Cookies）。手动导出 Cookie 文本文件不仅繁琐且极易失效。``yt-dlp`` 构建了一套直接读取宿主机各类主流浏览器本地加密数据库并实时解密凭证的 ``CookieJar`` 引擎，同时设计了严格的跨域作用域隔离机制以防范凭证泄漏（GHSA-v8mc-9377-rwjj）。本节将全面解构多平台密钥环解密算法、二进制 Cookie 解析器与会话管理模型。

***
流媒体凭证体系与多浏览器存储拓扑
***

现代浏览器为了保护用户的身份凭证不被恶意进程窃取，普遍采用 **“操作系统级安全密钥环（OS Keyring）加密 + 本地 SQLite/二进制文件存储”** 的防御架构。

.. code-block:: text
   :caption: 多浏览器 Cookie 存储与解密分发矩阵

                              load_cookies()
                                    |
            +-----------------------+-----------------------+
            |                                               |
     --cookies 文件 (Netscape)                   --cookies-from-browser
            |                                               |
            v                                               v
   YoutubeDLCookieJar                       _parse_browser_specification()
   (7 字段 TSV 格式解析与会话修复)                            |
                                    +-----------------------+-----------------------+
                                    |                       |                       |
                              Chromium 内核              Firefox                  Safari
                           (Chrome/Edge/Brave)              |                       |
                                    |                       v                       v
                                    |                moz_cookies.sqlite     Cookies.binarycookies
                                    |                (PRAGMA 版本适配 &      (自研二进制字节流
                                    |                 多容器上下文隔离)       状态机解析器)
                                    v
                     +------------------------------+
                     | 操作系统安全密钥解密 (OS Key) |
                     +--------------+---------------+
                                    |
            +-----------------------+-----------------------+
            |                       |                       |
      Windows (DPAPI)        macOS (Keychain)        Linux (SecretStorage /
     (CryptUnprotectData    (PBKDF2-HMAC-SHA1       KWallet DBus / BasicText)
      + AES-256-GCM)         1003次迭代 + AES-CBC)   (PBKDF2-HMAC-SHA1 1次迭代)

浏览器底层存储路径与特征矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 主流浏览器 Cookie 存储媒介与加密特征
   :widths: 16 26 28 30
   :header-rows: 1

   * - 浏览器体系
     - 默认存储路径
     - 数据库格式 / 载荷
     - 加密机制与保护级别
   * - Chromium 家族 (Windows)
     - ``%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies``
     - SQLite3 (``cookies`` 表)
     - ``Local State`` 存储经 DPAPI 加密的 Master Key；字段采用 AES-256-GCM (``v10``)
   * - Chromium 家族 (macOS)
     - ``~/Library/Application Support/Google/Chrome/Default/Cookies``
     - SQLite3 (``cookies`` 表)
     - 登录 Keychain 提取安全存储密码；PBKDF2 派生密钥；字段采用 AES-128-CBC (``v10``)
   * - Chromium 家族 (Linux)
     - ``~/.config/google-chrome/Default/Cookies``
     - SQLite3 (``cookies`` 表)
     - DBus 探测 GNOME Keyring / KWallet；PBKDF2 派生；字段采用 AES-128-CBC (``v10``/``v11``)
   * - Mozilla Firefox
     - ``~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite``
     - SQLite3 (``moz_cookies`` 表)
     - 凭证未对字段进行对称加密，依赖 OS 文件系统权限保护；支持多账号容器
   * - Apple Safari
     - ``~/Library/Cookies/Cookies.binarycookies``
     - 专有二进制文件 (Binary Cookies)
     - 专有二进制分页格式；时间戳基于 Mac 纪元（2001-01-01）

---
三端 OS 安全密钥解密流水线
---

``yt_dlp/cookies.py`` 实现了跨平台的底层解密器抽象体系（``ChromeCookieDecryptor``）。

1. Windows 端 DPAPI 与 AES-256-GCM 解密
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Windows 系统上，Chromium（Chrome 80+）引入了新型的混合加密模型：

1. **主密钥提取**：解析 ``User Data/Local State`` JSON 文件中的 ``os_crypt.encrypted_key``，剔除前缀 ``b'DPAPI'``；
2. **DPAPI 解密**：通过 ``ctypes.windll.crypt32.CryptUnprotectData`` 调用系统级数据保护 API，使用当前登录用户的 Windows 凭据解密出 256 位 AES 主密钥；
3. **字段解密**：针对数据库中以 ``b'v10'`` 开头的 ``encrypted_value``，截取 12 字节 Nonce（IV）、中间的 Ciphertext 以及末尾 16 字节的 Authentication Tag，调用 ``aes_gcm_decrypt_and_verify_bytes`` 完成认证解密。

2. macOS 端 Keychain 与 PBKDF2-AES-CBC 解密
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 macOS 上，Chromium 将固定服务名注册于系统 Keychain：

1. **密码获取**：调用系统安全工具 ``security find-generic-password -w -a Chrome -s "Chrome Safe Storage"``；
2. **密钥派生**：采用 PBKDF2-HMAC-SHA1 算法进行 **1003 次哈希迭代**，盐值为固定字符串 ``b'saltysalt'``，派生出 16 字节（128 位）AES 密钥；
3. **CBC 模式解密与哈希裁剪**：使用固定 IV（16 个空格 ``b' ' * 16``）执行 AES-128-CBC 解密并剥离 PKCS#7 填充。若 SQLite 元数据版本 ``meta_version >= 24``，解密后前 32 字节为哈希校验头，需予以截断保留后续真实明文。

3. Linux 端桌面环境探测与 Keyring 适配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Linux 桌面环境碎片化严重，``yt-dlp`` 实现了自动桌面环境识别引擎（``_get_linux_desktop_environment``）：

* **KDE Plasma (KDE4/5/6)**：通过 DBus 调用 ``org.kde.KWallet.networkWallet`` 获取网络钱包名称，随后调用 ``kwallet-query`` 提取安全存储密码；
* **GNOME / XFCE / Unity**：通过 ``secretstorage`` 库与系统 Secret Service DBus 接口通信，遍历集合检索标签为 ``"<Browser> Safe Storage"`` 的条目；
* **BasicText 模式**：若未检测到 Keyring 服务，降级使用内置默认密码 ``b'peanuts'`` 或空密码派生密钥；
* **单次迭代派生**：Linux 规范仅执行 **1 次 PBKDF2 迭代**，显著区别于 macOS 的 1003 次迭代。

---
Firefox 与 Safari 特殊存储格式解析引擎
---

1. Firefox 多账号容器与 SQLite Schema 演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Firefox 凭证提取核心逻辑位于 ``_extract_firefox_cookies``：

* **并发锁定绕过 (`_open_database_copy`)**：Firefox 运行时会对 ``cookies.sqlite`` 施加独占写锁。引擎在系统临时目录中创建数据库副本，确保在浏览器处于活动状态时无阻碍读取；
* **数据库 Schema 跨版本兼容**：Firefox 142 将数据库升级至 Schema Version 16，将 ``expiry`` 时间戳字段从秒级变更为毫秒级。引擎通过 ``PRAGMA user_version`` 自动探测并在命中高版本时执行 ``expiry /= 1000``；
* **多账号容器（Multi-Account Containers）精确隔离**：解析 ``containers.json``，将用户指定的容器名（如 ``--cookies-from-browser firefox::work``）转换为 ``userContextId``，并通过 SQL 条件精准过滤：

.. code-block:: sql

   SELECT host, name, value, path, expiry, isSecure 
   FROM moz_cookies 
   WHERE originAttributes LIKE '%userContextId=1' OR originAttributes LIKE '%userContextId=1&%'

2. Safari BinaryCookies 字节流解析状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Safari 将全部 Cookie 紧凑序列化为单个二进制文件。``DataParser`` 实现了针对其私有格式的逆向解包状态机：

.. code-block:: text
   :caption: Safari BinaryCookies 二进制文件结构拓扑

   +-------------------------------------------------------------------+
   | File Header: 4 bytes Magic (b'cook')                              |
   | Number of Pages: 4 bytes (Big-Endian uint32)                      |
   | Page Sizes Table: N * 4 bytes (Big-Endian uint32)                 |
   +-------------------------------------------------------------------+
   | Page 0:                                                           |
   |   - Page Header: 4 bytes Magic (b'\x00\x00\x01\x00')              |
   |   - Number of Cookies: 4 bytes (Little-Endian uint32)             |
   |   - Cookie Offsets Table: M * 4 bytes (Little-Endian uint32)      |
   |   +-------------------------------------------------------------+ |
   |   | Cookie Record 0:                                            | |
   |   |   - Record Size: 4 bytes                                    | |
   |   |   - Flags: 4 bytes (0x0001: isSecure, 0x0004: httpOnly)     | |
   |   |   - Offsets: domain_off, name_off, path_off, value_off      | |
   |   |   - Expiration / Creation: 8 bytes Float64 (Mac Epoch)      | |
   |   |   - Null-terminated C-Strings (Domain, Name, Path, Value)   | |
   |   +-------------------------------------------------------------+ |
   +-------------------------------------------------------------------+

解析器通过 ``_mac_absolute_time_to_posix`` 算法：

.. code-block:: python

   def _mac_absolute_time_to_posix(timestamp):
       return int((dt.datetime(2001, 1, 1, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=timestamp)).timestamp())

将以 ``2001-01-01 00:00:00 UTC`` 为基准的 Mac 绝对时间戳精确换算为标准 UNIX 时间戳。

---
Netscape 规范持久化与 Session Cookie 智能推导
---

``YoutubeDLCookieJar`` 继承并重写了 Python 标准库的 ``http.cookiejar.MozillaCookieJar``。

Netscape 7 字段 TSV 格式标准
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

所有导出的 Cookie 文本均严格遵循 Netscape 格式：

.. code-block:: text

   # domain  include_subdomains  path  https_only  expires_at  name  value
   .youtube.com  TRUE  /  TRUE  1780000000  LOGIN_INFO  AFmmF2cwRQIhA...

* **``#HttpOnly_`` 前缀**：当 Cookie 标记为 HttpOnly 时，在行首添加 ``#HttpOnly_`` 注释前缀，兼顾标准兼容性与客户端解析能力；
* **会话 Cookie（Session Cookie）保活机制**：标准 ``MozillaCookieJar`` 在保存和读取时默认丢弃无过期时间的临时会话 Cookie。然而在流媒体场景中，用户未勾选“记住我”时的核心鉴权凭证（如 ``SSID``, ``SID``）往往作为会话 Cookie 存在。``YoutubeDLCookieJar`` 在持久化时将 ``expires=None`` 强制写为 ``0``，并在重新加载时将 ``expires=0`` 还原为内存中的有效会话 Cookie，确保认证状态不丢失。

宽容度解析器 (LenientSimpleCookie)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准 Python 库的 ``http.cookies.SimpleCookie`` 在遇到非标准字符（如非法未转义分号、控制字符）时会直接抛出 ``CookieError`` 异常中断流程。``LenientSimpleCookie`` 扩展了正则分词规则，在遇到畸形属性时自动跳过无效字段并保留核心鉴权键值，极大增强了网络容错韧性。

---
跨域作用域隔离与凭证防泄漏安全沙箱 (GHSA-v8mc-9377-rwjj)
---

在复杂的视频提取场景中，主视频页面可能托管于目标网站，而媒体分片流或第三方跟踪器托管于外部 CDN 或嵌入式域名。如果网络请求层无差别地将主站 Cookie 附加到所有发出的 HTTP 请求中，攻击者可通过恶意构造的第三方重定向链接轻松窃取用户的会话凭证。

``yt-dlp`` 构建了严格的 **基于 URL 的动态作用域安全沙箱**：

.. code-block:: text
   :caption: Cookie 安全跨域作用域隔离流向

   提取器返回包含未限定作用域 Cookie 的 HTTP 响应头
                           |
                           v
   +-------------------------------------------------------------------+
   | 1. 入口拦截与作用域注入 (_load_cookies)                           |
   |    - 检测 Cookie 是否缺失 Domain 属性                             |
   |    - 若缺失，强制将其 Domain 锁定为当前请求主机的子域 (.domain)    |
   |    - 拒绝向全局发送 Unscoped Cookies                              |
   +-------------------------------+-----------------------------------+
                                   |
                                   v
   +-------------------------------------------------------------------+
   | 2. 请求发出前动态提取匹配 (_calc_headers)                         |
   |    - 剥离静态 headers 中的全局 Cookie                             |
   |    - 调用 cookiejar.get_cookies_for_url(target_url)               |
   |    - 仅提取与 target_url 的 Domain、Path、Secure 匹配的凭证        |
   |    - 动态拼接为当前请求专用的 'Cookie' 请求头                     |
   +-------------------------------------------------------------------+

---
端到端凭证装载时序图与行级源码映射
---

.. code-block:: text
   :caption: 凭证提取与请求注入端到端调用时序

   CLI Option (--cookies-from-browser)   YoutubeDL.__init__()     extract_cookies_from_browser()     CookieDecryptor (OS)       RequestDirector
               |                                 |                             |                                  |                    |
               |-- load_cookies() -------------->|                             |                                  |                    |
               |                                 |-- extract_chrome_cookies()->|                                  |                    |
               |                                 |                             |-- _open_database_copy() (SQLite) |                    |
               |                                 |                             |-- get_cookie_decryptor() ------->|                    |
               |                                 |                             |                                  |-- 获取 OS Keyring  |
               |                                 |                             |                                  |-- 派生 AES 密钥    |
               |                                 |                             |<-- 解密后的 Cookie 键值对 -------|<-- AES-GCM / CBC   |
               |                                 |<-- YoutubeDLCookieJar ------|                                                       |
               |                                 |                                                                                     |
               |-- extract_info(url) ----------->|                                                                                     |
               |                                 |-- _calc_headers(url) (依据域名安全筛选 Cookie) ------------------------------------>|
               |                                 |-- urlopen(Request(headers=scoped_cookies)) ---------------------------------------->| 发起安全请求

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: Cookie 引擎核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``load_cookies()``
     - ``yt_dlp/cookies.py:65-90``
     - 凭证加载总入口、多源 CookieJar 合并与异常捕获
   * - ``_extract_chrome_cookies()``
     - ``yt_dlp/cookies.py:165-245``
     - Chromium SQLite 临时副本复制、版本元数据探测与迭代解密
   * - ``WindowsChromeCookieDecryptor``
     - ``yt_dlp/cookies.py:345-385``
     - ``Local State`` 解析、Win32 DPAPI 解密与 AES-256-GCM 认证解密
   * - ``MacChromeCookieDecryptor``
     - ``yt_dlp/cookies.py:320-344``
     - Keychain 密码读取、PBKDF2 1003 次迭代派生与 AES-CBC 模式解密
   * - ``LinuxChromeCookieDecryptor``
     - ``yt_dlp/cookies.py:270-318``
     - 桌面环境探测、KWallet / SecretStorage DBus 交互与 AES 解密
   * - ``parse_safari_cookies()``
     - ``yt_dlp/cookies.py:465-495``
     - ``Cookies.binarycookies`` 二进制状态机解析与 Mac 纪元时间戳转换
   * - ``_extract_firefox_cookies()``
     - ``yt_dlp/cookies.py:95-155``
     - SQLite Schema 16 毫秒转换与 ``containers.json`` 容器隔离过滤
   * - ``YoutubeDLCookieJar``
     - ``yt_dlp/cookies.py:730-840``
     - Netscape 7 字段 TSV 格式序列化、会话 Cookie 保活与 URL 作用域过滤

***
小结与下章导读
***

本节系统剖析了 ``yt-dlp`` 的 Cookie 凭证提取与会话管理中枢，厘清了：
1. Chromium 家族在 Windows、macOS 与 Linux 三大操作系统上的底层密钥环解密与对称密码学实现；
2. Firefox 多账号容器与 Safari 专有二进制 Cookie 文件的逆向解析算法；
3. ``YoutubeDLCookieJar`` 对 Netscape 规范的扩展与会话 Cookie 的生命周期保活；
4. 基于 URL 的动态作用域安全沙箱（GHSA-v8mc-9377-rwjj）如何严密防范跨域凭证泄漏。

在下一节（``04_proxy_and_geo_bypass.rst``）中，我们将深入网络流量调度的最后一环——剖析智能代理池架构、SOCKS5 传输层穿透、X-Forwarded-For 地理围栏突破以及网络故障指数退避重试算法。
