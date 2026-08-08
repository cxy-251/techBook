第115章：Read Path Failure Modes: Loading Hole, Overfetch, Underfetch, and Stale Data
===================================================================================

核心知识点
----------

* 读路径故障不只发生在“请求失败”；很多线上问题发生在 HTTP 成功之后：没有中间状态、返回过多、返回不足、旧数据覆盖新数据、权限变化后旧缓存继续展示。
* Loading hole 指用户意图已被系统接收，但 UI 没有解释当前阶段、有效上下文、等待区域和恢复方式；整页空白、旧内容瞬间清空、重复 skeleton 都属于典型症状。
* Overfetch 是跨边界返回超过当前 UI、当前权限和当前阶段所需的数据；它同时浪费网络、解析、内存、序列化、缓存和隐私预算。
* Underfetch 是关键路径一次读取拿不到完成主要展示/操作所需的信息，导致后续串行 round trip、N+1 请求、嵌套 loading 和 hydration 后补数据。
* Stale data 是本地或中间缓存持有的快照已落后于权威事实。问题不在“有缓存”，而在 UI 是否把 stale snapshot 伪装成当前确认事实。
* 读路径必须区分首次 loading、background refresh、参数变化、分页追加、权限重验和 retry；这些状态不能压缩成一个 ``loading`` 布尔值。
* Response shape 应围绕当前页面/权限构造显式 view model，避免把 ORM 实体、完整关系树或内部字段直接序列化给浏览器。
* 修复 overfetch 时不能简单把接口无限拆细，否则会转成 underfetch；目标是让 payload 粒度、缓存粒度和用户关键路径对齐。
* 旧请求晚返回时需要 identity/version 检查；tenant、filter、viewer 或 route 已变化的结果不能覆盖当前 UI。

关键路径
--------

``User Intent → URL/UI State → Loader/Query → Network → Server/Auth → Database/Cache → Response Shape → Client Cache → UI``

出现故障时从用户症状反推：空白/闪烁先查 loading boundary；payload 大先查 response shape 与字段权限；请求阶梯式启动先查 underfetch/waterfall；显示旧值先查 query key、freshness、invalidation、HTTP/CDN/framework cache 和旧请求提交资格。

概念辨析
--------

* **Loading hole vs slow request**：慢请求会放大等待；loading hole 的本质是等待阶段没有被正确建模和表达。
* **Overfetch vs rich API**：接口功能丰富不等于应把所有字段发给当前页面；关键是当前 contract 是否最小且安全。
* **Underfetch vs progressive loading**：非关键内容延迟属于设计；关键路径被迫串行补齐才是 underfetch。
* **Stale vs cached**：cached 表示有副本；stale 表示需要重新验证；两者都不等于错误，但 UI 不能伪装成刚确认事实。
* **Empty vs permission denied**：无结果和无权限属于不同服务器结论，不应被同一个空状态掩盖。

本章结论
--------

读路径质量由“等待是否可解释、响应是否恰到好处、快照是否属于当前上下文、旧数据是否被正确标记”共同决定。排查时必须沿完整跨层路径定位 loading、payload、dependency、cache 和 identity，而不是把所有问题归因于某个 ``fetch`` 或某个接口耗时。