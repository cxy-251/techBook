========================================================================================
05.02 FormatSorter 多维度自适应权重排序算法 (分辨率/码率/编码/声道/HDR/协议)
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们解构了 ``yt-dlp`` 格式选择领域特定语言（Format Selection DSL）的词法分析流、递归下降 AST 解析器以及 ``_merge`` 多轨合并模型。在 DSL 执行过程中，诸如 ``best``、``worst``、``bestvideo``、``bestaudio`` 等原子关键字的实际物理指向，高度依赖于底层格式列表的相对排序。早期 ``youtube-dl`` 的排序算法较为粗糙（主要依赖单一码率与简单分辨率判定），常常导致其选出画质低劣但码率奇高的高开销陈旧编码（如高码率 MPEG-4/H.264），或者忽略了高动态范围（HDR）、高帧率（60fps）及多声道（5.1 Surround）音频的优势。为此，``yt-dlp`` 研发了革命性的 **``FormatSorter``（``yt_dlp/utils/_utils.py``）** 多维自适应权重排序引擎。本节将全面剖析其 20+ 维特征拓扑、偏好元组数学模型、阈值（``:``）与邻近（``~``）边界计算机制。

***
FormatSorter 多维全序排序体系架构
***

在 Python 中，排序通常基于可比较元组（Tuple Comparison）。``FormatSorter`` 将每一个媒体格式字典映射为一个高维元组（Preference Tuple），通过字典序（Lexicographical Order）从高到低确定格式的优劣全序。

.. code-block:: text
   :caption: FormatSorter 20+ 维度排序权重级联拓扑

   原始未排序 Formats 列表 (来自各 Extractors)
                        |
                        v FormatSorter._fill_sorting_fields() 字段补全与参数推导
   +-------------------------------------------------------------------------------+
   | 1. 强制前置约束 (Forced Priority):                                            |
   |    - hidden: 排除 preference < -1000 的不可见流                               |
   |    - aud_or_vid: 确保至少包含有效音频或视频 (剔除纯字幕/封面图片流)            |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 视觉与听觉核心维度
   +-------------------------------------------------------------------------------+
   | 2. 核心画质与声学表现 (Audio/Video Core):                                     |
   |    - hasvid: 优先选择包含视频轨道的流                                         |
   |    - ie_pref: 平台提取器显式指定流权重 (preference)                           |
   |    - lang: 语言匹配偏好 (language_preference)                                 |
   |    - quality: 媒体全局质量评分 (quality)                                      |
   |    - res: 物理分辨率 (min(width, height)，优先 4K/1080p > 720p > 480p)        |
   |    - fps: 视频帧率 (60fps > 30fps > 24fps)                                    |
   |    - hdr: 动态范围 (Dolby Vision > HDR12 > HDR10+ > HDR10 > HLG > SDR)        |
   |    - vcodec: 视频编码代际效率 (AV1 > VP9.2 > VP9 > HEVC/H.265 > AVC/H.264)   |
   |    - channels: 声道配置 (7.1 > 5.1 > 立体声 2.0 > 单声道 1.0)                 |
   |    - acodec: 音频编码代际效率 (FLAC/ALAC > Opus > Vorbis > AAC > MP3)         |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 物理传输与容器层
   +-------------------------------------------------------------------------------+
   | 3. 传输开销与容器稳定性 (Transport & Container):                              |
   |    - size / fs_approx: 物理文件体积 (预估或确定大小)                          |
   |    - br: 综合码率 (tbr / vbr / abr)                                           |
   |    - asr: 音频采样率 (48000Hz > 44100Hz)                                      |
   |    - proto: 传输协议稳定性 (HTTPS/HTTP > HLS m3u8 > DASH > WebSocket > RTMP)  |
   |    - ext / vext / aext: 容器格式偏好 (MP4/WebM/MKV)                           |
   |    - hasaud: 优先选择带音频轨道的流                                           |
   |    - source: 媒体源偏好 (source_preference)                                   |
   |    - id: 格式 ID (确定性 Tie-breaker 兜底)                                    |
   +-------------------------------------------------------------------------------+
                        |
                        v 产出严格有序的 formats 列表 (供 Format DSL 挑选)

