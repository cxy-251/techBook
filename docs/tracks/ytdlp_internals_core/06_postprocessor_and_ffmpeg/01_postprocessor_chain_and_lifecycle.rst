========================================================================================
06.01 PostProcessor 插件链结构、POSTPROCESS_WHEN 多生命周期切入点
========================================================================================

.. note:: 前置背景与上下文承接
   在前一模块中，我们全面解析了 ``yt-dlp`` 格式选择 DSL、``FormatSorter`` 20+ 维排序算法以及音视频轨道兼容性矩阵。当网络下载器（Downloader）完成物理流或切片的抓取并将原始字节写入磁盘后，多媒体处理流水线并未终结，而是进入了全书最具工程延展性的核心中枢——**后处理器（PostProcessor）体系**。从分离音视频轨道的物理复用（Muxing）、流故障自愈（Fixup）、软字幕/封面图内嵌、动态转码到元数据清洗与章节切割，所有多媒体重构操作均由后处理器完成。为了在长流水线中精确控制各个处理器的触发时机，``yt-dlp`` 构建了高度模块化的插件链模型与 **``POSTPROCESS_WHEN`` 八大生命周期切入点**。本节将深度解构其元类包装、链式传递、文件跟踪状态机与钩子机制。

***
PostProcessor 插件化拓扑与架构设计
***

``yt-dlp`` 将所有对媒体元数据、辅助文件或音视频二进制流的后续加工操作抽象为 **``PostProcessor``（``yt_dlp/postprocessor/common.py``）** 基类。每一个后处理器独立封装单一职责，并在 ``YoutubeDL`` 的主控制循环中按序串联。

.. code-block:: text
   :caption: PostProcessor 插件链级联执行模型

   YoutubeDL 主调度器 (调度生命周期切入点: POSTPROCESS_WHEN)
             |
             v 传入 (files_to_delete_accum, info_dict)
   +-------------------------------------------------------------------------------+
   | PostProcessor 1 (例如: FFmpegMergerPP)                                        |
   |   - run(info_dict): 执行音视频物理混流                                        |
   |   - 返回: ([f137.mp4, f140.m4a], updated_info_dict)                          |
   +---------------------------------------+---------------------------------------+
                                           | 输出结果管道式传递给下一个 PP
                                           v
   +-------------------------------------------------------------------------------+
   | PostProcessor 2 (例如: FFmpegEmbedSubtitlePP)                                 |
   |   - run(info_dict): 将 VTT/SRT 字幕流内嵌至目标容器                           |
   |   - 返回: ([sub.vtt], updated_info_dict)                                      |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v
   +-------------------------------------------------------------------------------+
   | PostProcessor 3 (例如: EmbedThumbnailPP)                                      |
   |   - run(info_dict): 将 cover.jpg 作为原子附件写入容器                         |
   |   - 返回: ([cover.jpg], updated_info_dict)                                    |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v
   +-------------------------------------------------------------------------------+
   | 垃圾回收与中间文件清理 (Garbage Collection):                                  |
   |   - 若未开启 --keep-video: 调用 _delete_downloaded_files 物理删除中间文件     |
   |   - 若开启 --keep-video: 保留所有源分轨与衍生文件                             |
   +-------------------------------------------------------------------------------+

PostProcessor 基类核心契约
~~~~~~~~~~~~~~~~~~~~~~~~~~

每个 ``PostProcessor`` 遵循严格的输入/输出契约：

.. code-block:: python

   def run(self, information: dict) -> tuple[list[str], dict]:
       """
       执行后处理任务。
       
       :param information: 视频元数据字典 (必须包含 'filepath' 字段指向目标文件)
       :return: (files_to_delete, updated_information)
                - files_to_delete: 允许被主调度器安全清理的中间文件路径列表
                - updated_information: 经后处理修改/扩展后的元数据字典
       :raises PostProcessingError: 当后处理失败时抛出，由主流程决定重试或熔断
       """
       return [], information

