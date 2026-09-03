========================================================================================
05.03 音视频轨道兼容性矩阵 get_compatible_ext、动态合并与容器规范判定
========================================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们解构了 ``yt-dlp`` 格式选择 DSL 的抽象语法树（AST）编译流水线与 ``FormatSorter`` 基于 20+ 维特征的全序排序算法。当 Format DSL 的合并运算符（``+``）从流列表中独立圈选出最优视频轨（如 VP9 或 H.264）与最优音频轨（如 Opus 或 AAC）后，下载引擎面临着核心的多媒体工程挑战——**容器兼容性判定与轨道物理缝合**。不同的多媒体封装容器（MP4、WebM、Matroska/MKV 等）受制于国际标准规范（ISO/IEC 14496、WebM Project、RFC 8428），对内部封装的音视频编码标准存在严苛的白名单约束。若将不兼容的流（如 VP9 视频与 AAC 音频，或 H.264 视频与 Opus 音频）强行混流至 MP4 或 WebM 容器中，将导致大多数硬件解码器与播放器严重故障。``yt-dlp`` 在工具层构建了 **``get_compatible_ext``（``yt_dlp/utils/_utils.py``）** 兼容性推理矩阵与 **``_merge``（``yt_dlp/YoutubeDL.py``）** 流合成引擎。本节将深度解构该算法体系。

***
多媒体容器规范与编解码器兼容性矩阵
***

主流多媒体容器标准对音视频编解码器（Codecs）的支持范围存在本质差异：

.. code-block:: text
   :caption: 主流多媒体封装容器与编解码器兼容性拓扑

   +-------------------------------------------------------------------------------+
   | ISO Base Media File Format / MP4 (ISO/IEC 14496-14)                           |
   |   - 视频编码: H.264/AVC, H.265/HEVC, AV1                                      |
   |   - 音频编码: AAC (mp4a), AC-3/E-AC-3, AC-4, ALAC                             |
   |   - 限制: 传统规范排斥 VP8/VP9 视频与 Vorbis/Opus 音频                        |
   +-------------------------------------------------------------------------------+
   | WebM Container (Google / WebM Project, 基于 Matroska 子集)                    |
   |   - 视频编码: VP8, VP9, AV1                                                   |
   |   - 音频编码: Opus, Vorbis                                                    |
   |   - 限制: 严格禁止专利限制的私有编码 (H.264, H.265, AAC, MP3)                |
   +-------------------------------------------------------------------------------+
   | Matroska / MKV (RFC 8428 开放多媒体容器)                                      |
   |   - 万能兼容: 支持所有主流视频、音频、多音轨、多字幕轨道与章节元数据          |
   |   - 定位: 跨编码合并与多音轨/多视轨合成的通用兜底容器                         |
   +-------------------------------------------------------------------------------+

容器与编解码器兼容性判定矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 主流多媒体容器格式与编解码器支持矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1

   * - 编码组合 (Video + Audio)
     - MP4 容器
     - WebM 容器
     - MKV 容器
     - 最佳目标容器决策
   * - **H.264 (AVC) + AAC**
     - 原生完全兼容
     - 严格不兼容
     - 完全兼容
     - ``mp4``
   * - **H.265 (HEVC) + AAC/EAC3**
     - 原生完全兼容
     - 严格不兼容
     - 完全兼容
     - ``mp4``
   * - **VP9 + Opus**
     - 不推荐/不兼容
     - 原生完全兼容
     - 完全兼容
     - ``webm``
   * - **AV1 + Opus**
     - 部分支持 (新标准)
     - 原生完全兼容
     - 完全兼容
     - ``webm`` (或 ``mp4``)
   * - **AV1 + AAC**
     - 原生完全兼容
     - 严格不兼容
     - 完全兼容
     - ``mp4``
   * - **VP9 + AAC**
     - 不兼容 (非标准)
     - 不兼容 (禁止 AAC)
     - 完全兼容
     - ``mkv``
   * - **H.264 + Opus**
     - 不兼容 (非标准)
     - 不兼容 (禁止 AVC)
     - 完全兼容
     - ``mkv``
   * - **多音轨 / 多视轨组合**
     - 受限 (复杂映射)
     - 受限
     - 完全原生支持
     - ``mkv``

