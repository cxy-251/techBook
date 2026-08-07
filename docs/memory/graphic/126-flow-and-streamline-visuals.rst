第126章：流场与流线可视化
========================

核心知识点
----------

流场可视化的输入是 Vector Field
   二维场常写成 ``v(x,y)=(u,v)``，三维场写成 ``v(x,y,z)``。位置、方向、速度单位、采样网格和时间步必须同时保留，否则 glyph、streamline 和颜色编码会失去物理含义。

Glyph 强调局部，Streamline 强调连续路径
   箭头图适合读取某点方向和大小；流线适合观察主流向、旋涡、汇聚和绕流路径。选择哪种表达应由分析任务决定。

Streamline 是当前时间片上的瞬时切线
   它满足 ``dp/dt = v(p)``。Pathline 追踪单个粒子随时间的轨迹，Streakline 追踪连续释放粒子形成的集合。非稳态数据中三者不能混用。

向量场首先要统一坐标与单位
   经纬度、模型坐标、网格索引、世界坐标和屏幕坐标必须有明确转换。速度可能是 m/s、每时间步位移或归一化方向，积分步长必须与这些单位一致。

规则网格与非规则网格的采样路径不同
   规则网格适合 texture 与双线性/三线性插值；非规则网格通常需要 cell lookup、空间索引或预先生成 streamline。插值方法会改变边界和不连续区域的视觉结构。

派生量帮助选择视觉编码
   Speed magnitude 可用于 sequential color scale；方向角可用于 glyph rotation；divergence 表示源/汇；curl/vorticity 表示旋转结构。不同派生量应对应不同 legend 和任务。

Seed Placement 决定流线图读什么
   均匀 seed 展示全局方向，入口边界 seed 展示通道，按速度/旋度加权 seed 强调热点。Seed 太密会产生遮挡，太稀会漏掉结构。

积分器决定路径稳定性
   Euler 快但误差大；RK2/RK4 更稳定；自适应积分适合速度变化大的区域。交互模式可先粗积分，再对停留区域精细重算。

Termination Reason 应可观察
   流线可能因离开数据域、速度接近零、达到最大长度/步数、进入 mask 或满足间距规则而停止。断线调试必须能区分这些原因。

Streamline Geometry 有多种表达
   Polyline 成本低，screen-space strip 能稳定线宽，tube/ribbon 提供深度和光照线索。几何形式越复杂，顶点数、带宽和遮挡成本越高。

Arrow Glyph 更适合 Instancing
   基础箭头 mesh 可复用，每个 instance 保存位置、方向、长度、颜色或数据 ID。它把大量相同几何的 CPU submit 成本压成 instance buffer 更新。

Color Scale 必须与数据类型匹配
   大小使用 sequential，正负偏差使用 diverging，方向角使用 cyclic，分类使用 qualitative。Legend 必须标明单位、范围、clamp/p95 规则和当前 filter。

多编码组合要分清视觉责任
   背景热力图可编码速度大小，流线编码路径，箭头确认方向。若三个图层都重复编码同一量，会增加视觉噪声而非信息量。

交互更新应分离稳定资源与动态资源
   静态网格、边界、glyph mesh 可长期驻留；velocity texture、mask、streamline vertex buffer、instance transform 和 color range 是动态资源。交互只更新真正变化部分。

局部重算比全域重算更适合实时探索
   时间步切换、阈值筛选或局部 seed 修改时，应尽量只重积分受影响区域，并保留旧区域的有效结果，减少 CPU/GPU 上传和视觉闪烁。

多视图联动应共享 Selection State
   流线、热力图、直方图和属性面板通过数据 ID、时间步和 filter 共享状态。Hover 只需要高亮，提交 selection 才触发统计或重算。

质量评价要回到任务正确率
   主流向是否可读、旋涡是否容易定位、两时间步差异是否可比较、断线原因是否可解释，比“线条是否漂亮”更重要。可结合 contrast、occlusion、label density、task accuracy 与完成时间评价。

关键路径
--------

流线生成：

::

   vector field samples
   → coordinate/unit validation
   → interpolation
   → seed placement
   → integration
   → termination
   → polyline/tube geometry
   → color mapping + legend
   → render

交互更新：

::

   time/filter/seed change
   → update vector field or mask
   → identify affected region
   → recompute local streamlines
   → update dynamic GPU buffers
   → redraw linked views
   → refine when idle

质量排查：

::

   unreadable flow
   → verify vector direction/unit
   → inspect seed density
   → integration step/error
   → line width/occlusion
   → color scale/legend
   → task accuracy

概念辨析
--------

* **Streamline 与 Pathline**：前者描述瞬时向量场，后者描述粒子跨时间运动轨迹。
* **Glyph 与 Streamline**：glyph 读局部向量，streamline 读连续流动结构。
* **Seed Density 与 Data Resolution**：seed 数量控制显示路径密度，数据分辨率控制原始向量场精度。
* **Integration Accuracy 与 Visual Density**：积分更精确不代表图更可读，线条过密仍会降低判断效率。
* **Color Mapping 与 Geometry Encoding**：颜色可表达大小，几何方向/路径表达空间关系，两者承担不同信息。
* **Hover Highlight 与 Data Filter**：hover 通常只改视觉状态，filter 会改变数据集合和统计结果。

本章结论
--------

流场可视化应按“Vector Field—Interpolation—Seed—Integration—Geometry/Glyph—Color/Legend—Interaction—Quality”理解。方向错误先查坐标、单位和插值，路径异常再查 seed、积分和终止条件，性能问题则控制局部重算和动态资源更新。最终目标是让用户准确判断流向和结构，而不是生成尽可能多的线。