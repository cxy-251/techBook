第008章：几何与向量分析
=======================

核心知识点
----------

连续几何最终要进入离散图元
   Bezier、B-Spline、NURBS 与参数曲面使用控制点和参数域描述连续形状，光栅化管线最终消费顶点、索引和三角形。采样密度决定 silhouette 与曲率近似，法线和切线生成决定离散网格上的局部朝向。

几何精度与着色连续性是两类问题
   三角形数量不足会让轮廓和曲率呈现折线；法线、切线或 UV 处理错误会让几何轮廓正确却出现高光断裂和 normal map 接缝。排查时应先看 silhouette，再看 debug normal、tangent 与材质接缝。

面法线由绕序和叉乘决定
   三角形的未归一化面法线可由 ``cross(P1 - P0, P2 - P0)`` 得到，方向取决于顶点绕序，长度与三角形面积相关。它既可用于 flat shading，也可作为面积加权顶点法线的贡献。

顶点法线由邻域与平滑策略决定
   面积加权、角度加权和 smoothing group 会产生不同顶点法线。hard edge、UV seam、material split 或 tangent sign 不一致时，同一几何位置可能必须拆成多个顶点，不能只按 position 去重。

切线空间连接纹理与表面方向
   ``T``、``B``、``N`` 构成 TBN basis，normal map 样本从 ``[0,1]`` 解码到 ``[-1,1]`` 后，经 TBN 变换到 world 或 view space。镜像 UV 需要 tangent sign，贴图 Y 通道、切线算法和烘焙工具必须与运行时一致。

梯度把标量场转换为方向信息
   高度场 gradient 表示最大上升方向，可构造扰动法线；SDF gradient 指向距离增长最快方向，可用于 ray marching 表面法线；divergence 描述流场局部源汇，curl 描述局部旋转。使用前必须确认场的定义域、采样步长和输出尺度。

静态属性应优先在资产阶段预计算
   静态曲面采样、normal、tangent、bounds、LOD 和邻接信息适合在导入阶段生成并缓存；运行时顶点位移、动态拓扑、SDF 或高度场法线才需要 shader 或 compute 重新计算。阶段选择取决于数据是否随帧变化和是否值得重复计算。

Lambert 是方向链的最小验证模型
   在线性颜色空间中，``max(dot(N, L), 0)`` 把单位法线与单位光照方向的夹角转换为漫反射比例。它能直接验证法线空间、TBN、normal map、光向量、归一化和颜色能量是否一致。

关键路径
--------

参数曲面进入实时渲染：

::

   DCC 中的控制点、knot 与参数曲面
   → 按曲率或误差阈值采样参数域
   → 生成 position 与 index
   → 按平滑、UV 和材质边界生成 normal、tangent
   → 上传 vertex/index buffer
   → vertex shader 变换几何属性
   → rasterizer 插值
   → fragment shader 完成材质与光照

Normal map 进入光照：

::

   顶点 normal、tangent 与 tangent sign
   → 在同一空间构造 TBN
   → 采样 normal map
   → 从 [0,1] 解码到 [-1,1]
   → TBN 变换为 shading normal
   → 重新归一化
   → 与同空间 light direction 计算 Lambert 或 BRDF

标量场生成方向：

::

   height、SDF 或其它标量场
   → 在匹配定义域的位置采样邻域
   → 按纹理尺寸或世界尺度选择差分步长
   → 计算 gradient
   → 归一化或保留幅值
   → 用于法线、流向、边界或 debug 可视化

概念辨析
--------

* **连续曲面与三角形网格**：连续曲面由参数和控制结构定义；网格是对它的有限采样，用于实时渲染、碰撞和缓存。
* **几何法线与着色法线**：几何法线来自实际三角形；着色法线可以由顶点插值、normal map 或程序扰动得到，用于控制光照而不改变真实轮廓。
* **面法线与顶点法线**：面法线属于单个三角形并产生 flat shading；顶点法线综合相邻面贡献，在光栅化后形成平滑变化。
* **normal 与 tangent**：normal 指向表面外侧；tangent 沿表面 UV 方向。二者与 bitangent 共同定义 normal map 的局部坐标系。
* **几何接缝与 UV 接缝**：几何接缝表示位置或拓扑断开；UV 接缝允许位置连续但纹理坐标分裂，并常伴随 tangent 或顶点拆分。
* **gradient、divergence 与 curl**：gradient 将标量场变为方向场；divergence 衡量向量场的局部流出或流入；curl 衡量局部旋转趋势。
* **预计算与运行时计算**：预计算减少每帧成本并保持资产一致性；运行时计算能响应变形和动态场，但增加同步、带宽和执行成本。

本章结论
--------

几何处理的核心是把连续形状、离散拓扑、顶点属性和 shader 方向计算连接成一条数据链。阅读资产管线或排查画面时，应先区分几何采样误差与着色属性错误，再沿 normal、tangent、场梯度和光向量检查空间与接缝；Lambert 调试图能够以最小计算验证这条链是否完整。