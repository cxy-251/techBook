====================================================================
yt-dlp 多媒体流媒体引擎内核架构与逆向对抗全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书目录导航
   :numbered:

   ROADMAP
   01_architecture_and_lifecycle/index
   02_networking_and_traffic/index
   03_extractor_framework_and_pipeline/index
   04_downloader_and_protocols/index
   05_format_selection_and_sorting/index
   06_postprocessor_and_ffmpeg/index
   07_reverse_engineering_and_js_engine/index

专著简介与架构全景
==================

本书是一本以现代开源流媒体提取与下载工业级引擎 ``yt-dlp`` 核心源码为基础，自顶向下、由表及里剖析现代多媒体网络协议、音视频流分片组装、动态爬虫与逆向解密系统的硬核技术专著。

全书坚持“源码级真实实现与网络/协议物理层优先”原则，摒弃浅层命令参数罗列，深入 Python 异步与多协议分发控制模型、HTTP/HTTPS/TLS 协议栈指纹模拟、HLS/DASH 分片时间线索引对齐、FFmpeg 流多路复用与自愈机制，以及基于 JS 引擎/AST 的反爬签名对抗链路，完整还原现代复杂 Web 多媒体生态的工程全貌。

核心知识模块拓扑
----------------

1. **请求生命周期与调度控制器 (01_architecture_and_lifecycle)**
   - CLI 与 API 双入口控制、参数解析模型 (parseOpts/validate_options) 与兼容层转换
   - YoutubeDL 核心控制器的生命周期状态机、上下文管理与插件/钩子注册总线
   - 端到端调度流水线：``extract_info`` -> ``process_ie_result`` -> ``process_video_result``
   - 输出模板引擎 (Outtmpl) 的 AST 语法树遍历、算术求值与安全沙箱防护
   - 下载归档 (Download Archive) 幂等性控制与跨平台文件锁机制

2. **网络请求层与协议栈适配 (02_networking_and_traffic)**
   - RequestDirector 架构：多后端 RequestHandler (`urllib`, `requests`, `curl_cffi`, `websockets`) 优先级分发
   - 浏览器指纹伪装：ImpersonateTarget 与 TLS Client Hello / JA3 / JA4 握手特征模拟
   - CookieJar 多浏览器凭证解密提取 (DPAPI/Keychain/SecretStorage) 与安全跨域作用域隔离
   - 智能代理池、X-Forwarded-For 地理欺骗与网络故障指数退避重试算法

3. **InfoExtractor 抽象与解析流水线 (03_extractor_framework_and_pipeline)**
   - InfoExtractor 基类抽象、双向绑定机制与 ``_real_extract`` 核心范式
   - URL 正则路由分发系统、优先级匹配与 GenericIE 降级熔断策略
   - Web 页面结构化解析、Microdata/JSON-LD 提取与健壮容错容灾机制
   - 播放列表流式生成器、PagedList/LazyList 惰性求值与内存边界保护

4. **流媒体分片与下载器协议实现 (04_downloader_and_protocols)**
   - FileDownloader 基类多态体系、协议探测自适应挂载与并发控制
   - 原生 HTTP/HTTPS 断点续传、分块传输 (Chunked Transfer) 与精准限速令牌桶
   - Native HLS (M3U8) 解析器：AES-128-CBC 动态解密、DISCONTINUITY 断点缝合
   - DASH (MPD) XML 清单树解析、SegmentTimeline 索引计算与动态直播滑动窗口

5. **格式选择器与媒体排序算法 (05_format_selection_and_sorting)**
   - 格式选择 DSL 语法解析器：Tokenize 词法流、布尔表达式与 AST 过滤树构建
   - FormatSorter 多维度自适应权重排序算法 (分辨率/码率/编码/声道/HDR/协议)
   - 音视频轨道兼容性矩阵 ``get_compatible_ext``、动态合并与容器规范判定

6. **后处理器流水线与媒体重构 (06_postprocessor_and_ffmpeg)**
   - PostProcessor 插件链结构、``POSTPROCESS_WHEN`` 多生命周期切入点
   - FFmpeg 子进程封装、音视频流多路复用 (FFmpegMergerPP) 与流故障自愈 (Fixup 修复链)
   - 字幕多格式转换与原子级流内嵌 (EmbedSubtitlePP)、封面图裁剪与元数据注入
   - 章节切分 (SplitChaptersPP)、SponsorBlock 片段智能剔除与文件系统扩展属性写入

7. **逆向对抗、JS 执行引擎与反爬突破 (07_reverse_engineering_and_js_engine)**
   - 外部 JS 运行时架构 (Deno/Node/Bun/QuickJS) 与进程间 IPC 沙箱通信
   - YouTube 播放器脚本逆向：AST 语法树静态分析、n-parameter 算法提取与 sig 解密
   - WebAssembly (WASM) 逆向分析、动态混淆与 VM 虚拟机反混淆还原
   - Proof of Origin (PO Token) 签名对抗、BotGuard 探测防御与设备凭证模拟
