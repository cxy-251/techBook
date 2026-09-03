========================================================================================
第 4 节：Sliver 滚动流式协议、SliverConstraints 12 维物理约束与 Viewport 懒加载引擎
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/sliver.dart``、``packages/flutter/lib/src/rendering/viewport.dart`` 与 ``packages/flutter/lib/src/rendering/sliver_list.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/widgets/sliver.dart`` 与 ``packages/flutter/lib/src/rendering/viewport_offset.dart``
   * **核心使命**：以海量无限滚动列表（如包含 100,000 条长列表）的极致内存与帧率控制为基准，深度解构 Flutter 滚动体系的核心协议——**Sliver Protocol**。系统剖析从二维笛卡尔盒模型（``RenderBox``）到一维流式切片（``RenderSliver``）的协议跃迁、``SliverConstraints`` 12 维输入约束方程（``scrollOffset``、``overlap``、``remainingPaintExtent``、``cacheOrigin``）、``SliverGeometry`` 11 维几何状态机输出、``RenderViewport`` 双向生长布局求解、以及 ``SliverMultiBoxAdaptorElement`` 视口裁剪与 $O(	ext{Viewport})$ 常数级内存回收机制。

----------------------------------------------------------------------------------------

第一幕：从二维笛卡尔盒模型到一维流式切片（Box vs. Sliver 协议跃迁）
-------------------------------------------------------------------

在常规 UI 排版中，所有的二维控件都遵循 **Box 协议**（``RenderBox``）：
* **Box 协议的物理局限**：输入是二维空间包围盒 ``BoxConstraints(minWidth, maxWidth, minHeight, maxHeight)``，输出是单一静态尺寸 ``Size(width, height)``；
* **无限滚动的内存崩塌**：如果一个垂直列表包含 100,000 个商品卡片，若全部采用 Box 协议排版，系统必须在内存中同时为 10 万个组件分配 ``Element`` 与 ``RenderBox`` 节点并完成全局测量，内存会瞬间耗尽崩溃（OOM）。

为了解决无限滚动的物理困境，Flutter 建立了**一维流式切片协议（Sliver Protocol）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Box 协议 vs Sliver 协议的本质差异                                        │
   ├───────────────────┬──────────────────────────────────────────────────────┤
   │ 特征维度          │ Box Protocol (二维盒模型)   │ Sliver Protocol (一维流式切片)│
   ├───────────────────┼────────────────────────────┼──────────────────────┤
   │ 核心基类          │ RenderBox                  │ RenderSliver         │
   │ 输入约束          │ BoxConstraints (宽/高区间) │ SliverConstraints (12 维时空状态)│
   │ 输出几何          │ Size (绝对宽与高)          │ SliverGeometry (11 维渲染流输出)│
   │ 坐标系特征        │ 局部笛卡尔平面 (dx, dy)    │ 主轴滚动流偏移 (scrollOffset) │
   │ 内存与生命周期    │ 全量静态常驻内存           │ 视口懒加载，滑出即时回收     │
   └───────────────────┴────────────────────────────┴──────────────────────┘

在 Sliver 体系下，整个可滚动区域被切片为多个连续的 ``RenderSliver``（如固定吸顶头部 ``SliverAppBar``、动态列表 ``SliverList``、网格 ``SliverGrid``），统一由外层视口宿主 **``RenderViewport``** 负责线性拼接与可见性裁剪。

----------------------------------------------------------------------------------------

第二幕：`SliverConstraints` 12 维输入约束方程与物理意义
-------------------------------------------------------

在 ``packages/flutter/lib/src/rendering/sliver.dart`` 中，视口向每个子 Sliver 传递的不是简单的长宽，而是一个包含了滚动动力学状态的 **12 维物理约束流（``SliverConstraints``）**：

