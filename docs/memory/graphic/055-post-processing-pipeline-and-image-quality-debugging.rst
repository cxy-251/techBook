第055章：后处理管线与图像质量调试
==============================

核心知识点
----------

后处理是 frame graph 中一组显式资源变换
   Blur、bloom、SSAO、TAA、tone mapping、sharpening 都不是孤立效果，而是“读哪些纹理、写哪个目标、使用什么格式、下一步谁消费”的 frame graph 节点。画质问题必须能落到具体 pass 与资源边界。

每个后处理资源都要记录三类语义
   内容语义说明保存的是 HDR color、depth、normal、motion、history 还是 display color；格式语义说明是 FP16、UNORM、motion-vector format 等；同步语义说明上一 pass 写完后何时能被下一 pass 读取。三者缺一都可能制造伪影。

Pass 顺序会改变效果含义
   Bloom 依赖 HDR 高光，通常位于 tone mapping 前；TAA 需要稳定 current/history 输入，sharpening 常放在 TAA/upscale 后；film grain 和 UI 通常靠近最终输出。把同一 shader 放错阶段，公式不变也会产生完全不同结果。

Bloom 是高亮提取与多尺度扩散
   Prefilter 决定哪些 HDR 值进入 bloom，downsample/blur/upsample 决定光晕尺度，composite 决定能量。中间纹理若精度不足或高光提前 clamp，bloom 会断层、偏白或变成整屏雾。

SSAO 依赖 depth 与 normal 的屏幕空间近似
   原始 AO mask 通常含噪，需要 spatial/temporal filter。Depth discontinuity、normal 错误、半分辨率 upsample 和过强 composite 会形成 halo、暗边和远景闪烁。调试应先看独立 AO mask，再看 blur，最后看 composite。

Temporal pass 的核心是 history reprojection
   Motion vector 把当前像素映射回上一帧位置，history validation 再根据 depth、normal、颜色邻域、velocity、reactive mask 判断是否复用。Camera cut、动态分辨率、jitter 约定变化后 history 必须 reset 或重建。

Motion vector 的空间和尺度必须写进接口合同
   Pixel、UV、NDC 等表示都可以使用，但 producer 与 consumer 必须一致。Jitter 是否包含在 velocity 中也要固定；重复补偿 jitter 会造成反向抖动，遗漏则会造成重投影漂移。

透明物是 temporal reconstruction 的薄弱区域
   粒子、玻璃、火焰、毛发和屏幕空间反射经常没有稳定 depth 或 motion。需要 reactive/material mask、低 history 权重或单独路径；否则最常见结果就是拖影和旧颜色残留。

中间格式决定是否保留算法需要的数值范围
   HDR scene/bloom 常需浮点格式，motion 需要有符号高精度，mask 可用低位深 UNORM。把 HDR bloom 放进 ``R8_UNORM``、把 motion 压得过粗、把 history 存成错误颜色空间，都会让后续 pass 无法补救。

Resource hazard 会表现成随机画质错误
   Render-target write 后 shader read 需要正确 barrier/layout transition；UAV 写后读需要执行顺序；ping-pong filter 应避免同一资源无定义读写；temporary resource aliasing 需要生命周期不重叠。错误同步常表现为偶发闪烁、旧帧内容或平台相关污染。

Async compute 让同步边界更重要
   Bloom、histogram、TAA 等可能放到 compute queue。Graphics 消费结果前必须等待生产完成，否则画面会随机缺失或读取上一版本。Queue timeline、semaphore/fence 与 frame graph dependency 都是图像正确性的一部分。

画质调试必须寻找“最早出错的 pass”
   最终图像包含多次采样和转换，直接调最终参数会掩盖根因。应固定复现，保存每个 pass 输入输出，逐个关闭效果，检查 format/barrier/history，最后只修改一个变量验证。

关键路径
--------

典型后处理链：

::

   opaque / transparent lighting
   → SceneColorHDR + depth + normal + motion
   → SSAO + denoise
   → bloom prefilter / pyramid
   → HDR composite
   → TAA / temporal upscale + history
   → tone mapping
   → sharpening / grain / vignette
   → UI composite
   → display encode
   → swapchain

Temporal pass：

::

   current color
   + motion vector
   + depth / normal
   + previous history
   + reactive / validity masks
   → reproject
   → validate / clamp history
   → accumulate
   → write resolved color
   → write next history

Resource 正确性：

::

   pass A writes texture
   → state / layout transition
   → barrier / queue dependency
   → pass B reads texture
   → 若继续写则使用 ping-pong / UAV ordering
   → 生命周期结束后才允许 alias/reuse

图像质量调试：

::

   固定相机 / 时间 / jitter / 分辨率
   → 关闭全部 post 得到 raw scene
   → 按 pass 逐个恢复
   → 保存每级输入 / 输出
   → 查看 HDR / depth / normal / motion / history / mask
   → 检查 format / color space / barrier
   → 只改一个参数
   → 连续帧回归

概念辨析
--------

* **Post effect 与 frame graph node**：效果名称描述视觉目标；frame graph node 描述真实资源读写和同步关系。调试必须以后者为准。
* **HDR pass 与 LDR pass**：前者保留场景能量，适合 bloom/exposure 等；后者已面向显示，适合最终锐化、UI 与呈现处理。
* **Current frame 与 history**：current 是本帧直接观测，history 是上一帧推断证据。后者必须经过 validation，不能无条件相信。
* **Motion vector 与 optical flow**：motion vector 通常来自已知几何/相机变换；optical flow 从图像估计运动。实时 TAA 首选前者。
* **Format bug 与 shader bug**：shader 数学正确但中间纹理范围不足，同样会稳定地产生错误结果。
* **Barrier 与等待 CPU**：GPU barrier 只建立资源访问顺序，不等于 CPU readback；后处理通常应保持依赖在 GPU 内解决。
* **Random artifact 与 random shader noise**：偶发旧内容、跨平台差异或仅 async 开启后出现的问题，要优先查 hazard 和资源生命周期。

本章结论
--------

后处理应按“frame graph 依赖—资源语义—格式精度—历史状态—同步边界”理解。画面拖影先查 motion/history，bloom 异常先查 HDR 输入和 pass 顺序，随机闪烁先查 barrier/aliasing，多队列问题查 queue dependency。最有效的调试方法不是继续叠加参数，而是固定一帧和连续历史，找到第一个已经错误的中间资源；从那一层修正，后续画质问题往往会一起消失。