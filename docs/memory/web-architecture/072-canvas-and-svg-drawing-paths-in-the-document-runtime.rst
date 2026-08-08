Canvas and SVG Drawing Paths in the Document Runtime
====================================================

核心知识点
----------

* Canvas 是立即模式绘制：应用保存场景状态，脚本把绘制命令写入位图；浏览器通常只看到一个 ``canvas`` 元素，不知道单个图形对象的业务含义。
* SVG 是保留模式绘制：图形以 DOM 节点存在，能够参与 CSS、事件、焦点、测试和可访问性映射。
* 选择绘制模型先看状态所有权。高频、海量、像素级或图像处理更适合 Canvas；结构清晰、节点需要独立交互和语义时更适合 SVG。
* Canvas 性能受重绘面积、对象数量、像素读写、文本/图像处理、设备像素比和主线程调度影响；高 DPI 会增加实际位图像素数量。
* SVG 性能受 DOM 节点数量、样式计算、复杂 path、filter、mask、文本布局和高频属性更新影响。
* Canvas 的命中测试、场景图、撤销、选择和可访问性往往需要应用自行维护；SVG 可复用浏览器文档模型。
* ``OffscreenCanvas`` 可把部分绘制移到 Worker，降低主线程压力，但 DOM、焦点和用户可见语义仍由主线程负责。
* 复杂图形页面常采用混合架构：密集背景或动态图层用 Canvas，少量交互标注、控制和辅助信息用 SVG/DOM。

关键路径
--------

``Canvas``：

``Data / User Input → Application Scene State → JS Drawing Commands → Canvas Bitmap → Paint / Composite → Display``

``SVG``：

``Data / User Input → SVG DOM Nodes / Attributes → Style / Geometry → Paint / Composite → Display``

高性能 Canvas 常见路径：

``Main Thread Intent → transferable data → Worker → OffscreenCanvas → bitmap / GPU-backed work → compositor → Display``

分析时依次确认：图形状态由谁保存 → 每帧更新多少对象/像素 → 是否必须独立命中和聚焦 → 是否能分层缓存或移出主线程 → 是否存在可访问性旁路。

概念辨析
--------

* **Canvas ≠ DOM 图形树**：画完一个矩形后，浏览器不会保留“这个矩形是订单 42”的节点身份。
* **SVG ≠ 免费的矢量绘制**：节点越多、样式和滤镜越复杂，DOM 与渲染成本越高。
* **CSS 尺寸 ≠ Canvas 内部像素尺寸**：``canvas.width/height`` 决定位图分辨率，CSS 只决定页面中的显示尺寸。
* **像素已经画出 ≠ 语义已经提供**：Canvas 仍需额外 DOM/ARIA 结构表达标题、状态、表格或可聚焦操作。
* **移到 Worker ≠ 整个 UI 离开主线程**：用户输入、DOM、焦点和最终页面状态仍需要主线程协调。

本章结论
--------

Canvas 与 SVG 的根本差异是图形状态放在哪里：Canvas 把结构留给应用、把结果压成位图；SVG 把结构交给浏览器文档系统。工程上应按对象规模、更新频率、交互粒度、可访问性和帧预算选择，并在复杂场景中主动组合 Canvas、SVG、DOM、Worker 与 GPU 路径。