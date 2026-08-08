第114章：Streaming Data, Deferred Data, Placeholder UI, and Progressive Rendering
================================================================================

核心知识点
----------

* Streaming/deferred reading 把“一次页面必须等所有数据完成”改成“先交付关键数据和稳定 shell，再逐步补齐非关键分支”。
* Initial chunk 必须先回答页面身份、权限、主要任务和关键交互状态；推荐、评论摘要、配送等可独立区域才适合延迟。
* Deferred data 的判断依据是用户任务，不是接口快慢。会改变全局状态码、权限、资源存在性和交易正确性的读取，应在 initial response 前完成。
* Placeholder UI 是等待状态契约：skeleton 表达结构，fallback 文案表达异步分支状态，旧快照加刷新标记表达 revalidation；空白不构成稳定 placeholder。
* Progressive rendering 需要 data boundary 与 layout boundary 对齐；一个分支的数据完成，应只 reveal 对应 UI 区域，而不是让整个页面重新进入 loading。
* Streaming 需要 server runtime、proxy/CDN、compression、browser parser 和 UI runtime 协同；任意一层缓冲都可能让渐进输出退化成一次性显示。
* 一旦 response headers/部分 body 已提交，后续错误很难再改变全局 HTTP 状态；late error 必须在局部 boundary 内解释、重试或降级。
* Cache 需要知道快照是否完整、是否 stale、哪个 deferred 分支已完成；“页面部分可见”不能被误当作“所有数据已经确认”。

关键路径
--------

``Navigation → Server Read Plan → Critical Reads → Initial HTML/Data → Browser Parse/Render → Deferred Reads → Streamed Chunks → Local Boundary Reveal → Cache/UI Reconcile``

先完成资源存在性、权限、主标题、关键交易状态等会决定页面语义的读取；随后并行启动推荐、评论、配送等可局部失败的分支。每个 deferred branch 都要有自己的 placeholder、error 与 completion 状态。

概念辨析
--------

* **Streaming vs faster backend**：streaming 主要把等待重叠并提前交付可用内容，不保证减少总计算量。
* **Deferred vs unimportant**：deferred 表示可以晚到，不代表业务价值低；关键在于是否阻塞用户最初理解和操作。
* **Placeholder vs fake content**：placeholder 必须明确表达等待，不能伪装成已确认事实。
* **Partial UI vs partial truth**：页面可以部分显示，但交易、权限等关键事实必须在可信边界确认后才允许用户操作。
* **Late error vs initial error**：初始错误还能决定 status/整页结果；stream 已提交后的错误通常只能局部恢复。

本章结论
--------

渐进读取的核心不是“把响应切成块”，而是把关键事实、延迟事实、UI 边界和失败语义一起拆分。只有 initial shell 可解释、deferred branch 可独立、placeholder 稳定、late error 可恢复，并且缓存知道快照完整度时，streaming 才真正改善用户等待路径。