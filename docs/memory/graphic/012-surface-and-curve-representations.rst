第012章：曲线与曲面表示
=======================

核心知识点
----------

连续表示与运行时网格属于不同层级
   Bézier、B-Spline、NURBS 和 subdivision surface 用少量控制数据表达可编辑的连续形状；实时管线最终消费求值后的 patch、顶点、索引及属性。画面问题必须先确认当前使用的是控制曲面、运行时细分结果还是离线三角网格。

表示方式决定控制能力与求值成本
   Bézier 适合局部轮廓和短曲线，B-Spline 适合长距离局部光顺控制，NURBS 通过权重精确表达圆弧和工程曲面，subdivision surface 用粗控制笼逼近有机极限曲面。所有表示进入实时渲染前都要确定采样密度、边界缝合和属性生成规则。

参数化把三维曲面映射到二维纹理域
   UV 是随顶点进入 GPU 的参数化结果。Seam 是曲面被剪开的边界，stretch 是长度或面积比例变化，texel density 描述单位表面占用的纹理像素，chart packing 与 padding 决定 mipmap 下是否产生边界串色。

UV seam 通常要求复制渲染顶点
   同一空间位置在不同 UV chart 中拥有不同 UV，因此会生成多个顶点；normal、tangent、morph delta 和 skin weight 也可能随之分裂。位置连续不代表光照、采样或动画连续，接缝两侧的完整属性必须按设计意图校验。

几何近似误差与参数化误差应分开判断
   连续曲面采样过稀会破坏 silhouette、曲率和高光；UV 拉伸会改变纹理方向、清晰度与 texel density。模型空间误差还要投影到屏幕像素判断，同一误差在近景和远景的可见程度不同。

Tangent space 决定 normal map 接缝
   DCC、烘焙工具、导入器与运行时 shader 必须使用兼容的 tangent basis。Tangent handedness、镜像 UV、零面积 UV、退化三角形或不同三角化结果都会让 normal map 在侧光下出现亮线和翻转。

动画会放大静态属性不一致
   Morph target 可修改 position、normal 与 tangent，skinning 使用 joint 和 weight 变换顶点。Seam 两侧重复顶点若拥有不同 morph delta 或 skin weight，中立姿态可以闭合，动画后却会形成几何裂缝或光照断层。

曲面变形后仍需维护着色属性
   只更新 position 而沿用旧 normal、tangent，会让形状与光照解释不一致。大幅变形还会让固定 UV 产生动态拉伸，需要从基础拓扑、UV 分配、变形属性或材质补偿中选择修复位置。

关键路径
--------

连续曲面进入 GPU：

::

   DCC 控制点、knot、weight 或 subdivision cage
   → 曲线曲面求值
   → 按曲率、距离或屏幕误差采样
   → 三角化并生成 position/index
   → 生成 UV、normal、tangent 与 seam split
   → 导入器统一单位、轴向和属性
   → 上传 vertex/index buffer
   → shader 变换、插值、采样与着色

接缝排查：

::

   用纯色、checker、flat normal 分离几何与材质现象
   → 按 position 聚类 seam 两侧重复顶点
   → 比较 UV、normal、tangent 与 tangent sign
   → 检查退化三角形和零面积 UV
   → 确认烘焙与运行时 tangent basis 一致
   → 检查 atlas padding、mipmap 与导出三角化
   → 在目标光照和距离下复查

动画曲面排查：

::

   先验证 bind pose 的 mesh、UV、normal 和 tangent
   → 单独播放一个 morph target
   → 比较 seam 两侧 position/normal/tangent delta
   → 单独播放 skinning 并比较 joint/weight
   → 检查 morph、skinning、node transform 的执行顺序
   → 重新计算或正确混合变形后的 normal/tangent
   → 组合动画与材质复查接缝和纹理拉伸

概念辨析
--------

* **控制曲面与三角网格**：控制曲面保存连续形状意图；三角网格是有限采样结果，直接进入多数实时绘制路径。
* **Bézier、B-Spline 与 NURBS**：Bézier 控制直观但长曲线需分段；B-Spline 提供局部控制；NURBS 在 B-Spline 上加入权重以表达精确有理曲面。
* **Subdivision 与 tessellation**：subdivision 定义曲面细化规则；tessellation 是把 patch 或曲面按某个精度展开为可绘制图元的过程。
* **UV seam 与几何裂缝**：UV seam 可以只分裂纹理参数而保持位置连续；几何裂缝表示变换后 position 也不连续。
* **几何误差与着色误差**：几何误差改变真实轮廓或表面位置；着色误差来自 normal、tangent、UV 或材质解释，即使轮廓正确也可明显可见。
* **Morph target 与 skinning**：morph 用属性增量改变基础网格；skinning 用骨骼矩阵加权变换顶点。两者可叠加，但属性与执行顺序必须一致。
* **Texel density 与纹理分辨率**：纹理分辨率是资源总像素数；texel density 是这些像素如何分配到模型表面，局部密度失衡不能只靠提高整图分辨率修复。

本章结论
--------

曲面资产应沿“表示—采样—参数化—属性—动画—shader”整条链判断。先确认连续形状如何变成运行时网格，再区分几何近似与 UV 失真，随后检查 seam 两侧的 normal、tangent 和动画属性；只有控制层、导入层与运行时解释保持一致，曲面轮廓、贴图密度、normal map 和动态变形才能同时稳定。