---
get_compatible_ext 核心算法与集合推理推导
---

``get_compatible_ext`` 接收待合并轨道的视频编码列表 ``vcodecs``、音频编码列表 ``acodecs``、视频原始扩展名 ``vexts``、音频原始扩展名 ``aexts`` 以及用户偏好列表 ``preferences``，通过多级集合包含判定（Set Superset Evaluation）确定最优输出扩展名。

.. code-block:: python
   :caption: get_compatible_ext 核心实现 (yt_dlp/utils/_utils.py)

   def get_compatible_ext(*, vcodecs, acodecs, vexts, aexts, preferences=None):
       assert len(vcodecs) == len(vexts) and len(acodecs) == len(aexts)

       allow_mkv = not preferences or 'mkv' in preferences

       # 阶段 1: 多轨道并发流守卫 (Multi-stream Guard)
       if allow_mkv and max(len(acodecs), len(vcodecs)) > 1:
           return 'mkv'

       # 阶段 2: 编解码器兼容白名单集合
       COMPATIBLE_CODECS = {
           'mp4': {
               'av1', 'hevc', 'avc1', 'mp4a', 'ac-4',
               'h264', 'aacl', 'ec-3',
           },
           'webm': {
               'av1', 'vp9', 'vp8', 'opus', 'vrbs',
               'vp9x', 'vp8x',
           },
       }

       # 阶段 3: 编码标识符清洗与归一化
       sanitize_codec = functools.partial(
           try_get, getter=lambda x: x[0].split('.')[0].replace('0', '').lower())
       vcodec, acodec = sanitize_codec(vcodecs), sanitize_codec(acodecs)

       # 阶段 4: 基于 Codec 集合超集关系匹配
       for ext in preferences or COMPATIBLE_CODECS.keys():
           codec_set = COMPATIBLE_CODECS.get(ext, set())
           if ext == 'mkv' or codec_set.issuperset((vcodec, acodec)):
               return ext

       # 阶段 5: 基于扩展名集合兼容性降级匹配
       COMPATIBLE_EXTS = (
           {'mp3', 'mp4', 'm4a', 'm4p', 'm4b', 'm4r', 'm4v', 'ismv', 'isma', 'mov'},
           {'webm', 'weba'},
       )
       for ext in preferences or vexts:
           current_exts = {ext, *vexts, *aexts}
           if ext == 'mkv' or current_exts == {ext} or any(
                   ext_sets.issuperset(current_exts) for ext_sets in COMPATIBLE_EXTS):
               return ext

       # 阶段 6: 终极兜底
       return 'mkv' if allow_mkv else preferences[-1]

算法执行维度的数学推导与边界处理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **编码标识符归一化映射**：
   在 MPD/M3U8 中，编解码器通常带有复杂的 Profile/Level 后缀（如 ``avc1.640028``、``vp09.02.10.10.01.09.16.09.01``、``mp4a.40.2``）。
   算法通过 ``x[0].split('.')[0].replace('0', '').lower()`` 执行清洗：
   - ``avc1.640028`` $	o$ ``avc1``；
   - ``vp09.02...`` $	o$ ``vp9``；
   - ``mp4a.40.2`` $	o$ ``mp4a``。
2. **集合超集运算（Set Superset）**：
   对于清洗后的二元元组 $(C_{	ext{video}}, C_{	ext{audio}})$，算法检测：

   .. math::

      (C_{	ext{video}}, C_{	ext{audio}}) \subseteq \mathbf{S}_{	ext{container}}

   若 $\{ 	ext{'vp9'}, 	ext{'opus'} \} \subseteq \mathbf{S}_{	ext{webm}}$ 成立，则直接命中 ``webm``；若混入非开放编码（如 $\{ 	ext{'avc1'}, 	ext{'opus'} \}$），两者的交集无法被 ``mp4`` 或 ``webm`` 完全覆盖，循环落入 ``mkv``。
