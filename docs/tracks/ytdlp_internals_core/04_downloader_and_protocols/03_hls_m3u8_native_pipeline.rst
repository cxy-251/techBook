========================================================================================
04.03 Native HLS (M3U8) 解析器：AES-128-CBC 动态解密、DISCONTINUITY 断点缝合
========================================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们解构了 ``FileDownloader`` 多态继承架构以及原生 ``HttpFD`` 在单文件分块拉取与限速对抗中的底层机制。在现代互联网流媒体传输中，基于切片的自适应码率流媒体（Adaptive Bitrate Streaming, ABR）占据了 80% 以上的流量份额，其中由 Apple 主导制定的 **HTTP Live Streaming (HLS / RFC 8216)** 是应用最为广泛的行业标准。许多传统工具在处理 HLS 时极度依赖外部黑盒进程（如 FFmpeg），这在面临多线程分片加速、动态密钥注入、Cookie/指纹隔离以及广告切片过滤时存在严重的控制盲区。``yt-dlp`` 研发了纯原生的 **``HlsFD``（``yt_dlp/downloader/hls.py``）** 流水线。本节将深度解密其 M3U8 清单状态机、AES-128-CBC 动态密码学解密、不连续序列（``EXT-X-DISCONTINUITY``）缝合与多线程保序组装机制。

***
RFC 8216 HTTP Live Streaming (HLS) 协议规范与 Native 架构
***

HLS 协议将完整的音视频流分割为由索引清单（Playlist / Manifest）描述的连续短分片（通常为 2~10 秒的 TS 或 fMP4 切片）：

