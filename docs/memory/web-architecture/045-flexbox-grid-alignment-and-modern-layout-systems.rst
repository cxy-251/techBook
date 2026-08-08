Flexbox, Grid, Alignment, and Modern Layout Systems
==================================================

核心知识点
----------

* 现代布局应先识别约束，再选择布局模型。Flexbox 主要解决一维空间分配，Grid 主要解决二维轨道与区域关系。
* Flexbox 沿 main axis 分配剩余空间，并沿 cross axis 对齐；``flex-basis``、``flex-grow``、``flex-shrink``、``min-width/min-height`` 与 intrinsic size 共同决定最终尺寸。
* Grid 先建立 rows、columns、tracks、lines、areas，再放置 item；``fr``、``minmax()``、``auto-fit/auto-fill`` 和 intrinsic size 决定轨道如何伸缩。
* Box Alignment 提供跨布局模型的统一对齐语言：``justify-*``、``align-*``、``place-*``、``gap``。使用前必须先确定当前轴和 alignment subject。
* ``min-width: 0`` / ``minmax(0, 1fr)`` 常用于解除内容的默认最小尺寸约束，避免长文本、表格或代码把 flex/grid 容器撑破。
* CSS 可以改变视觉 placement，但 DOM source order 仍承担阅读顺序、焦点顺序和无样式语义；布局重排不能破坏可访问顺序。

关键路径
--------

布局模型选择：

``界面约束 → 一维分配? → Flexbox``

``界面约束 → 二维轨道/区域? → Grid``

Flexbox：

``container size → item base size → grow/shrink → main-axis distribution → cross-axis alignment → final boxes``

Grid：

``container size → explicit/implicit tracks → track sizing → item placement → alignment → final boxes``

大型页面常见组合：

``Page/Grid shell → local Flex rows/columns → gap/alignment → responsive constraints``

概念辨析
--------

* **Flexbox vs Grid**：Flex 更偏内容驱动的一维分配；Grid 更偏容器驱动的二维轨道。
* **Main Axis vs Inline Axis**：Flex 主轴由 ``flex-direction`` 决定；Grid 的 justify/align 更多跟 writing mode 的 inline/block axis 对应。
* **``gap`` vs Item Margin**：``gap`` 把兄弟项间距责任放在容器；margin 把外部间距散到子元素，复用时更易冲突。
* **Visual Order vs DOM Order**：CSS ``order`` 或 grid placement 可以改视觉位置，不应依赖它重写语义、键盘或辅助技术顺序。
* **``1fr`` vs 无限可缩**：``1fr`` 仍受 track 最小尺寸和内容 intrinsic size 约束；必要时使用 ``minmax(0, 1fr)``。

本章结论
--------

布局系统的稳定性来自让 CSS 直接表达约束：一维关系交给 Flexbox，二维结构交给 Grid，对齐和间距交给容器级 alignment。JavaScript 应负责状态与交互，不应长期承担浏览器已经能完成的几何计算。