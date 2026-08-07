第030章：次表面散射
===================

核心知识点
----------

SSS 描述光在介质内部传播后从邻近位置射出的现象
   普通 BRDF 假设入射点和出射点相同；BSSRDF 允许二者分离。皮肤、蜡、玉石和薄叶片的柔和阴影、暖色渗透与薄处透光，都来自这类跨位置能量传输。

SSS 与表面镜面反射应分层处理
   表层 BRDF 负责 Fresnel、高光和 roughness；内部散射负责低频 diffuse 的空间扩散和透光。把最终 beauty color 整体模糊会同时抹掉毛孔、法线和镜面高光，造成典型“蜡像感”。

Diffusion profile 描述不同颜色通道的散射半径
   实时皮肤常为 RGB 设置不同扩散范围，使红色传播更远、绿蓝更短。Profile 应绑定真实材质尺度，并稳定映射到当前屏幕像素半径；相机距离和分辨率变化不应让散射宽度无控制漂移。

Screen-space SSS 用屏幕邻域近似跨表面传播
   常见输入包括 depth、normal、diffuse lighting/irradiance、albedo、material/profile id。Blur 时使用 depth 和 normal 权重阻止跨物体、跨轮廓和跨大折线渗色。它易接入 deferred renderer，但无法访问屏幕外和被遮挡表面信息。

Thickness 描述光穿过介质的有效距离
   Thickness map、light-space entry/exit depth 或其它厚度估计适合耳廓、鼻翼、手指和叶片。薄处背光透射更强，厚处因吸收衰减更暗。它解决的是“穿过多少介质”，不等同于表面邻域 blur。

Wrap lighting 与 pre-integrated skin 是更低成本近似
   Wrap lighting 通过扩展 ``N·L`` 响应柔化明暗交界，几乎不需要额外 buffer；pre-integrated skin 通过 LUT 把曲率、光照角度和散射响应预先压缩。它们适合移动端、风格化或预算受限路径，但表达不了完整空间传播。

SSS 应优先扩散低频 diffuse irradiance
   Diffuse lighting 可以被邻域传播；specular、normal 细节和大多数高频材质信号应保持独立。面颊阴影变柔而毛孔仍清晰，是判断分层是否正确的关键视觉证据。

Depth、normal 与 material mask 是边界保护三件套
   Depth 防止前景皮肤向背景渗色，normal 防止跨鼻梁、唇线等几何折线扩散，material/profile id 防止皮肤 profile 影响眼球、牙齿、头发或其它材质。

实时 SSS 的成本主要由分辨率、采样核和覆盖面积决定
   Half-resolution、separable blur、tile/skin mask 筛选、有限 profile 数量和按距离降级可显著降低成本。近景 hero 角色可使用高质量 profile + thickness，远景则可以退回更简单近似。

关键路径
--------

Deferred screen-space SSS：

::

   G-buffer 生成 skin mask / profile id / depth / normal / albedo
   → lighting pass 得到 diffuse irradiance
   → 选择当前 profile 半径和 RGB 权重
   → 横向 blur，使用 depth/normal/material 权重
   → 纵向 blur，继续边界保护
   → 得到 scattered diffuse
   → 可选 thickness/translucency 背光项
   → 与未模糊 specular 合成
   → tone mapping

SSS 画面错误排查：

::

   关闭 SSS 保存基线
   → 检查 skin mask 与 profile id
   → 确认 blur 输入是 diffuse/irradiance 而非最终颜色
   → 检查 profile 半径和世界/屏幕尺度
   → 检查 depth 权重
   → 检查 normal 权重
   → 单独检查 thickness 与背光方向
   → 最后恢复 specular 和真实 albedo

概念辨析
--------

* **BRDF 与 BSSRDF**：BRDF 处理同一表面点的反射，BSSRDF 允许光在一个位置进入、另一个位置离开。
* **Diffusion profile 与 blur kernel**：profile 描述材质散射分布；blur kernel 是屏幕空间实现这一分布的数值近似。
* **Screen-space SSS 与 thickness**：前者扩散可见表面的低频光照；后者估计背光穿过介质的距离，解决不同视觉问题。
* **SSS 与 translucency**：SSS 强调内部散射和邻域出射；translucency 常强调薄区域背光穿透，两者可组合但不应混成一个参数。
* **Roughness 与 SSS radius**：roughness 控制表面镜面高光，SSS radius 控制内部 diffuse 扩散范围，职责完全不同。
* **Specular 与 diffuse SSS**：specular 通常保持锐利，diffuse 参与扩散；整体模糊会破坏材质层次。
* **Wrap lighting 与真实扩散**：wrap 只修改局部角度响应，没有真实跨位置传播，属于廉价视觉近似。

本章结论
--------

SSS 的工程核心是把“表面反射”和“内部散射”分开，并只让低频 diffuse 沿材质允许的空间范围传播。近景皮肤应由 diffusion profile 控制扩散、screen-space pass 完成邻域传播、thickness 处理薄处背光，depth/normal/mask 保护边界，specular 保持独立；这样柔化、透光和高频细节才能同时成立。