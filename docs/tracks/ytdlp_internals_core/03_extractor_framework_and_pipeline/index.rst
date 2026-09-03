========================================================================
第 3 模块：InfoExtractor 抽象与解析流水线 (03_extractor_framework_and_pipeline)
========================================================================

本模块深入剖析 ``yt-dlp`` 最核心的爬虫与多媒体信息提取框架。``InfoExtractor`` 抽象体系支撑着上千个多媒体站点的解析适配与海量异构网页的结构化提取。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_info_extractor_base_architecture
   02_url_matching_and_dispatch
   03_page_parsing_and_microdata
   04_playlist_and_lazy_evaluation

模块核心要点
------------

1. **InfoExtractor 基类体系**：解剖 `InfoExtractor` 核心属性 (`_VALID_URL`, `_TESTS`)、生命周期方法 (`_real_extract`) 与向 `YoutubeDL` 控制器的双向绑定。
2. **URL 路由分发机制**：高效正则表达式匹配算法、IE 优先级注册、GenericIE 智能降级与重定向探测。
3. **网页解析与容错提取机制**：`_search_regex`、`_search_json`、`_parse_json` 容错提取工具集，以及 OpenGraph、Microdata、JSON-LD 标准元数据提取引擎。
4. **播放列表与惰性求值模型**：基于 `PlaylistEntries` 与 `LazyList` 的流式生成器架构，实现超大规模播放列表的零内存暴涨流式处理。
