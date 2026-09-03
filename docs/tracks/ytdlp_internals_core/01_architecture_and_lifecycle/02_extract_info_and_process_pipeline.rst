========================================================================================
01.02 extract_info 调度中枢与多态结果流水线解析
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们深入剖析了 ``YoutubeDL`` 控制器的实例化过程、参数编译管线与上下文生命周期状态机。当调用方执行 ``ydl.download([url])`` 时，控制器正式进入数据抽取与业务调度中枢。本节将深入 ``YoutubeDL.py`` 的核心调度引擎——解剖 ``extract_info`` 是如何驱动提取器进行 URL 路由匹配、如何通过 ``process_ie_result`` 统一多态实体对象（``video``、``url``、``url_transparent``、``playlist``、``multi_video``），以及 ``process_video_result`` 是如何将异构元数据规整为严密的媒体实体图谱。

***
extract_info 调度中枢与异常容灾体系
***

``extract_info`` 是 ``yt-dlp`` 整个提取流水线的顶层统一入口。其核心函数签名如下：

.. code-block:: python

   def extract_info(self, url, download=True, ie_key=None, extra_info=None,
                    process=True, force_generic_extractor=False):
       """
       抽取并返回目标 URL 对应的多媒体信息字典 (InfoDict)
       @param url          目标音视频或播放列表 URL
       @param download     提取完成后是否立即触发物理下载与后处理
       @param process      是否就地递归解析所有未决引用 (URL / Playlist Items)
       @param ie_key       显式指定使用的 InfoExtractor 唯一键名
       @param extra_info   级联传递的额外上下文元数据字典
       """

.. code-block:: text
   :caption: extract_info 路由与异常重试状态转换

   输入目标 URL (例如 "https://www.youtube.com/watch?v=...")
             |
             v
   +------------------------------------------------------------------+
   | 1. 提取器匹配循环 (Extractor Selection Loop)                     |
   |    - 遍历 self._ies (或指定 ie_key)                              |
   |    - 调用 ie.suitable(url) 正则判定                              |
   +----------------------------------+-------------------------------+
                                      | 命中首个合规 IE (如 YoutubeIE)
                                      v
   +------------------------------------------------------------------+
   | 2. 预检快速过滤 (Archive Pre-check)                              |
   |    - ie.get_temp_id(url) 快速提取 ID                             |
   |    - 判定 in_download_archive() --> 若已存在且 break_on_existing  |
   |      则快速短路终止                                              |
   +----------------------------------+-------------------------------+
                                      | 未归档，继续
                                      v
   +------------------------------------------------------------------+
   | 3. __extract_info (执行受保护的实体提取)                         |
   |    - _apply_header_cookies(url) 注入域名受限 Cookie              |
   |    - ie.extract(url) 执行真实网页抓取与解密                      |
   |    - 捕获异常: ReExtractInfo, GeoRestrictedError, ExtractorError  |
   +----------------------------------+-------------------------------+
                                      | 获得原始提取结果 ie_result
                                      v
   +------------------------------------------------------------------+
   | 4. 实体规整与分发分流                                             |
   |    - add_default_extra_info(ie_result, ie, url)                  |
   |    - 若 process=True: 进入 process_ie_result 多态分发管线        |
   |    - 若 process=False: 直接返回未展开的原始字典                  |
   +----------------------------------+-------------------------------+

