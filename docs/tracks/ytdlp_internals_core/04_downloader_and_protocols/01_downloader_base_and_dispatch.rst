========================================================================================
04.01 FileDownloader 基类多态体系、协议探测自适应挂载与并发控制
========================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块中，我们深入剖析了 ``InfoExtractor`` 抽象体系如何通过正则路由、微数据结构化抽取以及 ``LazyList`` 流式生成器，将混乱的 Web 页面与异构 API 解析为标准化的音视频元数据字典（``info_dict``）。当提取阶段产出包含流媒体物理 URL、编码格式及分片清单的目标格式后，流媒体引擎的核心任务便切换至 **底层二进制比特流的物理抓取、分片组装与落盘持久化**。面对直接 HTTP 静态文件、自适应分片协议（HLS/DASH/ISM）、实时直播推流以及外部加速工具（Aria2c/FFmpeg/Curl），``yt-dlp`` 设计了高度解耦的 ``FileDownloader`` 多态体系。本节将全面剖析下载器自适应路由算法、进程间 IPC 管道桥接与健壮的生命周期状态机。

***
FileDownloader 多态体系与下载控制器拓扑
***

``yt-dlp`` 的下载子系统构建在 ``FileDownloader``（``yt_dlp/downloader/common.py``）抽象基类之上，形成了分层明确的多态继承族谱：

.. code-block:: text
   :caption: FileDownloader 继承族谱与架构拓扑

                                +--------------------------------+
                                |         FileDownloader         |
                                | (生命周期/状态机/限速/进度监控)|
                                +---------------+----------------+
                                                |
        +---------------------------------------+---------------------------------------+
        |                                       |                                       |
        v                                       v                                       v
   +----------+                           +------------+                          +------------+
   |  HttpFD  |                           | FragmentFD |                          | ExternalFD |
   |(原生单流)|                           |(切片分段流)|                          |(外部进程桥)|
   +----+-----+                           +-----+------+                          +-----+------+
        |                                       |                                       |
   +----+----+            +-------------+-------+-------+-------------+       +---------+----+----+---------+
   |  FtpFD  |            |             |               |             |       |         |    |    |         |
   +---------+            v             v               v             v       v         v    v    v         v
                     +---------+   +----------+    +----------+   +-------+ +----+   +----+ +----+ +----+ +------+
                     |  HlsFD  |   | DashFD   |    |  IsmFD   |   | F4mFD | |Aria|   |FFm | |Curl| |Wget| |Axel  |
                     |(Native) |   |(Segments)|    |(Smooth)  |   |(Adobe)| |2c  |   |peg | |    | |    | |/Http |
                     +---------+   +----------+    +----------+   +-------+ +----+   +----+ +----+ +----+ +------+

核心职责划分
~~~~~~~~~~~~

1. **``FileDownloader`` 基类**：统管下载生命周期、断点续传检查、``.part`` 临时文件原子重命名、令牌桶限速（``slow_down``）、多行终端进度渲染（``MultilinePrinter``）以及文件系统异常重试（``wrap_file_access``）；
2. **``FragmentFD`` 分段基类**：定义分片流媒体协议通用骨架，统管分片重试队列、AES 解密管道挂载、分片并发拉取以及断点拼接；
3. **``ExternalFD`` 外部下载器基类**：实现与第三方高性能二进制工具的跨进程 IPC 管道桥接，负责命令行转译、Cookie 凭证注入与子进程信号捕获。

---
协议探测与下载器自适应路由决议 (`get_suitable_downloader`)
---

当 ``YoutubeDL`` 准备下载某一目标格式时，调用 ``yt_dlp/downloader/__init__.py`` 中的 ``get_suitable_downloader`` 函数。该函数根据 ``info_dict`` 的协议特征、URL 结构与用户运行时参数，动态计算出最优下载器类。

.. code-block:: text
   :caption: get_suitable_downloader 优先级决议流水线

   info_dict (包含 protocol, url, is_live, impersonate 等)
                          |
                          v determine_protocol() 规范化协议名称
   +-------------------------------------------------------------------+
   | 1. 外部下载器参数评估 (params.get('external_downloader'))          |
   |    - 检查是否配置全局或协议专属外部下载器 (如 aria2c, ffmpeg)     |
   |    - 评估指纹伪装安全约束:                                        |
   |      * 若启用了 impersonate (TLS/JA3 伪装)，强制禁用外部工具，    |
   |        自动回退至 Native 原生下载器以维持 TLS 特征一致性          |
   +------------------------------+------------------------------------+
                                  |
                  +---------------+---------------+
                  |                               |
              命中外部下载器                  未命中/回退原生
                  v                               v
   +------------------------------+   +--------------------------------+
   | 2. ExternalFD.can_download() |   | 3. 流媒体专用分发规则          |
   |    - 检查二进制可执行文件路径|   |    - m3u8/m3u8_native:         |
   |    - 校验协议支持白名单      |   |      * is_live -> FFmpegFD     |
   |    - 命中则直接返回该 FD 类  |   |      * 静态点播 -> HlsFD (原生)|
   +------------------------------+   |    - http_dash_segments:       |
                                      |      * is_live -> FFmpegFD     |
                                      |      * 点播 -> DashSegmentsFD  |
                                      |    - 直播弹幕 -> LiveChatFD    |
                                      |    - 标准 HTTP/FTP -> HttpFD   |
                                      +---------------+----------------+
                                                      |
                                                      v
                                        [返回最优 Downloader 类]

