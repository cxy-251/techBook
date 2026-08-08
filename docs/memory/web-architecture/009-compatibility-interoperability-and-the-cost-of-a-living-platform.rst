Compatibility, Interoperability, and the Cost of a Living Platform
==================================================================

核心知识点
----------

* Compatibility 是目标浏览器集合中的“可用性约束”；interoperability 是多个独立实现对同一能力形成可预测行为；两者共同决定 Web 能否作为平台运行。
* Web 是 Living Platform：标准、实现、测试和开发实践持续演化，同时大量旧内容不能轻易失效，因此平台长期承担兼容成本。
* 一个特性“写进规范”只提供语义证据；进入生产还要看多个浏览器实现、共享测试、兼容数据和项目自身目标环境。
* 浏览器差异可能发生在 API 是否存在、CSS 解析、事件顺序、安全策略、媒体能力、存储、GPU、性能和平台 bug 等多个位置。
* 兼容策略应先划分核心路径、增强路径和高成本路径，再决定 feature detection、polyfill、transpilation 或 fallback。
* 浏览器支持范围应成为显式工程状态，进入构建目标、测试矩阵、监控维度和产品降级策略，而不是发布前临时补丁。

关键路径
--------

兼容性判断路径：

``Feature/Behavior → Specification → Browser Implementations → Shared Tests → Compatibility Data → Target User Environment → Base/Enhanced Path``

页面运行分支：

``Base HTML/URL/HTTP path → capability profile → enhanced path``

能力不满足或运行失败时：

``enhanced failure → fallback/degradation → core user task remains available``

工程检查顺序：

``目标浏览器 → 核心任务依赖 → 缺失能力后的最小闭环 → 构建/运行时补偿 → 线上观测``

概念辨析
--------

* **Compatibility vs Interoperability**：前者关注项目在目标环境能否工作；后者关注不同浏览器对同一标准是否表现一致。
* **规范支持 vs 真实支持**：规范存在不等于目标浏览器已实现，更不等于复杂边界和性能特征已经收敛。
* **Polyfill vs Transpilation**：polyfill 在运行时补 API 表面；transpilation 在构建期改写源码语法或部分语言特性。
* **Feature Detection vs User-Agent Sniffing**：前者检查当前能力事实；后者根据身份推断能力，通常更脆弱。
* **旧行为保留 vs 平台停滞**：兼容历史会增加复杂度，但也是公开 Web 保持长期可访问性的代价。

本章结论
--------

Web 架构必须把兼容性当作系统约束，而不是浏览器列表。可靠的采用策略是用规范定义语义，用多实现和共享测试确认互操作性，用目标用户数据决定支持范围，再通过基础路径、增强路径和可观测 fallback 控制 Living Platform 持续演进带来的风险。