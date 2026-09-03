========================================================================================
01.04 download_archive 与幂等去重状态持久化机制
========================================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们完整剖析了 ``YoutubeDL`` 的参数解析状态机、核心调度提取流水线以及输出模板路径生成引擎。当音视频物理数据完成下载与格式后处理后，流媒体下载引擎必须解决大规模增量抓取与周期性订阅归档的工程核心难题——**“去重幂等与状态持久化”**。本节将深度解构 ``yt-dlp`` 的 ``download_archive`` 架构，剖析基于复合键的记录机制、跨平台并发文件锁（Windows ``LockFileEx`` 与 POSIX ``flock``/``fcntl``）的原子安全控制、双阶段短路熔断状态机以及历史 ID 兼容迁移算法。

***
download_archive 核心架构与复合键记录模型
***

在分布式抓取或长期订阅场景中，重复下载已归档的视频不仅浪费带宽与算力，还可能触发目标站点的风控封禁。``yt-dlp`` 采用轻量级纯文本行存储配合内存哈希集合（``set``），构建了高吞吐、零外部数据库依赖的归档持久化模型。

.. code-block:: text
   :caption: download_archive 全生命周期与内存镜像流向

   +-------------------------------------------------------------------+
   | 1. 初始化预加载 (YoutubeDL.__init__)                              |
   |    - 检查 params['download_archive']                              |
   |    - 使用 locked_file 获取只读共享锁 (Shared Lock)                |
   |    - 逐行 strip() 并装载至内存集合 self.archive = set()            |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 2. 阶段一：提取前预检短路 (Pre-extraction Check)                  |
   |    - temp_id = ie.get_temp_id(url) 快速无网络开销提取 ID          |
   |    - 匹配 in_download_archive() --> 命中直接跳过，支持 break 中断 |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 3. 阶段二：清洗后精确断言 (Post-extraction Match Filter)          |
   |    - 结合完整 info_dict 与 _old_archive_ids 综合判定              |
   |    - 命中则拦截后继物理下载，抛出 ExistingVideoReached (可选)     |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 4. 阶段三：物理落盘后原子追加 (Post-download Record)              |
   |    - 校验所有分片/音频/视频流成功状态 (__write_download_archive)   |
   |    - locked_file 获取独占排他锁 (Exclusive Lock)                  |
   |    - 原子追加写入 vid_id + '
'，并同步更新内存 self.archive      |
   +-------------------------------------------------------------------+

