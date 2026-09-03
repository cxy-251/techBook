========================================================================================
04.02 原生 HTTP/HTTPS 断点续传、分块传输 (Chunked Transfer) 与精准限速令牌桶
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们全面解析了 ``FileDownloader`` 多态继承体系、协议探测自适应路由（``get_suitable_downloader``）以及外部进程 IPC 桥接机制。当流媒体的提取结果为直接指向 CDN 的单个大文件（如 MP4、WebM、FLV）或分块切片时，底层执行引擎将分发给原生网络下载器 **``HttpFD``（``yt_dlp/downloader/http.py``）**。面对大型 CDN 节点对长连接的动态限速（Bandwidth Throttling）、网络抖动导致的连接重置、以及 HTTP 416 范围溢出等复杂物理环境，``HttpFD`` 构建了一套基于 ``Range`` 协商的自愈状态机、防限速分块传输引擎以及动态缓冲区自适应算法。本节将深度解构其底层通信协议原语与数学模型。

***
原生 HTTP 流媒体传输模型与物理层挑战
***

在直接拉取 HTTP 音视频裸流时，流媒体传输面临着与普通网页静态文件完全不同的网络特征：

.. code-block:: text
   :caption: 流媒体 CDN 限速对抗与分块拉取模型

   传统单长连接模式 (易被 CDN 识别并降速):
   Client ====== HTTP GET /video.mp4 (无 Range 或单次全量) ======> CDN Server
   [0s - 2s]: TCP 慢启动突发 (满速 50MB/s)
   [2s 之后]: CDN 识别为视频播放，强制节流至 1.25x 播放码率 (降速至 500KB/s)
   [网络波动]: TCP 连接断开 -> 无法精确自愈

   yt-dlp http_chunk_size 分块并发/连续拉取模型 (突破限速):
   Client --- GET Range: bytes=0-10485759 (第1块 10MB) ---------> CDN (满速突发)
   Client --- GET Range: bytes=10485760-20971519 (第2块 10MB) --> CDN (重新建立连接/重置节流窗口)
   Client --- GET Range: bytes=20971520-31457279 (第3块 10MB) --> CDN (持续享受突发高带宽)
   (全生命周期维持最高物理带宽，且任意分块失败可独立原地重试)

---
HTTP Range 语义与断点续传状态机
---

``HttpFD`` 严格遵循 RFC 7233（HTTP/1.1 Range Requests）规范，并通过防御性设计消解服务端实现的非标准缺陷。

.. code-block:: text
   :caption: establish_connection 握手与 Range 状态机

   启动建立连接 (establish_connection)
                    |
                    v
   +-------------------------------------------------------------------+
   | 1. 探测本地 .part 文件与断点: ctx.resume_len = getsize(tmpfile)   |
   |    - 计算请求 Range: range_start = ctx.resume_len + req_start     |
   |    - 注入请求头: 'Accept-Encoding': 'identity' (强制禁用 gzip/br) |
   |    - 注入请求头: 'Range': f'bytes={range_start}-{range_end}'      |
   +--------------------------------+----------------------------------+
                                    |
                                    v 发起 HTTP 请求 (ydl.urlopen)
   +-------------------------------------------------------------------+
   | 2. 审查响应头 Content-Range 语义一致性                            |
   +--------------------------------+----------------------------------+
                                    |
                    +---------------+---------------+
                    |                               |
              服务端返回 206                 服务端返回 200 / 无 Content-Range
                    v                               v
   +--------------------------------+   +--------------------------------+
   | Content-Range 与 Range 吻合    |   | 服务端不支持断点续传 (忽略Range)|
   | 开启追加写入模式 ('ab')        |   | 截断清空本地 .part 文件 (0 字节)|
   | 成功进入流式下载               |   | 回退为覆盖写入模式 ('wb')      |
   +--------------------------------+   +--------------------------------+

