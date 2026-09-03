========================================================================================
04.04 DASH (MPD) XML 清单树解析、SegmentTimeline 索引计算与动态直播滑动窗口
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们深入剖析了原生 HLS (M3U8) 下载器 ``HlsFD`` 的单遍状态机、AES-128-CBC 密码学动态解密与时间戳缝合流水线。除 HLS 之外，由 ISO/IEC 联合制定的 **MPEG-DASH (Dynamic Adaptive Streaming over HTTP, ISO/IEC 23009-1)** 是现代流媒体领域另一大基石标准（广泛应用于 YouTube、Netflix、Bilibili、Vimeo 等主流平台）。与 HLS 基于简单文本行的 M3U8 播放列表不同，DASH 采用高度结构化、层次复杂的 XML 文档——**媒体呈现描述（Media Presentation Description, MPD）**。MPD 支持多级属性级联继承、复杂的模板变量动态展开（``$Time$`` / ``$Number$`` / ``$Bandwidth$``）、分片时间线（``SegmentTimeline``）重复压缩以及多周期（Multi-Period）媒体拼接。``yt-dlp`` 在提取层实现了完备的 MPD 清单树解析与 Period 合并算法，并在下载层由 **``DashSegmentsFD``（``yt_dlp/downloader/dash.py``）** 驱动流式分片拉取与外部下载器协议桥接。本节将深度解构这一工业级流媒体内核。

***
ISO/IEC 23009-1 MPEG-DASH 协议模型与 XML 树型拓扑
***

MPEG-DASH 规范定义了一个严格的四层树状模型，用以描述在不同网络带宽和设备特性下自适应切换的多媒体流：

.. code-block:: text
   :caption: MPEG-DASH MPD 层次模型与级联继承拓扑

   +-------------------------------------------------------------------------------+
   | MPD (根节点: @type="static"|"dynamic", @mediaPresentationDuration, BaseURL)    |
   +---------------------------------------+---------------------------------------+
                                           | 1:N 包含多个时间周期
                                           v
   +-------------------------------------------------------------------------------+
   | Period (时间分期: @id, @start, @duration, BaseURL, SegmentTemplate/List)       |
   +---------------------------------------+---------------------------------------+
                                           | 1:N 包含多个媒体类型集合
                                           v
   +-------------------------------------------------------------------------------+
   | AdaptationSet (自适应集合: @mimeType="video/mp4"|"audio/mp4", @codecs, BaseURL)|
   +---------------------------------------+---------------------------------------+
                                           | 1:N 包含同一媒体的不同码率/分辨率实现
                                           v
   +-------------------------------------------------------------------------------+
   | Representation (媒体变体: @id="137", @bandwidth="4194304", @width, @height)   |
   |   -> SegmentTemplate / SegmentTimeline / SegmentList / Initialization         |
   +-------------------------------------------------------------------------------+

MPD 树型节点的核心层级语义
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **MPD (Media Presentation Description)**：
   根节点，定义流媒体全局呈现类型（``static`` 表示点播 VOD，``dynamic`` 表示在线直播 Live）、整体媒体总时长（``mediaPresentationDuration``）、可用性起始时间（``availabilityStartTime``）以及全局 ``BaseURL``。
2. **Period (时间分期)**：
   表示时间轴上的一个连续片段（例如正片、插入的片头广告、中插广告）。点播视频通常仅包含单个 Period，而长视频或包含动态插播的广播流可能包含多个连续的 Periods。
3. **AdaptationSet (自适应媒体集合)**：
   包含一组在内容上等价但在编码参数（码率、分辨率、帧率）上不同的媒体轨道。通常按媒体类型（Video、Audio、Subtitles/Captions、Storyboards）严格分离。
4. **Representation (媒体表现/变体)**：
   一个具体的编码流变体（如 1080p@6Mbps H.264、720p@2.5Mbps VP9 或 128kbps Opus 音频）。客户端根据当前可用网络带宽在同一 AdaptationSet 内的不同 Representation 之间进行平滑动态切换。

---
多层级属性级联继承与 BaseURL 解析算法
---

在 DASH XML 中，为了精简清单体积，许多关键配置（如 ``BaseURL``、``SegmentTemplate``、``timescale``、``ContentProtection``）可以在任意高层节点（MPD、Period、AdaptationSet）中声明，并向下隐式传递与逐级覆盖。

