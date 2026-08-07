第020章：光栅化算法
===================

核心知识点
----------

光栅化把连续几何转换为离散 fragment 与 sample
   输入是已经完成顶点处理、装配和裁剪的屏幕空间 primitive，以及 viewport、scissor、raster、depth/stencil、multisample、blend 和 attachment 状态。Coverage 只决定哪些像素或 sample 被几何覆盖，最终颜色还取决于 shader、深度模板、混合和写入。

三角形覆盖由边函数与共享边规则稳定定义
   Edge function 判断 sample 位于三条有向边的哪一侧；top-left rule 让两个相邻三角形的共享边只归属于其中一边，避免重复覆盖或裂缝。Subpixel precision、viewport 与 jitter 会影响边界 sample 的最终归属。

Depth test 与 depth write 是两个独立状态
   Depth test 决定当前 fragment/sample 是否通过可见性比较，depth write 决定通过后是否更新 depth buffer。不透明物体通常两者都开；透明物体常测试深度但关闭写入，再配合从远到近排序和 blending。

深度正确性依赖完整状态链
   Projection 的 z 约定、depth clear value、compare op、depth format、near/far、reverse-Z 与 depth write 必须互相匹配。Z-fighting 主要来自深度分辨率不足或几何过近，不能靠随意更改 compare op 从根本解决。

Early-Z 用已有深度减少昂贵片元工作
   前景不透明物体先稳定写深度后，后方 fragment 可在 shader 之前被拒绝。Shader 自定义 depth、discard、alpha test、透明混合等会限制提前深度测试的机会，因此 overdraw 高并不意味着 early-Z 一定生效。

MSAA 主要提高几何 coverage 的空间采样
   一个像素包含多个 sample 位置，coverage mask 记录三角形覆盖了哪些 sample。Resolve 再把多 sample 结果合成单像素图像。MSAA 对几何边缘有效，对纹理、normal map、高光等 shader 内部高频 aliasing 需要其它过滤策略。

Alpha-to-coverage 把 alpha 映射成 sample coverage
   植被、栅栏和头发卡片可借助 alpha-to-coverage 在 MSAA 下得到更稳定边缘；代价是透明级别受 sample 数量限制，并且会改变 coverage、depth 与 resolve 行为。

Stencil 用离散标记控制后续写入资格
   Stencil 不表示距离，而是保存小整数状态，可用于 portal、mask、outline、shadow volume 和 UI 裁剪。Depth/stencil、coverage、blend 与 resolve 处于不同层级，排查时必须分开。

Vulkan 与 DX12 把光栅状态显式化
   Viewport/scissor 定义绘制区域，rasterizer 定义 fill/cull/depth bias，depth-stencil 定义可见性，multisample 定义 sample 行为，blend 定义颜色合并，attachment format 与 sample count 定义真实存储。任何状态不匹配都可能让 draw 无输出或产生错误。

Raster 性能主要受 overdraw、片元复杂度与输出带宽影响
   Depth pre-pass 用额外几何工作换取更少重 fragment shader 执行；透明 blend、HDR、MRT、MSAA 和高分辨率会放大 color/depth 读写带宽。优化必须先区分 shader-bound、ROP/bandwidth-bound、overdraw-bound 或 geometry-bound。

关键路径
--------

三角形生成最终像素：

::

   clip primitive
   → perspective divide
   → viewport transform
   → triangle setup
   → edge function / sample coverage
   → perspective-correct attribute interpolation
   → depth/stencil test
   → fragment shader
   → coverage/write mask
   → blend/output merge
   → color/depth attachment
   → MSAA resolve（如启用）

深度错误排查：

::

   确认 projection 与 API depth range
   → 检查 depth format 与 clear value
   → 检查 compare op
   → 检查 depth test / depth write
   → 检查 reverse-Z 配套状态
   → 检查透明 pass 排序与写深度策略
   → 检查共面几何、depth bias 与 near/far

片元性能定位：

::

   记录 fragment invocation、overdraw 与 GPU 时间
   → 确认前景不透明深度是否先写入
   → 检查 early-Z 是否被 depth 输出、discard 或 alpha test 限制
   → 对比是否需要 depth pre-pass
   → 检查 blend、MRT、HDR、MSAA 与 resolve 带宽
   → 最后按瓶颈减少 shader、透明层数、sample 或 attachment 成本

概念辨析
--------

* **Coverage 与 shading**：coverage 决定某 sample 是否属于 primitive；shading 决定这个候选贡献产生什么颜色或其它输出。
* **Depth test 与 depth write**：test 决定是否通过；write 决定是否更新 depth buffer，两者可以独立开关。
* **Early-Z 与 depth pre-pass**：early-Z 是硬件提前执行深度拒绝；depth pre-pass 是应用主动先画一遍深度，为后续 pass 创造更有效的早期拒绝条件。
* **MSAA 与 SSAA**：MSAA 主要增加几何 coverage sample；SSAA 提高整个渲染分辨率和 shader 采样密度，成本更高但覆盖范围更广。
* **Alpha blend 与 alpha-to-coverage**：blend 读取已有颜色并做颜色合成；alpha-to-coverage 用 alpha 修改 sample mask，属于 coverage 路径。
* **Stencil 与 depth**：stencil 保存离散标签，depth 保存远近值；二者常共享 attachment，但语义完全不同。
* **Overdraw 与 fragment cost**：overdraw 表示同一区域被重复覆盖；真正成本还取决于 early-Z、shader 复杂度、blend 和 attachment 带宽。
* **Raster state 与 shader state**：光栅化、深度、sample、blend 多由固定管线状态定义；shader 只控制其中可编程计算，不能单独解释最终结果。

本章结论
--------

光栅化问题应沿“覆盖—深度/模板—shader—混合—写回”顺序拆解。边函数和 sample rule 决定几何覆盖，depth/stencil 决定可见性，MSAA 决定几何边缘采样，blend 与 attachment 决定最终写回成本；性能上只有结合 overdraw、early-Z、fragment invocation 和 render-target 带宽，才能判断应优化深度顺序、shader、透明路径、MSAA 还是输出格式。