复合协议解构（Composite Protocols）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在双流合并或 DASH 复合场景中，协议字段可能呈现为复合形式（如 ``http_dash_segments+https`` 或 ``m3u8_native+m3u8_native``）。
* 路由分发器通过 ``protocol.split('+')`` 拆分并独立解析子协议下载器；
* 当两个流均指向 ``FFmpegFD`` 时，触发 ``FFmpegFD.can_merge_formats()``，直接由单个 FFmpeg 子进程同时输入双流并在下载过程中完成动态多路复用（Muxing），避免生成中间碎片文件。

---
通用下载状态机与生命周期控制
---

``FileDownloader.download()`` 封装了工业级的通用下载状态机：

.. code-block:: text
   :caption: FileDownloader 核心状态机生命周期

              +------------------------------------------+
              | 状态 1: 幂等与断点探测 (Idempotence)    |
              | 检查目标文件是否存在 & continuedl 是否开启|
              +--------------------+---------------------+
                                   |
                   +---------------+---------------+
                   |                               |
                文件已完工                     需要拉取/续传
                   v                               v
       [上报已下载并快速短路退出]      +-----------------------------------+
                                       | 状态 2: 礼貌防爬睡眠 (Politeness) |
                                       | 根据 sleep_interval 执行动态休眠  |
                                       +-----------------+-----------------+
                                                         |
                                                         v
                                       +-----------------------------------+
                                       | 状态 3: 派发 real_download()      |
                                       | 执行特定协议二进制流拉取与解密    |
                                       +-----------------+-----------------+
                                                         |
                                         +---------------+---------------+
                                         |                               |
                                       成功                            异常
                                         v                               v
                       +-----------------------------------+   [触发 RetryManager]
                       | 状态 4: 原子重命名与状态清理      |   [记录失败并抛出异常]
                       | os.replace(.part, target_file)    |
                       | 广播 status='finished' 进度钩子   |
                       +-----------------------------------+