BaseURL 的向上回溯与绝对路径缝合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``InfoExtractor._parse_mpd_periods()`` 通过自底向上的四级回溯链提取并组装完整的物理基准 URL：

.. code-block:: python

   # 遍历 Representation -> AdaptationSet -> Period -> MPD 四个层级
   base_url = ''
   for element in (representation, adaptation_set, period, mpd_doc):
       base_url_e = element.find(_add_ns('BaseURL'))
       if try_call(lambda: base_url_e.text) is not None:
           base_url = base_url_e.text + base_url
           # 一旦遇到绝对 URL (http:// 或 https://)，终止向上回溯
           if re.match(r'https?://', base_url):
               break

   # 结合 MPD 文件自身的网络请求 URL 进行标准化合并
   if mpd_base_url and base_url.startswith('/'):
       base_url = urllib.parse.urljoin(mpd_base_url, base_url)
   elif mpd_base_url and not re.match(r'https?://', base_url):
       if not mpd_base_url.endswith('/'):
           mpd_base_url += '/'
       base_url = mpd_base_url + base_url

级联字典继承引擎 (extract_multisegment_info)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

分片寻址元数据通过 ``extract_multisegment_info(element, ms_parent_info)`` 在 Period $\rightarrow$ AdaptationSet $\rightarrow$ Representation 之间进行浅拷贝与重载覆盖，确保子节点既能继承父节点的默认 ``timescale`` 与 ``startNumber``，又能自由声明专属于本 Representation 的 ``media`` 模板或 ``initialization`` 切片。

.. code-block:: text
   :caption: 多层级元数据级联继承机制

   Period 级 (默认: start_number=1, timescale=1)
          |
          v extract_multisegment_info(AdaptationSet, period_ms_info)
   AdaptationSet 级 (补充: timescale=90000, initialization="$RepresentationID$_init.mp4")
          |
          v extract_multisegment_info(Representation, adaptation_set_ms_info)
   Representation 级 (覆盖/特化: media="$RepresentationID$_$Number$.m4s", start_number=100)
          |
          +-> 最终形成完备的 representation_ms_info 寻址上下文

---
多模式分片寻址机制与模板转译算法
---

DASH 规范提供了三种主流的分片定位机制：``SegmentTemplate`` 动态模板、``SegmentTimeline`` 时间线驱动以及 ``SegmentList`` 显式列表。``yt-dlp`` 统一将其抽象并编译为标准化的分片清单。

1. SegmentTemplate 模板语法与安全转译引擎
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``SegmentTemplate`` 中，分片 URL 是一个包含动态占位符的字符串模板。常见的标识符包括：
* ``$RepresentationID$``：当前媒体流的 ID（如 ``137``、``video_1080p``）；
* ``$Number$``：分片序号（可带格式化修饰符，如 ``$Number%05d$``）；
* ``$Bandwidth$``：媒体流码率（bps）；
* ``$Time$``：当前分片在媒体时间轴上的起始绝对时间戳（基于 ``timescale``）。

转译与防转义冲突算法 (prepare_template)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python 的字符串格式化操作符 ``%`` 遇到原始 URL 中的合法 ``%`` 字符（例如 URL 编码的 ``%20`` 或 ``%2F``）时极易发生语法崩溃。``yt-dlp`` 设计了双遍扫描与转译算法：

.. code-block:: python

   def prepare_template(template_name, identifiers):
       tmpl = representation_ms_info[template_name]
       if representation_id is not None:
           tmpl = tmpl.replace('$RepresentationID$', representation_id)
       
       # 阶段 1: 扫描并转义非模板区域的 '%' 字符为 '%%'，防止 Python % 运算解析失败
       t = ''
       in_template = False
       for c in tmpl:
           t += c
           if c == '$':
               in_template = not in_template
           elif c == '%' and not in_template:
               t += c  # 翻倍为 %%
       
       # 阶段 2: 将 DASH 的 $Identifier$ 与 $Identifier%Format$ 转为 Python 标准 %(Identifier)s 命名占位符
       t = re.sub(r'\$({})\$'.format('|'.join(identifiers)), r'%(\1)d', t)
       t = re.sub(r'\$({})%([^$]+)\$'.format('|'.join(identifiers)), r'%(\1)\2', t)

       # 阶段 3: 将 DASH 规范中的转义标识符 '$$' 还原为单字符 '$'
       return t.replace('$$', '$')