1. 强制禁用传输压缩 (`Accept-Encoding: identity`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在常规 Web 浏览中，服务端常通过 gzip/brotli 压缩传输数据。然而在流媒体二进制下载中，若服务端返回压缩流，``Content-Length`` 将表示压缩后大小而非真实物理字节偏移，导致 ``Range`` 断点计算彻底错位。因此，``HttpFD`` 显式强制设置 ``Accept-Encoding: identity``，禁止中间代理和 CDN 进行二次编码。

2. HTTP 416 范围溢出与 $\pm 100$ 字节容错算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当客户端请求的 ``range_start`` 大于或等于服务端文件总大小时，服务端返回 ``HTTP 416 Range Not Satisfiable``。这通常发生在上次下载已基本完成但未及时重命名的边界情况下。

对于 YouTube / GoogleVideo 等大型 CDN，服务端由于分布式元数据同步或尾部填充（Padding），同一视频的实际文件长度可能存在微小的动态波动（通常在 100 字节以内）。

.. code-block:: python

   except HTTPError as err:
       if err.status == 416:
           # 发生 416 时，去掉 Range 头重新探测服务端的实际真实 Content-Length
           ctx.data = self.ydl.urlopen(Request(url, request_data, headers))
           content_length = ctx.data.headers['Content-Length']

           # 关键容错判定: 本地已下载字节与服务端声明长度差异小于 100 字节
           if content_length and (ctx.resume_len - 100 < int(content_length) < ctx.resume_len + 100):
               self.report_file_already_downloaded(ctx.filename)
               self.try_rename(ctx.tmpfilename, ctx.filename)
               self._hook_progress({'status': 'finished', 'total_bytes': ctx.resume_len}, info_dict)
               raise SucceedDownload  # 判定下载成功，优雅退出
           else:
               # 真实长度严重不符，判定为脏数据，从 0 字节重新开始
               self.report_unable_to_resume()
               ctx.resume_len = 0
               ctx.open_mode = 'wb'

---
http_chunk_size 分块传输与防限速抖动机制
---

为绕过 CDN 的长连接速率节流，用户可通过 ``--http-chunk-size 10M`` 启用分块流式传输。

1. 随机化抖动（Jittering）消除指纹
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

固定大小的分块请求（如严格连续的 10,485,760 字节）极易被 WAF 识别为爬虫行为。``HttpFD`` 在每次分块请求前注入随机抖动：

.. code-block:: python

   ctx.chunk_size = (
       random.randint(int(chunk_size * 0.95), chunk_size)
       if not is_test and chunk_size else chunk_size
   )

每次请求的块大小在 $[0.95 	imes 	ext{chunk\_size}, 	ext{chunk\_size}]$ 之间随机浮动，有效打乱网络请求特征指纹。

2. NextFragment 零惩罚状态机转移
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当单个 Chunk 数据块读取完毕且文件尚未结束时，下载器抛出内部受控异常 ``NextFragment``：

.. code-block:: python

   for retry in RetryManager(self.params.get('retries'), self.report_retry):
       try:
           establish_connection()
           return download()
       except NextFragment:
           retry.error = None
           retry.attempt -= 1  # 关键: 抵消重试计数器递增，分块正常推进不消耗网络重试额度
           continue

该设计使得上千个分块的连续拉取能够复用主外层重试状态机，且完全不会触发“超过最大重试次数”的误判。

---
动态自适应缓冲区与限速令牌桶模型
---

1. 动态缓冲区自适应算法 (`best_block_size`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Python 运行时中，``socket.read()`` 调用的系统调用（Syscall）上下文切换开销不可忽视。若缓冲区过小（如 1KB），极高吞吐率下将产生大量 Syscall 导致 CPU 100% 阻塞；若缓冲区过大，则无法精细控制限速和进度渲染。

``FileDownloader.best_block_size`` 实现了基于上一次 I/O 耗时的 **动态自适应调节算法**：

.. code-block:: python

   @staticmethod
   def best_block_size(elapsed_time, bytes):
       # 动态设定上下限边界 (最大 4MB，最小为上次读取量的一半)
       new_min = max(bytes / 2.0, 1.0)
       new_max = min(max(bytes * 2.0, 1.0), 4194304)  # 4MB 上限
       if elapsed_time < 0.001:  # 耗时极短 (<1ms)，说明带宽极充裕，直接扩容至上限
           return int(new_max)
       rate = bytes / elapsed_time  # 计算瞬时吞吐速率
       if rate > new_max:
           return int(new_max)
       if rate < new_min:
           return int(new_min)
       return int(rate)

2. slow_down 令牌桶时间差平滑限速
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户设置 ``--limit-rate 5M``（``ratelimit = 5,242,880``）时，下载器在每个数据块写入后调用 ``slow_down`` 执行时间差补偿：

.. code-block:: python

   def slow_down(self, start_time, now, byte_counter):
       rate_limit = self.params.get('ratelimit')
       if rate_limit is None or byte_counter == 0:
           return
       if now is None:
           now = time.time()
       elapsed = now - start_time
       if elapsed <= 0.0:
           return
       speed = float(byte_counter) / elapsed
       # 若实际速率超过设定阈值，计算理论所需时间与实际消耗时间的差值并执行睡眠
       if speed > rate_limit:
           sleep_time = float(byte_counter) / rate_limit - elapsed
           if sleep_time > 0:
               time.sleep(sleep_time)

3. 被动节流探测与自愈 (`throttledratelimit`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户配置 ``--throttled-rate 100K`` 时，若下载瞬时速度低于 100KB/s 持续超过 3 秒，``HttpFD`` 主动抛出 ``ThrottledDownload`` 异常：
* 终止当前僵死或受控降速的 TCP 连接；
* 触发 ``YoutubeDL`` 的流媒体重新提取（Re-extract）或更换 IP / 协议后端重试，实现全自动防限速自愈。

---
端到端 HTTP 流式下载时序图与源码映射
---

.. code-block:: text
   :caption: HttpFD 分块拉取与自适应下载端到端调用链

   HttpFD.real_download()      establish_connection()               download() Loop                CDN Webserver
            |                           |                                  |                             |
            |-- 初始化 Context ---------|                                  |                             |
            |-- establish_connection()->|                                  |                             |
            |                           |-- 计算 Range: bytes=0-10485759   |                             |
            |                           |-- 发起 GET 请求 ---------------------------------------------->|
            |                           |<-- 返回 206 Partial Content (Content-Range 校验通过) ----------|
            |                           \-- 挂载 ctx.data 流 ------------->|                             |
            |                                                              |-- 进入 while 循环           |
            |                                                              |-- ctx.data.read(block_size)->|
            |                                                              |<-- 返回 64KB 二进制流 -------|
            |                                                              |-- ctx.stream.write(block)   |
            |                                                              |-- best_block_size 调整大小  |
            |                                                              |-- slow_down() 限速平滑      |
            |                                                              |-- 达到 Chunk 边界           |
            |                                                              \-- raise NextFragment        |
            |                                                                            |
            |<-- 捕获 NextFragment (attempt -= 1) ---------------------------------------/
            |
            |-- 二次调用 establish_connection() (Range: bytes=10485760-20971519) ------->|
            |-- 循环往复直到全文接收完毕 ------------------------------------------------->|
            |-- try_rename(.part, target) ------------------------------------------------|
            \-- 广播 status='finished' ----------------------------------------------------|

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 原生 HTTP 下载与限速核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``HttpFD.real_download()``
     - ``yt_dlp/downloader/http.py:20-80``
     - HTTP 下载主状态机、上下文初始化与外层重试调度
   * - ``establish_connection()``
     - ``yt_dlp/downloader/http.py:55-140``
     - Range 请求头构造、Content-Range 校验与 416 容错自愈
   * - ``download()`` 循环
     - ``yt_dlp/downloader/http.py:150-245``
     - 动态数据块读取、NextFragment 切块转移与限速监控
   * - ``best_block_size()``
     - ``yt_dlp/downloader/common.py:115-130``
     - 基于 I/O 耗时的动态自适应缓冲区计算模型（1B~4MB）
   * - ``slow_down()``
     - ``yt_dlp/downloader/common.py:135-150``
     - 时间差补偿精准滑动窗口限速算法
   * - ``parse_http_range()``
     - ``yt_dlp/utils/_utils.py:4080-4090``
     - 标准 HTTP Range 与 Content-Range 响应头双向解析器

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 原生 HTTP 下载引擎 ``HttpFD`` 的通信原理与算法实现，厘清了：
1. 强制 ``identity`` 编码与 ``Range`` / ``Content-Range`` 严格一致性校验机制；
2. HTTP 416 范围溢出下的 $\pm 100$ 字节尾部抖动自愈算法；
3. ``http_chunk_size`` 随机化抖动与 ``NextFragment`` 零惩罚状态机转移；
4. ``best_block_size`` 动态缓冲区伸缩、``slow_down`` 平滑限速与 ``throttledratelimit`` 主动熔断。

在下一节（``03_hls_m3u8_native_pipeline.rst``）中，我们将切入当代主流的自适应流媒体协议——深度解密 ``HlsFD`` 如何在没有外部 FFmpeg 依赖的情况下，通过 Native 原生管道完成 M3U8 清单递归展开、AES-128-CBC 动态密钥解密以及 ``EXT-X-DISCONTINUITY`` 不连续时间戳校准与缝合。
