第176章：Core Web Vitals, Real User Monitoring, and User-Visible Performance
===========================================================================

核心知识点
----------

* Web 性能必须按用户可见结果判断：主要内容何时出现、交互何时反馈、页面是否稳定、失败是否及时恢复；局部 server latency 或 bundle 指标只有映射到用户体验后才有意义。
* Core Web Vitals 用 LCP、INP、CLS 分别描述主要内容加载、交互响应性和视觉稳定性，是通用用户体验入口，不是完整性能指标集合。
* LCP 的责任路径可能跨 server TTFB、CDN、HTML 输出、CSS、图片发现/优先级、字体和浏览器渲染，不能只归为“前端图片慢”。
* INP 的责任路径主要落在用户输入后的 main-thread 排队、event handler、framework update、style/layout/paint 和 presentation delay；long task 是重要证据。
* CLS 通常来自尺寸未预留、字体替换、广告/推荐位、异步内容插入和图片尺寸缺失；本质是用户已看到的布局被意外移动。
* Lab data 与 field data 回答不同问题。Lab 适合可重复机制诊断，RUM/field data 反映真实设备、网络、地区、浏览器、登录态、缓存和实验环境。
* Lab 快而可控，不代表真实用户分布；field data 真实但噪声更大，需要按 route、device、network、region、browser、release 等维度切分。
* RUM 应把性能指标与 route、release、runtime、user segment 和关键资源关联，使“页面慢”能缩小成某个版本、用户群和具体元素/交互。
* 性能分析应关注百分位和分布，不只看平均值；慢设备、弱网和尾部交互通常会被平均值掩盖。
* Performance regression 应视为 release failure。新版本显著恶化 LCP、INP、CLS、TTFB、long task、bundle 或 route transition 时，应触发门禁、灰度停止或回滚。
* Performance budget 让质量可执行，可约束 JS/CSS/font/image 大小、TTFB、LCP、INP、CLS、long task、hydration 和 route transition。
* User-visible performance 是 full-stack property：browser、CDN、server、build output、cache、image/font pipeline 与第三方脚本都可能进入关键路径。

关键路径
--------

性能诊断：

::

   user-visible symptom
   → map to LCP / INP / CLS / TTFB / custom metric
   → RUM segment by route/device/network/region/release
   → reproduce representative case in lab
   → inspect network/main-thread/rendering evidence
   → fix responsible boundary
   → verify field distribution recovers

发布门禁：

::

   build/release candidate
   → asset + lab budgets
   → preview performance checks
   → production RUM by release
   → regression threshold exceeded?
   → stop rollout / rollback / forward fix

概念辨析
--------

* **Lab Data 与 Field Data**：lab 用受控环境解释机制，field 用真实用户数据判断规模和实际体验。
* **LCP 与 TTFB**：TTFB 是响应开始时间的一部分，LCP 还包含资源发现、下载、渲染等后续成本。
* **INP 与 JavaScript Duration**：INP 包含输入排队、事件处理和下一次 paint，不等于某个 handler 自身耗时。
* **CLS 与 Animation**：CLS 关注意外布局位移，受控 transform animation 不等同于布局被推移。
* **Performance Budget 与 Performance Goal**：goal 是期望，budget 是能进入 CI/发布门禁的可检查阈值。

本章结论
--------

Web 性能应按 ``User Outcome → Field Metric → Segment → Lab Evidence → Responsible Boundary → Release Budget`` 治理。Core Web Vitals 提供共同入口，RUM 决定真实用户是否受影响，DevTools/lab 负责解释机制，最终修复必须落回具体 full-stack 边界。