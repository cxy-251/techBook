========================================================================================
06.02 FFmpeg 子进程封装、音视频流多路复用 (FFmpegMergerPP) 与流故障自愈 (Fixup 修复链)
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们解构了 ``yt-dlp`` 后处理器系统的基础架构与 ``POSTPROCESS_WHEN`` 八大生命周期切入点。在实际的多媒体下载任务中，自适应流媒体（DASH / HLS）通常采用视音频分轨传输，下载落盘后得到的是独立的视频切片文件与音频切片文件。此外，由于各平台流媒体切片编码器实现参差不齐，下载得到的原始文件经常存在**非等比像素拉伸（Stretched SAR/DAR）**、**MPEG-TS 混入 MP4 容器**、**AAC ADTS 格式头缺失**、**多 Period 合并后的重复 MOOV atom** 以及**WebSocket 直播时间戳漂移**等工业级故障。``yt-dlp`` 围绕底层多媒体处理巨擘 FFmpeg，构建了工业级的子进程封装抽象 **``FFmpegPostProcessor``**、无损物理混流器 **``FFmpegMergerPP``** 以及流故障自愈体系 **``FFmpegFixup`` 修复链**。本节将深入解密其底层命令构建、流映射拓扑与自愈状态机。

***
FFmpeg 子进程管道封装模型 (FFmpegPostProcessor)
***

``yt-dlp`` 并不直接依赖庞大且绑定 C ABI 的 Python-FFmpeg 动态链接库，而是通过直接操作子进程（Subprocess IPC）的方式与系统的 ``ffmpeg`` / ``ffprobe`` 静态二进制程序进行交互。这种解耦架构保证了在各种极端操作系统环境下的极致便携性与稳定性。

.. code-block:: text
   :caption: FFmpeg 子进程探测与多级参数分发拓扑

   用户配置/环境变量 (--ffmpeg-location)
                   |
                   v FFmpegPostProcessor._determine_executables()
   +-------------------------------------------------------------------------------+
   | 可执行文件探测 (Executable Resolver):                                         |
   |   - 探测系统 PATH 或显式指定路径下的 ffmpeg 与 ffprobe 二进制文件             |
   |   - 缓存可执行文件路径与探针别名 (self.basename, self.probe_basename)         |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v _get_ffmpeg_version()
   +-------------------------------------------------------------------------------+
   | 版本与特性矩阵探针 (Version & Feature Probing):                               |
   |   - 执行 "ffmpeg -bsfs" 解析输出字符串与 libavformat 运行时版本               |
   |   - 构建特性字典 self._features: {fdk: bool, setts: bool, needs_adtstoasc: bool}|
   +---------------------------------------+---------------------------------------+
                                           |
                                           v real_run_ffmpeg()
   +-------------------------------------------------------------------------------+
   | 统一命令执行沙箱 (Execution Sandbox):                                         |
   |   - 注入安全通用标志: -y, -loglevel repeat+info, -movflags +faststart         |
   |   - 文件路径加固: 注入 'file:' 前缀 (阻断冒号协议注入与负号参数攻击)          |
   |   - 分层参数路由: 注入用户 --postprocessor-args (精确匹配 _i1, _o1 等作用域)   |
   |   - Popen IPC 调用与最老源文件 mtime 时间戳还原 (try_utime)                   |
   +-------------------------------------------------------------------------------+

1. 二进制路径解析与特性探针 (_get_ffmpeg_version)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在首次初始化时，基类通过调用 ``ffmpeg -bsfs`` 获取底层支持的比特流过滤器列表与编译元数据：

.. code-block:: python

   # 检查 libavformat 运行时版本与现代特性支持
   mobj = re.search(r'(?m)^\s+libavformat\s+(?:[0-9. ]+)\s+/\s+(?P<runtime>[0-9. ]+)', out)
   lavf_runtime_version = mobj.group('runtime').replace(' ', '') if mobj else None
   self._features_cache[path] = features = {
       'fdk': '--enable-libfdk-aac' in out,               # 是否支持高质量 Fraunhofer FDK AAC
       'setts': 'setts' in out.splitlines(),               # 是否支持免重编码 setts 比特流过滤器 (FFmpeg 4.4+)
       'needs_adtstoasc': is_outdated_version(lavf_runtime_version, '57.56.100', False),
   }

2. 命令安全加固与文件名协议注入防御 (real_run_ffmpeg)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

