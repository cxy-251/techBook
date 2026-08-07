第115章：内存带宽优化
====================

核心知识点
----------

带宽瓶颈首先表现为“像素/数据量增长时帧时间同步增长”
   4K、Deferred、多层后处理、SSR/TAA、粒子和 compute-driven 都会放大读写量。降低分辨率或减少 full-screen pass 后显著提速，是带宽受限的重要信号。

带宽成本来自多条路径
   Texture fetch、structured/storage buffer、render target、depth/stencil、MSAA resolve、copy、upload/readback 都消耗内存流量。优化前必须定位是哪类资源和哪个 pass 在产生峰值。

先做每 Pass 的字节级估算
   可用 ``像素数 × 每像素读写字节 × 采样次数`` 估算下界，再用 profiler 的 memory throughput、L2 traffic、color/depth bandwidth 等 counter 验证真实成本。

Data Locality 决定 Cache 与事务效率
   相邻线程访问相邻地址更容易 coalescing 和 cache hit；随机间接索引会扩大 memory transaction 和 stall。GPU 访存优化的核心是让执行粒度与数据布局匹配。

AoS 与 SoA 要按实际读取字段选择
   一个 pass 只读取 position/velocity 时，SoA 可减少无效字段进入 cache；需要完整对象参数时，紧凑 AoS 可能更合适。没有一种布局对所有 pass 都最优。

Texture Mip 是带宽控制机制
   远处物体采样过高 mip 会同时增加 aliasing 与带宽。合理 mip selection、anisotropy 档位和 streaming residency 应与屏幕投影尺寸绑定。

Format Width 是最直接的带宽杠杆
   ``RGBA16F``、``RGBA8``、``R8`` 的字节数差异会在全屏 pass 中被放大。G-buffer、history、mask、velocity、HDR target 都应按实际精度需求选择最窄格式。

G-buffer 应按消费方反推字段
   Albedo、normal、material、velocity、depth 只保留 Lighting/SSR/SSAO/TAA 真正需要的数据。Normal 可压缩编码，roughness/metallic/AO 可通道打包，减少后续每个 pass 的读取量。

Source Texture 压缩与 Render Target 压缩不是同一件事
   BC/ASTC/ETC 等是资产侧可采样压缩；render target/depth 常依赖硬件内部颜色/深度/tile 压缩。不能把离线块压缩规则直接套到可写 attachment。

Streaming 的目标是控制 Residency 与 Upload 峰值
   大纹理、virtual texture page、mesh LOD 应按可见性和优先级渐进驻留。过晚会降画质，过早会占显存并产生 upload spike。运行时需记录 resident mip/page 与每帧 upload bytes。

Pass 合并可以减少中间 Read/Write
   Tone mapping、color grading、vignette 等有时可合并，减少一次 full-screen target 写回和再次读取。合并后若 register pressure、分支或 shader 复杂度明显上升，则需要用实测判断得失。

Shared/Tile Memory 只有在有复用时才有价值
   邻域滤波、tile reduction、局部 lighting list 可用片上缓存减少 global traffic；只读取一次的数据先搬入 shared memory通常没有收益。

带宽优化不能只看吞吐百分比
   高 memory throughput 可能是有效工作，也可能是浪费。必须结合 cache hit、stall、资源格式、访问模式和 pass GPU time 判断“哪些字节是不必要的”。

压缩和收窄格式必须做画质回归
   Normal 精度、HDR range、motion vector、texture artifact 都可能因格式变化产生视觉问题。性能收益和视觉误差必须一起进入验收。

关键路径
--------

带宽定位：

::

   frame time scales with resolution
   → find hot pass
   → enumerate input/output resources
   → estimate bytes / pixel or element
   → inspect cache/coalescing/counters
   → identify unnecessary traffic
   → change format/layout/sampling/lifetime
   → retest image + GPU time

资源优化：

::

   source texture → compression + mip chain + streaming
   render target → narrower format + fewer passes + hardware compression
   buffer → compact layout + contiguous access
   history → correct resolution/version/lifetime

流式路径：

::

   screen-space demand
   → target mip/page/LOD
   → streaming request
   → upload budget
   → resident version published
   → shader samples resident resource
   → evict low-priority data under pressure

概念辨析
--------

* **Bandwidth 与 Latency**：bandwidth 是单位时间搬运量，latency 是单次访问等待；GPU 可用并发隐藏部分 latency，但无法无限突破带宽上限。
* **Cache Hit 与 Coalescing**：cache hit 关注数据是否已在近端缓存，coalescing 关注同一 wave 的请求是否能合并成较少事务。
* **AoS 与 SoA**：一个按对象聚合字段，一个按属性聚合字段，选择取决于 pass 的实际读取模式。
* **Source Texture Compression 与 Render Target Compression**：前者主要来自资产格式，后者通常由 GPU 内部压缩机制实现。
* **Streaming 与 Compression**：streaming 控制何时/多少资源驻留，compression 控制每单位资源占多少字节。
* **Pass Merge 与 Shader Simplification**：合并减少中间带宽，简化减少计算；两者解决不同成本。

本章结论
--------

内存带宽优化应按“Hot Pass—Resource Bytes—Access Pattern—Format/Layout—Compression/Streaming—Counter—Image Quality”理解。先找出真正搬运大量数据的 pass，再减少无效字节、改善局部性和生命周期。带宽优化的本质不是让 GPU 更快地搬同样的数据，而是让一帧必须搬的数据变少。