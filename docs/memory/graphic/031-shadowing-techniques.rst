第031章：阴影技术
=================

核心知识点
----------

阴影的本质是光照可见性测试
   对当前接收面 fragment，局部光照已经知道 ``N``、``L`` 和材质；阴影再回答“这条光路是否被遮挡”。最终常把直接光乘以 ``shadowFactor``，其中 1 表示光可达，0 表示被挡住，中间值来自过滤或软阴影近似。

Shadow Mapping 用光源深度图近似遮挡关系
   第一遍从光源视角只写 depth，得到 shadow map；第二遍相机 pass 把当前世界位置变换到 light space，取得 receiver depth，并与 shadow map 中的最近深度比较。Caster 与 receiver 可以来自不同可见集合，屏幕外物体也可能投下屏幕内阴影。

Shadow pass 必须与真实几何变形保持一致
   Skinned mesh、morph、alpha cutout、wind animation 等若只在 color pass 中执行，而 shadow pass 没有等价处理，阴影会与物体分离。Depth-only 不代表可以忽略决定真实轮廓的顶点或 alpha 逻辑。

Bias 是数值稳定性与接触精度之间的权衡
   Bias 太小会产生 shadow acne，自身表面因深度误差出现黑色条纹；bias 太大会产生 Peter Panning，阴影与物体接触处出现亮缝。常量 bias、slope-scaled bias、normal offset 都应围绕实际分辨率、投影范围和表面倾角调节。

PCF 过滤的是深度比较结果，而不是简单模糊深度图
   多个邻近 texel 分别执行 compare，再对可见性结果求平均，可缓解硬锯齿。采样核越大，纹理访问越多，并且接收面深度与邻近 texel 的几何对应越弱，bias 与漏光问题也会被放大。

CSM 通过多个级联分配方向光阴影分辨率
   相机视锥按深度切分，每个 subfrustum 建立独立 light-space 正交投影。近级联范围小、texel 密度高，负责角色脚下和近景；远级联覆盖建筑和大场景。Cascade 数量、split、blend band 和投影稳定性共同决定质量与成本。

Texel snapping 用少量空间浪费换时间稳定性
   方向光正交投影若随相机连续平移，同一世界点会不断跨 shadow texel，产生 shimmer。把 light-space 投影中心量化到 ``worldUnitsPerTexel`` 的整数倍，可以明显降低相机移动时的边缘抖动。

Shadow Volumes 用几何体积与 stencil 判断阴影区域
   从相对光源的 silhouette edge 延伸体积，结合已有 depth buffer 和 stencil increment/decrement 统计视线是否穿过阴影体。Z-pass 实现简单但怕相机进入体积或 near clipping；z-fail 更鲁棒，但要求体积闭合并正确处理前后盖面。

Shadow Map 与 Shadow Volume 的成本结构不同
   Shadow Map 主要受额外 depth pass、纹理分辨率、PCF 和 cascade 数影响；Shadow Volume 主要受 silhouette 构建、额外几何和 stencil fill cost 影响。现代通用引擎通常以 Shadow Mapping 为主，volume 更适合硬阴影、特殊风格或调试路径。

关键路径
--------

方向光 Shadow Mapping：

::

   计算 light view/projection
   → 生成 shadow caster list
   → depth-only shadow pass
   → shadow depth texture
   → DepthWrite 到 ShaderRead 状态转换
   → camera pass 获得 world position
   → world → light clip → shadow UV/depth
   → 选择 cascade
   → comparison sample / PCF
   → shadowFactor
   → 调制直接光

阴影伪影排查：

::

   固定相机、光源并关闭随机/时间过滤
   → 显示 shadow map depth
   → 检查 caster 变形与 alpha cutout
   → 显示 light-space UV / cascade index
   → 关闭 PCF 查看 raw compare
   → 调整 constant/slope bias
   → 检查 cascade split / blend
   → 锁定矩阵并检查 texel snapping
   → 最后再调 resolution、filter 和 contact shadow

Shadow Volume：

::

   找到相对光源的 silhouette edge
   → 沿背光方向挤出封闭 volume
   → 先有 camera depth
   → 渲染 volume front/back
   → 按 z-pass 或 z-fail 更新 stencil
   → stencil 非零区域标记阴影
   → lighting pass 使用 stencil mask

概念辨析
--------

* **Shadow 与 local lighting**：光照模型回答表面如何反射到达的光；阴影回答光是否到达表面。
* **Caster 与 receiver**：caster 写入或形成遮挡信息，receiver 读取可见性；同一物体可以同时承担两者。
* **Shadow map depth 与 camera depth**：前者在光源空间记录最近遮挡面，后者在相机空间解决最终可见性，不能混用坐标语义。
* **Bias 与 filtering**：bias 修正深度比较数值误差，filter 改善边缘采样质量；大核 filter 不能替代正确 bias。
* **Acne 与 Peter Panning**：前者常来自 bias 不足，后者常来自 bias 过大，是同一调节轴两端的失败表现。
* **CSM 与普通多 shadow map**：CSM 专门按相机深度切分同一方向光覆盖范围，用多个投影重新分配 texel 密度。
* **PCF 与普通 blur**：PCF 对多个 texel做深度比较后平均，不是先把 depth texture 做普通颜色模糊。
* **Z-pass 与 z-fail**：两者都用 stencil 计数阴影体穿越关系，但更新发生在 depth pass 或 fail 条件上，鲁棒性边界不同。

本章结论
--------

阴影系统应沿“光源空间几何—深度/体积表示—接收面可见性—过滤与稳定性”理解。Shadow Mapping 的正确性先看 light matrix、caster、深度比较和 bias，再看 PCF、级联和 texel snapping；Shadow Volume 则先看 silhouette、体积闭合和 stencil/depth 状态。质量优化只有在这些基础路径正确后才有意义，否则更高分辨率和更多采样只会放大错误与成本。