.. code-block:: text

   SliverConstraints (视口向 Sliver 注入的时空物理约束)
        │
        ├── 1. axisDirection            (主轴几何方向: down / up / right / left)
        ├── 2. growthDirection          (内容生长方向: forward 顺向 / reverse 逆向)
        ├── 3. userScrollDirection      (用户手势滚动方向: forward / reverse / idle)
        ├── 4. scrollOffset             (当前 Sliver 顶部已滚出视口上边缘的物理距离)
        ├── 5. precedingScrollExtent    (排在当前 Sliver 之前的所有 Sliver 累计占用的总滚动距离)
        ├── 6. overlap                  (上一个吸顶/悬浮 Sliver 覆盖当前 Sliver 顶部的重叠高度)
        ├── 7. remainingPaintExtent     (当前视口剩余未被填充的物理可见像素高度)
        ├── 8. crossAxisExtent          (交叉轴物理宽度，如垂直滚动时的屏幕宽度)
        ├── 9. crossAxisDirection       (交叉轴文字排版方向: ltr / rtl)
        ├── 10. viewportMainAxisExtent  (视口在主轴上的总物理可视高度)
        ├── 11. cacheOrigin             (预加载缓存区的起始负向偏移量，恒 <= 0.0)
        └── 12. remainingCacheExtent    (包含可见区与前后缓冲区的总缓存区高度)

1. `scrollOffset` 与 `remainingPaintExtent` 动态裁剪方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
设当前 Sliver 自身真实内容总长度为 $H_{	ext{content}}$：
* **可见绘制长度（`paintExtent`）物理推导**：
  当 Sliver 正在滚过视口边缘时，其实际在屏幕上绘制的物理高度受到双向截断：
  $$	ext{paintExtent} = \operatorname{clamp}\left(H_{	ext{content}} - 	ext{scrollOffset}, 0.0, 	ext{remainingPaintExtent}\right)$$
* **传递给下一个 Sliver 的可用空间方程**：
  $$	ext{remainingPaintExtent}_{	ext{next}} = \max\left(0.0, 	ext{remainingPaintExtent}_{	ext{current}} - 	ext{layoutExtent}\right)$$
视口沿着主轴自上而下顺序推进，一旦某一个 Sliver 将 $	ext{remainingPaintExtent}$ 消耗归零，后续所有排在屏幕外的 Sliver **其输入约束中的 `remainingPaintExtent` 直接变为 0.0**，从而瞬间跳过所有子项的布局与绘制。

2. `cacheOrigin` 与预加载平滑消除掉帧
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了防止用户高速滑动时因即时构建组件而产生视觉白块，视口在物理屏幕可视区外侧开辟了前后缓冲带（默认 250px）：
* ``cacheOrigin`` 始终为负值（例如 $-250.0	ext{px}$），指示当前 Sliver 必须在可见区域之前提前向前渲染 250px 的内容；
* 使得组件在真正进入用户肉眼视野前，已经由 GPU 完成了光栅化准备。

----------------------------------------------------------------------------------------

第三幕：`SliverGeometry` 11 维几何状态机输出
--------------------------------------------

每个 ``RenderSliver`` 在执行完 ``performLayout()`` 后，必须向视口提交一个 **``SliverGeometry``**，描述自身在流式空间中的几何形态：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ SliverGeometry (Sliver 向视口上报的几何状态机)                            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ • scrollExtent:      该 Sliver 在虚拟世界中占用的完整理论滚动总距离      │
   │ • paintExtent:       当前帧实际需要在屏幕物理视口内绘制的像素高度        │
   │ • layoutExtent:      该 Sliver 实际推挤后续 Sliver 布局起点的物理距离    │
   │ • paintOrigin:       绘制起点的相对偏移量 (默认 0.0)                     │
   │ • maxPaintExtent:    在无约束下能提供的最大绘制长度 (用于 ShrinkWrap)    │
   │ • maxScrollObstructionExtent: 吸顶常驻条对后续滚动区域的遮挡高度         │
   │ • hitTestExtent:     当前能接收手势点击碰撞测试的有效区域                │
   │ • visible:           当前是否可见 (paintExtent > 0.0)                    │
   │ • hasVisualOverflow: 内容是否溢出 (用于告知 Viewport 启用图层裁剪 Clip)  │
   │ • scrollOffsetCorrection: 动态偏移校正信号 (用于子项尺寸突变时重排视口)  │
   │ • cacheExtent:       在缓存区中实际消耗的像素长度                        │
   └──────────────────────────────────────────────────────────────────────────┘

