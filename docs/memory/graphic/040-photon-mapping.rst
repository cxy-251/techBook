第040章：Photon Mapping
======================

核心知识点
----------

Photon Mapping 是“光源端追踪 + 相机端密度估计”的双阶段算法
   第一阶段从光源发射 photon，沿 BSDF 在场景中传播，并在合适表面记录位置、入射方向、flux 和路径类型。第二阶段从 camera hit point 查询邻近 photon，用局部密度估计得到间接光或 caustics。

Photon 是算法样本，不是逐个真实物理光子
   它携带一小份光通量和路径状态，服务于数值估计。工程实现关心的是采样分布、flux 权重、空间位置和材质事件，而不是物理粒子计数。

Caustic map 与 global map 应分离
   经过 specular reflection/transmission 后首次命中 diffuse 表面的 photon 适合进入 caustic map，用较高密度和较小 gather 半径表达高频焦散；普通多次 diffuse 传播更适合 global map，用于低频 color bleeding 和间接光。

密度估计把离散 photon 转成连续光照
   对半径 ``r`` 内 photon，可近似把 ``sum(flux * BRDF)`` 除以 ``pi*r^2``。半径越大，结果越平滑但 bias 越强；半径越小，细节更锐但稀疏区域噪声更明显。

Photon 数量与 gather 半径共同决定 bias-variance 取舍
   更多 photon 允许使用更小半径并保持稳定，焦散更锐；photon 少时必须扩大半径才能得到足够样本，焦散会变厚。Progressive Photon Mapping 通过多轮累计并逐步缩小半径改善这一矛盾。

kd-tree 与 hash grid 都服务近邻查询
   kd-tree 适合静态离线 photon map 和 k-nearest/radius 查询；hash grid 适合 GPU、固定 cell 和动态更新。选择应看构建频率、查询半径、内存布局和并行方式，而不是只比较理论复杂度。

固定半径与 k-nearest 是两种不同估计策略
   固定半径控制物理支持范围，但 photon 数会随局部密度波动；k-nearest 固定样本数量，并让第 k 个 photon 的距离决定局部半径，稀疏区更稳但高频边缘容易被扩大半径抹宽。

查询必须保护几何与材质边界
   邻近 photon 在三维距离上很近，也可能位于薄墙另一侧或背面。应结合法线、平面距离、surface/material/path flags 过滤，否则会出现跨面漏光和错误焦散。

Photon emission 的 PDF 决定效率与能量正确性
   完全球面随机发射会浪费大量 photon。可针对玻璃、水面或 caustic generator 的立体角做重要性采样，但必须把对应 PDF 纳入 photon flux，才能提高命中率而不改变总能量。

Path flags 是 caustics 正确分类的关键
   Photon 经历过 specular/glossy/transmission 事件后，再命中 diffuse receiver，才能被识别为 caustic path。Flags 错误会让真正焦散 photon 进入 global map，或者普通间接 photon 污染 caustic map。

Photon Mapping 擅长相机端很难随机命中的困难光路
   小光源经过玻璃或镜面再聚焦到 diffuse 表面的 ``Light→Specular→Diffuse→Camera`` 路径，是普通单向 Path Tracing 的高方差区域，却天然适合从 light side 生成 photon 后缓存。

动态场景是主要工程边界
   只移动相机时 photon map 可复用；移动光源、玻璃、接收面或改变材质后，旧 photon 分布失效，通常需要重发射或局部更新。因此实时系统常只保留局部 caustics 或其它简化 light-side cache。

关键路径
--------

Photon Map 构建：

::

   sample light position / direction / power
   → 初始化 photon flux 与 PDF
   → trace scene
   → BSDF reflection / transmission / diffuse
   → 更新 throughput / path flags
   → 在 diffuse hit 处分类 caustic/global
   → 写 photon position / incidentDir / flux
   → 构建 kd-tree / hash grid

相机 gather：

::

   camera ray
   → visible surface hit
   → 查询 radius 或 k-nearest photons
   → 法线 / surface / path-type 过滤
   → kernel weight
   → sum photon flux
   → area normalization
   → receiver BRDF
   → caustic/global indirect contribution
   → 与 direct/specular 合成

Caustics 排查：

::

   显示 photon ray / hit point cloud
   → 检查 specular/transmission path flags
   → 检查 caustic map 数量
   → 检查 receiver 上 photon 密度
   → 检查 gather count / radius
   → 检查 flux / PDF / photon count 归一
   → 最后检查 BRDF 与最终合成

概念辨析
--------

* **Photon Mapping 与 Path Tracing**：前者从 light side 生成并复用空间样本，密度估计带 bias；后者从 camera side 随机估计路径，标准形式主要表现为 variance。
* **Caustic map 与 global map**：前者专注 specular/glossy 后落到 diffuse 的高频能量；后者服务更一般的低频间接 diffuse。
* **Photon flux 与 radiance**：photon 保存的是离散光通量样本，camera gather 后结合面积和 BRDF 才形成当前观察方向的 radiance。
* **Radius query 与 k-nearest**：前者固定空间尺度，后者固定样本数并自适应尺度。
* **Photon density 与 brightness**：密度高通常意味着局部能量聚集，但最终亮度还受每个 photon flux、BRDF 和面积归一影响。
* **Emission targeting 与作弊增亮**：针对 caustic generator 重要性采样只改变样本分布，必须用 PDF 修正 flux，不能直接增加总能量。
* **Blotch 与 firefly**：Photon Mapping 的 blotch 多来自稀疏/大半径密度估计；Path Tracing firefly 多来自低 PDF 高贡献路径。

本章结论
--------

Photon Mapping 应沿“光源发射—路径分类—空间存储—局部查询—密度估计”理解。焦散问题先看 photon 是否正确穿过 specular/transmission 物体并落到 receiver，再看 map 分类、查询半径和 flux 归一。它最适合 light-side 容易发现而 camera-side 难采到的高能量路径，代价是额外存储、密度估计 bias 和动态更新压力。