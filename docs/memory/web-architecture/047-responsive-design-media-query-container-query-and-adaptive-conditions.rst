Responsive Design, Media Query, Container Query, and Adaptive Conditions
=======================================================================

核心知识点
----------

* Responsive Design 是内容、布局、交互和资源的适配策略；断点只是实现手段之一，不能替代内容优先级和状态归属判断。
* Media Query 面向 viewport、媒体类型、输入能力、DPR、用户偏好等全局环境；适合页面级布局、主题、减少动效和输入模式策略。
* Container Query 面向组件所在局部容器；适合可复用组件根据实际可用空间改变内部布局，避免把组件形态绑定到全局 viewport。
* ``srcset``、``sizes``、``picture`` 与图片宽高把显示尺寸和下载资源分开管理；资源选择也属于响应式架构的一部分。
* 字体、语言、长文本、writing mode、DPR 和资源迟到会改变几何，响应式设计必须同时考虑布局稳定性与加载成本。
* ``hover``、``pointer``、``prefers-reduced-motion``、``prefers-color-scheme`` 等条件表达用户环境，不应被 JavaScript 或 UA sniffing 重复维护成另一套真相。
* 全局环境、局部容器、资源条件和业务状态应分别归属；混成一个“mobile/desktop”布尔状态会导致组件耦合与状态碎片。

关键路径
--------

响应式决策：

``User Task → Content Priority → Global Environment + Local Container → Layout Variant → Resource Selection → Interaction Path → Stable Result``

页面级条件：

``Viewport/User Preference/Input Capability → @media → Page Layout/Theme/Motion``

组件级条件：

``Parent Available Space → query container → @container → Component Internal Layout``

图片资源：

``CSS display size + viewport/DPR + srcset/sizes → browser candidate selection → fetch/cache → decode → layout/paint``

概念辨析
--------

* **Responsive Design vs Breakpoints**：响应式是整体适配策略；breakpoint 只是某个条件阈值。
* **Media Query vs Container Query**：media query 看全局环境；container query 看局部组件空间。
* **Viewport Width vs Component Width**：桌面大 viewport 中的窄侧栏组件仍然可能只有几百像素，不能用 viewport 代替组件真实空间。
* **CSS Condition vs Business State**：viewport、container、input mode 属于浏览器环境；库存、登录、权限属于业务状态，不能混为一套样式条件。
* **Responsive Image vs CSS Resize**：CSS 只改变显示尺寸；``srcset/sizes`` 才帮助浏览器选择合适的下载资源。
* **Hover Capability vs Keyboard Access**：hover 条件只能描述指针能力；重要操作仍需 focus/keyboard 等价路径。

本章结论
--------

稳定响应式架构要按边界分配条件：页面环境交给 media query，组件空间交给 container query，资源选择交给浏览器候选算法，业务状态仍由应用拥有。先定义内容和交互目标，再定义条件，才能避免“断点越写越多、组件越复用越脆”的状态碎片。