Compression, Streaming, Incremental Delivery, and Progressive Response
======================================================================

核心知识点
----------

* Compression 改变传输字节形态，不改变资源语义；浏览器最终仍按原始 ``Content-Type`` 把解压后的内容交给 HTML/CSS/JS/media 等消费者。
* ``Accept-Encoding`` 表达客户端能力，``Content-Encoding`` 表达实际编码，缓存还需要正确区分 representation 变体。
* 文本类资源通常压缩收益高；已经压缩的图片、音视频等再次压缩收益有限。动态压缩还会引入 server/edge CPU 成本和浏览器解压成本。
* 静态 hashed asset 适合 build-time 预压缩和长期缓存；动态 HTML/JSON 要结合个性化、CPU 负载、cache policy 和响应大小判断。
* Streaming 把 response 从“完整对象”变成时间序列：headers 先提交，body 分段产生、转发、消费，server compute、network transfer 和 browser parse 可以部分重叠。
* 协议支持分块传输并不等于用户一定能看到渐进结果；proxy/CDN buffering、compression buffering、server flush 时机和 browser consumer 都可能重新把 stream 缓冲起来。
* Streaming 改变延迟分布而不减少总工作量；关键指标是 first useful byte、chunk gap、FCP/LCP 等，而不是只看 TTFB。
* 流式系统必须处理 backpressure、abort、timeout、partial failure 和已提交 headers 后无法再修改 status/header 的约束。

关键路径
--------

压缩路径：

``Browser Accept-Encoding → Server/CDN representation selection → Content-Encoding → Cache Variant → Transfer → Browser Decompress → Parser/Runtime``

流式响应：

``Request → Server starts response → headers committed → first useful chunk → proxy/CDN forward-or-buffer → browser receives chunks → incremental parse/render → final close``

流式 HTML：

``shell/critical hints → browser parser/resource discovery → slow data arrives later → incremental markup/result → progressive UI``

诊断闭环：

``response headers → encoded/decoded size → first byte/useful byte → buffering points → chunk timing → parser/render milestones → abort/error``

概念辨析
--------

* **Content-Type vs Content-Encoding**：前者说明内容是什么；后者说明传输时怎样编码。
* **压缩率 vs 总体性能**：更高压缩率可能增加构建、server、edge 或客户端 CPU；需要看总路径成本。
* **Streaming vs Chunked Protocol**：协议允许分块只是基础；应用还要逐步生成有意义内容，中间层也必须及时转发。
* **TTFB vs First Useful Byte**：早发一个无用空壳可以降低 TTFB，却不一定改善用户可见体验。
* **Streaming vs 减少工作量**：streaming 主要让生成、传输和消费重叠，总计算、总字节和解析工作仍然存在。
* **Buffering vs Backpressure**：buffering 是把数据积攒后再发送；backpressure 是消费者变慢时反向限制生产者，防止无界内存增长。
* **完整响应错误 vs 流式部分失败**：headers/部分 body 已发送后，服务端通常不能重新返回完整错误状态，只能终止 stream 或发送应用级错误片段。

本章结论
--------

资源交付优化要同时看字节数量和时间结构。Compression 用 CPU 换传输体积，Streaming 用增量生成与消费换更早的可见结果；两者都跨越 server、CDN、cache、browser 和 runtime boundary，必须用 headers、缓存变体、buffering、backpressure 和真实用户时间线共同验证。