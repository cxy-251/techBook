========================================================================
第 4 模块：流媒体分片与下载器协议实现 (04_downloader_and_protocols)
========================================================================

本模块深入剖析 ``yt-dlp`` 在各种网络流媒体传输协议下的底层二进制抓取与组装引擎。涵盖传统单一流下载以及当代主流的切片式自适应码率协议 (HLS / DASH)。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_downloader_base_and_dispatch
   02_http_and_chunked_transfer
   03_hls_m3u8_native_pipeline
   04_dash_mpd_and_segment_timeline

模块核心要点
------------

1. **FileDownloader 基类与自适应路由**：多态分发模型、外部下载器 (`aria2c`, `ffmpeg`, `curl`, `wget`) 桥接与参数传递。
2. **原生 HTTP 分块传输协议**：基于 `HttpFD` 的 Range 请求断点续传、并发分片下载、动态缓冲区与令牌桶限速算法。
3. **Native HLS (M3U8) 组装流水线**：M3U8 标签解析、AES-128-CBC 密钥提取与实时解密、EXT-X-DISCONTINUITY 不连续时间戳校准与 Native 拼接。
4. **DASH (MPD) 清单与分片时间线**：SegmentBase / SegmentList / SegmentTemplate 寻址算法、动态 MPD 直播滑窗追赶与 init 分片注入。
