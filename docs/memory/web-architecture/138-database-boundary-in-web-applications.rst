第138章：Database Boundary in Web Applications
===============================================

核心知识点
----------

* Database boundary 是用户临时交互变成 durable state 的位置。输入框、component state、request payload 和 optimistic UI 都不是持久事实；只有成功提交到权威持久化系统后，状态才可跨刷新、设备和进程恢复。
* Web 应用通常把 database 作为 source of truth；browser cache、query cache、server memory、search index 和 CDN 都是临时或派生副本，必须定义来源、刷新和冲突规则。
* 数据库访问必须经过可信 runtime。Browser 只能提交意图，server/受控 backend 负责身份、tenant、authorization、validation、query shape 与错误裁剪。
* 数据访问不能把原始浏览器输入直接拼成查询。查询结构、tenant filter、资源归属和返回字段都应由可信代码控制，并使用参数化查询或等价机制。
* Query shape 决定 UI 能知道什么。字段、关联、聚合、排序和分页会直接塑造 loading state、API contract、缓存结构与权限暴露面。
* 原始 database row 不应自动成为 browser response。应通过 view model / DTO 显式裁剪当前用户当前页面真正可见的字段。
* Database boundary 也是 security boundary：读取和写入都必须携带 subject、tenant、resource ownership、permission 与字段级暴露规则。
* Database constraint、transaction、index 与 concurrency control 是最终数据现实。Framework、ORM 和类型系统可以包装它们，不能取消它们。
* Persistence error 会变成用户可见一致性问题，例如 timeout、unique conflict、deadlock、connection exhaustion、replication lag、migration mismatch 会表现成保存失败、重复记录或 stale UI。
* Source of truth 必须按业务事实逐项定义。订单状态可能由本地数据库拥有；支付最终状态可能由 payment provider 拥有，本地库只保存镜像与同步状态。

关键路径
--------

一次持久化写入：

::

   browser intent / form state
   → server request boundary
   → authentication + tenant + authorization
   → input/domain validation
   → data access layer
   → database transaction + constraints
   → durable result / row version
   → invalidate derived caches
   → return user-scoped view model
   → browser reconciles temporary state

状态所有权判断：

::

   browser draft      = temporary user interaction
   client/server cache = derived copy
   database            = durable application fact
   external provider   = external-owned fact when applicable

概念辨析
--------

* **Browser State 与 Durable State**：前者服务当前交互，后者可在刷新、重启和跨设备后恢复。
* **Database 与 Cache**：database 保存权威事实，cache 保存可失效副本；命中更快不代表更权威。
* **Query Shape 与 Table Shape**：数据库表服务持久化模型，query/view model 服务具体读取路径，两者不应机械一一暴露。
* **Data Access 与 Authorization**：能执行查询不代表有权读取资源；tenant 和 resource filter 应进入可信数据路径。
* **Source of Truth 与 Single Copy**：权威位置可以只有一个，但系统仍可存在多个副本；关键是冲突时谁裁决。

本章结论
--------

Web 数据路径应按 ``Temporary Intent → Trusted Policy → Durable Write → Derived Copies → UI Reconciliation`` 阅读。数据库边界的核心价值不是“保存数据”，而是定义哪些事实真正成立、由谁保护、失败后如何恢复，以及其他副本如何重新与权威状态一致。
