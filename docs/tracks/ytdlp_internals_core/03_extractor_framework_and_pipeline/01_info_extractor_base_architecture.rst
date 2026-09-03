========================================================================================
03.01 InfoExtractor 基类抽象、双向绑定机制与 _real_extract 核心范式
========================================================================================

.. note:: 前置背景与上下文承接
   在前两个模块中，我们深入剖析了 ``yt-dlp`` 的顶层控制器生命周期与底层网络协议栈（``RequestDirector``、浏览器指纹伪装、CookieJar 凭证解密与代理调度）。然而，流媒体下载引擎最庞大、最复杂的业务层，在于如何将成千上万个结构各异的音视频网站（YouTube、Bilibili、TikTok、Vimeo、Twitter、Twitch 等）的异构网页与 API 响应，统一抽象为标准化的多媒体信息图谱。``InfoExtractor`` 基类是整个提取器生态的基石与核心中枢。本节将深度解构 ``InfoExtractor`` 的类层次设计、类属性元编程、与 ``YoutubeDL`` 的双向绑定机制、生命周期执行状态机以及 ``_real_extract`` 设计范式。

***
InfoExtractor 核心类层次与元编程模型
***

``InfoExtractor`` 定义了统一的信息提取协议。所有针对特定站点的解析器（如 ``YoutubeIE``、``BiliBiliIE``）均直接或间接继承自该基类。

.. code-block:: text
   :caption: InfoExtractor 继承与插件派生拓扑

                           InfoExtractor (基类)
                                    |
            +-----------------------+-----------------------+
            |                       |                       |
   SearchInfoExtractor      UnsupportedURLIE         具体站点提取器
   (搜索 DSL 抽象基类)      (不支持链接降级兜底)    (如 YoutubeIE, BiliBiliIE)
                                                            |
                                                            v
                                                  __init_subclass__ 注入
                                                (第三方插件覆写与运行时挂载)

核心类属性与路由元数据规范
~~~~~~~~~~~~~~~~~~~~~~~~~~

一个合规的 ``InfoExtractor`` 子类通过声明一组静态类属性，向调度引擎注册其路由规则与安全策略：

.. list-table:: InfoExtractor 核心静态属性与行为语义
   :widths: 22 28 50
   :header-rows: 1

   * - 类属性名称
     - 类型规范
     - 行为语义与引擎控制逻辑
   * - ``_VALID_URL``
     - ``str`` 或 ``tuple[str, ...]`` 或 ``False``
     - 核心路由正则。必须包含 ``(?P<id>...)`` 命名捕获组；声明为 ``False`` 时表示仅用于嵌入式提取（Embed-only）
   * - ``_EMBED_REGEX``
     - ``list[str]``
     - 嵌入正则列表。供 ``GenericIE`` 在第三方宿主网页中扫描嵌套视频时调用
   * - ``_TESTS`` / ``_TEST``
     - ``list[dict]`` / ``dict``
     - 回归测试用例集。驱动单元测试，并由 ``age_limit`` 描述符反向推导内容分级
   * - ``_GEO_BYPASS``
     - ``bool`` (默认 ``True``)
     - 是否针对该提取器启用基于 ``X-Forwarded-For`` 的动态地理伪装
   * - ``_GEO_COUNTRIES``
     - ``list[str]`` (如 ``['US', 'JP']``)
     - 该站点已知不受限的国家 ISO 代码列表，供地理伪装引擎优先采样
   * - ``_NETRC_MACHINE``
     - ``str`` (如 ``'youtube'``)
     - 认证域名标识。用于在 ``.netrc`` 凭证文件与 ``--netrc-cmd`` 中检索账户密码
   * - ``_WORKING`` / ``_ENABLED``
     - ``bool``
     - 站点可用性状态。``_WORKING=False`` 输出不可用告警，``_ENABLED=False`` 需显式启用

