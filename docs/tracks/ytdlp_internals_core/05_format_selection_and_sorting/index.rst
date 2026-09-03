========================================================================
第 5 模块：格式选择器与媒体排序算法 (05_format_selection_and_sorting)
========================================================================

本模块深入剖析 ``yt-dlp`` 革命性的多媒体流格式选择语言 (Format Selection DSL) 与智能多维排序权重算法。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_format_dsl_parser_and_ast
   02_format_sorter_and_ranking
   03_stream_filtering_and_compatibility

模块核心要点
------------

1. **Format DSL 语法解析器**：基于 `tokenize` 词法流的自顶向下解析器、布尔逻辑组合 (`/`, `+`, `,`)、过滤选择器与 AST 树构建。
2. **FormatSorter 多维权重排序模型**：基于 15+ 维度的格式排序算法 (分辨率、码率、帧率、HDR、编码效率、语言偏好、协议稳定性)。
3. **音视频流合并与容器兼容性判定**：`_merge` 逻辑、音频/视频轨道分离、`get_compatible_ext` 格式兼容性计算与多音轨/多视轨过滤。