1. 吸顶悬浮头部（`SliverAppBar`）的 `layoutExtent` 与 `paintExtent` 分离魔法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为什么 ``SliverAppBar`` 能够在用户向上滚动时常驻吸顶，而下方的列表却能自由滑入其底部？
* **物理秘密**：在固定吸顶模式下，当页面向上滚动，头部自身的 $	ext{scrollOffset} > 0$ 时：
  * 它向视口上报 $	ext{paintExtent} = 56.0	ext{px}$（命令 GPU 必须在屏幕顶部绘制 56px 的工具栏）；
  * 但它将推挤下一个组件的 $	ext{layoutExtent}$ 逐渐压缩至 0px；
  * 后续的列表组件依据 $	ext{layoutExtent}$ 推进布局，自然而然地滑入到了头部下方，以纯数学方式实现了华丽的吸顶与叠层效果。

2. `scrollOffsetCorrection` 解决异步高度突变
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在动态列表中，若上方的某个图片组件在异步加载完成后高度突然从 0 变为了 200px：
* 若直接重排，用户眼前的列表会发生剧烈跳动；
* Sliver 可在 ``SliverGeometry`` 中返回 ``scrollOffsetCorrection = 200.0``；
* 视口收到信号后，自动在同一帧内修正滚动偏移量并重跑布局，实现无感锚定。

----------------------------------------------------------------------------------------

第四幕：`RenderViewport` 双向生长与 `SliverMultiBoxAdaptor` 懒加载回收
-----------------------------------------------------------------------

在 ``packages/flutter/lib/src/rendering/sliver_list.dart`` 中，``RenderSliverList`` 实现了工业级的子节点懒加载与内存垃圾回收：

.. code-block:: text

   [用户快速向下滚动列表]
             │
             ▼
   1. RenderViewport 传入新的 SliverConstraints (scrollOffset 增大)
             │
             ▼
   2. SliverMultiBoxAdaptorElement 激活滑动窗口算法 (Sliding Window):
      • 计算当前落在 [scrollOffset + cacheOrigin, remainingCacheExtent] 内的 index 区间
             │
             ├─►【进入视口区项】: 调用 SliverChildDelegate.build(context, index)
             │                   动态创建 Element 与 RenderBox 挂载到树上
             │
             └─►【滑出视口区项】: 判定 index < firstIndex || index > lastIndex
                                触发 collectGarbage() ──► 将滑出的 Element 彻底卸载 (Unmount)
                                并在内存中释放其对应的 RenderBox 渲染节点！
             │
             ▼
   3. 无论列表包含 10 条还是 1,000,000 条数据:
      内存中常驻的 Element 数量恒定为: O(可视区容纳项数 + 缓冲区项数) ≈ 15 ~ 20 个！

这种精准的**视口滑动窗口回收算法**，使得 Flutter 在面对百万级数据流时，内存占用始终平稳如一，彻底摆脱了传统前端 DOM 节点的内存泄漏危机。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 06 第 4 节：``06_framework_layout_system/04_sliver_scroll_viewport.rst`` 已全量落盘完工**！系统拆解了 Box 到 Sliver 的协议跃迁、SliverConstraints 12 维输入时空约束、SliverGeometry 11 维几何状态机、吸顶 layoutExtent 与 paintExtent 分离物理机制、以及 SliverMultiBoxAdaptor 的 $O(	ext{Viewport})$ 常数级懒加载内存回收引擎。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 06 第 5 节：``06_framework_layout_system/05_render_flex_algorithm.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/flex.dart`` 源码，系统剖析 Flutter 最核心的弹性排版引擎——**``RenderFlex``（Row / Column）两遍布局测量算法（Two-Pass Layout）、主轴与交叉轴剩余空间分配方程、``FlexFit.tight`` vs ``FlexFit.loose`` 物理差异、以及基线对齐（``Baseline``）与溢出断言判定机制**。
