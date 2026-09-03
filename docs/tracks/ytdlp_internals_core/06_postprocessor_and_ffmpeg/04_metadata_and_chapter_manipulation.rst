========================================================================================
06.04 章节切分 (SplitChaptersPP)、SponsorBlock 片段智能剔除与文件系统扩展属性写入
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们解构了软字幕内嵌（``FFmpegEmbedSubtitlePP``）、封面图多后端注入（``EmbedThumbnailPP``）以及基于 FFMETADATA1 的全局元数据封装（``FFmpegMetadataPP``）。当音视频文件被完整复用与元数据装配后，面对长达数小时的长视频（如播客、发布会、音乐专辑或课程合集），用户往往希望将其物理切分为按章节命名的独立文件；或者在观看时能够自动规避其中的赞助广告、片头赞助口播与冗余闲聊。此外，为了将媒体来源、原始 URL 及下载元数据深度内嵌到现代操作系统层面，还需要向文件系统写入扩展属性。``yt-dlp`` 研发了三组极为强大的后处理器：基于关键帧对齐的章节切割器 **``FFmpegSplitChaptersPP``**、基于优先队列与时间线拓扑剪枝的广告消除引擎 **``ModifyChaptersPP`` / ``SponsorBlockPP``** 以及跨平台扩展属性注入器 **``XAttrMetadataPP``**。本节将深入剖析其底层算法与实现机理。

***
基于关键帧对齐的物理章节切分流水线 (FFmpegSplitChaptersPP)
***

``FFmpegSplitChaptersPP`` 负责将包含 ``chapters`` 元数据的主媒体文件，无损或者精确帧级切分为独立的章节文件集合。

.. code-block:: text
   :caption: FFmpegSplitChaptersPP 章节切分架构

   主媒体文件 /tmp/album.mp4 (包含 N 个章节元数据)
                        |
                        v FFmpegSplitChaptersPP.run()
   +-------------------------------------------------------------------------------+
   | 1. 章节边界规范化校验 (_fixup_chapters):                                      |
   |    - 补充末尾章节 end_time = _get_real_video_duration(filepath)               |
   |    - 校验 start_time < end_time，剔除时长 <= 0 的异常断片                     |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 关键帧重编码与精确剪辑判定
   +-------------------------------------------------------------------------------+
   | 2. 关键帧注入机制 (force_keyframes):                                          |
   |    - 若开启 --force-keyframes-at-cuts:                                        |
   |      提取所有章节起始时间戳 [t1, t2, ..., tn]                                  |
   |      调用 ffmpeg -force_key_frames t1,t2,... 重新编码切分点关键帧 (GOP 对齐)   |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 遍历切分每一个章节
   +-------------------------------------------------------------------------------+
   | 3. 模板化命名与切分执行:                                                      |
   |    - 计算目标路径: destination = prepare_filename(info, 'chapter')            |
   |      (基于 %(title)s - %(section_number)03d %(section_title)s.%(ext)s)        |
   |    - 构造切片参数: ['-ss', str(start_time), '-t', str(end_time - start_time)] |
   |    - 执行流复制: -map 0 -c copy -dn -ignore_unknown destination               |
   +-------------------------------------------------------------------------------+
                        |
                        v 交付一组按章节命名的独立多媒体文件

1. 关键帧不对齐引发的剪辑伪影与 -force_key_frames
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 H.264 / HEVC 等基于 GOP（Group of Pictures）的帧间压缩编码中，视频流由 I 帧（Intra-coded Frame，关键帧）、P 帧（Predicted Frame）和 B 帧（Bi-directional Frame）组成。
* 若直接使用 ``-c copy`` 执行流切分，切分点（``-ss``）如果落在 P 帧或 B 帧上，由于缺少前序参考 I 帧，切分出的新文件在片头会出现数秒的**花屏、黑屏或音画不同步**；
* ``FFmpegSplitChaptersPP.force_keyframes()`` 通过向 FFmpeg 传递 ``-force_key_frames <timestamps>`` 参数，强制编码器在每个章节的 ``start_time`` 插入关键帧，实现 100% 帧级精确且片头立即可播的无缝切割。

