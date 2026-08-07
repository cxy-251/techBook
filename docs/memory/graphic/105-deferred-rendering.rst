第105章：Deferred Rendering
==========================

核心知识点
----------

Deferred Rendering 把“可见表面解析”和“光照计算”拆开
   G-buffer pass 先写 normal、albedo、roughness、metallic、depth、velocity 等表面数据；lighting pass 再在屏幕空间读取这些属性和 light/shadow 数据，计算最终 HDR lighting。光照不再和每个物体的材质 draw 强绑定。

Deferred 的主要收益是大量动态光的可扩展性
   多个局部灯只在自身屏幕影响区域内执行 lighting，避免每个 mesh material shader 重复遍历同一批灯。夜景城市、室内大量小灯、复杂屏幕空间效果是典型场景。

G-buffer 是 Pass 间接口，不只是几张纹理
   每个 attachment 都必须定义 format、字段、色彩空间、normal 空间、编码方式、清屏值、producer、consumer 和 debug 解释。Lighting、SSAO、SSR、decal、TAA 都依赖这一 contract。

G-buffer Layout 首先由消费方反推
   Lighting 需要 albedo/normal/material/depth；SSAO 需要 depth/normal；SSR 需要 depth/normal/roughness/scene color；TAA 需要 velocity。没有实际消费者的字段不应仅为“以后可能用”长期占据带宽。

Normal 空间必须全管线一致
   World-space 与 view-space 都可行，但写入、lighting、SSR、SSAO 和 debug view 必须统一。空间混用会表现为相机旋转时光照或反射方向漂移。

精度与编码直接决定带宽和质量
   Albedo 通常可用 8-bit 格式；normal 可使用 octahedral encoding 压到两个通道；motion vector 常需要更高精度；HDR accumulation 使用 float 格式。每提升一档格式都要付出读写带宽和显存成本。

Material ID/Flags 是 Shading Model 的压缩入口
   Clear coat、subsurface、cloth、anisotropy 等模型可通过 material id 或 flags 在 lighting pass 分支；当类型和参数超过 G-buffer 容量时，应考虑材质表索引、额外 attachment 或 forward/special pass，而不是无限扩张 G-buffer。

Depth 是 Deferred 多个系统的共同基础
   Lighting 使用 inverse projection 重建位置；SSAO/SSR 读取深度；light volume 和 stencil 也依赖 depth。Reversed-Z、near/far、jitter 与 clip-space convention 必须在所有消费者中一致。

Decal 是对 G-buffer Contract 的局部修改
   Deferred decal 可修改 albedo、normal、roughness 等字段，但必须遵守原始编码和 blend 规则。Decal 后的 attachment 仍要保持 lighting、SSR、debug view 可正确解释。

Transparent 通常需要 Forward Fallback
   单层 G-buffer 只描述最前方不透明表面，无法自然保存多层透明与排序。因此玻璃、粒子、毛发等通常在 deferred lighting 后进入 forward transparent pass。

Deferred 不会消除 Shadow 成本
   Shadow caster 仍需生成 shadow map，lighting pass 仍需采样 shadow。大量小灯是否启用动态阴影仍必须严格预算。

Lighting 应配合 Tiled/Clustered Culling
   仅把 80 个光源全部循环到每个像素并不能获得 Deferred 的全部收益。光源应通过 tile/cluster/light volume 限制到对应像素区域，成本接近实际 light coverage。

Debug View 是 Deferred 的核心工程优势
   Albedo、normal、roughness、material id、velocity、linear depth、light volume、SSAO、SSR 等都应能独立显示。最终画面异常时，先确定哪一个中间字段首次失真。

Deferred 的主要成本是带宽
   多 attachment 写入、lighting 读取、HDR 输出、SSR/SSAO 再读会造成高流量。1080p 下每像素 20 字节的 G-buffer，单次完整写入理想数据量已超过 40 MB；高分辨率、MSAA 和多次 pass 会快速放大。

移动端/Tile GPU 对 G-buffer 更敏感
   Tile memory 能缓解部分外部带宽，但 attachment 数量、store/load、MSAA 和跨 pass 读取仍有平台限制。Deferred 是否合适必须由 platform profile 与实测决定。

关键路径
--------

Deferred Frame：

::

   visibility
   → optional depth prepass
   → G-buffer pass
   → decals
   → SSAO / screen-space preparation
   → light culling
   → deferred lighting
   → HDR scene color
   → SSR / reflections
   → forward transparent fallback
   → post process
   → present

G-buffer Contract：

::

   material/geometry attributes
   → attachment encoding
   → color/depth write
   → decal modification
   → lighting / SSAO / SSR / TAA consumers
   → debug views

带宽排查：

::

   attachment formats × resolution
   → G-buffer write bandwidth
   → lighting read bandwidth
   → light coverage / shadow sampling
   → HDR accumulation write
   → SSR/SSAO extra reads
   → transparent overdraw
   → GPU memory counters / pass timings

概念辨析
--------

* **G-buffer 与 Scene Color**：G-buffer 保存可见表面属性，scene color 保存经过光照或合成后的颜色。
* **Geometry Pass 与 Lighting Pass**：前者决定当前像素是什么表面，后者决定该表面在当前光照下是什么颜色。
* **Deferred 与 Tiled/Clustered Lighting**：Deferred 描述几何/光照拆分，tile/cluster 描述如何限制每个屏幕区域的灯光集合。
* **Depth Value 与 Reconstructed Position**：G-buffer 常只保存 depth，lighting 根据相机矩阵重建位置；二者不是同一对象。
* **Deferred Material ID 与 Shader Variant**：ID 让 lighting 在屏幕空间选择 shading model，variant 是几何 pass 或 special pass 的编译状态组合。
* **Deferred 与 Transparent Rendering**：Deferred 主要服务不透明可见表面，透明通常仍走 forward/special path。

本章结论
--------

Deferred Rendering 应按“G-buffer Contract—Depth—Light Culling—Lighting—Transparent Fallback—Bandwidth”理解。画面错误先检查具体 attachment 和编码，灯光慢先看屏幕覆盖与 light list，整体 GPU 慢则优先核算 G-buffer/HDR/SSR 的读写带宽。Deferred 的价值来自多灯光和屏幕空间数据复用；它的上限由 attachment contract、透明路径和显存带宽共同决定。