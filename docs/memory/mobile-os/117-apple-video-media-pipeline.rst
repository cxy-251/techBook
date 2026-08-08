第117章：Apple Video Media Pipeline
===================================

核心知识点
----------

* Apple 视频栈可按 AVFoundation、Core Media、Core Video、VideoToolbox、Core Animation / Metal 分层理解，每层处理的数据对象不同。
* AVFoundation 负责 asset、track、player、reader、writer、capture 等高层媒体组织；它解决“资源是什么、如何读写、如何播放”的问题。
* Core Media 负责媒体时间与 sample 语义。CMTime 表示精确时间，CMSampleBuffer 绑定数据与时间，CMFormatDescription 描述 codec、尺寸、颜色与格式信息。
* Core Video 负责 CVPixelBuffer、pixel buffer pool 等像素内存对象，使 decoder、Metal、Core Animation 和 writer 能共享图像数据。
* VideoToolbox 的 VTDecompressionSession / VTCompressionSession 是公开硬件编解码访问边界；App 请求能力，具体硬件调度由系统决定。
* AVPlayer / AVPlayerItem 适合系统托管播放状态机；AVAssetReader / Writer 适合逐 sample 读取、处理与导出；AVSampleBufferDisplayLayer 适合 App 自己掌握 sample timing 的显示路径。
* Metal 可把 CVPixelBuffer 映射成 texture 做滤镜或合成，再把结果送到显示 layer 或 encoder。
* Apple 媒体排查应先确定当前数据是压缩 CMSampleBuffer、CVPixelBuffer、Metal texture、display layer 还是输出文件，再定位对应框架。

关键路径
--------

普通播放：

``AVAsset → AVPlayerItem → AVPlayer → Decode / Sync → AVPlayerLayer → Core Animation → Display``

逐帧处理与导出：

``AVAsset → AVAssetReader → CMSampleBuffer → VideoToolbox Decode / CVPixelBuffer → Metal Processing → VideoToolbox Encode → AVAssetWriter → Output File``

时间与像素对象关系：

``CMSampleBuffer = Media Data + CMTime + CMFormatDescription``

``Decoded Image → CVPixelBuffer → Core Animation / Metal / Encoder``

概念辨析
--------

* **AVPlayer vs AVAssetReader**：AVPlayer 让系统接管播放；Reader 让 App 自己消费 sample。
* **CMSampleBuffer vs CVPixelBuffer**：CMSampleBuffer 是媒体样本容器，可携带时间和格式；CVPixelBuffer 是解码后的像素内存。
* **Core Media vs Core Video**：Core Media 管时间与 sample 语义；Core Video 管像素 buffer。
* **VideoToolbox vs AVFoundation**：VideoToolbox 更接近 codec；AVFoundation 负责更高层的媒体工作流。
* **Core Animation vs Metal**：Core Animation 负责 layer 提交与显示；Metal 负责 App 主动编码 GPU 工作。

本章结论
--------

Apple 视频系统的稳定读法是 ``Asset / Track → Sample / Time → Pixel Buffer → Codec / GPU → Layer / Writer``。先判断数据形态，再判断框架职责，能避免把播放、逐帧处理、硬件编解码和显示合成混成同一层。