---
格式排序字段预填充与补全推导 (_fill_sorting_fields)
---

在进入排序比较之前，许多平台返回的元数据存在不同程度的字段缺漏（如仅有 ``tbr`` 无 ``vbr``/``abr``，或缺少显式 ``protocol``）。``FormatSorter._fill_sorting_fields(format)`` 执行规范化参数推演：

1. 码率守恒推算方程
~~~~~~~~~~~~~~~~~~~

对于音视频分离或未完整标注文档的流：

.. math::

   \begin{aligned}
   VBR &= TBR - ABR \quad (	ext{当 } vcodec 
eq 	ext{'none'} 	ext{ 且 } VBR 	ext{ 缺失}) \
   ABR &= TBR - VBR \quad (	ext{当 } acodec 
eq 	ext{'none'} 	ext{ 且 } ABR 	ext{ 缺失}) \
   TBR &= VBR + ABR \quad (	ext{当 } TBR 	ext{ 缺失})
   \end{aligned}

2. 轨类型与容器扩展名分离
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # 若为纯音频流 (vcodec == 'none')，将其 ext 划入 audio_ext，并将 video_ext 标记为 'none'
   if format.get('vcodec') == 'none':
       format['audio_ext'] = format['ext'] if format.get('acodec') != 'none' else 'none'
       format['video_ext'] = 'none'
   else:
       format['video_ext'] = format['ext']
       format['audio_ext'] = 'none'

3. 规范越界格式惩罚降级
~~~~~~~~~~~~~~~~~~~~~~~

针对不合规的历史封装（例如在 FLV 容器中封装 HEVC/H.265 编码视频，该行为违反 Adobe FLV 原始规范并会导致大多数播放器崩溃）：

.. code-block:: python

   if format.get('preference') is None and format.get('ext') == 'flv' and re.match(r'[hx]265|he?vc?', format.get('vcodec') or ''):
       format['preference'] = -100  # 强制大幅降权，优先使用合法封装

---
编解码器与动态范围代际能效排序矩阵
---

现代流媒体技术的核心进步体现在更高压缩率的视频编码标准与更广色域的高动态范围（HDR）。``FormatSorter`` 建立了精确的代际能效层级矩阵（基于正则模式匹配与有序列表反向索引）：

视频编码代际拓扑 (vcodec)
~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 视频编解码器优先级排序表
   :widths: 20 25 55
   :header-rows: 1

   * - 编码类型
     - 正则匹配表达式
     - 架构定位与选型考量
   * - **AV1**
     - ``av0?1``
     - 现代免版税开源编码标准，相同画质下较 H.264 节省 50% 码率，优先度最高
   * - **VP9 Profile 2**
     - ``vp0?9\.0?2``
     - 10-bit/12-bit HDR 增强版 VP9 编码，广泛用于 YouTube 4K HDR
   * - **VP9 Profile 0**
     - ``vp0?9``
     - Google 主推 8-bit 高效编码，4K/2K 分辨率标配
   * - **HEVC / H.265**
     - ``[hx]265|he?vc?``
     - 工业级 4K 广播与移动设备硬件解码标准
   * - **AVC / H.264**
     - ``[hx]264|avc``
     - 历史兼容性最好的通用编码标准（兜底兼容）
   * - **VP8 / H.263 / Theora**
     - ``vp0?8`` / ``mp4v|h263``
     - 遗留老旧编码，画质与压缩比落后，排位最末

音频编码代际拓扑 (acodec)
~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 音频编解码器优先级排序表
   :widths: 20 25 55
   :header-rows: 1

   * - 编码类型
     - 正则匹配表达式
     - 架构定位与声学特性
   * - **FLAC / ALAC**
     - ``[af]lac``
     - 无损压缩音频（Lossless），保留完整原始频响
   * - **WAV / AIFF**
     - ``wav|aiff``
     - 无压缩 PCM 音频流
   * - **Opus**
     - ``opus``
     - 现代交互式与流媒体最优声学编码，64~160kbps 下音质超越同码率 AAC
   * - **Vorbis / OGG**
     - ``vorbis|ogg``
     - 开源高保真音频编码
   * - **AAC / M4A**
     - ``aac`` / ``mp?4a?``
     - MPEG 通用音频编码，生态兼容性极强
   * - **MP3 / Dolby AC-3**
     - ``mp3`` / ``ac-?3``
     - 历史遗留格式或多声道广播音频

