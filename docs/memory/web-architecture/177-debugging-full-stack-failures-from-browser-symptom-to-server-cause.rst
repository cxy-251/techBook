第177章：Debugging Full-Stack Failures from Browser Symptom to Server Cause
============================================================================

核心知识点
----------

* 全栈调试应从用户可见症状开始，而不是从某个服务或代码模块开始猜。白屏、旧数据、提交失败、按钮无响应、登录跳转异常分别对应不同主路径。
* 第一步是固定复现坐标：route、用户动作、实际结果、预期结果、browser/device、network、region、auth state、release、experiment 和时间窗口。
* 第二步是还原真实路径：``user action → browser event → request → auth/routing → handler → data state → cache → response → UI``。
* “请求成功”不等于“用户看到正确结果”。数据库写入成功之后，query cache、CDN、Service Worker、SSR HTML 或组件 state 仍可能展示旧副本。
* Client failure、network failure、server failure、cache failure 应分开验证。Console/DOM/Network/Performance、HTTP status/timing、server log/trace、cache hit/key/age 分别提供不同证据。
* Browser evidence 应先于 server assumption。请求是否发出、payload/credential 是否正确、response 是否被 CORS/redirect/cache 改变、UI 是否在 hydration 后覆盖数据，都能直接从浏览器侧验证。
* Server evidence 用于闭合后端路径：access log、request id、trace span、authorization result、database transaction、cache operation、queue status 和 release id 应可关联。
* 旧数据问题应按副本来源追踪：client query cache、HTTP cache、CDN、server cache、read replica、search index 或异步 read model，而不是统一称为“缓存问题”。
* “Only some users” 通常提示环境或版本分裂：浏览器版本、device class、region/CDN POP、A/B experiment、permission/tenant、cache version、灰度 release 都应进入分组。
* Release/version evidence 是现代 Web 调试关键。用户可能运行旧 HTML、新 server、旧 Service Worker、不同 edge region 或不同 schema compatibility window。
* 根因修复后，应把事故反馈到测试、日志字段、cache policy、timeout/retry、release gate 和 recovery UX 中，避免只修一个代码点。
* 调试的最终产物不是一句“找到 bug”，而是一条可验证证据链：症状如何经过哪个边界演化成用户结果，以及为何修复能阻断该路径。

关键路径
--------

全栈故障定位：

::

   record user-visible symptom + environment
   → reconstruct user action path
   → inspect browser evidence
   → classify client/network/server/cache/data boundary
   → correlate request/trace/release ids
   → identify first boundary that diverges from expected behavior
   → fix + verify end-to-end recovery

旧数据定位：

::

   confirm source-of-truth version
   → inspect response/version in browser
   → inspect client query/storage/service-worker state
   → inspect CDN/server cache key + age
   → inspect replica/index/read-model lag
   → repair invalidation/revalidation/ownership

概念辨析
--------

* **Symptom 与 Root Cause**：症状是用户看到的结果，root cause 是最早让路径偏离预期的边界或状态变化。
* **200 Success 与 Correct State**：HTTP 成功只说明请求获得成功响应，不证明持久状态、缓存和 UI 已经收敛。
* **Client Bug 与 Server Bug**：责任按证据定位，不按代码仓库或团队边界预设。
* **Cache Stale 与 Data Corruption**：前者是副本旧，后者是权威事实错误；必须先确认 source of truth。
* **Partial User Impact 与 Randomness**：只影响部分用户通常存在可分组变量，如 region、release、browser、experiment、tenant 或 cache state。

本章结论
--------

全栈调试应按 ``User Symptom → Path Reconstruction → Browser Evidence → Cross-Boundary Correlation → First Divergence → Recovery`` 执行。可靠排障不靠经验猜服务，而靠把用户动作、请求、状态、副本、版本和运行环境连接成一条可验证证据链，并把事故结果反馈回架构与发布流程。