3. **多流防御（Multi-stream Guard）**：
   当用户请求多音轨合并（如多语言解说）时，$\max(|A|, |V|) > 1$。由于 MP4 容器在某些播放器上处理多音频轨道的 Track 映射存在兼容性瑕疵，引擎强制将输出扩展名收敛为 ``mkv``。

---
多轨合并状态机与流数量约束 (_merge)
---

在 ``YoutubeDL.build_format_selector`` 中定义的内部函数 ``_merge(formats_pair)`` 负责将两个候选流（通常为视频与音频）合成为单一复合格式字典。

.. code-block:: text
   :caption: _merge 多轨流过滤与合成状态机

   输入 formats_pair: (format_1, format_2)
             |
             v 展开嵌套的 requested_formats
   +-------------------------------------------------------------------+
   | 收集格式字典列表: formats_info = [fmt_1, fmt_2, ...]              |
   +---------------------------------+---------------------------------+
                                     |
                                     v 单流模式校验 (Single Stream Guard)
   +-------------------------------------------------------------------+
   | 检查 allow_multiple_streams['video'/'audio'] 配置:                |
   | - 若未开启多流允许:                                               |
   |   - 剔除无声且无画面的无效流                                      |
   |   - 保留首个视频流与首个音频流，剔除后续冗余重复流                |
   +---------------------------------+---------------------------------+
                                     |
                                     v 提取 video_fmts 与 audio_fmts
   +-------------------------------------------------------------------+
   | 1. 调用 get_compatible_ext() 计算输出扩展名 output_ext            |
   | 2. 构造合成复合字典 new_dict:                                     |
   |    - requested_formats = [保留的物理流字典列表]                   |
   |    - format_id = "137+140"                                        |
   |    - ext = output_ext ("mp4" / "mkv" / "webm")                    |
   |    - protocol = "https+https"                                     |
   |    - tbr = sum(tbr_video, tbr_audio)                             |
   |    - filesize_approx = sum(size_video, size_audio)                |
   |    - 聚合单视轨与单音轨的专有元数据 (width, height, fps, acodec...) |
   +-------------------------------------------------------------------+

元数据聚合与规约
~~~~~~~~~~~~~~~~

``_merge`` 合成字典时，执行多轨参数智能合并：
* **``format_id``**：使用 ``+`` 拼接（例如 ``137+140`` 或 ``303+251``）；
* **``filesize_approx``**：对子流体积求和，提供整体下载体积精确预估；
* **``language``**：通过 ``orderedSet`` 提取并去重音轨语言标记（如 ``[en, zh]``）；
* **单流元数据继承**：若合成流中仅包含单一视频轨道与单一音频轨道，直接将视频的宽高、帧率、色彩空间与音频的采样率、声道数提升至复合字典顶层，确保格式化打印（``--list-formats``）与输出模板（``-o``）能无缝提取。

---
动态容器转换与后处理约束 (Dynamic Container Conversion)
---

在格式下载完成进入后处理阶段（``post_process``）时，特定插件（PostProcessor）对文件物理结构的要求可能与预选容器产生冲突。``yt-dlp`` 建立了动态修正保护机制。

WebM 封面内嵌冲突与 MKV 自动升级
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

WebM 规范设计初衷是网络流媒体轻量级播放，其容器标准不包含 Matroska 完整的 Attachments（附件）子规范，因而 **FFmpeg 无法在不破坏 WebM 标准的前提下将 JPEG/PNG 封面图内嵌进 WebM 文件**。

当用户同时指定了 ``--embed-thumbnail`` 并下载了 WebM 格式时，``YoutubeDL.process_info()`` 触发安全升级逻辑：

.. code-block:: python

   # 检测是否需要内嵌封面且当前容器为 webm
   if (info_dict['ext'] == 'webm'
           and info_dict.get('thumbnails')
           and any(type(pp) == EmbedThumbnailPP for pp in self._pps['post_process'])):
       info_dict['ext'] = 'mkv'
       self.report_warning("webm doesn't support embedding a thumbnail, mkv will be used")

这一机制避免了 FFmpeg 在后处理执行 ``-attach`` 时抛出致命错误 ``Could not write header for output file #0 (incorrect codec parameters ?): Invalid argument``。