PostProcessorMetaClass 元类包装机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了消除各子类重复编写生命周期通知代码，基类采用 ``PostProcessorMetaClass`` 元类，在类加载时自动拦截并装饰 ``run`` 方法：

.. code-block:: python

   class PostProcessorMetaClass(type):
       @staticmethod
       def run_wrapper(func):
           @functools.wraps(func)
           def run(self, info, *args, **kwargs):
               info_copy = self._copy_infodict(info)
               # 1. 触发后处理开始钩子 (status: 'started')
               self._hook_progress({'status': 'started'}, info_copy)
               ret = func(self, info, *args, **kwargs)
               if ret is not None:
                   _, info = ret
               # 2. 触发后处理完成钩子 (status: 'finished')
               self._hook_progress({'status': 'finished'}, info_copy)
               return ret
           return run

       def __new__(cls, name, bases, attrs):
           if 'run' in attrs:
               attrs['run'] = cls.run_wrapper(attrs['run'])
           return type.__new__(cls, name, bases, attrs)

---
POSTPROCESS_WHEN 八大生命周期切入点
---

传统的下载工具通常仅在“全部下载完成后”触发后处理，这无法满足诸如“在匹配过滤前动态修改标题”、“在下载前预取多源信息”或“在播放列表级聚合元数据”等复杂诉求。

``yt-dlp`` 定义了 8 个粒度精细的生命周期切入点：

.. code-block:: python

   POSTPROCESS_WHEN = (
       'pre_process',    # 1. 提取完成、未执行过滤与格式选择前
       'after_filter',   # 2. 刚刚通过 match_filter 检查后
       'video',          # 3. 进入单个视频处理管道起点
       'before_dl',      # 4. 格式选择完毕、即将发起物理网络下载前
       'post_process',   # 5. 文件下载成功后的主后处理链 (混流/转码/内嵌)
       'after_move',     # 6. 文件移动至最终输出目录后 (写扩展属性/快捷方式)
       'after_video',    # 7. 该视频的所有请求格式与分段全部处理完毕后
       'playlist',       # 8. 整个播放列表遍历聚合完毕后
   )

.. list-table:: POSTPROCESS_WHEN 生命周期切入点矩阵与典型插件挂载
   :widths: 18 24 58
   :header-rows: 1

   * - 切入点标识 (WHEN)
     - 触发位置 (YoutubeDL.py)
     - 典型应用场景与挂载插件
   * - **``pre_process``**
     - ``pre_process(ie_info, 'pre_process')``
     - 早期元数据重构：如 ``MetadataParserPP`` 基于正则清洗原始标题，供后续过滤与模板使用
   * - **``after_filter``**
     - ``pre_process(info_dict, 'after_filter')``
     - 过滤后初级修正：在确认视频不被丢弃后，对提取数据进行特定字段注入
   * - **``video``**
     - ``pre_process(info_dict, 'video')``
     - 视频实体生命周期初始化，配置章节信息与格式列表
   * - **``before_dl``**
     - ``pre_process(info_dict, 'before_dl')``
     - 下载前准备：如动态拉取第三方歌词/外部外挂字幕、创建特定关联临时文件
   * - **``post_process``**
     - ``post_process(dl_filename, info_dict)``
     - **核心后处理阶段**：``FFmpegMergerPP`` 混流、``FFmpegFixup*PP`` 容错修复、音频提取、字幕封面内嵌、SponsorBlock 片段裁剪
   * - **``after_move``**
     - ``run_all_pps('after_move', info_dict)``
     - 文件落盘后处理：``XAttrMetadataPP`` 写入 macOS/Linux 文件扩展属性、执行用户自定义命令（``ExecAfterDownloadPP``）
   * - **``after_video``**
     - ``run_all_pps('after_video', info_dict)``
     - 视频处理收尾：写入最终下载归档记录（``download_archive``）、多时间分段汇总
   * - **``playlist``**
     - ``__process_playlist(ie_result)``
     - 播放列表级后处理：生成专辑/播放列表级聚合 ``.info.json``、下载播放列表封面与汇总描述

