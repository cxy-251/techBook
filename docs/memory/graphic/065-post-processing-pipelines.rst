第065章：后处理管线
==================

核心知识点
----------

后处理本质上是一条图像信号处理链
   每个 pass 都应明确读取哪张纹理、写入哪张纹理、使用什么格式和分辨率、是否依赖 history，以及输出仍处于 HDR scene-linear 还是已经进入 display-referred 空间。

HDR Scene Color 是后处理主输入
   主渲染通常先写入 ``RGBA16F``、``R11G11B10F`` 等 HDR buffer，同时保留 depth、velocity、exposure 和历史资源。超过显示白的高光必须在 tone mapping 前保留，Bloom、景深和部分 temporal pass 才有正确输入。

Pass 顺序首先由颜色空间决定
   Bloom、exposure、很多镜头效果应读取 HDR/linear color；tone mapping 把 scene-referred 压到 display-referred；LUT、grain、vignette、UI 等更靠近输出侧。把效果放错阶段，即使 shader 数学正确也会得到错误结果。

Tone Mapping 与 Exposure 是不同控制层
   Exposure 改变进入曲线前的信号尺度；tone mapper 决定 toe、中间调和 shoulder 如何压缩。White point 控制高光趋近显示白的速度。错误曝光不应靠后处理 LUT 或 Bloom 强行补偿。

Color Grading LUT 必须匹配预期输入空间
   面向 display-linear 的 LUT 不能直接读取未压缩 HDR scene color。白平衡、颜色空间矩阵、曲线和 3D LUT 的输入输出合同需要显式记录，否则不同平台和 HDR/SDR 路径会发生色彩漂移。

Bloom 是 HDR 高亮的多尺度扩散
   典型路径是 threshold/prefilter、downsample pyramid、blur、upsample 和 composite。Bloom 中间纹理必须保留足够动态范围；提前 clamp 或使用低精度 UNORM 会让高光变成白块或白雾。

景深和 Motion Blur 都依赖几何辅助 buffer
   景深使用 depth 计算 CoC，再决定 near/far blur；motion blur 使用 velocity 生成采样方向。Depth、velocity、jitter 和动态分辨率必须对应同一帧和同一空间，否则最常见症状就是边缘漏光与错误拖影。

UI 通常在显示映射后合成
   普通 UI 资源以 SDR/font atlas/屏幕颜色为基础，若跟场景一起进入 tone mapper，亮度和文字边缘会失控。HDR UI 需要单独定义 reference white 与 display mapping，不能简单复用 SDR 规则。

Frame Graph 是可配置后处理的最佳抽象之一
   Pass descriptor 应声明 input/output、format、resolution scale、pipeline、temporal dependency、quality tier 和 debug view。系统据此分配临时资源、插入 barrier、做生命周期 aliasing，并让中间纹理可被观察。

临时资源生命周期直接影响显存
   多级 Bloom、DOF、TAA、motion blur 会创建大量中间 texture。生命周期不重叠的资源可以 alias/reuse，但必须确保上一消费者已经结束；错误 aliasing 或 barrier 会表现成偶发旧内容、随机闪烁或平台差异。

质量档位应改变资源规模，而不只是效果开关
   低档可降低 Bloom mip 数、DOF 半径、motion blur samples、temporal 质量；高档则增加分辨率和采样。有效 tier 需要能说明具体少了哪些 pass、纹理或 sample。

后处理常常受带宽而不是 ALU 限制
   全分辨率 HDR pass 每次都要读写大量像素。优化应先看分辨率、格式、读写次数和 pass count，再看 shader 算术。Tone mapping、LUT、vignette、grain 等简单全屏操作经常可以合并。

关键路径
--------

典型后处理：

::

   HDR scene color + depth + velocity + exposure
   → temporal resolve / upscale
   → Bloom prefilter / pyramid
   → DOF / motion blur
   → pre-tonemap HDR composite
   → tone mapping
   → color grading LUT
   → sharpen / grain / vignette
   → UI composite
   → output transfer / backbuffer

Frame Graph：

::

   pass declares reads / writes
   → choose format + resolution
   → allocate transient texture
   → insert state/layout barrier
   → execute graphics/compute pass
   → expose debug output
   → release/alias resource after last use

性能排查：

::

   GPU timestamps per pass
   → record resolution / format
   → count texture reads / writes / samples
   → disable one effect and compare
   → downscale or merge candidate passes
   → inspect barrier / async overlap
   → verify visual regressions

概念辨析
--------

* **Post Process 与简单滤镜**：真实后处理还包含 temporal history、depth/velocity 依赖、颜色空间转换和资源同步，不只是叠一层颜色效果。
* **HDR Scene Color 与 HDR Display**：内部浮点 HDR buffer 不等于最终 HDR 输出；显示路径还要匹配 gamut、transfer、swapchain color space 和系统状态。
* **Exposure 与 Tone Mapping**：前者缩放场景信号，后者压缩到显示范围。
* **Tone Mapping 与 Color Grading**：tone mapping 解决动态范围，grading 主要调整最终 look；两者输入空间不同。
* **Bloom Blur 与普通 Blur**：Bloom 先选择 HDR 高亮再做多尺度扩散，普通 blur 不包含高亮选择语义。
* **Depth of Field 与 Motion Blur**：二者都是邻域重建，但一个由 focus/depth 驱动，一个由 velocity 驱动。
* **Pass Count 与视觉复杂度**：效果很多不一定需要很多独立全屏 pass，简单操作可以在同一 shader 合并。
* **Barrier 与 CPU Stall**：GPU 资源 barrier 建立访问顺序，不等于让 CPU 等待 GPU；应尽量保持后处理依赖在 GPU 内闭环。

本章结论
--------

后处理应按“HDR 输入—时域/镜头效果—tone mapping—grading—UI—显示输出”理解，并用 frame graph 显式管理每个 pass 的资源、格式、分辨率、历史和同步。画质问题先沿 pass 输出寻找最早错误资源，性能问题先按像素量、格式、读写次数和 pass count 计算带宽。只有执行顺序、颜色空间、临时资源生命周期和最终 backbuffer 合同同时清楚，后处理管线才能在不同质量等级与平台上稳定扩展。