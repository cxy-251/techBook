第007章：坐标系与变换
=====================

核心知识点
----------

每个几何量都必须携带空间标签
   model、world、view、clip、NDC 与 screen space 是同一对象在不同参照系中的表达。位置、法线、光照方向、观察方向和屏幕 UV 只有在所属空间明确时才能安全参与相减、点乘、重建或采样。

位置路径具有固定阶段边界
   局部顶点经 ``model`` 进入世界空间，经 ``view`` 进入相机空间，经 ``projection`` 进入四维 clip space；固定管线完成裁剪、perspective divide 和 viewport 映射。几何消失、位置错误和深度异常应沿这条路径逐阶段定位。

变换组合顺序决定参照系
   在列向量约定下，常见局部到世界变换为 ``T * R * S``，实际执行顺序从右向左。父子层级通常满足 ``WorldChild = WorldParent * LocalChild``。变换顺序错误会让物体绕错误中心旋转、平移被缩放或层级挂点错位。

逆矩阵负责反向空间映射
   相机的 ``view`` matrix 是 camera world transform 的逆；世界位置乘模型矩阵的逆可回到模型空间；屏幕深度经 inverse projection 与 inverse view 可重建世界位置。逆变换成立依赖原矩阵可逆且所有约定属于同一帧和同一管线。

投影参数共同决定透视与深度
   FOV 控制视野与透视感，aspect 控制横纵比例，near/far 控制可见范围和深度精度，NDC depth range 决定投影矩阵与深度纹理解释。reversed-Z 还要求同步调整投影、clear depth、compare function 和深度重建。

光照运算要求方向处于同一空间
   ``N``、``L`` 和 ``V`` 可统一放在 world space 或 view space，不能混用。法线在非均匀缩放后需要 normal matrix，光栅化插值后还需重新归一化，否则相机或对象运动会让明暗关系异常。

屏幕空间重建依赖完整约定
   screen UV、viewport 原点、深度样本、NDC depth range、jitter、inverse projection 和 inverse view 必须匹配。任一项来自不同 API 约定或不同帧，SSAO、SSR、TAA 与拾取都会产生翻转、漂移或断层。

调试应先固定单个观察对象
   选择一个顶点、法线或像素，逐步输出 world position、view depth、clip ``w``、NDC、world normal、linear depth 或 UV。复杂材质和后处理应在基础空间路径验证后再恢复。

关键路径
--------

位置空间转换：

::

   model-space position
   → model matrix
   → world-space position
   → view matrix
   → view-space position
   → projection matrix
   → clip-space position
   → clipping 与 perspective divide
   → NDC
   → viewport 映射为 screen position 与 depth

世界空间光照：

::

   model-space normal
   → normal matrix
   → world normal 并归一化
   → world light position - world surface position
   → 归一化为 light direction
   → 与 world normal 计算 dot
   → 输出漫反射或进入更复杂材质模型

屏幕深度重建世界位置：

::

   screen UV 与 depth sample
   → 按 API 约定转换为 NDC x、y、z
   → 组成 clip coordinate
   → inverse projection 得到 view position
   → 除以 view w
   → inverse view 得到 world position
   → 与当前帧相机、jitter 和 viewport 结果交叉验证

概念辨析
--------

* **model space 与 world space**：model space 以资产局部原点和轴为参照；world space 表示对象在场景中的全局位置与方向。
* **view space 与 camera world transform**：camera world transform 描述相机在世界中的姿态；view matrix 是其逆，用于把整个世界转换到相机参照系。
* **clip space 与 NDC**：clip space 是投影后的四维坐标，仍保留 ``w`` 并用于裁剪；NDC 是透视除法后的三维标准化坐标。
* **NDC 与 screen space**：NDC 与具体分辨率无关；screen space 经过 viewport 映射，具有像素尺寸、原点方向和 framebuffer 约定。
* **row/column major 与矩阵顺序**：前者描述数字在内存中的排列；后者描述变换如何组合。错误排查必须分别验证。
* **near/far 与 depth range**：near/far 是相机可见距离参数；depth range 是 clip/NDC 到深度缓冲的 API 约定。二者共同影响深度精度但不可互换。
* **普通 Z 与 reversed-Z**：普通 Z 通常让近处映射到较小深度；reversed-Z 反转映射以改善浮点深度分布，同时必须反转清屏值和比较方向。
* **screen UV 与纹理 UV**：screen UV 来自 framebuffer 位置，用于屏幕纹理；mesh UV 来自资产参数化，用于材质纹理。两者范围可能相同，语义和插值来源不同。

本章结论
--------

坐标变换是一条可逐阶段验证的数据路径，而不是一组孤立矩阵公式。阅读渲染代码时，应先确定每个量的空间和几何语义，再检查 TRS、层级、逆矩阵、投影和屏幕约定；排查错误时抓住固定顶点、法线或像素沿路径观察，能把位置、光照、深度与后处理问题分离到真实责任阶段。