2. 章节动态命名空间展开 (_prepare_filename)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

切分过程中，引擎动态向 ``info`` 字典注入章节特有字段：

.. code-block:: python

   def _prepare_filename(self, number, chapter, info):
       info = info.copy()
       info.update({
           'section_number': number,           # 章节序号 (1, 2, 3...)
           'section_title': chapter.get('title'), # 章节标题
           'section_start': chapter.get('start_time'), # 章节起始秒数
           'section_end': chapter.get('end_time'),     # 章节结束秒数
       })
       # 通过 outtmpl['chapter'] 模板引擎求值输出路径
       return self._downloader.prepare_filename(info, 'chapter')

---
SponsorBlock 智能广告识别与优先队列时间线剪枝 (ModifyChaptersPP)
---

SponsorBlock 是一个广受欢迎的开源众包平台，数百万用户协同标记 YouTube 视频中的赞助广告（Sponsor）、自主推广（Self-promotion）、求点赞互动（Interaction）、片头/片尾赞助口播（Intro/Outro）及非音乐闲聊（Music Offtopic）片段。

``yt-dlp`` 不仅支持拉取这些片段标记为视频章节（``SponsorBlockPP``），更通过 **``ModifyChaptersPP``** 在视频本地落盘阶段直接将这些广告物理切除并重新无缝拼接。

.. code-block:: text
   :caption: SponsorBlock 与章节多区间重叠消除拓扑图

   原始时间轴:
   |=== 正常章节 1 ===|===== 正常章节 2 =====|======= 正常章节 3 =======|
            [-- 赞助广告 1 --]             [-- 自主推广 2 --]
                    |
                    v ModifyChaptersPP 优先队列区间重叠求交算法
   +-------------------------------------------------------------------+
   | 1. 将所有正常章节与赞助区间统一压入小顶堆优先队列 (heapq)        |
   | 2. 状态机动态处理 8 种区间重叠拓扑 (cut, normal, sponsor)         |
   | 3. 计算切除区间 cuts = [[start1, end1], [start2, end2]]           |
   | 4. 重新计算剩余章节的物理持续时长与 start/end 绝对时间戳          |
   | 5. 剔除切分后时长 < 1 秒的超微小碎片章节 (_TINY_CHAPTER_DURATION) |
   +---------------------------------+---------------------------------+
                                     |
                                     v 生成 ffconcat 拼接脚本并驱动 FFmpeg
   +-------------------------------------------------------------------+
   | ffconcat version 1.0                                              |
   | file 'file:/path/video.mp4'                                       |
   | inpoint 0.000000                                                  |
   | outpoint 45.200000                                                |
   | file 'file:/path/video.mp4'                                       |
   | inpoint 75.800000                                                 |
   | outpoint 320.000000                                               |
   +-------------------------------------------------------------------+

优先队列区间剪枝数学算法 (_remove_marked_arrange_sponsors)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当一段赞助广告跨越了两个正常章节的边界，或者多个广告片段存在重叠时，简单的列表遍历无法正确维护时间戳的连续性。``ModifyChaptersPP`` 构建了基于优先队列（Priority Queue / Heap）的区间扫描线算法：

