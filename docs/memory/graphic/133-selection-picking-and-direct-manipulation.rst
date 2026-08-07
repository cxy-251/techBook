第133章：选择、Picking 与直接操作
================================

核心知识点
----------

Picking 是一次 Screen-to-Scene Query
   输入来自鼠标、触摸或笔的二维位置，输出不应只是对象指针，而应是结构化 hit record：object id、distance/depth、world position、normal、primitive/instance id、layer、picking path 和 priority。

坐标链必须完整闭合
   Window/Client Coordinate → Viewport Local → NDC → Clip/View/World → Ray。DPI、viewport offset、scissor、Y 翻转、clip-space depth range 和矩阵约定任一失配都会造成“点 A 选 B”。

Picking Ray 是 Camera + Viewport 的派生结果
   Camera matrix、projection、viewport size 或 framebuffer scale 更新滞后时，ray 会偏离实际像素。交互错位应先查这条状态同步链，再怀疑几何求交算法。

CPU Ray、GPU ID 与 Depth Picking 回答不同问题
   CPU ray 回答几何上射线先碰到谁；GPU ID 回答当前屏幕像素实际绘出了谁；Depth picking 回答可见表面点在哪里。透明、裁剪、overlay 和 procedural geometry 下三者可能不同。

Hit Testing 负责候选裁决
   2D UI、gizmo、mesh、volume、overlay 可能同时覆盖一个像素。系统应明确 modal/tool priority、z-order、depth、layer mask、locked/hidden 与 pass-through policy。

Hybrid Scene 应先分层再排序
   常见优先级可为 ``modal tool → gizmo → 2D overlay → selectable mesh → volume → background``。优先级是工具语义，不能散落在多个事件回调中。

小对象需要 Screen-Space Tolerance
   细线、螺栓、控制点、骨骼和曲线手柄可按像素半径扩张候选范围。容差值应写入 hit record，保证命中行为可解释。

透明度与可选择性应分离
   ``opaqueOnly``、``transparentSelectable``、``passThrough``、``locked``、``hidden`` 等 pick policy 比直接用材质 alpha 决定命中更稳定。

区域选择有不同语义
   包含中心点、任意相交、完全包围、仅可见对象等策略会产生不同 selection set。工具应把 selection policy 保存进 command/undo 记录。

候选栈比单一命中更有价值
   重叠对象可保留 ``hitCandidate[]``，支持循环选择、右键候选菜单、hover preview 和调试。这样冲突策略从隐式猜测变为可见规则。

Gizmo 把屏幕拖拽转换成受约束 Transform
   输入包括 active selection、pivot、space、handle id、pointer ray、snap 和 start transform；输出是 translation/rotation/scale delta。拖拽期间必须基于固定起始状态计算。

Capture 阶段决定 Gizmo 稳定性
   Pointer down 时保存 start pointer/ray、start transform、pivot、axis、camera 和 snap。后续 move 只计算相对起始状态的增量，不能每帧重新定义基准。

World、Local、View Space 必须明确
   同一个 X 轴手柄可能表示世界 X、本地 X 或相机 X。属性面板、gizmo 和最终对象矩阵必须共享同一空间语义，否则会出现方向与数值不一致。

Preview 与 Commit 应分开
   Drag 期间只更新 preview transform 和 feedback；Pointer up 后才提交层级更新、undo record、resource rebuild。Cancel 可以无损恢复 start state。

Selection State 与 Render Feedback 应分离
   Selection model 记录 hover/selected/active/locked/hidden/multi-selected；渲染层根据状态生成 outline、stencil、overlay、label 和 gizmo。不要把选择语义直接写进材质实例。

多个反馈面必须共享同一 Selection
   Viewport 高亮、属性面板、outliner、breadcrumb 和 gizmo 必须指向相同 object/instance id。不同模块各自重新 picking 会产生状态漂移。

Interaction Mismatch 要按链路调试
   首先记录 event coordinate、viewport、DPI、NDC；再检查 camera/inverse VP；随后检查 ray/depth/object ID；然后检查 hit priority；最后检查 selection state、gizmo transform 与 outline pass。

Debug Overlay 应直接可视化证据
   点击位置十字、picking ray、hit point、candidate list、depth、object ID、active axis、pivot 和 matrix 可以把“交互感觉不对”转成具体错误层级。

关键路径
--------

Picking：

::

   pointer coordinate
   → viewport-local pixel
   → NDC
   → inverse view-projection
   → ray / id / depth query
   → hit candidates
   → hit policy
   → hit record
   → selection state
   → highlight + inspector

Gizmo Drag：

::

   selected object
   → hit gizmo handle
   → capture start state
   → pointer movement
   → project movement onto axis/plane/ring
   → preview transform
   → visual/numeric feedback
   → commit or cancel

错位排查：

::

   wrong object / wrong transform
   → input + DPI + viewport
   → camera matrices
   → ray/depth/id evidence
   → candidate priority
   → selection id
   → gizmo space/pivot
   → feedback pass

概念辨析
--------

* **Picking 与 Hit Testing**：picking 生成候选和命中证据，hit testing/policy 决定本次交互最终选择谁。
* **CPU Ray 与 GPU ID Picking**：前者按几何查询，后者按实际屏幕输出查询。
* **Depth Picking 与 Object Picking**：depth 给表面位置，不天然给完整对象语义。
* **Hover 与 Selection**：hover 是临时反馈，selection 是持久交互状态。
* **Selection State 与 Render State**：前者描述选中语义，后者负责怎样把它画出来。
* **Local Axis 与 World Axis**：轴名称相同也可能属于不同坐标空间，必须由工具模式明确指定。

本章结论
--------

选择与直接操作应按“Input Coordinate—Camera/Viewport—Picking Evidence—Hit Policy—Selection State—Manipulator Constraint—Feedback”理解。可靠交互首先保证屏幕坐标、深度、对象身份和矩阵使用同一套空间事实，再通过候选优先级和稳定 selection model 驱动 gizmo 与高亮。任何错位都应沿这条链找第一处不一致，而不是靠增大命中容差掩盖问题。