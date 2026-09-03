========================================================================================
03.02 URL 正则路由分发系统、优先级匹配与 GenericIE 降级熔断策略
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们解构了 ``InfoExtractor`` 抽象基类的生命周期状态机、类属性元编程以及与 ``YoutubeDL`` 的双向绑定契约。当用户输入一个未知 URL 时，流媒体引擎面临的首要挑战是：**如何在 1000+ 个各异的提取器中，以毫秒级时延精准匹配出最适宜的目标解析器？当所有专用解析器均无法命中时，系统如何通过通用探测机制实现自动化视频发现与嵌入式流提取？** 本节将深入解密 ``yt-dlp`` 的 URL 正则路由分发引擎、零 I/O 短路归档校验、通用提取器 ``GenericIE`` 的多层级探测管线，以及分布式嵌入嗅探中的 ``StopExtraction`` 独占熔断机制。

***
URL 正则路由分发系统与拓扑决议机制
***

``yt-dlp`` 的提取器路由调度基于 **全局确定性线性拓扑（Deterministic Linear Priority）**。

.. code-block:: text
   :caption: URL 路由分发与优先级决议流水线

   输入 URL (例如: https://example.com/embed/12345)
                           |
                           v
   +-------------------------------------------------------------------+
   | 1. 全局提取器列表构建 (add_default_info_extractors)               |
   |    - 调用 gen_extractor_classes() 生成标准排序的 IE 列表          |
   |    - 评估 allowed_extractors 白名单正则过滤                       |
   |    - 注入插件覆盖层 (plugin_ies_overrides)                        |
   |    - 末尾追加兜底提取器: GenericIE 与 UnsupportedURLIE           |
   +-------------------------------+-----------------------------------+
                                   |
                                   v 遍历 _ies (for ie_key, ie in _ies.items():)
   +-------------------------------------------------------------------+
   | 2. 静态路由探测 (ie.suitable(url))                                |
   |    - 检查 _match_valid_url(url)                                   |
   |    - 惰性正则匹配: regex.match(url)                              |
   +-------------------------------+-----------------------------------+
                                   |
                   +---------------+---------------+
                   |                               |
                 未命中                          命中
                   v                               v
           [继续评估下一 IE]           +-----------------------------------+
                   |                   | 3. 零 I/O 快速 ID 提取            |
                   v 遍历至末尾        |    temp_id = ie.get_temp_id(url)  |
           [命中 GenericIE]            +-----------------+-----------------+
                   |                                     |
                   v                                     v
           [进入通用探测流水线]        +-----------------------------------+
                                       | 4. 幂等归档校验 (in_download_arc) |
                                       +-----------------+-----------------+
                                                         |
                                         +---------------+---------------+
                                         |                               |
                                      已归档                           未归档
                                         v                               v
                             [触发 break_on_existing 短路退出]  [执行 ie.extract(url)]

路由顺序敏感性（Order-Sensitivity）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``_ies`` 字典中，提取器的注册顺序具有决定性意义：
1. **专用子路由优先于通用主路由**：例如针对同一平台，特定子功能提取器（如 ``YoutubeTabIE`` 频道列表、``YoutubeClipIE`` 剪辑片段）必须排在标准 ``YoutubeIE`` 之前；
2. **专属第三方服务优先于宿主门户**：例如嵌入在新闻站点的专用视频源解析器，优先于通用 CMS 提取器；
3. **``GenericIE`` 绝对兜底**：声明 ``_VALID_URL = r'.*'` 的通用提取器始终置于列表末尾，确保专用提取器拥有绝对的优先匹配权。

---
零 I/O 快速探测与短路归档校验 (`get_temp_id`)
---

在分布式采集或处理包含数千个视频的巨型列表时，若对每个 URL 都发起 HTTP 请求拉取元数据，网络 I/O 成本将极其高昂。

``InfoExtractor`` 规范强制要求 ``_VALID_URL`` 必须包含 ``(?P<id>...)`` 命名捕获组。引擎利用该特性实现了 **零网络 I/O 的短路快速归档检查**：

.. code-block:: python

   @classmethod
   def _match_id(cls, url):
       return cls._match_valid_url(url).group('id')

   @classmethod
   def get_temp_id(cls, url):
       try:
           return cls._match_id(url)
       except (IndexError, AttributeError):
           return None

在 ``YoutubeDL.extract_info()`` 中：

.. code-block:: python

   temp_id = ie.get_temp_id(url)
   if temp_id is not None and self.in_download_archive({'id': temp_id, 'ie_key': key}):
       self.to_screen(f'[download] {temp_id}: has already been recorded in the archive')
       if self.params.get('break_on_existing', False):
           raise ExistingVideoReached
       return None

在不发送任何网络数据包的前提下，引擎仅耗费数十微秒完成正则解包与归档哈希比对，将已下载视频直接阻断熔断，极大提升了多任务轮询吞吐量。

---
通用提取器 GenericIE 核心架构与多层级降级流
---

当目标 URL 无法被任何专用提取器匹配时，请求降级至 ``GenericIE``（``yt_dlp/extractor/generic.py``）。``GenericIE`` 是一个高度精密的 **全自动多媒体逆向嗅探引擎**，其内部构建了严密的多层级探测流水线：

.. code-block:: text
   :caption: GenericIE 多层级自适应探测流水线

   GenericIE._real_extract(url)
                 |
                 v
   +-------------------------------------------------------------------+
   | 阶段 1: 协议与直接媒体流探测 (Direct Media Probing)                |
   |    - 审查响应头 Content-Type (audio/*, video/*, application/ogg)   |
   |    - 读取首部 512 字节 Magic Bytes:                                |
   |      * b'#EXTM3U' -> 直接分发至 HLS (M3U8) 解析器                  |
   |      * 非 HTML 二进制流 -> 判定为原生直接媒体 (MP4/FLV/WebM)       |
   +---------------------------------+---------------------------------+
                                     |
                                     v 判定为 HTML 页面
   +-------------------------------------------------------------------+
   | 阶段 2: 结构化清单与 XML 提要探测 (Structured Manifest Probing)   |
   |    - 尝试将网页解析为 XML ElementTree                             |
   |    - doc.tag == 'rss' -> _extract_rss() (播客与 RSS 媒体源)        |
   |    - doc.tag == 'SmoothStreamingMedia' -> ISM Manifest 提取        |
   |    - doc.tag 匹配 smil -> SMIL XML 多码率流提取                   |
   |    - doc.tag 匹配 xspf -> XSPF 播放列表展开                       |
   |    - doc.tag 匹配 MPD -> MPEG-DASH Manifest 提取                   |
   +---------------------------------+---------------------------------+
                                     |
                                     v 未命中 XML 清单
   +-------------------------------------------------------------------+
   | 阶段 3: 现代 Web 嵌入式播放器逆向嗅探 (Embedded Players Probing)  |
   |    - 运行 _extract_embeds() 广播扫描嵌入视频                       |
   |    - JWPlayer: 提取 window.jwplayer().setup() 与 flashvars 负载   |
   |    - Video.js: 解析 videojs(...).src([{...}]) 数据源              |
   |    - KVS Player: 执行 _kvs_get_real_url() 混淆算法解密             |
   |    - Schema.org JSON-LD: 深度遍历 VideoObject 实体                |
   |    - 社交卡片元数据: Twitter Player Stream / OpenGraph 视频流      |
   |    - HTTP 自动跳转: 嗅探 http-equiv="refresh" 与 Refresh 头       |
   +---------------------------------+---------------------------------+
                                     |
                                     v 若依然未发现任何多媒体实体
   +-------------------------------------------------------------------+
   | 阶段 4: 熔断与异常抛出                                            |
   |    - raise UnsupportedError(url)                                  |
   +-------------------------------------------------------------------+

KVS Player 核心解密算法逆向 (`_kvs_get_real_url`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

许多成人门户及独立视频站广泛使用 Kernel Video Sharing (KVS) 播放器。其视频真实 URL 往往被 ``function/0/`` 伪协议及动态许可证令牌（License Code）混淆。

``GenericIE`` 实现了对其对称置换算法的逆向还原：

.. code-block:: python

   @classmethod
   def _kvs_get_real_url(cls, video_url, license_code):
       if not video_url.startswith('function/0/'):
           return video_url  # 未混淆链接

       parsed = urllib.parse.urlparse(video_url[len('function/0/'):])
       license_token = cls._kvs_get_license_token(license_code)
       urlparts = parsed.path.split('/')

       HASH_LENGTH = 32
       hash_ = urlparts[3][:HASH_LENGTH]
       indices = list(range(HASH_LENGTH))

       # 根据许可证令牌动态计算置换累加步长并交换哈希索引
       accum = 0
       for src in reversed(range(HASH_LENGTH)):
           accum += license_token[src]
           dest = (src + accum) % HASH_LENGTH
           indices[src], indices[dest] = indices[dest], indices[src]

       urlparts[3] = ''.join(hash_[index] for index in indices) + urlparts[3][HASH_LENGTH:]
       return urllib.parse.urlunparse(parsed._replace(path='/'.join(urlparts)))

---
分布式嵌入式嗅探与 StopExtraction 独占熔断机制
---

在 ``GenericIE._extract_embeds`` 中，引擎并非仅仅使用静态规则扫描 HTML，而是 **反向驱动所有已注册提取器的嵌入式探测接口**。

.. code-block:: text
   :caption: _extract_embeds 广播分发与 StopExtraction 熔断

   GenericIE._extract_embeds(webpage)
                  |
                  v 遍历已注册的提取器列表 (for ie in _ies.values():)
   +-------------------------------------------------------------------+
   | 1. 调用 ie.extract_from_webpage(ydl, url, webpage)                |
   |    - 执行该 IE 声明的 _EMBED_REGEX 正则扫描 (如 iframe src)       |
   |    - 生成候选嵌入 URL                                             |
   +------------------------------+------------------------------------+
                                  |
                  +---------------+---------------+
                  |                               |
               正常产出                        抛出异常
                  v                               v
      [将嵌入结果追加至 embeds 队列]      [捕获 ie.StopExtraction]
                  |                               |
                  |                               v
                  |               +-----------------------------------+
                  |               | 2. 独占熔断 (Exclusive Match)     |
                  |               |    - 判定该提取器对当前网页拥有独占权 |
                  |               |    - 丢弃其余所有已发现的 embeds   |
                  |               |    - 立即返回当前 IE 的提取结果   |
                  |               +-----------------------------------+
                  v 所有 IE 扫描完毕
      [汇总全部 embeds 并返回]

StopExtraction 的工程防御价值
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代去中心化/分布式流媒体服务（如 PeerTube 实例、Invidious 代理网关）中，不同站点的域名完全随机且不固定，无法通过静态 ``_VALID_URL`` 穷举。
* 当 PeerTubeIE 扫描网页特征发现其符合 PeerTube 前端规范时，它会抛出 ``self.StopExtraction`` 异常；
* ``GenericIE`` 捕获该异常后，立即终止对其它通用播放器或社交元数据的低信噪比扫描，将控制权完全移交给该专用协议提取器，从机制上杜绝了重复抓取与误判。

---
端到端路由与通用嗅探时序图与源码映射
---

.. code-block:: text
   :caption: URL 路由、GenericIE 降级与嵌入式解析完整调用链

   User Input               YoutubeDL.extract_info()       Dedicated IE (e.g. VimeoIE)      GenericIE
       |                               |                                |                       |
       |-- extract_info(url) --------->|                                |                       |
       |                               |-- ie.suitable(url) ----------->| (匹配失败)            |
       |                               |-- ... (遍历其它专用 IE 失败) ->|                       |
       |                               |-- GenericIE.suitable(url) ---------------------------->| (匹配成功)
       |                               |-- GenericIE.extract(url) ----------------------------->|
       |                               |                                                        |-- _request_webpage()
       |                               |                                                        |-- _extract_embeds(html)
       |                               |                                                        |    |-- 广播至 VimeoIE._EMBED_REGEX
       |                               |                                                        |    \<-- 发现 Vimeo 嵌入 iframe
       |                               |                                                        |-- 返回 url_result(vimeo_url, 'Vimeo')
       |                               |<-- url_result -----------------------------------------|
       |                               |
       |                               |-- 识别 _type='url'，触发二次递归分发 ----------------->|
       |                               |-- VimeoIE.suitable(vimeo_url) -> 命中!                 |
       |                               |-- VimeoIE.extract(vimeo_url) -> 成功拉取高清媒体流 ----->|

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 路由分发与通用提取核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``gen_extractor_classes()``
     - ``yt_dlp/extractor/__init__.py:18-28``
     - 全局提取器列表加载、插件注入与保序导出
   * - ``YoutubeDL.extract_info()``
     - ``yt_dlp/YoutubeDL.py:530-580``
     - 顶层路由匹配分发、``get_temp_id`` 快速提取与幂等去重
   * - ``GenericIE``
     - ``yt_dlp/extractor/generic.py:40-300``
     - 全网兜底通用提取器、多层级媒体嗅探与 XML/Manifest 适配
   * - ``_kvs_get_real_url()``
     - ``yt_dlp/extractor/generic.py:230-270``
     - Kernel Video Sharing 播放器哈希索引动态置换逆向解密
   * - ``_extract_embeds()``
     - ``yt_dlp/extractor/generic.py:380-480``
     - 广播驱动各 IE 的 ``extract_from_webpage`` 并处理 ``StopExtraction`` 熔断
   * - ``InfoExtractor.StopExtraction``
     - ``yt_dlp/extractor/common.py:970-985``
     - 联邦分布式与非标准站点提取器的独占控制权熔断异常

***
小结与下章导读
***

本节系统剖析了 ``yt-dlp`` 高性能 URL 路由分发系统与 ``GenericIE`` 通用探测引擎的架构原理，厘清了：
1. 全局提取器线性拓扑优先级决议与顺序敏感性；
2. 基于 URL 命名捕获组的零 I/O 快速 ID 提取与幂等归档短路阻断；
3. ``GenericIE`` 涵盖直接流、XML 清单、专用 Web 播放器与社交卡片的多层自适应探测管线；
4. ``_extract_embeds`` 广播机制与 ``StopExtraction`` 独占熔断策略。

在下一节（``03_page_parsing_and_microdata.rst``）中，我们将聚焦于微数据结构化抽取——剖析 ``yt-dlp`` 如何从海量混乱的 Web 页面中，通过 OpenGraph、Microdata、Schema.org JSON-LD 以及健壮的容错正则表达式工具集，精确剥离出标准化的音视频元数据。