高动态范围拓扑 (hdr)
~~~~~~~~~~~~~~~~~~~~

``FormatSorter`` 将色彩空间细分为 8 级阶梯：
``Dolby Vision (dv) > HDR12 > HDR10+ > HDR10 > HLG > SDR > None``。

---
偏好元组计算数学模型 (_calculate_field_preference_from_value)
---

为了将各种离散或连续字段转化为统一的 Python 比较元组，``FormatSorter`` 构建了一个三元评分结构：

.. math::

   \mathbf{S}(f, 	ext{field}) = (P_{	ext{bucket}}, V_{	ext{primary}}, V_{	ext{tiebreaker}})

其中 $P_{	ext{bucket}}$ 为优先级分桶（$1$ 为最高特殊值，$0$ 为正常匹配区，$-1$ 为超限惩罚区，$-10$ 为空值/无效区）。

.. code-block:: python

   def _calculate_field_preference_from_value(self, format_, field, type_, value):
       reverse = self._get_field_setting(field, 'reverse')
       closest = self._get_field_setting(field, 'closest')
       limit = self._get_field_setting(field, 'limit')

       # 1. 空值处理: 字段缺失则分配最低桶 (-10)
       if value is None:
           return (-10, 0)

       # 2. 邻近匹配模式 (Closest Match: ~)
       if closest:
           # 距离越小评分越高: -|value - limit|
           return (0, -abs(value - limit), value - limit if reverse else limit - value)

       # 3. 阈值上限模式 (Threshold Limit: :)
       if not reverse and (limit is None or value <= limit):
           return (0, value, 0)
       elif limit is None or (reverse and value == limit) or value > limit:
           # 超出上限阈值，进入惩罚降权
           return (0, -value, 0)
       else:
           return (-1, value, 0)

三种核心匹配模式的形式化推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **自然正序 / 逆序（Natural Order）**：
   - 默认模式下：$V = 	ext{value}$，值越大越优先（如分辨率 2160 > 1080 > 720）；
   - 若指定 ``+``（如 ``+res`` 或 ``+size``）：$V = -	ext{value}$，值越小越优先（适合寻找体积最小的格式）。
2. **阈值上限过滤（Upper Bound Limit: ``:``）**：
   - 语法：``res:1080``、``fps:30``、``size:500M``。
   - 规则：在不超过阈值（$\le 1080$）的前提下，数值越大越好；超过阈值（$> 1080$）的格式并不会被直接剔除，而是被赋予负向权重（$-V$）沉底，充当极端情况下的降级备选。
3. **目标值邻近匹配（Closest Target Match: ``~``）**：
   - 语法：``res~720``、``br~128k``。
   - 规则：以目标值 $\lambda$ 为中心，计算差值绝对值 $-\lvert V - \lambda \rvert$ 作为主排序键。

---
动态排序链组合与用户覆盖语义 (-S / --format-sort)
---

用户可以通过命令行参数 ``-S``（``--format-sort``）自由调整任意维度的优先级顺序。

排序链的层叠组合流水线 (evaluate_params)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

引擎按照以下严格次序构建最终的排序维度列表 ``sort_list``：

.. code-block:: python

   sort_list = (
       # 1. 强制不可变维度 (hidden, aud_or_vid)
       tuple(field for field in self.default if self._get_field_setting(field, 'forced'))
       # 2. 优先级维度 (hasvid, ie_pref) - 可被 --format-sort-force 旁路覆盖
       + (tuple() if params.get('format_sort_force', False)
          else tuple(field for field in self.default if self._get_field_setting(field, 'priority')))
       # 3. 用户命令行指定维度 (通过 -S / --format-sort 传入)
       + tuple(self._sort_user)
       # 4. 平台提取器显式指定维度 (Extractor Sort Fields)
       + tuple(sort_extractor)
       # 5. 系统默认兜底全量维度 (self.default)
       + self.default
   )

