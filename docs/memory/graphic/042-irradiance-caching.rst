第042章：Irradiance Caching
==========================

核心知识点
----------

Irradiance Cache 缓存的是 diffuse 间接照度
   对 Lambertian 或近似 diffuse 表面，出射间接光主要由半球入射 irradiance 决定。大面积墙面、地面和天花板上的 irradiance 变化通常较低频，因此可以用少量高质量 record 服务邻近 shading point。

Cache 的收益来自“稀疏高成本估计 + 邻域插值复用”
   当前 hit point 先查询已有 record；若足够可信就插值，否则发射半球 ray 重新估计 irradiance、创建 record 并插入空间结构。这样把逐点重复 ray tracing 转成 cache hit 与少量 miss tracing。

Record 必须保存几何、光照和生命周期信息
   最少包括 position、normal、irradiance、valid radius、局部几何尺度、surface/room key、可选 gradient、age/version。没有这些字段，就无法判断一个 record 能否跨位置、跨法线或跨帧安全复用。

可信半径应跟局部几何尺度变化
   开阔墙面半球 ray 的命中距离较大，record 可以覆盖更远；墙角、门洞、桌脚附近遮挡变化快，半径应缩小并增加 record density。固定世界半径容易在简单区域过密、复杂边界又漏光。

插值必须同时考虑距离、法线和结构边界
   空间距离只说明点靠得近，不代表看到同一半球。法线差异、surfaceKey、room/portal、薄墙、depth discontinuity 和 visibility 都可作为 rejection 条件。跨墙复用是典型漏光来源。

Gradient 只适合补偿低频局部变化
   Irradiance gradient 可以预测位置移动或法线旋转后的照度变化，使大面积缓变表面更平滑；它不能跨越可见性突变。门洞和桌脚附近仍应由 rejection 与新增 record 处理。

Cache hit 与 miss 都必须可观察
   调试 overlay 应显示 record id、参与 record 数、最大权重、误差、miss 标记、rejection reason 和 density。这样漏光、过度平滑和重复 record 才能映射到具体规则。

错误复用比 cache miss 更危险
   Miss 只是增加 ray tracing 成本；错误 hit 会把另一侧墙面、旧灯光或旧遮挡的 irradiance 插值进当前点，产生系统性 bias。优化时不能只追求更低 miss ratio。

动态场景需要明确 invalidation
   物体移动、灯光变化、门开合都会改变可见半球和 irradiance。可通过 version、age、局部 dirty region 或分层 cache 区分静态层、动态修正层与短期 history，避免旧 record 长期污染结果。

Record density 应由误差驱动而非屏幕分辨率驱动
   开阔区域密度高通常表示半径过保守；边界区域密度低通常表示 rejection 不够严格。Miss ratio、单位面积 record 数、每帧新增数和最大插值误差应同时观察。

GPU 实现还要处理并发和存储布局
   多线程同时 miss 可能在同一区域重复插入 record，需要 cell 级合并、append buffer 上限和淘汰策略。Record 字段应紧凑，随机 lookup、原子写、barrier 和 history resolve 都可能成为真实瓶颈。

Irradiance Cache 只适合低频 diffuse indirect
   Glossy reflection、mirror、transmission、sharp shadow 和 caustics 不应直接塞进同一 irradiance record。现代 radiance/probe/neural cache 虽然扩展了表达对象，但本章的核心仍是 diffuse irradiance 的受控复用。

关键路径
--------

Cache lookup 与补样本：

::

   visible surface hit
   → 查询附近 records
   → surface / room / visibility 结构过滤
   → normal difference
   → distance / validRadius
   → error metric / gradient correction
   → 权重足够: interpolate irradiance
   → 权重不足: hemisphere ray tracing
   → 生成 new record
   → 插入 cache
   → diffuse indirect shading

边界错误排查：

::

   输出 cached-indirect-only
   → record id / count / density overlay
   → 检查错误像素用了哪些 records
   → 检查 surfaceKey / room id
   → 检查 normal 与 valid radius
   → 检查 visibility / thin-wall 边界
   → 限制 gradient 外推
   → 必要时触发新 record
   → 最后检查 dynamic version / age

性能定位：

::

   cache lookup time
   → miss ratio
   → miss tracing time
   → record insertion / atomics
   → 每 cell 候选数量
   → 每帧新增与淘汰数量
   → cache memory / bandwidth
   → barrier / history resolve

概念辨析
--------

* **Irradiance 与 radiance**：irradiance 是表面点半球入射能量积分，没有出射方向；radiance 具有方向性。
* **Irradiance Cache 与 lightmap**：前者按实际 shading point 稀疏生成并插值，适合增量/视点相关使用；lightmap 是预先烘焙到 UV 纹理的固定表面数据。
* **Irradiance Cache 与 probe grid**：两者都复用低频光照，前者通常依附实际表面 record，probe grid 在体积空间预布点。
* **Cache hit 与 temporal history**：cache hit 是空间光照复用；history 是跨帧复用。二者都需有效性检查，但失效条件和数据结构不同。
* **Valid radius 与 filter radius**：valid radius 表示 record 的几何可信范围，不只是画面模糊半径。
* **Gradient 与 visibility**：gradient 近似平滑变化，visibility 决定两点是否共享相似入射环境；gradient 不能修复跨遮挡复用。
* **Low miss ratio 与正确性**：低 miss 可能来自过宽阈值并导致漏光；缓存优化必须同时看误差和成本。
* **Irradiance cache 与 glossy cache**：本章 cache 只保存 diffuse irradiance，方向性高光需要 radiance cache、reflection path 或其它表示。

本章结论
--------

Irradiance Caching 的核心是“只在 diffuse 低频成立的区域复用，并在几何/可见性变化处主动拒绝”。工程上先设计 record 的位置、法线、半径、surface key 和生命周期，再建立严格 lookup/rejection，最后才降低 miss ratio。合格实现应在开阔墙面稳定减少半球 tracing，在门洞、薄墙、墙角和接触区增加密度或重新采样，同时让 record density、rejection reason、成本和内存都可观察。