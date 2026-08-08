第091章：Loading Boundary, Error Boundary, Redirect, and Missing Routes
=====================================================================

核心知识点
----------

* 路由导航中的四类一等状态是等待、失败、改道和缺失；它们都应有明确的 route/layout 边界，而不是散落成全局布尔值和临时跳转。
* Loading boundary 决定 pending 状态替换哪一层 UI。已经确认的上层上下文应尽量保留，只让尚未确认的 segment 进入 fallback。
* Error boundary 决定失败影响范围。越靠近叶子，失败越局部；越靠近根，说明更高层前提已经失效。
* Redirect 是导航控制流，不是普通数据结果。它改变目标 URL、history、后续 loader 顺序、缓存与最终用户路径。
* Missing route 可能来自无匹配 path，也可能来自资源不存在、tenant 缺失、locale 非法、权限隐藏或资源已删除。
* 好的边界在失败时保留尽可能多的有效上下文，并提供与失败层级匹配的重试、返回、切换或重新登录路径。

关键路径
--------

``Navigation → Route Match → Data/Auth Check → Loading/Error/Redirect/Missing Decision → Boundary UI → Recovery``

* 用户进入嵌套路由时，父 layout 已确认的 tenant、导航和标题应继续显示，叶子数据未完成时只替换局部内容。
* 数据 owner 负责确认 404、403、业务缺失等事实；route boundary 负责决定这些事实在页面中的展示范围。
* 临时运行失败提供重试与 request id/digest；业务缺失提供返回父资源；身份失效触发认证 redirect。
* Redirect 前明确触发者、runtime、目标 URL 信任范围、history push/replace 语义和旧数据失效规则。
* 对 mutation 后跳转，状态码/框架语义应避免刷新导致重复提交；对 canonical 迁移，目标 URL 应成为新的稳定地址。
* Missing 状态必须返回可分析语义，不能把所有异常统一成空白页或通用 500。

概念辨析
--------

* **Loading boundary vs global spinner**：boundary 绑定具体 route/data scope；全局 spinner 容易抹掉已经稳定的上下文。
* **Error boundary vs error logging**：boundary 负责用户可见降级；日志负责诊断证据，两者缺一不可。
* **Redirect vs render another component**：redirect 改变导航目标和 URL；局部渲染不改变当前位置语义。
* **Route missing vs resource missing**：前者没有可匹配 route；后者 route 存在但业务资源不存在。
* **404 vs 403**：404 表示目标不可形成有效资源页面；403 表示资源已知但当前主体无权访问。产品可因信息隐藏策略选择不同外部表达，但内部原因必须可区分。

本章结论
--------

等待、错误、重定向和缺失都是导航状态机的一部分。边界放置应依据“哪一层前提已经确定、哪一层仍在等待或失败”来决定，并尽量保留有效 layout、用户输入和导航上下文。只有 loading、error、redirect、missing 与 history、status、cache 和 recovery 同时设计，路由失败才是可恢复系统状态，而不是页面崩溃。
