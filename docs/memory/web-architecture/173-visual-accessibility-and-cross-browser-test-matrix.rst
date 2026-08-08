第173章：Visual Accessibility and Cross-Browser Test Matrix
============================================================

核心知识点
----------

* Visual regression 保护最终用户可见输出，覆盖布局、间距、字体、主题、换行、重叠、截断、图片和响应式状态等 DOM 断言难以发现的问题。
* 视觉测试的输入不仅是 HTML/CSS，还包括 viewport、DPR、浏览器版本、OS、字体、图片、时间、动画、随机内容和网络资源；这些条件必须尽量固定。
* Screenshot baseline 本质是 UI contract。更新基线应经过 review，确认用户可见变化是否合理，而不是机械消除测试失败。
* Accessibility test 保护 semantic/interaction path：role、accessible name、keyboard navigation、focus order、ARIA state、form error、landmark 和状态通知都属于用户契约。
* 自动化 a11y scanner 只能发现一部分规则性问题，无法替代真实键盘路径、读屏顺序、复杂 widget 操作和认知可理解性检查。
* 视觉正确不代表可访问。一个按钮看起来正常，仍可能缺少语义名称、错误焦点、错误禁用状态或无法被键盘操作。
* Cross-browser test 保护平台假设。Chrome、Safari、Firefox、移动浏览器和 WebView 在 CSS、input、font、storage、privacy、media 与 Web API 上可能存在差异。
* Browser/device matrix 应按真实用户占比和 capability risk 选择，而不是追求组合数量；关键 API、输入方式、低性能设备和移动 viewport 应优先。
* User-visible test 不应只覆盖 happy path，还要覆盖 loading、empty、error、offline、slow network、permission denied、expired session 和 recovery。
* 稳定测试应优先使用 fixture、固定时钟、禁用动画、受控字体/图片和明确 viewport，减少与产品逻辑无关的视觉噪声。
* 同一用户路径可组合 DOM 语义断言、截图、a11y scan 与跨浏览器 E2E；各自保护不同层面，不应互相替代。

关键路径
--------

用户可见测试设计：

::

   critical user path
   → enumerate visible/interactive states
   → stabilize data/time/fonts/viewport
   → DOM + interaction assertions
   → visual baseline
   → accessibility checks
   → browser/device risk matrix
   → failure/recovery states

Accessibility 路径：

::

   semantic HTML / ARIA
   → accessibility tree
   → keyboard/focus path
   → state/error announcement
   → assistive technology behavior

概念辨析
--------

* **DOM Test 与 Visual Test**：DOM test 证明结构/语义存在，visual test 证明最终渲染结果没有被破坏。
* **Automated A11y 与 Human A11y Review**：自动化适合规则检查，真实任务路径仍需键盘、读屏和人工场景验证。
* **Cross-Browser 与 Cross-Device**：浏览器差异关注平台实现，设备差异还包含性能、输入、屏幕和网络条件。
* **Stable Baseline 与 Pixel Perfection**：稳定基线用于识别重要视觉回归，不要求忽略所有合理渲染细节差异。
* **Happy Path 与 User Contract**：用户契约包括失败、等待和恢复状态，不只包括成功页面。

本章结论
--------

用户可见质量应按 ``Rendered Output → Semantic Accessibility → Browser Capability → Device Risk → Failure Recovery`` 验证。视觉、a11y 和跨浏览器测试共同保护 browser boundary，重点不是扩大矩阵，而是覆盖最可能破坏真实用户任务的环境和状态。