---
后处理器管道调度与文件清理状态机
---

在 ``YoutubeDL`` 中，所有后处理器的链式执行由 ``run_pp`` 与 ``run_all_pps`` 驱动：

.. code-block:: python
   :caption: run_pp 核心调度与异常防护逻辑 (yt_dlp/YoutubeDL.py)

   def run_pp(self, pp, infodict):
       files_to_delete = []
       if '__files_to_move' not in infodict:
           infodict['__files_to_move'] = {}
       try:
           # 执行后处理器核心业务
           files_to_delete, infodict = pp.run(infodict)
       except PostProcessingError as e:
           if self.params.get('ignoreerrors') is True:
               self.report_error(e)
               return infodict
           raise

       if not files_to_delete:
           return infodict

       # 文件清理与保留控制
       if self.params.get('keepvideo', False):
           # 若开启 -k/--keep-video，将待删除文件登记入移动映射，防止被物理抹除
           for f in files_to_delete:
               infodict['__files_to_move'].setdefault(f, '')
       else:
           # 物理安全解链并删除中间过渡文件
           self._delete_downloaded_files(
               *files_to_delete, info=infodict, msg='Deleting original file %s (pass -k to keep)')
       return infodict

文件移动追踪与原子替换映射 (__files_to_move)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当视频在临时目录（``--paths temp:...``）下载并经过多道后处理后，最终由专门的 **``MoveFilesAfterDownloadPP``** 统一搬运至宿主最终目录（``--paths home:...``）。

``infodict['__files_to_move']`` 维护了一个动态路由字典：
* 键（Key）：后处理产生或移动前的源文件绝对路径；
* 值（Value）：目标目标文件绝对路径（若为 ``None`` 则代表该文件无需搬运，若为 ``''`` 则代表保留原位）。

.. code-block:: text
   :caption: 文件路径动态重映射与最终落盘流

   临时下载路径: /tmp/temp_video.f137.mp4
             |
             +-> FFmpegMergerPP -> 产出 /tmp/merged_video.mp4, 标记删除 f137.mp4
             |
             +-> FFmpegEmbedSubtitlePP -> 更新 /tmp/merged_video.mp4
             |
             v MoveFilesAfterDownloadPP
   最终目标路径: /Users/cxy251/Movies/MyVideo.mp4 (原子级重命名与跨盘搬运)

---
插件注册中心与参数安全传递架构
---

为了支持无侵入式扩展与第三方插件，``yt-dlp`` 建立了全局后处理器注册表（``globals.postprocessors`` 与 ``globals.plugin_pps``）。

插件动态注册机制 (Plugin Registration)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

所有继承自 ``PostProcessor`` 且以 ``PP`` 结尾的类，在模块导入时通过 ``register_plugin_spec`` 自动挂载至命名空间：

.. code-block:: python

   def get_postprocessor(key):
       """通过命令行简称 (如 'FFmpegMerger', 'EmbedThumbnail') 动态解析对应类"""
       return postprocessors.value[key + 'PP']

参数命名空间与后处理器参数注入 (_configuration_args)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

用户可以通过命令行向指定的后处理器注入专属的底层二进制参数（如向 FFmpeg 传递自定义 filter），语法结构为：
``--postprocessor-args "NAME:ARGS"``（例如 ``--postprocessor-args "Merger+ffmpeg:-c:v copy -c:a aac"``）。

后处理器基类通过 ``_configuration_args`` 自动完成多级作用域检索：
1. 查找 ``"{PP_NAME}+{EXE}"``（精确匹配当前后处理器和指定可执行程序）；
2. 查找 ``"{PP_NAME}"``（匹配当前后处理器）；
3. 查找 ``"default"``（全局默认参数兜底）。

