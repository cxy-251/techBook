Accessibility Tree, Semantic Mapping, Focus, and Keyboard Navigation
====================================================================

核心知识点
----------

* 浏览器会根据 DOM、HTML 语义、ARIA、CSS 可见性、元素状态和当前 focus 派生 accessibility tree，再通过操作系统 Accessibility API 暴露给屏幕阅读器等辅助技术。
* 辅助技术消费的是浏览器运行时语义，不是框架组件树。组件 props 只有最终映射成正确元素、文本、attribute 和状态，才会进入可访问路径。
* 可访问对象主要由 role、name、state 和 property 构成。原生 ``button``、``input``、``select``、``a`` 等元素已经提供大量 role、keyboard 和 state 语义。
* ARIA 用于补充或表达原生 HTML 无法直接描述的关系，不应把 ``div`` + ``role`` 当成原生控件的等价替代；自定义控件还必须补 focus、键盘、disabled、value 和交互反馈。
* Focus 是键盘与辅助技术的导航状态。``document.activeElement``、Tab 顺序、弹窗 focus trap、route transition、DOM removal 与 focus restoration 都属于用户连续操作路径。
* ``aria-expanded``、``aria-controls``、``aria-describedby`` 等状态必须与真实 DOM/视觉状态同步；只更新 ARIA 或只更新视觉层都会造成双重事实。
* Keyboard path 需要与 pointer path 等价：主要操作应能通过 Tab、Enter、Space、Arrow/Escape 等符合控件语义的键盘行为完成。

关键路径
--------

语义映射：

``HTML/DOM + ARIA + CSS visibility + runtime state → browser semantic mapping → accessibility tree → platform Accessibility API → assistive technology``

键盘交互：

``Keyboard input → focus target → native/custom event behavior → state mutation → DOM/ARIA update → accessible feedback``

弹窗/路由恢复：

``trigger element → open/transition → move focus to meaningful target → interaction → close/back → restore focus``

排查顺序：先检查最终 DOM 与语义，再看 accessibility tree，再验证 focus 顺序和键盘操作，最后确认视觉反馈与辅助技术反馈同步。

概念辨析
--------

* **DOM tree vs Accessibility tree**：后者由前者及语义状态派生，通常会过滤装饰节点并增加名称、角色和关系信息。
* **Role vs Name**：role 说明“是什么”；name 说明“叫什么”。两者缺一都会降低可识别性。
* **ARIA vs Native HTML**：ARIA 主要补充语义；原生元素同时提供语义、键盘和默认行为，优先级更高。
* **Focus vs Selection/Hover**：focus 是浏览器交互当前位置；视觉 hover 或列表选中状态不等于键盘 focus。
* **Hidden visually vs Hidden accessibly**：``display:none``、``hidden``、``aria-hidden``、opacity 和屏幕外定位对渲染与 accessibility tree 的影响不同。
* **Pointer accessibility vs Keyboard accessibility**：鼠标能点击不代表键盘或辅助技术能完成相同任务。

本章结论
--------

可访问性是浏览器运行时的一条正式系统路径。语义 HTML 建立基础，ARIA 补充状态和关系，focus/keyboard 保证操作连续性，浏览器再把结果映射给辅助技术。可靠实现必须让 DOM、视觉状态、ARIA 状态和 focus 状态保持同一事实。