.. code-block:: python

   # 1. 将所有待处理章节（正常章节 + 待切除赞助片段）按 start_time 转化为小顶堆
   chapters = [(c['start_time'], i, c) for i, c in enumerate(chapters)]
   heapq.heapify(chapters)

   _, cur_i, cur_chapter = heapq.heappop(chapters)
   while chapters:
       _, i, c = heapq.heappop(chapters)
       
       # 情况 A: 无重叠区间，直接流式追加
       if cur_chapter['end_time'] <= c['start_time']:
           (append_chapter if 'remove' not in cur_chapter else append_cut)(cur_chapter)
           cur_i, cur_chapter = i, c
           continue

       # 情况 B: 重叠区间 - 严密处理 8 种边界拓扑
       if 'remove' in cur_chapter:
           if 'remove' in c:
               # (cut, cut) 重叠: 扩展当前切除区间的 end_time
               cur_chapter['end_time'] = max(cur_chapter['end_time'], c['end_time'])
           elif cur_chapter['end_time'] < c['end_time']:
               # (cut, normal/sponsor): 截断后续章节的头部，并重新压入堆以保证时间有序性
               c['start_time'] = cur_chapter['end_time']
               c['_was_cut'] = True
               heapq.heappush(chapters, (c['start_time'], i, c))
       elif 'remove' in c:
           # (normal/sponsor, cut): 截断当前章节的尾部
           cur_chapter['_was_cut'] = True
           if cur_chapter['end_time'] <= c['end_time']:
               cur_chapter['end_time'] = c['start_time']
               append_chapter(cur_chapter)
               cur_i, cur_chapter = i, c
               continue
           # 当前章节完全包含该切除区间: 拆分并压回堆中
           ...

