========================================================================================
03.04 播放列表流式生成器、PagedList/LazyList 惰性求值与内存边界保护
========================================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们完整解构了 ``InfoExtractor`` 的基类生命周期、URL 正则路由分发机制以及基于 ``traverse_obj`` 与 JSON-LD 的页面结构化提取。在流媒体采集领域，另一类极具挑战性的场景是 **超大规模播放列表（Playlists）、频道视频归档（Channels）与用户订阅流的批量拉取**。当一个 YouTube 频道或 Spotify 歌单包含数十万个条目时，若采用传统的即时全量求值（Eager Evaluation），不仅会导致长时间的网络阻塞与巨额内存占用（OOM 崩溃），更无法实现“边拉取元数据、边下载流媒体”的流式消费。``yt-dlp`` 构建了一套基于 ``LazyList``、``PagedList`` 与 ``PlaylistEntries`` 的惰性流式计算体系。本节将深度解构其惰性求值状态机、切片 DSL 解析算法与内存边界保护机制。

***
海量播放列表与内存爆炸挑战
***

在爬虫与下载引擎处理大型播放列表时，传统架构普遍面临两大性能瓶颈：

1. **网络往返时延（RTT）累积阻塞**：对于包含 50,000 个视频的频道，若必须先拉取完所有分页才能开始下载第 1 个视频，用户需忍受长达数十分钟的初始白屏等待；
2. **内存空间暴涨（Memory Explosion）**：每个视频条目的元数据字典（包含格式列表、缩略图、描述信息）约占 10KB~50KB 内存，全量缓存在内存中将直接消耗数 GB 物理内存。

.. code-block:: text
   :caption: Eager 模式与 Lazy 模式内存与时序对比

   Eager 模式 (全量预加载):
   [请求第1页] -> [请求第2页] -> ... -> [请求第1000页] -> [全部载入内存 (GB级)] -> [开始下载第1个视频]
   (前置耗时极长，内存持续线性暴涨)

   Lazy 模式 (流式按需求值):
   [请求第1页] -> [产出第1个视频] -> [立即启动下载] -> [消费完毕释放] -> [按需滑动窗口请求第2页]
   (首帧即刻响应，内存恒定保持 O(1) 边界)

---
惰性不可变序列 LazyList 架构与算法实现
---

``yt_dlp/utils/_utils.py`` 实现了强类型不可变惰性序列 ``LazyList``，继承自标准库的 ``collections.abc.Sequence``。

.. code-block:: text
   :caption: LazyList 内部双重缓存与按需推进状态机

   LazyList 实例
   +-------------------------------------------------------------------+
   | _iterable: 生成器或迭代器 (未消费数据流)                           |
   | _cache: list (已按需消费并物化的元素缓存)                         |
   | _reversed: bool (是否反向视图)                                    |
   +---------------------------------+---------------------------------+
                                     |
                                     v __getitem__(idx)
   +-------------------------------------------------------------------+
   | 1. 索引边界计算: n = max(start, stop) - len(_cache) + 1           |
   | 2. 若 n > 0 (超出已缓存范围):                                     |
   |    - 调用 itertools.islice(_iterable, n) 仅推进必要步长           |
   |    - 追加至 _cache                                                |
   | 3. 若遇到负数索引或全量求值 (len / exhaust):                       |
   |    - 耗尽 _iterable 并清空引用 (以便支持 pickle 序列化)           |
   +-------------------------------------------------------------------+

核心切片与反向索引映射算法
~~~~~~~~~~~~~~~~~~~~~~~~~~

``LazyList`` 能够像普通 Python ``list`` 一样支持切片与反向索引，其底层通过位运算取反（``~x``）实现坐标系映射：

.. code-block:: python

   class LazyList(collections.abc.Sequence):
       def __init__(self, iterable, *, reverse=False, _cache=None):
           self._iterable = iter(iterable)
           self._cache = [] if _cache is None else _cache
           self._reversed = reverse

       @staticmethod
       def _reverse_index(x):
           # 利用按位取反操作实现对称逆向索引变换: 0 -> -1, 1 -> -2, None -> None
           return None if x is None else ~x

       def __getitem__(self, idx):
           if isinstance(idx, slice):
               if self._reversed:
                   idx = slice(self._reverse_index(idx.start), self._reverse_index(idx.stop), -(idx.step or 1))
               start, stop, step = idx.start, idx.stop, idx.step or 1
           elif isinstance(idx, int):
               if self._reversed:
                   idx = self._reverse_index(idx)
               start, stop, step = idx, idx, 0

           # 仅当切片跨越未缓存区域时，才驱动生成器前向推进
           n = max(start or 0, stop or 0) - len(self._cache) + 1
           if n > 0:
               self._cache.extend(itertools.islice(self._iterable, n))
           return self._cache[idx]

