第014章：细节层次与网格简化
===========================

核心知识点
----------

LOD 是可见性阶段的资源选择
   CPU 或 GPU culling 得到候选实例后，根据相机、包围体、屏幕占比、误差预算、pass 类型和 streaming 状态选择 mesh、index range、material 或 impostor。后续顶点与片元阶段看到的已经是选定层级。

屏幕空间误差比固定距离更可靠
   同一对象空间误差在不同距离、FOV 和分辨率下对应不同像素影响。LOD 阈值应围绕 projected error、对象屏幕高度或投影面积建立；距离适合快速宽相判断，不能独立代表视觉可辨识度。

不同 pass 可以使用不同 LOD
   主视图关心轮廓、材质与法线，阴影 pass 主要关心遮挡轮廓，低分辨率反射或探针可以接受更大误差。LOD 选择应服务当前输出目标，不必让所有 pass 强制使用同一层级。

网格简化需要几何、属性和拓扑三类约束
   Position error 衡量低模偏离原表面的程度；normal、tangent、UV、color、skin weight 和 material boundary 决定着色与动画误差；boundary、hole、连通部件和硬边决定哪些拓扑变化被允许。

Edge collapse 与 QEM 是常用简化主线
   Edge collapse 逐步折叠低代价边，QEM 用局部平面二次误差估计顶点移动代价。Vertex clustering 更快但轮廓控制较弱，pair contraction 可合并分离部件。算法选择应由目标 LOD、资产类型和受保护属性决定。

LOD 生成必须从干净输入开始
   重复顶点、退化三角形、错误法线、异常材质 ID 和单位问题会污染简化结果。输入阶段要区分真正重复和 UV seam、硬边、材质分界造成的合法拆分，再设置轮廓、开口、关键关节和高频 UV 区域的保护权重。

切换稳定性需要滞回与过渡
   直接跨阈值切换会产生 silhouette pop、高光跳变、阴影变化和材质闪烁。Hysteresis 防止阈值附近来回切换，cross-fade 或 dithered transition 平滑视觉变化，但会增加过渡区 draw、fragment 或 temporal resolve 成本。

LOD 收益必须对应真实瓶颈
   降低三角形可减少 index/vertex fetch、vertex shader 和 primitive 工作；合并 submesh 可减少 CPU submission；简化材质和纹理可降低 fragment 与带宽；低层级资源可减轻 streaming。若场景 fragment-bound 或 draw-bound，只降三角形可能收益很小。

关键路径
--------

运行时 LOD 选择：

::

   frustum、distance 与 occlusion 得到候选可见集
   → 计算包围体屏幕占比
   → 将每层对象空间误差换算为像素误差
   → 按主视图、阴影、反射等 pass 调整阈值
   → 根据运动速度和遮挡状态调整预算
   → 应用 hysteresis 与 transition 区间
   → 选择 mesh、material、renderer 与 streaming page
   → 写入 draw command 或 indirect args

自动生成 LOD 链：

::

   统一单位、坐标轴、法线和材质
   → 清理退化面并区分合法属性拆点
   → 构建邻接和误差数据
   → 标记轮廓、边界、UV seam、材质边界和动画关节
   → 按目标误差或三角形预算执行简化
   → 修复 normal、tangent、skin weight、bounds 与碰撞代理
   → 写入每层误差、推荐阈值和过渡宽度
   → 固定相机、光照和动画做视觉回归

性能验证：

::

   记录未启用 LOD 的整帧与目标 draw 基线
   → 记录每层 vertex、triangle、submesh、buffer 和 material 数量
   → 比较 vertex invocation、draw time、fragment time 与 upload bytes
   → 判断当前瓶颈是 vertex、fragment、submission 还是 streaming
   → 联合调整几何、材质、纹理和实例组织
   → 只保留能降低目标瓶颈且视觉误差可接受的层级

概念辨析
--------

* **距离阈值与屏幕误差**：距离只描述相机关系；屏幕误差还包含对象尺度、FOV 和分辨率，更接近视觉可辨识度。
* **LOD 与 culling**：culling 决定对象是否参与当前 pass；LOD 决定参与时使用多复杂的表达。被选为低 LOD 的对象仍然是可见对象。
* **简化与压缩**：简化减少几何元素并可能改变形状和拓扑；压缩改变编码和位宽，通常不改变元素数量。
* **几何误差与属性误差**：前者影响位置和轮廓；后者影响法线、高光、纹理、颜色和动画，即使几何距离很小也可能明显可见。
* **Render LOD 与 collision proxy**：render LOD 随视角和像素预算变化；碰撞代理服务物理稳定性，不应随相机频繁切换。
* **Hysteresis 与 cross-fade**：hysteresis 延迟反向切换以避免抖动；cross-fade 同时混合两个层级以减少视觉跳变，成本模型不同。
* **Triangle count 与性能收益**：三角形数是输入规模指标，不是最终性能结论；收益取决于对应 pass 的瓶颈是否真的落在几何路径。

本章结论
--------

LOD 的主线是用可量化的屏幕误差换取资源成本，而非按固定距离机械降面。生产阶段应同时保护轮廓、拓扑、UV、法线、材质和动画属性，运行阶段应结合可见性、pass、运动和 streaming 选择层级，并用真实 GPU、CPU 与内存证据验证收益；只有误差、过渡和瓶颈三者同时成立，LOD 才是有效优化。