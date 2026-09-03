========================================================================
第 1 模块：请求生命周期与调度控制器 (01_architecture_and_lifecycle)
========================================================================

本模块深入剖析 ``yt-dlp`` 顶层中枢控制系统的架构设计与运行机制。作为整个引擎的大脑，``YoutubeDL`` 类统筹管理了参数解析、生命周期状态机、插件系统、异常处理模型、输出模板解析与文件归档幂等性。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_youtubedl_entry_and_params
   02_extract_info_and_process_pipeline
   03_outtmpl_and_template_formatting
   04_download_archive_and_deduplication

模块核心要点
------------

1. **入口控制与参数解析系统**：剖析从命令行参数解析 (`parseOpts`)、兼容性参数修正 (`set_compat_opts`) 到强类型校验 (`validate_options`) 的全链路。
2. **控制器生命周期与状态机**：详细解剖 ``YoutubeDL`` 的上下文管理器、全局状态维护、控制流异常拓扑与日志系统。
3. **调度流水线**：梳理 ``extract_info`` -> ``process_ie_result`` -> ``process_video_result`` -> ``process_info`` 的多级解包与分发拓扑。
4. **输出模板引擎 (Outtmpl)**：深度分析 AST 格式化字段提取、算术运算、日期与正则匹配以及沙箱防命令注入机制。
5. **下载归档与去重幂等**：深入剖析基于哈希与 ID 的 ``download_archive`` 持久化机制及并发文件锁设计。