文件访问容错装饰器 (`wrap_file_access`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在高并发下载或多进程争用场景下，文件系统 I/O 极易遭遇临时锁定（Windows 共享冲突、杀毒软件扫描锁、``EACCES`` / ``EINVAL``）。
``FileDownloader`` 实现了方法级装饰器 ``wrap_file_access``，结合 ``RetryManager`` 构筑了微秒级指数退避自愈管道：

.. code-block:: python

   def wrap_file_access(action, *, fatal=False):
       def error_callback(err, count, retries, *, fd):
           return RetryManager.report_retry(
               err, count, retries, info=fd.__to_screen,
               warn=lambda e: (time.sleep(0.01), fd.to_screen(f'[download] Unable to {action} file: {e}')),
               error=None if fatal else lambda e: fd.report_error(f'Unable to {action} file: {e}'),
               sleep_func=fd.params.get('retry_sleep_functions', {}).get('file_access'))

       def wrapper(self, func, *args, **kwargs):
           for retry in RetryManager(self.params.get('file_access_retries', 3), error_callback, fd=self):
               try:
                   return func(self, *args, **kwargs)
               except OSError as err:
                   if err.errno in (errno.EACCES, errno.EINVAL):
                       retry.error = err
                       continue
                   retry.error_callback(err, 1, 0)
       return functools.partial(functools.partialmethod, wrapper)

---
外部下载器 IPC 管道桥接与跨进程通信 (ExternalFD)
---

当用户指定 ``--downloader aria2c`` 或需使用 FFmpeg 录制直播流时，引擎通过 ``ExternalFD`` 启动外部子进程并进行双向交互。

1. 命令行参数自适应转译与安全注入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

不同 CLI 工具的参数语法差异巨大。``ExternalFD`` 提供了声明式参数映射器（``_option``、``_bool_option``、``_valueless_option``）将 ``YoutubeDL`` 的通用参数精准编译为目标二进制的专属 CLI 选项：

.. list-table:: 外部下载器核心 CLI 参数转译矩阵
   :widths: 22 26 26 26
   :header-rows: 1

   * - 引擎参数
     - Aria2c 转译结果
     - Curl 转译结果
     - Wget 转译结果
   * - ``ratelimit``
     - ``--max-overall-download-limit <val>``
     - ``--limit-rate <val>``
     - ``--limit-rate <val>``
   * - ``continuedl``
     - ``--remove-control-file=false``
     - ``--continue-at -``
     - (默认开启续传)
   * - ``nocheckcertificate``
     - ``--check-certificate=false``
     - ``--insecure``
     - ``--no-check-certificate``
   * - ``source_address``
     - ``--interface <ip>``
     - ``--interface <ip>``
     - ``--bind-address <ip>``

2. Cookie 凭证跨进程无盘传递
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为防止在磁盘留下明文 Cookie 文件，针对支持 STDIN 读取的现代版本 Curl（$\ge 7.59$）或 Unix 命名管道，引擎采用内存注入：

.. code-block:: python

   if self._curl_version >= (7, 59):
       cmd += ['--cookie', '-']  # 告知 curl 从 stdin 接收 Cookie
       buffer = io.StringIO()
       self.ydl.cookiejar._really_save(buffer, True, True)
       return Popen.run(cmd, text=True, input=buffer.getvalue())

3. 信号捕获与优雅退出（Graceful Shutdown）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于正在录制直播的外部进程（如 FFmpeg），若直接发送 ``SIGKILL`` 信号终止进程，会导致输出的 MP4 容器尾部索引（``moov atom``）未正常闭合而变成损坏文件。
* ``ExternalFD`` 捕获用户的 ``KeyboardInterrupt``（Ctrl+C）；
* 拦截终止信号，通过标准输入向 FFmpeg 进程写入 ASCII 字符 ``q``；
* 触发 FFmpeg 内部正常收尾逻辑，平合封装元数据后以退出码 0 优雅退出。

---
端到端下载器调度时序图与源码映射
---

.. code-block:: text
   :caption: 下载器路由分发与执行端到端调用链

   YoutubeDL.process_info()        get_suitable_downloader()       FileDownloader (e.g. Aria2cFD)       External Process
              |                               |                                |                              |
              |-- get_suitable_downloader() ->|                                |                              |
              |   (传入 info_dict 与 params)  |                                |                              |
              |<-- 返回 Aria2cFD 类 ----------|                                |                              |
              |                                                                |                              |
              |-- 实例化 fd = Aria2cFD(ydl, params) -------------------------->|                              |
              |-- fd.download(filename, info_dict) --------------------------->|                              |
              |                                                                |-- 检查 .part 文件与幂等状态  |
              |                                                                |-- _write_cookies() 准备凭证  |
              |                                                                |-- _make_cmd() 编译命令行     |
              |                                                                |-- Popen.run(cmd) ----------->| 启动 aria2c 进程
              |                                                                |                              |-- 多线程高速分块拉取
              |                                                                |<-- 进程退出返回 returncode --|
              |                                                                |-- try_rename(.part, target)  |
              |                                                                |-- 广播 status='finished'     |
              |<-- 返回 (True, True) ------------------------------------------|                              |

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 下载器基类与分发核心模块与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``get_suitable_downloader()``
     - ``yt_dlp/downloader/__init__.py:4-22``
     - 全局协议自适应嗅探、复合协议解析与外部下载器挂载
   * - ``FileDownloader``
     - ``yt_dlp/downloader/common.py:35-180``
     - 下载抽象基类、多行进度监控、限速令牌桶与生命周期统管
   * - ``wrap_file_access``
     - ``yt_dlp/downloader/common.py:185-215``
     - 文件系统 I/O 操作异常拦截与指数退避重试装饰器
   * - ``ExternalFD``
     - ``yt_dlp/downloader/external.py:20-135``
     - 外部下载器跨进程 IPC 通信抽象基类、Cookie 注入与分片合并
   * - ``FFmpegFD``
     - ``yt_dlp/downloader/external.py:280-450``
     - FFmpeg 进程封装、多音视频流实时 Direct-Merge 与直播优雅停机
   * - ``Aria2cFD``
     - ``yt_dlp/downloader/external.py:205-265``
     - Aria2c 高性能 16 线程分片加速下载器封装与路径安全清洗

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 复杂而严密的下载器多态体系与自适应分发机制，厘清了：
1. ``FileDownloader``、``FragmentFD`` 与 ``ExternalFD`` 的层次继承拓扑；
2. ``get_suitable_downloader`` 基于协议特征、指纹伪装与直播状态的最优决议流；
3. 幂等检查、原子重命名与 ``wrap_file_access`` 文件系统容错管道；
4. 外部进程命令行自适应编译、内存 Cookie 传递与直播信号平滑退出机制。

在下一节（``02_http_and_chunked_transfer.rst``）中，我们将聚焦于纯原生网络流下载——深度解剖 ``HttpFD`` 如何通过 HTTP Range 请求实现断点续传、并发分块传输（Chunked Transfer）以及动态缓冲区与令牌桶限速算法的数学实现。