FFmpegMergerPP 物理封装与参数映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 ``requested_formats`` 包含多个独立下载的音视频文件时，``YoutubeDL`` 将 ``FFmpegMergerPP`` 压入后处理队列：
1. **无损流复制（Stream Copy）**：构建 ``ffmpeg -i video.mp4 -i audio.m4a -c copy -map 0:v:0 -map 1:a:0 output.mp4``；
2. **时间戳重对齐**：对于 DASH/HLS 切片合成产生的轻微 PTS 偏移，自动注入时间戳校准参数；
3. **临时分片自动清理**：合并成功后安全移除中间分轨文件（``f137.mp4`` 与 ``f140.m4a``）。

---
端到端轨道兼容与合并时序图与源码映射
---

.. code-block:: text
   :caption: 音视频轨道合并与容器判定时序流

   Format DSL (+) 求值
           |
           v
   YoutubeDL._merge() -------------------------------------------------+
           |                                                           |
           |-- 1. 过滤冗余轨道 (Single Stream Guard)                   |
           |-- 2. 提取 vcodecs, acodecs, vexts, aexts                  |
           |-- 3. 调用 get_compatible_ext() -------------------------> |
           |      |                                                    |
           |      |-- 检查多音轨/多视轨 -> 返回 "mkv"                  |
           |      |-- 集合超集匹配 -> 返回 "mp4" / "webm"              |
           |      \-- 扩展名组降级 -> 确定 output_ext                  |
           |                                                           |
           |<-- 4. 获得最优容器扩展名 ----------------------------------+
           |
           v
   构造 requested_formats 复合字典并交付下载器
           |
           v 独立下载视频轨与音频轨分片
           |
           v 后处理阶段 (post_process)
   +-------------------------------------------------------------------+
   | 1. 检查插件约束 (如 EmbedThumbnailPP 对 WebM 的冲突 -> 升为 MKV)  |
   | 2. 唤起 FFmpegMergerPP 执行物理无损封装 (-c copy)                 |
   | 3. 生成最终完备的单文件媒体交付用户                               |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 轨道兼容性与合并引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``get_compatible_ext()``
     - ``yt_dlp/utils/_utils.py:3100-3135``
     - 编解码器兼容性集合运算、多轨守卫与最佳容器推断
   * - ``_merge()``
     - ``yt_dlp/YoutubeDL.py:2437-2488``
     - Format DSL 笛卡尔积流合成、单流约束过滤与复合元数据打包
   * - ``FFmpegMergerPP``
     - ``yt_dlp/postprocessor/ffmpeg.py:580-640``
     - FFmpeg 音视频多路复用子进程封装、无损流拷贝管道
   * - ``process_info()`` 容器安全升级
     - ``yt_dlp/YoutubeDL.py:2980-3015``
     - 封面内嵌（EmbedThumbnail）与 WebM 冲突检测及自动升级 MKV

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 在音视频轨道合并与容器格式判定层面的核心算法与规范约束，厘清了：
1. MP4、WebM 与 Matroska (MKV) 容器的编解码器兼容性矩阵与标准边界；
2. ``get_compatible_ext`` 基于集合超集论与编码标识符清洗的容器推断引擎；
3. ``_merge`` 状态机在单流约束过滤、多轨元数据汇总及笛卡尔积组合中的底层实现；
4. 动态容器转换保护机制（如 WebM 内嵌封面时向 MKV 容器的无损平滑升级）与 ``FFmpegMergerPP`` 无损复用。

至此，**第 5 模块（格式选择器与媒体排序算法）全量完工**！在接下来的 **第 6 模块（后处理器流水线与媒体重构）** 中，我们将深入剖析 ``yt-dlp`` 在媒体下载完成后的原子级重构中枢——第 1 节（``06_postprocessor_and_ffmpeg/01_postprocessor_chain_and_lifecycle.rst``）将全面解构 ``PostProcessor`` 插件链架构、生命周期切入点（``POSTPROCESS_WHEN``）以及多阶段钩子机制。