直接向 FFmpeg 传递文件名存在严重的安全与解析隐患：
* 若文件名中包含冒号（如 ``2026-08-24: Episode 1.mp4``），FFmpeg 会将其误识别为协议前缀（如 ``http:``、``crypto:``）导致打开失败；
* 若文件名以中划线开头（如 ``-video.mp4``），FFmpeg 会将其误解析为命令行开关参数。

``FFmpegPostProcessor`` 设计了严格的参数编码与加固管道：

.. code-block:: python

   @staticmethod
   def _ffmpeg_filename_argument(fn):
       if fn.startswith(('http://', 'https://')):
           return fn
       # 显式添加 'file:' 前缀，强制 FFmpeg 将其作为本地文件处理，并安全放行 '-' (stdout 流式输出)
       return 'file:' + fn if fn != '-' else fn

3. 多级参数作用域路由 (_configuration_args)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对多输入文件（如合并视频轨与音频轨），引擎动态分配参数占位符：
* ``-i`` 输入前缀：针对第 1 个输入应用 ``_i1`` 级参数，针对全局输入应用 ``_i`` 参数；
* 输出参数：默认追加 ``-movflags +faststart``（优化 Web 播放的 moov atom 前置），并路由 ``_o1`` / ``_o`` 用户自定义参数。

---
音视频流物理多路复用引擎 (FFmpegMergerPP)
---

当下载器获取了分立的视频流与音频流后，``FFmpegMergerPP`` 负责将它们无损封装为单一的目标容器（如 MP4、MKV、WebM）。

.. code-block:: text
   :caption: FFmpegMergerPP 物理流映射与封装管道

   输入分轨文件:
   [0] 视频轨 /tmp/video.f137.mp4 (H.264/AVC, 1080p)
   [1] 音频轨 /tmp/audio.f140.m4a (AAC, 128kbps, m3u8_native 抓取)
                            |
                            v FFmpegMergerPP.run() 命令组装
   +-------------------------------------------------------------------------------+
   | ffmpeg -y -loglevel repeat+info \                                             |
   |   -i file:/tmp/video.f137.mp4 \                                               |
   |   -i file:/tmp/audio.f140.m4a \                                               |
   |   -c copy \                                                                   |
   |   -map 0:v:0 \                                                                |
   |   -map 1:a:0 \                                                                |
   |   -bsf:a:0 aac_adtstoasc \  <-- 针对 M3U8 AAC 流自动注入 ADTS 转换过滤器       |
   |   -movflags +faststart \                                                      |
   |   file:/tmp/temp.output.mp4                                                   |
   +---------------------------------------+---------------------------------------+
                            |
                            v 原子级替换与垃圾回收
   1. os.rename('/tmp/temp.output.mp4', '/tmp/output.mp4')
   2. 向上层返回待删除文件: ['/tmp/video.f137.mp4', '/tmp/audio.f140.m4a']

流映射与无损直通 (-c copy)
~~~~~~~~~~~~~~~~~~~~~~~~~~

``FFmpegMergerPP`` 遍历 ``info['requested_formats']`` 中的每一轨：
* 视频流映射：``-map {i}:v:0``；
* 音频流映射：``-map {i}:a:0``；
* 传输参数：配置 ``-c copy``。由于只进行容器封装重构（Remuxing）而不触碰音视频原始 NALU 编码载荷，合并过程仅受磁盘 I/O 限制，通常在数百毫秒内即可完成数 GB 文件的复用。

M3U8 AAC 比特流过滤器自适应修正 (aac_adtstoasc)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HLS (M3U8) 流中的 AAC 音频切片通常带有 ADTS（Audio Data Transport Stream）头部。然而，ISO Base Media File Format（MP4/M4A 容器）规范要求音频使用基于 AudioSpecificConfig 的 ASC 格式头。若直接无损封装，导出的 MP4 文件将在许多播放器中出现音频爆音或静音。

``FFmpegMergerPP`` 在流映射时主动探测音频协议与编码：

.. code-block:: python

   aac_fixup = fmt['protocol'].startswith('m3u8') and self.get_audio_codec(fmt['filepath']) == 'aac'
   if aac_fixup:
       args.extend([f'-bsf:a:{audio_streams}', 'aac_adtstoasc'])

---
流媒体故障自愈体系 (FFmpegFixup 修复链)
---

网络流媒体源文件常常伴随各种格式缺陷。``yt-dlp`` 在 ``YoutubeDL.process_info`` 中设计了动态检测机制，并在后处理队列中自适应挂载 ``FFmpegFixupPostProcessor`` 家族修复插件。

