CSS Containment, Layout Invalidation, and Layout Shift
=====================================================

核心知识点
----------

* Invalidation 表示浏览器把已有计算结果标记为过期：可能是 style、layout、paint 或 composite 状态失效。它决定一次局部变化会扩散到多大范围。
* Style invalidation 关注 selector、inheritance、custom property 和 computed style；layout invalidation 关注尺寸、位置、换行、scroll range 和 containing block 等几何结果。
* DOM、class、attribute、stylesheet、图片尺寸、字体、广告、异步数据和 viewport 变化都可能触发失效；真正成本取决于它最终影响哪些 CSS 属性和布局依赖。
* CSS Containment 通过 ``contain``、``content-visibility``、``contain-intrinsic-size`` 等声明边界，帮助浏览器限制子树的 style/layout/paint 影响范围。
* Containment 是性能与语义契约，不是免费优化。声明错误会破坏 intrinsic sizing、positioning、overflow、sticky 或可见性行为。
* Layout Shift 是用户可见几何移动；一次 layout recalculation 不一定产生 shift，反过来很小的迟到内容也可能造成大面积可见位移。
* CLS 的根本治理是提前建立几何契约：图片/视频尺寸、广告占位、字体策略、异步区域 skeleton/placeholder、SSR/hydration 结构一致性。
* JavaScript “写 → 同步读几何 → 再写”会触发 forced synchronous layout，把本可批处理的失效变成多次同步计算。

关键路径
--------

渲染失效：

``DOM/CSSOM/Resource Change → Style Invalidation → Geometry Changed? → Layout → Paint → Composite → Frame``

用户可见位移：

``Late Size/Content Change → Layout Recalculation → Visible Elements Move → Layout Shift → CLS contribution``

Containment：

``Large Document → declare local boundary → browser limits dependency/invalidation scope → smaller style/layout/paint blast radius``

稳定首屏：

``Known dimensions / reserved space → initial layout → async resource arrives → fill existing box → minimal/no shift``

概念辨析
--------

* **Style Invalidation vs Layout Invalidation**：前者重算样式结果；后者重算几何依赖。
* **Layout Invalidation vs Layout Shift**：layout invalidation 是浏览器内部工作；layout shift 是用户看到的元素位置变化。
* **Containment vs Isolation**：containment 是布局/样式/绘制优化边界，不是安全隔离或业务状态隔离。
* **``content-visibility`` vs Lazy Loading**：前者主要让浏览器跳过屏外子树的渲染工作；lazy loading 主要改变资源何时加载，两者可组合但职责不同。
* **CLS vs 所有页面移动**：用户主动交互后预期发生的布局变化和加载期意外位移含义不同；指标和产品体验都要结合触发原因判断。
* **Custom Property vs 成本类型**：变量更新本身不决定成本；用于 ``color`` 可能只重绘，用于 ``gap/width/font-size`` 则可能触发布局。

本章结论
--------

页面稳定性要从“谁拥有几何”开始治理。先减少不必要的失效扩散，再用 containment 收窄局部子树，最后让图片、字体、广告、异步内容和 hydration 在首屏前就拥有稳定尺寸契约。性能问题看 invalidation，体验问题看 layout shift，两者必须在同一条路径上分析。