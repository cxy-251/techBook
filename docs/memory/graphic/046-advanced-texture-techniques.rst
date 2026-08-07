第046章：高级纹理技术
====================

核心知识点
----------

高级纹理技术首先是坐标来源问题
   普通 surface texture 通常使用 UV；planar/triplanar 使用模型或世界位置；decal/projective mapping 使用投影空间；Cubemap 使用方向向量；3D Texture 使用三维位置。坐标来源不同，错误症状也不同，排查时必须先回答“当前采样坐标从哪里来”。

UV transform 仍是最轻量的纹理控制方式
   Scale、offset、rotation 可控制平铺、滚动与局部相位。强缩放和非线性扭曲会改变屏幕空间导数与 LOD，必要时要显式提供 gradient 或 LOD，避免远处闪烁和异常模糊。

Planar 与 Triplanar 用生成坐标减少 UV 依赖
   Planar 适合单一朝向表面，侧面容易拉伸；triplanar 从三个轴向分别采样，再按法线方向混合，可用于岩石、地形、混凝土和程序化几何。它通常以三倍左右的采样成本换取更稳定的坐标覆盖。

Triplanar normal 必须先统一到同一空间
   三个投影面的 tangent-space normal 不能直接相加。每一路应根据投影轴转换到统一 world/object space，再按 blend weight 混合并归一化，否则墙角和坡面会出现高光方向突变。

Decal 是局部投影材质修改，不只是“贴一张颜色图”
   Fragment 世界位置先变换到 decal local space，盒内坐标映射为 decal UV，再由 mask 控制写入范围。Decal 可以只改 base color，也可以同时修改 normal、roughness、metallic 等 G-buffer/材质参数；必须定义通道、顺序和混合规则。

Cubemap 是方向纹理
   Skybox 使用 view direction，环境反射使用 reflection direction，IBL 还会根据 roughness 读取预过滤 cubemap 的不同 mip。方向空间、面顺序、左右手系与反射向量只要有一处错，环境就会旋转、翻转或出现接缝。

Cubemap seam 既是资源问题，也是预过滤问题
   六个面需保持一致方向与曝光，并尽量使用 seamless filtering。Prefiltered environment 的卷积需要跨面连续；逐面独立模糊会让粗糙反射出现十字形边界。Local reflection probe 还需要 box/parallax correction 处理近场视差。

3D Texture 用可过滤三维资源表达空间函数
   Density、noise、体积颜色或 LUT 都可以存入 3D Texture。体积雾/云通常把 world position 转到 volume local space 后采样，若错误使用 view-space 坐标，纹理会随相机平移产生滑动。

Ray marching 的成本是“步数 × 体积采样”
   每步读取 density，并累积 scattering/transmittance。步长过大产生切片感，过小增加采样和带宽；远距离还要处理 3D mip/LOD。Temporal filtering 可以用较少步数重建稳定体积，但必须做遮挡与 history rejection。

纹理采样优化要先判断瓶颈类型
   材质可能同时采 base color、normal、ORM、decal、cubemap、LUT 和 volume。优化入口包括通道打包、texture array、atlas、bindless、sampler reuse、roughness/coverage 条件采样、LOD 与分辨率控制。减少绑定和减少采样不是同一问题。

PBR 纹理应该在参数层汇合
   Base color、normal、roughness、metallic、AO 先被正确解码，再交给统一 BRDF/IBL。贴花和材质层也优先混合这些参数，而不是直接混合最终 lit color，才能让 direct light、IBL、阴影与 tone mapping 看到一致材质状态。

Roughness、metallic、AO 的作用边界不同
   Roughness 同时影响直射高光和 prefiltered environment mip；metallic 改变 diffuse/specular 能量分配；AO 通常只调制间接环境项，不应粗暴乘到所有直接光。材质出现“积水像镜子、混凝土像金属、直射面过脏”时应逐通道检查。

关键路径
--------

高级表面映射：

::

   surface position / UV / normal
   → 选择 UV / planar / triplanar / projective 坐标
   → transform / projection
   → sampler + mip / LOD
   → texture sample
   → 统一 normal / material parameter space
   → 参数层混合
   → BRDF / IBL

Cubemap / probe：

::

   view direction / reflection direction
   → 统一 world/view space
   → 可选 local probe parallax correction
   → roughness → prefiltered mip
   → cubemap sample
   → environment specular / sky

体积纹理：

::

   camera ray + scene depth / volume bounds
   → world-space march position
   → worldToVolume
   → 3D texture UVW
   → density / noise sample
   → scattering + transmittance accumulation
   → temporal reprojection / filtering
   → composite

复杂纹理故障排查：

::

   先确认坐标来源与空间
   → 显示坐标 / blend weight / density
   → 检查 texture / sampler / mip
   → 检查 normal 与 PBR 通道
   → 固定 roughness / cubemap LOD
   → 关闭 temporal/history
   → 最后恢复 decal / probe / volume / lighting 组合

概念辨析
--------

* **UV mapping 与 triplanar**：UV 是显式表面参数化；triplanar 根据三维位置和法线运行时生成采样坐标。
* **Projective mapping 与 decal**：projective mapping 是坐标生成方法；decal 是利用局部投影范围修改材质通道的一类工程应用。
* **Cubemap 与 2D texture**：Cubemap 通过三维方向定位六个面，不使用普通二维 UV。
* **Skybox 与 IBL**：skybox 是背景显示；IBL 把环境纹理作为光照输入，并通常需要 diffuse/specular 预处理。
* **Distant probe 与 local probe**：前者近似环境在无限远；后者表示局部空间，需要视差修正和体积权重。
* **3D Texture 与 ray marching**：3D Texture 是空间数据资源；ray marching 是沿光线反复读取并积分该资源的算法。
* **Atlas、array 与 bindless**：atlas 合并到一张二维图并需要 UV sub-rect；array 保持同尺寸层；bindless 允许 shader 通过索引访问大量独立纹理，三者解决的绑定/布局问题不同。
* **参数混合与最终颜色混合**：参数混合先形成一致材质再进入 BRDF；最终颜色混合无法正确重建 roughness、metallic、normal 等光照响应。

本章结论
--------

高级纹理技术可统一成“坐标生成—资源类型—采样与 LOD—材质语义—最终合成”。Triplanar 先解决坐标稳定再处理法线空间，Cubemap 先保证方向与预过滤连续，3D Texture 先保证 world-space 密度再调步数与 temporal，PBR 层则先验证 base color、normal、roughness、metallic、AO。复杂效果一旦按这条链拆开，就能同时获得可定位的画质问题和明确的采样性能预算。