例如：``segment_$RepresentationID$_$Number%04d$.m4s?token=a%20b`` 会被严密转译为：
``segment_137_%(Number)04d.m4s?token=a%%20b``，从而能够安全执行字典传参求值。

2. SegmentTimeline 压缩时间线与连续重复累加
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当流媒体分片并非恒定长度（例如存在关键帧对齐、广告切片或丢帧抖动）时，清单会使用 ``<SegmentTimeline>`` 标签精确列出每一个分片的时间信息：

.. code-block:: xml

   <SegmentTemplate timescale="1000" media="chunk_$Time$.m4s">
       <SegmentTimeline>
           <S t="0" d="2000" r="2" />
           <S d="1500" />
           <S t="8000" d="2000" />
       </SegmentTimeline>
   </SegmentTemplate>

* ``t``：该时间线切片的起始绝对时间戳（省略时等于前一切片的结束时间戳）；
* ``d``：该分片的持续时长（基于 ``timescale``）；
* ``r``：连续重复次数（Repeat Count，若 ``r=2`` 表示后续还有 2 个持续时长同样为 ``d`` 的相邻分片，共计 $1 + r = 3$ 个切片）。

时间戳状态推进数学推导
^^^^^^^^^^^^^^^^^^^^^^

``yt-dlp`` 维护时间累加器，算法推导过程如下：

.. math::

   t_{k, 0} = 
   \begin{cases} 
   S_k.t & 	ext{若 } S_k 	ext{ 显式声明 } t \ 
   t_{k-1, 	ext{end}} & 	ext{若 } S_k.t 	ext{ 缺省} 
   \end{cases}

对于每个重复项 $j \in [0, r]$：

.. math::

   t_{k, j} = t_{k, 0} + j 	imes S_k.d, \quad N_{	ext{curr}} = N_{	ext{curr}} + 1

代码级迭代实现：

.. code-block:: python

   for s in representation_ms_info['s']:
       segment_time = s.get('t') or segment_time
       segment_d = s['d']
       add_segment_url()
       segment_number += 1
       for _ in range(s.get('r', 0)):
           segment_time += segment_d
           add_segment_url()
           segment_number += 1
       segment_time += segment_d

3. SegmentList 与 SegmentURL 显式列表模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``SegmentList`` 模式中，XML 直接枚举出所有物理切片节点：
``<SegmentURL media="seg-1.m4s"/>``、``<SegmentURL media="seg-2.m4s"/>``。
引擎直接遍历并提取 ``media`` 属性，若声明了 ``timescale`` 和 ``duration``，则均匀分配分片时长。

---
初始化分片 (Initialization Segment) 优先注入与 fMP4 解码头保障
---

与传统的 MPEG-TS 容器不同，DASH 普遍采用 **fMP4 (Fragmented MP4 / ISO Base Media File Format, ISOBMFF)** 封装。

.. code-block:: text
   :caption: fMP4 容器结构与初始化分片依赖

   +-------------------------------------------------------------------------------+
   | 初始化分片 Initialization Segment (init.mp4)                                  |
   | +-----------------------+ +-------------------------------------------------+ |
   | | ftyp Box (文件类型)   | | moov Box (包含 trak, mdia, minf, stbl 编解码全局参数) | |
   | +-----------------------+ +-------------------------------------------------+ |
   +-------------------------------------------------------------------------------+
                                          |
                                          | 必须置顶注入并首先写入磁盘文件头部
                                          v
   +-------------------------------------------------------------------------------+
   | 媒体分片 1 Media Segment (chunk_1.m4s)                                        |
   | +-----------------------+ +-------------------------------------------------+ |
   | | moof Box (分片元数据) | | mdat Box (原始音视频 NALU 载荷)                     | |
   | +-----------------------+ +-------------------------------------------------+ |
   +-------------------------------------------------------------------------------+
   | 媒体分片 2 Media Segment (chunk_2.m4s)                                        |
   | +-----------------------+ +-------------------------------------------------+ |
   | | moof Box (分片元数据) | | mdat Box (原始音视频 NALU 载荷)                     | |
   | +-----------------------+ +-------------------------------------------------+ |
   +-------------------------------------------------------------------------------+