.. code-block:: text
   :caption: HLS 两级清单结构与 Native 组装架构

   主清单 Master Playlist (例如: master.m3u8)
   +-------------------------------------------------------------------+
   | #EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080 -> 1080p.m3u8|
   | #EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720  -> 720p.m3u8 |
   +---------------------------------+---------------------------------+
                                     |
                                     v 经 FormatSorter 选择最优变体流
   媒体清单 Media Playlist (例如: 1080p.m3u8)
   +-------------------------------------------------------------------+
   | #EXT-X-VERSION:3                                                  |
   | #EXT-X-TARGETDURATION:6                                           |
   | #EXT-X-MEDIA-SEQUENCE:1001                                        |
   | #EXT-X-KEY:METHOD=AES-128,URI="key.php?id=1",IV=0x00...01         |
   | #EXT-X-MAP:URI="init.mp4",BYTERANGE="718@0" (fMP4 初始化分片)     |
   | #EXTINF:6.000,                                                    |
   | segment_1001.ts                                                   |
   | #EXT-X-DISCONTINUITY (时间戳/编码参数重置点)                      |
   | #EXTINF:6.000,                                                    |
   | segment_1002.ts                                                   |
   +---------------------------------+---------------------------------+
                                     |
                                     v HlsFD 原生解析与并行下载流水线
   +-------------------------------------------------------------------+
   | 1. 并发拉取分片 (concurrent_fragment_downloads 线程池)            |
   | 2. 动态拉取密钥与 IV 推导 -> 执行 AES-128-CBC 解密                |
   | 3. 处理 EXT-X-MAP 初始化头注入与 DISCONTINUITY 时间戳缝合         |
   | 4. 消除广告切片 (#ANVATO / #UPLYNK) -> 组装输出单一完备媒体文件   |
   +-------------------------------------------------------------------+

Native HLS 流水线的工程优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~

相比直接调用外部 FFmpeg 进程，原生 ``HlsFD`` 具备显著的架构优势：
1. **连接与指纹完全受控**：复用主进程的 ``CookieJar``、``ImpersonateTarget`` 与代理连接池，规避外部工具因无法复用 TLS 指纹被 WAF 拦截的问题；
2. **多线程并发提速**：利用 ``concurrent_fragment_downloads`` 开启多线程并行拉取不同分片，将下载吞吐量提升 5~10 倍；
3. **精准字节级广告剥离**：能够在解包阶段直接识别并剔除服务端注入的广告分片（Ad Insertion），实现无损纯净翻录。

---
M3U8 语法树解析与分片状态机
---

``HlsFD.real_download()`` 对 M3U8 文本流执行单遍扫描（Single-pass Lexical Scan），构建分片元数据队列：

.. code-block:: text
   :caption: M3U8 逐行扫描与分片状态机转移

      M3U8 文本流输入
             |
             v 逐行扫描 for line in s.splitlines():
   +-------------------------------------------------------------------+
   | 遇到 #EXT-X-KEY:METHOD=...                                        |
   | -> 解析 URI、IV、KEYFORMAT，生成/更新当前分片的 decrypt_info 字典  |
   +---------------------------------+---------------------------------+
   | 遇到 #EXT-X-MAP:URI=...,BYTERANGE=...                             |
   | -> 提取 fMP4 初始化头，将其作为 frag_index=1 优先注入 fragments   |
   +---------------------------------+---------------------------------+
   | 遇到 #EXT-X-BYTERANGE:length[@offset]                             |
   | -> 计算当前分片在宿主大文件中的 [start:end] 字节偏移               |
   +---------------------------------+---------------------------------+
   | 遇到 #EXT-X-DISCONTINUITY                                         |
   | -> discontinuity_count += 1，标记不连续点                         |
   +---------------------------------+---------------------------------+
   | 遇到广告特征标签 (#ANVATO-SEGMENT-INFO / #UPLYNK-SEGMENT)         |
   | -> ad_frag_next = True，直接丢弃后续广告分片                      |
   +---------------------------------+---------------------------------+
   | 遇到非注释 URI 行                                                 |
   | -> 将分片封装为字典: {url, decrypt_info, byte_range, media_sequence}|
   | -> 压入 fragments 队列，推进 media_sequence += 1                  |
   +-------------------------------------------------------------------+

DRM 商业版权保护拦截
~~~~~~~~~~~~~~~~~~~~

针对受商业数字版权管理（DRM）保护的流，``HlsFD._has_drm()`` 扫描特定加密标签：
* **Apple FairPlay**: ``URI="skd://..."`` 或 ``KEYFORMAT="com.apple.streamingkeydelivery"``；
* **Microsoft PlayReady**: ``KEYFORMAT="com.microsoft.playready"``；
* **Adobe Flash Access**: ``#EXT-X-FAXS-CM:``。

一旦发现商业 DRM，引擎主动阻断并输出明确的错误提示，避免下载无法解密的密文碎片。

---
AES-128-CBC 密钥动态协商与实时解密管道
---

当 M3U8 声明 ``#EXT-X-KEY:METHOD=AES-128`` 时，每个媒体分片均经过标准对称加密保护。

.. code-block:: text
   :caption: AES-128 密钥协商与分片解密流

   分片元数据字典
   +-------------------------------------------------------------------+
   | URI: "https://example.com/key.bin"                                |
   | IV: 显式声明的十六进制 或 缺失                                    |
   | media_sequence: 1001                                              |
   +---------------------------------+---------------------------------+
                                     |
                                     v 提取密钥与 IV (FragmentFD.decrypter)
   +-------------------------------------------------------------------+
   | 1. 密钥获取与缓存:                                                |
   |    - 若 _key_cache 中存在 -> 直接复用 (避免上千次重复网络请求)    |
   |    - 若不存在 -> 发起 HTTP GET 拉取 16 字节密钥并存入 _key_cache  |
   | 2. IV 初始向量推导:                                               |
   |    - 若清单显式声明 IV -> binascii.unhexlify(IV[2:].zfill(32))    |
   |    - 若清单未声明 IV -> 依照 RFC 8216 规范推导:                   |
   |      iv = struct.pack('>8xq', fragment['media_sequence'])         |
   |      (前 8 字节填充 0x00，后 8 字节为大端序 64 位序列号)          |
   +---------------------------------+---------------------------------+
                                     |
                                     v 执行密码学解密
   +-------------------------------------------------------------------+
   | 优先调用 PyCryptodome (C 扩展加速):                               |
   |   Cryptodome.Cipher.AES.new(key, AES.MODE_CBC, iv).decrypt(data)  |
   | 兜底回退至内置纯 Python 实现 (yt_dlp/aes.py):                     |
   |   aes_cbc_decrypt_bytes(data, key, iv)                            |
   | 最终剥离 PKCS#7 填充: unpad_pkcs7(decrypted_data)                 |
   +-------------------------------------------------------------------+

隐式 IV 数学推导实现
~~~~~~~~~~~~~~~~~~~~

RFC 8216 规范第 5.2 节严格规定：*若 EXT-X-KEY 标签未显式包含 IV 属性，则必须将该媒体分片的序列号（Media Sequence Number）作为大端序 128 位无符号整数进行填充*。

``FragmentFD`` 实现了标准的大端序结构体打包：

.. code-block:: python

   # '>8xq' 表示: '>' 大端序, '8x' 8字节填充 (0x00*8), 'q' 8字节有符号/无符号四字整数 (64-bit int)
   iv = decrypt_info.get('IV') or struct.pack('>8xq', fragment['media_sequence'])
   # 最终生成 16 字节标准 CBC 初始向量: b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xe9'

---
EXT-X-DISCONTINUITY 不连续时间戳校准与分片缝合
---

在 HLS 广播与拼接点播中，``#EXT-X-DISCONTINUITY`` 标志着流的内部特征发生了根本性突变：
1. **文件格式与编码参数跳变**：从一种分辨率/码率切换至另一种分辨率，或编码 Profile 发生变更；
2. **时间戳重置（Epoch Reset）**：分片内部的 MPEG-TS 基础时间戳（PTS/DTS）发生不连续跳变或清零；
3. **广告插入（Ad Insertion）**：视频内容与贴片广告交界点。

WebVTT 外挂字幕的不连续滑动窗口去重
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 HLS 流包含 WebVTT 字幕轨道时，分片边界往往存在字幕重叠，且 MPEG PES 时间戳存在 33 位无符号整数回绕溢出（Wrap-around at $2^{33}$）。

``HlsFD`` 构建了基于时间轴校准与滑动窗口（``webvtt_dedup_window``）的缝合算法：

.. code-block:: python

   # 1. 检测 MPEG PES 33-bit 时间戳溢出 (90kHz 时钟下约 26.5 小时回绕一次)
   if block.mpegts < extra_state.get('webvtt_mpegts_last', 0):
       overflow = True
       block.mpegts += 1 << 33  # 补偿高位溢出

   # 2. 维护去重窗口，合并跨越多个分片的铰链字幕块 (Hinged CueBlocks)
   while i < len(dedup_window):
       wblock = webvtt.CueBlock.from_json(dedup_window[i])
       if wblock.hinges(block):  # 相邻分片中重叠的同一句字幕
           wcue['end'] = block.end  # 动态延长字幕结束时间
           is_new = False
           continue

---
并发分片下载与 .ytdl 断点状态机
---

在 ``FragmentFD.download_and_append_fragments`` 中，下载器通过线程池并发拉取分片，并维护状态机保证分片严格按序写入磁盘：

.. code-block:: python

   # 采用 ThreadPoolExecutor 并发下载，通过 pool.map 保持输出有序性
   with concurrent.futures.ThreadPoolExecutor(max_workers) as pool:
       for fragment, frag_index, frag_filename in pool.map(_download_fragment, fragments):
           ctx.update({'fragment_filename_sanitized': frag_filename, 'fragment_index': frag_index})
           # 顺序读取临时分片文件 -> 执行解密 -> 追加写入目标容器流 -> 立即删除临时分片
           raw_content = self._read_fragment(ctx)
           decrypted_content = decrypt_fragment(fragment, raw_content)
           self._append_fragment(ctx, decrypted_content)

断点续传状态持久化 (`.ytdl` 文件)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于数十 GB 的超长流媒体，为防止意外中断导致从头重下，引擎在下载期间实时写入 ``filename.ytdl`` JSON 状态文件：
* 记录 ``current_fragment.index`` 与已完成的物理字节数；
* 再次启动时读取 ``.ytdl``，校验目标文件的物理尺寸一致性后，直接跳过已完成分片，实现精准断点续传。

---
端到端 HLS 下载与解密时序图与源码映射
---

.. code-block:: text
   :caption: HlsFD 整体执行与解密调用链

   HlsFD.real_download()       M3U8 Parser                  decrypter & KeyCache           ThreadPoolExecutor
            |                       |                                 |                             |
            |-- 下载 M3U8 清单 ---->|                                 |                             |
            |-- can_download() 校验 |                                 |                             |
            |-- 扫描生成 fragments  |                                 |                             |
            |   (解析 KEY/MAP/IV) ->|                                 |                             |
            |                                                         |                             |
            |-- download_and_append_fragments() --------------------------------------------------->|
            |                                                         |                             |-- 并发拉取分片 1, 2, 3...
            |                                                         |                             |<-- 暂存至 .part-Frag* 文件
            |                                                         |                             |
            |                                                         |-- pool.map 保序产出 --------|
            |                                                         |-- 检查 KeyCache (拉取 key)  |
            |                                                         |-- struct.pack 构造 IV       |
            |                                                         |-- 执行 AES-128-CBC 解密     |
            |                                                         \-- dest_stream.write() 追加  |
            |                                                                                       |
            |-- 所有分片组装完毕 -------------------------------------------------------------------|
            |-- 移除 .ytdl 状态文件 ----------------------------------------------------------------|
            \-- try_rename(.part, filename) -> 交付最终媒体文件 -----------------------------------|

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: Native HLS 下载与解密核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``HlsFD.real_download()``
     - ``yt_dlp/downloader/hls.py:65-150``
     - M3U8 清单单遍扫描、标签属性提取、广告过滤与外部下载器挂载
   * - ``HlsFD.can_download()``
     - ``yt_dlp/downloader/hls.py:25-55``
     - 原生 HLS 特性兼容性检测与 FairPlay/PlayReady DRM 阻断识别
   * - ``FragmentFD.decrypter()``
     - ``yt_dlp/downloader/fragment.py:230-260``
     - AES-128 密钥会话级内存缓存、大端序 IV 推导与密码学解密管道
   * - ``download_and_append_fragments()``
     - ``yt_dlp/downloader/fragment.py:310-380``
     - 线程池并发分片拉取、保序解密聚合、断点追加与错误重试
   * - ``_read_ytdl_file()`` / ``_write_ytdl_file()``
     - ``yt_dlp/downloader/fragment.py:60-95``
     - ``.ytdl`` JSON 状态文件持久化与分片下载一致性校验

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 原生 HLS 下载引擎 ``HlsFD`` 的核心架构与算法，厘清了：
1. RFC 8216 HLS 清单层次体系与原生流水线相比外部工具在指纹/并发维度的优势；
2. M3U8 语法树单遍状态机、广告特征切片剔除与商业 DRM 拦截；
3. AES-128-CBC 密钥会话缓存、大端序隐式 IV 数学推导与 PKCS#7 解密管道；
4. 不连续时间戳缝合、WebVTT 33 位时间戳溢出校准与 ``.ytdl`` 断点状态机。

在下一节（``04_dash_mpd_and_segment_timeline.rst``）中，我们将切入另一大工业级自适应流媒体标准——深度剖析 ``DashSegmentsFD`` 如何解析复杂的 MPEG-DASH XML (MPD) 清单树、动态计算 ``SegmentTimeline`` 与 ``SegmentTemplate`` 寻址矩阵，并实现直播流滑动窗口的动态追赶。