外挂字幕时间轴联动裁剪 (_get_supported_subs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当视频主体被切除广告片段后，如果外挂字幕文件不进行同步裁切，字幕将发生严重的时间轴漂移（Desync）。``ModifyChaptersPP`` 会自动扫描 ``requested_subtitles`` 中的所有外挂字幕文件（SRT, VTT, ASS），并对其同步执行相同的 ``ffconcat`` 裁剪与时间戳重映射。

---
文件系统扩展属性注入 (XAttrMetadataPP)
---

操作系统文件系统（如 Linux ext4/btrfs、macOS APFS/HFS+ 以及 Windows NTFS）支持在标准文件数据之外挂载键值对形式的 **扩展属性（Extended Attributes / XAttr）** 或 **备用数据流（Alternate Data Streams / ADS）**。

``XAttrMetadataPP`` 将视频标题、上传者、原始 URL、发布时间等元数据直接写入底层文件系统 inode：

.. list-table:: 各操作系统平台扩展属性映射与字段规范
   :widths: 22 28 50
   :header-rows: 1

   * - 操作系统 / 文件系统
     - 属性命名空间与 Key
     - 写入内容与应用场景
   * - **macOS (APFS/HFS+)**
     - ``com.apple.metadata:kMDItemWhereFroms``
     - 记录视频下载源 URL 与网页 URL，被 Spotlight 索引及 Safari“来源”显示
   * - **Linux (FreeDesktop)**
     - ``user.xdg.comment`` / ``user.xdg.referrer.url``
     - 记录视频描述、来源 URL，遵循 XDG 桌面规范，被 GNOME/KDE 文件管理器读取
   * - **Linux (Dublin Core)**
     - ``user.dublincore.title`` / ``user.dublincore.date``
     - 遵循都柏林核心元数据标准（ISO 15836）
   * - **Windows (NTFS)**
     - ``filename:user.xdg.comment`` (ADS)
     - 写入 NTFS 备用数据流，不影响主数据流，被特定归档工具检索

跨平台 write_xattr 容灾实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``yt_dlp/utils/_utils.py:write_xattr`` 中，引擎通过平台分支与 C 扩展/系统工具级联调用实现无损写入：

.. code-block:: python

   def write_xattr(path, key, value):
       # 1. Windows 平台: 写入 NTFS 备用数据流 (ADS)
       if os.name == 'nt':
           with open(f'{path}:{key}', 'wb') as f:
               f.write(value)
           return

       # 2. UNIX/macOS 平台: 优先调用 Python 原生 os.setxattr 或 xattr/pyxattrs C 扩展
       if callable(getattr(os, 'setxattr', None)):
           os.setxattr(path, key, value)
           return

       # 3. 兜底回退: 探测并调用外部 setfattr (Linux) 或 xattr (macOS) 二进制程序
       exe = 'setfattr' if check_executable('setfattr') else 'xattr'
       Popen.run([exe, '-w', key, value.decode(), path] if exe == 'xattr' else [exe, '-n', key, '-v', value.decode(), path])

针对文件系统不支持 XAttr（如 FAT32/exFAT U盘）或磁盘空间不足（``ENOSPC`` / ``EDQUOT``）的情况，引擎封装了 ``XAttrMetadataError``，发出告警而不中断主下载进程。

---
端到端章节切分与广告消除调用链与源码映射
---

.. code-block:: text
   :caption: 章节切分、广告消除与扩展属性完整执行调用流

   用户指令 (--split-chapters 或 --sponsorblock-remove sponsor)
                |
                v YoutubeDL.post_process() 插件链调度
   +-------------------------------------------------------------------+
   | 阶段 1: ModifyChaptersPP / SponsorBlockPP                         |
   |    - 拉取 SponsorBlock 众包数据库标记广告区间                     |
   |    - 优先队列求交合并重叠切除块 cuts                              |
   |    - 生成 ffconcat 脚本执行视频与字幕无缝裁切拼接                 |
   +---------------------------------+---------------------------------+
                                     |
                                     v
   +-------------------------------------------------------------------+
   | 阶段 2: FFmpegSplitChaptersPP (若用户指定 --split-chapters)       |
   |    - 扫描最终剩余的 chapters 列表                                 |
   |    - (可选) force_keyframes 插入切分点关键帧                      |
   |    - 循环执行 -ss / -t 流复制切割为 N 个章节文件                  |
   +---------------------------------+---------------------------------+
                                     |
                                     v
   +-------------------------------------------------------------------+
   | 阶段 3: XAttrMetadataPP                                           |
   |    - 向最终生成的主文件或各章节文件写入 xattr 元数据              |
   |    - 写入 Spotlight / XDG / NTFS ADS 文件系统属性                 |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 章节切分、SponsorBlock 与 XAttr 核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``FFmpegSplitChaptersPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:1015-1060``
     - 物理章节切割、关键帧强制重编码插入与输出模板路径求值
   * - ``ModifyChaptersPP``
     - ``yt_dlp/postprocessor/modify_chapters.py:15-180``
     - 广告与章节区间优先队列重叠消除、时间戳重映射与 ``ffconcat`` 裁切
   * - ``SponsorBlockPP``
     - ``yt_dlp/postprocessor/sponsorblock.py:15-110``
     - SponsorBlock API 接口对接、哈希查询与广告分类元数据转换为章节
   * - ``XAttrMetadataPP``
     - ``yt_dlp/postprocessor/xattrpp.py:10-55``
     - 文件系统扩展属性字段编排与后处理挂载
   * - ``write_xattr()``
     - ``yt_dlp/utils/_utils.py:1260-1300``
     - 跨平台扩展属性写入（macOS Spotlight、Linux XDG、NTFS ADS）

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 在媒体后处理阶段的高阶章节操纵与系统层集成技术：
1. ``FFmpegSplitChaptersPP`` 依托 ``-force_key_frames`` 与 ``-ss / -t`` 实现了关键帧对齐的零伪影章节物理切分；
2. ``ModifyChaptersPP`` 创造性地运用小顶堆优先队列（``heapq``）解决了章节与广告切片复杂的 8 种重叠拓扑冲突，并通过 ``ffconcat`` 实现了视音频与外挂字幕的同步无损拼接；
3. ``SponsorBlockPP`` 实现了与众包广告库的工业级接口集成；
4. ``XAttrMetadataPP`` 与 ``write_xattr`` 达成了对 macOS Spotlight、Linux XDG 及 Windows NTFS ADS 的全平台文件系统元数据写入。

至此，**第 6 模块（后处理器流水线与媒体重构）全量完工**！在接下来的 **第 7 模块（逆向对抗、JS 执行引擎与反爬突破）** 中，我们将步入 ``yt-dlp`` 技术皇冠上的明珠——深度揭秘其如何与现代 Web 端最高级别的防爬与签名对抗体系博弈：第 1 节（``07_reverse_engineering_and_js_engine/01_js_runtime_bridge.rst``）将全面解构外部 JavaScript 运行时架构（Deno、Node.js、Bun、QuickJS）与进程间 IPC 沙箱通信协议。