去重与别名归一化（Alias Resolution）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

遍历 ``sort_list`` 时，引擎动态将用户友好的别名映射为内部标准键（例如 ``resolution -> res``、``framerate -> fps``、``bitrate -> br``、``video_codec -> vcodec``），并剔除重复字段，保留最高优先级的首次声明。

---
端到端 FormatSorter 排序时序与源码映射
---

.. code-block:: text
   :caption: FormatSorter 整体排序执行时序

   YoutubeDL.process_video_result()
                |
                v YoutubeDL.sort_formats()
   +-------------------------------------------------------------------+
   | 1. 初始化 FormatSorter 实例:                                      |
   |    - evaluate_params(): 合并默认/用户/提取器排序链                |
   |    - 解析阈值限制 (:, ~) 与反向标记 (+)                           |
   +---------------------------------+---------------------------------+
                                     |
                                     v list.sort(key=FormatSorter.calculate_preference)
   +-------------------------------------------------------------------+
   | 2. 针对每个 format 字典计算 calculate_preference:                 |
   |    - 调用 _fill_sorting_fields() 补全码率与协议                   |
   |    - 遍历 self._order 中的每一个维度字段                          |
   |    - 调用 _calculate_field_preference() 生成偏好评分三元组        |
   |    - 打包为高维元组: (score_hidden, score_res, score_vcodec, ...) |
   +---------------------------------+---------------------------------+
                                     |
                                     v Python 内部 Timsort 算法
   +-------------------------------------------------------------------+
   | 3. 完成全量 Formats 的多维全序排列                                |
   |    (最优格式位于 formats[-1]，最劣格式位于 formats[0])            |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: FormatSorter 排序引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``FormatSorter`` 类定义
     - ``yt_dlp/utils/_utils.py:3150-3330``
     - 多维排序配置字典、别名映射系统与默认 20 维排序链
   * - ``FormatSorter.evaluate_params()``
     - ``yt_dlp/utils/_utils.py:3240-3280``
     - 用户参数 (``-S``)、提取器偏好与系统默认规则的级联融合
   * - ``FormatSorter._calculate_field_preference_from_value()``
     - ``yt_dlp/utils/_utils.py:3285-3315``
     - 三元偏好评分数学模型（自然序、阈值上限、邻近目标）
   * - ``FormatSorter._fill_sorting_fields()``
     - ``yt_dlp/utils/_utils.py:3318-3350``
     - 码率守恒反推、音频/视频容器扩展名分离与非法封装惩罚
   * - ``YoutubeDL.sort_formats()``
     - ``yt_dlp/YoutubeDL.py:2280-2295``
     - 驱动目标格式列表执行 Timsort 排序与回调触发

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 核心格式决策大脑中的 **``FormatSorter`` 多维度自适应权重排序模型**，阐明了：
1. 20+ 维媒体特征拓扑结构及其在画质、声学、传输和容器层面的阶梯关系；
2. ``_fill_sorting_fields`` 基于码率守恒与协议特性的参数推演与异常封装惩罚；
3. AV1 > VP9 > HEVC > AVC 与 FLAC > Opus > AAC 的代际压缩能效排序矩阵；
4. 偏好评分三元组 $(P, V_1, V_2)$ 在阈值上限（``:``）与邻近匹配（``~``）下的数学计算模型；
5. ``evaluate_params`` 中强制字段、优先字段与用户自定义排序链（``-S``）的级联装配机制。

在掌握了格式选择 DSL 与多维排序算法之后，下载引擎在面临多音轨（如双语配音）、多视轨及多字幕封装时，必须判定流与流之间的容器物理兼容性。在下一节（``05_format_selection_and_sorting/03_stream_filtering_and_compatibility.rst``）中，我们将深入解构 **音视频轨道兼容性矩阵 ``get_compatible_ext``、多音轨流过滤与动态容器封装判定算法**。