惰性正则编译缓存 (`_match_valid_url`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了加速上千个提取器的启动时间（Lazy Loading），``yt-dlp`` 并不在模块导入时编译所有正则，而是在首次路由匹配时进行类级动态缓存：

.. code-block:: python

   @classmethod
   def _match_valid_url(cls, url):
       if cls._VALID_URL is False:
           return None
       # 显式检查类字典 __dict__ 而非 getattr，杜绝子类错误命中父类已缓存的正则表达式
       if '_VALID_URL_RE' not in cls.__dict__:
           cls._VALID_URL_RE = tuple(map(re.compile, variadic(cls._VALID_URL)))
       return next(filter(None, (regex.match(url) for regex in cls._VALID_URL_RE)), None)

---
双向绑定机制与控制器上下文代理 (Bidirectional Binding)
---

在架构设计上，``InfoExtractor`` 与顶层控制器 ``YoutubeDL`` 构成了高内聚的 **双向依赖与互相注册机制**：

.. code-block:: text
   :caption: YoutubeDL 与 InfoExtractor 双向绑定与能力透传

   YoutubeDL 控制器实例                         InfoExtractor 提取器实例
   +------------------------------------+       +------------------------------------+
   | - self.params (全局参数配置)       |       | - self._downloader (绑定指向 ydl)  |
   | - self.cache (文件系统持久缓存)    |<=====>| - self.cache -> ydl.cache          |
   | - self.cookiejar (安全会话容器)    | 互相  | - self.cookiejar -> ydl.cookiejar  |
   | - self.urlopen() (网络调度引擎)    | 绑定  | - self.get_param() -> ydl.params   |
   | - self._ies (注册提取器集合)       |       | - self._request_webpage() 代理网络 |
   +------------------------------------+       +------------------------------------+

上下文透明代理接口
~~~~~~~~~~~~~~~~~~

``InfoExtractor`` 实例并不直接持有全局配置或网络句柄，而是通过一系列封装方法代理至绑定的 ``_downloader``：

* **缓存代理 (`self.cache`)**：提取器可通过 ``self.cache.load()`` 与 ``self.cache.store()`` 缓存签名密钥、Po-Token 或解密 JS 脚本，实现跨运行生命周期的状态持久化；
* **参数透传 (`self.get_param(name, default)`)**：安全读取用户在命令行或 API 中传入的配置（如 ``extractor_args``、``wait_for_video`` 等）；
* **受保护的网络请求 (`self._request_webpage`)**：
  提取器发起 HTTP 请求时，基类自动完成以下流水线装配：
  1. 遵守 ``sleep_interval_requests`` 请求休眠限制；
  2. 自动注入基于当前站点地理策略生成的 ``X-Forwarded-For`` 伪造头；
  3. 传递 ``impersonate`` 浏览器指纹扩展；
  4. 最终委托给 ``self._downloader.urlopen()``。

---
生命周期状态机与 `_real_extract` 设计范式
---

当用户调用 ``ydl.extract_info(url)`` 时，单个 ``InfoExtractor`` 经历严格的五阶段生命周期演进：

.. code-block:: text
   :caption: InfoExtractor 提取生命周期状态转换

   输入 URL
      |
      v
   [阶段 1: 静态路由判定] --------> cls.suitable(url) / cls.get_temp_id(url)
      |                            (零 I/O 正则匹配与快速 ID 提取)
      v 命中当前 IE
   [阶段 2: 实例初始化] ----------> ie.initialize()
      |                            - _initialize_geo_bypass() (注入区域 IP)
      |                            - _initialize_pre_login() (登录前状态准备)
      |                            - _perform_login() (执行密码/OAuth登录鉴权)
      |                            - _real_initialize() (拉取站点公共配置)
      v 初始化完成 (_ready = True)
   [阶段 3: 核心解析执行] --------> ie._real_extract(url)
      |                            - 抓取网页/API 数据
      |                            - 提取音视频 formats、字幕、章节、元数据
      v 返回原始 InfoDict
   [阶段 4: 兜底修补与派生] ------> 注入 __x_forwarded_for_ip、webpage_url、extractor 等系统字段
      |
      v
   [阶段 5: 惰性延迟增强] --------> 执行 __post_extractor() (按需拉取耗时数据，如长评论列表)

`_real_extract` 标准契约规范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

子类必须覆写 ``_real_extract(self, url)``，其返回的字典必须严格遵循如下多态契约：

1. **单一视频实体 (``_type='video'``，默认)**：
   * 必须包含 ``id``（字符串）与 ``title``（非空字符串）；
   * 必须包含 ``formats``（格式字典列表）或 ``url``（单一媒体流链接）；
   * 规范化注入通用元数据字段：``duration``、``timestamp``、``uploader``、``thumbnails``、``subtitles``、``chapters`` 等。
2. **嵌套外部实体引用 (``_type='url'`` / ``'url_transparent'``)**：
   * 通过辅助方法 ``self.url_result(url, ie='Youtube', video_id='...')`` 返回，通知调度中枢进行二次递归展开或属性跨层合并。
3. **播放列表集合 (``_type='playlist'`` / ``'multi_video'``)**：
   * 通过 ``self.playlist_result(entries, playlist_id, playlist_title)`` 返回，其中 ``entries`` 必须为可迭代生成器或列表。

---
结构化抽取辅助方法工具集 (Helper Utilities)
---

``InfoExtractor`` 内置了经过十余年工业级实战沉淀的辅助方法矩阵，极大简化了异构网页的数据提取并提供最高等级的容错保障。

.. list-table:: InfoExtractor 核心结构化抽取工具集
   :widths: 26 34 40
   :header-rows: 1

   * - 辅助方法名称
     - 适用数据载荷 / 格式
     - 核心优势与容错机制
   * - ``_download_webpage``
     - HTML / 纯文本响应
     - 自动推导字符集编码；自动识别国家级/企业级审查阻断页面（``__check_blocked``）
   * - ``_download_json`` / ``_parse_json``
     - JSON / 嵌入式 JS 对象
     - 基于 ``LenientJSONDecoder`` 自动修复畸形尾逗号、未闭合大括号；支持 ``js_to_json`` 转换
   * - ``_download_xml`` / ``_parse_xml``
     - XML / RSS / ATOM 报文
     - 自动清洗非法 ``&`` 字符；支持带命名空间的 XPath 查询（``xpath_element``）
   * - ``_search_regex`` / ``_html_search_regex``
     - 正则匹配与 HTML 过滤
     - 多正则候选列表；自动执行 HTML 实体转义与标签清洗（``clean_html``）
   * - ``_search_json_ld``
     - 页面 ``application/ld+json``
     - 深度遍历 JSON-LD 图谱，自动映射 ``VideoObject``、``TVEpisode`` 与交互统计指标
   * - ``_og_search_*``
     - OpenGraph 社交元数据
     - 快速提取 ``og:title``, ``og:description``, ``og:image``, ``og:video``

现代前端水合数据解构引擎 (Next.js & Nuxt.js)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对现代 SPA / SSR 框架渲染的网页，``InfoExtractor`` 实现了专用逆向解析器：

* **Next.js 数据提取 (`_search_nextjs_data` & `_search_nextjs_v13_data`)**：
  针对 Next.js v13+ App Router 引入的 React Server Components（RSC）Flight 数据流（``self.__next_f.push(...)``），引擎实现了专用的分块拼装与树形展开算法，快速解构出服务端注水的原始 JSON 元数据；
* **Nuxt.js 数据提取 (`_search_nuxt_data` & `_search_nuxt_json`)**：
  针对 Nuxt 3 富 JSON 负载（``__NUXT_DATA__``），内置 ``devalue.parse_iter`` 迭代器，通过引用还原器（Revivers）反序列化复杂的循环引用与 Ref 状态对象。

---
端到端提取调用时序图与源码映射
---

.. code-block:: text
   :caption: InfoExtractor 端到端提取流向时序

   YoutubeDL.extract_info(url)          InfoExtractor (e.g. BiliBiliIE)             RequestDirector / Downloader
               |                                       |                                         |
               |-- ie.suitable(url) ------------------>| (静态正则命中验证)                      |
               |-- ie.extract(url) ------------------->|                                         |
               |                                       |-- initialize()                          |
               |                                       |    |-- _initialize_geo_bypass()         |
               |                                       |    \-- _perform_login()                 |
               |                                       |                                         |
               |                                       |-- _real_extract(url)                    |
               |                                       |    |-- _download_webpage() ------------>| (代理发起 HTTP 请求)
               |                                       |    |<-- html_content -------------------|
               |                                       |    |-- _search_json_ld(html)            |
               |                                       |    |-- _extract_m3u8_formats() -------->| (拉取流媒体清单)
               |                                       |    \<-- formats_list -------------------|
               |                                       |                                         |
               |<-- raw_info_dict ---------------------|<-- 组装完整 InfoDict -------------------|
               |
               |-- process_ie_result(raw_info_dict) ->| (进入多态分发与规整流水线)

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: InfoExtractor 核心架构与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 方法
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``InfoExtractor``
     - ``yt_dlp/extractor/common.py:40-350``
     - 核心基类定义、字段协议规范与双向绑定属性代理
   * - ``_match_valid_url()``
     - ``yt_dlp/extractor/common.py:355-375``
     - 类级惰性正则编译、缓存与 URL 匹配
   * - ``extract()`` / ``initialize()``
     - ``yt_dlp/extractor/common.py:380-450``
     - 生命周期驱动中枢、地理伪装注入、登录鉴权与重试捕获
   * - ``_request_webpage()``
     - ``yt_dlp/extractor/common.py:460-520``
     - 网络请求装配、休眠节流、指纹伪装扩展透传与异常封装
   * - ``_download_json()`` / ``_parse_json()``
     - ``yt_dlp/extractor/common.py:530-580``
     - 容错 JSON 解析、Lenient 解码器挂载与动态代码执行转换
   * - ``_search_json_ld()`` / ``_json_ld()``
     - ``yt_dlp/extractor/common.py:730-840``
     - Schema.org 标准 JSON-LD 元数据结构化提取引擎
   * - ``_search_nextjs_v13_data()``
     - ``yt_dlp/extractor/common.py:850-910``
     - Next.js 13+ RSC Flight 数据流反混淆与反序列化还原

***
小结与下章导读
***

本节系统剖析了 ``InfoExtractor`` 抽象基类的核心架构与设计哲学，厘清了：
1. 静态类属性元编程模型与惰性正则编译缓存机制；
2. ``InfoExtractor`` 与 ``YoutubeDL`` 的双向绑定与能力代理通道；
3. 五阶段提取生命周期状态机与 ``_real_extract`` 标准契约；
4. 工业级容错抽取工具集与现代前端（Next.js/Nuxt.js）水合数据解构引擎。

在下一节（``02_url_matching_and_dispatch.rst``）中，我们将深入 URL 路由分发系统——剖析 ``yt-dlp`` 如何从 1000+ 个提取器中实现毫秒级高效路由匹配、提取器优先级判定以及通用提取器 ``GenericIE`` 的智能降级与重定向探测机制。