复合归档键生成算法 (`make_archive_id`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了避免不同视频平台之间数字或短哈希 ID 的偶然碰撞（例如 YouTube 视频 ID 与 Bilibili 稿件 ID 发生同名），``yt-dlp`` 强制采用 **“提取器标识符 + 实体唯一 ID”** 的复合主键体系：

.. code-block:: python

   def make_archive_id(ie, video_id):
       ie_key = ie if isinstance(ie, str) else ie.ie_key()
       return f'{ie_key.lower()} {video_id}'

在 ``YoutubeDL._make_archive_id(info_dict)`` 中，主键提取逻辑具备向后兼容与自适应回退能力：

1. 优先读取 ``info_dict['extractor_key']`` 或 ``info_dict['ie_key']``；
2. 若外层元数据缺失提取器标识，则尝试使用 ``info_dict['url']`` 重新在 ``self._ies`` 路由表中进行 ``ie.suitable(url)`` 正则反查；
3. 统一将提取器名称转换为小写（``ie_key.lower()``），彻底消除跨版本大小写重构带来的不兼容隐患。

---
跨平台并发文件锁：locked_file 深度实现
---

在大规模爬虫集群或本地多进程并发运行（例如通过 ``xargs -P`` 或多实例并行下载频道列表）时，多个进程可能同时读取或追加同一个 ``download_archive`` 文件。若缺乏强有力的文件锁保障，追加写操作将发生数据覆盖、行错位或截断损坏。

``yt-dlp/utils/_utils.py`` 中的 ``locked_file`` 类封装了针对 Windows 与 POSIX 系统的跨平台原子锁机制。

.. list-table:: 跨平台文件锁技术选型与系统调用对比
   :widths: 22 38 40
   :header-rows: 1

   * - 操作系统体系
     - 底层系统调用 / API
     - 锁语义与特性实现
   * - Windows (Win32 API)
     - ``kernel32.LockFileEx`` / ``UnlockFileEx``
     - 基于 ``OVERLAPPED`` 异步结构；强制性文件锁（Mandatory Locking）；锁定全量虚拟区间 ``0x00000000 ~ 0x7FFFFFFF``
   * - Linux / macOS (POSIX)
     - ``fcntl.flock(fd, LOCK_EX | LOCK_SH)``
     - 建议性文件锁（Advisory Locking）；通过内核直接绑定 open file table description；跨子进程继承
   * - Android (AOSP)
     - ``fcntl.lockf(fd, F_LOCK | F_ULOCK)``
     - 针对无 ``flock()`` 支持的裁剪内核环境自动优雅降级为 POSIX 记录锁
   * - 虚拟化文件系统
     - ``fcntl.flock(fd, flags | fcntl.LOCK_NB)``
     - 兼容 VirtioFS / NFS 网络存储，防止解锁阶段阻塞死锁

Windows 底层 Win32 结构与锁标志
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Windows 平台上，标准 C 运行时库并不直接暴露细粒度共享/排他锁控制。``yt-dlp`` 通过 ``ctypes.WinDLL('kernel32')`` 直接调用 Win32 原生 API：

.. code-block:: python

   class OVERLAPPED(ctypes.Structure):
       _fields_ = [
           ('Internal', ctypes.wintypes.LPVOID),
           ('InternalHigh', ctypes.wintypes.LPVOID),
           ('Offset', ctypes.wintypes.DWORD),
           ('OffsetHigh', ctypes.wintypes.DWORD),
           ('hEvent', ctypes.wintypes.HANDLE),
       ]

   # 锁定整个 32 位地址空间范围 (0x00000000 ~ 0x7FFFFFFF)
   whole_low = 0xffffffff
   whole_high = 0x7fffffff

   def _lock_file(f, exclusive, block):
       overlapped = OVERLAPPED()
       f._lock_file_overlapped_p = ctypes.pointer(overlapped)
       flags = (0x2 if exclusive else 0x0) | (0x0 if block else 0x1)  # 0x2: LOCKFILE_EXCLUSIVE_LOCK, 0x1: LOCKFILE_FAIL_IMMEDIATELY
       handle = msvcrt.get_osfhandle(f.fileno())
       if not LockFileEx(handle, flags, 0, whole_low, whole_high, f._lock_file_overlapped_p):
           raise BlockingIOError(f'Locking file failed: {ctypes.FormatError(ctypes.GetLastError())!r}')

文件截断竞争防御（Race-Free Truncation）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Python 原生使用 ``open(fn, 'w')`` 时，操作系统会在调用 ``open()`` 的瞬间**立即执行文件截断（Truncate to 0 bytes）**。如果在截断之后才尝试获取文件锁，那么在获取锁之前的微小时间窗口内，其他并发进程读取到的将是一个被清空的损坏文件。

``locked_file`` 严密重构了底层文件打开与截断的时序：

.. code-block:: python

   # 1. 组合底层系统 open 标志位，确保在加锁前绝不执行 O_TRUNC
   flags = functools.reduce(operator.ior, (
       getattr(os, 'O_CLOEXEC', 0),
       getattr(os, 'O_BINARY', 0),
       os.O_CREAT if writable else 0,
       os.O_APPEND if 'a' in mode else 0,
       os.O_EXCL if 'x' in mode else 0,
       os.O_RDONLY if not writable else os.O_RDWR if readable else os.O_WRONLY,
   ))
   self.f = os.fdopen(os.open(filename, flags, 0o666), mode, encoding=encoding)

   # 2. 获取排他锁
   _lock_file(self.f, exclusive, self.block)

   # 3. 只有在成功持有排他锁之后，才安全执行截断
   if 'w' in self.mode:
       self.f.truncate()

---
双阶段短路去重与快速熔断状态机
---

在大规模播放列表（例如包含 10,000 个视频的频道）巡检过程中，如果对每个视频都发起 HTTP 请求抓取完整 HTML 和 DASH/HLS 清单后再判定是否已归档，将造成极大的网络浪费。

``yt-dlp`` 设计了 **双阶段过滤与短路熔断机制**：

.. code-block:: text
   :caption: 双阶段去重决策与熔断状态机

                       进入播放列表条目循环
                                |
                                v
   +-------------------------------------------------------------------+
   | [阶段 1: 无网络开销预检]                                           |
   | 调用 ie.get_temp_id(url) 基于 URL 正则直接抽取临时 ID             |
   | in_download_archive({'id': temp_id, 'ie_key': key})               |
   +--------------------------------+----------------------------------+
                                    |
                     +--------------+--------------+
                     |                             |
                   已归档                        未归档
                     v                             v
   [输出 [download] ID: has already ...]  [执行 ie.extract(url) 真实网页抓取]
                     |                             |
                     v                             v
   +---------------------------------+    +------------------------------------+
   | 检查 --break-on-existing 标志位  |    | [阶段 2: 规整后精确断言]           |
   +----------------+----------------+    | in_download_archive(info_dict)     |
                    |                     | 检查当前 ID 与 _old_archive_ids    |
           +--------+--------+            +-----------------+------------------+
           |                 |                              |
         开启               关闭                   +--------+--------+
           v                 v                     |                 |
   [抛出异常中断]    [继续下一项迭代]            已归档            未归档
   ExistingVideoReached                            v                 v
   [终止整个列表/频道]                   [跳过当前条目下载]   [进入音视频物理下载管线]
                                                   |                 |
                                                   v                 v
                                         [触发 break_on_existing] [落盘后写入归档记录]

阶段 1：URL 正则零网络预检 (`get_temp_id`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

大多数提取器（如 YouTube、Bilibili、Twitter）的视频 ID 直接编码在 URL 路径或查询参数中（如 ``v=dQw4w9WgXcQ`` 或 ``/video/BV1xx411c7mD``）。``InfoExtractor.get_temp_id(url)`` 仅通过内存正则表达式提取 ID，无需发起任何网络请求即可直接完成 ``in_download_archive()`` 断言。

阶段 2：历史 ID 别名映射与平滑迁移 (`_old_archive_ids`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在提取器重构、上游平台改版或提取器合并过程中，视频的主键标识符可能会发生变更（例如从数字 ID 迁移为字符串 UUID，或提取器名称从 ``Youtube`` 变更为 ``YoutubeTab``）。

为了保证用户的历史 ``download_archive`` 文件永久有效，``info_dict`` 支持注入 ``_old_archive_ids`` 列表：

.. code-block:: python

   def in_download_archive(self, info_dict):
       if not self.archive:
           return False

       vid_ids = [self._make_archive_id(info_dict)]
       vid_ids.extend(info_dict.get('_old_archive_ids') or [])
       return any(id_ in self.archive for id_ in vid_ids)

只要当前视频的全新 ID 或任意一个历史别名 ID 命中内存集合，下载器即判定去重生效，从而实现了多版本间的无缝平滑迁移。

---
特殊执行模式下的归档控制策略
---

在复杂的自动化脚本与归档调度任务中，用户常常需要干预归档写入行为：

.. list-table:: 归档控制参数与行为矩阵
   :widths: 26 28 46
   :header-rows: 1

   * - 配置参数
     - 适用场景
     - 归档核心行为与逻辑流向
   * - ``--download-archive FILE``
     - 默认增量下载
     - 仅当音视频物理文件及全部后处理器链执行成功后，才触发 ``record_download_archive``
   * - ``--force-write-archive``
     - 模拟归档 / 标记已读
     - 在 ``--simulate``、``--skip-download`` 或仅提取元数据时，**强制将记录写入归档文件**
   * - ``--break-on-existing``
     - 订阅追更增量同步
     - 遍历频道按时间倒序排列的列表，一旦遇到首个已归档视频立即抛出 ``ExistingVideoReached`` 终止遍历
   * - ``--break-per-url``
     - 批量 URL 队列控制
     - 将 ``--break-on-existing`` 的中断作用域限制在单个输入 URL（如单播放列表），而不影响队列中后续 URL

---
端到端调用时序与源码行级对照表
---

.. code-block:: text
   :caption: download_archive 全链路调用时序

   YoutubeDL.__init__()          extract_info()          process_info()          locked_file
          |                            |                       |                      |
          |-- preload_archive() ------>|                       |                      |
          |    |-- open(archive) ---------------------------------------------------->| (获取只读共享锁)
          |    |<-- lines -------------|                       |                      |
          |    \-- self.archive = set()|                       |                      |
          |                            |                       |                      |
          |                            |-- get_temp_id(url)    |                      |
          |                            |-- in_download_archive |                      |
          |                            |   (若已归档则短路)    |                      |
          |                            |                       |                      |
          |                            |                       |-- dl() 物理下载      |
          |                            |                       |-- post_process()     |
          |                            |                       \-- record_archive() ->|
          |                            |                                              |-- open(archive, 'a')
          |                            |                                              |   (获取独占排他锁)
          |                            |                                              |-- write(vid_id + '
')
          |                            |                                              \-- self.archive.add()

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 归档持久化模块核心方法与源码位置
   :widths: 28 26 46
   :header-rows: 1

   * - 核心方法 / 类
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``locked_file``
     - ``yt_dlp/utils/_utils.py:210-310``
     - 跨平台文件锁（Win32 ``LockFileEx``、POSIX ``flock``/``lockf``）与安全延迟截断
   * - ``preload_download_archive()``
     - ``yt_dlp/YoutubeDL.py:510-525``
     - 初始化时加锁读取并构建内存归档哈希集合 ``self.archive``
   * - ``_make_archive_id()``
     - ``yt_dlp/YoutubeDL.py:1260-1280``
     - 生成 ``extractor_key.lower() + ' ' + video_id`` 标准复合主键
   * - ``in_download_archive()``
     - ``yt_dlp/YoutubeDL.py:1282-1290``
     - 综合主键与 ``_old_archive_ids`` 进行多版本兼容去重查询
   * - ``record_download_archive()``
     - ``yt_dlp/YoutubeDL.py:1292-1305``
     - 持有独占文件锁，原子追加写入并同步刷新内存集合
   * - ``_match_entry()``
     - ``yt_dlp/YoutubeDL.py:732-790``
     - 结合归档状态判定与 ``break_on_existing`` 快速熔断异常抛出

***
小结与下章导读
***

至此，我们完整解析了 **第 1 模块：请求生命周期与调度控制器** 的全部核心基石：
1. ``01.01`` 中 ``YoutubeDL`` 的参数解析状态机与上下文生命周期；
2. ``01.02`` 中 ``extract_info`` 的多态实体解包与选流决策规整流水线；
3. ``01.03`` 中 ``outtmpl`` 双层正则微语法引擎与沙箱安全防御；
4. ``01.04`` 中 ``download_archive`` 跨平台文件锁与幂等持久化机制。

在接下来的 **第 2 模块：网络请求层与协议栈适配 (02_networking_and_traffic)** 中，我们将深入引擎的物理网络中枢——剖析全新重构的 ``RequestDirector`` 架构，解密多后端网络处理器（``urllib``、``requests``、``curl_cffi``、``websockets``）的动态调度与协议栈自适应分发机制。
