========================================================================================
03.03 Web 页面结构化解析、Microdata/JSON-LD 提取与健壮容错容灾机制
========================================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们剖析了 ``InfoExtractor`` 基类架构以及基于全局优先级的 URL 路由分发机制。当特定站点的提取器（或通用的 ``GenericIE``）命中目标页面并拉取 HTML/API 数据后，核心任务便转移到了 **如何从非结构化或半结构化的混乱 Web 页面中，高信噪比、零崩溃地提取出标准化的视频元数据**。现代前端网页充斥着不规范的 HTML 标签、动态注水脚本、畸形 JSON 以及多层嵌套的微数据。``yt-dlp`` 研发了一整套基于声明式 DSL 的对象遍历引擎（``traverse_obj``）、Schema.org 标准 JSON-LD 递归图谱解析器与工业级容错管道。本节将全面解构该结构化解析体系的数学模型与容灾机制。

***
Web 页面多源半结构化元数据提取拓扑
***

在真实的流媒体爬取场景中，视频元数据通常分散在 HTML 的不同层级与规范中：

.. code-block:: text
   :caption: Web 页面多层元数据提取优先级拓扑

   HTML 原始响应字节流
          |
          v 解码与清洗 (__decode_webpage & __check_blocked)
   +-------------------------------------------------------------------+
   | 优先级 1: Schema.org JSON-LD (<script type="application/ld+json">)|
   |           语义最完备、类型最严格的标准图谱 (VideoObject / Episode)  |
   +---------------------------------+---------------------------------+
                                     |
                                     v 缺失或部分字段为空
   +-------------------------------------------------------------------+
   | 优先级 2: 现代前端 SSR 注水对象 (Next.js __NEXT_DATA__ / Nuxt.js)   |
   |           包含前端组件初始化的完整原始 State 树                   |
   +---------------------------------+---------------------------------+
                                     |
                                     v 缺失或经过动态混淆
   +-------------------------------------------------------------------+
   | 优先级 3: 社交开放图谱协议 (OpenGraph <meta property="og:*">)       |
   |           提取 og:title, og:description, og:image, og:video       |
   +---------------------------------+---------------------------------+
                                     |
                                     v 缺失或未配置
   +-------------------------------------------------------------------+
   | 优先级 4: Twitter Card / HTML 原生 Meta 标签 (<meta name="*">)    |
   |           提取 twitter:player, dc.creator, itemprop, rating       |
   +---------------------------------+---------------------------------+
                                     |
                                     v 兜底回退
   +-------------------------------------------------------------------+
   | 优先级 5: HTML DOM 与页面标题提取 (<title>, <h1>, 容错正则提取)   |
   +-------------------------------------------------------------------+

---
Schema.org JSON-LD 递归图谱解析引擎
---

``yt_dlp/extractor/common.py`` 实现了全自动化的 ``_search_json_ld`` 与 ``_json_ld`` 递归图谱解析器，能够直接解析符合 W3C / Schema.org 标准的结构化微数据。

.. code-block:: text
   :caption: JSON-LD 图谱递归遍历与实体解构

   HTML 内容
      |
      v 正则扫描 JSON_LD_RE
   [<script type="application/ld+json">...</script>]
      |
      v _yield_json_ld (LenientJSONDecoder 反序列化)
   JSON-LD 根对象树
      |
      +---> 命中 @graph 树形集合 ----> 递归展开 traverse_json_ld(e['@graph'])
      |
      +---> 匹配 @type == 'VideoObject' / 'AudioObject'
      |       |-- 提取 contentUrl, encodingFormat (mimetype2ext 转换为 ext)
      |       |-- 提取 name (title), description, duration, uploadDate (timestamp)
      |       |-- 提取 thumbnail (支持多字段回退: thumbnailUrl / thumbnailURL)
      |       |-- 提取 InteractionCounter (播放量、点赞数、评论数)
      |       \-- 提取 Clip 列表 (智能组装 chapters 章节分段)
      |
      +---> 匹配 @type == 'TVEpisode' / 'Episode'
      |       \-- 级联提取 episode, episode_number, season (partOfSeason), series
      |
      \---> 匹配 @type == 'Article' / 'NewsArticle'
              \-- 级联探测文章内嵌的 subjectOf / video (嵌套 VideoObject)

