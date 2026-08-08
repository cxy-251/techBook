Mutation Write Path from User Action to Durable State
=====================================================

核心知识点
----------

* Mutation 的起点是用户意图，终点是可信持久化系统确认后的 durable state；按钮变色、pending、乐观更新都只是浏览器侧预测或过程状态。
* 一次完整写入通常穿过 ``User Intent → Browser/Form/Event → Request Encoding → Network → Server Validation → Auth/Policy → Transaction → Side Effect → Cache Invalidation → Response → UI Recovery``。
* 浏览器负责收集输入和维护交互上下文；服务器负责把不可信请求转成可信业务命令；数据库事务负责决定事实是否真正提交。
* 输入校验、身份、权限、tenant、资源版本和业务规则必须在可信 server boundary 内重新确认，客户端校验不能建立信任。
* 主事实提交后，列表、详情、搜索索引、通知、统计和缓存只是派生投影，需要通过同步更新、失效、队列或重新读取收敛。
* 写入失败时优先保护用户意图：保留草稿、提交值、mutation identity、目标资源和可恢复错误，而不是只返回“保存失败”。

关键路径
--------

``User Action`` → 收集目标资源、提交值、页面上下文与版本 → 编码 ``POST/PUT/PATCH/DELETE`` 或 action 请求 → server schema 校验 → session / permission / tenant 检查 → 事务内读取当前事实并检查版本 → 写入主事实 → 提交事务 → 处理审计、通知、队列等副作用 → 失效相关缓存与投影 → 返回 canonical result / error / redirect → 客户端只把结果应用到仍匹配的 mutation context。

关键检查点是数据库 commit：commit 前 UI 只能表示 pending 或预测；commit 后结果才可作为系统事实传播。外部副作用若无法与事务原子提交，应使用 outbox、可靠队列、幂等调用或补偿流程，避免“数据库成功、外部动作失败”形成不可解释中间态。

概念辨析
--------

* **UI change vs durable mutation**：前者属于客户端显示状态，后者需要可信持久化边界确认。
* **HTTP method vs business safety**：method 表达协议语义；幂等、权限、事务与副作用安全仍由应用实现。
* **主事实 vs 派生投影**：数据库记录是权威事实；列表、缓存、索引和计数是需要重新对齐的副本。
* **validation vs authorization**：validation 判断输入能否解释；authorization 判断当前身份能否改变目标资源。
* **失败 vs 不确定**：网络超时只证明客户端没拿到结果，不能证明服务器没有提交；不确定写入需要查询状态或幂等重试。

本章结论
--------

可靠 mutation 必须把用户意图一路保存到 durable state，再把服务器确认的事实传播回 UI。分析写入问题时，先定位事实在哪个 commit boundary 成立，再检查副作用、缓存和客户端投影是否围绕同一 mutation identity 完成收敛。