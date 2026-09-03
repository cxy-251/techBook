========================================================================
第 6 模块：后处理器流水线与媒体重构 (06_postprocessor_and_ffmpeg)
========================================================================

本模块深入剖析 ``yt-dlp`` 在下载完成后的多媒体重构、转码、流封装与元数据注入体系。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_postprocessor_chain_and_lifecycle
   02_ffmpeg_merger_and_fixup
   03_subtitles_and_thumbnail_embedder
   04_metadata_and_chapter_manipulation

模块核心要点
------------

1. **PostProcessor 插件架构与阶段分发**：解剖 `PostProcessor` 基类、`POSTPROCESS_WHEN` 生命周期切入点（`before_dl`, `post_process`, `after_move`, `playlist`）与状态同步。
2. **FFmpeg 封装器与流故障自愈 (Fixup)**：音视频流物理合成 (`FFmpegMergerPP`)、非等比像素修复 (`FFmpegFixupStretchedPP`)、AAC 时间戳断裂修复 (`FFmpegFixupM3u8PP`) 与 MP4 重复 MOOV 修复 (`FFmpegFixupDuplicateMoovPP`)。
3. **字幕转换与封面图原子注入**：VTT/SRT/ASS 格式转换、软字幕流封装 (`FFmpegEmbedSubtitlePP`) 与原子写入。
4. **元数据、章节与 SponsorBlock 处理**：精确时间范围视频裁剪 (`FFmpegSplitChaptersPP`)、SponsorBlock API 对接与文件系统扩展属性 (XAttr) 写入。
