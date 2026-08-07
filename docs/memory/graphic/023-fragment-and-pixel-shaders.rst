第023章：Fragment 与 Pixel Shader
===============================

核心知识点
----------

Fragment Shader 处理的是光栅化产生的 fragment
   OpenGL、Vulkan、WebGPU 常称 Fragment Shader，Direct3D 常称 Pixel Shader；它们处于同一类管线位置。Invocation 由 primitive coverage 产生，输入包括插值 varying、内建屏幕信息、texture、sampler、material/light buffer，输出进入 color/depth attachment 或 MRT。

Fragment 是否执行取决于 shader 之外的固定功能条件
   Primitive 必须先通过裁剪、viewport、scissor、culling 和 coverage。Depth/stencil 可以在 shader 前后参与拒绝；如果目标采样点根本没有形成 fragment，修改 fragment shader 代码不会产生任何输出。

Early depth 能减少被遮挡 fragment 的昂贵计算
   前景不透明几何先写入稳定 depth 后，后方 fragment 有机会在 shader 前被拒绝。Shader 写自定义 depth、使用 discard/alpha test 或产生某些副作用时，提前深度测试空间会缩小，overdraw 中的 texture fetch 和光照成本会增加。

Helper invocation 服务导数与 mip 选择
   ``dFdx``、``dFdy`` 和隐式纹理 LOD 需要相邻 invocation 形成导数组，GPU 可为无真实覆盖的位置运行辅助 invocation。它们参与导数计算，不代表最终 framebuffer 写入；discard、边缘和动态分支附近的导数问题应考虑这一执行模型。

颜色计算必须保持颜色空间和几何空间一致
   Base color 通常按 sRGB 资源解码后进入 linear lighting；normal、roughness、metallic、AO 等数据纹理通常按线性数据使用。Normal map 需要正确 TBN，光照向量与法线必须处于同一空间，最终 HDR 颜色再由后续 tone mapping 映射到显示空间。

Texture fetch 成本会被屏幕覆盖面积放大
   采样次数、mip/filter、anisotropy、压缩格式、cache locality 与 overdraw 共同决定纹理成本。Normal map、shadow map、PBR 参数图即使单次采样不贵，在大面积、高 overdraw 的 fragment path 中也会成为主要带宽来源。

分支优化要看分支一致性而不是语法形式
   由材质或 draw uniform 控制的分支通常在同一 wave 内一致；像素级条件会造成执行路径分歧。Branchless math 适合小型连续条件，但若为了去分支而同时执行两条昂贵采样路径，成本可能更高。

Texture packing 是采样与资产管线的联合优化
   Roughness、metallic、AO、mask 可打包进 RGBA 通道，减少 descriptor 和采样次数；代价是所有通道共享纹理尺寸、压缩格式、mip 生成和生命周期。压缩块伪影与通道语义必须在资产阶段验证。

MRT 把 fragment 输出变成宽写入合同
   Deferred G-buffer 可同时写 albedo、normal、roughness、metallic、motion 等 attachment。每增加一个输出都增加格式转换、显存和带宽压力；shader output location/semantic、attachment 顺序、format、blend 和后续解码必须完全一致。

关键路径
--------

一个 fragment 进入 framebuffer：

::

   primitive coverage
   → viewport/scissor/cull/sample mask
   → 生成 fragment 与插值 varying
   → 可选 early depth/stencil
   → Fragment Shader
   → texture/material/light 读取
   → discard 或 depth 输出（如有）
   → late depth/stencil
   → blend / color write mask
   → 单 attachment 或 MRT 写入
   → 后续 lighting、tone mapping 或 resolve

材质颜色排查：

::

   先输出固定常量色确认 fragment 与 attachment
   → 输出 UV/debug gradient
   → 单独输出 base color
   → 检查 sRGB/linear 解释
   → 单独输出 normal/TBN
   → 单独输出 roughness/metallic/shadow term
   → 最后恢复 BRDF 与 HDR 输出

Fragment 性能定位：

::

   统计 fragment invocation 与 overdraw
   → 检查 early-z 是否有效
   → 统计 texture/sample 次数与 cache/bandwidth
   → 检查分支、寄存器和 ALU
   → 检查 MRT、HDR、MSAA、blend 写回
   → 按瓶颈减少输入集合、采样、分支或 attachment 宽度

概念辨析
--------

* **Fragment 与 pixel**：fragment 是几何对一个 sample/像素位置的候选贡献；pixel 是最终图像存储位置。多个 fragment 可以竞争同一个 pixel。
* **Fragment Shader 与 fragment operations**：shader 负责可编程颜色/数据计算；depth、stencil、blend、coverage 等固定功能继续决定结果是否和如何写入。
* **Early depth 与 late depth**：前者在 shader 主体前拒绝部分 fragment；后者在 shader 后完成测试。具体时机取决于 shader 行为、状态和硬件实现。
* **Discard 与透明混合**：discard 直接取消当前 fragment 的贡献；alpha blend 保留 fragment 并与已有颜色合成，成本和排序规则完全不同。
* **Texture sampling 与颜色计算**：采样只是读取数据；BRDF、光照和颜色空间转换决定这些数据如何参与最终颜色。
* **Uniform branch 与 divergent branch**：统一分支对同组 invocation 走同一路径；像素级变化分支更容易造成 SIMD/SIMT 发散。
* **Forward 与 deferred 输出**：forward 直接输出最终或近最终颜色；deferred 先写 G-buffer，再由后续 pass 重建材质与几何信息。
* **MRT 与多个 pass**：MRT 在一次 fragment invocation 中同时写多个 attachment；多个 pass 则会重新执行几何或 shader 路径，成本模型不同。

本章结论
--------

Fragment Shader 应沿“coverage—执行条件—采样与材质—depth/stencil—输出写回”理解。画面缺失先排查固定功能与 attachment，再进入 shader；性能问题先看 fragment 数和 overdraw，再判断 texture、ALU、分支还是 MRT/Blend 带宽。只有把 invocation 为什么产生、读了什么、算了什么、最终写到哪里解释清楚，像素阶段的正确性和性能才具有可操作的因果链。