.. list-table:: FFmpegFixup 修复链矩阵与自愈策略
   :widths: 24 28 48
   :header-rows: 1

   * - 自愈后处理器
     - 触发条件与缺陷特征
     - 底层 FFmpeg 自愈命令与操作原理
   * - **``FFmpegFixupStretchedPP``**
     - ``stretched_ratio not in (None, 1)``（非等比像素/宽荧幕变形）
     - ``-aspect {stretched_ratio:f} -c copy``：在不重编码画面的情况下，重写容器视频轨头的显示宽高比（DAR）
   * - **``FFmpegFixupM4aPP``**
     - ``container == 'm4a_dash'``（DASH 音频切片直写 M4A）
     - ``-f mp4 -c copy``：修复 DASH 规范中的非标准音频容器头，转为完全符合 RFC 4337 的 MP4 音频流
   * - **``FFmpegFixupM3u8PP``**
     - MP4/M4A 文件内部实际封装了 MPEG-TS 流或存在畸变 AAC
     - ``-f mp4 -bsf:a aac_adtstoasc -c copy``：重新解复用并封装为标准 MP4，消除 TS 包头与 PES 时钟抖动
   * - **``FFmpegFixupDuplicateMoovPP``**
     - DASH 直播录制或多 Period 合并后存在重复 ``moov`` atom
     - ``-c copy -movflags +faststart``：丢弃冗余历史索引，重新生成单一线性的全局 ``moov`` box
   * - **``FFmpegFixupTimestampPP``**
     - WebSocket 流或分片时间戳乱序/存在负数时间戳（PTS/DTS 错位）
     - 现代模式：``-c copy -bsf setts=ts=TS-STARTPTS -ss 0.001``（极速无损修复）；老旧模式降级：``-vf setpts=PTS-STARTPTS``（重编码修复）
   * - **``FFmpegFixupDurationPP``**
     - 流切片封装导致容器头丢失准确的总时长（Duration）
     - ``-c copy``：重新扫描全局音视频包时间戳，重建正确的容器元数据时长

