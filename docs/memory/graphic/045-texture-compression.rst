第045章：纹理压缩
================

核心知识点
----------

纹理压缩是一份显存、带宽、平台支持与画质之间的契约
   压缩格式决定每个 block 如何存储、硬件如何解码、完整 mip chain 占多少显存，以及采样时需要搬运多少字节。格式选择不能脱离纹理语义、目标平台和可接受误差。

块压缩的主要收益来自容量与带宽
   未压缩 RGBA8 为 32 bpp；BC1 约 4 bpp，BC3/BC5/BC6H/BC7 约 8 bpp。压缩减少 resident texture memory、streaming 字节数、upload 数据量和 texture cache 外部带宽，对移动 GPU、开放世界与大量材质尤其重要。

压缩误差会沿后续渲染链被放大
   Base color 的色块可能在 lighting 后不明显；normal 的方向误差会表现为高光抖动；roughness 的通道污染会改变高光宽度；HDR 环境图的误差会在曝光和 tone mapping 后被放大；UI 则会直接暴露透明边缘和块边界。

BC 系列应按数据语义选择
   BC1 适合普通无连续 alpha 的 LDR color；BC3 适合传统 RGBA；BC4 适合单通道数据；BC5 适合 normal XY；BC6H 适合 HDR；BC7 适合高质量 LDR RGBA。格式不是“越新越好”，而是通道结构与误差模型是否匹配。

ASTC 用 block footprint 连续调节码率
   ASTC 仍使用固定 128-bit block，但 4x4、5x5、6x6、8x8 等 footprint 对应不同 bpp。Block 越小质量越高、容量越大；越大越省内存但细节误差更明显，适合移动和跨平台 profile 做分级。

Normal map 应优先保护方向精度
   常见做法是压缩 X/Y 两通道，shader 中重建 Z 并重新归一化。Normal 必须按 linear 数据读取，通道 swizzle、绿色通道方向和压缩 profile 要与 shader 一致。静态截图不足以判断质量，移动光源下的高光稳定性更有价值。

Packed mask 的风险是通道之间统计不相关
   Roughness、metallic、AO 放在同一 RGB 可以减少采样和 descriptor，但共享颜色端点的格式可能让一个通道的边界污染另一个通道。应逐通道 debug，再决定 BC4 拆分、BC7 或 ASTC 小 footprint。

UI 与 HDR 往往需要单独 profile
   UI 直接映射屏幕，对文字、alpha 与边缘极敏感，常使用 RGBA8、高质量 BC7 或 ASTC 4x4；HDR skybox/IBL 关注高亮能量和渐变，常使用 BC6H 或 ASTC HDR，并需在多档 exposure 下检查。

压缩应发生在 asset build 阶段
   源图保留高质量无损数据；构建系统根据 texture semantic 与 platform profile 生成 DDS/KTX2 等运行时产物。运行时只负责选择变体、加载、上传、streaming 与 residency，不应在主帧中执行昂贵压缩编码。

Streaming 与压缩格式必须共享同一布局合同
   加载器要按 block width、block height、bytes per block 计算 row pitch、slice pitch、mip offset 和 array/cubemap face 布局。块对齐错误会造成纹理错行、mip 损坏或 GPU 上传失败。

压缩是否值得必须用 profiler 验证
   容量收益看 resident memory 与 streaming backlog；带宽收益看 texture bandwidth、cache miss、sampler stall 和 pass time；CPU/IO 收益看加载队列、转码与上传字节。若主瓶颈是 ALU 或 overdraw，压缩仍有价值，但未必显著改变帧时间。

关键路径
--------

Asset 管线：

::

   source texture
   → semantic classification
   → color-space metadata
   → platform capability/profile
   → choose BC / ASTC / ETC / uncompressed format
   → offline encode all mip levels
   → package DDS / KTX2 / platform container
   → automated size / format / screenshot validation
   → runtime load
   → upload / residency / streaming
   → hardware sample + decode

格式选择：

::

   先看目标平台支持
   → 再看纹理语义
   → 计算完整 mip chain 容量
   → 选择候选码率
   → 用语义 debug view 比较画质
   → 用 profiler 验证带宽 / residency 收益
   → 固化到 platform profile

画质排查：

::

   同屏比较 source 与 compressed base level
   → 比较各 mip
   → base color 看 albedo
   → normal 看 normal + moving highlight
   → mask 逐通道看 roughness / metallic / AO
   → HDR 用多 exposure
   → UI 用 1:1 截图与 alpha coverage

概念辨析
--------

* **文件压缩与 GPU 纹理压缩**：PNG/JPEG 主要服务磁盘/传输，通常解码成普通像素；BC/ASTC 等格式可直接以压缩 block 驻留并由 GPU 采样硬件解码。
* **BC1 与 BC7**：二者都是 LDR block compression，BC1 码率更低，BC7 表达能力和质量更高。
* **BC5 与普通 RGB normal**：BC5 按两个独立通道保存 normal XY，更符合方向数据需求。
* **ASTC block size 与纹理分辨率**：block footprint 改的是压缩码率，不是原始纹理宽高。
* **通道打包与纹理压缩**：打包减少纹理/采样数量；压缩减少每张纹理的存储与带宽，两者可以同时使用。
* **Compression artifact 与 filtering artifact**：前者来自 block 重建误差，后者来自 LOD/采样 footprint。必须用压缩前后与固定 LOD 分离判断。
* **容量优化与帧时间优化**：显存减少并不保证 GPU pass 一定加速，最终收益取决于当前瓶颈是否在带宽、cache 或 streaming。

本章结论
--------

纹理压缩应遵循“平台能力—纹理语义—候选格式—容量计算—语义画质验证—性能验证”的顺序。Base color、normal、mask、UI、HDR 不应共享同一粗暴策略；格式选择必须让误差落在当前数据最能承受的位置。压缩真正的工程价值不是单纯把文件变小，而是让更多有效纹理以更低带宽稳定驻留并被 GPU 直接采样。