---
后处理器生命周期执行时序图与源码映射
---

.. code-block:: text
   :caption: PostProcessor 端到端生命周期执行调用链

   YoutubeDL.process_info()
            |
            |-- 1. 触发 pre_process('before_dl') --------------------> 运行 before_dl 阶段 PPs
            |
            |-- 2. 执行网络下载 (dl) -> 产出临时文件 dl_filename
            |
            |-- 3. 动态注入自动修复与合并插件:
            |      - FFmpegMergerPP (若为多轨下载)
            |      - FFmpegFixup*PP (若存在时间戳/MOOV异常)
            |
            |-- 4. 触发 post_process(dl_filename) -------------------> 依次执行 post_process 链:
            |      |                                                    |-- FFmpegMergerPP.run()
            |      |                                                    |-- FFmpegEmbedSubtitlePP.run()
            |      |                                                    |-- EmbedThumbnailPP.run()
            |      |                                                    \-- FFmpegMetadataPP.run()
            |      |
            |      \-- 执行 MoveFilesAfterDownloadPP ---------------> 将文件从 Temp 移至 Home 最终目录
            |
            |-- 5. 触发 run_all_pps('after_move') --------------------> 运行 after_move 阶段 PPs:
            |                                                           |-- XAttrMetadataPP.run()
            |                                                           \-- ExecAfterDownloadPP.run()
            |
            \-- 6. 触发 run_all_pps('after_video') -------------------> 标记 download_archive 幂等归档

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: PostProcessor 架构核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``PostProcessor`` 基类
     - ``yt_dlp/postprocessor/common.py:25-140``
     - 后处理器契约规范、参数检索、通用日志与文件清理接口
   * - ``PostProcessorMetaClass``
     - ``yt_dlp/postprocessor/common.py:12-23``
     - 元类装饰器，自动向所有子类的 ``run()`` 注入进度与状态钩子
   * - ``POSTPROCESS_WHEN`` 常量
     - ``yt_dlp/utils/_utils.py:1675-1685``
     - 8 大生命周期切入点枚举定义
   * - ``YoutubeDL.run_pp()``
     - ``yt_dlp/YoutubeDL.py:2930-2960``
     - 单个后处理器安全执行沙箱、异常捕获与 ``-k`` 垃圾回收
   * - ``YoutubeDL.run_all_pps()``
     - ``yt_dlp/YoutubeDL.py:2962-2975``
     - 遍历特定生命周期阶段的后处理器队列并管道式传递元数据
   * - ``MoveFilesAfterDownloadPP``
     - ``yt_dlp/postprocessor/movefilesafterdownload.py:1-60``
     - 临时目录到最终宿主目录的原子化文件迁移与重命名引擎

***
小结与下章导读
***

本节深入剖析了 ``yt-dlp`` 后处理体系的架构中枢，明确了：
1. ``PostProcessor`` 插件化基类抽象与基于 ``PostProcessorMetaClass`` 的无侵入式钩子包装；
2. ``POSTPROCESS_WHEN`` 八大生命周期切入点（从 ``pre_process`` 到 ``after_move``）在主下载循环中的精准分布；
3. ``run_pp`` 与 ``__files_to_move`` 状态机在中间过渡文件跟踪与安全清理中的底层实现；
4. 动态插件注册中心与基于 ``--postprocessor-args`` 的多级参数安全分发机制。

在后处理器生态中，最庞大、最复杂的子集是以 **FFmpeg** 为核心的音视频重构引擎。在下一节（``06_postprocessor_and_ffmpeg/02_ffmpeg_merger_and_fixup.rst``）中，我们将深入解构 **``FFmpegMergerPP`` 多流复用器与流故障自愈体系（``FFmpegFixup`` 修复链）**，剖析其如何通过底层管道命令解决非等比像素（Stretched Aspect Ratio）、M3U8 AAC 时间戳断裂以及 MP4 重复 MOOV box 等工业级流媒体顽疾。