Init Segment 注入机制
~~~~~~~~~~~~~~~~~~~~~

每个 ``moof + mdat`` 媒体切片本身并不包含音视频编码参数字典（SPS/PPS、声道配置、采样率）。若缺少包含 ``moov`` 的初始化分片，任何播放器与解复用器（如 FFmpeg）均无法解析后续媒体切片。

因此，``_parse_mpd_periods()`` 强制将解析出的 ``initialization_url`` 作为 **``fragments[0]``** 置顶插入切片列表：

.. code-block:: python

   if 'initialization_url' in representation_ms_info:
       initialization_url = representation_ms_info['initialization_url']
       if not f.get('url'):
           f['url'] = initialization_url
       f['fragments'].append({location_key(initialization_url): initialization_url})
   f['fragments'].extend(representation_ms_info['fragments'])

初始化分片致命性校验 (is_fatal)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``DashSegmentsFD.real_download()`` 触发分片拉取时，向基类传入严苛的断言函数：

.. code-block:: python

   return self.download_and_append_fragments_multiple(*args, is_fatal=lambda idx: idx == 0)

* 当 ``idx == 0``（初始化分片）下载失败时，直接抛出致命错误，彻底终止下载，避免浪费带宽拉取后续无头垃圾数据；
* 当 ``idx > 0`` 时，允许根据用户配置的重试策略进行网络重试或容灾跳过。

---
多周期合并算法 (_merge_mpd_periods) 与跨 Period 流缝合
---

对于包含多个 ``Period`` 的复杂点播或直播清单，直接向提取器返回离散的周期列表会导致下游流程（格式选择、后处理）无法识别。``_merge_mpd_periods()`` 实现了跨 Period 的等价格式无缝合并：

.. code-block:: python

   def _merge_mpd_periods(self, periods):
       formats, subtitles = {}, {}
       for period in periods:
           for f in period['formats']:
               assert 'is_dash_periods' not in f, 'format already processed'
               f['is_dash_periods'] = True
               # 计算格式等价特征元组 (排除 format_id, fragments, manifest_stream_number)
               format_key = tuple(v for k, v in f.items() if k not in (
                   ('format_id', 'fragments', 'manifest_stream_number')))
               if format_key not in formats:
                   formats[format_key] = f
               elif 'fragments' in f:
                   # 相同规格的流，将后序 Period 的分片无缝追加至已存在的流中
                   formats[format_key].setdefault('fragments', []).extend(f['fragments'])

           for sub_lang, sub_info in period['subtitles'].items():
               subtitles.setdefault(sub_lang, []).extend(sub_info)

       return list(formats.values()), subtitles

通过特征提取三元组匹配，跨越广告和章节的不同 Period 被无损整合成一条连续的单一媒体轨道，并标记 ``is_dash_periods=True``，为后续 ``FFmpegMergerPP`` 提供标准输入。

---
动态直播流 (Dynamic MPD) 与滑动窗口追赶机制
---

当 MPD 声明 ``type="dynamic"`` 时，代表这是一个正在进行的实时直播流。

.. code-block:: text
   :caption: Dynamic MPD 时间滑窗与追赶模型

   UTC 时间轴 ->
   [00:00:00] ..................... [01:00:00] ------------- [01:30:00] (当前时刻: Now)
   |<-------- 过期被清理切片 -------->|<--- timeShiftBufferDepth (可回看滑窗) --->|
                                    ^                                              ^
                                    | 历史起始分片                                 | 最新直播边缘 (Live Edge)
                                    | (--live-from-start 追赶点)                   | (普通实时模式)

直播核心控制参数解析
~~~~~~~~~~~~~~~~~~~~

1. **``availabilityStartTime``**：流媒体广播全局时间锚点（UTC 时间戳）；
2. **``timeShiftBufferDepth``**：服务端保留的最大回放缓冲深度（例如 30 分钟）。落后于该滑窗的分片将被服务器 404 清理；
3. **``suggestedPresentationDelay``**：播放器推荐延迟，用于吸收网络抖动。

``--live-from-start`` 与生成器驱动协议
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对 YouTube、Twitch 等平台支持的 DASH 直播“从头回看”（Live from start）功能：
* 提取层返回 ``http_dash_segments_generator`` 协议；
* ``DashSegmentsFD.real_download()`` 检测到该协议后，**主动禁用外部下载器挂载**（因为外部工具如 aria2c 无法动态感知 MPD 滑窗的定时轮询与刷新）：