核心容灾机制与异常重试拦截器 (`_handle_extraction_exceptions`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在实际网络抓取中，直播未开始、地理区域封锁（Geo-blocking）、临时签名过期以及限流是常态。``yt-dlp`` 在 ``__extract_info`` 外层包裹了装饰器 ``_handle_extraction_exceptions``，构建了高韧性重试状态机：

1. **动态首播等待 (`_wait_for_video` 与 `ReExtractInfo`)**：
   当视频属于预告首播（``live_status == 'is_upcoming'``）且配置了 ``--wait-for-video (min, max)`` 时，调度器计算 ``diff = release_timestamp - time.time()``，进入倒计时睡眠循环。等待窗口结束后抛出 ``ReExtractInfo`` 异常，装饰器捕获后自动重新触发 ``ie.extract(url)``，实现无缝首播追赶。
2. **地理封锁探测 (`GeoRestrictedError`)**：
   当提取器抛出 ``GeoRestrictedError`` 时，装饰器通过 ``ISO3166Utils.short2full`` 将受限国家代码自动翻译为可读地区清单，并给出代理建议（如 ``--proxy`` 或 ``--geo-bypass-country``）。
3. **熔断与容错控制**：
   若全局配置了 ``ignoreerrors=True``，常规 ``ExtractorError`` 会被转化为日志输出并将 ``self._download_retcode`` 置为 1，确保批量处理或播放列表遍历不会因个别视频失效而整体崩溃。

---
多态实体解包机制：process_ie_result
---

``InfoExtractor.extract()`` 返回的结果并不是单一结构的静态对象，而是高度动态的“多态实体字典（Polymorphic InfoDict）”。``process_ie_result`` 根据实体内部的关键标识字段 ``_type`` 展开多态分发。

.. list-table:: _type 实体类型特征与分发行为矩阵
   :widths: 20 22 30 28
   :header-rows: 1

   * - 实体类型 (``_type``)
     - 典型产生场景
     - 核心载荷字段
     - 控制器调度与处理行为
   * - ``video`` (默认)
     - 单一视频/音频页面
     - ``id``, ``title``, ``formats``, ``url``
     - 进入 ``process_video_result`` 执行流选择、下载与后处理
   * - ``url``
     - 搜索结果、重定向链接、第三方短链
     - ``url``, ``ie_key``
     - 递归调用 ``extract_info(url, ie_key)`` 进行二次深度提取
   * - ``url_transparent``
     - 嵌入式页面（如博客嵌入 YouTube）
     - ``url``, ``ie_key``, 外层覆盖元数据
     - 提取目标 URL，并将外层标题/封面图与内层实体深度合并
   * - ``playlist``
     - 频道、播放列表、合集
     - ``entries`` (迭代器/列表), ``id``, ``title``
     - 进入 ``__process_playlist`` 进行流式遍历与分页解包
   * - ``multi_video``
     - 多镜头/多视角视频包
     - ``entries``, ``id``, ``title``
     - 处理流程与 playlist 类似，但不参与外部列表计数
   * - ``compat_list``
     - 历史遗留提取器返回的纯列表
     - ``entries: List[dict]``
     - 触发向后兼容警告，逐项修补元数据并递归分发

url_transparent 跨层元数据合并拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在当代 Web 架构中，一个视频可能被嵌入在第三方门户新闻中，外部页面往往附带了更精确的本地化标题或封面图，而视频流本身托管于 YouTube 或 Vimeo。``url_transparent`` 机制正是为此而生：

.. code-block:: text
   :caption: url_transparent 元数据合并流向

   外层页面解析结果 (url_transparent)
   [外层元数据: title="独家专访", description="本地新闻描述", url="https://vimeo.com/..."]
                           |
                           v
   控制器提取内层视频实体: inner_info = extract_info(url, download=False, process=False)
   [内层元数据: title="Vimeo 原生英文名", formats=[...], uploader="ChannelA"]
                           |
                           v
   执行属性安全过滤与继承 (Exempted Fields: _type, url, ie_key, id, extractor):
   inner_info.update(outer_non_exempted_fields)
                           |
                           v
   最终合成实体: [title="独家专访", formats=[...], uploader="ChannelA", _type="video"]
                           |
                           v
   递归重新送入 process_ie_result(final_info)

---
播放列表流式展开与内存边界保护 (__process_playlist)
---

当 ``_type`` 为 ``playlist`` 或 ``multi_video`` 时，播放列表可能包含数万甚至数百万个视频条目（如大型频道或音乐流派索引）。如果直接全量加载到内存，将引发不可控的 OOM（Out Of Memory）。

``yt-dlp`` 通过 ``PlaylistEntries`` 结合 ``LazyList`` 与 ``ChainMap`` 构建了高内聚的流式迭代体系。

.. code-block:: text
   :caption: 播放列表流式管道

   ie_result['entries'] (生成器 Generator / 惰性可迭代对象)
                           |
                           v
   all_entries = PlaylistEntries(self, ie_result)
   entries = orderedSet(all_entries.get_requested_items(), lazy=True)
                           |
                           v 逐项迭代 (for i, (playlist_index, entry) in enumerate(entries):)
   +------------------------------------------------------------------+
   | 1. ChainMap 上下文级联                                           |
   |    entry_copy = ChainMap(entry, common_info, {                   |
   |        'playlist_index': playlist_index,                         |
   |        'playlist_autonumber': i + 1,                             |
   |    })                                                            |
   +----------------------------------+-------------------------------+
                                      |
                                      v
   +------------------------------------------------------------------+
   | 2. match_filter 快速断言                                         |
   |    - _match_entry(entry_copy, incomplete=True)                   |
   |    - 提早跳过不符合日期/播放量条件的条目                         |
   +----------------------------------+-------------------------------+
                                      |
                                      v
   +------------------------------------------------------------------+
   | 3. __process_iterable_entry(entry, download, extra_info)         |
   |    - 递归调用 process_ie_result 完成单项下载与落盘               |
   +----------------------------------+-------------------------------+
                                      |
                                      v
   +------------------------------------------------------------------+
   | 4. 连续错误熔断控制                                              |
   |    - 失败计数 failures += 1                                      |
   |    - 若 failures >= skip_playlist_after_errors 则立即跳出循环    |
   +----------------------------------+-------------------------------+

内存驻留策略控制 (`extract_flat`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了平衡极速抓取与内存开销，``extract_flat`` 参数控制着播放列表条目的保留深度：

* ``extract_flat=False``（API 默认）：完全展开并保持解析后的全部条目。
* ``extract_flat='discard'`` / ``'discard_in_playlist'``（CLI 默认优化）：在迭代完成并落盘单个视频后，立即从父级列表引用中剔除该条目实体，确保整个解析进程的内存占用始终保持在常数级 :math:`O(1)`。

---
视频实体图谱规整与选流决议 (process_video_result)
---

当实体最终确认为单一 ``video`` 时，进入 ``process_video_result()``。该方法是多媒体数据结构走向物理落盘前最关键的清洗与决策中枢。

.. code-block:: text
   :caption: process_video_result 流水线十二步规整

   原始 Video InfoDict
          |
          v
   [Step 1: ID 与数值字段类型强转] ---> 强制确保 id 为 str，view_count/duration 为 int/float
          |
          v
   [Step 2: 章节元数据插值补齐]     ---> 自动补齐首章节 start_time=0 与未命名章节标题
          |
          v
   [Step 3: 封面图数组归一化与排序] ---> _sanitize_thumbnails: 补齐 resolution 并按 preference 排序
          |
          v
   [Step 4: 通用派生字段注入]       ---> _fill_common_fields: 格式化 duration_string, upload_date
          |
          v
   [Step 5: 字幕与自动字幕抽取]     ---> process_subtitles: 匹配语言正则，筛选指定格式字幕
          |
          v
   [Step 6: DRM 探测与不可播过滤]   ---> 检测 has_drm，非 allow_unplayable 模式下自动剔除受保护流
          |
          v
   [Step 7: 格式数组属性完备化]     ---> 自动推导 acodec/vcodec、aspect_ratio、dynamic_range(SDR/HDR)
          |
          v
   [Step 8: 格式数组排序 (FormatSort)] -> FormatSorter: 根据 15+ 维权重对 formats 执行降序排列
          |
          v
   [Step 9: 歧义 format_id 唯一化]  ---> 检测重复 format_id 并自动重命名为 "format_id-0", "format_id-1"
          |
          v
   [Step 10: pre_process 预处理器]  ---> 执行 MetadataParserPP 等 pre_process / after_filter 插件
          |
          v
   [Step 11: 选流决议与交互选择]    ---> format_selector(formats) 编译执行，输出最佳音视频组合
          |
          v
   [Step 12: 物理切片与分发下载]    ---> 遍历 formats_to_download 与 download_ranges，分发至 process_info()

章节时间线自动补齐算法
~~~~~~~~~~~~~~~~~~~~~~

很多提取器返回的章节数据存在起始点缺失或首段偏移。``yt-dlp`` 采用滑动窗口插值算法对 ``chapters`` 列表进行拓扑闭包：

.. code-block:: python

   chapters = info_dict.get('chapters') or []
   if chapters and chapters[0].get('start_time'):
       chapters.insert(0, {'start_time': 0})

   dummy_chapter = {'end_time': 0, 'start_time': info_dict.get('duration')}
   for idx, (prev, current, next_) in enumerate(zip(
           (dummy_chapter, *chapters), chapters, (*chapters[1:], dummy_chapter), strict=False), 1):
       if current.get('start_time') is None:
           current['start_time'] = prev.get('end_time')
       if not current.get('end_time'):
           current['end_time'] = next_.get('start_time')
       if not current.get('title'):
           current['title'] = f'<Untitled Chapter {idx}>'

该算法通过在列表头尾插入虚拟哨兵（``dummy_chapter``），以单次三元滑动遍历（``prev, current, next_``）修复了所有断裂的章节时间戳，为后续 ``FFmpegSplitChaptersPP`` 提供了确定性的切割边界。

---
端到端调用时序与核心源码行级映射
---

.. code-block:: text
   :caption: 实体解包与选流调用时序

   Caller             YoutubeDL             InfoExtractor         FormatSorter         Downloader
     |                    |                       |                     |                  |
     |-- extract_info() ->|                       |                     |                  |
     |                    |-- extract(url) ------>|                     |                  |
     |                    |<-- raw_info ----------|                     |                  |
     |                    |                                             |                  |
     |                    |-- process_ie_result(raw_info)               |                  |
     |                    |    |                                        |                  |
     |                    |    |-- [判断 _type]                         |                  |
     |                    |    |   |-- 'video': process_video_result()  |                  |
     |                    |    |   |    |                               |                  |
     |                    |    |   |    |-- sort_formats() ------------>|                  |
     |                    |    |   |    |<-- sorted_formats ------------|                  |
     |                    |    |   |    |                                                  |
     |                    |    |   |    |-- format_selector(sorted_formats)                |
     |                    |    |   |    |   (计算视频+音频最优流组合)                      |
     |                    |    |   |    |                                                  |
     |                    |    |   |    \-- process_info(target_fmt) --------------------->|
     |                    |    |   |                                    |                  |
     |                    |    |   \-- 'playlist': __process_playlist() |                  |
     |                    |    |        |-- 遍历 entries 逐项流式解包   |                  |
     |                    |    |        \-- 递归调用 process_ie_result  |                  |
     |<-- final_info -----|                                                                |

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 调度流水线核心方法与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心方法
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``extract_info()``
     - ``yt_dlp/YoutubeDL.py:348-385``
     - 顶层抽取中枢、提取器路由循环、归档预检与受保护调用
   * - ``__extract_info()``
     - ``yt_dlp/YoutubeDL.py:461-487``
     - 注入 Cookie 作用域、调用 `ie.extract()` 与直播等待拦截
   * - ``process_ie_result()``
     - ``yt_dlp/YoutubeDL.py:503-605``
     - 多态实体解包分发（video, url, url_transparent, playlist）
   * - ``__process_playlist()``
     - ``yt_dlp/YoutubeDL.py:637-732``
     - 播放列表流式展开、分页惰性求值、内存丢弃与错误熔断
   * - ``process_video_result()``
     - ``yt_dlp/YoutubeDL.py:848-1090``
     - 单视频实体图谱清洗、章节补齐、格式排序与选流决策

***
小结与下章导读
***

本节系统剖析了 ``YoutubeDL`` 的调度中枢与多态实体流转机制，厘清了：
1. ``extract_info`` 对异常状态机的拦截、恢复与首播动态等待；
2. ``process_ie_result`` 针对不同实体类型的多态分发拓扑与嵌套引用解包；
3. ``__process_playlist`` 基于 ``PlaylistEntries`` 的常数级内存保护模型；
4. ``process_video_result`` 对音视频流、章节、字幕的十二步物理清洗管线。

在下一节（``03_outtmpl_and_template_formatting.rst``）中，我们将深入物理落盘前的核心引擎——剖析 ``yt-dlp`` 输出模板解析引擎（Outtmpl），揭示其如何通过词法 AST 解析、算术求值器、格式化宏与沙箱机制，安全生成高度动态的文件存储路径。