1. 交互统计指标归一化提取 (`extract_interaction_statistic`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

不同站点对交互统计（播放、点赞、点踩、评论）的命名各异。解析器构建了语义映射矩阵，并使用自适应整数转换器 ``str_to_int`` 容忍带逗号分隔符的计数字符串：

.. code-block:: python

   INTERACTION_TYPE_MAP = {
       'CommentAction': 'comment',
       'AgreeAction': 'like',
       'DisagreeAction': 'dislike',
       'LikeAction': 'like',
       'DislikeAction': 'dislike',
       'ListenAction': 'view',
       'WatchAction': 'view',
       'ViewAction': 'view',
   }

2. 章节分段区间缝合算法 (`extract_chapter_information`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于声明了 ``hasPart: [{"@type": "Clip", "startOffset": ..., "endOffset": ...}]`` 的视频，提取器通过相邻片段滑动窗口自动缝合起止时间：

.. code-block:: python

   for idx, (last_c, current_c, next_c) in enumerate(zip(
           [{'end_time': 0}, *chapters], chapters, chapters[1:], strict=False)):
       current_c['end_time'] = current_c['end_time'] or next_c['start_time']
       current_c['start_time'] = current_c['start_time'] or last_c['end_time']
   # 最后一个章节的终止时间自动回退至视频总时长 duration
   if chapters:
       chapters[-1]['end_time'] = chapters[-1]['end_time'] or info['duration']

---
声明式对象安全遍历 DSL 引擎 (traverse_obj)
---

在解析复杂的深层嵌套 JSON（如 YouTube 的 Initial Data、Bilibili 的 playurl 结构、TikTok 的 Webcast 载荷）时，传统的 Python 代码充斥着防御性判断（如 ``data.get('a', {}).get('b', [{}])[0].get('c')``），不仅代码冗长晦涩，且极易因服务端返回类型突变导致 ``AttributeError`` 或 ``IndexError`` 崩溃。

``yt-dlp/utils/traversal.py`` 引入了图灵完备的 **声明式路径遍历 DSL 引擎——``traverse_obj``**。

.. list-table:: traverse_obj DSL 语法原语与操作语义
   :widths: 22 28 50
   :header-rows: 1

   * - 语法原语
     - 结构范例
     - 语义行为与控制逻辑
   * - 键路径索引
     - ``'key'``, ``0``
     - 访问字典键或列表索引；遇到 ``None`` 或缺失时安全返回 ``None``
   * - 全量广播分支
     - ``...`` (Ellipsis)
     - 展开当前集合中的所有元素，将单线路径分支为并发评估流
   * - 切片分支
     - ``slice(0, 5)``
     - 截取列表子集并分支展开后续路径
   * - 类型断言与转换
     - ``{str}``, ``{int_or_none}``
     - 单元素集合：若为类型则执行 ``isinstance`` 过滤；若为函数则执行安全转换
   * - 谓词条件过滤
     - ``lambda k, v: v['bitrate'] > 1000``
     - 对字典键值对或列表元素进行动态布尔过滤
   * - 结构重塑映射
     - ``{'title': 'name', 'url': ('media', 0, 'url')}``
     - 字典原语：递归将目标对象转换为结构化字典
   * - 聚合与收敛原语
     - ``any``, ``all``, ``filter``
     - ``any`` 取首个非空匹配项（终止分支）；``all`` 汇总全量分支为列表；``filter`` 过滤假值

实战案例：一行代码重塑多层嵌套媒体列表
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # 传统脆弱写法 (极易因空指针崩溃):
   formats = []
   for item in raw_data.get('response', {}).get('body', {}).get('streams', []):
       if item and item.get('url'):
           formats.append({
               'url': item['url'],
               'tbr': int(item.get('bitrate', 0)) // 1000 if item.get('bitrate') else None,
               'width': item.get('video_meta', {}).get('width'),
           })

   # traverse_obj 声明式安全写法 (零崩溃保证、自动清洗空值):
   formats = traverse_obj(raw_data, ('response', 'body', 'streams', ..., {
       'url': ('url', {url_or_none}),
       'tbr': ('bitrate', {float_or_none}, {lambda x: x / 1000 if x else None}),
       'width': ('video_meta', 'width', {int_or_none}),
   }))

---
工业级容错与脏数据自愈工具集
---

1. 容错正则管道 (`_search_regex` & `_html_search_regex`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对频繁变动的 HTML 标签结构，``_search_regex`` 支持传入 **优先级递减的正则模式列表**：

.. code-block:: python

   # 依次尝试匹配现代 class、遗留 id 以及 data-* 属性，全部未命中时抛出富上下文 RegexNotFoundError
   title = self._html_search_regex(
       (r'<h1[^>]+class="video-title"[^>]*>(?P<title>[^<]+)</h1>',
        r'<div[^>]+id="title"[^>]*>(?P<title>[^<]+)</div>',
        r'data-video-title="(?P<title>[^"]+)"'),
       webpage, 'video title', default=NO_DEFAULT, fatal=True)

* **``_html_search_regex`` 深度清洗**：内部串联 ``unescapeHTML`` 还原 HTML 实体（如 ``&amp;`` $\rightarrow$ ``&``、``&#x27;`` $\rightarrow$ ``'``），并剔除内嵌的无用 HTML 子标签（``clean_html``）。

2. 宽容度 JSON 解析器 (`LenientJSONDecoder`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

真实网页中的内联 JavaScript 变量往往并非严格标准的 JSON（例如包含单引号、未加双引号的键名、末尾多余逗号、十六进制数字或行内注释）。

* ``_parse_json`` 默认挂载 ``LenientJSONDecoder`` 与 ``js_to_json`` 转换器；
* 能够自动将 JavaScript 对象字面量（JS Object Literals）转译为合规的 JSON 字节流，大幅降低因页面脚本语法不规范导致的解析崩溃。

3. HTML5 多媒体标签多流解构 (`_parse_html5_media_entries`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对标准 HTML5 视频页面及 AMP 页面，``_parse_html5_media_entries`` 实现了多轨自适应解析：
* 支持标准 ``<video>`` / ``<audio>`` 以及扩展的 ``<amp-video>``、``<dl8-video>``；
* 解析内嵌的所有 ``<source src="..." type="..." res="..." label="...">`` 标签，自动解构多码率清晰度矩阵；
* 自动提取 ``<track kind="subtitles" srclang="..." src="...">`` 外挂字幕轨道。

4. 国家级审查与网络阻断主动识别 (`__check_blocked`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当请求遭遇区域审查、企业网关过滤或防火墙拦截时，服务器通常返回伪装的 200 OK 拦截说明页。``__check_blocked`` 在解码内容前进行特征指纹匹配：
* 识别 **Websense 企业防火墙**、**印度网络审查（Indian censorship）** 以及 **俄罗斯 Roskomnadzor (RKN)** 封锁页；
* 主动抛出明确的 ``ExtractorError(..., expected=True)`` 友好提示，避免将拦截页误作为正常视频解析而产生晦涩的空指针堆栈。

---
端到端页面微数据抽取时序图与源码映射
---

.. code-block:: text
   :caption: Web 页面微数据抽取端到端调用链

   InfoExtractor._real_extract(url)           JSON-LD Parser                  traverse_obj DSL               InfoDict
                 |                                  |                                |                           |
                 |-- _download_webpage(url) ------->|                                |                           |
                 |   (执行 __check_blocked 校验)    |                                |                           |
                 |<-- html -------------------------|                                |                           |
                 |                                  |                                |                           |
                 |-- _search_json_ld(html) -------->|                                |                           |
                 |                                  |-- JSON_LD_RE 正则提取字符串    |                           |
                 |                                  |-- LenientJSONDecoder 反序列化  |                           |
                 |                                  |-- 递归提取 VideoObject / Clip  |                           |
                 |<-- json_ld_info -----------------|                                |                           |
                 |                                                                   |                           |
                 |-- traverse_obj(json_ld_info, ('thumbnails', ..., 'url')) -------->| (安全解构提取缩略图列表)  |
                 |<-- sanitized_thumbnails ------------------------------------------|                           |
                 |                                                                                               |
                 |-- _og_search_title(html, default=...) ------------------------------------------------------->| 兜底补齐 title
                 |-- _html_search_meta('duration', html) ------------------------------------------------------->| 兜底补齐 duration
                 |                                                                                               |
                 \-- 组装完整标准化 InfoDict -------------------------------------------------------------------->| 返回控制器

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 页面解析与微数据提取核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``_search_json_ld()`` / ``_json_ld()``
     - ``yt_dlp/extractor/common.py:730-840``
     - Schema.org JSON-LD 图谱递归遍历、多类型适配与交互统计映射
   * - ``traverse_obj()``
     - ``yt_dlp/utils/traversal.py:30-220``
     - 声明式对象遍历 DSL 引擎、分支广播与类型安全断言
   * - ``_search_regex()`` / ``_html_search_regex()``
     - ``yt_dlp/extractor/common.py:640-695``
     - 多候选正则回退匹配、命名组提取与 HTML 标签/实体清洗
   * - ``_parse_json()``
     - ``yt_dlp/extractor/common.py:535-565``
     - 挂载 ``LenientJSONDecoder`` 的容错 JSON 与 JS 对象解析器
   * - ``_parse_html5_media_entries()``
     - ``yt_dlp/extractor/common.py:1260-1360``
     - 标准 HTML5/AMP `<video>`、`<source>` 与 `<track>` 标签抽取器
   * - ``__check_blocked()``
     - ``yt_dlp/extractor/common.py:500-530``
     - Websense / RKN / 审查阻断页面指纹拦截识别

***
小结与下章导读
***

本节系统剖析了 ``yt-dlp`` 在复杂 Web 页面中提取结构化微数据的全套技术栈，厘清了：
1. Web 页面多层半结构化元数据的优先级提取模型；
2. ``_search_json_ld`` 针对 Schema.org 规范的递归图谱解构与章节分段区间缝合算法；
3. ``traverse_obj`` 声明式 DSL 的语法原语、分支广播与生产级防崩溃机制；
4. 工业级容错正则、LenientJSON 解码、HTML5 媒体解构与网络阻断指纹识别。

在下一节（``04_playlist_and_lazy_evaluation.rst``）中，我们将深入播放列表流式处理引擎——剖析 ``PlaylistEntries``、``LazyList`` 与 ``PagedList`` 如何通过惰性求值模型，实现针对包含数十万条目巨型播放列表的零内存暴涨流式解包与并发下载。