1. 非等比像素修复 (FFmpegFixupStretchedPP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

部分老旧电视广播源或平台视频（如某些 1440x1080 的 16:9 节目）使用矩形像素存储。若直接播放会被压缩为 4:3 画面。提取器在解析到 ``stretched_ratio`` 后，自愈插件执行元数据重写：

.. code-block:: python

   class FFmpegFixupStretchedPP(FFmpegFixupPostProcessor):
       @PostProcessor._restrict_to(images=False, audio=False)
       def run(self, info):
           stretched_ratio = info.get('stretched_ratio')
           if stretched_ratio not in (None, 1):
               self._fixup('Fixing aspect ratio', info['filepath'], [
                   *self.stream_copy_opts(), '-aspect', f'{stretched_ratio:f}'])
           return [], info

2. 重复 MOOV 修复与 FastStart 优化 (FFmpegFixupDuplicateMoovPP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在多周期（Multi-Period）DASH 下载或直播流片段拼接中，每个分片自身都包含独立的 ``moov`` atom。直接二进制追加会导致生成的文件内部嵌套多个索引头。QuickTime、iOS 原生播放器及 Windows Media Player 遇到此类文件会直接报错拒绝播放。

``FFmpegFixupDuplicateMoovPP`` 执行单遍流拷贝复用，重新解包所有音视频 Sample 并写入单一标准化的文件尾部，随后经 ``-movflags +faststart`` 将整合后的统一 ``moov`` 移至文件头部，达成 100% 播放器兼容。

3. 时间戳重对齐算法 (FFmpegFixupTimestampPP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 WebSocket 直播抓取等弱时钟协议流，数据包常常携带错误的绝对时间戳偏移。自愈插件利用现代 FFmpeg 的 ``setts`` 比特流过滤器，在毫秒级时间内重置起始时间戳（$PTS = PTS - STARTPTS$），并微调剪裁（``-ss 0.001``）丢弃首帧前破损的残缺数据包。

---
Fixup 修复链动态决策状态机
---

在 ``YoutubeDL.process_info()`` 中，引擎通过闭包函数 ``fixup()`` 评估修复策略：

.. code-block:: python

   def fixup():
       fixup_policy = self.params.get('fixup')  # 'detect_or_warn' (默认) / 'never' / 'warn' / 'force'
       if fixup_policy in ('ignore', 'never'):
           return

       # 动态断言辅助器
       def ffmpeg_fixup(cndn, msg, cls):
           if not (do_fixup and cndn):
               return
           if fixup_policy == 'warn':
               self.report_warning(f'{vid}: {msg}')
               return
           pp = cls(self)
           if pp.available:
               # 动态插入后处理器队列
               info_dict['__postprocessors'].append(pp)
           else:
               self.report_warning(f'{vid}: {msg}. Install ffmpeg to fix this automatically')

       # 依次触发 Stretched / M4A / M3U8 / DuplicateMoov / Timestamp 判定
       ...

---
端到端混流与自愈执行时序图与源码映射
---

.. code-block:: text
   :caption: FFmpegMerger 与 Fixup 自愈端到端执行调用链

   YoutubeDL.process_info()
            |
            |-- 1. 判定多轨下载 -> 配置 info_dict['__files_to_merge']
            |-- 2. 运行 fixup() 状态机 -> 将 FFmpegFixup*PP 注入 __postprocessors
            |
            v 调用 post_process(dl_filename, info_dict)
   +-------------------------------------------------------------------+
   | 阶段 1: FFmpegMergerPP.run()                                      |
   |   - 扫描视频与音频分轨                                            |
   |   - 注入 -map 与 aac_adtstoasc                                    |
   |   - 执行 -c copy 极速混流 -> 产出 temp.output.mp4                 |
   |   - 登记待删除分轨源文件列表                                      |
   +---------------------------------+---------------------------------+
                                     |
                                     v 管道传递至下一个修复插件
   +-------------------------------------------------------------------+
   | 阶段 2: FFmpegFixupDuplicateMoovPP / M3U8PP.run()                 |
   |   - 检测是否存在 MOOV 重复或 MPEG-TS 容器污染                     |
   |   - 执行流重构自愈 -> 产出规范化 MP4 容器                         |
   +---------------------------------+---------------------------------+
                                     |
                                     v
   +-------------------------------------------------------------------+
   | 阶段 3: 垃圾回收与原子重命名                                      |
   |   - os.replace(temp_filename, final_filename)                     |
   |   - 清理所有源分轨临时文件                                        |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: FFmpeg 封装与自愈引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``FFmpegPostProcessor``
     - ``yt_dlp/postprocessor/ffmpeg.py:50-240``
     - FFmpeg/FFprobe 二进制探针、特性探测与安全参数路由引擎
   * - ``real_run_ffmpeg()``
     - ``yt_dlp/postprocessor/ffmpeg.py:195-235``
     - 统一命令行调度、``file:`` 前缀防注入、IPC 管道执行与 utime 还原
   * - ``FFmpegMergerPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:420-450``
     - 视音频分轨物理复用（Muxing）、``-map`` 路由与 ``aac_adtstoasc`` 注入
   * - ``FFmpegFixupStretchedPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:460-475``
     - 非等比像素自愈，重写视频轨显示宽高比（``-aspect``）
   * - ``FFmpegFixupM3u8PP``
     - ``yt_dlp/postprocessor/ffmpeg.py:485-510``
     - HLS MPEG-TS 混入 MP4 容器自愈与 AAC 比特流头重构
   * - ``FFmpegFixupDuplicateMoovPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:530-545``
     - DASH 直播/多 Period 合并后重复 MOOV atom 净化与 FastStart 优化
   * - ``YoutubeDL.process_info (fixup)``
     - ``yt_dlp/YoutubeDL.py:2730-2770``
     - 流故障特征动态判定状态机与 Fixup 插件自动化挂载

***
小结与下章导读
***

本节全面剖析了 ``yt-dlp`` 基于 FFmpeg 的媒体重构与自愈内核，明确了：
1. ``FFmpegPostProcessor`` 二进制探针体系、特性字典缓存与 ``file:`` 协议防注入加固模型；
2. ``FFmpegMergerPP`` 基于 ``-c copy`` 的多轨无损物理复用与 M3U8 AAC 比特流自适应转译；
3. ``FFmpegFixup`` 家族在非等比像素、M4A 容器纠偏、MPEG-TS 混入、重复 MOOV atom 及时间戳漂移五大场景下的自愈算法；
4. ``fixup()`` 决策状态机在主下载生命周期中的自动化挂载与执行。

除音视频流本身的物理复用外，现代视频往往还伴随着多语言字幕轨与高清封面图。在下一节（``06_postprocessor_and_ffmpeg/03_subtitles_and_thumbnail_embedder.rst``）中，我们将深入解密 **字幕多格式转换（VTT/SRT/ASS）、软字幕原子级流内嵌（``FFmpegEmbedSubtitlePP``）与封面图裁剪注入（``EmbedThumbnailPP``）**。
