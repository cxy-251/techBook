第124章：科学可视化基础
======================

核心知识点
----------

科学可视化先服务分析任务
   医学、地理、工程仿真、流体、金融和监控虽然数据类型不同，但都应先回答“用户要判断什么”，再选择颜色、几何、体积、箭头、曲线或多视图。视觉效果不能脱离任务语义单独设计。

数据进入 GPU 前已经带有领域含义
   Field name、unit、coordinate system、timestamp、missing value、confidence 与 threshold 会决定 buffer/texture 布局、shader 归一化、legend、LOD 和交互逻辑。渲染层不能把这些信息当成无意义浮点数。

稳定流程是 Data Ingest → Cleaning → Mapping → Geometry/Resource → Render → Interaction
   Ingest 读取格式和元数据；Cleaning 处理缺失、异常、单位和时间对齐；Mapping 把字段转成颜色/透明度/高度/方向；Geometry/Resource 把结果转成 GPU 可消费形式；Interaction 再反馈到映射或数据选择。

Mapping 是数据语义到视觉语义的关键边界
   标量适合颜色、透明度、高度、等值线；向量适合 glyph、streamline、粒子速度；分类数据适合离散符号；置信度可用透明度、边框或 hatch 表达。编码方式必须与任务匹配。

坐标系必须在数据层和渲染层之间显式转换
   经纬度、投影坐标、模型坐标、网格索引、世界坐标、clip space 不能混用。医学体素 spacing、工程网格单位、地理投影都应进入统一 metadata，并贯穿 picking、legend 和 shader。

单位错误会直接制造可信但错误的画面
   摄氏度、Pa、m/s、mm、m、时间步等单位必须在清洗阶段统一，并在 tooltip/legend 中保留。数值范围看似正常并不意味着物理含义正确。

LOD 必须声明误差边界
   地图瓦片、点云层级、仿真网格降采样、体数据多分辨率都需要说明降低细节后损失什么。LOD 的目标不是“少画一点”，而是在屏幕误差和资源预算之间做可解释取舍。

GPU 资源布局应按访问模式设计
   规则标量网格适合 texture，点/站点适合 instance buffer，非规则网格需要 vertex/index 与 field buffer，体数据适合 3D texture/brick。资源形式应由后续 shader 的实际访问方式决定。

Shader Encoding 必须保留数据范围和异常语义
   归一化、阈值、缺失值、log scale、clamp 和颜色查表都属于数据解释的一部分。把异常值简单 clamp 到正常色阶会让用户无法区分真实极值与显示饱和。

Legend 是可视化契约，不是装饰
   Legend 要明确字段、单位、范围、阈值、缺失值、质量标记和当前过滤条件。没有 legend 的颜色或箭头长度无法形成可复查分析结果。

交互应分成轻量反馈和重计算
   Hover、camera、color ramp 可只更新 overlay/uniform；空间筛选、时间步切换、数据重采样可能需要 buffer 重建或远程查询。两类更新应使用不同 latency budget。

Progressive Refinement 适合重型可视化
   用户拖动和缩放时先显示低分辨率/聚合结果，停止后再补高精度数据。系统需要显式标记当前画面是 preview、partial 还是 complete，避免低质量结果被误认为最终数据。

失败状态也是数据语义的一部分
   Missing、loading、stale、partial、error 不能都显示成空白。数据加载失败或传感器离线时，应保留上一份可信结果并显示状态，防止用户把“没有数据”理解成“数值为零”。

评价应回到准确性、可读性、响应和任务效率
   随机数值抽样、probe 对齐、legend 正确性、任务完成时间、误判率、input-to-feedback latency、P95/P99 frame time 都比“画面漂亮”更能评价科学可视化质量。

关键路径
--------

数据到画面：

::

   analysis task
   → dataset + metadata
   → clean / align / unit conversion
   → visual mapping
   → geometry / GPU resource generation
   → render passes
   → legend / overlay
   → interaction feedback

交互更新：

::

   user action
   → update filter / camera / threshold / time
   → classify light vs heavy change
   → uniform/overlay update or data rebuild
   → GPU resource diff
   → redraw
   → progressive refinement

正确性检查：

::

   raw sample
   → cleaned value
   → mapped value
   → shader input
   → rendered color/geometry
   → tooltip/legend value
   → verify all units and coordinates agree

概念辨析
--------

* **Scientific Visualization 与普通渲染**：前者以数据任务和保真为核心，后者通常以场景和视觉效果为核心。
* **Data Cleaning 与 Visual Mapping**：cleaning 修正数据事实，mapping 决定如何显示这些事实。
* **LOD 与 Data Loss**：LOD 是受控误差策略，不是无条件减少数据。
* **Missing Value 与 Zero**：缺失表示未知，零是合法数值，必须分开编码。
* **Preview 与 Final Result**：preview 服务交互响应，final result 服务完整精度，两者需要明确质量状态。
* **Legend 与 UI Decoration**：legend 是视觉编码的语义说明，属于正确性链条的一部分。

本章结论
--------

科学可视化应按“Task—Dataset/Metadata—Cleaning—Mapping—GPU Resource—Render—Interaction—Evaluation”理解。可靠系统的核心不是把更多数据画出来，而是让每个颜色、几何、数值、选择和交互反馈都能回到明确的数据语义、单位、坐标和质量状态，并最终帮助用户更准确、更快地完成分析任务。