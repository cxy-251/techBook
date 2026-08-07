第125章：体渲染
==============

核心知识点
----------

体渲染直接积累体数据内部样本
   与表面光栅化不同，Volume Rendering 对每个像素生成射线，在三维标量场中推进并采样，再把多个样本合成为最终颜色。输入通常是 3D texture、transfer function、相机和包围盒。

Scalar Field 是基础数据模型
   ``V(x,y,z)`` 表示三维空间中的标量值。CT 强度、密度、温度、烟雾浓度和地质属性都可使用同一模型。体素 spacing 和物理单位必须参与采样与坐标变换。

Transfer Function 决定“哪些结构可见”
   标量值通常映射到 RGBA，颜色表示类别或数值，alpha 决定沿射线的遮挡贡献。Transfer function 本质上是数据分类器，错误范围会直接让结构消失、粘连或过曝。

Ray Marching 的基本路径稳定
   Screen pixel → camera ray → volume box intersection → sample position → 3D texture → transfer function → alpha accumulation → next step。任何黑屏或裁剪异常都可以沿这条链逐段排查。

前向 Alpha Compositing 保持前后遮挡关系
   常见累积形式是 ``C += (1-A)*a*c``、``A += (1-A)*a``。当前方透明度接近 1 后，后方样本贡献迅速下降，因此可使用 early termination。

Step Size 同时控制质量和成本
   步长过大会漏掉细薄结构并产生 banding；过小会增加纹理读取和循环次数。基准步长应与 voxel spacing 关联，而不是只按纹理分辨率拍脑袋设置。

透明度应随步长归一
   改变采样距离时，单次 alpha 不能保持不变，否则整体亮度和遮挡会随步数变化。基于密度和路径长度的指数衰减更容易保持积分稳定。

Gradient 提供边界和局部方向
   标量场梯度可通过邻域差分估计。梯度方向可用于局部光照，梯度幅值可强调组织或材料边界；它补充的是“变化信息”，不是替代原始标量。

Early Termination 减少高不透明区域采样
   当累积 alpha 接近饱和时提前结束射线。它对高密度/高透明结构收益明显，对整体半透明云雾类场景收益有限。

Empty-Space Skipping 跳过无贡献区域
   将体数据分成 brick，并保存 min-max、occupancy 或最大 alpha，可让射线直接跨过当前 transfer function 下完全透明的块。Transfer function 变化后，跳过条件也必须重新验证。

Pre-Integration 处理尖锐 Transfer Function
   当两个采样点之间跨过窄高透明区时，普通点采样可能漏掉贡献。Pre-integration 用相邻标量与步长估计区间积分，适合窄窗口医学可视化和受限采样预算。

Jitter 把规则条纹转成噪声
   对射线起点或步进位置做随机/低差异偏移能打散 banding，后续可用 temporal accumulation 降噪。它改善静态结构，却可能增加交互时闪烁。

Fragment 与 Compute 都可实现体渲染
   Fragment 路径通常以全屏三角形或包围盒驱动像素射线；Compute 路径更方便 tile、共享缓存和自定义输出。选择依据是资源组织、同步和后续 pass，而不是算法语义差异。

体渲染常同时受纹理带宽、循环和 ALU 限制
   3D texture sample、梯度估计、transfer lookup 消耗带宽；光照和积分消耗 ALU；不同射线长度和 early-out 会造成控制流差异。Profiler 需要同时看 pass time、采样次数、memory throughput 和 iteration 分布。

容量问题必须独立处理
   ``512^3`` 的 16-bit 单通道体数据已约 256 MB，多时间步、梯度和层级数据会快速放大显存。格式量化、brick、mipmap、sparse/streaming 和多分辨率是资源系统问题，不应只靠 shader 优化解决。

LOD/Brick 应与 Transfer Function 关联
   某个 brick 的 min-max 若与当前非透明区间无交集，可不加载或不采样；用户修改窗口后，原先透明块可能变可见。数据工作集必须随 transfer function 动态变化。

医学/地理实例都应保留元数据语义
   CT/MRI 需要 spacing、窗口、强度单位与切片方向；地质/气象体需要空间坐标、变量单位和层级。最终画面必须能反查到原始数据范围和当前质量层级。

关键路径
--------

单像素 Ray March：

::

   pixel
   → camera ray
   → volume box entry/exit
   → sample 3D texture
   → scalar + gradient
   → transfer function
   → opacity/color accumulation
   → early terminate or advance
   → final pixel

性能优化：

::

   measure volume pass
   → inspect step count / ray length
   → reduce empty samples
   → early termination
   → brick/min-max skipping
   → adjust format / gradient storage
   → LOD / streaming
   → compare quality + frame time

大体数据路径：

::

   source volume
   → preprocess / quantize / brick
   → build min-max + hierarchy
   → stream visible bricks
   → resident 3D resources
   → ray march current LOD
   → refine when interaction settles

概念辨析
--------

* **Volume Rendering 与 Isosurface Rendering**：前者沿射线积分内部样本，后者先提取某个等值表面再按表面渲染。
* **Scalar 与 Gradient**：scalar 表示数据值，gradient 表示局部变化方向和强度。
* **Step Size 与 Volume Resolution**：一个是采样策略，一个是数据离散精度；两者相关但不等价。
* **Early Termination 与 Empty-Space Skipping**：前者因前景已不透明而结束，后者因未来区域无贡献而跳过。
* **Compression 与 LOD**：compression 减少字节，LOD 减少当前需要的数据精度和工作集。
* **Preview Volume 与 Final Volume**：交互时可用低分辨率或大步长，停止后再恢复高精度。

本章结论
--------

体渲染应按“Scalar Field—Transfer Function—Ray/Box—Sampling—Compositing—Acceleration—Streaming—Evidence”理解。画面异常先查数据范围、坐标和 transfer function，再查步长与积分；性能问题则先减少无贡献采样，再处理体数据容量和驻留。高质量体渲染的核心，是让采样精度、可见结构和资源预算共同受控。