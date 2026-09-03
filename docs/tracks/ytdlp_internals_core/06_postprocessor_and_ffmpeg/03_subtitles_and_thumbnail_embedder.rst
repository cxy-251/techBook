========================================================================================
06.03 字幕多格式转换与原子级流内嵌 (EmbedSubtitlePP)、封面图裁剪与元数据注入
========================================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们解构了后处理器系统的插件链生命周期模型以及 ``FFmpegMergerPP`` / ``FFmpegFixup`` 对音视频分立流的无损物理复用与流故障自愈体系。然而，现代完整的多媒体资产不仅包含视音频本体，更囊括了多语言外挂字幕、高清封面图（Album Art / Cover Art）以及丰富结构化的节目元数据（Title, Artist, Album, Chapters, InfoJSON）。如果单纯将字幕与封面作为松散文件散落在文件系统中，不仅难以管理，且在移动设备、智能电视和流媒体服务器（如 Jellyfin, Plex, Emby）中极易丢失关联。``yt-dlp`` 构建了一套工业级的原子化内嵌引擎：涵盖字幕多格式转换器 **``FFmpegSubtitlesConvertorPP``**、多语言软字幕流内嵌器 **``FFmpegEmbedSubtitlePP``**、多后端自适应封面注入器 **``EmbedThumbnailPP``** 以及全局元数据与章节注入器 **``FFmpegMetadataPP``**。本节将全面剖析其底层封装原理与多格式转换算法。

***
字幕多格式转换流水线与容器兼容性矩阵 (FFmpegSubtitlesConvertorPP)
***

各流媒体平台分发的字幕格式极具异构性（YouTube 常用 WebVTT 或 JSON3，Netflix/VOD 平台常用 TTML/DFXP，动画与动漫平台常用 ASS/SSA，传统广播常用 SAMI/SRT）。不同视频封装容器对内嵌字幕的编解码器有着严苛的标准限制。

.. list-table:: 视频封装容器与内嵌字幕格式兼容性矩阵
   :widths: 18 22 25 35
   :header-rows: 1

   * - 目标容器扩展名
     - 原生支持字幕格式
     - FFmpeg 内部编码器 (Codec)
     - 限制与特殊行为
   * - **MP4 / M4V / MOV**
     - Timed Text (``.srt`` 转译)
     - ``mov_text`` (3GPP TS 26.245)
     - 严禁嵌入 ASS/SSA 复杂样式字幕；仅支持纯文本与简单加粗/斜体
   * - **WebM**
     - WebVTT (``.vtt``)
     - ``webvtt``
     - 仅支持 WebVTT 格式；嵌入 SRT 或 ASS 会直接被 WebM 解复用器拒绝
   * - **MKV / MKA**
     - ASS, SSA, SRT, VTT, TTML
     - ``copy`` (全格式透传)
     - Matroska 容器支持任意格式字幕流以原生结构无损封装为独立 Track
   * - **MP3 / AAC**
     - 不支持内嵌流字幕
     - N/A
     - 仅支持 ID3v2 歌词标签（USLT / SYLT）

1. DFXP / TTML 语法树解析与 SRT 降级生成 (dfxp2srt)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于广播级 XML 字幕（TTML / DFXP），直接调用 FFmpeg 转码常常因命名空间（Namespaces）混乱导致解析失败。``yt-dlp`` 在 ``yt_dlp/utils/_utils.py`` 中内置了纯 Python 编写的 ``dfxp2srt`` 原生状态机解析器：