.. code-block:: python

   if 'http_dash_segments_generator' in info_dict['protocol'].split('+'):
       real_downloader = None  # 必须由 Native 引擎执行增量生成器迭代
   else:
       # 普通点播切片可安全托管给支持 'dash_frag_urls' 的外部并发下载器
       real_downloader = get_suitable_downloader(
           info_dict, self.params, None, protocol='dash_frag_urls', to_stdout=(filename == '-'))

---
DashSegmentsFD 执行时序图与源码映射
---

.. code-block:: text
   :caption: DashSegmentsFD 端到端执行调用链

   DashSegmentsFD.real_download()   _get_fragments()            _resolve_fragments()        FragmentFD (多流/单流)
                 |                          |                           |                             |
                 |-- 判断 protocol 特征 --->|                           |                             |
                 |   (禁止外部 FD 接管直播) |                           |                             |
                 |                          |                           |                             |
                 |-- 构建上下文 ctx -------->|                           |                             |
                 |-- 调用 _get_fragments -->|-- _resolve_fragments ---->|                             |
                 |                          |   (执行 generator/list) ->|                             |
                 |                          |                           |                             |
                 |                          |<-- 返回 URL 迭代生成器 ---|                             |
                 |                          |-- 拼接 BaseURL 与 query --|                             |
                 |                          |-- 产出结构化切片流 ------>|                             |
                 |                                                                                    |
                 \-- download_and_append_fragments_multiple(is_fatal=lambda idx: idx == 0) --------->|
                                                                                                      |-- 并发拉取 Init Segment
                                                                                                      |   (若失败则触发熔断)
                                                                                                      |-- 并发拉取 Media Segments
                                                                                                      \-- 保序组装并写入目标容器

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: DASH (MPD) 解析与下载引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``InfoExtractor._parse_mpd_periods()``
     - ``yt_dlp/extractor/common.py:1640-1845``
     - XML 语法树递归遍历、四级 BaseURL 解析、SegmentTemplate/Timeline 提取
   * - ``InfoExtractor._merge_mpd_periods()``
     - ``yt_dlp/extractor/common.py:1615-1638``
     - 多 Period 格式等价特征归一化、流式分片拼接与字幕合并
   * - ``prepare_template()``
     - ``yt_dlp/extractor/common.py:1710-1740``
     - DASH 模板占位符转译、URL 百分号防冲突安全转义
   * - ``DashSegmentsFD.real_download()``
     - ``yt_dlp/downloader/dash.py:15-60``
     - DASH 分片流调度、外部下载器协议分发与 Init 分片致命性约束
   * - ``DashSegmentsFD._get_fragments()``
     - ``yt_dlp/downloader/dash.py:65-85``
     - 惰性切片 URL 生成器、BaseURL 补全与附加查询参数动态注入

***
小结与下章导读
***

本节全面解构了 ``yt-dlp`` 针对 MPEG-DASH (MPD) 清单与分片传输的底层实现机制，明确了：
1. ISO/IEC 23009-1 四层树型体系结构与 ``BaseURL`` 四级回溯级联继承算法；
2. ``SegmentTemplate`` 动态模板转译机制（占位符转标准格式化、``%`` 字符防冲突转义）；
3. ``SegmentTimeline`` 压缩时间轴的 $S$ 标签连续重复数学推导与切片生成；
4. fMP4 容器初始化头（``ftyp/moov``）作为 ``fragments[0]`` 的置顶注入与 ``is_fatal`` 熔断设计；
5. 多周期（Multi-Period）等价流特征合并与动态直播（Dynamic MPD）滑窗追赶。

至此，**第 4 模块（流媒体分片与下载器协议实现）全量完工**！在接下来的 **第 5 模块（格式选择器与媒体排序算法）** 中，我们将进入 ``yt-dlp`` 极为精妙的元数据决策中枢——第 1 节（``05_format_selection_and_sorting/01_format_dsl_parser_and_ast.rst``）将深入剖析 ``-f / -S`` 格式选择 DSL 的词法分析器、布尔逻辑表达式解析与抽象语法树（AST）求值引擎。
