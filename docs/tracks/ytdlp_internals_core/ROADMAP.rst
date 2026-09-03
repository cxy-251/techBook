========================================================================
yt-dlp 多媒体流媒体引擎内核架构与逆向对抗全景深度剖析：工程图谱
========================================================================

.. note:: 单一事实源说明
   本文件是《yt-dlp 多媒体流媒体引擎内核架构与逆向对抗全景深度剖析》全书各章节编写状态与知识依赖的唯一权威图谱。所有自动化写作任务与调度器均以此文件的完成状态作为推进依据。

总体进度概览
============

- **总规划模块数**：7 个核心模块
- **总规划章节数**：28 节深度专著章节
- **已完成章节**：26 节
- **当前写作状态**：模块七第 3 节已完成落盘，下一待施工章节为全书收官之节——模块七第 4 节（``07_reverse_engineering_and_js_engine/04_po_token_and_botguard.rst``：Proof of Origin (PO Token) 签名对抗、BotGuard 探测防御与设备凭证模拟）

.. contents::
   :local:
   :depth: 2

------------------------------------------------------------------------

模块详细进度与章节清单
======================

第 1 模块：请求生命周期与调度控制器 (01_architecture_and_lifecycle)
---------------------------------------------------------------------

- [x] ``01_youtubedl_entry_and_params.rst`` - YoutubeDL 入口控制、参数解析模型 (parseOpts/validate_options)、上下文生命周期状态机与插件/钩子机制
- [x] ``02_extract_info_and_process_pipeline.rst`` - ``extract_info`` 与 ``process_ie_result`` / ``process_video_result`` 核心调度流水线与视频实体图谱解析
- [x] ``03_outtmpl_and_template_formatting.rst`` - 输出模板解析引擎 ``prepare_outtmpl`` / ``evaluate_outtmpl``、AST 字段安全展开与沙箱过滤机制
- [x] ``04_download_archive_and_deduplication.rst`` - 下载归档与幂等控制 ``download_archive``、断点续传锁机制与历史状态持久化

第 2 模块：网络请求层与协议栈适配 (02_networking_and_traffic)
--------------------------------------------------------------

- [x] ``01_request_director_and_handlers.rst`` - RequestDirector 架构：多后端 RequestHandler (`urllib`, `requests`, `curl_cffi`, `websockets`) 优先级分发
- [x] ``02_browser_impersonation_and_tls.rst`` - 浏览器指纹伪装：ImpersonateTarget 与 TLS Client Hello / JA3 / JA4 握手特征模拟
- [x] ``03_cookiejar_and_session_management.rst`` - CookieJar 多浏览器凭证解密提取 (DPAPI/Keychain/SecretStorage) 与安全跨域作用域隔离
- [x] ``04_proxy_and_geo_bypass.rst`` - 智能代理池、X-Forwarded-For 地理欺骗与网络故障指数退避重试算法

第 3 模块：InfoExtractor 抽象与解析流水线 (03_extractor_framework_and_pipeline)
---------------------------------------------------------------------------------

- [x] ``01_info_extractor_base_architecture.rst`` - InfoExtractor 基类抽象、双向绑定机制与 ``_real_extract`` 核心范式
- [x] ``02_url_matching_and_dispatch.rst`` - URL 正则路由分发系统、优先级匹配与 GenericIE 降级熔断策略
- [x] ``03_page_parsing_and_microdata.rst`` - Web 页面结构化解析、Microdata/JSON-LD 提取与健壮容错容灾机制
- [x] ``04_playlist_and_lazy_evaluation.rst`` - 播放列表流式生成器、PagedList/LazyList 惰性求值与内存边界保护

第 4 模块：流媒体分片与下载器协议实现 (04_downloader_and_protocols)
--------------------------------------------------------------------

- [x] ``01_downloader_base_and_dispatch.rst`` - FileDownloader 基类多态体系、协议探测自适应挂载与并发控制
- [x] ``02_http_and_chunked_transfer.rst`` - 原生 HTTP/HTTPS 断点续传、分块传输 (Chunked Transfer) 与精准限速令牌桶
- [x] ``03_hls_m3u8_native_pipeline.rst`` - Native HLS (M3U8) 解析器：AES-128-CBC 动态解密、DISCONTINUITY 断点缝合
- [x] ``04_dash_mpd_and_segment_timeline.rst`` - DASH (MPD) XML 清单树解析、SegmentTimeline 索引计算与动态直播滑动窗口

第 5 模块：格式选择器与媒体排序算法 (05_format_selection_and_sorting)
----------------------------------------------------------------------

- [x] ``01_format_dsl_parser_and_ast.rst`` - 格式选择 DSL 语法解析器：Tokenize 词法流、布尔表达式与 AST 过滤树构建
- [x] ``02_format_sorter_and_ranking.rst`` - FormatSorter 多维度自适应权重排序算法 (分辨率/码率/编码/声道/HDR/协议)
- [x] ``03_stream_filtering_and_compatibility.rst`` - 音视频轨道兼容性矩阵 ``get_compatible_ext``、动态合并与容器规范判定

第 6 模块：后处理器流水线与媒体重构 (06_postprocessor_and_ffmpeg)
------------------------------------------------------------------

- [x] ``01_postprocessor_chain_and_lifecycle.rst`` - PostProcessor 插件链结构、``POSTPROCESS_WHEN`` 多生命周期切入点
- [x] ``02_ffmpeg_merger_and_fixup.rst`` - FFmpeg 子进程封装、音视频流多路复用 (FFmpegMergerPP) 与流故障自愈 (Fixup 修复链)
- [x] ``03_subtitles_and_thumbnail_embedder.rst`` - 字幕多格式转换与原子级流内嵌 (EmbedSubtitlePP)、封面图裁剪与元数据注入
- [x] ``04_metadata_and_chapter_manipulation.rst`` - 章节切分 (SplitChaptersPP)、SponsorBlock 片段智能剔除与文件系统扩展属性写入

第 7 模块：逆向对抗、JS 执行引擎与反爬突破 (07_reverse_engineering_and_js_engine)
----------------------------------------------------------------------------------

- [x] ``01_js_runtime_bridge.rst`` - 外部 JS 运行时架构 (Deno/Node/Bun/QuickJS) 与进程间 IPC 沙箱通信
- [x] ``02_youtube_signature_and_n_sig.rst`` - YouTube 播放器脚本逆向：AST 语法树静态分析、n-parameter 算法提取与 sig 解密
- [x] ``03_wasm_and_dynamic_obfuscation.rst`` - WebAssembly (WASM) 逆向分析、动态混淆与 VM 虚拟机反混淆还原
- [ ] ``04_po_token_and_botguard.rst`` - Proof of Origin (PO Token) 签名对抗、BotGuard 探测防御与设备凭证模拟