.. code-block:: python

   # 1. 消除老旧 DFXP 命名空间冲突
   for k, v in LEGACY_NAMESPACES:
       for ns in v:
           dfxp_data = dfxp_data.replace(ns, k)

   # 2. 遍历 <style> 节点构建样式字典 (颜色, 字号, 加粗, 斜体)
   for style in dfxp.findall('.//ttml:style'):
       styles[style_id] = extract_tts_properties(style)

   # 3. 递归扫描 <p> 段落并计算毫秒级时间戳 (begin, end, dur)
   for para, index in zip(paras, itertools.count(1)):
       begin_time = parse_dfxp_time_expr(para.attrib.get('begin'))
       end_time = parse_dfxp_time_expr(para.attrib.get('end')) or (begin_time + parse_dfxp_time_expr(para.attrib.get('dur')))
       out.append(f'{index}
{srt_time(begin_time)} --> {srt_time(end_time)}
{parse_node(para)}

')

2. 字幕格式动态转码 (FFmpegSubtitlesConvertorPP.run)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户指定 ``--convert-subs srt`` 或目标容器要求特定字幕格式时，``FFmpegSubtitlesConvertorPP`` 执行流式转换：

.. code-block:: python

   class FFmpegSubtitlesConvertorPP(FFmpegPostProcessor):
       def run(self, info):
           subs = info.get('requested_subtitles')
           new_ext = self.format  # 例如 'srt', 'vtt', 'ass'
           new_format = 'webvtt' if new_ext == 'vtt' else new_ext

           for lang, sub in subs.items():
               old_file = sub['filepath']
               new_file = replace_extension(old_file, new_ext)
               # 若为 DFXP 先经由 Python 原生解析为 SRT，再通过 FFmpeg 桥接
               if sub['ext'] in ('dfxp', 'ttml', 'tt'):
                   srt_data = dfxp2srt(open(old_file, 'rb').read())
                   write_file(replace_extension(old_file, 'srt'), srt_data)
               # 触发 FFmpeg 进行格式转换
               self.run_ffmpeg(old_file, new_file, ['-f', new_format])
               sub['filepath'] = new_file
               sub['ext'] = new_ext

---
多语言软字幕原子级流内嵌 (FFmpegEmbedSubtitlePP)
---

与将字幕硬编码烧录进视频图像（Hardcode / Burn-in，破坏原画且无法关闭）不同，``FFmpegEmbedSubtitlePP`` 采用软字幕（Soft Subtitles）技术——将多语言字幕文件作为独立的字幕轨道（Subtitle Track）复用到多媒体容器中。

.. code-block:: text
   :caption: 多语言字幕流映射与元数据注入拓扑

   输入多媒体与字幕文件:
   [0] 主视频 /tmp/video.mp4 (Video + Audio)
   [1] 英文外挂字幕 /tmp/video.en.vtt
   [2] 中文外挂字幕 /tmp/video.zh-Hans.srt
                            |
                            v FFmpegEmbedSubtitlePP.run() 参数编排
   +-------------------------------------------------------------------------------+
   | ffmpeg -y -loglevel repeat+info \                                             |
   |   -i file:/tmp/video.mp4 \                                                    |
   |   -i file:/tmp/video.en.vtt \                                                 |
   |   -i file:/tmp/video.zh-Hans.srt \                                            |
   |   -c copy \                                  <-- 视音频载荷无损直通            |
   |   -map 0 \                                   <-- 映射主输入全部视音频轨        |
   |   -dn -ignore_unknown \                      <-- 规避未知数据流中断            |
   |   -c:s mov_text \                            <-- (若为 MP4) 强制字幕转为 mov_text|
   |   -map -0:s \                                <-- 剥离源视频中已存在的陈旧字幕轨|
   |   -map 1:0 -metadata:s:s:0 language=eng \    <-- 映射第 1 个字幕并打标 ISO-639 |
   |   -map 2:0 -metadata:s:s:1 language=zho \    <-- 映射第 2 个字幕并打标 ISO-639 |
   |   -metadata:s:s:1 handler_name="Chinese" \   <-- 写入轨道显示名                |
   |   -movflags +faststart \                                                      |
   |   file:/tmp/temp.video.mp4                                                    |
   +---------------------------------------+---------------------------------------+
                            |
                            v 原子级替换与生命周期清理
   1. os.replace('/tmp/temp.video.mp4', '/tmp/video.mp4')
   2. 校验 already_have_subtitle 标志: 若用户未开启 --keep-subs，则安全物理删除外挂字幕文件

多语言 ISO-639-2/T 编码标准化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

播放器（如 VLC, IINA, Apple TV）识别字幕音轨依赖标准的 3 字母 ISO-639-2 代码（如 ``eng``, ``zho``, ``jpn``, ``fra``）。``FFmpegEmbedSubtitlePP`` 自动调用 ``ISO639Utils.short2long(lang)`` 进行规范化转换，确保字幕菜单能够正确显示多语言名称。

---
封面图裁剪、格式纠偏与多后端嵌入引擎 (EmbedThumbnailPP)
---

不同多媒体容器与音频标签规范对封面嵌入（Cover Art / Thumbnail）的技术实现截然不同。为达成 100% 的播放器兼容性并保持极速处理，``EmbedThumbnailPP`` 实现了四种异构后端的分级自适应调用：

.. code-block:: text
   :caption: EmbedThumbnailPP 多后端自适应分发架构

                                  目标文件容器扩展名判定
                                            |
         +--------------------+-------------+------------+--------------------+
         | (MP4 / M4A / MOV)  | (MP3)                    | (MKV / MKA)        | (FLAC / OGG / OPUS)
         v                    v                          v                    v
   +--------------+    +--------------+           +--------------+     +--------------+
   | 后端级联:    |    | FFmpeg ID3v2 |           | FFmpeg 附件  |     | Mutagen 原生 |
   | 1. Mutagen   |    | -id3v2_version 3         | -attach      |     | FLAC Picture |
   | 2. AtomicP.  |    | -metadata:s:v            | -metadata    |     | VorbisComment|
   | 3. FFmpeg    |    | title="Cover"|           | mimetype=... |     | BLOCK_PICTURE|
   +--------------+    +--------------+           +--------------+     +--------------+

1. WebP 签名真伪嗅探与格式自适应修复 (fixup_webp)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

YouTube 等现代 Web 平台普遍采用 WebP 格式分发超高清缩略图，但网络响应头或 URL 扩展名经常被伪装为 ``.jpg``。若未经校验直接将 WebP 写入 MP4 或 MP3 的 ID3 标签，将导致 Windows 资源管理器及主流播放器解码失败崩溃。

``EmbedThumbnailPP`` 在处理前通过 Python 原生 ``imghdr.what()`` 读取图片文件魔数（Magic Number）：

.. code-block:: python

   def fixup_webp(self, info, idx=-1):
       thumbnail_filename = info['thumbnails'][idx]['filepath']
       # 嗅探文件内部二进制头部是否为 RIFF....WEBP
       if imghdr.what(thumbnail_filename) == 'webp':
           webp_filename = replace_extension(thumbnail_filename, 'webp')
           os.replace(thumbnail_filename, webp_filename)
           info['thumbnails'][idx]['filepath'] = webp_filename

若目标容器为 MP4/MP3 等不支持 WebP 封面的格式，进一步调用 ``FFmpegThumbnailsConvertorPP`` 将其无损转换为 PNG 或优化 JPEG（注入 ``-bsf:v mjpeg2jpeg`` 修复 MJPEG 比特流）。

2. MP4 / M4A 容器的三级降级嵌入流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对 MPEG-4 / ISO Base Media 容器，引擎设计了三级稳健回退策略：

* **第一级：Mutagen 原生注入 (零子进程开销)**
  直接在 Python 进程内读写 MP4 的 ``moov.udta.meta.ilst.covr`` atom，耗时小于 10ms，速度比调用外部进程快数十倍：

  .. code-block:: python

     meta = MP4(filename)
     meta.tags['covr'] = [MP4Cover(data=thumb_data, imageformat=MP4Cover.FORMAT_JPEG)]
     meta.save()

* **第二级：AtomicParsley 外部进程注入**
  若 Mutagen 未安装，自动探测系统中的 ``AtomicParsley`` 二进制程序，执行 ``AtomicParsley input.mp4 --artwork thumb.jpg -o temp.mp4``。
* **第三级：FFmpeg 附加视频流模式降级**
  若上述工具均缺失，调用 FFmpeg 将封面作为附着视频流写入（``-map 1 -disposition:v:1 attached_pic``）。

3. FLAC / Ogg / Opus 的 VorbisComment 结构体封装
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于开源音频格式，封面图不能简单作为二进制流追加，而必须遵循 Xiph.org 的 ``METADATA_BLOCK_PICTURE`` 规范：
1. 提取封面图物理分辨率（通过微型探针 ``_get_thumbnail_resolution`` 解析）；
2. 构造 ``Picture()`` 结构体，配置 ``type = 3``（Cover Front，正面封面）、MIME 类型、宽高与色彩深度；
3. 将序列化后的二进制块进行 Base64 编码，写入 Vorbis 文本标签 ``METADATA_BLOCK_PICTURE`` 中。

---
全局元数据流注入与章节重构 (FFmpegMetadataPP)
---

``FFmpegMetadataPP`` 负责将提取阶段收集的数百项元数据结构化写入多媒体容器，使下载的文件在各大媒体管理软件中展现出完整的艺术家、专辑、发行日期及章节索引。

.. code-block:: text
   :caption: FFmpegMetadataPP 多维元数据注入机制

   InfoDict 提取元数据字典
              |
              v _get_metadata_opts(info) 映射转换
   +-------------------------------------------------------------------------------+
   | 基础标签: Title, Artist, Album, Track, Date, Genre, PURL, Description         |
   | 剧集标签: Series, Season_Number, Episode_ID, Episode_Sort                     |
   | 编码优化: -write_id3v1 1 (兼容老旧播放器)                                     |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 章节与附件流生成
   +-------------------------------------------------------------------------------+
   | 1. FFMETADATA1 章节注入: 生成 ;FFMETADATA1 文件并应用 -map_metadata 1         |
   | 2. info.json 附件注入: (仅针对 MKV/MKA) 应用 -attach info.json                |
   | 3. 流级语言打标: -metadata:s:0 language=jpn, -metadata:s:1 language=eng      |
   +-------------------------------------------------------------------------------+

FFMETADATA1 文本生成与章节切分对齐
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于包含章节信息的视频，引擎动态构建内存级 FFMETADATA1 脚本：

.. code-block:: text

   ;FFMETADATA1
   [CHAPTER]
   TIMEBASE=1/1000
   START=0
   END=125000
   title=01. 开场引入与背景说明
   [CHAPTER]
   TIMEBASE=1/1000
   START=125000
   END=450000
   title=02. 核心架构深度剖析

通过 ``-map_metadata 1`` 参数，FFmpeg 将文本文件中的时间区间直接编译为 MP4 ``chpl`` atom 或 MKV Chapters 节点，播放器即可直接显示章节导航进度条。

---
端到端媒体后处理与元数据装配调用链
---

.. code-block:: text
   :caption: 后处理器阶段完整执行调用流

   YoutubeDL.process_info()
            |
            |-- 1. FFmpegMergerPP (音视频物理复用)
            |-- 2. FFmpegSubtitlesConvertorPP (字幕转码为目标格式: WebVTT/SRT)
            |-- 3. FFmpegEmbedSubtitlePP (多语言软字幕内嵌封装)
            |-- 4. EmbedThumbnailPP (WebP 纠偏 -> Mutagen/FFmpeg 封面注入)
            |-- 5. FFmpegMetadataPP (FFMETADATA1 章节 + 基础元数据 + 附件流)
            |-- 6. MoveFilesAfterDownloadPP (移动至用户最终目标目录)
            v
   交付 100% 完整封装、内嵌字幕、带高清封面与章节的成品多媒体文件

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 字幕转换、封面与元数据内嵌核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``FFmpegSubtitlesConvertorPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:939-1014``
     - 字幕格式转码、DFXP/TTML 语法树原生解析降级为 SRT
   * - ``dfxp2srt()``
     - ``yt_dlp/utils/_utils.py:2780-2860``
     - TTML/DFXP XML 状态机解析器、时间戳对齐与样式保留
   * - ``FFmpegEmbedSubtitlePP``
     - ``yt_dlp/postprocessor/ffmpeg.py:581-660``
     - 多语言软字幕流多路复用、ISO-639-2 语言代码打标与原子级替换
   * - ``EmbedThumbnailPP``
     - ``yt_dlp/postprocessor/embedthumbnail.py:30-180``
     - 封面图 WebP 二进制嗅探、Mutagen / AtomicParsley / FFmpeg 多后端级联注入
   * - ``FFmpegThumbnailsConvertorPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:1062-1130``
     - 封面图格式无损转码（PNG / JPEG）、MJPEG 比特流过滤器修复
   * - ``FFmpegMetadataPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:662-820``
     - 全局元数据字段映射、FFMETADATA1 章节文件生成与 MKV JSON 附件内嵌

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 在多媒体资产重构层面的四大核心内嵌组件：
1. ``FFmpegSubtitlesConvertorPP`` 与 ``dfxp2srt`` 实现了全格式字幕在 MP4（``mov_text``）、WebM（``webvtt``）与 MKV（``copy``）之间的无缝兼容转码；
2. ``FFmpegEmbedSubtitlePP`` 建立了多语言软字幕的流映射拓扑与 ISO-639-2/T 元数据打标规范；
3. ``EmbedThumbnailPP`` 打造了涵盖 WebP 魔数嗅探、Mutagen 零开销注入、AtomicParsley 兼容及 VorbisComment 结构体封装的强大封面处理管道；
4. ``FFmpegMetadataPP`` 实现了章节索引、全局 ID3/MP4 标签及 MKV ``info.json`` 附件的完备封装。

在完成了音视频复用、字幕内嵌与封面注入后，面对超长视频或存在大量赞助广告的流媒体，用户往往需要按章节将视频物理切分为独立文件，或者智能剔除冗余广告片段。在下一节（``06_postprocessor_and_ffmpeg/04_metadata_and_chapter_manipulation.rst``）中，我们将深入解构 **精确时间范围视频裁剪（``FFmpegSplitChaptersPP``）、SponsorBlock 片段智能剔除算法与文件系统扩展属性（XAttr）写入机制**。