---
分页拉取状态机 PagedList 体系 (OnDemand vs InAdvance)
---

针对基于 Web API 分页（Pagination Tokens、Offset/Limit、Page Number）的流媒体服务，``yt-dlp`` 构建了 ``PagedList`` 层次体系。

.. list-table:: PagedList 核心派生类与适用场景
   :widths: 22 28 50
   :header-rows: 1

   * - 类名称
     - 分页终止判定机制
     - 典型应用场景
   * - ``OnDemandPagedList``
     - 动态按需抓取。当某页返回数量小于 ``pagesize`` 时判定为末页
     - 滚动加载的无限流、YouTube Browse API、Bilibili 用户动态
   * - ``InAdvancePagedList``
     - 预知总页数 ``pagecount``。精准计算起止页码范围
     - 具有固定总页码的传统论坛、Vimeo 分页、分类检索目录

OnDemandPagedList 连续索引坐标变换算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户请求切片 ``playlist[105:250]`` 时，``OnDemandPagedList`` 必须将连续全局元素索引精确映射至离散的分页网络请求：

.. code-block:: python

   class OnDemandPagedList(PagedList):
       def _getslice(self, start, end):
           # 计算起始页码: start // pagesize
           for pagenum in itertools.count(start // self._pagesize):
               firstid = pagenum * self._pagesize
               nextfirstid = firstid + self._pagesize
               if start >= nextfirstid:
                   continue

               # 计算当前页内的局部切片区间 [startv:endv]
               startv = start % self._pagesize if firstid <= start < nextfirstid else 0
               endv = (((end - 1) % self._pagesize) + 1
                       if (end is not None and firstid <= end <= nextfirstid)
                       else None)

               page_results = self.getpage(pagenum)
               if startv != 0 or endv is not None:
                   page_results = page_results[startv:endv]
               yield from page_results

               # 动态终止优化: 若当前页未填满 pagesize，说明已达末尾，主动熔断终止
               if len(page_results) + startv < self._pagesize:
                   break
               if end == nextfirstid:
                   break

---
PlaylistEntries 切片 DSL 解析器与过滤熔断
---

``PlaylistEntries`` 是连接提取器输出与下载控制器的 **复合迭代中枢**。它负责解析用户复杂的 ``--playlist-items`` 命令行 DSL。

.. code-block:: text
   :caption: PlaylistEntries 架构与 DSL 展开流向

   CLI 参数: --playlist-items "1:5,10,20:30:2,50:-1"
                           |
                           v PlaylistEntries.parse_playlist_items()
   [slice(1, 5), 10, slice(20, 30, 2), slice(50, None)]
                           |
                           v PlaylistEntries.get_requested_items()
   +-------------------------------------------------------------------+
   | 1. 驱动底层 LazyList / PagedList 按需产出 (i, entry)               |
   | 2. 前置匹配过滤 (ydl._match_entry)                                |
   |    - 检查 daterange、matchtitle、rejecttitle                      |
   |    - 检查 download_archive (命中已下载归档)                       |
   | 3. 熔断判定 (Early Termination):                                  |
   |    - 若命中归档且开启 break_on_existing -> raise ExistingVideoReached |
   |    - 若未过过滤且开启 break_on_reject -> raise RejectedVideoReached   |
   +-------------------------------+-----------------------------------+
                                   |
                                   v 仅将通过校验的条目流式输送至下载管线
                     [YoutubeDL.process_video_result]

---
--lazy-playlist 流式消费管道与内存边界保护
---

在 ``YoutubeDL.__process_playlist`` 中，系统支持两种截然不同的消费模式：

.. list-table:: 播放列表处理模式对比
   :widths: 20 25 25 30
   :header-rows: 1

   * - 处理模式
     - 内存复杂度
     - 启动时延
     - 支持的操作与限制
   * - 默认模式 (Eager)
     - $O(N)$ (线性增长)
     - 需等待全列表提取完毕
     - 支持反向排序（``--playlist-reverse``）、随机乱序（``--playlist-random``）
   * - ``--lazy-playlist``
     - $O(1)$ (常数边界)
     - 零等待（首项即刻消费）
     - 禁用全量乱序；支持无限流式消费，杜绝超大列表 OOM

内存释放与平坦化丢弃策略 (`extract_flat`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户仅希望下载视频文件而不希望在内存中累积数万个视频的庞大字典时，可通过 ``--extract-flat discard_in_playlist`` 启用内存回收策略：

.. code-block:: python

   keep_resolved_entries = self.params.get('extract_flat') != 'discard'
   if self.params.get('extract_flat') == 'discard_in_playlist':
       keep_resolved_entries = ie_result['_type'] != 'playlist'

   for i, (playlist_index, entry) in enumerate(entries):
       entry_result = self.__process_iterable_entry(entry, download, ...)
       if keep_resolved_entries:
           resolved_entries[i] = (playlist_index, entry_result)
       # 若未开启 keep_resolved_entries，entry_result 处理完毕后立即被 GC 回收

---
端到端流式播放列表处理时序图与源码映射
---

.. code-block:: text
   :caption: 播放列表流式生成、按需加载与下载端到端时序

   Extractor (e.g. YoutubeTabIE)       PagedList / LazyList         PlaylistEntries            YoutubeDL.__process_playlist
              |                                 |                          |                                 |
              |-- 返回 playlist_result(entries) |                          |                                 |
              |   (entries 为生成器或 PagedList)|                          |                                 |
              |-------------------------------->|                          |                                 |
              |                                 |-- 初始化包装 ------------>|                                 |
              |                                 |                          |-- get_requested_items() ------->|
              |                                 |                          |                                 | (开启 --lazy-playlist)
              |                                 |<-- 请求第 1 批切片 ------|                                 |
              |-- 发起网络请求获取第 1 页 ----->|                          |                                 |
              |<-- 返回 50 个视频元数据 --------|                          |                                 |
              |                                 |-- 产出 entry 1 --------->|-- yield (1, entry 1) ---------->|
              |                                 |                          |                                 |-- process_video_result()
              |                                 |                          |                                 |-- 完成第 1 个视频下载落盘
              |                                 |                          |                                 |-- 立即释放 entry 1 内存
              |                                 |-- 产出 entry 2 --------->|-- yield (2, entry 2) ---------->|
              |                                 |                          |                                 |-- process_video_result()
              |                                 | ...                      | ...                             | ...

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 播放列表与惰性求值核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``LazyList``
     - ``yt_dlp/utils/_utils.py:4140-4215``
     - 惰性不可变序列、双重缓存机制、按需推进与反向切片变换
   * - ``PagedList``
     - ``yt_dlp/utils/_utils.py:4220-4250``
     - 分页抽象基类、页码缓存与索引转换
   * - ``OnDemandPagedList``
     - ``yt_dlp/utils/_utils.py:4255-4290``
     - 未知总页数动态按需抓取、局部切片与非满页终止判定
   * - ``InAdvancePagedList``
     - ``yt_dlp/utils/_utils.py:4295-4320``
     - 已知总页数状态机、精准页码范围计算与短路求值
   * - ``PlaylistEntries``
     - ``yt_dlp/utils/_utils.py:4325-4420``
     - 播放列表条目复合迭代器、``--playlist-items`` DSL 语法解析与前置过滤熔断
   * - ``YoutubeDL.__process_playlist``
     - ``yt_dlp/YoutubeDL.py:1120-1240``
     - 播放列表流式调度中枢、``--lazy-playlist`` 内存保护与平坦化丢弃

***
小结与下章导读
***

至此，我们完整解析了 **第 3 模块：InfoExtractor 抽象与解析流水线** 的全部核心基石：
1. ``03.01`` 中 ``InfoExtractor`` 基类架构、双向绑定与 ``_real_extract`` 设计范式；
2. ``03.02`` 中 URL 正则路由分发系统、零 I/O 快速 ID 提取与 ``GenericIE`` 多层级探测降级；
3. ``03.03`` 中 Web 页面多源微数据提取、Schema.org JSON-LD 递归图谱解析与 ``traverse_obj`` 声明式 DSL；
4. ``03.04`` 中 ``LazyList``、``PagedList`` 与 ``PlaylistEntries`` 构筑的常数级内存边界保护流式管道。

在接下来的 **第 4 模块：流媒体分片与下载器协议实现 (04_downloader_and_protocols)** 中，我们将深入音视频数据传输的物理引擎——剖析 ``FileDownloader`` 多态体系、原生 HTTP 分块下载、HLS (M3U8) AES-128-CBC 动态解密与 DASH (MPD) 清单索引计算。
